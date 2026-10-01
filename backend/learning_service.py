"""Epic 3「學習閉環」的**服務層**：哈希鏈純函數 + 庫層薄封裝 + 單遍鏈校驗（零 SQL、零 sqlite3）。

對齊：docs/epic3-learning-design-v1.md
  §2.3  canonical 口徑（`sort_keys=True` / `separators=(",", ":")` / `ensure_ascii=False`；
        payload 頂層 9 鍵 = 參與哈希的鍵集合；**明文姓名不入鏈**）
  §2.4  A3 鏈節指紋公式 + `GENESIS_HASH`（64 個 ASCII '0'）+ 單遍 / `seq` 升序 / 零額外狀態的校驗算法
  §2.5  A2 `seq` 語義：按老師單鏈、從 1 起、步長 1、不跳號 / 不複用；分配 = `MAX(seq) + 1`
  §2.6  索引（`uq_agent_learning_events_teacher_seq` 是併發兜底：衝突即失敗，**絕不靜默丟事件**）
  §4-② 口徑凍結：本文件的常量與公式**一經落地即為見證入口復用基準**，變更須 CTO 單獨裁決 + 數據遷移方案
  §6    A4 總閘 `LEARNING_ENABLED`（照 template / agent_stage / lineage 三套慣例：on/1/true/yes、現讀、默認 off）

CTO 2026-09-30 step 3.2 裁決（本文件的施工依據）：
  · 本步 = 骨架 + 純函數，**零接線**：不碰 `insert_draft` / `update_draft_content` / `template_api` /
    `agent_stage_service._evaluate`（那些屬 3.3 / 3.4）；本文件今天只被 `test_learning.py` 調用。
  · 模組導入期**零副作用**：不讀檔、不讀庫、不讀 env（flag 由 `learning_enabled()` 每次現讀）。
  · 分層（裁決 B / 補充 2）：**SQL 全在 `database.py`**（4 個庫層原語 + 1 個列白名單），
    本文件**零 SQL 字面量 + 零 `import sqlite3`** —— 四條庫層原語只做薄封裝（`_db()` 函數內延遲 import）。
    理由：Epic 1 / Epic 2 的分層就是「SQL 全在 database.py、服務層純計算」；Epic 4 `lineage_service`
    直接寫 SQL 屬**偏離**，已由 CTO 登記 **TD-018**，本 Epic 不跟隨、也不動它。
  · 源碼級守護（補充 3）：零 `import sqlite3`、零 SQL 關鍵字字面量、零 `_stage_audit` / `require_capability`
    調用；另加本 Epic 自己的紅線：零 `current_stage` 調用（Epic 2 §2.2 的唯一能力閘門，全倉白名單只含
    `agent_stage_service.py` / `agent_stage_api.py`）、零寫 `agent_stage_log`（A6：兩張表、兩條流，§3.3）。

CTO 2026-09-30 step 3.3-a 裁決（本文件的施工依據 · **追加段**）：
  · 本步 = **差異記錄純函數 + 5 個事件寫入入口**：`compute_content_diff()`（+ `split_sections()` /
    `split_section_field()` 兩個純助手）與 5 個 `record_*` 薄封裝。**仍然零接線** ——
    本文件今天依然不被任何生產模組 import（庫層落點 / 服務層適配器 / 接口層屬 3.3-b → 3.3-f）。
  · R10 口徑（CTO 批）：`field` / `before_hash` / `after_hash` / `wording_changed` 三件事的定義逐條寫在
    `compute_content_diff()` 的 docstring；`field` 的包裹符剝法與 `agent_stage_service._split_heading()`
    **逐字同一套**（差別只是本文件**不 import 它** —— 見下一條）。
  · CTO 追加 1（方案 c，import 方向）：**歸一化在調用方** —— 調用方先跑
    `agent_stage_service._normalize_metric_text()`，再把結果傳進 `compute_content_diff()`。
    理由：本文件保持「純函數 + **零 import 生產模組**」（兩個方向的循環依賴都不成立）。
    代價（明寫在 docstring，不藏）：傳未歸一化的原文**不保證結果穩定**（用例反向釘住）。
  · CTO 追加 2（守護歸 3.3-f）：「庫層 → 服務層轉發點唯一」由 `database.py` 的模組級 / 函數體級
    源碼守護負責，本文件不摻和。
  · flag / 存儲探針 / 吞異常三件事只在 `_record_event()` 裡各判**一次**（5 個 `record_*` 只負責拼
    `detail`）—— 「同一個判斷只許有一份實現」，理由見該函數 docstring。

啟用方式（本機 / 生產，PowerShell；**默認 off**）：
    $env:LEARNING_ENABLED = "on"
"""
import hashlib
import json
import os
import re
from datetime import datetime

# ---------------------------------------------------------------------------
# §2.3 / §2.4 口徑常量：**與遷移 `0006` 逐字一致**
# ---------------------------------------------------------------------------
# 本段是「遷移 0006（凍結見證）↔ 服務層（實現）」的**雙向對齊**點：`test_learning.py` 從**兩邊**斷言
# （遷移側的守護用例在 `test_migrations.py` 的 0006 組）—— 防的正是「設計↔實現單側漂移」。
GENESIS_HASH = "0" * 64         # 創世哈希 = 空鏈的「上一條鏈節指紋」（64 個 ASCII '0'）
PAYLOAD_HASH_ALGO = "sha256"    # 摘要算法（唯一允許值）
PATIENT_NAME_HASH_LEN = 16      # 【A5】patient_name_hash = sha256(patient_name)[:16]

CANONICAL_SORT_KEYS = True
CANONICAL_SEPARATORS = (",", ":")
CANONICAL_ENSURE_ASCII = False

# 參與哈希的鍵集合 = payload 的**頂層 9 鍵**（`detail` 內部鍵參與哈希但隨事件類型演進，§3.2）
PAYLOAD_TOP_LEVEL_KEYS = (
    "seq",
    "event_type",
    "teacher_name",
    "created_at",
    "lineage_id",
    "patient_name_hash",
    "draft_id",
    "template_id",
    "detail",
)

# §3.1 五類事件（順序 = 登記順序，**不是**先後約束；枚舉凍結：不得新增 / 改名 / 縮寫）
EVENT_TYPES = (
    "template_configured",
    "draft_generated",
    "draft_modified",
    "learning_event_emitted",
    "agent_updated",
)

# 鏈校驗返回碼（§2.4 偽碼的三個失敗原因 + 成功）
CHAIN_OK = "ok"
CHAIN_SEQ_GAP = "seq_gap"
CHAIN_PAYLOAD_TAMPERED = "payload_tampered"
CHAIN_LINK_BROKEN = "link_broken"


# ---------------------------------------------------------------------------
# §6 A4 總閘 flag（與 Epic 1 / Epic 2 / Epic 4 三套 flag **逐字同款**，默認 off）
# ---------------------------------------------------------------------------
LEARNING_ENABLED_VALUES = ("on", "1", "true", "yes")


def learning_enabled():
    """總閘 `LEARNING_ENABLED`：**每次調用現讀**（便於灰度切換 / 測試，不必重啟 uvicorn）。**默認 off。**

    flag off = 與今天 1:1（§6）：不寫事件、不分配 `seq`、不改任何既有響應字段、既有 SQL 逐字節不變。

    **本函數只讀環境變量**：不讀庫、不打日誌、不拋異常、不緩存（讀到的永遠是當前 env）。
    """
    return os.environ.get("LEARNING_ENABLED", "off").strip().lower() in LEARNING_ENABLED_VALUES


# ---------------------------------------------------------------------------
# 庫層薄封裝的唯一入口（SQL 全在 `database.py`）
# ---------------------------------------------------------------------------
def _db():
    """延遲取 `database` 模組：`DB_PATH` / `row_factory` / **全部 SQL** 仍由 `database.py` 單點持有。

    `import database` 恆在**函數體內**（與 `agent_stage_service._store_connection()` /
    `lineage_service` 同口徑）：模組載入期不碰庫，兩個方向的循環依賴都不成立。

    本模組**只**允許碰四個庫層原語（`next_seq` / `get_last_learning_event` / `get_learning_events` /
    `insert_learning_event`）—— 「只讀 + 只增」由此在源碼級成立（`test_learning.py` 有白名單守護）。
    """
    import database
    return database


# ============================================================================
# 【純函數】§2.3 canonical 口徑 + §2.4 鏈節指紋 + §5.2 A5 姓名哈希
# ----------------------------------------------------------------------------
# 這一節**零 SQL、零狀態、零副作用**：同樣入參永遠得到同樣結果（可被測試寫死期望字面量）。
# 口徑若變 = 已落庫的鏈全部驗不過 → 走 §4-② 的凍結變更流程（CTO 裁決 + 數據遷移方案）。
# ============================================================================
def sha256_hex(text):
    """`sha256` 摘要（小寫 hex）。輸入恆為 `str`，**顯式 `utf-8`**（§2.3：禁用平台默認編碼）。"""
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def canonical_json(payload):
    """§2.3 canonical 口徑：三個參數**逐字**取自上面的常量（`sort_keys` / `separators` / `ensure_ascii`）。

    · `sort_keys=True` → 鍵序無關（同 payload 換鍵序 = 逐字節同結果）；
    · `separators=(",", ":")` → **零多餘空白**（默認的 `", "` / `": "` 會讓同一 payload 有第二種字節）；
    · `ensure_ascii=False` → 中文原樣輸出（配合上面的顯式 `utf-8`）。
    """
    return json.dumps(
        payload,
        sort_keys=CANONICAL_SORT_KEYS,
        separators=CANONICAL_SEPARATORS,
        ensure_ascii=CANONICAL_ENSURE_ASCII,
    )


def compute_payload_hash(payload):
    """§2.3 payload 哈希 = `sha256(canonical_json(payload))`。

    落庫時 `payload_json` 必須存**這條 canonical 字串本身**（`insert_learning_event()` 就是這麼做的）
    → 鏈第 1 層校驗 `sha256_hex(row["payload_json"]) == row["payload_hash"]` 才成立
    （**不是**「存下來再 canonically 重排一次」，那會讓證據的權威源變成代碼而不是字節）。
    """
    return sha256_hex(canonical_json(payload))


def compute_link_hash(seq, event_type, payload_hash_value, prev_hash):
    """§2.4 A3 鏈節指紋 = `sha256(canonical_json({seq, event_type, payload_hash, prev_hash}))`。

    **值語義（設計 §2.4「列名命名留痕」，凍結不改）**：本函數的產物就是 `agent_learning_events.prev_hash`
    這一列要存的值 —— 該列既接收「上一節」的輸入，也承載本節的累積結果（列名不是「上一行的哈希」的字面義）。
    因此第 n 條的鏈接是：

        row_n.prev_hash = compute_link_hash(n, et_n, ph_n, row_{n-1}.prev_hash)

    第 1 條以 `GENESIS_HASH` 起算。參數名沿用設計偽碼的 `prev_hash`（不改成 `prev_link`），
    免得「同一件事兩個名字」。
    """
    return sha256_hex(canonical_json({
        "seq": seq,
        "event_type": event_type,
        "payload_hash": payload_hash_value,
        "prev_hash": prev_hash,
    }))


def compute_patient_name_hash(patient_name):
    """【A5】`patient_name_hash = sha256(patient_name)[:16]`；**明文姓名不落庫、不入鏈**。

    · `None` → 按空串歸一（`str()` 兜底，不拋）；空名 → `sha256("")[:16]`（固定值，用例寫死期望）；
    · 返回值恆為 `PATIENT_NAME_HASH_LEN`（16）個小寫 hex 字符 —— 長度本身就是「明文不入鏈」的見證。
    """
    text = "" if patient_name is None else str(patient_name)
    return sha256_hex(text)[:PATIENT_NAME_HASH_LEN]


def build_payload(seq, event_type, teacher_name, created_at, lineage_id, patient_name_hash,
                  draft_id, template_id, detail):
    """按 §2.3 組出**恰好 9 個頂層鍵**的 payload（鍵集 == `PAYLOAD_TOP_LEVEL_KEYS`，缺值用空值哨兵）。

    三條硬規則（§2.3）在這裡落地：
      · **9 鍵恆存在**：本函數只產出這 9 個鍵（多 / 少一個都會被用例的鍵集斷言釘住）；
      · payload 內**不得出現 `None`**：`detail` 的空值哨兵由調用方（3.3 的事件構造）自負，
        本函數只把 `None` detail 兜成 `{}`；
      · **數值類型歸一**：`seq` / `draft_id` / `template_id` 一律 `int`（禁 `float` / 字串數字）。
    """
    return {
        "seq": int(seq),
        "event_type": str(event_type),
        "teacher_name": str(teacher_name),
        "created_at": str(created_at),
        "lineage_id": str(lineage_id or ""),
        "patient_name_hash": str(patient_name_hash or ""),
        "draft_id": int(draft_id or 0),
        "template_id": int(template_id or 0),
        "detail": detail if detail is not None else {},
    }


# ============================================================================
# 【庫層原語的薄封裝】四條：next_seq / get_last_learning_event / get_learning_events / insert_learning_event
# ----------------------------------------------------------------------------
# 本節每個函數都**只有一行轉發**：SQL、連接、`row_factory`、`ValueError` 白名單全在 `database.py`
# （裁決 B：Epic 1 / Epic 2 的分層；本文件零 SQL 字面量 —— 用例以 AST 掃描**代碼裡的字符串常量**守住，
# docstring / 註釋裡「提到」SQL 是允許的，與 Epic 2「提到可以、import 不行」同一口徑）。
# ============================================================================
def next_seq(teacher_name):
    """§2.5-2：該老師鏈上的下一個 `seq`（`COALESCE(MAX(seq), 0) + 1`；首條 = 1）。

    只讀、不分配、不預留：真正的兜底是索引 `uq_agent_learning_events_teacher_seq`
    —— 兩個調用方搶到同一個號時後到者 `IntegrityError`，**不靜默丟事件**（§2.5-3）。
    """
    return _db().next_seq(teacher_name)


def get_last_learning_event(teacher_name):
    """該老師鏈上 `seq` 最大的一行 → `dict`；一次都沒有 → `None`（= 空鏈，以 `GENESIS_HASH` 起鏈）。"""
    return _db().get_last_learning_event(teacher_name)


def get_learning_events(teacher_name, limit=20):
    """按 `seq` **升序**（= 鏈序）讀該老師的事件 → `[dict]`；`limit=None` / `<= 0` → 全量。

    全量只有鏈校驗需要（`LIMIT` 會靜默截斷 → 缺行被誤判成 ok）；倒序 / 時間窗展示由調用方自行排序。
    """
    return _db().get_learning_events(teacher_name, limit)


def insert_learning_event(teacher_name, event_type, payload, lineage_id="", patient_name="",
                          draft_id=0, template_id=0, seq=None, created_at=None):
    """寫入一條學習事件（**只增**）→ 返回新行 `id`。**本文件唯一的寫入口。**

    `payload` = **本事件的特化載荷**（= 設計 §3.2 的 `detail` 對象，例如 `draft_generated` 的
    `{"template_version": 2, "content_hash": "...", "degraded": False}`）；其餘 8 個頂層鍵由本函數按
    §2.2 / §2.3 組裝：

      · `seq`：缺省由 `next_seq()` 分配；顯式傳入則**必須**等於「庫內最後一條 + 1」，
        否則 `ValueError`（§2.5 不跳號 / 不複用 —— 寧可拒絕寫入，也不留一條斷鏈）；
      · `patient_name_hash` = `compute_patient_name_hash(patient_name)` —— **明文姓名只用於算哈希，
        不落庫、不入鏈**（A5）；
      · `lineage_id` 僅審計標註（**不**做師門過濾；按師門檢索事件本 Epic 不做，§11-5）；
      · `payload_json` 存 `canonical_json()` 的產物、`payload_hash` = 它的 `sha256`（第 1 層自洽）；
      · `prev_hash` 存本行的**鏈節指紋**（`compute_link_hash(...)`，見該函數的命名留痕說明）。

    四條邊界：
      · `event_type` 必須在 `EVENT_TYPES` 白名單內（枚舉凍結，§3.1）→ 否則 `ValueError`；
      · `teacher_name` 非空（按老師單鏈，§2.5）→ 否則 `ValueError`；
      · **不判 flag**：本函數是原語，`if not learning_enabled(): return` 屬調用點（3.3）的職責
        —— 同一個總閘只許有一處判斷；
      · **不吞庫異常**：`IntegrityError`（併發搶號）原樣冒泡，「重試或顯式報錯」由調用點決定。
    """
    if not teacher_name:
        raise ValueError("insert_learning_event 必須給 teacher_name（按老師單鏈，§2.5）")
    if event_type not in EVENT_TYPES:
        raise ValueError("未知 event_type：%r（白名單見 EVENT_TYPES，§3.1）" % (event_type,))

    last = get_last_learning_event(teacher_name)
    expected_seq = 1 if last is None else int(last["seq"]) + 1
    if seq is None:
        seq = next_seq(teacher_name)
    if int(seq) != expected_seq:
        raise ValueError(
            "seq 必須連續：庫內應為 %d，收到 %r（§2.5 不跳號 / 不複用）" % (expected_seq, seq)
        )
    seq = int(seq)

    created_at = created_at or datetime.now().isoformat()
    payload_dict = build_payload(
        seq, event_type, teacher_name, created_at, lineage_id,
        compute_patient_name_hash(patient_name), draft_id, template_id, payload,
    )
    payload_json = canonical_json(payload_dict)
    payload_hash = sha256_hex(payload_json)          # == compute_payload_hash(payload_dict)
    prev_link = GENESIS_HASH if last is None else last["prev_hash"]
    link = compute_link_hash(seq, event_type, payload_hash, prev_link)

    return _db().insert_learning_event(
        teacher_name, event_type,
        seq=seq,
        lineage_id=payload_dict["lineage_id"],
        patient_name_hash=payload_dict["patient_name_hash"],
        draft_id=payload_dict["draft_id"],
        template_id=payload_dict["template_id"],
        payload_json=payload_json,
        payload_hash=payload_hash,
        prev_hash=link,
        created_at=created_at,
    )


# ============================================================================
# 【鏈校驗】§2.4 單遍 / `seq` 升序 / 零額外狀態
# ============================================================================
def verify_learning_chain(teacher_name):
    """校驗該老師的整條鏈 → `{"ok", "checked", "first_bad_seq", "reason"}`。

    兩層判定（**逐字**照設計 §2.4 偽碼，只是把「返回值三元組」包成 dict 便於接口層直出）：
      1. `sha256_hex(row["payload_json"]) != row["payload_hash"]` → `payload_tampered`（載荷字節被改）；
      2. `row["prev_hash"] != compute_link_hash(row["seq"], row["event_type"], row["payload_hash"],
         expected_prev)` → `link_broken`（鏈斷 / 中間行被刪 / 換序）；
      另加 `row["seq"] != expected_seq` → `seq_gap`（跳號 / 亂序 / 缺行）。

    三條口徑：
      · **全量讀**（`limit=None`）：截斷會讓「尾行被刪」驗不過來；
      · 空鏈 → `{"ok": True, "checked": 0, "first_bad_seq": None, "reason": "ok"}`
        （`checked == 0` 即「沒有可驗的鏈節」，與設計偽碼的返回值一致）；
      · **不吞異常**：表缺失 / 庫不可讀屬「存儲沒就緒」，由 `learning_store_ready()` 與接口層 503 回答，
        這裡讓它原樣冒泡（「鏈壞了」與「庫沒準備好」必須分開，與 `lineage` 同口徑）。

    **明示殘餘（§2.4「未覆蓋」/ §11-3，本步不解決）**：八個投影列被**單獨**修改（不動 `payload_json`）
    時本函數驗不出來 —— 強校驗（從投影列 + `detail` 重建 canonical payload 逐字節比對）是 3.2 的
    待裁決項，未獲放行前不實現。
    """
    rows = get_learning_events(teacher_name, None)
    expected_seq = 1
    expected_prev = GENESIS_HASH
    checked = 0
    for row in rows:
        if int(row["seq"]) != expected_seq:
            return {"ok": False, "checked": checked, "first_bad_seq": row["seq"],
                    "reason": CHAIN_SEQ_GAP}
        if sha256_hex(row["payload_json"] or "") != row["payload_hash"]:
            return {"ok": False, "checked": checked, "first_bad_seq": row["seq"],
                    "reason": CHAIN_PAYLOAD_TAMPERED}
        if row["prev_hash"] != compute_link_hash(row["seq"], row["event_type"],
                                                row["payload_hash"], expected_prev):
            return {"ok": False, "checked": checked, "first_bad_seq": row["seq"],
                    "reason": CHAIN_LINK_BROKEN}
        expected_seq += 1
        expected_prev = row["prev_hash"]
        checked += 1
    return {"ok": True, "checked": checked, "first_bad_seq": None, "reason": CHAIN_OK}


# ============================================================================
# 【存儲探針】照 `template_store_ready()` / `agent_stage_store_ready()` / `lineage_store_ready()`
# ============================================================================
def learning_store_ready():
    """`agent_learning_events` 表是否就位（遷移 `0006` 未跑 / 表被改名 / 庫不可讀 → `False`）。

    三條口徑（寫死在這裡，後續子步不得改）：
      1. **不讀 flag**：flag 與「存儲就緒」是**兩件事**，不許合併成一個布林 ——
         flag off → 調用點根本不進來；flag on 但表缺失 → 503 `learning_store_unavailable`（§7）；
      2. **只看這一張表**：別的列 / 索引缺失不屬「存儲沒就緒」；
      3. **絕不建庫 / 建表 / 寫入，異常一律吞成 `False`**（只捕「任何異常」，不 print、不拋）。

    【本步的落地方式（裁決 B）】本函數**零 SQL**：探測走 `next_seq("")` 這條**只讀**語句
    （SQL 在 `database.py` 單點）；空老師名保證不命中任何行，故不產生任何副作用。
    若 3.3 的接口層需要更嚴格的「按 `sqlite_master` 逐名探測」，加**第 5 個庫層函數**由 CTO 裁決
    （本步不加：指令明確「4 個新函數」）。
    """
    try:
        _db().next_seq("")
    except Exception:  # noqa: BLE001 —— 表缺失 / 庫不可讀都不是本函數要回答的問題（答案就是「沒就緒」）
        return False
    return True


# ============================================================================
# 【差異記錄】§3.2 / A8：字段級 diff（第一類）+ 措辭變化（第二類）—— 純函數（3.3-a）
# ----------------------------------------------------------------------------
# CTO 2026-09-30 step 3.3-a 裁決（R10）逐條落點：
#   · `field` = 剝掉**配對包裹符**的段標題（與 `agent_stage_service._split_heading()` 同一套表 / 同一剝法）；
#   · `before_hash` / `after_hash` = `sha256(歸一化段文本)`（**只放哈希，明文正文不入鏈** —— A5 取向）；
#   · `wording_changed` = 「標題集合相同且僅內容變化」；
#   · 歸一化**復用** `agent_stage_service._normalize_metric_text()`，但**在調用方做**（追加 1 方案 c）：
#     本文件零 import 生產模組 → 本函數**不**自行歸一化，入參必須已是歸一化產物。
#
# 三條已知邊界（都寫進 `compute_content_diff()` 的 docstring，不藏）：
#   ① 入參必須已歸一化；傳原文 = 假陽性（用例反向釘住：段內連續空白 / 段內換行沒折疊就會誤報「有變化」）；
#   ② 段邊界只認**被包裹符包裹的標題 token** —— `_normalize_metric_text()` 把換行折成空格後，
#      「行首」這個信息已經消失，無包裹符的 `主訴：…` 無法與正文裡的冒號區分；認不出標題時整篇退化成
#      「無標題段」一格（仍記錄「有變化」，只是不給字段級拆解）；
#   ③ `field` 長度上限 `FIELD_MAX_CHARS`（20，同 Epic 1 §3.3 段標題 1–20 字）→ 超長的 `【…】` 一律當正文，
#      防「正文被當成字段名寫進鏈」（`field` 也會進 payload、也會被哈希）。
# ============================================================================
FIELD_MAX_CHARS = 20            # 段標題（`field`）長度上限；超過即不視為段標題
UNTITLED_FIELD = ""             # 「無標題段」的 `field` 值：標題之前的文字 / 整篇沒有標題時的唯一一格
SECTION_BRACKETS = (            # 與 `_split_heading()` 的包裹符表**逐字同表**（同一把尺子；用例行為釘住）
    ("【", "】"),
    ("[", "]"),
    ("〔", "〕"),
    ("《", "》"),
)
EMPTY_TEXT_HASH = "e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855"   # == sha256_hex("")


def _section_heading_token():
    """段標題 token 的正則（由 `SECTION_BRACKETS` + `FIELD_MAX_CHARS` **生成**，免得兩處漂移）。

    口徑三條：
      · token 必須**整格**是包裹符對（`【…】` / `[…]` / `〔…〕` / `《…》`），內層 1–`FIELD_MAX_CHARS` 字、
        不含空白（內層用否定字符類擋住）；
      · token 必須被**空白界定**（串首 / 串尾 / 前後是空白）—— 換行折成空格後，「行首」的等價物就是這個；
      · 包裹符一律走 `re.escape()`（`[` / `]` 這對在正則裡有特殊身份：裸寫會變成「嵌套字符類」或
        「字符類提前閉合」，兩者都是**靜默**的解析差異 —— 所以兩個位置都轉義，字符類的收尾 `]` 才裸寫）。
    """
    alternatives = "|".join(
        "%s[^%s\\s]{1,%d}%s" % (re.escape(start), re.escape(end), FIELD_MAX_CHARS, re.escape(end))
        for start, end in SECTION_BRACKETS)
    return re.compile("(?:^|(?<=\\s))(%s)(?=\\s|$)" % alternatives)


_HEADING_TOKEN = _section_heading_token()


def split_section_field(token):
    """段標題 token → `field`：剝掉**配對**的包裹符（`【】` / `[]` / `〔〕` / `《》`）。

    剝法與 `agent_stage_service._split_heading()` **逐字一致**（`test_learning.py` 用它本尊做行為對照）：
    只在「首尾是同一對包裹符且長度 > 兩個包裹符長度之和」時剝，其餘**原樣返回** ——
    逐字符剝會留下半個 `】`，把標題切壞（Epic 2 step 3.4-a 的 ⑯ 組抓到過這個 bug）。
    `None` / 非字符串 → `""`（不拋）。
    """
    text = "" if token is None else str(token).strip()
    for start, end in SECTION_BRACKETS:
        if len(text) > len(start) + len(end) and text.startswith(start) and text.endswith(end):
            return text[len(start):-len(end)].strip()
    return text


def split_sections(normalized_text):
    """已歸一化的整篇正文 → `[(field, segment_text), ...]`（**依出現順序**；同名段合併）。

    四條口徑（全部有測試釘住）：
      · **只認包裹符標題**（見 `_section_heading_token()`）：標題之前的文字歸 `UNTITLED_FIELD`（`""`）；
      · **空段保留**（標題在、正文空 → `segment_text == ""`）：它的哈希 = `EMPTY_TEXT_HASH` ——
        好處是「某段被整段刪掉」在 `wording_changed` 上仍算**結構變化**（若把空段丟掉，這一格會消失）；
      · **同名段合併**成一個 `field`（文本按出現順序以**單空格**相接）—— 同一標題寫兩次不會變成兩筆 diff；
      · 非字符串 / `None` → `""`（= 一個空的無標題段），**不拋**。
    """
    text = "" if normalized_text is None else str(normalized_text)
    pieces = []
    body_start = 0
    current_field = UNTITLED_FIELD
    for match in _HEADING_TOKEN.finditer(text):
        pieces.append((current_field, text[body_start:match.start(1)]))
        current_field = split_section_field(match.group(1))
        body_start = match.end(1)
    pieces.append((current_field, text[body_start:]))

    merged = []
    positions = {}
    for field, body in pieces:
        body = body.strip()
        if field in positions:
            index = positions[field]
            existing = merged[index][1]
            if body:
                merged[index][1] = (existing + " " + body).strip() if existing else body
        else:
            positions[field] = len(merged)
            merged.append([field, body])
    return [(field, body) for field, body in merged]


def compute_content_diff(normalized_before, normalized_after):
    """§3.2 / A8 `draft_modified` 的 `detail`（**純函數**：零 SQL、零副作用、同入參同結果）。

    **入參必須已歸一化**（CTO 追加 1 方案 c）：調用方先跑
    `agent_stage_service._normalize_metric_text(text)`（換行折成空格、連續空白折疊、首尾裁剪、
    可選截斷）再傳進來。本函數**不**自行歸一化（本文件零 import 生產模組）→
    **傳未歸一化的原文不保證結果穩定**：段內連續空白 / 段內換行不會被折疊 → 段文本哈希不同 →
    `field_diff` 憑空多一條（**假陽性**）。`test_learning.py` 有反向用例把這條釘住。

    返回**恆為兩鍵**的 dict（設計 §3.2 的骨架，鍵集合不放寬）：
      · `field_diff`: `[{field, before_hash, after_hash}, ...]`，只收「哈希不同」的段。三條細則：
          - 順序 = **after 段的出現順序**在前，其後是「只在 before 出現」的段（依 before 出現順序）
            → 穩定、可逐條寫死期望；
          - **單側缺失**（段被刪 / 段被加）→ 缺的那側用 `EMPTY_TEXT_HASH`（= `sha256("")`）；
            「段不存在」與「段存在但空」在此**同值**，這是刻意的：兩者都答不出正文；
          - 內容**逐字相同**時 `field_diff == []` → 調用方可據此**跳過寫事件**（別往鏈裡塞空節）；
      · `wording_changed`: 「**標題集合相同且僅內容變化**」= before / after 的**具名**段標題集合非空且相等，
        且 `field_diff` 非空。任一側沒有具名標題（整篇無標題 / 標題全被當正文）→ `False`
        —— 結構信息不可得時**不聲稱**「僅措辭變化」（寧可少報，不虛報）。
    """
    before_segments = split_sections(normalized_before)
    after_segments = split_sections(normalized_after)
    before = dict(before_segments)
    after = dict(after_segments)

    field_diff = []
    for field, body in after_segments:
        before_hash = sha256_hex(before[field]) if field in before else EMPTY_TEXT_HASH
        after_hash = sha256_hex(body)
        if before_hash != after_hash:
            field_diff.append({"field": field, "before_hash": before_hash, "after_hash": after_hash})
    for field, body in before_segments:
        if field in after:
            continue
        field_diff.append({"field": field, "before_hash": sha256_hex(body),
                           "after_hash": EMPTY_TEXT_HASH})

    named_before = {field for field, _ in before_segments if field != UNTITLED_FIELD}
    named_after = {field for field, _ in after_segments if field != UNTITLED_FIELD}
    wording_changed = bool(field_diff) and bool(named_before) and named_before == named_after
    return {"field_diff": field_diff, "wording_changed": wording_changed}


# ============================================================================
# 【事件寫入的服務層入口】5 個 `record_*` 薄封裝（3.3-a；§3.1 五類事件各一）
# ----------------------------------------------------------------------------
# 為什麼要這一層：3.3-b → 3.3-e 的接線點（`database` 的三個既有鉤子 + 新增的「改 4」）只許調它 ——
# 接線點**不**自己拼 `detail`、**不**自己判 flag、**不**自己探存儲、**不**自己吞異常：
#   · `detail` 的鍵集合是設計 §3.2 的骨架（本文件是它的唯一真相源，逐鍵寫死）；
#   · flag / 存儲 / 吞異常三件事只在 `_record_event()` 裡各**判一次** —— 散成五處就會出現
#     「某一處漏判 flag」這種 §6 紅線（flag off 仍寫事件）。
# 五個入口**一律不拋、一律不回退業務**（§9-聲明一「事件寫入失敗不得回退業務輸出」，
# 與 `database.sign_draft()` 末尾 `on_draft_signed(...)` 的最佳努力同口徑）：返回 `bool` = 真的寫成功。
# ============================================================================
def _as_int(value):
    """`detail` / 投影列的整數讀數兜底：`None` / 非數字字符串 / 其它怪值 → `0`，**不拋**。"""
    try:
        return int(value)
    except (TypeError, ValueError):
        return 0


def _as_str_list(value):
    """`detail` 的字符串數組欄位：`None` → `[]`；字符串 → `[該串]`（**不**拆成單字符）；其餘按可迭代取。"""
    if value is None:
        return []
    if isinstance(value, str):
        return [value]
    try:
        return [str(item) for item in value]
    except TypeError:
        return [str(value)]


def _record_event(event_name, teacher_name, event_type, detail, lineage_id="", patient_name="",
                  draft_id=0, template_id=0, created_at=None):
    """5 個 `record_*` 的**共同體**：唯一一處判 flag / 探存儲 / 吞異常（三步順序即契約）。

      ① **flag 門**（§6 / A4）：`learning_enabled()` 為假 → `return False`，**零 SQL**
         （連存儲探針那一條只讀語句都不發 —— flag off = 與今天 1:1）；
      ② **存儲門**（§7）：`learning_store_ready()` 為假（遷移 `0006` 沒跑 / 表被改名 / 庫不可讀）→
         `return False`。這裡**不建表、不拋、不打日誌**：`503 learning_store_unavailable` 是 3.5
         接口層的職責（「功能沒開」與「遷移沒跑」兩件事不許合併）；
      ③ **寫入**：`insert_learning_event()`（本文件唯一的寫入口）。它拋的一切（`ValueError`：
         `seq` 不連續 / 枚舉外事件 / 空老師名；`IntegrityError`：併發搶號；`OperationalError`：
         寫入期庫故障）→ **吞掉 + 一行 `[warn]`（繁體）**，`return False`。

    `event_name` 只用在 warn 文案（留名才可定位），不參與 payload。
    **只用模組內的兩個函數**（`learning_store_ready` / `insert_learning_event`）→ 本文件對
    `database` 的取用面**不因 3.3-a 增加**（源碼級守護 `_database_attrs` 仍是那四個原語）。
    """
    if not learning_enabled():
        return False
    try:
        if not learning_store_ready():
            return False
        insert_learning_event(teacher_name, event_type, detail, lineage_id=lineage_id,
                              patient_name=patient_name, draft_id=draft_id,
                              template_id=template_id, created_at=created_at)
        return True
    except Exception as exc:  # noqa: BLE001 —— best-effort：任何失敗都不得冒泡回業務路徑
        print("[warn] learning_service.%s 寫入學習事件失敗（已忽略，業務結果不受影響）：%s"
              % (event_name, exc))
        return False


def record_template_configured(teacher_name, template_id=0, template_type="", version=0,
                               from_status="", to_status="", lineage_id="", created_at=None):
    """【`template_configured`】老師發佈 / 歸檔 / 啟用某類模板（接線點 = `template_api` 的三個狀態端點）。

    `detail` 逐鍵 = 設計 §3.2：`{template_id:int, template_type:str, version:int, from_status:str,
    to_status:str}`；`draft_id` 恆 0（配置事件不指向草案）。
    """
    detail = {
        "template_id": _as_int(template_id),
        "template_type": str(template_type or ""),
        "version": _as_int(version),
        "from_status": str(from_status or ""),
        "to_status": str(to_status or ""),
    }
    return _record_event("record_template_configured", teacher_name, "template_configured", detail,
                         lineage_id=lineage_id, template_id=template_id, created_at=created_at)


def record_draft_generated(teacher_name, draft_id=0, template_id=0, template_version=0,
                           content_hash="", degraded=False, patient_name="", lineage_id="",
                           created_at=None):
    """【`draft_generated`】智能體生成病歷草案並落庫（接線點 = `database.insert_draft()` 末尾）。

    `detail` 逐鍵 = 設計 §3.2：`{template_version:int, content_hash:str, degraded:bool}`；
    `degraded` = 該草案是否產自觀察期降級骨架（Epic 2 §5.6 / TD-015 的樣本識別口徑，由調用方判定）。
    `patient_name` 只被拿去算哈希（A5：**明文姓名不入鏈**）。
    """
    detail = {
        "template_version": _as_int(template_version),
        "content_hash": str(content_hash or ""),
        "degraded": bool(degraded),
    }
    return _record_event("record_draft_generated", teacher_name, "draft_generated", detail,
                         lineage_id=lineage_id, patient_name=patient_name, draft_id=draft_id,
                         template_id=template_id, created_at=created_at)


def record_draft_modified(teacher_name, normalized_before, normalized_after, draft_id=0,
                          template_id=0, patient_name="", lineage_id="", created_at=None):
    """【`draft_modified`】老師修改草案內容（接線點 = `database.update_draft_content()` 末尾，3.3-c）。

    `normalized_before` / `normalized_after` **必須已歸一化**（CTO 追加 1 方案 c）：調用方先各跑一次
    `agent_stage_service._normalize_metric_text(text)` 再傳進來；本函數**不**替調用方歸一化
    （本文件零 import 生產模組）。`detail` = `compute_content_diff(...)` 的產物
    （兩鍵：`field_diff` / `wording_changed`，逐條口徑見該函數 docstring）。

    邊界（留給調用方判，本函數不替它判）：內容**逐字相同** → `field_diff == []` ——
    接線點據此**跳過寫事件**（§一-1 裁決：冪等分支不寫事件，別往鏈裡塞空節）。
    `patient_name` 只被拿去算哈希（A5）。
    """
    detail = compute_content_diff(normalized_before, normalized_after)
    return _record_event("record_draft_modified", teacher_name, "draft_modified", detail,
                         lineage_id=lineage_id, patient_name=patient_name, draft_id=draft_id,
                         template_id=template_id, created_at=created_at)


def record_learning_event_emitted(teacher_name, source_event_types=(), difference_kinds=(),
                                  sample_count=0, lineage_id="", created_at=None):
    """【`learning_event_emitted`】一次學習結算**被產出**（接線點 = `agent_stage_service._evaluate()`）。

    `detail` 逐鍵 = 設計 §3.2：`{source_event_types:[str], difference_kinds:[str], sample_count:int}`
    —— 「本次學習發生了什麼」的**匯總節**（來源事件類型 / 差異種類 / 樣本數）。
    兩個數組欄位由 `_as_str_list()` 兜底（`None` → `[]`；字符串 → `[該串]`）。
    """
    detail = {
        "source_event_types": _as_str_list(source_event_types),
        "difference_kinds": _as_str_list(difference_kinds),
        "sample_count": _as_int(sample_count),
    }
    return _record_event("record_learning_event_emitted", teacher_name, "learning_event_emitted",
                         detail, lineage_id=lineage_id, created_at=created_at)


def record_agent_updated(teacher_name, from_stage="", to_stage="", capability="", metrics_hash="",
                         lineage_id="", created_at=None):
    """【`agent_updated`】學習結果落實到統計指標 / 階段視圖（接線點 = `agent_stage_service._evaluate()`）。

    `detail` 逐鍵 = 設計 §3.2：`{from_stage:str, to_stage:str, capability:str, metrics_hash:str}`；
    `metrics_hash` = 本次評估結果快照的哈希（快照本體留在 `agent_stage_state.last_metrics_json`，
    **不**複製進鏈）。

    §一-4 裁決（CTO 批）：**3.3 只在 `_evaluate()` 寫這一類事件**；升階路徑（`apply_upgrade_confirmation`
    等）的 `agent_updated` 寫入**留給 3.4** —— 本函數今天只有一個接線點。
    """
    detail = {
        "from_stage": str(from_stage or ""),
        "to_stage": str(to_stage or ""),
        "capability": str(capability or ""),
        "metrics_hash": str(metrics_hash or ""),
    }
    return _record_event("record_agent_updated", teacher_name, "agent_updated", detail,
                         lineage_id=lineage_id, created_at=created_at)
