"""【Epic 4 step 4.2「服務層隔離讀路徑」】師門隔離守護測試。

對齊 `docs/epic4-lineage-design-v1.md`：
  §3.2  老師端讀路徑改造清單（P0 / P1）—— 本文件逐條走一遍
  §3.3  模板線接口層收口（`template_api._check_lineage` 兩態語義）
  §4.1  錯誤碼契約（8 碼 → HTTP 狀態碼；統一錯誤體四鍵 `{error, msg, errors, warnings}`）
  §4.3  既有接口改造（路徑不變，只加可選 `lineage_id`）
  §4.4  feature flag `LINEAGE_ENABLED`（默認 off；off = 零行為變化）
  §8    測試矩陣：③ 組（flag off 逐字節一致）、⑤ 組（隔離正確性，**核心**）、
        ⑨ 組（默認師門 id 可復現 + 無 `COALESCE(lineage_id` 兜底）

運行（與其它測試同款）：
    cd backend
    ..\\venv\\Scripts\\python.exe -m pytest test_lineage.py -q

前置（`conftest.py`）：每用例重建 `test.db` + `migrations_runner.run_upgrade()`
→ `lineage` 表 + 12 張表的 `lineage_id` 列 + 默認師門種子就位；`LINEAGE_ENABLED`
**不設**（默認 off），故既有測試基線不變；需要 flag on 的用例一律
`monkeypatch.setenv("LINEAGE_ENABLED", "on")`。

fixture 紀律（§8 ⑤ 組：**不許**用「單老師 + 手工改庫」代替）：
`two_lineages` 造 **兩位老師 × 兩個真實師門**（`lineage` 兩行、各有一位 owner），
每位老師各有自己的學生與業務行，並額外造兩類「暗雷行」：
  · **未歸屬行**（`lineage_id = ''`）—— flag on 時不得出現在任何讀點結果裡；
  · **跨門行**（`teacher_name` = 老師 A、`lineage_id` = 師門 B）—— 只能被師門 B 看到。
每個讀點用例都把返回集合與「直接 SQL 按 lineage 過濾」的結果**逐行**比對；
flag on 缺 `lineage_id` → 4xx（斷言「不存在 4xx 之外的靜默全量」）。

本文件**不含**（各歸其子步）：
  · ④ 組（§4.2 的 7 個新接口 —— `lineage_api.router` 本子步仍為空）；
  · ⑥ 組（歸屬生命週期 / 寫側落 `lineage_id`：本子步讀路徑已過濾，寫側仍落 `''`）；
  · ⑦ 組（模板線 scope 接線 —— `lineage_id` 已在 `template_service._SCOPE_WHERE` 首位，
    本子步只守 `_check_lineage` 兩態）；
  · §3.2 **P2**（`get_draft_samples` / `get_agent_stage_log_stats` 的指標口徑）——
    這兩個讀點的唯一調用方在 Epic 3 的階段評估鏈（`agent_stage_service`），
    透傳 lineage 必然連帶改 Epic 3 的評估入口與其籤住的簽名；本子步不動 Epic 3 代碼。
"""
import hashlib
import json
import os
import re
from datetime import datetime, timedelta

import pytest
from fastapi import HTTPException

import agent
import database
import lineage_service
import template_api
from lineage_service import LineageError

# ---------------------------------------------------------------------------
# 兩師門常量：id 一律由 `slugify()` **計算**得出（§5.4 第 6 條：不落代碼常量）
# ---------------------------------------------------------------------------
TEACHER_A = "李老师"                                   # 師門 A 的 owner（0005 種子）
TEACHER_B = "王老师"                                   # 師門 B 的 owner（本 fixture 新建）
LIN_A = lineage_service.default_lineage_id(TEACHER_A)  # = 0005 種子出來的那一行
LIN_B = lineage_service.default_lineage_id(TEACHER_B)

STUDENT_A1 = "张三"          # init_db() 種子學生，0005 已回填到師門 A
STUDENT_A2 = "李四"          # 同上
STUDENT_A_ORPHAN = "陈七"    # 老師 A 名下但 `pt.lineage_id = ''`（未歸屬）
STUDENT_B1 = "王五"          # 師門 B 的 active 學生
STUDENT_B_QUIT = "赵六"      # 師門 B 的 inactive（退出）學生 → 老師側不可見

# ---------------------------------------------------------------------------
# 時間一律**相對當前時刻**計算（fixture 的「200 天前 / 1 天前」必須真的落在
# `agent.RECALL_DAYS`（60 天）與沉默閾值（30 天）之外 / 之內，不能靠寫死日期碰運氣）
# ---------------------------------------------------------------------------
_NOW = datetime.now()
STAMP = (_NOW - timedelta(minutes=5)).isoformat(timespec="seconds")
OLD_VISIT = (_NOW - timedelta(days=200)).isoformat(timespec="seconds")   # > RECALL_DAYS → 久未復診
RECENT_VISIT = (_NOW - timedelta(days=1)).isoformat(timespec="seconds")  # < RECALL_DAYS → 冷卻內
SILENT_SINCE = (_NOW - timedelta(days=200)).strftime("%Y-%m-%d")         # last_active_at 口徑 = YYYY-MM-DD
DAY_1 = (_NOW + timedelta(days=1)).strftime("%Y-%m-%d")                  # 未來 7 天內（日曆網格能命中）
DAY_2 = (_NOW + timedelta(days=2)).strftime("%Y-%m-%d")
DAY_3 = (_NOW + timedelta(days=3)).strftime("%Y-%m-%d")

# ---------------------------------------------------------------------------
# 小工具：直接讀庫 / 直接 SQL 期望值 / 語句序列採樣
# ---------------------------------------------------------------------------
def _conn():
    return database.get_connection()


def _fetch(sql, params=()):
    conn = _conn()
    try:
        return [dict(row) for row in conn.execute(sql, params).fetchall()]
    finally:
        conn.close()


def _sql_ids(sql, params=()):
    """「直接 SQL 按 lineage 過濾」的期望集合（§8 ⑤ 組的判據，取第一列排序）。"""
    conn = _conn()
    try:
        return sorted(row[0] for row in conn.execute(sql, params).fetchall())
    finally:
        conn.close()


def _ids(rows):
    """讀點返回的行集合 → 排序後的 id 列表。"""
    return sorted(row["id"] for row in rows)


def _names(rows):
    return sorted(row["name"] for row in rows)


def _insert(table, values):
    """插一行，返回 `lastrowid`（列名即 dict 鍵；`lineage_id` 未給則落 `''`）。"""
    payload = dict(values)
    payload.setdefault("lineage_id", "")
    cols = ", ".join(payload)
    marks = ", ".join("?" for _ in payload)
    conn = _conn()
    try:
        cur = conn.execute("INSERT INTO %s (%s) VALUES (%s)" % (table, cols, marks),
                           tuple(payload.values()))
        row_id = cur.lastrowid
        conn.commit()
    finally:
        conn.close()
    return row_id


def _sql_log(monkeypatch):
    """把每次 `database.get_connection()` 開出的連接掛上 trace → 收集**語句序列**（③ 組證據）。

    `lineage_service._store_connection()` 也走 `database.get_connection()`（函數體內 import +
    屬性查找），故此樁同時能抓到「flag off 時是否偷偷探了 `lineage` 表」。
    """
    log = []
    real = database.get_connection

    def _wrapped():
        conn = real()
        conn.set_trace_callback(log.append)
        return conn

    monkeypatch.setattr(database, "get_connection", _wrapped)
    return log



# ---------------------------------------------------------------------------
# 四態行（§8 ⑤ 組的「暗雷」）：a = 本師門行；cross = 跨門行；b = 別師門行；
# orphan = 未歸屬行（`lineage_id = ''`）——flag on 時只有 `a` 允許出現在師門 A 的讀點裡。
# ---------------------------------------------------------------------------
_KINDS = {
    "a": (TEACHER_A, LIN_A, STUDENT_A1),
    "cross": (TEACHER_A, LIN_B, STUDENT_B_QUIT),
    "b": (TEACHER_B, LIN_B, STUDENT_B1),
    "orphan": (TEACHER_A, "", STUDENT_A1),
}


@pytest.fixture
def two_lineages(client):
    """兩位老師 × 兩個師門；返回 `{"a": 師門 A id, "b": 師門 B id, "rows": {...}, "client": ...}`。

    師門 A = 遷移 0005 的種子（`lin-` + `slugify("李老师")`）+ `init_db()` 種下、0005 回填的兩個學生；
    師門 B = 本 fixture 用**同一個 id 口徑**新建（一師一門：`owner_teacher_name` = 老師 B）。
    """
    conn = _conn()
    # ① 老師 B + 三個新患者（`patients` 是跨師門主體，明確不加 `lineage_id`）
    conn.execute("INSERT OR IGNORE INTO teachers (name, description, status, last_active_at, created_at) "
                 "VALUES (?, '', 'active', ?, ?)", (TEACHER_B, STAMP, STAMP))
    for name in (STUDENT_B1, STUDENT_B_QUIT, STUDENT_A_ORPHAN):
        conn.execute("INSERT OR IGNORE INTO patients (name, guardian_name, relation, created_at) "
                     "VALUES (?, 'self', '本人', ?)", (name, STAMP))
    # 學生 A1/A2 拉到「沉默」區間（`scan_silent_students` 的 `last_active_at` 口徑 = YYYY-MM-DD）
    conn.execute("UPDATE patients SET last_active_at = ? WHERE name IN (?, ?)",
                 (SILENT_SINCE, STUDENT_A1, STUDENT_A2))
    # ② 師門 B（一師一門：owner = 老師 B）
    conn.execute("INSERT OR IGNORE INTO lineage (id, name, owner_teacher_name, description, status, "
                 "created_at, updated_at) VALUES (?, ?, ?, '', 'active', ?, ?)",
                 (LIN_B, TEACHER_B + "師門", TEACHER_B, STAMP, STAMP))
    # ③ 歸屬行：A 師門兩行由 0005 回填；此處補「未歸屬行」+「B 師門 active / inactive」
    for patient, teacher, status, lineage in (
        (STUDENT_A_ORPHAN, TEACHER_A, "active", ""),
        (STUDENT_B1, TEACHER_B, "active", LIN_B),
        (STUDENT_B_QUIT, TEACHER_B, "inactive", LIN_B),
    ):
        conn.execute("INSERT OR REPLACE INTO patient_teachers "
                     "(patient_name, teacher_name, status, created_at, lineage_id) VALUES (?, ?, ?, ?, ?)",
                     (patient, teacher, status, STAMP, lineage))
    conn.commit()
    conn.close()

    def _seed(table, payload_by_kind, has_patient=True):
        """四態各插一行（順序 a → cross → b → orphan；orphan 最後插 = id 最大的那一行）。"""
        out = {}
        for kind, (teacher, lineage, patient) in _KINDS.items():
            values = dict(payload_by_kind[kind])
            values["teacher_name"] = teacher
            values["lineage_id"] = lineage
            if has_patient:
                values["patient_name"] = patient
            out[kind] = _insert(table, values)
        return out

    def _care_task(patient):
        """沉默關懷請示的 `action_data`（去重口徑 = action + patient_name）。"""
        return json.dumps({"action": "send_care_notice", "patient_name": patient, "template": "care"},
                          ensure_ascii=False)

    rows = {}

    # 未簽草案：`a` / `a2` 在師門 A；`cross` / `orphan` 都是學生 A1 的**更高 id** 行
    #   → 子查詢若漏了 lineage（只在外層過濾），學生 A1 會被整行漏掉（越權的鏡像面 = 漏行）。
    rows["drafts"] = {
        "a": _insert("drafts", {"patient_name": STUDENT_A1, "teacher_name": TEACHER_A,
                                "content": "師門 A 草案", "signed": 0, "lineage_id": LIN_A}),
        "a2": _insert("drafts", {"patient_name": STUDENT_A2, "teacher_name": TEACHER_A,
                                 "content": "師門 A 草案（李四）", "signed": 0, "lineage_id": LIN_A}),
        "a_signed": _insert("drafts", {"patient_name": STUDENT_A1, "teacher_name": TEACHER_A,
                                       "content": "已簽，不得當草案", "signed": 1, "lineage_id": LIN_A}),
        "cross": _insert("drafts", {"patient_name": STUDENT_A1, "teacher_name": TEACHER_A,
                                    "content": "跨門草案（老師 A / 師門 B）", "signed": 0,
                                    "lineage_id": LIN_B}),
        "orphan": _insert("drafts", {"patient_name": STUDENT_A1, "teacher_name": TEACHER_A,
                                     "content": "未歸屬草案", "signed": 0, "lineage_id": ""}),
        "b": _insert("drafts", {"patient_name": STUDENT_B1, "teacher_name": TEACHER_B,
                                "content": "師門 B 草案", "signed": 0, "lineage_id": LIN_B}),
    }

    # 待處理轉述：`a2` 已處理（`processed = 1`）→ 任何態都不該返回
    rows["transcriptions"] = _seed("transcriptions", {
        "a": {"content": "轉述 A", "data_type": "chat", "processed": 0},
        "cross": {"content": "轉述 跨門", "data_type": "chat", "processed": 0},
        "b": {"content": "轉述 B", "data_type": "chat", "processed": 0},
        "orphan": {"content": "轉述 未歸屬", "data_type": "chat", "processed": 0},
    })
    rows["transcriptions"]["a2"] = _insert("transcriptions", {
        "patient_name": STUDENT_A2, "teacher_name": TEACHER_A, "content": "已處理轉述",
        "data_type": "chat", "processed": 1, "lineage_id": LIN_A})

    # 病歷：`a` / `a2` = 久未復診（200 天前）；`cross` = 老師 A 在師門 B 的**最近**就診
    #   → 復診掃描 flag on 時看不到 cross ⇒ 學生 A1 判為「久未復診」（與不加過濾的結論相反）。
    rows["patient_records"] = _seed("patient_records", {
        "a": {"ai_draft": "AI 草案 A", "final_plan": "終稿 A", "doctor": TEACHER_A,
              "visit_at": OLD_VISIT},
        "cross": {"ai_draft": "AI 草案 跨門", "final_plan": "終稿 跨門", "doctor": TEACHER_A,
                  "visit_at": RECENT_VISIT},
        "b": {"ai_draft": "AI 草案 B", "final_plan": "終稿 B", "doctor": TEACHER_B,
              "visit_at": OLD_VISIT},
        "orphan": {"ai_draft": "AI 草案 未歸屬", "final_plan": "終稿 未歸屬", "doctor": TEACHER_A,
                   "visit_at": OLD_VISIT},
    })
    rows["patient_records"]["a2"] = _insert("patient_records", {
        "patient_name": STUDENT_A2, "teacher_name": TEACHER_A, "ai_draft": "AI 草案 A2",
        "final_plan": "終稿 A2", "doctor": TEACHER_A, "visit_at": OLD_VISIT, "lineage_id": LIN_A})

    rows["appointments"] = _seed("appointments", {
        "a": {"initiator": STUDENT_A1, "scheduled_date": DAY_1, "scheduled_time": "09:00",
              "reason": "複診", "status": "confirmed", "created_at": STAMP, "confirmed_at": STAMP},
        "cross": {"initiator": STUDENT_B_QUIT, "scheduled_date": DAY_1,
                  "scheduled_time": "10:00", "reason": "跨門", "status": "confirmed",
                  "created_at": STAMP, "confirmed_at": STAMP},
        "b": {"initiator": STUDENT_B1, "scheduled_date": DAY_2, "scheduled_time": "09:00",
              "reason": "複診", "status": "confirmed", "created_at": STAMP, "confirmed_at": STAMP},
        "orphan": {"initiator": STUDENT_A1, "scheduled_date": DAY_3,
                   "scheduled_time": "09:00", "reason": "未歸屬", "status": "confirmed",
                   "created_at": STAMP, "confirmed_at": STAMP},
    })

    rows["record_tags"] = _seed("record_tags", {
        "a": {"record_id": 1, "tag_type": "證型", "tag_value": "氣虛", "created_at": STAMP},
        "cross": {"record_id": 2, "tag_type": "證型", "tag_value": "陰虛", "created_at": STAMP},
        "b": {"record_id": 3, "tag_type": "證型", "tag_value": "陽虛", "created_at": STAMP},
        # 未歸屬行故意與 `a` **同一個標籤** → flag on 時 count 必須是 1（不是 2）
        "orphan": {"record_id": 4, "tag_type": "證型", "tag_value": "氣虛", "created_at": STAMP},
    }, has_patient=False)

    rows["prescriptions"] = _seed("prescriptions", {
        "a": {"items_json": json.dumps([{"name": "黃芪", "dose": "10g"}], ensure_ascii=False),
              "note": "師門 A 方", "created_at": STAMP},
        "cross": {"items_json": "[]", "note": "跨門方", "created_at": STAMP},
        "b": {"items_json": "[]", "note": "師門 B 方", "created_at": STAMP},
        "orphan": {"items_json": "[]", "note": "未歸屬方", "created_at": STAMP},
    })

    # 智能體待辦：`a` = 學生 A2 的 pending（沉默掃描的「同門去重」用）；
    #   `cross` = 學生 A1 的 pending 但落在**師門 B** → 不得把師門 A 的 A1 頂掉（漏建的鏡像面）。
    rows["agent_tasks"] = _seed("agent_tasks", {
        "a": {"task_type": "request", "category": "student", "title": "李四已沉默 100 天",
              "content": "是否發送關懷通知？", "status": "pending", "created_at": STAMP,
              "action_data": _care_task(STUDENT_A2)},
        "cross": {"task_type": "request", "category": "student", "title": "张三（跨門）",
                  "content": "是否發送關懷通知？", "status": "pending", "created_at": STAMP,
                  "action_data": _care_task(STUDENT_A1)},
        "b": {"task_type": "request", "category": "student", "title": "王五（師門 B）",
              "content": "是否發送關懷通知？", "status": "pending", "created_at": STAMP,
              "action_data": _care_task(STUDENT_B1)},
        "orphan": {"task_type": "request", "category": "student", "title": "未歸屬待辦",
                   "content": "是否發送關懷通知？", "status": "pending", "created_at": STAMP,
                   "action_data": _care_task(STUDENT_A1)},
    }, has_patient=False)   # `agent_tasks` 無 `patient_name` 列（學生名在 action_data 裡）

    rows["agent_action_log"] = _seed("agent_action_log", {
        "a": {"task_id": 1, "action": "approved", "detail": "師門 A 行動", "created_at": STAMP},
        "cross": {"task_id": 2, "action": "approved", "detail": "跨門行動", "created_at": STAMP},
        "b": {"task_id": 3, "action": "approved", "detail": "師門 B 行動", "created_at": STAMP},
        "orphan": {"task_id": 4, "action": "approved", "detail": "未歸屬行動", "created_at": STAMP},
    }, has_patient=False)

    rows["complaints"] = _seed("complaints", {
        "a": {"content": "師門 A 陳述", "created_at": STAMP, "status": "pending"},
        "cross": {"content": "跨門陳述", "created_at": STAMP, "status": "pending"},
        "b": {"content": "師門 B 陳述", "created_at": STAMP, "status": "pending"},
        "orphan": {"content": "未歸屬陳述", "created_at": STAMP, "status": "pending"},
    })

    # 作業：`orphan` 是**同一學生 + 同一老師**的未歸屬行、且 id 更大 → flag off 取到的
    #   「最新一行」正是 orphan（既有全量行為，逐字節不變）；flag on 只能取到 `a`。
    rows["homework"] = {
        "a": _insert("homework", {"patient_name": STUDENT_A1, "teacher_name": TEACHER_A,
                                  "task": "師門 A 作業", "detail": "本門", "status": "pending",
                                  "created_at": STAMP, "lineage_id": LIN_A}),
        "orphan": _insert("homework", {"patient_name": STUDENT_A1, "teacher_name": TEACHER_A,
                                       "task": "未歸屬作業", "detail": "未歸屬", "status": "pending",
                                       "created_at": STAMP, "lineage_id": ""}),
        "b": _insert("homework", {"patient_name": STUDENT_B1, "teacher_name": TEACHER_B,
                                  "task": "師門 B 作業", "detail": "別門", "status": "pending",
                                  "created_at": STAMP, "lineage_id": LIN_B}),
    }

    # 欠費掃描的餘額來源（`accounts.username` = 學生姓名）：王五的 0 餘額不得給老師 A 建單
    conn = _conn()
    for username in (STUDENT_A1, STUDENT_B1):
        conn.execute("INSERT OR REPLACE INTO accounts (username, role, balance, updated_at) "
                     "VALUES (?, 'student', 0, ?)", (username, STAMP))
    conn.commit()
    conn.close()

    return {"a": LIN_A, "b": LIN_B, "rows": rows, "client": client}

# ---------------------------------------------------------------------------
# ⑨ 組：默認師門 id 可復現 + 「不許兜底 / 不許落常量」
# ---------------------------------------------------------------------------
def test_default_lineage_id_reproducible_and_matches_migration_seed(two_lineages):
    """⑨ 組：`default_lineage_id()` 是**純計算**（可復現、去空白），且庫裡那一行就是它。

    §5.4 第 6 條：默認師門 id 由 `slugify(teacher_name)` 計算得出，不落代碼常量；
    §0.1 / §3.1：一師一門 → `'lin-' + slugify(名)`。本用例把「計算口徑」與
    「遷移 0005 的種子 + 回填」釘在一起，防止兩邊漂移。
    """
    assert LIN_A == lineage_service.default_lineage_id(TEACHER_A)
    assert LIN_A == lineage_service.LINEAGE_ID_PREFIX + lineage_service.slugify(TEACHER_A)
    # 純中文名的 slug 走 `u<sha1(入參)[:8]>` 回落 —— hash 用的是**原始入參**，
    # 故「名字前後多帶空白」會算出**另一個** id：入參必須與庫裡 `owner_teacher_name` 逐字相同
    assert lineage_service.slugify(TEACHER_A) == \
        "u" + hashlib.sha1(TEACHER_A.encode("utf-8")).hexdigest()[:8]
    assert lineage_service.default_lineage_id("  " + TEACHER_A + " ") != LIN_A
    assert LIN_A != LIN_B
    # 庫裡兩行：owner 與計算出來的 id 一一對應（種子 + 本 fixture 新建各一）
    assert {(row["id"], row["owner_teacher_name"]) for row in
            _fetch("SELECT id, owner_teacher_name FROM lineage")} == {
        (LIN_A, TEACHER_A), (LIN_B, TEACHER_B)}
    # 0005 已把 init_db() 種下的兩個學生回填到師門 A；本 fixture 另建的「未歸屬」陳七
    # 保持 `lineage_id = ''`（孤兒不猜、不兜底 —— §5.4 第 2 條）
    by_patient = {row["patient_name"]: row["lineage_id"] for row in _fetch(
        "SELECT patient_name, lineage_id FROM patient_teachers WHERE teacher_name = ?", (TEACHER_A,))}
    assert by_patient[STUDENT_A1] == LIN_A and by_patient[STUDENT_A2] == LIN_A
    assert by_patient[STUDENT_A_ORPHAN] == ""
    # 空名 / 純符號名 → `u<sha1[:8]>` 回落（不生成空 slug、不拋異常）
    assert re.match(r"^lin-u[0-9a-f]{8}$", lineage_service.default_lineage_id(""))
    assert re.match(r"^lin-u[0-9a-f]{8}$", lineage_service.default_lineage_id("！！"))


def test_no_coalesce_and_no_hardcoded_default_lineage_id(two_lineages):
    """⑨ 組：全後端**不得**出現 `COALESCE(lineage_id` 兜底，也不得把默認師門 id 寫成常量。

    兩條都是設計明文：`COALESCE` 兜底會讓「未歸屬行」被靜默歸到某個師門（§5.4 第 2 條）；
    默認 id 只能由 `default_lineage_id()` 計算（§5.4 第 6 條）。本用例掃源碼字面量。
    """
    here = os.path.dirname(os.path.abspath(__file__))
    # 【掃描範圍】只掃**生產模組**：與 `test_migrations.py::test_0005_source_keeps_epic4_redlines`
    # 掃「遷移源碼字面量」同口徑。測試文件裡出現這個字面量恰恰是為了**斷言它不存在**，
    # 掃進來只會「測試命中自己」（假陽性）。
    modules = ("database.py", "main.py", "agent.py", "lineage_service.py", "lineage_api.py",
               "template_api.py", "template_service.py", "agent_stage_service.py")
    sources = {}
    for name in modules:
        path = os.path.join(here, name)
        assert os.path.exists(path), "%s 不存在？" % name
        with open(path, encoding="utf-8") as handle:
            sources[name] = handle.read()
    # needle 用拼接構造：避免本文件自身的註釋 / 斷言文本命中自己（同上的假陽性問題）
    needle = "COALESCE(" + "lineage_id"
    for name, text in sources.items():
        assert needle not in text, "%s 出現了 %s 兜底" % (name, needle)
        # 默認 id 不得硬編碼：本文件**計算**出來的那兩個 id 不得出現在生產代碼字面量裡
        assert LIN_A not in text, "%s 硬編碼了默認師門 id" % name
        assert LIN_B not in text, "%s 硬編碼了默認師門 id" % name


# ---------------------------------------------------------------------------
# ③ 組：flag off（默認）逐字節一致 —— 零 SQL、零校驗、零行為變化
# ---------------------------------------------------------------------------
def test_flag_off_scope_is_pure_noop(monkeypatch):
    """③ 組：flag off 時 `lineage_read_scope()` 對**任何**入參都返回 `(False, "")`，不拋異常。"""
    monkeypatch.delenv("LINEAGE_ENABLED", raising=False)
    assert lineage_service.lineage_enabled() is False
    assert lineage_service.lineage_read_scope(None, None) == (False, "")
    assert lineage_service.lineage_read_scope("", "!!") == (False, "")
    assert lineage_service.lineage_read_scope(TEACHER_A, LIN_B) == (False, "")
    assert lineage_service.lineage_read_scope(TEACHER_A, None) == (False, "")
    # 庫層轉發同款（`database.lineage_read_scope` 是同一入口的薄封裝）
    assert database.lineage_read_scope(TEACHER_A, LIN_B) == (False, "")
    assert database.lineage_read_scope(None, None) == (False, "")
    # flag 的取值口徑：on / 1 / true / yes（大小寫、空白無關）都算開；其餘一律算關
    for value in ("on", "ON", " 1 ", "true", "Yes"):
        monkeypatch.setenv("LINEAGE_ENABLED", value)
        assert lineage_service.lineage_enabled() is True, value
    for value in ("off", "0", "no", "", "lineage"):
        monkeypatch.setenv("LINEAGE_ENABLED", value)
        assert lineage_service.lineage_enabled() is False, value

def test_flag_off_never_touches_lineage_store(two_lineages, monkeypatch):
    """③ 組核心證據：flag off 時**一次都不碰** `lineage` 存儲（零 SQL、零校驗）。

    把存放探針（`_store_connection` / `lineage_store_ready` / `load_lineage`）全部換成
    「一被調用就炸」的樁：所有讀點照常返回全量結果 → 證明隔離邏輯在 flag off 時
    **完全不在路徑上**；`calls == []` 同時蓋住「有沒有人偷偷先探一下表」。
    """
    monkeypatch.delenv("LINEAGE_ENABLED", raising=False)
    calls = []

    def _boom(*args, **kwargs):
        calls.append(args)
        raise AssertionError("flag off 時不得碰 lineage 存儲")

    monkeypatch.setattr(lineage_service, "_store_connection", _boom)
    monkeypatch.setattr(lineage_service, "lineage_store_ready", _boom)
    monkeypatch.setattr(lineage_service, "load_lineage", _boom)
    monkeypatch.setattr(lineage_service, "parse_lineage_id", _boom)
    rows = two_lineages["rows"]

    # 老師端學生列表：flag off = 該老師**全部** active 學生（含未歸屬的陳七）
    assert _names(database.get_teacher_patients(TEACHER_A, LIN_B)) == \
        sorted([STUDENT_A1, STUDENT_A2, STUDENT_A_ORPHAN])
    # 未簽草案：無過濾 → 每位學生取「最新未簽」= 張三取到 orphan(5)、李四取到 a2(2)
    assert _ids(database.get_drafts(TEACHER_A, LIN_B)) == \
        sorted([rows["drafts"]["a2"], rows["drafts"]["orphan"]])
    assert _ids(database.get_transcriptions(STUDENT_A1, TEACHER_A, "!!")) == \
        sorted([rows["transcriptions"]["a"], rows["transcriptions"]["orphan"]])
    assert _ids(database.get_patient_records(STUDENT_A1, TEACHER_A, "!!")) == \
        sorted([rows["patient_records"]["a"], rows["patient_records"]["orphan"]])
    assert _ids(database.get_appointments(STUDENT_A1, TEACHER_A, None, None, "!!")) == \
        sorted([rows["appointments"]["a"], rows["appointments"]["orphan"]])
    # 聯絡簿：flag off 仍是「該學生 + 該老師的最新一行」= 未歸屬那行（既有語義一字不動）
    assert database.get_homework(STUDENT_A1, TEACHER_A, "!!")["task"] == "未歸屬作業"
    # 標籤匯總：未歸屬行與本門同標籤 → flag off 時 `氣虛` count = 2（全量口徑），
    # 跨門行的 `陰虛` 也照樣計入（`ORDER BY count DESC`）
    assert [dict(row) for row in database.get_teacher_tags_summary(TEACHER_A, "!!")] == \
        [{"tag_type": "證型", "tag_value": "氣虛", "count": 2},
         {"tag_type": "證型", "tag_value": "陰虛", "count": 1}]
    # 藥方：flag off = 該老師全部藥方（本門 + 跨門 + 未歸屬都在）
    assert _ids(database.get_prescriptions(TEACHER_A, None, "!!")) == \
        sorted([rows["prescriptions"][k] for k in ("a", "cross", "orphan")])
    assert _ids(database.get_agent_tasks(TEACHER_A, "pending", "!!")) == \
        sorted([rows["agent_tasks"][k] for k in ("a", "cross", "orphan")])
    assert _ids(database.get_agent_action_log(TEACHER_A, 20, "!!")) == \
        sorted([rows["agent_action_log"][k] for k in ("a", "cross", "orphan")])
    assert _ids(database.get_complaints(TEACHER_A, "pending", "!!")) == \
        sorted([rows["complaints"][k] for k in ("a", "cross", "orphan")])
    # 空老師名 + flag off：`get_agent_action_log` 的「既有 fail-closed」早返回不變
    assert database.get_agent_action_log("", 20, "!!") == []
    # 三類掃描一起跑：flag off 口徑 = 全量（逐項拆解見下一個用例）
    assert agent.scan_student_requests(TEACHER_A, lineage_id="!!") == 4
    assert calls == []

def test_flag_off_sql_bytes_and_payload_identical(two_lineages, monkeypatch):
    """③ 組逐字節證據（庫層）：flag off 時「加不加 `lineage_id`、值是否合法」**語句序列完全一致**。

    判據三條：
      ① 同一個讀點在 `lineage_id` = 合法本門 / 合法別門 / 非法串 / 空串 四種取值下，
         trace 到的**語句序列逐條相同**（含參數無關的語句字面量）；
      ② 序列裡**沒有任何語句提到 `lineage`**（既不查 `lineage` 表，也不加過濾列）；
      ③ 返回值的 JSON 逐字節相同。
    """
    monkeypatch.delenv("LINEAGE_ENABLED", raising=False)
    log = _sql_log(monkeypatch)
    pairs = [
        (lambda: database.get_teacher_patients(TEACHER_A),
         lambda lid: database.get_teacher_patients(TEACHER_A, lid)),
        (lambda: database.get_drafts(TEACHER_A),
         lambda lid: database.get_drafts(TEACHER_A, lid)),
        (lambda: database.get_transcriptions(None, TEACHER_A),
         lambda lid: database.get_transcriptions(None, TEACHER_A, lid)),
        (lambda: database.get_patient_records(None, TEACHER_A),
         lambda lid: database.get_patient_records(None, TEACHER_A, lid)),
        (lambda: database.get_appointments(None, TEACHER_A),
         lambda lid: database.get_appointments(None, TEACHER_A, None, None, lid)),
        (lambda: database.get_homework(STUDENT_A1, TEACHER_A),
         lambda lid: database.get_homework(STUDENT_A1, TEACHER_A, lid)),
        (lambda: database.get_teacher_tags_summary(TEACHER_A),
         lambda lid: database.get_teacher_tags_summary(TEACHER_A, lid)),
        (lambda: database.get_prescriptions(TEACHER_A),
         lambda lid: database.get_prescriptions(TEACHER_A, None, lid)),
        (lambda: database.get_agent_tasks(TEACHER_A),
         lambda lid: database.get_agent_tasks(TEACHER_A, "pending", lid)),
        (lambda: database.get_agent_tasks(TEACHER_A, ""),
         lambda lid: database.get_agent_tasks(TEACHER_A, "", lid)),
        (lambda: database.get_agent_action_log(TEACHER_A),
         lambda lid: database.get_agent_action_log(TEACHER_A, 20, lid)),
        (lambda: database.get_complaints(TEACHER_A),
         lambda lid: database.get_complaints(TEACHER_A, "pending", lid)),
        (lambda: database.get_complaints(TEACHER_A, ""),
         lambda lid: database.get_complaints(TEACHER_A, "", lid)),
    ]
    for without, with_lid in pairs:
        del log[:]
        without()
        baseline = list(log)
        assert baseline, "trace 沒抓到語句 —— 測試自身失效"
        base_payload = json.dumps(without(), sort_keys=True, ensure_ascii=False, default=str)
        for value in (LIN_A, LIN_B, "!!", ""):
            del log[:]
            payload = json.dumps(with_lid(value), sort_keys=True, ensure_ascii=False, default=str)
            assert list(log) == baseline, (value, baseline, list(log))
            assert payload == base_payload, value
        for sql in baseline:
            assert "lineage" not in sql.lower(), sql


def test_flag_off_http_payload_byte_identical(two_lineages, monkeypatch):
    """③ 組逐字節證據（接口層）：flag off 時四個 `lineage_id` 取值下，各讀接口響應**逐字節相同**。"""
    monkeypatch.delenv("LINEAGE_ENABLED", raising=False)
    client = two_lineages["client"]
    cases = [
        ("/api/teacher-patients", {"teacher_name": TEACHER_A}),
        ("/api/drafts", {"teacher_name": TEACHER_A}),
        ("/api/drafts", {}),
        ("/api/transcriptions", {"teacher_name": TEACHER_A}),
        ("/api/transcriptions", {"patient_name": STUDENT_A1}),
        ("/api/patient-records", {"teacher_name": TEACHER_A}),
        ("/api/patient-records", {"patient_name": STUDENT_A1}),
        ("/api/appointments", {"teacher_name": TEACHER_A}),
        ("/api/appointments/calendar", {"teacher_name": TEACHER_A}),
        ("/api/tags-summary", {"teacher_name": TEACHER_A}),
        ("/api/prescriptions", {"teacher_name": TEACHER_A}),
        ("/api/role-data", {"role": TEACHER_A, "teacher_name": TEACHER_A,
                            "patient_name": STUDENT_A1}),
        ("/api/agent/tasks", {"teacher_name": TEACHER_A}),
        ("/api/agent/tasks", {"teacher_name": TEACHER_A, "status": ""}),
        ("/api/agent_tasks", {"teacher_name": TEACHER_A}),
        ("/api/agent_action_log", {"teacher_name": TEACHER_A}),
        ("/api/complaints", {"teacher_name": TEACHER_A}),
        ("/api/complaints", {"teacher_name": TEACHER_A, "status": ""}),
    ]
    for path, params in cases:
        base = client.get(path, params=params)
        assert base.status_code == 200, (path, base.text)
        for value in (LIN_A, LIN_B, "!!", ""):
            variant = client.get(path, params=dict(params, lineage_id=value))
            assert variant.status_code == 200, (path, value, variant.text)
            assert variant.text == base.text, (path, value)

def test_flag_off_agent_scan_full_volume_and_ignores_param(two_lineages, monkeypatch):
    """③ 組：flag off 時 `/api/agent/scan` 的三類掃描範圍仍是**全量**，`lineage_id` 被完全忽略。

    逐項口徑（陳七 = 老師 A 名下的未歸屬學生，flag off 時必須照樣被掃到；`lineage_id` 傳
    別師門 id / 非法串都當空氣）：
      沉默關懷 1（陳七；張三 / 李四 已被 pending 去重命中）
      ＋ 欠費預存 1（張三餘額 0 < `BILLING_LOW_BALANCE`；李四 / 陳七從未開戶 → 不進欠費掃描）
      ＋ 復診提醒 2（張三 / 李四：老師 A 名下最後就診 = 200 天前 > `RECALL_DAYS`）
      = 4；第二次掃描 = 0（去重生效）。
    """
    monkeypatch.delenv("LINEAGE_ENABLED", raising=False)
    client = two_lineages["client"]
    before = {row["id"] for row in _fetch("SELECT id FROM agent_tasks")}
    first = client.post("/api/agent/scan", json={"teacher_name": TEACHER_A}, params={"lineage_id": LIN_B})
    assert first.status_code == 200
    assert first.json() == {"ok": True, "created": 4, "new_tasks": 4}
    new_rows = [row for row in
                _fetch("SELECT id, title, action_data, lineage_id FROM agent_tasks")
                if row["id"] not in before]
    assert len(new_rows) == 4
    # 新建行的歸屬學生含**未歸屬的陳七** —— 這正是 flag off「全量口徑」的簽名
    assert sorted(json.loads(row["action_data"])["patient_name"] for row in new_rows) == \
        sorted([STUDENT_A_ORPHAN, STUDENT_A1, STUDENT_A1, STUDENT_A2])
    assert all(row["lineage_id"] == "" for row in new_rows)   # 寫側仍落 ''（⑥ 組補）
    second = client.post("/api/agent/scan", json={"teacher_name": TEACHER_A}, params={"lineage_id": "!!"})
    assert second.json()["created"] == 0


def test_flag_off_template_check_lineage_keeps_epic1_contract(two_lineages, monkeypatch):
    """③ 組（Epic 1 回歸紅線）：flag off 時模板線**逐字保留** Epic 1 口徑 —— 非空 `lineage_id` 一律 400。"""
    monkeypatch.delenv("LINEAGE_ENABLED", raising=False)
    assert template_api._check_lineage(None, TEACHER_A) is None
    assert template_api._check_lineage("", TEACHER_A) is None
    with pytest.raises(HTTPException) as excinfo:
        template_api._check_lineage(LIN_A, TEACHER_A)
    assert excinfo.value.status_code == 400
    assert excinfo.value.detail["error"] == lineage_service.LINEAGE_NOT_SUPPORTED
    # 也走一次真實接口：`GET /api/templates` 帶 non-empty lineage_id → 400（路徑不變、錯誤體同形狀）
    res = two_lineages["client"].get("/api/templates", params={
        "teacher_name": TEACHER_A, "teacher_id": TEACHER_A, "lineage_id": LIN_A})
    assert res.status_code == 400
    assert res.json()["detail"]["error"] == lineage_service.LINEAGE_NOT_SUPPORTED


# ---------------------------------------------------------------------------
# ⑤ 組（核心）：三類智能體掃描的隔離正確性
# ---------------------------------------------------------------------------
def test_flag_on_silent_scan_scope_and_cross_lineage_not_suppressing(two_lineages, monkeypatch):
    """⑤ 組：flag on 時沉默掃描只掃本師門學生；別師門的同名 pending 不得把本門學生「頂掉」。

    張三在師門 B 已有一條 pending 關懷請示（跨門行）→ 若去重集合漏了 lineage 過濾，
    師門 A 的張三會被誤判為「已有 pending」而**不再建單**（漏建）；本用例斷言它建了。
    """
    monkeypatch.setenv("LINEAGE_ENABLED", "on")
    before = {row["id"] for row in _fetch("SELECT id FROM agent_tasks")}
    assert database.scan_silent_students(TEACHER_A, lineage_id=LIN_A) == 1
    new_rows = [row for row in
                _fetch("SELECT id, title, action_data, lineage_id FROM agent_tasks")
                if row["id"] not in before]
    # 新建的**只有**張三一條：李四本門已有 pending（去重命中）；陳七 / 王五不在本師門範圍內
    assert [row["title"] for row in new_rows] == ["%s已沉默 200 天" % STUDENT_A1]
    assert json.loads(new_rows[0]["action_data"]) == {
        "action": "send_care_notice", "patient_name": STUDENT_A1, "template": "care"}
    assert new_rows[0]["lineage_id"] == ""      # ⑤/⑥ 接口：寫側仍落 ''（本子步不改寫側）
    # 【⑤ 組已知缺口（屬 ⑥ 組）】寫側落 '' ⇒ flag on 的去重讀不到剛寫的行 ⇒ 再掃一次**仍建 1 條**。
    # ⑥ 組把寫側接上 lineage_id 後，此斷言應改成 0（那時才冪等）。
    assert database.scan_silent_students(TEACHER_A, lineage_id=LIN_A) == 1
    # 老師 B 的掃描碰不到師門 A 的學生：王五（師門 B）本門已有 pending → 0 條，
    # 且新建行的標題裡不會出現別門學生
    assert database.scan_silent_students(TEACHER_B, lineage_id=LIN_B) == 0
    assert all(STUDENT_B1 not in row["title"] for row in new_rows)


def test_flag_on_billing_and_recall_scans_isolated(two_lineages, monkeypatch):
    """⑤ 組：欠費 / 復診兩類掃描同樣只看本師門。

    · 欠費：王五（師門 B）餘額同為 0，但老師 A 的掃描不得給他建單 → 只建張三 1 條；
    · 復診：跨門行（老師 A / 師門 B）的就診時間不得參與「最近一次就診」→ 張三按**本門**的
      200 天前就診判為久未復診（與「不加過濾看不到提示」的結論相反）→ 建單。
    """
    monkeypatch.setenv("LINEAGE_ENABLED", "on")
    before = {row["id"] for row in _fetch("SELECT id FROM agent_tasks")}
    assert agent.check_billing_alerts(TEACHER_A, lineage_id=LIN_A) == 1
    assert agent.check_recall_alerts(TEACHER_A, lineage_id=LIN_A) == 2
    new_rows = sorted((row for row in _fetch("SELECT id, title, action_data FROM agent_tasks")
                       if row["id"] not in before), key=lambda row: row["title"])
    assert [row["title"] for row in new_rows] == sorted([
        "%s余额仅剩 0 分" % STUDENT_A1,                  # 欠費：只有本門的張三開過戶
        "%s距上次就诊已 200 天" % STUDENT_A1,            # 復診：只認本門那條 200 天前的就診
        "%s距上次就诊已 200 天" % STUDENT_A2,
    ])
    assert sorted(json.loads(row["action_data"])["patient_name"] for row in new_rows) == \
        sorted([STUDENT_A1, STUDENT_A1, STUDENT_A2])
    # 王五（師門 B，餘額同為 0）不得被老師 A 的兩類掃描碰到
    assert all(STUDENT_B1 not in row["title"] for row in new_rows)


def test_flag_on_unified_scan_total_and_no_foreign_student(two_lineages, monkeypatch):
    """⑤ 組：一次跑完三類（`agent.scan_student_requests`）→ 本師門 4 條；別師門學生 0 條。"""
    monkeypatch.setenv("LINEAGE_ENABLED", "on")
    before = {row["id"] for row in _fetch("SELECT id FROM agent_tasks")}
    assert agent.scan_student_requests(TEACHER_A, lineage_id=LIN_A) == 4
    new_rows = [row for row in _fetch(
        "SELECT id, title, action_data, teacher_name FROM agent_tasks") if row["id"] not in before]
    # 4 條全掛在老師 A 名下，歸屬學生 = 張三×3（關懷 / 欠費 / 復診）+ 李四×1（復診）
    assert len(new_rows) == 4
    assert {row["teacher_name"] for row in new_rows} == {TEACHER_A}
    assert sorted(json.loads(row["action_data"])["patient_name"] for row in new_rows) == \
        sorted([STUDENT_A1, STUDENT_A1, STUDENT_A1, STUDENT_A2])
    # 師門 B 自己掃描只碰王五：關懷（王五本門已有 pending → 去重命中 → 0）＋ 欠費 1 條
    # ＋ 復診 1 條（`b` 行 = 王五 / 師門 B / 200 天前就診 → 本門口徑下確實久未復診）
    assert agent.scan_student_requests(TEACHER_B, lineage_id=LIN_B) == 2
    b_rows = _fetch("SELECT title, action_data FROM agent_tasks WHERE teacher_name = ?", (TEACHER_B,))
    assert all(STUDENT_A1 not in row["title"] + (row["action_data"] or "") for row in b_rows)
    assert all(STUDENT_B1 not in row["title"] for row in new_rows)

# ---------------------------------------------------------------------------
# ⑤ 組（核心）：讀點的隔離正確性 + fail-loud 契約
# ---------------------------------------------------------------------------
def _assert_scope_contract(call, foreign_code=lineage_service.LINEAGE_FORBIDDEN):
    """flag on 的 5 條 fail-loud 路徑（§4.1 / §5.2「漏改的表現必須是 4xx」）。

    `call(lineage_id)` = 「以某老師身份讀某個讀點」。缺 / 空 / 純空白 → 400 `lineage_required`；
    格式非法 → 400 `lineage_invalid`；師門不存在 → 404 `lineage_not_found`；別師門 → 403。
    """
    for value in (None, "", "   "):
        with pytest.raises(LineageError) as excinfo:
            call(value)
        assert excinfo.value.code == lineage_service.LINEAGE_REQUIRED, value
        assert excinfo.value.detail() == {
            "error": lineage_service.LINEAGE_REQUIRED,
            "msg": excinfo.value.msg,
            "errors": [],
            "warnings": [],
        }
        assert lineage_service.lineage_error_status(excinfo.value.code) == 400
    with pytest.raises(LineageError) as excinfo:
        call("TCM-001")
    assert excinfo.value.code == lineage_service.LINEAGE_INVALID
    with pytest.raises(LineageError) as excinfo:
        call("lin-nobody-here")
    assert excinfo.value.code == lineage_service.LINEAGE_NOT_FOUND
    assert lineage_service.lineage_error_status(excinfo.value.code) == 404
    with pytest.raises(LineageError) as excinfo:
        call(LIN_B)
    assert excinfo.value.code == foreign_code
    assert lineage_service.lineage_error_status(excinfo.value.code) == 403


def test_flag_on_teacher_patients_isolated(two_lineages, monkeypatch):
    """⑤ 組 P0-①：老師端學生列表 = 本師門的 `active` 歸屬行；未歸屬 / 別門 / 已退出都不可見。"""
    monkeypatch.setenv("LINEAGE_ENABLED", "on")
    got = _names(database.get_teacher_patients(TEACHER_A, LIN_A))
    expected = _sql_ids("SELECT p.name FROM patients p "
                        "INNER JOIN patient_teachers pt ON p.name = pt.patient_name "
                        "WHERE pt.lineage_id = ? AND pt.teacher_name = ? AND pt.status = 'active' "
                        "ORDER BY p.name", (LIN_A, TEACHER_A))
    assert got == expected == sorted([STUDENT_A1, STUDENT_A2])
    assert STUDENT_A_ORPHAN not in got            # 未歸屬行（`lineage_id = ''`）不可見
    # 師門 B 只看得到王五（趙六 inactive → 不可見；張三/李四在師門 A）
    assert _names(database.get_teacher_patients(TEACHER_B, LIN_B)) == [STUDENT_B1]
    # 跨師門（別的 lineage_id）+ 空 / 非法 / 不存在 → 4xx，絕不返回全量
    _assert_scope_contract(lambda lid: database.get_teacher_patients(TEACHER_A, lid))
    # 老師為空（flag on）→ 400：先於一切查詢（「teacher_name 可空 = 高危」頭一條）
    with pytest.raises(LineageError) as excinfo:
        database.get_teacher_patients(None, LIN_A)
    assert excinfo.value.code == lineage_service.LINEAGE_REQUIRED
    with pytest.raises(LineageError) as excinfo:
        database.get_teacher_patients(TEACHER_B, LIN_A)   # 師門 A 的 owner 是李老师
    assert excinfo.value.code == lineage_service.LINEAGE_FORBIDDEN


def test_flag_on_drafts_subquery_is_filtered(two_lineages, monkeypatch):
    """⑤ 組 P0-②：未簽草案的 lineage 過濾必須進**子查詢**（否則「本門無草案」的學生整行漏掉）。"""
    monkeypatch.setenv("LINEAGE_ENABLED", "on")
    rows = two_lineages["rows"]
    got = _ids(database.get_drafts(TEACHER_A, LIN_A))
    expected = _sql_ids("SELECT d.id FROM drafts d INNER JOIN ("
                        "SELECT patient_name, MAX(id) AS max_id FROM drafts "
                        "WHERE signed = 0 AND lineage_id = ? AND teacher_name = ? "
                        "GROUP BY patient_name) latest ON d.id = latest.max_id",
                        (LIN_A, TEACHER_A))
    assert got == expected == sorted([rows["drafts"]["a"], rows["drafts"]["a2"]])
    # 張三本門那行必須在（若過濾只寫在外層：張三 latest = 跨門行(4) → 被外層丟掉 → 整行漏掉）
    assert rows["drafts"]["a"] in got
    assert rows["drafts"]["cross"] not in got       # 跨門行只歸師門 B
    assert rows["drafts"]["orphan"] not in got      # 未歸屬行不出現
    assert rows["drafts"]["a_signed"] not in got    # 已簽不算未簽草案
    assert _ids(database.get_drafts(TEACHER_B, LIN_B)) == [rows["drafts"]["b"]]
    _assert_scope_contract(lambda lid: database.get_drafts(TEACHER_A, lid))
    with pytest.raises(LineageError) as excinfo:
        database.get_drafts(None, LIN_A)            # 老師端可空 = 全庫草案（高危）→ 400
    assert excinfo.value.code == lineage_service.LINEAGE_REQUIRED


def test_flag_on_transcriptions_isolated(two_lineages, monkeypatch):
    """⑤ 組 P0-⑤：待處理轉述只回本師門（`processed = 0` 條件一字不動）。"""
    monkeypatch.setenv("LINEAGE_ENABLED", "on")
    rows = two_lineages["rows"]
    got = _ids(database.get_transcriptions(None, TEACHER_A, LIN_A))
    expected = _sql_ids("SELECT id FROM transcriptions WHERE processed = 0 "
                        "AND lineage_id = ? AND teacher_name = ?", (LIN_A, TEACHER_A))
    assert got == expected == [rows["transcriptions"]["a"]]
    # 學生 + 老師一起給：跨門 / 未歸屬行仍不可見
    assert _ids(database.get_transcriptions(STUDENT_A1, TEACHER_A, LIN_A)) == \
        [rows["transcriptions"]["a"]]
    assert _ids(database.get_transcriptions(None, TEACHER_B, LIN_B)) == \
        [rows["transcriptions"]["b"]]
    assert rows["transcriptions"]["a2"] not in got      # processed = 1
    _assert_scope_contract(lambda lid: database.get_transcriptions(None, TEACHER_A, lid))
    # 學生端讀法（不帶 teacher_name）flag on → 400，不退化為跨師門查詢
    with pytest.raises(LineageError) as excinfo:
        database.get_transcriptions(STUDENT_A1, None, LIN_A)
    assert excinfo.value.code == lineage_service.LINEAGE_REQUIRED
# ---------------------------------------------------------------------------
# ⑤ 組（核心）：其餘讀點（病歷 / 預約 / 聯絡簿 / 標籤 / 藥方 / 待辦 / 日誌 / 陳述）的隔離
# ---------------------------------------------------------------------------
def test_flag_on_patient_records_and_appointments_isolated(two_lineages, monkeypatch):
    """⑤ 組 P0-③ / P2：病歷歷史與預約列表只回本師門；學生端讀法（無 teacher_name）→ 400。"""
    monkeypatch.setenv("LINEAGE_ENABLED", "on")
    rows = two_lineages["rows"]

    # 病歷：老師 A + 師門 A + 學生張三 → 只有 `a`（未歸屬行同名同老師但 lineage='' → 不可見）
    assert _ids(database.get_patient_records(STUDENT_A1, TEACHER_A, LIN_A)) == \
        [rows["patient_records"]["a"]]
    # 不限學生：`a` + `a2`；跨門行（老师 A / 师门 B）與未歸屬行都不在
    got = _ids(database.get_patient_records(None, TEACHER_A, LIN_A))
    assert got == sorted([rows["patient_records"]["a"], rows["patient_records"]["a2"]])
    assert rows["patient_records"]["cross"] not in got
    assert rows["patient_records"]["orphan"] not in got
    assert _ids(database.get_patient_records(None, TEACHER_B, LIN_B)) == \
        [rows["patient_records"]["b"]]
    _assert_scope_contract(lambda lid: database.get_patient_records(None, TEACHER_A, lid))
    # 學生端讀法（不帶 teacher_name）→ 400，不退化成「該患者所有老師的記錄」
    with pytest.raises(LineageError) as excinfo:
        database.get_patient_records(STUDENT_A1, None, LIN_A)
    assert excinfo.value.code == lineage_service.LINEAGE_REQUIRED

    # 預約：本門只有 `a`（張三）；同學生同老師的未歸屬行被排除、跨門行歸師門 B
    assert _ids(database.get_appointments(None, TEACHER_A, None, None, LIN_A)) == \
        [rows["appointments"]["a"]]
    assert _ids(database.get_appointments(STUDENT_A1, TEACHER_A, None, None, LIN_A)) == \
        [rows["appointments"]["a"]]
    # 把三天全開的日期窗打開也拉不出別門 / 未歸屬行
    assert _ids(database.get_appointments(None, TEACHER_A, DAY_1, DAY_3, LIN_A)) == \
        [rows["appointments"]["a"]]
    assert _ids(database.get_appointments(None, TEACHER_B, None, None, LIN_B)) == \
        [rows["appointments"]["b"]]
    _assert_scope_contract(lambda lid: database.get_appointments(None, TEACHER_A, None, None, lid))
    with pytest.raises(LineageError) as excinfo:
        database.get_appointments(STUDENT_A1, None, None, None, LIN_A)
    assert excinfo.value.code == lineage_service.LINEAGE_REQUIRED


def test_flag_on_homework_and_tags_summary_isolated(two_lineages, monkeypatch):
    """⑤ 組 P0-④ / P1：聯絡簿「最新一行」與標籤匯總都只認本師門。"""
    monkeypatch.setenv("LINEAGE_ENABLED", "on")
    rows = two_lineages["rows"]

    # 聯絡簿：本門那行（`a`）；同學生同老師的未歸屬行（id 更大 = flag off 時的「最新」）不可見
    got = database.get_homework(STUDENT_A1, TEACHER_A, LIN_A)
    assert got["id"] == rows["homework"]["a"] and got["task"] == "師門 A 作業"
    assert database.get_homework(STUDENT_A1, TEACHER_B, LIN_B) is None   # 老師 B 名下沒有張三
    assert database.get_homework(STUDENT_B1, TEACHER_B, LIN_B)["id"] == rows["homework"]["b"]
    _assert_scope_contract(lambda lid: database.get_homework(STUDENT_A1, TEACHER_A, lid))
    with pytest.raises(LineageError) as excinfo:
        database.get_homework(STUDENT_A1, None, LIN_A)      # 老師名空（學生端讀法）→ 400
    assert excinfo.value.code == lineage_service.LINEAGE_REQUIRED

    # 標籤匯總：只算本門行（`a` 的 氣虛 = 1）—— 未歸屬同標籤行不得把它頂成 2，
    # 跨門行的 陰虛 也不進本門的匯總
    assert [dict(row) for row in database.get_teacher_tags_summary(TEACHER_A, LIN_A)] == \
        [{"tag_type": "證型", "tag_value": "氣虛", "count": 1}]
    assert [dict(row) for row in database.get_teacher_tags_summary(TEACHER_B, LIN_B)] == \
        [{"tag_type": "證型", "tag_value": "陽虛", "count": 1}]
    _assert_scope_contract(lambda lid: database.get_teacher_tags_summary(TEACHER_A, lid))
def test_flag_on_prescriptions_tasks_log_and_complaints_isolated(two_lineages, monkeypatch):
    """⑤ 組 P1 / P2：藥方、待辦、行動日誌、學生陳述 —— 四張「老師名下」表全按本師門過濾。"""
    monkeypatch.setenv("LINEAGE_ENABLED", "on")
    rows = two_lineages["rows"]

    assert _ids(database.get_prescriptions(TEACHER_A, None, LIN_A)) == [rows["prescriptions"]["a"]]
    assert _ids(database.get_prescriptions(TEACHER_A, STUDENT_A1, LIN_A)) == \
        [rows["prescriptions"]["a"]]     # 未歸屬那行同學生同老師，但 lineage='' → 不可見
    assert _ids(database.get_prescriptions(TEACHER_B, None, LIN_B)) == [rows["prescriptions"]["b"]]
    _assert_scope_contract(lambda lid: database.get_prescriptions(TEACHER_A, None, lid))

    # 待辦：帶 status 與不帶 status 兩個分支都要過濾（漏任一分支 = 漏改即越權）
    assert _ids(database.get_agent_tasks(TEACHER_A, "pending", LIN_A)) == [rows["agent_tasks"]["a"]]
    assert _ids(database.get_agent_tasks(TEACHER_A, "", LIN_A)) == [rows["agent_tasks"]["a"]]
    assert _ids(database.get_agent_tasks(TEACHER_B, "pending", LIN_B)) == [rows["agent_tasks"]["b"]]
    _assert_scope_contract(lambda lid: database.get_agent_tasks(TEACHER_A, "pending", lid))

    # 行動日誌：兩個分支同理；空老師名的「既有 fail-closed」先於作用域校驗 → flag on 也是 []
    assert _ids(database.get_agent_action_log(TEACHER_A, 20, LIN_A)) == \
        [rows["agent_action_log"]["a"]]
    assert _ids(database.get_agent_action_log(TEACHER_B, 20, LIN_B)) == \
        [rows["agent_action_log"]["b"]]
    assert database.get_agent_action_log("", 20, LIN_A) == []
    _assert_scope_contract(lambda lid: database.get_agent_action_log(TEACHER_A, 20, lid))

    # 學生陳述：pending / 全量兩分支同理
    assert [row["id"] for row in database.get_complaints(TEACHER_A, "pending", LIN_A)] == \
        [rows["complaints"]["a"]]
    assert [row["id"] for row in database.get_complaints(TEACHER_A, "", LIN_A)] == \
        [rows["complaints"]["a"]]
    assert [row["id"] for row in database.get_complaints(TEACHER_B, "pending", LIN_B)] == \
        [rows["complaints"]["b"]]
    _assert_scope_contract(lambda lid: database.get_complaints(TEACHER_A, "pending", lid))


def test_flag_on_scans_fail_loud_without_valid_lineage(two_lineages, monkeypatch):
    """⑤ 組：三類掃描在 flag on + 缺 / 非法 / 跨門 `lineage_id` 時一律 4xx，且**一行都不寫**。

    附帶守住「fail-loud 不佔連接」：`check_billing_alerts` 早期版本在**開完連接後**才由被調函數
    做作用域校驗，拋錯路徑走不到 `conn.close()` → 連接泄漏。本用例跑完接著的用例會刪 `test.db`
    （`client` fixture），泄漏的連接在 Windows 上會把刪除頂成 `PermissionError` —— 故本用例
    同時是「校驗前置於開連接」的回歸網（失敗現象在**下一個**用例的 setup）。
    """
    monkeypatch.setenv("LINEAGE_ENABLED", "on")
    for call in (
        lambda lid: database.scan_silent_students(TEACHER_A, 30, lid),
        lambda lid: agent.check_billing_alerts(TEACHER_A, lineage_id=lid),
        lambda lid: agent.check_recall_alerts(TEACHER_A, lineage_id=lid),
        lambda lid: agent.scan_student_requests(TEACHER_A, lid),
    ):
        before = len(_fetch("SELECT id FROM agent_tasks"))
        _assert_scope_contract(call)
        # fail-loud = 掃描沒跑起來：既沒有新建待辦，也沒有把別門 / 未歸屬的學生掃進來
        assert len(_fetch("SELECT id FROM agent_tasks")) == before, call


def test_lineage_error_handler_http_contract(two_lineages, monkeypatch):
    """⑤ 組（接口層）：`LineageError` → 真 HTTP 狀態碼 + `{error, msg, errors, warnings}` 四鍵。"""
    client = two_lineages["client"]
    url = "/api/teacher-patients"

    # flag off：同一請求（不帶 lineage_id）照常 200 → 向後兼容 / §4.4「零行為變化」
    monkeypatch.delenv("LINEAGE_ENABLED", raising=False)
    off = client.get(url, params={"teacher_name": TEACHER_A})
    assert off.status_code == 200
    assert sorted(row["name"] for row in off.json()) == \
        sorted([STUDENT_A1, STUDENT_A2, STUDENT_A_ORPHAN])

    monkeypatch.setenv("LINEAGE_ENABLED", "on")
    # 缺參數 → 400 lineage_required（**不許**退回全量）
    res = client.get(url, params={"teacher_name": TEACHER_A})
    assert res.status_code == 400
    assert sorted(res.json()["detail"]) == ["error", "errors", "msg", "warnings"]
    assert res.json()["detail"] == {
        "error": lineage_service.LINEAGE_REQUIRED,
        "msg": "缺少師門上下文（lineage_id）：老師端讀取必須帶 lineage_id",
        "errors": [], "warnings": [],
    }
    # 非法格式 → 400；不存在 → 404；別師門 → 403 —— 狀態碼全部取自服務層映射表
    for lineage_id, status_code, code in (
        ("TCM-001", 400, lineage_service.LINEAGE_INVALID),
        ("lin-nobody-here", 404, lineage_service.LINEAGE_NOT_FOUND),
        (LIN_B, 403, lineage_service.LINEAGE_FORBIDDEN),
    ):
        res = client.get(url, params={"teacher_name": TEACHER_A, "lineage_id": lineage_id})
        assert (res.status_code, res.json()["detail"]["error"]) == (status_code, code), lineage_id
        assert res.json()["detail"]["errors"] == [] and res.json()["detail"]["warnings"] == []
    # 合法本門 → 200，且只回本師門學生（未歸屬的陳七不可見）
    ok = client.get(url, params={"teacher_name": TEACHER_A, "lineage_id": LIN_A})
    assert ok.status_code == 200
    assert sorted(row["name"] for row in ok.json()) == sorted([STUDENT_A1, STUDENT_A2])

