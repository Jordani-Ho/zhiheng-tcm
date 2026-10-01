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


# 【3.3-b 白名單收窄 · 3.3-d 追加接口層 · 3.3-e 追加 `_evaluate`】`learning_service` 的**引用白名單**：`{"檔名": ("函數名", ...)}`。
#   為什麼要收窄：3.2 的「任何生產模組零 import」在當時是正確口徑（那時零接線）；3.3-b 起
#   `agent_stage_service.py` 新增兩個適配器，**函數內**延遲 import 學習服務層是設計的一部分
#   （白名單唯一處）。守護因此從「零 import」升級成「只許這兩處」——
#   頂層 import（任何模組）/ 白名單外的模組 / 同模組的其他函數體，三條照舊紅。
#   【3.3-d 追加】接口層 `template_api.py` 的三個狀態端點（`publish` / `archive` / `activate`）各在
#   **函數體內**延遲 import 並調一次 `record_template_configured()`（與同檔 `_check_lineage()` 的
#   `import lineage_service` 同款寫法）→ 白名單追加的就是**這三個函數名**，而不是 `None`（模組頂層）：
#   頂層 import 照舊紅，這一格因此沒有放寬 3.2 的口徑。
#   庫層落點（3.3-c）走既有轉發器、對 `learning_service` 零引用，故 `database.py` 至今不在白名單內。
#   【3.3-e 追加】`_evaluate`（`learning_event_emitted` / `agent_updated` 兩條事件）函數內延遲 import
#   —— 本步即該子步的放行（原注「`_evaluate`（3.3-e）的放行由該子步追加」逐字兌現）；
#   其餘「最終形」（轉發點唯一守護）仍在 3.3-f 收口。
ALLOWED_WIRING = {
    "agent_stage_service.py": ("on_draft_generated", "on_draft_modified", "_evaluate"),
    "template_api.py": ("publish_template", "archive_template", "activate_template"),
}


def _imports_learning_service(node):
    """該 AST 節點是否為 `import learning_service` / `from learning_service …`（按**根模組名**判定）。"""
    if isinstance(node, ast.Import):
        return any(alias.name.split(".")[0] == "learning_service" for alias in node.names)
    if isinstance(node, ast.ImportFrom):
        return (node.module or "").split(".")[0] == "learning_service"
    return False


def _learning_import_owners(tree):
    """每個 `… learning_service` 節點 → 它的**最近外層函數名**（模組頂層 → `None`）之集合。

    歸屬必須按「最近」而非「任意外層」：`ast.walk()` 不分層，若直接拿它當「所在函數」，巢狀函數裡的
    import 會被記到外層函數名下 —— 那樣白名單就漏了一格（內層函數偷偷 import 也算數）。故這裡自己
    遞迴下潛：進入 `FunctionDef` 時**換 owner**（內層覆蓋外層），回到同層時自然回到外層的 owner。
    """
    sites = set()

    def _walk(node, owner):
        if _imports_learning_service(node):
            sites.add((owner, node.lineno))
        for child in ast.iter_child_nodes(node):
            _walk(child, child.name
                  if isinstance(child, (ast.FunctionDef, ast.AsyncFunctionDef)) else owner)

    _walk(tree, None)
    return sites


def test_no_wiring_in_step_3_2():
    """【本步鐵律】3.2 只落骨架：四個待接線點與**任何**生產模組都不得引用 `learning_service`（零接線）。

    為什麼要能一眼看出「沒接線」：本步的驗收前提是「flag off = 與今天 1:1」——
    一旦有模組 import 了它（或往接線點的函數體裡塞了寫事件的一行），這個前提就必須重新證明。

    兩層守護：
      · **函數體級（【3.3-e 收窄：只剩庫層兩個落點】）**：`database.insert_draft` /
        `database.update_draft_content` 兩段源碼裡零 `learning_service` / `agent_learning_events` /
        `LEARNING_ENABLED`（庫層只許經唯一轉發器 `_call_agent_stage_hook()`，不許自己碰學習服務層）；
      · **模組級（【3.3-b 收窄為白名單形 · 3.3-d 追加接口層 · 3.3-e 追加 `_evaluate`】）**：backend 根目錄下**除測試文件與
        `learning_service.py` 本身**，只放行 `ALLOWED_WIRING` 逐項列出的「檔名 → 函數名」——
        今天 = `agent_stage_service.py` 的 `on_draft_generated` / `on_draft_modified`（3.3-b 服務層適配器）
        + `_evaluate`（3.3-e 的 `learning_event_emitted` / `agent_updated` 收口）
        + `template_api.py` 的 `publish_template` / `archive_template` / `activate_template`（3.3-d 接口層三個
        狀態端點）的**函數體內**延遲 import。**頂層 import（任何模組）/
        白名單外的模組 / 同模組的其他函數體**三條照舊紅 —— 3.2 的口徑因此只是**收窄**，沒有放寬。
        【變更披露 · CTO R4】**本條是既有斷言變更**：原斷言
        `"learning_service" not in _imported_roots(tree)` 表達不了「哪些位置允許」，故改為
        「按最近外層函數歸屬的白名單比對」（判定助手見下方 `_learning_import_owners()`）；
        庫層落點（3.3-c）走既有轉發器、對 `learning_service` **零引用**（因此不需放行）。
        【變更披露 · 3.3-e】**本條再次變更既有斷言**：`guarded` 撤掉 `agent_stage_service.py: ("_evaluate",)`
        —— 3.2 立的「`_evaluate` 三段源碼零引用」在 3.2 → 3.3-c 期間成立（那時它確實零引用），
        3.3-e 起 `_evaluate` 由上面的白名單放行（依據 = 本文件原注「`_evaluate`（3.3-e）的放行
        由該子步追加」）；**庫層那格照舊函數體級守護**，模組級與頂層兩條一條未鬆。
        **最終形（`database.py` 的「庫層 → 服務層轉發點唯一」守護）仍在 3.3-f 收口。**
    """
    guarded = {
        "database.py": ("insert_draft", "update_draft_content"),
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
    # 【3.3-e】`agent_stage_service.py` 的 `_evaluate` 已獲白名單放行「引用 `learning_service`」，
    #   但**表名字面量照舊不許**（學習事件的表名只屬 `database.py` / 遷移 / 服務層）——
    #   本條因此一字未改；名單不變 = 這條紅線不隨接線放寬。
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
        allowed = ALLOWED_WIRING.get(filename, ())    # 【3.3-b / 3.3-d / 3.3-e】白名單（最終形在 3.3-f）
        offenders = sorted((owner or "<模組頂層>", lineno)
                           for owner, lineno in _learning_import_owners(tree)
                           if owner not in allowed)
        assert offenders == [], \
            ("%s 出現了白名單外的 learning_service 引用：%r（3.3-e 白名單 = %r；"
             "頂層 import / 白名單外的模組 / 同模組的其他函數體一律紅，最終形在 3.3-f）"
             % (filename, offenders, ALLOWED_WIRING))


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


# ============================================================================
# ⑥ step 3.3-a：差異記錄純函數（§3.2 / A8）+ 5 個事件寫入入口（`record_*`）
# ----------------------------------------------------------------------------
# CTO 2026-09-30 step 3.3-a 指令要求本組用例釘住五件事：
#   · R10 口徑（`field` / `before_hash` / `after_hash` / `wording_changed`）逐條寫死期望；
#   · `field` 的包裹符剝法與 `agent_stage_service._split_heading()` **同一把尺子**（行為對照）；
#   · flag 門（零 SQL）與存儲門（不建表、不拋、不打日誌）各自獨立可驗；
#   · best-effort：寫入期任何異常 → 吞掉 + 一行**繁體** `[warn]`，不冒泡、不回退業務；
#   · `detail` 逐鍵 = 設計 §3.2 的五類骨架（鍵集合不放寬）。
# 本組**不動** conftest（`LEARNING_ENABLED` 仍默認 off）：需要 flag on 的用例自行 monkeypatch，
# 用完自動還原 —— 這是為了逐字節保住 ⑨/⑫ 的 flag-off 基線。
# ============================================================================
DRAFT_ID = 101                                  # 與 `SPECS` 裡那條草案同號（便於交叉對讀）

# 3.3-a 的樣本正文：**已歸一化**的形態（單空格分隔 = `_normalize_metric_text()` 的產物）
DIFF_BEFORE = "【主訴（學生原話）】 頭痛三日 【舌象】 舌淡紅 【脈象】"
DIFF_AFTER = "【主訴（學生原話）】 頭痛三日，夜間加重 【舌象】 舌淡紅 【脈象】"
STRUCT_BEFORE = "【主訴】 頭痛 【舌象】 舌淡紅"
STRUCT_AFTER = "【主訴】 頭痛 【脈象】 弦細"


def _text_hash(text):
    """獨立重述 `sha256(文本)`（**不經** `learning_service.sha256_hex()`）：期望值必須來自本文件。"""
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def _record_all(teacher_name=TEACHER):
    """把 5 個 `record_*` 各調一次（參數固定）→ `[(函數名, 返回值), ...]`（順序 = §3.1 五類事件）。

    參數刻意用**固定字面量**：happy path 的期望 `detail` 照同一份字面量寫死（見下）。
    """
    return [
        ("record_template_configured", learning_service.record_template_configured(
            teacher_name, template_id=7, template_type="record", version=2,
            from_status="draft", to_status="active", lineage_id=LINEAGE_ID)),
        ("record_draft_generated", learning_service.record_draft_generated(
            teacher_name, draft_id=DRAFT_ID, template_id=7, template_version=2,
            content_hash=DETAIL_DRAFT_GENERATED["content_hash"], degraded=False,
            patient_name=PATIENT_NAME, lineage_id=LINEAGE_ID)),
        ("record_draft_modified", learning_service.record_draft_modified(
            teacher_name, DIFF_BEFORE, DIFF_AFTER, draft_id=DRAFT_ID, template_id=7,
            patient_name=PATIENT_NAME, lineage_id=LINEAGE_ID)),
        ("record_learning_event_emitted", learning_service.record_learning_event_emitted(
            teacher_name, source_event_types=("draft_generated", "draft_modified"),
            difference_kinds=("field_diff", "wording_changed"), sample_count=3,
            lineage_id=LINEAGE_ID)),
        ("record_agent_updated", learning_service.record_agent_updated(
            teacher_name, from_stage="learning", to_stage="apprentice",
            capability="predict_pattern", metrics_hash=DETAIL_DRAFT_GENERATED["content_hash"],
            lineage_id=LINEAGE_ID)),
    ]


# ---- 一、純函數：`compute_content_diff` / `split_sections`（無 DB、無 flag）----

def test_content_diff_identical_or_empty_texts_have_no_field_diff():
    """空串 / 逐字相同 / 非字符串 → `field_diff == []`、`wording_changed is False`（零假陽性）。"""
    empty = {"field_diff": [], "wording_changed": False}
    assert learning_service.compute_content_diff("", "") == empty
    assert learning_service.compute_content_diff(DIFF_BEFORE, DIFF_BEFORE) == empty
    assert learning_service.compute_content_diff(STRUCT_BEFORE, STRUCT_BEFORE) == empty
    assert learning_service.compute_content_diff(None, None) == empty          # 非字符串 → 空串，不拋
    assert learning_service.compute_content_diff(123, 123) == empty

    # 返回體**恆為兩鍵**（設計 §3.2 的骨架：鍵集合不放寬、不加鍵）
    diff = learning_service.compute_content_diff(DIFF_BEFORE, DIFF_AFTER)
    assert set(diff) == {"field_diff", "wording_changed"}
    assert set(learning_service.compute_content_diff("", "").keys()) == {"field_diff", "wording_changed"}


def test_content_diff_missing_side_uses_frozen_empty_text_hash():
    """單側缺失（段被加 / 被刪）→ 缺的那側 = `EMPTY_TEXT_HASH`（寫死 + 獨立重述 `sha256("")`）。"""
    assert learning_service.EMPTY_TEXT_HASH == _text_hash("")
    assert learning_service.EMPTY_TEXT_HASH == (
        "e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855")
    assert learning_service.sha256_hex("") == learning_service.EMPTY_TEXT_HASH

    added = learning_service.compute_content_diff("", "【主訴】 頭痛")
    assert added == {"field_diff": [{"field": "主訴",
                                     "before_hash": learning_service.EMPTY_TEXT_HASH,
                                     "after_hash": _text_hash("頭痛")}],
                     "wording_changed": False}      # 只有一側有具名標題 → 不聲稱「僅措辭變化」

    removed = learning_service.compute_content_diff("【主訴】 頭痛", "")
    assert removed["field_diff"] == [{"field": "主訴",
                                      "before_hash": _text_hash("頭痛"),
                                      "after_hash": learning_service.EMPTY_TEXT_HASH}]
    assert removed["wording_changed"] is False


def test_content_diff_wording_only_change_is_wording_changed():
    """標題集合相同、只有正文變 → `wording_changed is True` + 恰好一條 `field_diff`（哈希逐條寫死）。"""
    diff = learning_service.compute_content_diff(DIFF_BEFORE, DIFF_AFTER)
    assert diff == {
        "field_diff": [{"field": "主訴（學生原話）",
                        "before_hash": _text_hash("頭痛三日"),
                        "after_hash": _text_hash("頭痛三日，夜間加重")}],
        "wording_changed": True,
    }
    # 段標題逐字保留（剝掉包裹符、其餘一個字都不動）；正文**不出現**在返回體裡（只放哈希 —— A5 取向）
    literal = json.dumps(diff, ensure_ascii=False)
    assert "主訴（學生原話）" in literal
    assert "頭痛三日" not in literal and "舌淡紅" not in literal


def test_content_diff_structural_change_is_not_wording_changed():
    """段增 / 段刪 → `wording_changed is False`；順序 = **after 出現順序在前、before 獨有段在後**。"""
    diff = learning_service.compute_content_diff(STRUCT_BEFORE, STRUCT_AFTER)
    assert diff == {
        "field_diff": [
            {"field": "脈象", "before_hash": learning_service.EMPTY_TEXT_HASH,
             "after_hash": _text_hash("弦細")},
            {"field": "舌象", "before_hash": _text_hash("舌淡紅"),
             "after_hash": learning_service.EMPTY_TEXT_HASH},
        ],
        "wording_changed": False,
    }

    # 「只加了一段、既有段一字未動」→ 仍是結構變化（標題集合不等），field_diff 只有新增那格
    added = learning_service.compute_content_diff(STRUCT_BEFORE, STRUCT_BEFORE + " 【脈象】 弦細")
    assert [item["field"] for item in added["field_diff"]] == ["脈象"]
    assert added["wording_changed"] is False


def test_content_diff_empty_named_section_still_counts_as_structure():
    """空段（標題在、正文空）**也是一個段** —— 被整段刪掉時**不得**誤判成「僅措辭變化」。"""
    assert learning_service.split_sections("【主訴】 頭痛 【舌象】") == [
        ("", ""), ("主訴", "頭痛"), ("舌象", "")]
    diff = learning_service.compute_content_diff("【主訴】 頭痛 【舌象】", "【主訴】 頭痛啊")
    assert diff["wording_changed"] is False            # 舌象段沒了 = 結構變化
    assert [item["field"] for item in diff["field_diff"]] == ["主訴", "舌象"]


def test_split_sections_merges_duplicate_titles_and_keeps_untitled_body():
    """同名段合併（單空格相接）；**沒有包裹符**的 `主訴：…` 認不出來 → 整篇一個無標題段（邊界 ②）。"""
    assert learning_service.split_sections("【舌象】 舌淡紅 【舌象】 苔薄白") == [
        ("", ""), ("舌象", "舌淡紅 苔薄白")]
    assert learning_service.split_sections("主訴：頭痛 舌象：舌淡紅") == [
        ("", "主訴：頭痛 舌象：舌淡紅")]
    assert learning_service.split_sections("") == [("", "")]
    assert learning_service.split_sections(None) == [("", "")]
    assert learning_service.UNTITLED_FIELD == ""


def test_section_field_bracket_table_matches_split_heading():
    """【同一把尺子】`split_section_field()` ↔ `agent_stage_service._split_heading()`：四對包裹符逐個對照。

    本文件**不 import** 生產模組（CTO 追加 1）→ 「同一個剝法」只能靠**行為對照**釘住：拿對方本尊
    逐 token 比對，任何一側改了包裹符表 / 剝法，本條立刻紅。
    """
    import agent_stage_service
    for token in ("【主訴（學生原話）】", "[舌象]", "〔脈象〕", "《施治方案》", "舌象", "【主訴】費解"):
        assert learning_service.split_section_field(token) == agent_stage_service._split_heading(token)[0], token
    assert learning_service.split_section_field(None) == ""          # 不拋
    assert learning_service.split_section_field("") == ""
    assert tuple(learning_service.SECTION_BRACKETS) == (
        ("【", "】"), ("[", "]"), ("〔", "〕"), ("《", "》"))


def test_section_heading_token_caps_field_length_at_twenty():
    """邊界 ③：標題內層 ≤ `FIELD_MAX_CHARS`（20）才算段標題；超長 `【…】` 一律當正文（正文不進 `field`）。"""
    assert learning_service.FIELD_MAX_CHARS == 20
    ok_title = "字" * learning_service.FIELD_MAX_CHARS
    assert learning_service.split_sections("【%s】 正文" % ok_title) == [("", ""), (ok_title, "正文")]

    long_title = "字" * (learning_service.FIELD_MAX_CHARS + 1)
    sections = learning_service.split_sections("【%s】 正文" % long_title)
    assert sections == [("", "【%s】 正文" % long_title)]              # 認不出 → 全歸無標題段
    assert all(len(field) <= learning_service.FIELD_MAX_CHARS for field, _ in sections)


def test_content_diff_normalization_is_caller_side():
    """CTO 追加 1（方案 c）：歸一化在**調用方** —— 歸一化後無差；直接傳原文 → **假陽性**（docstring 已明寫）。"""
    import agent_stage_service
    raw = "【主訴】 頭痛   三日"                  # 段內連續空白（未折疊）＝ 未歸一化
    normalized = "【主訴】 頭痛 三日"              # 已歸一化
    assert agent_stage_service._normalize_metric_text(raw) == normalized
    assert learning_service.compute_content_diff(normalized, normalized) == {
        "field_diff": [], "wording_changed": False}

    false_positive = learning_service.compute_content_diff(raw, normalized)
    assert false_positive == {
        "field_diff": [{"field": "主訴", "before_hash": _text_hash("頭痛   三日"),
                        "after_hash": _text_hash("頭痛 三日")}],
        "wording_changed": True,
    }

    # CRLF 也是調用方折疊的（`\r\n` → 空格）：折疊後段結構與已歸一化文本逐格相同
    normalized_crlf = agent_stage_service._normalize_metric_text("【主訴】\r\n頭痛\r\n三日")
    assert normalized_crlf == "【主訴】 頭痛 三日"
    assert learning_service.split_sections(normalized_crlf) == [("", ""), ("主訴", "頭痛 三日")]


def test_content_diff_truncation_belongs_to_caller():
    """截斷（`_normalize_metric_text(text, limit)`）屬調用方：截斷後不可區分 → 無 diff；不截斷 → 有 diff。

    生產口徑的截斷長度是 2000（`_normalize_metric_text(text, 2000)`，3.3 的適配器決定）；
    這裡用 `limit = 10` 只是為了讓期望值一眼能數出來 —— 被證的命題（「截斷在調用方」）完全相同。
    """
    import agent_stage_service
    base = "【主訴】 頭痛三日，夜間加重"
    longer = base + "，納差"
    limit = 10
    short_base = agent_stage_service._normalize_metric_text(base, limit)
    short_longer = agent_stage_service._normalize_metric_text(longer, limit)
    assert short_base == short_longer == "【主訴】 頭痛三日，"
    assert learning_service.compute_content_diff(short_base, short_longer) == {
        "field_diff": [], "wording_changed": False}
    assert learning_service.compute_content_diff(
        agent_stage_service._normalize_metric_text(base),
        agent_stage_service._normalize_metric_text(longer))["field_diff"] != []


def test_content_diff_is_pure_and_touches_no_database(monkeypatch, tmp_path, sql_log):
    """純函數的活證：`DB_PATH` 指向空庫時照樣算得出來，且**零 SQL**、零建表、零寫入。"""
    void_db = tmp_path / "void.db"
    monkeypatch.setattr(database, "DB_PATH", str(void_db))
    diff = learning_service.compute_content_diff(DIFF_BEFORE, DIFF_AFTER)
    assert diff["wording_changed"] is True
    assert _statements(sql_log) == []
    assert (not void_db.exists()) or void_db.stat().st_size == 0


# ---- 二、5 個事件寫入入口（`record_*`）：happy path / 兩道門 / best-effort ----

def test_record_entry_points_write_five_event_shapes(db, monkeypatch):
    """happy path：五個入口各寫一條 —— `detail` 逐鍵 = 設計 §3.2；投影列 / A5 / 鏈自洽一次釘全。"""
    monkeypatch.setenv("LEARNING_ENABLED", "on")
    called = _record_all()
    assert [name for name, _ in called] == [
        "record_template_configured", "record_draft_generated", "record_draft_modified",
        "record_learning_event_emitted", "record_agent_updated"]
    assert [ok for _, ok in called] == [True] * 5

    rows = _rows()
    assert [row["event_type"] for row in rows] == list(learning_service.EVENT_TYPES)
    assert [row["seq"] for row in rows] == [1, 2, 3, 4, 5]
    assert learning_service.verify_learning_chain(TEACHER) == {
        "ok": True, "checked": 5, "first_bad_seq": None, "reason": "ok"}

    expected_details = [
        {"template_id": 7, "template_type": "record", "version": 2,
         "from_status": "draft", "to_status": "active"},
        {"template_version": 2, "content_hash": DETAIL_DRAFT_GENERATED["content_hash"],
         "degraded": False},
        {"field_diff": [{"field": "主訴（學生原話）", "before_hash": _text_hash("頭痛三日"),
                         "after_hash": _text_hash("頭痛三日，夜間加重")}],
         "wording_changed": True},
        {"source_event_types": ["draft_generated", "draft_modified"],
         "difference_kinds": ["field_diff", "wording_changed"], "sample_count": 3},
        {"from_stage": "learning", "to_stage": "apprentice", "capability": "predict_pattern",
         "metrics_hash": DETAIL_DRAFT_GENERATED["content_hash"]},
    ]
    expected_projections = [(0, 7), (DRAFT_ID, 7), (DRAFT_ID, 7), (0, 0), (0, 0)]
    # A5：只落哈希（明文永不落庫）。兩個帶患者上下文的入口 → 具體姓名哈希；
    # 其餘三類事件不涉及具體患者（接線點無患者上下文）→ 空名哨兵 `sha256("")[:16]`。
    expected_name_hashes = [FROZEN_EMPTY_NAME_HASH, FROZEN_PATIENT_NAME_HASH,
                            FROZEN_PATIENT_NAME_HASH, FROZEN_EMPTY_NAME_HASH,
                            FROZEN_EMPTY_NAME_HASH]
    for row, detail, projection, name_hash in zip(rows, expected_details,
                                                  expected_projections, expected_name_hashes):
        payload = json.loads(row["payload_json"])
        assert set(payload) == set(learning_service.PAYLOAD_TOP_LEVEL_KEYS)     # 頂層 9 鍵不變
        assert payload["detail"] == detail                                      # 逐鍵，鍵集合不放寬
        assert (row["draft_id"], row["template_id"]) == projection               # 投影列 = 同名校驗
        assert row["patient_name_hash"] == name_hash                            # A5：只落哈希（逐事件期望）
        assert len(name_hash) == learning_service.PATIENT_NAME_HASH_LEN == 16   # A5 長度見證
        assert row["patient_name_hash"] == payload["patient_name_hash"]         # 列 = payload 同名鍵

    dumped = json.dumps([dict(row) for row in rows], ensure_ascii=False)
    assert PATIENT_NAME not in dumped                                            # 明文姓名一個字都不落庫


def test_record_entry_points_flag_off_are_zero_sql_and_silent(monkeypatch, capsys, sql_log):
    """flag 門（§6）：`LEARNING_ENABLED` off → 五個入口一律 `False`，**零 SQL**（連存儲探針都不發）、零輸出。"""
    monkeypatch.delenv("LEARNING_ENABLED", raising=False)
    assert [ok for _, ok in _record_all()] == [False] * 5
    assert _statements(sql_log) == []
    assert capsys.readouterr().out == ""            # flag off 是正常態，不是異常 → 不打 warn


def test_record_entry_points_store_missing_is_silent_false(monkeypatch, tmp_path, capsys):
    """存儲門（§7）：flag on 但表沒就位 → `False` + **靜默**（不建表、不拋、不打日誌；503 屬 3.5 接口層）。"""
    void_db = tmp_path / "void.db"
    monkeypatch.setenv("LEARNING_ENABLED", "on")
    monkeypatch.setattr(database, "DB_PATH", str(void_db))
    assert [ok for _, ok in _record_all()] == [False] * 5
    assert capsys.readouterr().out == ""

    conn = sqlite3.connect(str(void_db))
    try:
        tables = [row[0] for row in conn.execute("SELECT name FROM sqlite_master WHERE type = 'table'")]
    finally:
        conn.close()
    assert tables == [], "寫入入口竟然建了表：%r" % (tables,)


def test_record_entry_points_swallow_failures_with_traditional_warning(db, monkeypatch, capsys):
    """best-effort（§9-聲明一）：真實 `ValueError` 與寫入期任意異常都走同一條出口 ——

    `False` + 一行**繁體** `[warn]`（帶函數名，可定位）、**不冒泡**、**零寫入**（不留「寫一半」的節）。
    """
    monkeypatch.setenv("LEARNING_ENABLED", "on")
    assert learning_service.record_draft_generated("", draft_id=DRAFT_ID, content_hash="x") is False
    first = capsys.readouterr().out
    assert "[warn]" in first and "必須給 teacher_name" in first
    assert _rows() == []

    def boom(*args, **kwargs):
        raise RuntimeError("庫炸了")

    monkeypatch.setattr(learning_service, "insert_learning_event", boom)
    assert [ok for _, ok in _record_all()] == [False] * 5
    out = capsys.readouterr().out
    assert out.count("[warn]") == 5
    assert "寫入學習事件失敗" in out and "record_draft_modified" in out
    assert "業務結果不受影響" in out
    assert _rows() == []


def test_record_detail_coercions_never_put_none_in_payload(db, monkeypatch):
    """`detail` 兜底：`None` / 怪值一律歸一成基礎類型（`int` / `str` / `list` / `bool`）→ payload 無 `None`。"""
    monkeypatch.setenv("LEARNING_ENABLED", "on")
    assert learning_service.record_learning_event_emitted(
        TEACHER, source_event_types=None, difference_kinds="draft_modified",
        sample_count="7") is True
    assert learning_service.record_template_configured(
        TEACHER, template_id=None, version="x") is True

    details = [json.loads(row["payload_json"])["detail"] for row in _rows()]
    assert details[0] == {"source_event_types": [], "difference_kinds": ["draft_modified"],
                          "sample_count": 7}
    assert details[1] == {"template_id": 0, "template_type": "", "version": 0,
                          "from_status": "", "to_status": ""}
    for detail in details:
        assert None not in detail.values()


# ============================================================================
# ⑦ step 3.3-b：服務層適配器（`agent_stage_service.on_draft_generated` / `on_draft_modified`）
# ----------------------------------------------------------------------------
# 對齊：CTO 2026-09-30 step 3.3-b 指令 + 設計 §一-1（冪等跳過）/ §3.3 A5 A6 / §9-聲明二。
# 3.3-b 落**服務層適配器**（【3.3-c 已把兩個庫層落線點接上】）：`database.insert_draft()`（改 1）/
# `update_draft_content()`（改 4）經唯一轉發點 `database._call_agent_stage_hook()` 各發一節 ——
# 本組因此用兩條視角釘住它：**直接調適配器**（①-⑥）+ **走庫層唯一轉發點**（⑦ 的直調 +
# ⑧ 組的兩個真實業務路徑端到端）。
# 六件事（每件一個用例）：
#   · 閘門只認學習總閘：`LEARNING_ENABLED` off（階段閘刻意 on）→ 零 SQL、零行、恆 `None`；
#   · 階段閘 off / on 學習鏈**照寫**；`degraded` **現場**讀（每次調用現場讀一次，讀數換 → 內容換）；
#   · `field_diff == []` → **跳過寫事件**（§一-1：逐字相同的編輯不往鏈裡塞空節）；
#   · best-effort：任何異常 → 只留一行**繁體** `[warn]`（帶適配器名，可定位）、不冒泡、**恆 `None`**；
#   · **不代勞歸一化**（方案 c：歸一化在調用方）→ 傳原文會**假陽性**、傳 `_normalize_metric_text()`
#     的產物才跳過（⑥ 組 `test_content_diff_normalization_is_caller_side` 的**適配器層**版本）；
#   · 零階段面（§9-聲明二）：只寫 `agent_learning_events`，階段三表 / 業務兩表**一行都沒動**。
# 造數 / 斷言助手一律復用 ⑥ 組（`_rows` / `_statements` / `_raw_scalar` / `_text_hash` / `DIFF_*`…）；
# 源碼級守護在 `test_agent_stage.py` ⑮ 組追加的三條（兩處互為交叉驗證）。
# ============================================================================

def test_adapter_generated_flag_off_is_zero_sql_and_returns_none(db, monkeypatch, sql_log):
    """flag 門（A6 第一條）：`LEARNING_ENABLED` off（**階段閘刻意 on**）→ 兩個適配器都零 SQL、零行、`None`。

    「階段閘 on 也解不開學習事件」是本條的另一半：兩條鏈的閘各管各的流，判兩次只會多一個假歸因面。
    """
    import agent_stage_service

    monkeypatch.setenv("AGENT_STAGE_ENABLED", "on")            # 階段閘 on 不許解鎖學習事件
    monkeypatch.delenv("LEARNING_ENABLED", raising=False)      # 學習總閘默認 off
    mark = len(_statements(sql_log))

    assert agent_stage_service.on_draft_generated(
        TEACHER, DRAFT_ID, PATIENT_NAME, 7, 2, "content-hash", LINEAGE_ID) is None
    assert agent_stage_service.on_draft_modified(
        TEACHER, DRAFT_ID, PATIENT_NAME, DIFF_BEFORE, DIFF_AFTER) is None

    assert _statements(sql_log)[mark:] == [], "學習閘 off 時連存儲探針都不該發"
    assert _rows() == []


def test_adapter_writes_on_both_stage_flag_states_and_reads_degraded_live(db, monkeypatch):
    """A6（兩條鏈）+ `degraded` 現場讀：階段閘 off / on 都照寫；三次調用三次現場讀。

    第一次**不換任何讀數**：真 `generation_degraded()` 在階段閘 off 時只能是 `False`（§5.1 紅線①）。
    第二次把 `generation_degraded` 換成「記錄入參、回 `True`」的替身 → 事件裡的 `degraded` 必須跟著變
    `True`（若適配器改成預判 / 緩存結果 / 拿別的入參，這一格立刻紅）；第三次再換回 `False`。
    """
    import agent_stage_service

    monkeypatch.setenv("LEARNING_ENABLED", "on")
    monkeypatch.delenv("AGENT_STAGE_ENABLED", raising=False)   # 階段閘 off → 學習鏈照寫
    assert agent_stage_service.on_draft_generated(
        TEACHER, DRAFT_ID, PATIENT_NAME, 7, 2, "content-hash", LINEAGE_ID) is None

    seen = []

    def _degraded(teacher_name):
        seen.append(teacher_name)
        return True

    monkeypatch.setattr(agent_stage_service, "generation_degraded", _degraded)
    assert agent_stage_service.on_draft_generated(
        TEACHER, DRAFT_ID + 1, PATIENT_NAME, 7, 2, "content-hash", LINEAGE_ID) is None

    monkeypatch.setenv("AGENT_STAGE_ENABLED", "on")             # 階段閘 on → 學習鏈照寫（兩條鏈）
    monkeypatch.setattr(agent_stage_service, "generation_degraded", lambda teacher_name: False)
    assert agent_stage_service.on_draft_modified(
        TEACHER, DRAFT_ID, PATIENT_NAME, DIFF_BEFORE, DIFF_AFTER) is None

    assert seen == [TEACHER], "`degraded` 必須現場讀「該老師」（不得緩存 / 不得換入參）"
    rows = _rows()
    assert [row["event_type"] for row in rows] == [
        "draft_generated", "draft_generated", "draft_modified"]
    details = [json.loads(row["payload_json"])["detail"] for row in rows]
    assert details[0] == {"template_version": 2, "content_hash": "content-hash", "degraded": False}
    assert details[1] == {"template_version": 2, "content_hash": "content-hash", "degraded": True}
    assert details[2]["wording_changed"] is True
    assert [item["field"] for item in details[2]["field_diff"]] == ["主訴（學生原話）"]
    assert learning_service.verify_learning_chain(TEACHER) == {
        "ok": True, "checked": 3, "first_bad_seq": None, "reason": "ok"}


def test_adapter_modified_skips_empty_field_diff_without_writing(db, monkeypatch, sql_log):
    """§一-1 冪等分支：`field_diff == []`（逐字相同 / 兩側都空 / 都不傳）→ **不寫事件**、零 SQL、`None`。"""
    import agent_stage_service

    monkeypatch.setenv("LEARNING_ENABLED", "on")
    mark = len(_statements(sql_log))

    assert agent_stage_service.on_draft_modified(
        TEACHER, DRAFT_ID, PATIENT_NAME, DIFF_BEFORE, DIFF_BEFORE) is None     # 逐字相同
    assert agent_stage_service.on_draft_modified(TEACHER, DRAFT_ID, PATIENT_NAME) is None
    assert agent_stage_service.on_draft_modified(
        TEACHER, DRAFT_ID, PATIENT_NAME, "", "") is None                       # 兩側都空

    assert _statements(sql_log)[mark:] == [], "空節不該產生任何 SQL（連 seq 都不分配）"
    assert _rows() == []

    # 對照組：同一對樣本正文真的改了 → 寫 1 節（證明上面三條是「跳過」而非「寫不進去」）
    assert agent_stage_service.on_draft_modified(
        TEACHER, DRAFT_ID, PATIENT_NAME, DIFF_BEFORE, DIFF_AFTER) is None
    rows = _rows()
    assert [row["event_type"] for row in rows] == ["draft_modified"]
    assert rows[0]["seq"] == 1


def test_adapter_swallows_failures_with_traditional_warning_and_no_partial_write(db, monkeypatch, capsys):
    """§9-聲明一（best-effort）：三個失敗點**各自**被適配器這一層兜住 → 一行**繁體** `[warn]`、不冒泡、零行。

    為什麼挑「適配器這一層」的失敗點：`learning_service._record_event()` 自己就會吞掉寫入期異常（並留一行
    `record_*` 名下的 warn），**只**把庫層寫入換掉根本走不進適配器的 `except`。所以這裡逐個換掉
    `record_draft_generated` / `record_draft_modified` / `compute_content_diff` —— 正是適配器 docstring
    說的「import / 調用形狀這一層的意外」；而「差異計算」也在同一層兜底之列（不在 `record_*` 裡面）。
    """
    import agent_stage_service

    monkeypatch.setenv("LEARNING_ENABLED", "on")

    def boom(*args, **kwargs):
        raise RuntimeError("壞了")

    original_generated = learning_service.record_draft_generated
    monkeypatch.setattr(learning_service, "record_draft_generated", boom)
    assert agent_stage_service.on_draft_generated(TEACHER, DRAFT_ID, PATIENT_NAME, 7) is None
    monkeypatch.setattr(learning_service, "record_draft_generated", original_generated)

    original_modified = learning_service.record_draft_modified
    monkeypatch.setattr(learning_service, "record_draft_modified", boom)
    assert agent_stage_service.on_draft_modified(
        TEACHER, DRAFT_ID, PATIENT_NAME, DIFF_BEFORE, DIFF_AFTER) is None
    monkeypatch.setattr(learning_service, "record_draft_modified", original_modified)

    monkeypatch.setattr(learning_service, "compute_content_diff", boom)    # 差異計算期炸
    assert agent_stage_service.on_draft_modified(
        TEACHER, DRAFT_ID, PATIENT_NAME, DIFF_BEFORE, DIFF_AFTER) is None

    out = capsys.readouterr().out
    assert out.count("[warn]") == 3, out                                  # 每次失敗恰一行，不靜默也不囉嗦
    assert "學習事件轉發失敗" in out and "業務結果不受影響" in out            # 適配器自己的文案（非 `record_*` 的）
    assert "on_draft_generated" in out and "on_draft_modified" in out       # 可定位：帶函數名
    assert _rows() == [], "吞掉異常 ≠ 留半節"


def test_adapter_does_not_normalize_bodies_itself(db, monkeypatch):
    """方案 c（歸一化在**調用方**）：同一對正文，**傳原文 → 假陽性寫入**；傳歸一化產物 → 跳過、不寫。

    適配器**不**代勞 `_normalize_metric_text()`，所以接線點（3.3-c / 3.3-d）漏了歸一化就會在鏈上留下
    假陽性節 —— 本條把這個後果**主動**寫出來（而不是靠 docstring 口頭約定）。用戶側字面量與 ⑥ 組的
    `test_content_diff_normalization_is_caller_side` **逐字相同**（同一對樣本正文）。
    """
    import agent_stage_service

    monkeypatch.setenv("LEARNING_ENABLED", "on")
    raw = "【主訴】 頭痛   三日"                  # 段內連續空白（未折疊）＝ 未歸一化
    normalized = "【主訴】 頭痛 三日"              # 已歸一化（= `_normalize_metric_text()` 的產物）
    assert agent_stage_service._normalize_metric_text(raw) == normalized

    assert agent_stage_service.on_draft_modified(
        TEACHER, DRAFT_ID, PATIENT_NAME, raw, normalized) is None
    rows = _rows()
    assert [row["event_type"] for row in rows] == ["draft_modified"], \
        "適配器只轉發 → 傳原文必然假陽性（= 調用方漏歸一化的後果）"
    assert json.loads(rows[0]["payload_json"])["detail"] == {
        "field_diff": [{"field": "主訴", "before_hash": _text_hash("頭痛   三日"),
                        "after_hash": _text_hash("頭痛 三日")}],
        "wording_changed": True}

    # 正確姿勢（3.3-c / 3.3-d）：調用方先歸一化 → 逐字相同 → 不寫第二節
    assert agent_stage_service.on_draft_modified(
        TEACHER, DRAFT_ID, PATIENT_NAME,
        agent_stage_service._normalize_metric_text(raw),
        agent_stage_service._normalize_metric_text(normalized)) is None
    assert len(_rows()) == 1


def test_adapter_writes_only_learning_events_and_no_stage_table(db, monkeypatch, sql_log):
    """§9-聲明二（零階段面）：適配器只寫 `agent_learning_events` —— 階段三表 / 業務兩表**一行沒動**。

    階段面開著（`AGENT_STAGE_ENABLED=on`）時更硬：`degraded` 的現場讀會**只讀**地查狀態行 / 配置鏈
    （READ 允許），但**寫語句**清單裡一個階段表都不許出現。表集合沿用 ⑧ 組的 `audited` 五張。
    """
    import agent_stage_service

    monkeypatch.setenv("LEARNING_ENABLED", "on")
    monkeypatch.setenv("AGENT_STAGE_ENABLED", "on")
    audited = ("agent_stage_state", "agent_stage_config", "agent_stage_log",
               "drafts", "patient_records")
    before = {table: _raw_scalar("SELECT COUNT(*) FROM %s" % table) for table in audited}
    before_events = _raw_scalar("SELECT COUNT(*) FROM agent_learning_events")
    mark = len(_statements(sql_log))

    assert agent_stage_service.on_draft_generated(
        TEACHER, DRAFT_ID, PATIENT_NAME, 7, 2, "content-hash", LINEAGE_ID) is None
    assert agent_stage_service.on_draft_modified(
        TEACHER, DRAFT_ID, PATIENT_NAME, DIFF_BEFORE, DIFF_AFTER) is None

    writes = [sql for sql in _statements(sql_log)[mark:]
              if re.search(r"\b(INSERT|UPDATE|DELETE)\b", sql, re.I)]
    assert writes, "學習鏈本身要寫（否則本條失去對照組）"
    assert all("agent_learning_events" in sql for sql in writes), \
        "適配器只許寫學習表（實測另有：%r）" % [sql for sql in writes
                                              if "agent_learning_events" not in sql]
    after = {table: _raw_scalar("SELECT COUNT(*) FROM %s" % table) for table in audited}
    assert after == before, "適配器動了階段面 / 業務表"
    assert _raw_scalar("SELECT COUNT(*) FROM agent_learning_events") == before_events + 2


def test_database_forwarder_reaches_the_adapters_and_the_two_landings_call_it_once(db, monkeypatch):
    """庫層唯一轉發點 ↔ 適配器 ↔ 兩個落線點（**【3.3-c 落線後改寫】本檔唯一既有斷言變更**）。

    3.3-b 的「兩個接線點仍是零調用」守護到此結束 —— 現在守的是「落了線，而且落得對」：
      · 前兩句（沿用 3.3-b）：`_call_agent_stage_hook()` 按**名字**取到適配器就轉發、回 `True`、
        落下真實一節（前四參按**位置**傳，`args` 的形狀就是兩個落線點的形狀）→ 名字 / 簽名對不上
        時這裡紅；
      · 第三句（改寫）：兩個落線點體內**恰好一處**真實調用（`source.count('_call_agent_stage_hook("')`，
        與 `test_agent_stage.py` ⑫ 組同一套「只數真實調用」口徑 —— 註釋 / docstring 寫的是
        `_call_agent_stage_hook()`，括號後不帶引號，故不計入），且**不得**直呼
        `agent_stage_service.on_draft_*`（繞過唯一入口 = 第二個轉發點，設計 §10.1-1 紅線）；
      · 第四句（新增）：庫層不自己判學習總閘 —— `LEARNING_ENABLED` 一字不出現在這兩個函數體裡
        （flag 只在閘門函數裡判一次；payload 也歸適配器 / `learning_service`）。
    """
    import inspect

    monkeypatch.setenv("LEARNING_ENABLED", "on")
    assert database._call_agent_stage_hook(
        "on_draft_generated", TEACHER, DRAFT_ID, PATIENT_NAME, 7) is True
    rows = _rows()
    assert [row["event_type"] for row in rows] == ["draft_generated"]
    assert (rows[0]["draft_id"], rows[0]["template_id"]) == (DRAFT_ID, 7)

    landed = {"insert_draft": "on_draft_generated", "update_draft_content": "on_draft_modified"}
    for name, hook_name in landed.items():
        source = inspect.getsource(getattr(database, name))
        assert source.count('_call_agent_stage_hook("') == 1, \
            "%s 必須恰好一處真實轉發（唯一入口，按名字）" % name
        assert source.count('_call_agent_stage_hook("%s"' % hook_name) == 1, \
            "%s 的鉤子名必須是 %s（位置 / 名字錯 = 靜默丟事件）" % (name, hook_name)
        assert "agent_stage_service.on_draft_" not in source, \
            "%s 直呼服務層鉤子 → 繞過唯一轉發點（§10.1-1 紅線）" % name
        assert "LEARNING_ENABLED" not in source, \
            "%s 不許自己判學習總閘（flag 只在閘門裡判一次）" % name


# ============================================================================
# ⑧ step 3.3-c：庫層兩個落線點（`database.insert_draft` / `database.update_draft_content`）
# ----------------------------------------------------------------------------
# 對齊：CTO 2026-09-30 step 3.3-c 指令 + 設計 §3.1（事件流）/ §4.2 改 1、改 4 / §9-聲明一 / §10.1。
# 本步把「服務層適配器」（3.3-b）接到**兩個真實業務路徑**上，因此守護是**端到端**視角：
#   · `insert_draft()` → `draft_generated` 一節：定位鍵取自返回值（`draft_id`）與落庫的模板引用；
#     第 6 位（適配器的 `content_hash` 槽）= **已歸一化**的正文（截斷 2000）—— 歸一化在調用方做
#     （CTO 3.3-a 追加 1 方案 c）；庫層原樣落庫，不改老師看到的正文；
#   · `update_draft_content()` → UPDATE **之前**一條只讀 SELECT 取 `before` → `draft_modified` 一節
#     （兩側正文各歸一化一次）；逐字相同的編輯由適配器自己的冪等分支跳過（§一-1），庫層不替它判；
#   · 兩處都 **best-effort**（§9-聲明一）：鉤子炸了 / 草案不存在 → 業務結果與返回值一字不改、
#     零事件、不拋，只留 `[warn]`；
#   · flag off = 與今天 1:1：零 `agent_learning_events` 語句、零行（A4）。
# 源碼級守護：本檔 `test_no_wiring_in_step_3_2` 的函數體級斷言（零 `learning_service` /
# `agent_learning_events` / `LEARNING_ENABLED`）+ ⑦ 組改寫後那條（恰好一處、名字正確）—— 兩處交叉。
# ============================================================================

RAW_BODY = "【主訴】  頭痛   三日\r\n【舌象】  舌淡紅"
NORMALIZED_BODY = "【主訴】 頭痛 三日 【舌象】 舌淡紅"      # 上面那份原文的歸一化產物（換行 → 空格、連續空白折疊）


def _draft_content(draft_id):
    """草案當前的 `content`（直連庫文件讀，不污染 `sql_log` 的語句級斷言）。"""
    return _raw_scalar("SELECT content FROM drafts WHERE id = ?", (draft_id,))


def test_insert_draft_emits_draft_generated_event(db, monkeypatch):
    """改 1 端到端：`insert_draft()` 落庫後追加 `draft_generated` 一節，帶著**歸一化後的正文**。

    四件事一起釘：① 草案落庫的仍是**原文**（庫層不替老師改正文）；② 事件定位鍵 = 返回值
    （`draft_id`）與落庫的模板引用；③ 第 6 位拿到的是 `_normalize_metric_text()` 的產物
    （換行折成空格 + 段內連續空白折疊）；④ A5：明文姓名不入鏈（只留 `patient_name_hash`）。
    """
    monkeypatch.setenv("LEARNING_ENABLED", "on")

    draft_id = db.insert_draft(0, PATIENT_NAME, TEACHER, RAW_BODY, template_id=7, template_version=2)

    assert isinstance(draft_id, int), "返回值語義不變（仍是 draft_id）"
    assert _draft_content(draft_id) == RAW_BODY, "落庫的正文是原文，歸一化只發生在事件那一側"
    rows = _rows()
    assert [row["event_type"] for row in rows] == ["draft_generated"]
    assert (rows[0]["draft_id"], rows[0]["template_id"]) == (draft_id, 7)
    assert (rows[0]["seq"], rows[0]["lineage_id"]) == (1, ""), "單鏈從 1 起；定位鍵不臆造"
    assert rows[0]["patient_name_hash"] == FROZEN_PATIENT_NAME_HASH
    assert PATIENT_NAME not in rows[0]["payload_json"], "A5：明文姓名不入鏈"
    assert json.loads(rows[0]["payload_json"])["detail"] == {
        "template_version": 2, "content_hash": NORMALIZED_BODY, "degraded": False}


def test_insert_draft_event_body_is_normalized_and_truncated_at_2000(db, monkeypatch):
    """歸一化口徑落到事件上：換行折成空格 + 截斷 **2000**（與 ② 指標同一個函數、同一個上限）。

    正文 = `"A" * 2500 + 換行 + "B" * 10` → 歸一化後 2511 字 → 截斷 2000 ⇒ `"A" * 2000`
    （期望值**獨立**算出，不由實現代勞）。
    """
    monkeypatch.setenv("LEARNING_ENABLED", "on")

    db.insert_draft(0, PATIENT_NAME, TEACHER, "A" * 2500 + "\r\n" + "B" * 10)

    detail = json.loads(_rows()[0]["payload_json"])["detail"]
    assert detail == {"template_version": 0, "content_hash": "A" * 2000, "degraded": False}


def test_insert_draft_flag_off_is_zero_learning_sql(db, sql_log):
    """flag off = 與今天 1:1（§6 / A4）：`insert_draft()` 的語句序列裡**一句**學習表都不出現。

    零 SQL 來自閘門（`LEARNING_ENABLED` 默認 off，本檔不動 conftest）—— 庫層自己不判 flag，
    所以這一格同時是「庫層沒有第二個 flag 判斷」的行為面證據。
    """
    draft_id = db.insert_draft(0, PATIENT_NAME, TEACHER, "AI 原稿")

    assert isinstance(draft_id, int) and _draft_content(draft_id) == "AI 原稿"
    assert [sql for sql in _statements(sql_log) if "agent_learning_events" in sql] == []
    assert _rows() == []


def test_two_landings_are_best_effort_when_hooks_raise(db, monkeypatch, capsys):
    """§9-聲明一：鉤子炸了**絕不**回退業務 —— 業務結果 / 返回值一字不改，只留 `[warn]`、零半節。

    兩個落線點各炸一次；第二個刻意走**真的 `before`**（草案存在）—— 證明事件段是真的被兜住，
    不是「因為沒進到那一段才沒炸」。
    """
    import agent_stage_service

    monkeypatch.setenv("LEARNING_ENABLED", "on")

    def _boom(*args, **kwargs):
        raise RuntimeError("適配器炸了（用例注入）")

    monkeypatch.setattr(agent_stage_service, "on_draft_generated", _boom)
    monkeypatch.setattr(agent_stage_service, "on_draft_modified", _boom)

    draft_id = db.insert_draft(0, PATIENT_NAME, TEACHER, "AI 原稿")
    assert _draft_content(draft_id) == "AI 原稿", "草案照樣落庫"
    assert db.update_draft_content(draft_id, "老師改後的正文") is None
    assert _draft_content(draft_id) == "老師改後的正文", "修改照樣落庫"

    out = capsys.readouterr().out
    assert out.count("[warn]") == 2, out                     # 每個落線點恰好一行，不靜默也不囉嗦
    assert "on_draft_generated" in out and "on_draft_modified" in out   # 可定位
    assert _rows() == [], "吞掉異常 ≠ 留半節"


def test_update_draft_content_emits_draft_modified_event(db, monkeypatch):
    """改 4 端到端：UPDATE 前只讀讀 `before` → 追加 `draft_modified` 一節（兩側都**已歸一化**）。

    期望 `detail` 逐條寫死：`field` = 段標題（`主訴`）、兩個哈希 = 段文本的 `sha256`；
    `before` 段文本 = `"頭痛 三日"`（段內連續空白已折疊）、`after` 段文本 = `"頭痛三日"`。
    """
    draft_id = db.insert_draft(0, PATIENT_NAME, TEACHER, "【主訴】 頭痛   三日",
                               template_id=7, template_version=2)      # flag off：這一步不發事件
    monkeypatch.setenv("LEARNING_ENABLED", "on")

    assert db.update_draft_content(draft_id, "【主訴】 頭痛三日") is None

    rows = _rows()
    assert [row["event_type"] for row in rows] == ["draft_modified"]
    assert (rows[0]["draft_id"], rows[0]["template_id"]) == (draft_id, 7), "定位鍵取自草案行"
    assert rows[0]["patient_name_hash"] == FROZEN_PATIENT_NAME_HASH
    assert json.loads(rows[0]["payload_json"])["detail"] == {
        "field_diff": [{"field": "主訴", "before_hash": _text_hash("頭痛 三日"),
                        "after_hash": _text_hash("頭痛三日")}],
        "wording_changed": True}
    assert _draft_content(draft_id) == "【主訴】 頭痛三日", "既有 UPDATE 語義與落庫值不變"


def test_update_draft_content_skips_event_when_normalized_body_is_unchanged(db, monkeypatch):
    """§一-1 冪等：歸一化後逐字相同 → **不寫事件**（反覆保存同一份正文不在鏈上長空節）。

    兩次編輯只差「段內連續空白」—— 歸一化後一模一樣；`drafts.content` 仍照原文更新（業務不變）。
    """
    draft_id = db.insert_draft(0, PATIENT_NAME, TEACHER, "【主訴】 頭痛 三日")
    monkeypatch.setenv("LEARNING_ENABLED", "on")

    assert db.update_draft_content(draft_id, "【主訴】 頭痛   三日") is None

    assert _rows() == []
    assert _draft_content(draft_id) == "【主訴】 頭痛   三日", "業務寫入照做，只是不發事件"


def test_update_draft_content_missing_draft_is_quiet_and_keeps_update_statement(db, monkeypatch, sql_log):
    """草案不存在（今天那 0 行 UPDATE）：不拋、不發事件，且**既有 UPDATE 語句逐字不變**。

    這一格同時守住兩件事：「讀不到 `before` 就不發事件」與「UPDATE 語句 / 參數順序沒被本步改動」
    （§5.1 紅線③ —— 本步在 UPDATE **之前**新增的那條只讀 SELECT 不改變既有語句）。
    """
    monkeypatch.setenv("LEARNING_ENABLED", "on")

    assert db.update_draft_content(987654, "無主正文") is None

    assert _rows() == []
    assert ("UPDATE drafts SET content = ? WHERE id = ?", ("無主正文", 987654)) in sql_log[0].calls, \
        "既有 UPDATE 語句文本 / 參數順序一字不改"


# ============================================================================
# ⑨ step 3.3-d：接口層三個狀態端點（`template_api.publish` / `archive` / `activate`）
# ----------------------------------------------------------------------------
# 【分組編號 / 子步標籤說明】`⑨` 沿本文件 `⑦`（3.3-b 服務層適配器，段頭 `:1298`）/ `⑧`（3.3-c 庫層落點，段頭
# `:1541`）的排版慣例 —— 這三號在模組 docstring（`:19`–`:21`）另指 CTO 要求 ⑦/⑧/⑨，「**雙用**」是既有現象；
# 設計文件 §10 只細分到 3.1–3.5（**沒有** 3.3-a…3.3-f 小節），`3.3-d` 是施工細分標籤（倉庫內前向引用在
# `agent_stage_service.py:3917/3925`）。
# 對齊（照本文件 ⑦ 組的寫法：CTO 子步指令 + 設計條文；指令原文不在倉庫內 → 把**可查**依據逐條列出）：
#   · §3.1 第 1 行（逐字）：`template_configured` = 「老师**发布 / 归档 / 启用**某类模板（`template_api.py`
#     的 publish `:244` / archive `:266` / activate `:281`）」（落地步 = 3.3）—— 三個端點名的**唯一**出處；
#   · §3.2 第 1 行（逐字）：`detail` = `{"template_id": int, "template_type": str, "version": int,
#     "from_status": str, "to_status": str}`（复用 Epic 1 §3.5 的模板事件形状）；
#   · §一-1 裁決（冪等分支不寫空節；同 `learning_service.py:622` / `agent_stage_service.py:3970` 的既有寫法）；
#   · §6（flag off = 與今天 1:1：零行、響應一字不改）+ §2.5-5（flag off 不寫事件、不分配 `seq`）。
# 本組**走真 HTTP**（`client` = conftest 的 `TestClient`，`TEMPLATE_API_ENABLED=on` 由 conftest 統一打開）——
# 守四件事：
#   · 三個端點各發**恰好一節**，`from_status` 取**切換前**的讀數（`draft → active` / `active → archived` /
#     `archived → active`）、`to_status` 取切換後（拿 `updated` 當 `from_status` 就會寫出「active → active」
#     這種自相矛盾的節 —— 這一格把該反例釘死）；
#   · 冪等分支（`changed=false`：本來就 `active` / 本來就 `archived`）→ **零新節**（§一-1）；
#   · flag off → 三個端點照常切狀態、響應體**鍵集 / 鍵序**與 flag on 逐字節相同、鏈上零行；
#   · `lineage_id` **取自模板行**（不臆造：行上是 `''` 就寫 `''`，是師門 id 就寫師門 id）。
# ============================================================================
def _auth(**extra):
    """接口層雙欄位鑑權（§10.1：`teacher_name` + `teacher_id` 必須同一個人）。"""
    body = {"teacher_name": TEACHER, "teacher_id": TEACHER}
    body.update(extra)
    return body


def _publishable(template_type):
    """§9.0 發佈級完整性：問診至少 1 項必問 / 施治內容非空（其餘兩類默認骨架即滿足）。"""
    schema = database.default_template_schema(template_type)
    if template_type == "inquiry":
        schema["fields"][0]["required"] = True
    elif template_type == "treatment":
        schema["content"] = "疏肝理氣，健脾和胃；忌生冷。"
    return schema


def _draft(client, template_type="record"):
    """建一份**可發佈**的草稿 → 返回模板 id（走真接口，與前端同一條路徑）。"""
    created = client.post("/api/templates",
                          json=_auth(type=template_type, schema_json=_publishable(template_type)))
    assert created.status_code == 201, created.text
    return created.json()["template"]["id"]


def _detail_list():
    """該老師鏈上全部事件的 `detail`（`_rows()` 已按 `seq` 升序）。"""
    return [json.loads(row["payload_json"])["detail"] for row in _rows()]


def test_publish_endpoint_records_one_event_from_pre_switch_status(client, monkeypatch):
    """`POST /publish` → 恰好一節：`draft → active`；`from_status` 是**切換前**的讀數（不是 `active → active`）。

    `detail` 五鍵逐字寫死（§3.2）：`template_id` / `template_type` / `version` 取自模板行，
    `version` 不隨狀態切換變（`set_template_active()` 只改 `status` / `updated_at`）。
    """
    monkeypatch.setenv("LEARNING_ENABLED", "on")
    template_id = _draft(client)

    response = client.post("/api/templates/%d/publish" % template_id, json=_auth())

    assert response.status_code == 200, response.text
    assert response.json()["changed"] is True
    rows = _rows()
    assert [row["event_type"] for row in rows] == ["template_configured"]
    assert (rows[0]["seq"], rows[0]["template_id"], rows[0]["draft_id"]) == (1, template_id, 0), \
        "單鏈從 1 起；配置事件不指向草案（draft_id 恆 0）"
    assert rows[0]["teacher_name"] == TEACHER
    assert rows[0]["lineage_id"] == "", "行上沒有師門（未歸屬哨兵 `''`）→ 不臆造"
    assert _detail_list() == [{"template_id": template_id, "template_type": "record", "version": 1,
                               "from_status": "draft", "to_status": "active"}]


def test_archive_endpoint_records_one_event_and_keeps_response_shape(client, monkeypatch):
    """`POST /archive` → 恰好一節：`active → archived`；響應體仍是既有那兩鍵（鍵序不變）。"""
    monkeypatch.setenv("LEARNING_ENABLED", "on")
    template_id = _draft(client)
    assert client.post("/api/templates/%d/publish" % template_id, json=_auth()).status_code == 200

    response = client.post("/api/templates/%d/archive" % template_id, json=_auth())

    assert response.status_code == 200, response.text
    assert list(response.json().keys()) == ["template", "changed"], "既有響應鍵集 / 鍵序一字不改"
    assert response.json()["changed"] is True
    assert _detail_list() == [
        {"template_id": template_id, "template_type": "record", "version": 1,
         "from_status": "draft", "to_status": "active"},
        {"template_id": template_id, "template_type": "record", "version": 1,
         "from_status": "active", "to_status": "archived"},
    ]


def test_activate_endpoint_records_one_event_from_archived_to_active(client, monkeypatch):
    """`POST /activate` → 恰好一節：`archived → active`（鏈上第三節）；三鍵響應體鍵序不變。"""
    monkeypatch.setenv("LEARNING_ENABLED", "on")
    template_id = _draft(client)
    for path in ("publish", "archive"):
        assert client.post("/api/templates/%d/%s" % (template_id, path), json=_auth()).status_code == 200

    response = client.post("/api/templates/%d/activate" % template_id, json=_auth())

    assert response.status_code == 200, response.text
    assert list(response.json().keys()) == ["template", "archived_ids", "changed"]
    assert response.json()["changed"] is True
    details = _detail_list()
    assert [d["from_status"] + " → " + d["to_status"] for d in details] == [
        "draft → active", "active → archived", "archived → active"]
    assert details[2] == {"template_id": template_id, "template_type": "record", "version": 1,
                          "from_status": "archived", "to_status": "active"}


def test_idempotent_state_branches_emit_no_event(client, monkeypatch):
    """§一-1：三個端點的**冪等分支**（`changed=false`）各發零新節 —— 重複點同一顆按鈕不在鏈上長空節。

    每一段都是「先真切換一次（+1 節）→ 再對**同一個端點**做一次（`changed=false`）」：
    只有同一端點連做兩次才落在冪等分支上（跨端點的第二輪不是冪等：`archive` 接在 `activate` 之後
    是真的 `active → archived`）。
    """
    monkeypatch.setenv("LEARNING_ENABLED", "on")
    template_id = _draft(client)
    url = "/api/templates/%d/%%s" % template_id

    for path, expected_events in (("publish", 1), ("archive", 2), ("activate", 3)):
        first = client.post(url % path, json=_auth())
        assert (first.status_code, first.json()["changed"]) == (200, True), path
        assert len(_rows()) == expected_events, "%s 真切換應 +1 節" % path

        again = client.post(url % path, json=_auth())
        assert (again.status_code, again.json()["changed"]) == (200, False), \
            "%s 的冪等分支：仍是 200（業務語義不變）+ changed=false" % path
        assert len(_rows()) == expected_events, "%s 的冪等分支：零新節" % path

    assert [d["from_status"] + " → " + d["to_status"] for d in _detail_list()] == [
        "draft → active", "active → archived", "archived → active"], "三節＝三次真切換，沒有空節"


def test_event_lineage_id_comes_from_the_template_row(client, monkeypatch):
    """`lineage_id` **取自模板行**（不臆造）：行上是師門 id 就寫師門 id（`''` 那格見 publish 用例）。

    造法：建草稿後用**裸 SQL** 把行上的 `lineage_id` 填成正規師門 id —— 狀態端點（publish / archive /
    activate）**不**校驗師門（`_check_lineage()` 只掛在 create / update / derive），所以這一格測的正是
    「事件投影從行上取，而不是自己拼一個空串」。
    """
    monkeypatch.setenv("LEARNING_ENABLED", "on")
    template_id = _draft(client)
    _raw_execute("UPDATE templates SET lineage_id = ? WHERE id = ?", (LINEAGE_ID, template_id))

    assert client.post("/api/templates/%d/publish" % template_id, json=_auth()).status_code == 200

    assert _rows()[0]["lineage_id"] == LINEAGE_ID


def test_flag_off_keeps_response_shape_identical_and_writes_zero_rows(client, monkeypatch):
    """§6 flag off = 與今天 1:1：三個端點照常切狀態、響應體**鍵集 / 鍵序**與 flag on 逐字節相同、鏈上零行。

    兩趟對照：flag off 一趟（`record`）+ flag on 一趟（`treatment`，避免與上一趟的 scope 打架）——
    比的是**響應形狀**（鍵序 = 客戶端可見契約）與「zero 行」。
    """
    monkeypatch.delenv("LEARNING_ENABLED", raising=False)
    off_id = _draft(client)
    off = [client.post("/api/templates/%d/%s" % (off_id, path), json=_auth())
           for path in ("publish", "archive", "activate")]

    assert [r.status_code for r in off] == [200, 200, 200]
    assert [list(r.json().keys()) for r in off] == [
        ["template", "archived_ids", "changed", "event", "warnings"],
        ["template", "changed"],
        ["template", "archived_ids", "changed"],
    ]
    assert [r.json()["changed"] for r in off] == [True, True, True]
    assert off[0].json()["event"] == "template_configured", "Epic 1 §3.5 的預留鍵一字不改"
    assert [r.json()["template"]["status"] for r in off] == ["active", "archived", "active"]
    assert _rows() == [], "flag off：零行、零 seq（`learning_enabled()` 在寫入前就擋掉）"

    monkeypatch.setenv("LEARNING_ENABLED", "on")
    on_id = _draft(client, "treatment")
    on = [client.post("/api/templates/%d/%s" % (on_id, path), json=_auth())
          for path in ("publish", "archive", "activate")]

    assert [list(r.json().keys()) for r in on] == [list(r.json().keys()) for r in off], \
        "flag on / off 的響應鍵集與鍵序逐字節相同（flag 不參與響應組裝）"
    assert [r.json()["changed"] for r in on] == [r.json()["changed"] for r in off]
    assert [r.json()["template"]["status"] for r in on] == [r.json()["template"]["status"] for r in off]
    assert [d["from_status"] + " → " + d["to_status"] for d in _detail_list()] == [
        "draft → active", "active → archived", "archived → active"], "僅 flag on 那趟落鏈"


# ============================================================================
# ⑩ step 3.3-e：`agent_stage_service._evaluate()` 的兩類學習事件（評估鏈 → 學習鏈的收口）
# ----------------------------------------------------------------------------
# 【分組編號說明】`⑩` 沿本檔 ⑦/⑧/⑨ 的排版慣例；模組 docstring `:22` 的 `⑩` 另指 step 3.2 清單的
# 「源碼級守護」—— 「雙用」是既有現象（同一聲明見 ⑨ 組段頭 `:1707`–`:1710`）。
# 對齊：CTO 2026-09-30 step 3.3-e 指令 + 設計 §3.1（一次評估 = 兩節的事件流）/ §3.2（兩類 detail 的
#   三鍵 / 四鍵形狀）/ §一-4（3.3 只在 `_evaluate()` 寫 `agent_updated`）/ §一-1（不寫空節）/
#   §6（flag off = 與今天 1:1、零新 SQL）/ §9-聲明一（best-effort，失敗不回退業務）/
#   §9-聲明二（零階段面：只寫學習表）。
# 站位：本檔 ⑦→⑧→⑨ 逐層釘「服務層適配器 / 庫層落點 / 接口層端點」，本組釘**最後一個落點** ——
#   `evaluate()` → `_evaluate()` 內那段【施工步驟 3.3-e】（wiring 段頭在服務層 `:2118` 起；
#   工具鏈側的段頭在同檔 `:4033`「施工步驟 3.3-e」）。
# 六件事（編號 ↔ CTO 清單，逐件一用例）：
#   ① flag off → 評估照跑（階段面照寫）、學習鏈**零行**、階段面**逐字節不變**（狀態口徑；按 CTO 修正重寫）；
#   ② flag on → 一次評估**恰好 +2 節**（順序：`learning_event_emitted` → `agent_updated`），且第一節
#      三鍵 = 「本週期真讀到什麼」（空池不虛報 / 有樣本才報 / 逐字相同就不報段級差異）；
#   ③ 先手工種一條 `seq = 1` 的既有節 → 新兩節接著 `seq = 2` / `3`（`prev_hash` 接得上 → 鏈校驗 ok）；
#   ④ `agent_updated` 的 `from_stage == to_stage == describe_stage()["stage"]`（約束 3：評估不改階段）；
#   ⑤ `metrics_hash` 可**獨立重算**（= `sha256(canonical(快照))`；快照本體只留狀態行、**不**複製進鏈）；
#   ⑥ 返回體仍是 **18 鍵 + `changed`**（既有斷言在 `test_agent_stage.py` 的 `_EVALUATE_SNAPSHOT_KEYS`，
#      本組只**確認未破**：逐鍵字面量 + flag off / on 兩趟的**業務值**逐鍵相同（身份 / 時刻欄位不比））。
# 造數口徑（為什麼本組不造真實樣本池）：本組測的是「**已算好的兩份指標**如何落鏈」，樣本池的樣貌屬
#   ⑦ / ⑯ / ⑰ 組。需要「有樣本」的那兩趟改為注入 ①② 兩個純函數的**讀數**（骨架取自服務層自己的
#   `_blank_*()` → 形狀不與實現漂移）：被測面（那段 3.3-e 接線）零改動、零新 SQL、零新窗口定義。
# ============================================================================

# `evaluate()` 返回體的逐鍵契約：18 鍵快照 + `changed`（與 `test_agent_stage.py` 的
# `_EVALUATE_SNAPSHOT_KEYS`（當時 `:3605`）**逐字同表**；本檔不 import 測試模組 → 重述一份，
# 「兩處同時紅」才叫真的漂移）
EVALUATE_SNAPSHOT_KEYS = (
    "teacher_name", "skipped", "reason",
    "stage", "stage_label", "stage_since", "stage_source", "pending_stage", "pending_task_id",
    "degraded", "metrics", "metrics_reason", "thresholds", "config_source", "next_stage",
    "blockers", "evaluated_at", "metrics_ttl_hours",
)
CHANGED_KEYS = ("stage_changed", "recommended", "demoted", "reason")

# 返回體的**業務值**鍵集 = 18 鍵去掉「身份」（`teacher_name`）與「時刻」（`stage_since` / `evaluated_at`）。
# ⑥ 的兩趟比對只吃這一組：同一格連跑兩趟時，`stage_since`（首趟寫下的時刻）與 `evaluated_at` 必然不同。
STABLE_BODY_KEYS = tuple(
    key for key in EVALUATE_SNAPSHOT_KEYS
    if key not in ("teacher_name", "stage_since", "evaluated_at"))

# 學習鏈的**唯一**表名。判據：學習鏈每一條語句的 SQL 文本都自帶這個表名（`database.py` 的
# `next_seq` / `get_last_learning_event` / `insert_learning_event` 三處都以 `+ LEARNING_EVENTS_TABLE`
# 拼接）→ 這**一個**判據就足以把學習鏈的 SQL 整批挑出來。
LEARNING_TABLE_NAME = "agent_learning_events"

# 本組第三位老師：同一格要換三種指標讀數 → 三條互不干擾的鏈（各自 seq 從 1 起）
THIRD_TEACHER = "学习链测试老师丁"


@pytest.fixture
def stage_gate(monkeypatch):
    """⑩ 組公共前置（照 `test_agent_stage.py` 的同名前置）：打開階段總閘（`evaluate()` 的第一道門）
    + Epic 1 病歷模板通道（① 的基準來源）。

    **刻意不開學習總閘**：那正是本組要逐條切的開關（要 flag off 的用例各自 `delenv`）。
    """
    monkeypatch.setenv("AGENT_STAGE_ENABLED", "on")
    monkeypatch.setenv("TEMPLATE_API_ENABLED", "on")


def _learning_statements(statements):
    """從語句清單裡挑出**學習鏈**的那些（判據見 `LEARNING_TABLE_NAME` 的註釋）。"""
    return [sql for sql in statements if LEARNING_TABLE_NAME in sql]


def _details(teacher_name=TEACHER):
    """該老師鏈上全部事件的 `detail`（`_rows()` 已按 `seq` 升序）。

    ⑨ 組的 `_detail_list()` 只服務 `TEACHER`；本組三位老師各看一次 → 這裡多一個 `teacher_name`。
    """
    return [json.loads(row["payload_json"])["detail"] for row in _rows(teacher_name)]


def _patch_metric_readings(monkeypatch, match_samples, consistency_samples, consistency_min):
    """把 ①② 兩個**純函數**的讀數換成指定值（**入參注入**，不是期望值自證）。

    骨架取自服務層自己的 `_blank_template_match()`（10 鍵）/ `_blank_modification_consistency()`（6 鍵）
    → 日後加鍵 / 改鍵名，本助手不必跟著改。`_evaluate()` 只吃這兩個返回值，注入不影響被測面。
    """
    import agent_stage_service

    match = agent_stage_service._blank_template_match()
    match.update({"value": 1.0, "samples": match_samples, "hit_rate": 1.0, "order_rate": 1.0})
    consistency = agent_stage_service._blank_modification_consistency()
    consistency.update({"value": consistency_min, "samples": consistency_samples,
                        "min": consistency_min})
    monkeypatch.setattr(agent_stage_service, "compute_template_match",
                        lambda teacher_name, cfg: dict(match))
    monkeypatch.setattr(agent_stage_service, "compute_modification_consistency",
                        lambda teacher_name, cfg: dict(consistency))


# `agent_stage_log` 的**內容列**：身份（`teacher_name`）/ 自增 `id` / 時刻（`created_at`）按定義不同
# → 不比；其餘列（含兩個 JSON 串的**原樣字節**）才是「階段面沒被 flag 影響」的證據。
STAGE_LOG_CONTENT_COLUMNS = ("event_type", "from_stage", "to_stage", "capability",
                             "task_id", "metrics_json", "detail")


def _stage_log_rows(teacher_name):
    """該老師在 `agent_stage_log` 的全部行 → `[(內容列值, ...)]`（按寫入序；裸 sqlite3 讀，不碰 `sql_log`）。"""
    conn = sqlite3.connect(database.DB_PATH)
    try:
        rows = conn.execute(
            "SELECT %s FROM agent_stage_log WHERE teacher_name = ? ORDER BY id"
            % ", ".join(STAGE_LOG_CONTENT_COLUMNS), (teacher_name,)).fetchall()
    finally:
        conn.close()
    return [tuple(row) for row in rows]


# ---- ① flag off：學習鏈零痕（狀態口徑：零行 + 階段面逐字節不變）----

def test_evaluate_flag_off_adds_no_learning_rows(db, monkeypatch, capsys, stage_gate):
    """① §6：`LEARNING_ENABLED` off → 評估照跑（階段面照寫）、學習鏈**零行**，階段面**逐字節不變**。

    【按 CTO 修正重寫】原斷言比的是「兩趟的 SQL 條數差」，那條口徑的前提不成立：flag off 時學習路徑在
    **寫入前的總閘那一格**就短路掉（總閘只由 `learning_service._record_event()` 判**一次**，見服務層
    `:2121-2123`）—— 去數一條「根本沒走到」的路徑上可能多出來的語句，紅綠都不說明行為。
    可驗收的事實只有兩件，本條逐件釘：

      · 學習表**零行**（另用裸 SQL 複查一次，防 `learning_service` 這一層自己騙自己）；
      · 階段面（`agent_stage_log` 的**內容列**）在 flag off / on 兩趟裡**逐字節相同** —— 兩位**同構**
        老師（都無狀態行、無樣本池、無配置行）各跑一趟、只差學習總閘；flag on 那趟**另外**落兩節
        學習事件（否則本條會因「兩趟都沒寫」而假綠）。

    「逐字節」比的是庫裡的原樣字串（`metrics_json` / `detail` 直接比 JSON 串，不解析後再比）；只排除
    三列 —— `id`（自增）/ `teacher_name`（身份）/ `created_at`（時刻），它們按定義不同。
    """
    import agent_stage_service

    monkeypatch.delenv("LEARNING_ENABLED", raising=False)
    off = agent_stage_service.evaluate(TEACHER)
    off_log = _stage_log_rows(TEACHER)

    assert (off["skipped"], off["reason"]) == (False, "blocked"), \
        "flag off 也要真的走進評估實體（本條測的是「照常評估、但學習鏈不長痕」，不是 flag 的短路體）"
    assert _rows() == [], "flag off：學習鏈零行、零 seq"
    assert _raw_scalar("SELECT COUNT(*) FROM agent_learning_events") == 0, "裸 SQL 複查同一件事"
    assert off_log, "階段面照寫（`evaluation` 審計那一行必須在）—— 否則下面的比對是空斷言"

    monkeypatch.setenv("LEARNING_ENABLED", "on")
    on = agent_stage_service.evaluate(OTHER_TEACHER)
    on_log = _stage_log_rows(OTHER_TEACHER)

    assert on["skipped"] is False
    assert [row["event_type"] for row in _rows(OTHER_TEACHER)] == \
        ["learning_event_emitted", "agent_updated"], \
        "對照組必須真的落鏈（否則「兩趟階段面一樣」可能只是兩趟都沒寫）"
    assert on_log == off_log, \
        ("flag 只決定「要不要寫學習表」：階段面（`agent_stage_log` 內容列）逐字節不變；"
         "flag on 那趟 = %r" % (on_log,))
    assert "學習事件轉發失敗" not in capsys.readouterr().out, \
        "兩趟都不許出現學習側告警（flag off 的旁路尤其必須完全靜默）"


# ---- ② flag on：恰好 +2 節，且第一節只報「真讀到什麼」----

def test_evaluate_flag_on_appends_exactly_two_nodes_and_reports_what_it_read(db, monkeypatch,
                                                                            sql_log, stage_gate):
    """② §3.1 / §3.2：一次評估落**恰好兩節**，且第一節只報「本週期真讀到什麼」（三鍵口徑 G / H / I）。

    三趟換三種指標讀數（趟一 = 真實空樣本池；趟二 / 趟三 = 注入讀數），逐格釘 payload：
    空池不虛報、有樣本就兩類都報、`sample_count` = 兩池相加、② 最差一份逐字相同就不報段級差異。
    """
    import agent_stage_service

    monkeypatch.setenv("LEARNING_ENABLED", "on")
    mark = len(_statements(sql_log))

    assert agent_stage_service.evaluate(TEACHER)["skipped"] is False

    rows = _rows()
    assert len(rows) == 2, "一次評估恰好 +2 節（不是 1 節、也不是「每類指標各一節」）"
    assert [row["event_type"] for row in rows] == ["learning_event_emitted", "agent_updated"]
    assert [row["seq"] for row in rows] == [1, 2]
    writes = [sql for sql in _learning_statements(_statements(sql_log)[mark:])
              if sql.lstrip().upper().startswith("INSERT")]
    assert len(writes) == 2, "學習表恰好 2 條 INSERT（其餘學習語句是 `seq` / 鏈尾的只讀讀數）"
    assert _details()[0] == {"source_event_types": [], "difference_kinds": [], "sample_count": 0}, \
        "空樣本池：沒讀到就不虛報（`[]` / `[]` / 0，而不是編一個 `draft_generated`）"

    # 趟二：①② 各 3 / 2 份樣本、② 最差一份 0.5 → 兩類源事件都報 + 段級差異
    _patch_metric_readings(monkeypatch, 3, 2, 0.5)
    assert agent_stage_service.evaluate(OTHER_TEACHER)["skipped"] is False
    assert _details(OTHER_TEACHER)[0] == {
        "source_event_types": ["draft_generated", "draft_modified"],
        "difference_kinds": ["field_diff"], "sample_count": 5}, "`sample_count` = 兩池相加"

    # 趟三：同樣兩份樣本，但 ② 的 `min == 1.0`（逐字相同）→ 段級差異為空（§一-1：不塞空節）
    _patch_metric_readings(monkeypatch, 3, 2, 1.0)
    assert agent_stage_service.evaluate(THIRD_TEACHER)["skipped"] is False
    assert _details(THIRD_TEACHER)[0] == {
        "source_event_types": ["draft_generated", "draft_modified"],
        "difference_kinds": [], "sample_count": 5}


# ---- ③ 兩節 seq 連續、接在既有鏈尾 ----

def test_evaluate_two_new_nodes_continue_the_existing_chain(db, monkeypatch, stage_gate):
    """③ §2.4 / §2.5：新兩節接在**既有鏈尾**上 —— 先手工種下**恰好一條** `seq = 1` 的既有節，評估後
    新兩節必須是 `seq = 2` / `3`，且指紋逐節接得上（`verify_learning_chain()` 單遍覆核整條三節鏈）。

    【按 CTO 修正重寫】前置態由本條**現造**（`_insert(0)` → 落那一條 `seq = 1`）並斷言「鏈上恰好這一條」
    之後才評估 —— 不假設庫裡本來就有節；`seq` 用**字面量** `2` / `3` 釘死（不是 `N + 1` 這種相對式）。
    另修一處本條自身的口徑錯誤：`prev_hash` 的前驅輸入是**前一節的 `prev_hash` 列**（累積指紋），
    不是前一節的 `payload_hash`（見 `compute_link_hash()` 的「列名留痕」與 `verify_learning_chain()`）。
    """
    import agent_stage_service

    monkeypatch.setenv("LEARNING_ENABLED", "on")

    _insert(0)                                   # 凍結樣本第 0 條：`template_configured`，seq = 1
    seeds = _rows()
    assert [(row["seq"], row["event_type"]) for row in seeds] == [(1, "template_configured")], \
        "前置態恰好這一條（seq 從 1 起、隻身一節）"
    head = seeds[0]

    assert agent_stage_service.evaluate(TEACHER)["skipped"] is False

    rows = _rows()
    assert [row["seq"] for row in rows] == [1, 2, 3], \
        "既有 1 → 新兩節接著 2、3（按老師單鏈、步長 1）"
    assert [row["event_type"] for row in rows] == [
        "template_configured", "learning_event_emitted", "agent_updated"]
    first_new, second_new = rows[1], rows[2]
    assert (first_new["seq"], second_new["seq"]) == (2, 3)
    assert first_new["prev_hash"] == learning_service.compute_link_hash(
        first_new["seq"], first_new["event_type"], first_new["payload_hash"], head["prev_hash"]), \
        "接在既有鏈尾（不是每趟重起一條鏈）"
    assert second_new["prev_hash"] == learning_service.compute_link_hash(
        second_new["seq"], second_new["event_type"], second_new["payload_hash"],
        first_new["prev_hash"]), "兩節之間也接得上"
    assert learning_service.verify_learning_chain(TEACHER) == {
        "ok": True, "checked": 3, "first_bad_seq": None, "reason": "ok"}


# ---- ④ agent_updated 的階段一對：from == to == 階段真值視圖 ----

def test_evaluate_agent_updated_stage_pair_equals_the_stage_view(db, monkeypatch, stage_gate):
    """④ §一-4 / 約束 3：`_evaluate()` **不改階段** → `from_stage == to_stage`，且與階段真值同源。

    三路同源（鏈上 `detail` / 返回體 `stage` / 評估後**獨立再讀一次** `describe_stage()`）：任一路
    自己拼階段名（寫死 `"learning"`、把 `pending_stage` 當 `to_stage`、把升階前後當 from / to）這條
    立刻紅。
    """
    import agent_stage_service

    monkeypatch.setenv("LEARNING_ENABLED", "on")

    result = agent_stage_service.evaluate(TEACHER)

    detail = _details()[1]
    assert result["stage"] == agent_stage_service.describe_stage(TEACHER)["stage"] != ""
    assert result["stage"] == agent_stage_service.DEFAULT_STAGE_CONFIG["default_stage"], \
        "無狀態行的老師：兜底階段（`_ensure_state_row()` 落的零 delta 那一格）"
    assert detail["from_stage"] == result["stage"], "取值與快照的 `stage` 同源（不是自拼的常量）"
    assert detail["to_stage"] == result["stage"], "本步不改階段 → 恆 `from == to`"
    assert detail["capability"] == "", "3.3 只寫「指標 / 階段視圖落實」，不報能力名（§一-4）"
    assert detail["to_stage"] != result["pending_stage"], \
        "`to_stage` 不是「將要升入的階段」（那是 `pending_stage`，屬 3.4-c 的確認路徑）"
    assert result["changed"] == {"stage_changed": False, "recommended": False, "demoted": False,
                                 "reason": "blocked"}


# ---- ⑤ metrics_hash：可從狀態行獨立重算 ----

def test_evaluate_agent_updated_metrics_hash_is_independently_recomputable(db, monkeypatch,
                                                                         stage_gate):
    """⑤ §3.2 / §一-4：`metrics_hash` = **本次評估快照**的 canonical sha256 —— 可獨立重算。

    三件事：
      · 重算：`compute_payload_hash(json.loads(last_metrics_json))` == 鏈上那一格；
      · 再獨立一層：`sha256(canonical 串)`（不經 `compute_payload_hash()` 的實現）逐字相同；
      · 快照本體**不進鏈**（§3.2 明文）：鏈上只有那 4 個鍵，`metrics` / `thresholds` / `blockers`
        這些大對象與文本一概不上鏈；另附一條口徑差 —— 落庫字串（`json.dumps` 默認分隔符）**不是**
        canonical 串，哈希吃的是 canonical 那一份（`database._agent_stage_column_value` 那側不變）。
    """
    import agent_stage_service

    monkeypatch.setenv("LEARNING_ENABLED", "on")

    assert agent_stage_service.evaluate(TEACHER)["skipped"] is False

    raw_json = _raw_scalar(
        "SELECT last_metrics_json FROM agent_stage_state WHERE teacher_name = ?", (TEACHER,))
    snapshot = json.loads(raw_json)
    detail = _details()[1]

    assert sorted(detail) == ["capability", "from_stage", "metrics_hash", "to_stage"], \
        "`agent_updated` 的 detail 恰好 4 鍵（§3.2；快照本體不得複製進鏈）"
    assert detail["metrics_hash"] == learning_service.compute_payload_hash(snapshot)
    canonical = learning_service.canonical_json(snapshot)
    assert detail["metrics_hash"] == hashlib.sha256(canonical.encode("utf-8")).hexdigest(), \
        "獨立重述一層：canonical 串 → sha256（不經被測實現）"
    assert len(detail["metrics_hash"]) == 64
    assert raw_json != canonical, \
        "落庫字串（默認分隔符）≠ canonical 串：哈希吃的是後者（口徑差寫在這裡）"


# ---- ⑥ 返回體契約：18 鍵 + changed（確認未被 3.3-e 弄破）----

def test_evaluate_return_body_keeps_eighteen_plus_changed_keys(db, monkeypatch, stage_gate):
    """⑥ 返回體仍是 **18 鍵快照 + `changed`**，且 flag off / on 兩趟的**業務值**逐鍵相同（事件是旁路）。

    既有斷言在 `test_agent_stage.py`（`_EVALUATE_SNAPSHOT_KEYS` 逐鍵字面量、「快照 = 返回體去
    `changed`」、「接口層直出 18 鍵 + changed」）—— 本條不重複那三條，只確認 3.3-e **沒把它弄破**：
    鍵集逐字（本檔自帶同一份凍結表）+ `changed` 四鍵 + **業務值**逐鍵相同。

    【按 CTO 修正重寫】比對集 = 18 鍵去掉**身份**（`teacher_name`）與**時刻**（`stage_since` /
    `evaluated_at`）→ 兩趟必然不同的三格一律不比（同一格連跑兩趟時，`stage_since` 也會由 `""` 變成
    首趟寫下的真時刻）。CTO 點名的欄位逐一落點：`stage` / `metrics` / `blockers` / `next_stage` /
    `degraded` / `config_source` / `thresholds` 全在比對集內（下方 `named` 斷言逐名核對）；
    `capabilities` / `stale` 兩名**不在本返回體的 18 鍵契約內** —— 本契約用單值 `stage` 表達階段、
    用 `stage_since` + `metrics_ttl_hours` 表達證據新舊（欄名以 `_EVALUATE_SNAPSHOT_KEYS` 為唯一真相源，
    不為比對另造別名）。

    本條用兩位**同構**老師（都無狀態行 / 無樣本池 / 無配置行）承接兩趟：兩趟的業務值（含階段真值視圖）
    因此都能直接逐鍵比，不靠任何 mock。
    """
    import agent_stage_service

    monkeypatch.delenv("LEARNING_ENABLED", raising=False)
    off = agent_stage_service.evaluate(TEACHER)

    monkeypatch.setenv("LEARNING_ENABLED", "on")
    on = agent_stage_service.evaluate(OTHER_TEACHER)

    assert len(EVALUATE_SNAPSHOT_KEYS) == 18
    assert sorted(off) == sorted(on) == sorted(EVALUATE_SNAPSHOT_KEYS + ("changed",))
    assert sorted(off["changed"]) == sorted(on["changed"]) == sorted(CHANGED_KEYS)
    assert off["changed"] == {"stage_changed": False, "recommended": False, "demoted": False,
                              "reason": "blocked"}

    named = ("stage", "metrics", "blockers", "next_stage", "degraded", "config_source",
             "thresholds")
    assert set(named) <= set(STABLE_BODY_KEYS), "CTO 點名的欄位必須都在比對集內"
    assert len(STABLE_BODY_KEYS) == 15, "18 鍵 - 身份 1 - 時刻 2 = 15"
    assert (off["teacher_name"], on["teacher_name"]) == (TEACHER, OTHER_TEACHER), \
        "身份兩趟本該不同（因此不入比對集）"
    assert [row["event_type"] for row in _rows(OTHER_TEACHER)] == \
        ["learning_event_emitted", "agent_updated"], "flag 真的翻過去了（否則本條是空比對）"
    assert {key: off[key] for key in STABLE_BODY_KEYS} == \
        {key: on[key] for key in STABLE_BODY_KEYS}, \
        "flag 不參與返回體組裝：寫鏈與否不改評估結果（學習事件是旁路）"

