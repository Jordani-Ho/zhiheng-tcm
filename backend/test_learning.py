"""Epic 3「學習閉環」step 3.2 用例集：哈希鏈**純函數** + 庫層原語 + 單遍鏈校驗 + 源碼級守護。

對齊：docs/epic3-learning-design-v1.md
  §2.3 canonical 口徑（鍵序無關 / 零空白 / 中文原樣 / 頂層 9 鍵）
  §2.4 A3 鏈節指紋 + `GENESIS_HASH` + 單遍校驗（可定位到 `first_bad_seq`）
  §2.5 A2 `seq` 按老師單鏈、從 1 起、步長 1
  §2.6 兩種索引（`UNIQUE(teacher_name, seq)` 是併發兜底）
  §7   flag off = 與今天 1:1（零 SQL、零寫入）

CTO 2026-09-30 step 3.2 指令要求的十類核心用例，本文件逐條落點：
  ① 鍵序無關 → `test_canonical_json_is_key_order_independent`
  ② 一字符即變 → `test_payload_hash_one_character_change`
  ③ GENESIS + seq=1 → `test_first_event_chains_from_genesis_at_seq_one`
  ④ 鏈連續 → `test_chain_links_and_seq_strictly_increment`
  ⑤ 可定位篡改 → `test_verify_locates_middle_row_tampering`（+ 另兩條失敗原因）
  ⑥ 期望 hash 字面量凍結（3 條典型 payload，**寫死在文件裡**，不由實現自證）
     → `test_canonical_json_frozen_literals` / `test_payload_hash_frozen_literals` /
        `test_link_hash_frozen_literals`
  ⑦ 單鏈隔離 → `test_single_chain_isolation_two_teachers`
  ⑧ 零審計 → `test_ten_writes_keep_audit_tables_untouched`
  ⑨ flag off → `test_flag_off_values_and_zero_sql` / `test_flag_on_values`
  ⑩ 源碼級守護 → `test_source_guard_zero_sql_zero_audit_zero_capability`
另加本步自身要找死的兩條結構守護：**零接線**（`test_no_wiring_in_step_3_2`）與
**遷移 0006 雙向口徑對齊**（`test_constants_align_with_migration_0006`）。

運行方式（Windows，串行；見 pytest.ini）：
    cd backend
    ..\\venv\\Scripts\\python.exe -m pytest test_learning.py -v

紀律（照 test_agent_stage.py / test_lineage.py）：
  · 「寫死期望字面量」是本文件的核心手法 —— 期望值**不由被測實現算出來**，否則實現改了、用例跟著改，
    守護就等於零。凡出現期望哈希處，都是 `sha256` 的**獨立常數**；
  · 造前置態 / 模擬「人手改壞庫」一律走 `_raw_execute()` 直連庫文件，**不經** `database.get_connection()`
    —— 免得污染 `sql_log` 的「只發 SELECT」語句級斷言。
"""
import ast
import copy
import hashlib
import json
import os
import re
import sqlite3

import pytest

import database
import learning_service
import migrations_runner

# 【凍結字面量所用的老師名】`FROZEN_CANONICAL` / `FROZEN_PAYLOAD_HASH` / `FROZEN_LINK_HASH` 是用**這個名字**
# 算出來的（payload 的 `teacher_name` 參與哈希，所以名字本身是口徑的一部分）。因此需要與凍結值逐字比對的
# DB 用例（`_insert()` / `_rows()` 的默認老師）必須用同一個名字，否則「比對凍結值」會變成在比對別的 payload。
TEACHER = "李老师"
OTHER_TEACHER = "学习链测试老师乙"
NEVER_WRITTEN_TEACHER = "学习链测试老师丙"
PATIENT_NAME = "张三"
LINEAGE_ID = "lin-li-lao-shi"

# ---------------------------------------------------------------------------
# 【凍結字面量】三條典型 payload（§3.2 的事件形狀）+ 它們的 canonical 串 / payload 哈希 / 鏈節指紋
# ---------------------------------------------------------------------------
DETAIL_TEMPLATE_CONFIGURED = {"template_id": 7, "template_type": "record", "version": 2,
                              "from_status": "draft", "to_status": "active"}
DETAIL_DRAFT_GENERATED = {
    "template_version": 2,
    "content_hash": "9f86d081884c7d659a2feaa0c55ad015a3bf4f1b2b0b822cd15d6c15b0f00a08",
    "degraded": False,
}
DETAIL_DRAFT_MODIFIED = {
    "field_diff": [{"field": "主诉",
                    "before_hash": "0f1e2d3c4b5a69788796a5b4c3d2e1f000112233",
                    "after_hash": "1122334455667788990011223344556677889900"}],
    "wording_changed": True,
}

SPECS = (
    (1, "template_configured", "2026-09-30T09:00:00", 0, 7, DETAIL_TEMPLATE_CONFIGURED),
    (2, "draft_generated", "2026-09-30T09:05:00", 101, 7, DETAIL_DRAFT_GENERATED),
    (3, "draft_modified", "2026-09-30T09:10:00", 101, 7, DETAIL_DRAFT_MODIFIED),
)

# A5：patient_name_hash = sha256("张三")[:16]
FROZEN_PATIENT_NAME_HASH = "1d841bc0ee98309c"
# sha256("")[:16]（空名 / None 的哨兵值）
FROZEN_EMPTY_NAME_HASH = "e3b0c44298fc1c14"

# 3 條 canonical 串：**逐字節**（鍵升序、`", "` / `": "` 無空白、中文原樣不轉義）。
# 故意寫成單行整串而不是拼接：拼接的邊界打字錯會讓「凍結」變成「自己騙自己」。
FROZEN_CANONICAL = (
    "{\"created_at\":\"2026-09-30T09:00:00\",\"detail\":{\"from_status\":\"draft\",\"template_id\":7,\"template_type\":\"record\",\"to_status\":\"active\",\"version\":2},\"draft_id\":0,\"event_type\":\"template_configured\",\"lineage_id\":\"lin-li-lao-shi\",\"patient_name_hash\":\"1d841bc0ee98309c\",\"seq\":1,\"teacher_name\":\"李老师\",\"template_id\":7}",
    "{\"created_at\":\"2026-09-30T09:05:00\",\"detail\":{\"content_hash\":\"9f86d081884c7d659a2feaa0c55ad015a3bf4f1b2b0b822cd15d6c15b0f00a08\",\"degraded\":false,\"template_version\":2},\"draft_id\":101,\"event_type\":\"draft_generated\",\"lineage_id\":\"lin-li-lao-shi\",\"patient_name_hash\":\"1d841bc0ee98309c\",\"seq\":2,\"teacher_name\":\"李老师\",\"template_id\":7}",
    "{\"created_at\":\"2026-09-30T09:10:00\",\"detail\":{\"field_diff\":[{\"after_hash\":\"1122334455667788990011223344556677889900\",\"before_hash\":\"0f1e2d3c4b5a69788796a5b4c3d2e1f000112233\",\"field\":\"主诉\"}],\"wording_changed\":true},\"draft_id\":101,\"event_type\":\"draft_modified\",\"lineage_id\":\"lin-li-lao-shi\",\"patient_name_hash\":\"1d841bc0ee98309c\",\"seq\":3,\"teacher_name\":\"李老师\",\"template_id\":7}",
)

# 3 條 payload 哈希 = sha256(上面的 canonical 串)；3 條鏈節指紋（L1 以 GENESIS 起算，L2 接 L1，L3 接 L2）
FROZEN_PAYLOAD_HASH = (
    "93cdf3e45f33246f28ed8a70fc580a456ee1dd3c8e8237e0e20db7af0017c652",
    "6db5475af28d491dd6a3108937eab78956923e655edfb9c08e0cf247753dd68d",
    "99c4e65816a301b6fbc168600924a1d0a331c214203e730b372932d27bda1343",
)
FROZEN_LINK_HASH = (
    "dd0fd290c5a67b6578eb49f7aeb9e84c6e098cbeaa0502bf7b8a3672e08c01f0",
    "6d90ec23f6e34099f2a115a16417e6a23e93bf4c3b1e66ff6760ec0dabe71f6a",
    "92345abe1c0ac9ab058b0178acdd1b254ca9c4604fde9a5cda01004b14ecd520",
)

BACKEND_DIR = os.path.dirname(os.path.abspath(__file__))
MIGRATION_0006_PATH = os.path.join(BACKEND_DIR, "alembic", "versions",
                                   "0006_add_agent_learning_events.py")
LEARNING_SERVICE_PATH = os.path.join(BACKEND_DIR, "learning_service.py")

# 源碼級守護的 SQL 關鍵字掃描：**詞邊界**匹配 —— `insert_learning_event` 這種含 `INSERT` 的**標識符**
# 不會被誤判（`_` 是詞字符、因此其後不構成詞邊界），而任何真的 SQL 語句（`SELECT ...`）必被抓到。
SQL_KEYWORD_PATTERN = re.compile(
    r"\b(SELECT|INSERT|UPDATE|DELETE|CREATE|DROP|ALTER|PRAGMA)\b", re.IGNORECASE)


def _spec(index):
    """取第 `index`（0 起）條凍結 payload 的**期望** `(payload, canonical, payload_hash, link_hash)`。

    payload 用「寫死的 9 鍵字典」而不是 `learning_service.build_payload()` 生成 ——
    用例的輸入也必須獨立於被測實現（否則 build_payload 的鍵序 / 歸一邏輯一改，用例跟著漂移）。
    """
    seq, event_type, created_at, draft_id, template_id, detail = SPECS[index]
    payload = {
        "seq": seq,
        "event_type": event_type,
        "teacher_name": TEACHER,
        "created_at": created_at,
        "lineage_id": LINEAGE_ID,
        "patient_name_hash": FROZEN_PATIENT_NAME_HASH,
        "draft_id": draft_id,
        "template_id": template_id,
        "detail": detail,
    }
    return payload, FROZEN_CANONICAL[index], FROZEN_PAYLOAD_HASH[index], FROZEN_LINK_HASH[index]


# ============================================================================
# fixtures / 助手（照 test_agent_stage.py：造數與觀測都不走 database.get_connection()）
# ============================================================================
@pytest.fixture
def db():
    """每個用例前重建 test.db（與 conftest.client / test_agent_stage.db 同款前置）：

    刪庫 → `init_db()` → alembic 遷移（`agent_learning_events` 走生產同一條遷移路徑）。
    """
    if os.path.exists(database.DB_PATH):
        os.remove(database.DB_PATH)
    database.init_db()
    migrations_runner.run_upgrade()
    return database


class _RecordingConnection:
    """把 `execute` 錄下來的連接（包住真連接，其餘屬性原樣轉發）。"""

    def __init__(self, conn):
        self.__dict__["_conn"] = conn
        self.__dict__["calls"] = []

    def execute(self, sql, params=()):
        self.__dict__["calls"].append((sql, params))
        return self.__dict__["_conn"].execute(sql, params)

    def __getattr__(self, name):
        return getattr(self.__dict__["_conn"], name)


@pytest.fixture
def sql_log(monkeypatch):
    """錄下被測函數執行的全部語句（返回 `list[_RecordingConnection]`）。"""
    real = database.get_connection
    connections = []

    def wrapper():
        conn = _RecordingConnection(real())
        connections.append(conn)
        return conn

    monkeypatch.setattr(database, "get_connection", wrapper)
    return connections


def _statements(connections):
    return [sql for conn in connections for sql, _ in conn.calls]


def _raw_execute(sql, params=()):
    """繞過 `database.get_connection()` 直連庫文件寫一條（造前置態 / 模擬人手改壞庫）。"""
    conn = sqlite3.connect(database.DB_PATH)
    try:
        conn.execute(sql, params)
        conn.commit()
    finally:
        conn.close()


def _raw_scalar(sql, params=()):
    """繞過 `database.get_connection()` 直連庫文件讀一個標量。"""
    conn = sqlite3.connect(database.DB_PATH)
    try:
        return conn.execute(sql, params).fetchone()[0]
    finally:
        conn.close()


def _insert(spec_index, teacher_name=TEACHER, **overrides):
    """用凍結樣本寫一條事件（走 `learning_service` 的唯一寫入口）→ 返回新行 `id`。"""
    seq, event_type, created_at, draft_id, template_id, detail = SPECS[spec_index]
    kwargs = {
        "lineage_id": LINEAGE_ID,
        "patient_name": PATIENT_NAME,
        "draft_id": draft_id,
        "template_id": template_id,
        "created_at": created_at,
        "seq": seq,
    }
    kwargs.update(overrides)
    return learning_service.insert_learning_event(teacher_name, event_type, detail, **kwargs)


def _rows(teacher_name=TEACHER):
    """讀該老師的**全量**鏈（`limit=None`）。"""
    return learning_service.get_learning_events(teacher_name, None)


def _mutate(value):
    """造一個「與原值不同」的變體（不改類型語義，只求一個字節的差）。"""
    if isinstance(value, bool):
        return not value
    if isinstance(value, str):
        return value + "x"
    if isinstance(value, int):
        return value + 1
    return {"mutated": True}


# ============================================================================
# ① 純函數 / canonical 口徑（§2.3 / §2.4；無 DB、無 flag）
# ============================================================================
def test_canonical_json_is_key_order_independent():
    """① §2.3：同一 payload 換鍵序 → canonical 串**逐字**相同（`sort_keys=True` 的唯一功效）。

    反面對照一併釘住：`json.dumps` 的**默認**參數會在「鍵序」與「中文轉義」上都產生第二種字節
    —— 那正是三參必須凍結的理由。
    """
    payload, expected, _, _ = _spec(0)
    shuffled = dict(reversed(list(payload.items())))
    shuffled["detail"] = dict(reversed(list(payload["detail"].items())))

    assert list(payload.keys()) != list(shuffled.keys())                  # 前提：鍵序真的不同
    assert list(payload["detail"].keys()) != list(shuffled["detail"].keys())
    assert learning_service.canonical_json(payload) == expected
    assert learning_service.canonical_json(shuffled) == expected          # 鍵序無關
    assert learning_service.compute_payload_hash(shuffled) == FROZEN_PAYLOAD_HASH[0]

    assert " " not in expected                                            # separators 生效：零空白
    assert json.dumps(payload) != expected                                # 默認參數 ≠ canonical
    assert json.dumps(payload, ensure_ascii=False) != expected            # 只關轉義也不夠（鍵序 + 空白）


def test_canonical_json_frozen_literals():
    """⑥ §2.3：三條典型 payload 的 canonical 串**逐字**等於寫死的期望（鍵升序 / 零空白 / 中文原樣）。"""
    for index in range(3):
        payload, expected, _, _ = _spec(index)
        assert learning_service.canonical_json(payload) == expected, "第 %d 條 canonical 串漂移" % (index + 1)
        assert json.loads(expected) == payload                            # 期望串本身可回讀且與 payload 等值

    assert "李老师" in FROZEN_CANONICAL[0]                                # ensure_ascii=False：中文原樣
    assert "\\u674e" not in FROZEN_CANONICAL[0]                           # 不是 `\uXXXX` 轉義形式
    assert learning_service.CANONICAL_SORT_KEYS is True
    assert tuple(learning_service.CANONICAL_SEPARATORS) == (",", ":")
    assert learning_service.CANONICAL_ENSURE_ASCII is False


def test_payload_hash_one_character_change():
    """② §2.3：payload 任一字符變化 → payload_hash 必變（九個頂層鍵逐一試；另加三處單字符改）。"""
    for index in range(3):
        payload, _, expected_hash, _ = _spec(index)
        assert learning_service.compute_payload_hash(payload) == expected_hash
        for key in learning_service.PAYLOAD_TOP_LEVEL_KEYS:
            variant = copy.deepcopy(payload)
            variant[key] = _mutate(variant[key])
            assert learning_service.compute_payload_hash(variant) != expected_hash, \
                "第 %d 條改 %s 後哈希竟然沒變" % (index + 1, key)

    # 單字符改：版本號 +1 / 指紋尾部換一位 / 一個中文字加一筆
    def _bump(old):
        return old + 1

    def _last_digit(old):
        return old[:-1] + "9"

    def _stroke(old):
        return [dict(old[0], field="主诉。")]

    for index, path, mutate in ((0, ("version",), _bump),
                                (1, ("content_hash",), _last_digit),
                                (2, ("field_diff",), _stroke)):
        payload, _, expected_hash, _ = _spec(index)
        variant = copy.deepcopy(payload)
        node = variant["detail"]
        for step in path[:-1]:
            node = node[step]
        node[path[-1]] = mutate(node[path[-1]])
        assert learning_service.canonical_json(variant) != FROZEN_CANONICAL[index]
        assert learning_service.compute_payload_hash(variant) != expected_hash


def test_payload_hash_frozen_literals():
    """⑥ §2.3：三條 payload 的哈希**逐條寫死**（= sha256(canonical 串) 的獨立常數）。"""
    for index in range(3):
        payload, canonical, expected_hash, _ = _spec(index)
        assert learning_service.compute_payload_hash(payload) == expected_hash
        # 獨立重述一層：canonical 串 → sha256（不經 compute_payload_hash 的內部實現）
        assert hashlib.sha256(canonical.encode("utf-8")).hexdigest() == expected_hash
        assert len(expected_hash) == 64
    assert learning_service.PAYLOAD_HASH_ALGO == "sha256"


def test_link_hash_frozen_literals():
    """⑥ §2.4：三條鏈節指紋**逐條寫死**；L1 的輸入是 `GENESIS_HASH`（空鏈起點），其後逐節串接。"""
    previous = learning_service.GENESIS_HASH
    assert previous == "0" * 64 and len(previous) == 64
    for index in range(3):
        payload, _, payload_hash, expected_link = _spec(index)
        link = learning_service.compute_link_hash(payload["seq"], payload["event_type"],
                                                  payload_hash, previous)
        assert link == expected_link, "第 %d 條鏈節指紋漂移" % (index + 1)
        # 獨立重述公式：sha256(canonical_json({seq, event_type, payload_hash, prev_hash}))
        restated = hashlib.sha256(learning_service.canonical_json({
            "seq": payload["seq"],
            "event_type": payload["event_type"],
            "payload_hash": payload_hash,
            "prev_hash": previous,
        }).encode("utf-8")).hexdigest()
        assert link == restated
        previous = link


def test_link_hash_changes_with_every_input():
    """⑥ §2.4 的「一項即變」：`seq` / `event_type` / `payload_hash` / `prev_hash` 任一變化 → 指紋必變。"""
    _, _, payload_hash, _ = _spec(0)
    genesis = learning_service.GENESIS_HASH
    base = learning_service.compute_link_hash(1, "template_configured", payload_hash, genesis)
    assert learning_service.compute_link_hash(2, "template_configured", payload_hash, genesis) != base
    assert learning_service.compute_link_hash(1, "draft_generated", payload_hash, genesis) != base
    assert learning_service.compute_link_hash(1, "template_configured", payload_hash[:-1] + "9",
                                              genesis) != base
    assert learning_service.compute_link_hash(1, "template_configured", payload_hash,
                                              "0" * 63 + "1") != base
    # 空鏈起點**不等於**任一節的指紋（否則「首條沒有前驅」這一事實會被抹掉）
    assert base != genesis


def test_patient_name_hash_frozen_and_plaintext_never_leaks():
    """【A5】`sha256(patient_name)[:16]`：期望值寫死；產物裡**永不含明文**（長度 16 是硬約束）。"""
    assert learning_service.compute_patient_name_hash(PATIENT_NAME) == FROZEN_PATIENT_NAME_HASH
    assert hashlib.sha256(PATIENT_NAME.encode("utf-8")).hexdigest()[:16] == FROZEN_PATIENT_NAME_HASH
    assert learning_service.PATIENT_NAME_HASH_LEN == 16

    # None / 空串 → 同一個哨兵值（`sha256("")[:16]`），不拋
    assert learning_service.compute_patient_name_hash(None) == FROZEN_EMPTY_NAME_HASH
    assert learning_service.compute_patient_name_hash("") == FROZEN_EMPTY_NAME_HASH
    assert hashlib.sha256(b"").hexdigest()[:16] == FROZEN_EMPTY_NAME_HASH

    for name in (PATIENT_NAME, "", None, 123, "张三丰"):
        digest = learning_service.compute_patient_name_hash(name)
        assert len(digest) == 16 and digest == digest.lower()
        int(digest, 16)                                        # 必須是 16 個十六進制字符
        if name:
            assert str(name) not in digest                     # 明文一個字都不出現
    assert learning_service.compute_patient_name_hash(123) == learning_service.compute_patient_name_hash("123")
    assert (learning_service.compute_patient_name_hash("张三")
            != learning_service.compute_patient_name_hash("张三丰"))


def test_payload_contract_keys_event_types_and_no_none():
    """§2.3 / §3.1：頂層 9 鍵與 5 類事件**逐字**（含順序）；`build_payload` 只產這 9 鍵、值裡無 `None`。"""
    assert tuple(learning_service.PAYLOAD_TOP_LEVEL_KEYS) == (
        "seq", "event_type", "teacher_name", "created_at", "lineage_id",
        "patient_name_hash", "draft_id", "template_id", "detail")
    assert tuple(learning_service.EVENT_TYPES) == (
        "template_configured", "draft_generated", "draft_modified",
        "learning_event_emitted", "agent_updated")
    assert len(learning_service.EVENT_TYPES) == len(set(learning_service.EVENT_TYPES)) == 5

    built = learning_service.build_payload(2, "draft_generated", TEACHER, "2026-09-30T09:05:00",
                                           LINEAGE_ID, FROZEN_PATIENT_NAME_HASH, 101, 7, None)
    assert tuple(built.keys()) == tuple(learning_service.PAYLOAD_TOP_LEVEL_KEYS)
    assert isinstance(built["seq"], int) and isinstance(built["draft_id"], int)
    assert isinstance(built["template_id"], int) and isinstance(built["detail"], dict)

    def _assert_no_none(node, path=""):
        assert node is not None, "payload 裡出現 None：%s" % path
        if isinstance(node, dict):
            for key, value in node.items():
                _assert_no_none(value, "%s.%s" % (path, key))
        elif isinstance(node, list):
            for index, value in enumerate(node):
                _assert_no_none(value, "%s[%d]" % (path, index))

    for index in range(3):
        payload, _, _, _ = _spec(index)
        _assert_no_none(payload)


# ============================================================================
# ② 遷移 0006（凍結見證）↔ learning_service（實現）的雙向口徑對齊
# ============================================================================
def _load_migration_0006():
    """按路徑獨立載入遷移 0006（不觸發 alembic 環境；照 test_migrations.py 同名助手）。"""
    import importlib.util

    spec = importlib.util.spec_from_file_location("migration_0006_for_learning_test",
                                                 MIGRATION_0006_PATH)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_constants_align_with_migration_0006(monkeypatch):
    """遷移 0006（凍結見證）↔ `learning_service`（實現）的常量**逐字**一致。

    為什麼要兩邊對：設計文檔一份、遷移一份、服務層一份 —— 任意兩份漂移，都會讓「已落庫的鏈」與
    「新寫的鏈」用不同口徑算哈希（症狀：`verify` 從某條起全紅，且看起來像「庫被人改過」）。
    """
    migration = _load_migration_0006()
    assert migration.EVENTS_TABLE == database.LEARNING_EVENTS_TABLE == "agent_learning_events"
    assert migration.GENESIS_HASH == learning_service.GENESIS_HASH
    assert migration.PAYLOAD_HASH_ALGO == learning_service.PAYLOAD_HASH_ALGO
    assert migration.PATIENT_NAME_HASH_LEN == learning_service.PATIENT_NAME_HASH_LEN
    assert migration.CANONICAL_SORT_KEYS is learning_service.CANONICAL_SORT_KEYS is True
    assert (tuple(migration.CANONICAL_SEPARATORS)
            == tuple(learning_service.CANONICAL_SEPARATORS) == (",", ":"))
    assert migration.CANONICAL_ENSURE_ASCII is learning_service.CANONICAL_ENSURE_ASCII is False
    assert tuple(migration.PAYLOAD_TOP_LEVEL_KEYS) == tuple(learning_service.PAYLOAD_TOP_LEVEL_KEYS)
    assert tuple(migration.EVENT_TYPES) == tuple(learning_service.EVENT_TYPES)

    # 列全集 ↔ INSERT 白名單：`遷移列全集` 去掉三個非白名單列後，逐列、逐序相同
    assert tuple(database.LEARNING_EVENT_INSERT_FIELDS) == tuple(
        name for name in migration.ALL_COLUMNS if name not in ("id", "teacher_name", "event_type"))
    assert set(database.LEARNING_EVENT_REQUIRED_FIELDS) <= set(database.LEARNING_EVENT_INSERT_FIELDS)

    # flag：用遷移凍結的 `FLAG_NAME` 當環境變量鍵，驗服務層判讀行為（名字 / 值 / 默認三件事同口徑）
    monkeypatch.delenv("LEARNING_ENABLED", raising=False)
    assert learning_service.learning_enabled() is False
    monkeypatch.setenv(migration.FLAG_NAME, "on")
    assert learning_service.learning_enabled() is True
    assert tuple(learning_service.LEARNING_ENABLED_VALUES) == tuple(migration.FLAG_VALUES)
    assert migration.FLAG_NAME == "LEARNING_ENABLED"


# ============================================================================
# ③ 庫層原語 / 鏈行為（需要遷移後的 test.db）
# ============================================================================
def test_first_event_chains_from_genesis_at_seq_one(db):
    """③ §2.5 + §2.4：空鏈 → 首條 `seq == 1`，`prev_hash` 是**以 `GENESIS_HASH` 起算**的鏈節指紋。

    列值語義（§2.4「列名命名留痕」）：`prev_hash` 列存的是**本節的累積指紋**，不是「上一節的值」的照抄
    —— 所以首條 `prev_hash != GENESIS_HASH`；`GENESIS_HASH` 是它的**輸入**。這一點連同下一條用例
    （第 2 條的輸入不再是 GENESIS）共同釘住「GENESIS 只被首條用到」。
    """
    assert learning_service.get_last_learning_event(NEVER_WRITTEN_TEACHER) is None
    assert learning_service.next_seq(NEVER_WRITTEN_TEACHER) == 1
    assert learning_service.get_learning_events(NEVER_WRITTEN_TEACHER, None) == []
    assert learning_service.verify_learning_chain(NEVER_WRITTEN_TEACHER) == {
        "ok": True, "checked": 0, "first_bad_seq": None, "reason": "ok"}

    _, canonical, payload_hash, link = _spec(0)
    row_id = _insert(0)
    rows = _rows()
    assert len(rows) == 1 and rows[0]["id"] == row_id
    row = rows[0]
    assert row["seq"] == 1
    assert row["payload_json"] == canonical
    assert row["payload_hash"] == payload_hash
    assert row["prev_hash"] == link == FROZEN_LINK_HASH[0]
    assert row["prev_hash"] != learning_service.GENESIS_HASH
    assert row["prev_hash"] == learning_service.compute_link_hash(
        1, "template_configured", payload_hash, learning_service.GENESIS_HASH)
    assert learning_service.get_last_learning_event(TEACHER)["id"] == row_id


def test_chain_links_and_seq_strictly_increment(db):
    """④ §2.4 / §2.5：第 2 條起 `prev_hash` 的**輸入**是上一條的鏈節指紋；`seq` 嚴格 +1、不跳號。"""
    ids = [_insert(0), _insert(1), _insert(2)]
    rows = _rows()
    assert [row["id"] for row in rows] == ids
    assert [row["seq"] for row in rows] == [1, 2, 3]
    assert [row["payload_hash"] for row in rows] == list(FROZEN_PAYLOAD_HASH)
    assert [row["prev_hash"] for row in rows] == list(FROZEN_LINK_HASH)

    for index in range(1, 3):
        previous = rows[index - 1]
        assert rows[index]["prev_hash"] == learning_service.compute_link_hash(
            rows[index]["seq"], rows[index]["event_type"],
            rows[index]["payload_hash"], previous["prev_hash"])
        assert rows[index]["prev_hash"] != previous["prev_hash"]      # 逐節遞進，非原地踏步

    assert learning_service.next_seq(TEACHER) == 4
    assert learning_service.get_last_learning_event(TEACHER)["seq"] == 3
    assert learning_service.verify_learning_chain(TEACHER) == {
        "ok": True, "checked": 3, "first_bad_seq": None, "reason": "ok"}


def test_projection_columns_mirror_payload_values(db):
    """【A5 裁決落地】八個投影列 == `payload_json` 裡**同名鍵**的值。

    口徑（CTO 2026-09-30 step 3.1 裁決）：**列 = payload 的可檢索投影，權威源 = `payload_json`**。
    CTO 要求 3.3 的用例必須有「列 == payload 值」的**顯式斷言**；這裡把它提前釘在 3.2 的**寫路徑**上
    （寫完立刻比對），3.3 再覆蓋讀路徑，兩步合起來才是完整的「投影 = 權威源」證明。
    """
    _insert(0)
    _insert(1)
    row = _rows()[1]
    payload = json.loads(row["payload_json"])

    # 權威源的鍵集合 = 頂層 9 鍵；`payload_json` 是 canonical 串 → 回讀後鍵序必然**升序**
    assert len(payload) == len(learning_service.PAYLOAD_TOP_LEVEL_KEYS) == 9
    assert set(payload) == set(learning_service.PAYLOAD_TOP_LEVEL_KEYS)
    assert tuple(payload.keys()) == tuple(sorted(learning_service.PAYLOAD_TOP_LEVEL_KEYS))
    for column in ("seq", "event_type", "teacher_name", "created_at", "lineage_id",
                   "patient_name_hash", "draft_id", "template_id"):
        assert row[column] == payload[column], "列 %s 與 payload 同名鍵不一致" % column
    assert row["patient_name_hash"] == FROZEN_PATIENT_NAME_HASH

    # §2.2 兩分法：`detail` 只在 payload 裡（沒有同名列）；明文姓名沒有任何落點（A5）
    assert "detail" not in row
    assert "patient_name" not in row
    assert PATIENT_NAME not in json.dumps(row, ensure_ascii=False)


def test_payload_json_stored_verbatim_canonical(db):
    """§2.3：落庫的 `payload_json` **逐字等於** canonical 串（不是「存進去再重排一次」）。

    這一條是「證據的權威源是字節、不是代碼」的具體化：`payload_hash` 必須是**這一串字節**的 sha256，
    否則 verify 的第 1 層會變成「用當前代碼重算一遍」，庫被人改一個字符也驗不出來。
    """
    _insert(0)
    _insert(1)
    _insert(2)
    for index, row in enumerate(_rows()):
        assert row["payload_json"] == FROZEN_CANONICAL[index]
        assert hashlib.sha256(row["payload_json"].encode("utf-8")).hexdigest() == row["payload_hash"]
        assert row["payload_json"] == learning_service.canonical_json(json.loads(row["payload_json"]))


def test_verify_locates_middle_row_tampering(db):
    """⑤ §2.4：篡改中間行的 `payload_json`（一個單詞）→ `ok=False` 且 `first_bad_seq` **定位到那一行**。"""
    _insert(0)
    _insert(1)
    _insert(2)
    assert learning_service.verify_learning_chain(TEACHER)["ok"] is True

    original = _raw_scalar("SELECT payload_json FROM agent_learning_events "
                           "WHERE teacher_name = ? AND seq = 2", (TEACHER,))
    tampered = original.replace("false", "true")                     # 只改一個布爾值（JSON 仍合法）
    assert tampered != original and json.loads(tampered) != json.loads(original)
    _raw_execute("UPDATE agent_learning_events SET payload_json = ? "
                 "WHERE teacher_name = ? AND seq = 2", (tampered, TEACHER))

    result = learning_service.verify_learning_chain(TEACHER)
    assert result == {"ok": False, "checked": 1, "first_bad_seq": 2,
                      "reason": learning_service.CHAIN_PAYLOAD_TAMPERED}
    assert learning_service.CHAIN_PAYLOAD_TAMPERED == "payload_tampered"


def test_verify_reports_link_broken_when_prev_hash_edited(db):
    """⑤ §2.4：改 `prev_hash`（不動 payload）→ `link_broken`，且定位到被改的那一行。"""
    _insert(0)
    _insert(1)
    _insert(2)

    link = _raw_scalar("SELECT prev_hash FROM agent_learning_events "
                       "WHERE teacher_name = ? AND seq = 2", (TEACHER,))
    _raw_execute("UPDATE agent_learning_events SET prev_hash = ? "
                 "WHERE teacher_name = ? AND seq = 2", (link[:-1] + "f", TEACHER))

    result = learning_service.verify_learning_chain(TEACHER)
    assert result == {"ok": False, "checked": 1, "first_bad_seq": 2,
                      "reason": learning_service.CHAIN_LINK_BROKEN}
    assert learning_service.CHAIN_LINK_BROKEN == "link_broken"


def test_verify_reports_seq_gap_when_middle_row_deleted(db):
    """⑤ §2.5：中間行被**刪掉**（少了見證）→ `seq_gap`，`first_bad_seq` 指向斷口後的第一行。"""
    _insert(0)
    _insert(1)
    _insert(2)
    _raw_execute("DELETE FROM agent_learning_events WHERE teacher_name = ? AND seq = 2", (TEACHER,))

    result = learning_service.verify_learning_chain(TEACHER)
    assert result == {"ok": False, "checked": 1, "first_bad_seq": 3,
                      "reason": learning_service.CHAIN_SEQ_GAP}
    assert learning_service.CHAIN_SEQ_GAP == "seq_gap"
    # 少一行不影響「讀得到」：讀點照樣返回，只是少了那一節（驗不過就必須說出來，不許靜默）
    assert [row["seq"] for row in _rows()] == [1, 3]


def test_single_chain_isolation_two_teachers(db):
    """⑦ §2.5：按老師單鏈 —— 兩條鏈各自從 1 起、互不引用；改壞甲鏈不動乙鏈。"""
    _insert(0)
    _insert(1)
    other_ids = [_insert(0, teacher_name=OTHER_TEACHER),
                 _insert(1, teacher_name=OTHER_TEACHER)]

    mine, theirs = _rows(TEACHER), _rows(OTHER_TEACHER)
    assert [row["seq"] for row in mine] == [1, 2]
    assert [row["seq"] for row in theirs] == [1, 2]
    assert [row["id"] for row in theirs] == other_ids
    # 兩條鏈的每一條都**不相同**：`teacher_name` 本身是參與哈希的 9 鍵之一（隔離由此更硬）
    assert mine[0]["payload_hash"] != theirs[0]["payload_hash"]
    assert mine[0]["prev_hash"] != theirs[0]["prev_hash"]
    # 但兩條鏈各自的第 1 條都以 `GENESIS_HASH` 起算 → 誰也不引用誰（真隔離）
    for teacher in (TEACHER, OTHER_TEACHER):
        first = _rows(teacher)[0]
        assert first["prev_hash"] == learning_service.compute_link_hash(
            1, first["event_type"], first["payload_hash"], learning_service.GENESIS_HASH)
    assert learning_service.next_seq(TEACHER) == learning_service.next_seq(OTHER_TEACHER) == 3

    _raw_execute("UPDATE agent_learning_events SET payload_hash = ? "
                 "WHERE teacher_name = ? AND seq = 2", ("f" * 64, TEACHER))
    assert learning_service.verify_learning_chain(TEACHER)["ok"] is False
    assert learning_service.verify_learning_chain(TEACHER)["first_bad_seq"] == 2
    assert learning_service.verify_learning_chain(OTHER_TEACHER) == {
        "ok": True, "checked": 2, "first_bad_seq": None, "reason": "ok"}


def test_ten_writes_keep_audit_tables_untouched(db):
    """⑧ §3.3 / A6：連寫 10 條學習事件 → 階段三表與兩張業務表**一行都沒動**（零審計）。

    `seq` 這一輪全部走**自動分配**（不顯式傳）→ 順帶覆蓋 `next_seq()` 的分配路徑。
    """
    audited = ("agent_stage_state", "agent_stage_config", "agent_stage_log",
               "drafts", "patient_records")
    before = {table: _raw_scalar("SELECT COUNT(*) FROM %s" % table) for table in audited}
    before_events = _raw_scalar("SELECT COUNT(*) FROM agent_learning_events")

    for index in range(10):
        seq, event_type, created_at, _, _, detail = SPECS[index % 3]
        learning_service.insert_learning_event(
            TEACHER, event_type, detail, lineage_id=LINEAGE_ID, patient_name=PATIENT_NAME,
            draft_id=100 + index, template_id=7, created_at=created_at)

    after = {table: _raw_scalar("SELECT COUNT(*) FROM %s" % table) for table in audited}
    assert after == before, "學習事件寫入動了別的表"
    assert _raw_scalar("SELECT COUNT(*) FROM agent_learning_events") == before_events + 10
    assert learning_service.verify_learning_chain(TEACHER) == {
        "ok": True, "checked": 10, "first_bad_seq": None, "reason": "ok"}
    assert [row["seq"] for row in _rows()] == list(range(1, 11))


def test_flag_off_values_and_zero_sql(sql_log, monkeypatch):
    """⑨ §6：默認 off（未設 / off / 0 / false / no → False），且 flag 判讀**一條 SQL 都不發**。"""
    monkeypatch.delenv("LEARNING_ENABLED", raising=False)
    assert learning_service.learning_enabled() is False
    for value in ("off", "0", "false", "no", "OFF", " off "):
        monkeypatch.setenv("LEARNING_ENABLED", value)
        assert learning_service.learning_enabled() is False, value
    assert _statements(sql_log) == []          # flag 判讀零 SQL、零副作用、不讀庫


def test_flag_on_values(monkeypatch):
    """⑨ §6：on / 1 / true / yes（大小寫無關、可帶空白）→ True；且與三套既有 flag **逐字同款**。"""
    for value in ("on", "1", "true", "yes", "ON", "YES", " True "):
        monkeypatch.setenv("LEARNING_ENABLED", value)
        assert learning_service.learning_enabled() is True, value

    import agent_stage_service
    import lineage_service
    import template_service

    assert (learning_service.LEARNING_ENABLED_VALUES
            == agent_stage_service.AGENT_STAGE_ENABLED_VALUES
            == lineage_service.LINEAGE_ENABLED_VALUES
            == template_service.TEMPLATE_API_ENABLED_VALUES
            == ("on", "1", "true", "yes"))


def test_insert_rejects_bad_inputs_and_writes_nothing(db):
    """邊界：非法入參一律 `ValueError`，且**一行都不落庫** —— 寧可拒絕寫入，也不留一條斷鏈。"""
    _insert(0)
    before = _raw_scalar("SELECT COUNT(*) FROM agent_learning_events")

    # 服務層：空老師名 / 白名單外事件 / 跳號 / 復用號
    with pytest.raises(ValueError):
        learning_service.insert_learning_event("", "draft_generated", {})
    with pytest.raises(ValueError):
        learning_service.insert_learning_event(TEACHER, "not_an_event", {})
    with pytest.raises(ValueError):
        _insert(1, seq=5)
    with pytest.raises(ValueError):
        _insert(1, seq=1)

    # 庫層原語：payload_json 不收 dict / 缺必填 / seq 非法 / 白名單外欄位
    with pytest.raises(ValueError):
        database.insert_learning_event(TEACHER, "draft_generated", seq=2,
                                       payload_json={"seq": 2},
                                       payload_hash="a" * 64, prev_hash="b" * 64)
    with pytest.raises(ValueError):
        database.insert_learning_event(TEACHER, "draft_generated", seq=2,
                                       payload_json="{}", prev_hash="b" * 64)
    with pytest.raises(ValueError):
        database.insert_learning_event(TEACHER, "draft_generated", seq=0,
                                       payload_json="{}", payload_hash="a" * 64,
                                       prev_hash="b" * 64)
    with pytest.raises(ValueError):
        database.insert_learning_event(TEACHER, "draft_generated", seq=2, id=9,
                                       payload_json="{}", payload_hash="a" * 64,
                                       prev_hash="b" * 64)

    assert _raw_scalar("SELECT COUNT(*) FROM agent_learning_events") == before
    assert learning_service.verify_learning_chain(TEACHER) == {
        "ok": True, "checked": 1, "first_bad_seq": None, "reason": "ok"}


# ============================================================================
# ④ 源碼級守護（AST）與「零接線」守護
# ============================================================================
def _parse_module(path):
    """把 `path` 解析成 AST（統一 `utf-8` 讀檔；語法錯誤就讓它拋 —— 那種錯必須立刻可見）。"""
    with open(path, encoding="utf-8") as handle:
        return ast.parse(handle.read())


def _learning_service_tree():
    return _parse_module(LEARNING_SERVICE_PATH)


def _docstring_nodes(tree):
    """模組 / 函數 / 類的 docstring 節點（用 `id()` 標記）。"""
    nodes = set()
    for node in ast.walk(tree):
        if isinstance(node, (ast.Module, ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            body = getattr(node, "body", [])
            if (body and isinstance(body[0], ast.Expr) and isinstance(body[0].value, ast.Constant)
                    and isinstance(body[0].value.value, str)):
                nodes.add(id(body[0].value))
    return nodes


def _code_string_literals(tree):
    """**代碼裡**的字符串常量（排除 docstring）；註釋不在 AST 裡，天然排除。

    口徑與 Epic 2 的「提到可以、import 不行」同款：docstring / 註釋轉述設計偽碼是允許的
    （本文件與 `learning_service.py` 都大量引用偽碼），但只要**真的寫下一條 SQL**，就會被抓。
    """
    docs = _docstring_nodes(tree)
    return [node.value for node in ast.walk(tree)
            if isinstance(node, ast.Constant) and isinstance(node.value, str)
            and id(node) not in docs]


def _imported_roots(tree):
    roots = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            roots.update(alias.name.split(".")[0] for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            roots.add(node.module.split(".")[0])
    return roots


def _database_attrs(tree):
    """本模組取用的 `database` 屬性名（含 `_db().attr` 這種函數內延遲取用形式）。"""
    names = set()
    for node in ast.walk(tree):
        if not isinstance(node, ast.Attribute):
            continue
        value = node.value
        if isinstance(value, ast.Name) and value.id == "database":
            names.add(node.attr)
        elif (isinstance(value, ast.Call) and isinstance(value.func, ast.Name)
              and value.func.id == "_db"):
            names.add(node.attr)
    return names


def test_source_guard_zero_sql_zero_audit_zero_capability():
    """⑩ 源碼級守護（CTO step 3.2 補充 3 + Epic 2 §2.2 ⓮/⓯ 兩組白名單）：

      · 零 `import sqlite3`（頂層與函數內都不許）、零 SQL 關鍵字**字面量**（SQL 全在 `database.py`）；
      · 零 `_stage_audit` / `require_capability` / `permission_denied`（不許借道寫階段審計）；
      · 零 `current_stage`（Epic 2 的唯一能力閘門，全倉白名單只含 `agent_stage_service` / `agent_stage_api`）；
      · 零 `agent_stage_log`（A6：兩張表、兩條流）；
      · **只讀 + 只增**：只碰四個庫層原語，零 `get_connection` / `execute` / `commit`；
      · `import database` **不在模組頂層**（函數內延遲 import，模組載入期不碰庫）。
    """
    tree = _learning_service_tree()
    imports = _imported_roots(tree)

    assert "sqlite3" not in imports
    assert "sqlite3" not in _code_string_literals(tree)

    forbidden = SQL_KEYWORD_PATTERN.search
    for text in _code_string_literals(tree):
        found = forbidden(text)
        assert found is None, \
            "learning_service 出現 SQL 字面量：%r（命中關鍵字 %s）" % (text, found and found.group(0))

    for name in ("_stage_audit", "require_capability", "permission_denied",
                 "current_stage", "agent_stage_log"):
        assert name not in imports, name
        assert name not in _code_string_literals(tree), name
        assert not any(isinstance(node, ast.Attribute) and node.attr == name
                       for node in ast.walk(tree)), name

    assert _database_attrs(tree) == {"next_seq", "get_last_learning_event",
                                     "get_learning_events", "insert_learning_event"}
    all_attrs = {node.attr for node in ast.walk(tree) if isinstance(node, ast.Attribute)}
    assert all_attrs.isdisjoint({"get_connection", "execute", "executemany", "commit", "cursor"})

    top_level = set()
    for node in tree.body:
        if isinstance(node, ast.Import):
            top_level.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom):
            top_level.add(node.module or "")
    assert "database" not in top_level, "database 必須在函數內延遲 import"


def test_no_wiring_in_step_3_2():
    """【本步鐵律】3.2 只落骨架：四個待接線點與**任何**生產模組都不得引用 `learning_service`（零接線）。

    為什麼要能一眼看出「沒接線」：本步的驗收前提是「flag off = 與今天 1:1」——
    一旦有模組 import 了它（或往接線點的函數體裡塞了寫事件的一行），這個前提就必須重新證明。

    兩層守護：
      · **函數體級**：`database.insert_draft` / `database.update_draft_content` /
        `agent_stage_service._evaluate` 三段源碼裡零 `learning_service` / `agent_learning_events` /
        `LEARNING_ENABLED`（本步不得動它們一個字節）；
      · **模組級**：backend 根目錄下**除測試文件與 `learning_service.py` 本身**，
        沒有任何模組 import 過 `learning_service`（接線屬 3.3 / 3.4 / 3.5）。
    """
    guarded = {
        "database.py": ("insert_draft", "update_draft_content"),
        "agent_stage_service.py": ("_evaluate",),
    }
    for filename, function_names in guarded.items():
        path = os.path.join(BACKEND_DIR, filename)
        with open(path, encoding="utf-8") as handle:
            source = handle.read()
        tree = ast.parse(source)
        seen = set()
        for node in ast.walk(tree):
            if isinstance(node, ast.FunctionDef) and node.name in function_names:
                seen.add(node.name)
                segment = ast.get_source_segment(source, node)
                for marker in ("learning_service", "agent_learning_events", "LEARNING_ENABLED"):
                    assert marker not in segment, \
                        "%s::%s 已被 3.2 接線（出現 %s）" % (filename, node.name, marker)
        assert seen == set(function_names), "%s 缺函數：%s" % (filename, sorted(set(function_names) - seen))

    # 兩個未來的接線點（3.3 / 3.4）今天連表名都不該出現（database.py 例外：它是庫層落點）
    for filename in ("agent_stage_service.py", "template_api.py", "main.py"):
        with open(os.path.join(BACKEND_DIR, filename), encoding="utf-8") as handle:
            source = handle.read()
        assert "agent_learning_events" not in source, "%s 出現學習事件表名" % filename

    for filename in sorted(os.listdir(BACKEND_DIR)):
        if not filename.endswith(".py") or filename.startswith("test_"):
            continue                                          # 用例文件本來就該引用它
        if filename in ("conftest.py", "learning_service.py"):
            continue
        tree = _parse_module(os.path.join(BACKEND_DIR, filename))
        assert "learning_service" not in _imported_roots(tree), \
            "%s 在 step 3.2 就 import 了 learning_service（接線屬 3.3 / 3.4）" % filename


# ============================================================================
# ⑤ 存儲探針（§7：flag 與「存儲就緒」是兩件事）
# ============================================================================
def test_store_ready_true_and_probe_is_readonly(db, sql_log):
    """§7：遷移到位 → `learning_store_ready()` True；探測只發**一條只讀**語句（不建表、不寫入）。"""
    assert learning_service.learning_store_ready() is True
    statements = _statements(sql_log)
    assert len(statements) == 1
    assert statements[0].lstrip().upper().startswith("SELECT")
    assert SQL_KEYWORD_PATTERN.search(statements[0]).group(0).upper() == "SELECT"


def test_store_ready_false_without_table(monkeypatch, tmp_path):
    """§7：遷移沒跑（庫裡沒有這張表）→ False；探針**絕不建表 / 絕不寫入**。"""
    void_db = tmp_path / "void.db"
    monkeypatch.setattr(database, "DB_PATH", str(void_db))
    assert learning_service.learning_store_ready() is False

    conn = sqlite3.connect(str(void_db))
    try:
        tables = [row[0] for row in conn.execute("SELECT name FROM sqlite_master WHERE type = 'table'")]
    finally:
        conn.close()
    assert tables == [], "探針竟然建了表：%r" % (tables,)
