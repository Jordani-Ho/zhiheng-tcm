"""P-301「静默基线」验收用例。

来源：
  · `docs/phase3-construction-outline.md` P-301（施工大纲）
  · `team/instructions/INSTR-2026-10-04-03-C板块.md` §4（验收条件 1–6）

背景（本用例保护的回归）：
  `patients.last_active_at` 的**每一处写入都是硬编码日期**（`update_homework_status` /
  `insert_transcription` 写 `"2026-09-17"`；`create_homework` / `sign_draft` 写
  `"2026-09-16"` / `"2026-09-19"`），而读取用 `datetime.now()` 相减
  → **字段永不推进、沉默天数单向增长** → 门规 C1 一旦上线会把**全部学生**判为「无互动」。

处置：**废弃该字段**，门规改用「静默基线」= 从业务表**实时算**最后一次真实互动时间
（主力源 = `patient_records.visit_at`，`sign_draft` 落 `datetime.now().isoformat()`）。

本文件覆盖 INSTR-03 §4 的验收 1 / 2 / 3，外加两条口径用例。
"""
import pytest

import database
import lineage_service

TEACHER = "李老师"
STUDENT = "张三"          # init_db() 的种子学生，已挂在李老师名下


def _conn():
    return database.get_connection()


def _add_patient_record(patient_name, teacher_name, visit_at, lineage_id=""):
    """直接落一行病历 —— `visit_at` 是静默基线唯一认可的时间源。"""
    conn = _conn()
    conn.execute(
        "INSERT INTO patient_records (patient_name, teacher_name, final_plan, doctor, visit_at, lineage_id) "
        "VALUES (?, ?, '测试施治方案', ?, ?, ?)",
        (patient_name, teacher_name, teacher_name, visit_at, lineage_id)
    )
    conn.commit()
    conn.close()


def _freeze_last_active_at(patient_name, value="2026-09-17"):
    """把 `last_active_at` 写成硬编码死值（复现病害现场）。"""
    conn = _conn()
    conn.execute("UPDATE patients SET last_active_at = ? WHERE name = ?", (value, patient_name))
    conn.commit()
    conn.close()


# ============ 验收 1：静默天数随时间正常推进，不虚增 ============
def test_visit_yesterday_gives_one_day_then_advances(client):
    """INSTR-03 §4 验收 1。

    「昨天有就诊」→ 静默天数 = 1；隔天再查 = 2。
    后半段用「把就诊时间往前挪一天」等价模拟隔天，避免依赖真实时钟。
    """
    import datetime as _dt
    now = _dt.datetime.now()

    _add_patient_record(STUDENT, TEACHER, (now - _dt.timedelta(days=1)).isoformat())
    got = database.get_last_interaction_at(STUDENT, TEACHER)
    assert got is not None
    assert (now - got).days == 1

    # 隔天：就诊时间再往前一天 → 天数必须跟着变成 2（证明它在「实时算」）
    conn = _conn()
    conn.execute("UPDATE patient_records SET visit_at = ? WHERE patient_name = ?",
                 ((now - _dt.timedelta(days=2)).isoformat(), STUDENT))
    conn.commit()
    conn.close()
    got2 = database.get_last_interaction_at(STUDENT, TEACHER)
    assert (now - got2).days == 2


def test_dead_last_active_at_does_not_affect_baseline(client):
    """**核心回归**：把 `last_active_at` 写成死值，静默基线**不受影响**。

    这是整条 P-301 的存在理由 —— 若基线改回读 `last_active_at`，本用例立刻失败。
    """
    import datetime as _dt
    now = _dt.datetime.now()
    _add_patient_record(STUDENT, TEACHER, (now - _dt.timedelta(days=1)).isoformat())
    _freeze_last_active_at(STUDENT, "2020-01-01")   # 极端死值：5 年多以前

    got = database.get_last_interaction_at(STUDENT, TEACHER)
    assert got is not None
    # 基线 = 就诊时间（1 天），**不是** last_active_at（2000+ 天）
    assert (now - got).days == 1


# ============ 验收 2：从未互动 → 走独立分支，不按沉默阈值计 ============
def test_never_interacted_returns_none(client):
    """INSTR-03 §4 验收 2（前半）。

    无病历的学生 → 基线返回 `None`（= 无可靠互动时间）→ 调用方走「从未互动」分支。
    绝不返回一个「假的今天」或「假的 200 天前」。
    """
    assert database.get_last_interaction_at(STUDENT, TEACHER) is None


def test_never_interacted_not_in_batch_map(client):
    """INSTR-03 §4 验收 2（后半）——批量口径。

    无记录的学生**不在字典里**（而不是给一个占位值）→ 门规可据此把它与
    「沉默 N 天」区分开，避免新学生被立刻建议归档。
    """
    import datetime as _dt
    now = _dt.datetime.now()
    other = "李四"      # init_db() 的另一个种子学生，同属李老师
    _add_patient_record(other, TEACHER, (now - _dt.timedelta(days=1)).isoformat())

    got = database.get_last_interactions_by_teacher(TEACHER)
    assert other in got
    assert STUDENT not in got        # 从未互动 → 不在字典里，**不是** 0 / None 占位


def test_visit_at_empty_string_is_treated_as_no_baseline(client):
    """`visit_at` 为空串（第 77 天之前的老数据）→ 视为无基准，不是「1970 年」。"""
    conn = _conn()
    conn.execute(
        "INSERT INTO patient_records (patient_name, teacher_name, final_plan, doctor, visit_at) "
        "VALUES (?, ?, '老记录', ?, '')",
        (STUDENT, TEACHER, TEACHER)
    )
    conn.commit()
    conn.close()
    assert database.get_last_interaction_at(STUDENT, TEACHER) is None


# ============ 验收 3：跨师门隔离 ============
def test_cross_lineage_isolation(client, monkeypatch):
    """INSTR-03 §4 验收 3：A 师门学生的互动**不影响** B 师门。

    构造（一师两门 —— 因为 `lineage_read_scope` 要求 `teacher_name` 非空**且该老师是本师门
    owner**，见 `lineage_service.teacher_in_lineage`）：同一个学生「张三」在**两个师门**各有
    一次就诊 —— 师门 A「昨天」、师门 B「200 天前」。flag on 时按 `lineage_id` 取值，
    **同一老师**下两个师门各自算，互不串。

    这与生产的一师一门形态不同，但隔离**判据**是同一个（`WHERE lineage_id = ?`）。
    """
    import datetime as _dt
    lin_a = lineage_service.default_lineage_id(TEACHER)
    lin_b = "lin-li-lao-shi-second"          # 第二个师门（同 owner = 李老师）

    conn = _conn()
    # 第二个师门（owner 仍是李老师 → 通过 teacher_in_lineage 校验）
    conn.execute("INSERT OR IGNORE INTO lineage (id, name, owner_teacher_name, description, status, "
                 "created_at, updated_at) VALUES (?, '李老师第二师门', ?, '', 'active', '2026-10-04', '2026-10-04')",
                 (lin_b, TEACHER))
    # 张三在两个师门都有归属行（成员判定用）
    conn.execute("INSERT OR REPLACE INTO patient_teachers "
                 "(patient_name, teacher_name, status, created_at, lineage_id) VALUES (?, ?, 'active', '2026-10-04', ?)",
                 (STUDENT, TEACHER, lin_b))
    conn.execute("UPDATE patient_teachers SET lineage_id = ? WHERE patient_name = ? AND teacher_name = ?",
                 (lin_a, STUDENT, TEACHER))
    conn.commit()
    conn.close()

    now = _dt.datetime.now()
    # 同名学生两条病历，靠 lineage_id 区分：A = 昨天，B = 200 天前
    _add_patient_record(STUDENT, TEACHER, (now - _dt.timedelta(days=1)).isoformat(), lineage_id=lin_a)
    _add_patient_record(STUDENT, TEACHER, (now - _dt.timedelta(days=200)).isoformat(), lineage_id=lin_b)

    monkeypatch.setenv("LINEAGE_ENABLED", "on")

    # 指定师门 A → 取 A 的那条 = 昨天（1 天）——**不被师门 B 的 200 天串到**
    got_a = database.get_last_interaction_at(STUDENT, TEACHER, lineage_id=lin_a)
    assert got_a is not None
    assert (now - got_a).days == 1

    # 指定师门 B → 取 B 的那条 = 200 天
    got_b = database.get_last_interaction_at(STUDENT, TEACHER, lineage_id=lin_b)
    assert got_b is not None
    assert (now - got_b).days == 200

    # 批量口径同样按师门隔离
    map_a = database.get_last_interactions_by_teacher(TEACHER, lineage_id=lin_a)
    assert (now - database.parse_interaction_at(map_a[STUDENT])).days == 1


# ============ 口径用例：解析与共用实现 ============
@pytest.mark.parametrize("raw", [
    "2026-09-23T15:30:00",       # sign_draft 落的 ISO 主格式
    "2026-09-23 15:30:00",       # 空格分隔（手工造数据）
    "2026-09-23",                # 纯日期（早期写法）
])
def test_parse_interaction_at_accepts_three_legacy_formats(raw):
    """三种历史写法都要能解析（与 `agent._parse_visit_at` 同口径）。"""
    parsed = database.parse_interaction_at(raw)
    assert parsed is not None
    assert (parsed.year, parsed.month, parsed.day) == (2026, 9, 23)


def test_parse_interaction_at_rejects_garbage():
    assert database.parse_interaction_at("") is None
    assert database.parse_interaction_at(None) is None
    assert database.parse_interaction_at("不是日期") is None


def test_recall_alerts_delegates_to_shared_implementation(client, monkeypatch):
    """INSTR-03 §2.2 要求 4：复诊提醒与静默基线**共用一份实现**。

    通过「把共用函数 monkeypatch 成哨兵」证明 `check_recall_alerts` 确实走它，
    而不是各写一份 SQL（防回归：有人把它改回内联聚合）。
    """
    import agent
    calls = []

    def _sentinel(teacher_name, lineage_id=None):
        calls.append((teacher_name, lineage_id))
        return {}

    monkeypatch.setattr(database, "get_last_interactions_by_teacher", _sentinel)
    agent.check_recall_alerts(TEACHER)
    assert calls == [(TEACHER, None)]


def test_parse_visit_at_wrapper_still_works():
    """`agent._parse_visit_at` 保留为薄委托，签名与语义不变（外部引用零改动）。"""
    import agent
    assert agent._parse_visit_at("2026-09-23") is not None
    assert agent._parse_visit_at("") is None
