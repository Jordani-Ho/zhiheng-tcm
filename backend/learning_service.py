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

啟用方式（本機 / 生產，PowerShell；**默認 off**）：
    $env:LEARNING_ENABLED = "on"
"""
import hashlib
import json
import os
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
