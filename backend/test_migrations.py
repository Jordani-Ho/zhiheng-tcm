"""【Epic 1】Template 模型迁移守护测试

对齐：docs/epic1-template-design-v1.md §6.5（三类库执行步骤）/ §6.6（升级后校验清单）/ §14.1 A
- 全部用例都在 tmp_path 下自建独立 SQLite 文件，不碰 backend/zhiheng.db 与 backend/test.db；
- 直接调用 migrations_runner（与 main.py / conftest.py 同一条路径），另有一条真实 CLI 用例。
"""
import hashlib
import importlib.util
import json
import os
import sqlite3
import subprocess
import sys

import pytest
from alembic.config import Config
from alembic.script import ScriptDirectory

BACKEND_DIR = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, BACKEND_DIR)

import migrations_runner

# 【CTO 批复 2026-09-28 · design §5.5 修正句】head 不再硬编码：
# 原先两处断言写字面量 "0002_add_draft_template_refs"，任何新增 revision（如 0003）都会失败；
# 改为从 alembic 脚本目录动态取当前 head —— 只读脚本目录，不连库、不写 alembic_version。
# 用 backend/alembic.ini（其 script_location 由 %(here)s 锚定），故与 cwd 无关
# （从仓库根或 backend/ 跑结果一致）。
ALEMBIC_SCRIPT = ScriptDirectory.from_config(
    Config(os.path.join(BACKEND_DIR, "alembic.ini"))
)
ALEMBIC_HEAD = ALEMBIC_SCRIPT.get_current_head()

# 【Epic 2 施工步骤 2.6】降级中止后 alembic 可能停下的「中间态」同样改由上面这个动态来源给出：
# 语义与原先的字面量元组一字不差 —— 「允许停在 head 之前的任一 revision（今天展开即 0001 / 0002），
# 绝不允许退到 base」；原先写死的 ("0001_create_templates", "0002_add_draft_template_refs")
# 只是当时 head=0002 的展开结果，新增 revision 时不必再回来改测试（断言口径 / 强度均不变）。
# `iterate_revisions(head, "base")` 自上而下遍历整条链且**含 head 端点**（base 不是 revision，故不在链上），
# 因此这里剔掉 head 自身，只留中间态。
ALEMBIC_INTERMEDIATE_REVS = tuple(
    rev.revision
    for rev in ALEMBIC_SCRIPT.iterate_revisions(ALEMBIC_HEAD, "base")
    if rev.revision != ALEMBIC_HEAD
)

LEGACY_NAME = "施治模板（存量迁移）"
LEGACY_SOURCE = "plan_templates"

# 与 database.py:291-298 逐字一致的存量表结构（迁移只读它）
PLAN_TEMPLATES_DDL = """
CREATE TABLE IF NOT EXISTS plan_templates (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    teacher_name TEXT UNIQUE,
    content TEXT DEFAULT '',
    updated_at TEXT
)
"""


# 与 database.py init_db() 的 drafts 建表语句逐字一致（迁移 0002 只补两列，不改形状）
DRAFTS_DDL = """
CREATE TABLE IF NOT EXISTS drafts (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    transcript_id INTEGER,
    patient_name TEXT,
    teacher_name TEXT,
    content TEXT,
    signed INTEGER
)
"""


# 与 database.py init_db() 的 patient_records 建表语句逐字一致（迁移 0003 / 0004 只补列，不改形状；
# visit_at 由 init_db() 里那条 ADD COLUMN 兜底补，这里按建表基线造即可）
PATIENT_RECORDS_DDL = """
CREATE TABLE IF NOT EXISTS patient_records (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    patient_name TEXT,
    teacher_name TEXT,
    ai_draft TEXT,
    final_plan TEXT,
    doctor TEXT
)
"""


def _seed_legacy_db(db_path, rows=()):
    conn = sqlite3.connect(db_path)
    conn.execute(PLAN_TEMPLATES_DDL)
    for teacher_name, content, updated_at in rows:
        conn.execute(
            "INSERT INTO plan_templates (teacher_name, content, updated_at) VALUES (?, ?, ?)",
            (teacher_name, content, updated_at),
        )
    conn.commit()
    conn.close()


def _read(db_path, sql, params=()):
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    try:
        return conn.execute(sql, params).fetchall()
    finally:
        conn.close()


def _one(db_path, sql, params=()):
    rows = _read(db_path, sql, params)
    assert rows, "查询无结果：%s" % sql
    return rows[0]


def _names(rows):
    return [row["name"] for row in rows]


def _plan_templates_snapshot(db_path):
    return [
        (row["teacher_name"], row["content"], row["updated_at"])
        for row in _read(db_path, "SELECT teacher_name, content, updated_at FROM plan_templates ORDER BY id")
    ]


def test_upgrade_creates_table_and_indexes(tmp_path):
    """§6.6 第 1、2 条：版本表就位；表结构 + 3 个索引（含部分唯一索引）与设计一致。"""
    db = tmp_path / "m1.db"
    _seed_legacy_db(str(db), [("李老师", "疏肝理氣，健脾和胃。", "2026-09-01T10:00:00")])

    assert migrations_runner.run_upgrade(db_file=str(db)) is True

    ddl = _one(str(db), "SELECT sql FROM sqlite_master WHERE type='table' AND name='templates'")["sql"]
    assert "AUTOINCREMENT" in ddl.upper()  # 与存量业务表逐字一致：id INTEGER PRIMARY KEY AUTOINCREMENT
    for column in (
        "type",
        "lineage_id",
        "teacher_id",
        "name",
        "schema_json",
        "version",
        "parent_template_id",
        "status",
        "created_at",
        "updated_at",
    ):
        assert column in ddl, "缺少列 %s" % column
    assert "FOREIGN KEY" not in ddl.upper()  # 零外键（存量惯例）
    assert "CHECK" not in ddl.upper()  # 零 CHECK（存量惯例）

    indexes = _names(_read(str(db), "SELECT name FROM sqlite_master WHERE type='index' AND tbl_name='templates'"))
    assert set(indexes) >= {"uq_templates_active_one", "idx_templates_scope", "idx_templates_lineage"}

    partial = _one(str(db), "SELECT sql FROM sqlite_master WHERE name='uq_templates_active_one'")["sql"]
    assert "UNIQUE INDEX" in partial.upper()
    assert "WHERE status = 'active'" in partial

    assert _one(str(db), "SELECT version_num FROM alembic_version")["version_num"] == ALEMBIC_HEAD


def test_migration_backfills_plan_template(tmp_path):
    """§5.2 第 3 条 / §6.6 第 3、4 条：回填形状正确，且 plan_templates 逐行未动。"""
    db = tmp_path / "m2.db"
    _seed_legacy_db(
        str(db),
        [
            ("李老师", "疏肝理氣，健脾和胃。", "2026-09-01T10:00:00"),
            ("王老师", "   ", "2026-09-02T10:00:00"),  # 空白内容 = 没有模板，不迁移
        ],
    )
    before = _plan_templates_snapshot(str(db))

    assert migrations_runner.run_upgrade(db_file=str(db)) is True

    rows = _read(str(db), "SELECT * FROM templates")
    assert len(rows) == 1
    row = rows[0]
    assert row["type"] == "treatment"
    assert row["status"] == "active"
    assert row["version"] == 1
    assert row["name"] == LEGACY_NAME
    assert row["teacher_id"] == "李老师"
    assert row["lineage_id"] == ""
    assert row["parent_template_id"] is None
    assert row["created_at"] == "2026-09-01T10:00:00"
    assert row["updated_at"] == "2026-09-01T10:00:00"

    schema = json.loads(row["schema_json"])
    assert schema["format"] == "text"
    assert schema["content"] == "疏肝理氣，健脾和胃。"
    assert schema["placeholders"] == []
    assert schema["meta"]["legacy_source"] == LEGACY_SOURCE

    # 存量表毫发无损（行数 + 内容 + 时间戳）
    assert _plan_templates_snapshot(str(db)) == before


def test_migration_backfill_idempotent(tmp_path):
    """§6.6 第 6 条：重复 upgrade 为 no-op；downgrade → upgrade 重跑不产生重复行。"""
    db = tmp_path / "m3.db"
    _seed_legacy_db(str(db), [("李老师", "原模板內容", "2026-09-01T10:00:00")])

    assert migrations_runner.run_upgrade(db_file=str(db)) is True
    assert migrations_runner.run_upgrade(db_file=str(db)) is True  # 已升级库再升级 = no-op
    assert _one(str(db), "SELECT COUNT(*) AS c FROM templates")["c"] == 1

    migrations_runner.run_downgrade("base", db_file=str(db))
    assert _read(str(db), "SELECT name FROM sqlite_master WHERE type='table' AND name='templates'") == []

    assert migrations_runner.run_upgrade(db_file=str(db)) is True
    rows = _read(str(db), "SELECT id, schema_json FROM templates")
    assert len(rows) == 1
    assert json.loads(rows[0]["schema_json"])["content"] == "原模板內容"


def test_active_unique_partial_index_enforced(tmp_path):
    """§1.3：同一 scope 最多一条 active（硬约束）；draft / archived 不受限。"""
    db = tmp_path / "m4.db"
    _seed_legacy_db(str(db))
    assert migrations_runner.run_upgrade(db_file=str(db)) is True

    conn = sqlite3.connect(str(db))
    try:
        conn.execute("INSERT INTO templates (type, teacher_id, status) VALUES ('record', '王老师', 'active')")
        conn.commit()
        with pytest.raises(sqlite3.IntegrityError):
            conn.execute("INSERT INTO templates (type, teacher_id, status) VALUES ('record', '王老师', 'active')")
        conn.rollback()

        # 部分索引只约束 active：同 scope 的多条 draft / archived 合法
        for status in ("draft", "draft", "archived", "archived"):
            conn.execute(
                "INSERT INTO templates (type, teacher_id, status) VALUES ('record', '王老师', ?)", (status,)
            )
        conn.commit()
        counts = {
            row[0]: row[1]
            for row in conn.execute(
                "SELECT status, COUNT(*) FROM templates WHERE teacher_id='王老师' GROUP BY status"
            )
        }
        assert counts == {"active": 1, "draft": 2, "archived": 2}
    finally:
        conn.close()


def test_downgrade_removes_templates_but_keeps_plan_templates(tmp_path):
    """§6.4 / §6.6 第 6 条：回退后 templates 与索引消失，plan_templates 原数据仍在，且可重跑。"""
    db = tmp_path / "m5.db"
    _seed_legacy_db(str(db), [("李老师", "存量內容", "2026-09-01T10:00:00")])
    before = _plan_templates_snapshot(str(db))
    assert migrations_runner.run_upgrade(db_file=str(db)) is True

    migrations_runner.run_downgrade("base", db_file=str(db))

    tables = _names(_read(str(db), "SELECT name FROM sqlite_master WHERE type='table'"))
    assert "templates" not in tables
    assert _read(str(db), "SELECT name FROM sqlite_master WHERE type='index' AND tbl_name='templates'") == []
    assert _plan_templates_snapshot(str(db)) == before
    # alembic_version 保留空表（回退到 base 即无版本行），所以还能再 upgrade head
    assert _read(str(db), "SELECT version_num FROM alembic_version") == []
    # downgrade 可重跑：已在 base 再降一次仍是 no-op
    migrations_runner.run_downgrade("base", db_file=str(db))
    remaining = {name for name in _names(_read(str(db), "SELECT name FROM sqlite_master WHERE type='table'"))}
    remaining.discard("sqlite_sequence")  # SQLite 内部表（AUTOINCREMENT 附属），非业务表
    assert remaining == {"alembic_version", "plan_templates"}


def test_downgrade_safety_gate_blocks_when_teacher_created_template(tmp_path):
    """§6.4 第 1 条：老师已新建模板时拒绝降级（不静默吃掉数据），且整体回滚。"""
    db = tmp_path / "m6.db"
    _seed_legacy_db(str(db), [("李老师", "存量內容", "2026-09-01T10:00:00")])
    assert migrations_runner.run_upgrade(db_file=str(db)) is True

    conn = sqlite3.connect(str(db))
    try:
        conn.execute(
            "INSERT INTO templates (type, teacher_id, name, status) VALUES ('record', '李老师', '病歷模板', 'draft')"
        )
        conn.commit()
    finally:
        conn.close()

    with pytest.raises(Exception) as excinfo:
        migrations_runner.run_downgrade("base", db_file=str(db))
    assert "downgrade 已中止" in str(excinfo.value)

    # 安全闸中止后：模板表与两行数据完好（未执行任何 DROP），版本号只停在 head 之前的中间态
    # （即 ALEMBIC_INTERMEDIATE_REVS；SQLite 方言下 alembic_version 每步迁移后即落定，
    #  故多 revision 顺序回退时可能停在中间态；
    #  关键不变式是「老师配好的模板没被吃掉、也不许退到 base」——这是本用例真正要守的东西）
    assert _one(str(db), "SELECT COUNT(*) AS c FROM templates")["c"] == 2
    assert _one(str(db), "SELECT version_num FROM alembic_version")["version_num"] in (
        ALEMBIC_INTERMEDIATE_REVS
    )
    assert _one(str(db), "SELECT COUNT(*) AS c FROM templates WHERE type='record'")["c"] == 1

    # 清掉老师新建的行后降级通过 → 证明闸门是唯一阻塞点
    conn = sqlite3.connect(str(db))
    try:
        conn.execute("DELETE FROM templates WHERE type = 'record'")
        conn.commit()
    finally:
        conn.close()
    migrations_runner.run_downgrade("base", db_file=str(db))
    assert "templates" not in _names(_read(str(db), "SELECT name FROM sqlite_master WHERE type='table'"))


def test_init_db_does_not_create_templates(tmp_path, monkeypatch):
    """§1.1 / §7：DDL 唯一真相源是迁移脚本 —— init_db() 不得再建一份 templates。"""
    import database

    db_file = tmp_path / "init_only.db"
    monkeypatch.setattr(database, "DB_PATH", str(db_file))
    database.init_db()

    tables = _names(_read(str(db_file), "SELECT name FROM sqlite_master WHERE type='table'"))
    assert "plan_templates" in tables  # 存量表照旧
    assert "templates" not in tables  # 新表只由迁移创建


def test_cli_upgrade_reads_zhieng_db_env(tmp_path):
    """§6.1：命令行 alembic 也从 ZHIENG_DB 解析库路径（运维手册第 ② / ③ 步可照抄）。"""
    db = tmp_path / "cli.db"
    _seed_legacy_db(str(db), [("李老师", "命令行回填內容", "2026-09-01T10:00:00")])

    alembic_exe = os.path.join(os.path.dirname(sys.executable), "alembic.exe")
    env = dict(os.environ, ZHIENG_DB=str(db))
    if os.path.exists(alembic_exe):
        cmd = [alembic_exe, "upgrade", "head"]
    else:  # 兜底：不用 console script 也能跑同一个入口
        cmd = [sys.executable, "-c", "from alembic.config import main; main()", "upgrade", "head"]
    # 【CTO 2026-09-28 裁决② · 1 行卫生修复】显式钉住子进程输出的解码口径：alembic 的
    # print 是 UTF-8（含繁体中文），`text=True` 单独用会按 locale（本机 GBK）解码 → 告警 / 乱码。
    # 只加解码参数，**断言一字未改**（本用例恒 pass，修的是测量卫生）。
    proc = subprocess.run(cmd, cwd=BACKEND_DIR, env=env, capture_output=True,
                          text=True, encoding="utf-8", errors="replace")

    assert proc.returncode == 0, proc.stdout + proc.stderr
    row = _one(str(db), "SELECT schema_json, name FROM templates")
    assert row["name"] == LEGACY_NAME
    assert json.loads(row["schema_json"])["content"] == "命令行回填內容"


def test_migration_0002_adds_draft_template_refs(tmp_path):
    """§12.1：`drafts` 补 `template_id` / `template_version`（老行落 0），可重跑，回退不删列。"""
    db = tmp_path / "m7.db"
    conn = sqlite3.connect(str(db))
    conn.execute(DRAFTS_DDL)
    conn.execute(
        "INSERT INTO drafts (transcript_id, patient_name, teacher_name, content, signed) "
        "VALUES (0, '张三', '李老师', '老草案', 0)"
    )
    conn.commit()
    conn.close()

    assert migrations_runner.run_upgrade(db_file=str(db)) is True

    columns = _names(_read(str(db), "PRAGMA table_info('drafts')"))
    assert {"template_id", "template_version"} <= set(columns)
    old_row = _one(str(db), "SELECT * FROM drafts WHERE patient_name = '张三'")
    assert old_row["template_id"] == 0 and old_row["template_version"] == 0   # 老数据 = 未记录
    assert old_row["content"] == "老草案"                                    # 老行内容一字不动
    assert _one(str(db), "SELECT version_num FROM alembic_version")["version_num"] == ALEMBIC_HEAD

    # 可重跑：已在 head 再 upgrade 一次仍是 no-op（不重复加列、不报错）
    assert migrations_runner.run_upgrade(db_file=str(db)) is True
    assert _names(_read(str(db), "PRAGMA table_info('drafts')")).count("template_id") == 1

    # downgrade base：按 §12.1 默认不删列（删列会丢「依哪个模板哪个版本生成」的溯源信息）
    migrations_runner.run_downgrade("base", db_file=str(db))
    assert {"template_id", "template_version"} <= set(_names(_read(str(db), "PRAGMA table_info('drafts')")))


# ===========================================================================
# 【Epic 4 step 4.1】迁移 0005 守护测试：lineage 表 + 12 张必须表补 lineage_id + 默认师门种子 + 回填
# 对齐：docs/epic4-lineage-design-v1.md §2.1（lineage DDL = 迁移即唯一真相源）/ §2.3（必须 12 张、
#       明确不加 plan_templates 等）/ §2.4（`''` = 未归属，禁 COALESCE 兜底）/ §2.5（idx_patient_teachers_lineage）
#       / §6.1（upgrade 七步）/ §6.2（真机回填基线 1/10/5/4/1）/ §6.3（downgrade 只回收结构、不删业务列）
#       / §8 ① ② 组；CTO 2026-09-29「step 4.1 放行」五条约束（先红后绿、计数校验、downgrade 新口径…）。
# 纪律：全部用例都在 tmp_path 下自建独立 SQLite 文件，**绝不碰** backend/zhiheng.db 与 backend/test.db。
# ===========================================================================

# §2.3「必须」补 lineage_id 的 12 张表（`agent_stage_log` 由迁移 0003 在同一趟 upgrade 内建出；
# 本组基线夹具按「已跑到 0004」造库，与 §6.5 真机升级窗口一致）
LINEAGE_ID_TABLES = (
    "drafts",
    "patient_records",
    "complaints",
    "appointments",
    "prescriptions",
    "homework",
    "transcriptions",
    "record_tags",
    "agent_tasks",
    "agent_action_log",
    "agent_stage_log",
    "patient_teachers",
)

# §2.3「明确不加 lineage_id 列」的表（A1 裁决：plan_templates 不加 —— Epic 1 兼容镜像）
NO_LINEAGE_ID_TABLES = (
    "plan_templates",
    "patients",
    "patient_profiles",
    "teachers",
)

# 0005 **不得触碰**的表（裁决 ③-A：`agent_stage_state` 已有 lineage_id 列且恒 ''，结构一字不动；
# `agent_stage_config` 属老师维度的阈值配置，不师门化）
NO_LINEAGE_TOUCH_TABLES = NO_LINEAGE_ID_TABLES + ("agent_stage_state", "agent_stage_config")

MIGRATION_0005_PATH = os.path.join(BACKEND_DIR, "alembic", "versions", "0005_add_lineage.py")

# 真机 §6.2 基线（只读实测 2026-09-29）：整表行数（= 基线签名）+ 回填预期行数
REAL_DB_SIGNATURE = (
    ("teachers", 1),
    ("patient_teachers", 10),
    ("templates", 5),
    ("patient_records", 4),
    ("drafts", 1),
)
REAL_DB_EXPECTED_FILL = (
    ("patient_teachers", 10),
    ("templates", 5),
    ("patient_records", 4),
    ("drafts", 1),
)
REAL_TEACHER = "李老师"
REAL_LINEAGE_ID = "lin-ua8739bc7"  # 'lin-' + sha1('李老师')[:8]（真机 1 位老师 → 冻结值）
REAL_LINEAGE_NAME = "李老师師門"
PREVIOUS_REVISION = "0004_add_patient_record_template_refs"  # 0005 的上一版（基线夹具停在 / downgrade 回到这里）

# 与 database.py init_db() 逐字一致的建表语句（0005 只补列 / 只回填，不改这些表的形状）
LINEAGE_BASE_DDL = (
    """
CREATE TABLE IF NOT EXISTS teachers (
    name TEXT PRIMARY KEY,
    description TEXT DEFAULT '',
    status TEXT DEFAULT 'active',
    last_active_at TEXT,
    complaint_count INTEGER DEFAULT 0,
    created_at TEXT
)
""",
    """
CREATE TABLE IF NOT EXISTS patient_teachers (
    patient_name TEXT,
    teacher_name TEXT,
    status TEXT DEFAULT 'active',
    created_at TEXT,
    PRIMARY KEY (patient_name, teacher_name)
)
""",
    """
CREATE TABLE IF NOT EXISTS homework (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    patient_name TEXT,
    teacher_name TEXT,
    task TEXT,
    detail TEXT,
    status TEXT DEFAULT 'pending',
    created_at TEXT
)
""",
    """
CREATE TABLE IF NOT EXISTS transcriptions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    patient_name TEXT,
    teacher_name TEXT,
    content TEXT,
    data_type TEXT,
    processed INTEGER DEFAULT 0
)
""",
    """
CREATE TABLE IF NOT EXISTS drafts (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    transcript_id INTEGER,
    patient_name TEXT,
    teacher_name TEXT,
    content TEXT,
    signed INTEGER
)
""",
    """
CREATE TABLE IF NOT EXISTS patient_records (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    patient_name TEXT,
    teacher_name TEXT,
    ai_draft TEXT,
    final_plan TEXT,
    doctor TEXT,
    visit_at TEXT
)
""",
    """
CREATE TABLE IF NOT EXISTS appointments (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    patient_name TEXT,
    teacher_name TEXT,
    initiator TEXT,
    scheduled_date TEXT,
    scheduled_time TEXT,
    reason TEXT,
    status TEXT DEFAULT 'pending',
    created_at TEXT,
    confirmed_at TEXT,
    is_remote INTEGER DEFAULT 0
)
""",
    """
CREATE TABLE IF NOT EXISTS record_tags (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    record_id INTEGER,
    teacher_name TEXT,
    tag_type TEXT,
    tag_value TEXT,
    created_at TEXT
)
""",
    """
CREATE TABLE IF NOT EXISTS complaints (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    teacher_name TEXT,
    patient_name TEXT,
    content TEXT,
    created_at TEXT,
    status TEXT DEFAULT 'pending',
    resolved_at TEXT
)
""",
    """
CREATE TABLE IF NOT EXISTS prescriptions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    teacher_name TEXT,
    patient_name TEXT DEFAULT '',
    items_json TEXT,
    note TEXT DEFAULT '',
    created_at TEXT,
    is_remote INTEGER DEFAULT 0
)
""",
    """
CREATE TABLE IF NOT EXISTS agent_tasks (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    teacher_name TEXT,
    task_type TEXT,
    category TEXT,
    title TEXT,
    content TEXT,
    action_data TEXT,
    status TEXT DEFAULT 'pending',
    created_at TEXT,
    resolved_at TEXT
)
""",
    """
CREATE TABLE IF NOT EXISTS agent_action_log (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    teacher_name TEXT,
    task_id INTEGER,
    action TEXT,
    detail TEXT,
    created_at TEXT
)
""",
)


def _exec_script(db_path, script):
    """按句执行建表 / 造数脚本（等价于 `sqlite3 < file.sql`；本机无 sqlite3 CLI，故走 Python，§6.4 同款判据）。"""
    conn = sqlite3.connect(db_path)
    try:
        conn.executescript(script)
        conn.commit()
    finally:
        conn.close()


def _count(db_path, table, where=""):
    sql = "SELECT COUNT(*) AS c FROM %s%s" % (table, (" WHERE " + where) if where else "")
    return _one(db_path, sql)["c"]


def _filled_counts(db_path, tables=None):
    """指定表里 `lineage_id <> ''` 的行数（= 实回填行数）；不存在的表直接跳过。

    默认 = §2.3「必须」的 12 张（**不含** `templates` —— 它自带 `lineage_id`，只回填不补列）。
    """
    present = _tables(db_path)
    return {
        t: _count(db_path, t, "lineage_id <> ''")
        for t in (tables or LINEAGE_ID_TABLES)
        if t in present
    }


def _tables(db_path):
    return set(_names(_read(db_path, "SELECT name FROM sqlite_master WHERE type='table'")))


def _indexes(db_path):
    return set(_names(_read(db_path, "SELECT name FROM sqlite_master WHERE type='index'")))


def _columns_of(db_path, table):
    return [row["name"] for row in _read(db_path, "PRAGMA table_info('%s')" % table)]


def _load_migration_0005():
    """按文件路径载入迁移模块（alembic 也是按路径载入的），用于核对 id 契约与红线常量。"""
    assert os.path.exists(MIGRATION_0005_PATH), "迁移 0005 尚未创建：%s" % MIGRATION_0005_PATH
    spec = importlib.util.spec_from_file_location("migration_0005_add_lineage", MIGRATION_0005_PATH)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _lineage_row(db_path):
    rows = _read(db_path, "SELECT * FROM lineage")
    assert len(rows) == 1, "lineage 应恰好 1 行（真机 1 位老师），实测 %d 行" % len(rows)
    return rows[0]


def _survivors(row):
    """只取「幂等重跑必须一字不动」的字段（时间戳每次种子按当时时刻落，属预期变化）。"""
    return {key: row[key] for key in ("id", "name", "owner_teacher_name", "description", "status")}


def _seed_baseline_db(db_path, orphan_rows=0):
    """造一份与真机 §6.2 基线同形的库（teachers 1 / patient_teachers 10 / templates 5 / records 4 / drafts 1）。

    两段式：① 存量表 + 存量行（跑到 0004；0001 会把 plan_templates 那 1 行回填成 templates 第 1 行）；
    ② 补 4 行 templates（凑满 §6.2 的 5 行）→ 停在 0004，调用方随后 `run_upgrade()` 就只差 0005。

    orphan_rows：塞几个「老师不在 teachers 表」的 patient_teachers 行（回填必须留 `''`，不得兜底进默认师门）。
    """
    _exec_script(db_path, ";\n".join(LINEAGE_BASE_DDL) + ";")
    _exec_script(db_path, PLAN_TEMPLATES_DDL + ";")

    conn = sqlite3.connect(db_path)
    try:
        conn.execute(
            "INSERT INTO teachers (name, description, status, last_active_at, complaint_count, created_at) "
            "VALUES (?, '', 'active', '2026-09-01T00:00:00', 0, '2026-09-01T00:00:00')",
            (REAL_TEACHER,),
        )
        for i in range(10 - orphan_rows):
            conn.execute(
                "INSERT INTO patient_teachers (patient_name, teacher_name, status, created_at) "
                "VALUES (?, ?, 'active', '2026-09-01T00:00:00')",
                ("患者%02d" % (i + 1), REAL_TEACHER),
            )
        for i in range(orphan_rows):
            conn.execute(
                "INSERT INTO patient_teachers (patient_name, teacher_name, status, created_at) "
                "VALUES (?, ?, 'active', '2026-09-01T00:00:00')",
                ("孤儿%02d" % (i + 1), "無此老师"),
            )
        for i in range(4):
            conn.execute(
                "INSERT INTO patient_records (patient_name, teacher_name, ai_draft, final_plan, doctor, visit_at) "
                "VALUES (?, ?, 'AI 原稿', '老师定稿', ?, '2026-09-0%dT10:00:00')" % (i + 2),
                ("患者%02d" % (i + 1), REAL_TEACHER, REAL_TEACHER),
            )
        conn.execute(
            "INSERT INTO drafts (transcript_id, patient_name, teacher_name, content, signed) "
            "VALUES (0, '患者01', ?, '老草案', 0)",
            (REAL_TEACHER,),
        )
        conn.execute(
            "INSERT INTO plan_templates (teacher_name, content, updated_at) "
            "VALUES (?, '疏肝理氣，健脾和胃。', '2026-09-01T10:00:00')",
            (REAL_TEACHER,),
        )
        for i in range(5):
            conn.execute(
                "INSERT INTO agent_tasks (teacher_name, task_type, category, title, content, action_data, "
                "status, created_at, resolved_at) "
                "VALUES (?, 'request', 'student', '请示%d', '内容', '{}', 'pending', "
                "'2026-09-01T00:00:00', '')" % (i + 1),
                (REAL_TEACHER,),
            )
        conn.execute(
            "INSERT INTO complaints (teacher_name, patient_name, content, created_at, status, resolved_at) "
            "VALUES (?, '患者01', '十问歌摘要', '2026-09-01T00:00:00', 'pending', '')",
            (REAL_TEACHER,),
        )
        conn.execute(
            "INSERT INTO appointments (patient_name, teacher_name, initiator, scheduled_date, scheduled_time, "
            "reason, status, created_at, confirmed_at, is_remote) "
            "VALUES ('患者01', ?, 'patient', '2026-09-10', '09:00', '复诊', 'pending', "
            "'2026-09-01T00:00:00', '', 0)",
            (REAL_TEACHER,),
        )
        conn.execute(
            "INSERT INTO prescriptions (teacher_name, patient_name, items_json, note, created_at, is_remote) "
            "VALUES (?, '患者01', '[]', '', '2026-09-01T00:00:00', 0)",
            (REAL_TEACHER,),
        )
        conn.execute(
            "INSERT INTO homework (patient_name, teacher_name, task, detail, status, created_at) "
            "VALUES ('患者01', ?, '每日泡脚', '20 分钟', 'pending', '2026-09-01T00:00:00')",
            (REAL_TEACHER,),
        )
        conn.execute(
            "INSERT INTO transcriptions (patient_name, teacher_name, content, data_type, processed) "
            "VALUES ('患者01', ?, '转述内容', 'text', 0)",
            (REAL_TEACHER,),
        )
        conn.execute(
            "INSERT INTO record_tags (record_id, teacher_name, tag_type, tag_value, created_at) "
            "VALUES (1, ?, 'symptom', '失眠', '2026-09-01T00:00:00')",
            (REAL_TEACHER,),
        )
        conn.commit()
    finally:
        conn.close()

    assert migrations_runner.run_upgrade(PREVIOUS_REVISION, db_file=db_path) is True

    conn = sqlite3.connect(db_path)
    try:
        for tpl_type, status in (("record", "active"), ("inquiry", "active"),
                                 ("prescription", "active"), ("record", "archived")):
            conn.execute(
                "INSERT INTO templates (type, lineage_id, teacher_id, name, schema_json, version, "
                "parent_template_id, status, created_at, updated_at) "
                "VALUES (?, '', ?, '夹具模板', '{}', 1, NULL, ?, '2026-09-01T00:00:00', '2026-09-01T00:00:00')",
                (tpl_type, REAL_TEACHER, status),
            )
        conn.commit()
    finally:
        conn.close()

    # 基线签名硬前置：夹具一旦漂移就当场失败，避免 Tier-2（真机基线）断言静默失效
    for table, expected in REAL_DB_SIGNATURE:
        actual = _count(db_path, table)
        assert actual == expected, "基线夹具失真：%s 应 %d 行，实测 %d 行" % (table, expected, actual)
    return db_path


def _seed_small_db(db_path, orphan_rows=0):
    """小夹具（**故意不匹配真机基线签名**）：只建部分业务表，用来验「表不存在 → 跳过」与孤儿行分支。

    只建 teachers / patient_teachers / drafts 三张表 —— 其余表**故意缺失**（`patient_records` /
    `templates` / `agent_stage_log` …），用来覆盖 0005 的「表不存在 → 探测后跳过、不报错」分支；
    0001 仍会在 upgrade 时建出 `templates`。
    """
    subset = (LINEAGE_BASE_DDL[0], LINEAGE_BASE_DDL[1], LINEAGE_BASE_DDL[4])
    _exec_script(db_path, ";\n".join(subset) + ";")
    conn = sqlite3.connect(db_path)
    try:
        conn.execute(
            "INSERT INTO teachers (name, status, created_at) VALUES (?, 'active', '2026-09-01T00:00:00')",
            (REAL_TEACHER,),
        )
        for i in range(2 - orphan_rows):
            conn.execute(
                "INSERT INTO patient_teachers (patient_name, teacher_name, status, created_at) "
                "VALUES (?, ?, 'active', '2026-09-01T00:00:00')",
                ("小患者%02d" % (i + 1), REAL_TEACHER),
            )
        for i in range(orphan_rows):
            conn.execute(
                "INSERT INTO patient_teachers (patient_name, teacher_name, status, created_at) "
                "VALUES (?, ?, 'active', '2026-09-01T00:00:00')",
                ("孤儿%02d" % (i + 1), "無此老师"),
            )
        conn.execute(
            "INSERT INTO drafts (transcript_id, patient_name, teacher_name, content, signed) "
            "VALUES (0, '小患者01', ?, '草案', 0)",
            (REAL_TEACHER,),
        )
        conn.commit()
    finally:
        conn.close()
    return db_path


def test_0005_slug_and_lineage_id_contract():
    """§0.1 / §2.1：`id = 'lin-' + slugify(name)`；非 ASCII → `-`、折叠、去首尾；空结果回落 `u<sha1(名)[:8]>`。"""
    module = _load_migration_0005()

    assert module.slugify("Li") == "li"
    assert module.slugify("Li 老師") == "li"
    assert module.slugify("Dr. Li 老師") == "dr-li"
    assert module.slugify("--A--B--") == "a-b"
    assert module.slugify("A_B.C") == "a-b-c"
    fallback = "u" + hashlib.sha1(REAL_TEACHER.encode("utf-8")).hexdigest()[:8]  # 独立复算，冻结公式
    assert module.slugify(REAL_TEACHER) == fallback
    assert module.lineage_id_for(REAL_TEACHER) == REAL_LINEAGE_ID
    assert module.lineage_name_for(REAL_TEACHER) == REAL_LINEAGE_NAME
    assert module.lineage_id_for(REAL_TEACHER) == module.lineage_id_for(REAL_TEACHER)  # 稳定可复现


def test_0005_source_keeps_epic4_redlines():
    """§2.3 / §2.4 / §6.3 + 裁决③④：不加不该加的表、无 COALESCE 兜底、downgrade 不删列、不动阶段表。"""
    module = _load_migration_0005()
    source = open(MIGRATION_0005_PATH, encoding="utf-8").read()

    touched = {table for table, _column in module.ADD_COLUMNS}
    touched |= {table for table, _owner in module.BACKFILL_SOURCES}
    assert set(NO_LINEAGE_TOUCH_TABLES) & touched == set()  # plan_templates（A1）/ agent_stage_* （裁决③）…
    assert "COALESCE(lineage_id" not in source  # §2.4 纪律 3
    assert "DROP COLUMN" not in source  # 裁决④：只回收结构，不删业务列
    assert "ALTER TABLE agent_stage_state" not in source  # 裁决③-A：阶段表结构不动
    assert set(LINEAGE_ID_TABLES) - touched == set()  # §2.3「必须」12 张一张不漏


def test_0005_upgrade_adds_table_columns_and_backfill(tmp_path):
    """§8 组①：真机同形库 upgrade → lineage 表 + 2 个索引 + 12 张表补列 + 回填 10/5/4/1。"""
    db = str(tmp_path / "m9.db")
    _seed_baseline_db(db)

    assert migrations_runner.run_upgrade(db_file=db) is True

    # ① lineage 表（§2.1：TEXT 主键、零 FK/CHECK，与 templates.lineage_id 同构）
    assert "lineage" in _tables(db)
    ddl = _one(db, "SELECT sql FROM sqlite_master WHERE type='table' AND name='lineage'")["sql"]
    assert "id                  TEXT PRIMARY KEY" in ddl
    for column in ("name", "owner_teacher_name", "description", "status", "created_at", "updated_at"):
        assert column in ddl
    assert "FOREIGN KEY" not in ddl.upper() and "CHECK" not in ddl.upper()
    assert {"idx_lineage_owner", "idx_patient_teachers_lineage"} <= _indexes(db)

    # ② 默认师门种子：真机 1 位老师 → 1 行；id = 'lin-' + slugify(name)（计算得出，非常量）
    row = _lineage_row(db)
    assert row["id"] == REAL_LINEAGE_ID
    assert row["name"] == REAL_LINEAGE_NAME
    assert row["owner_teacher_name"] == REAL_TEACHER
    assert row["description"] == "" and row["status"] == "active"
    assert row["created_at"] and row["updated_at"]

    # ③ §2.3：必须 12 张都有 lineage_id；明确不加的表没有
    for table in LINEAGE_ID_TABLES:
        assert "lineage_id" in _columns_of(db, table), "%s 缺 lineage_id" % table
    for table in NO_LINEAGE_ID_TABLES:
        if table in _tables(db):
            assert "lineage_id" not in _columns_of(db, table), "%s 不该有 lineage_id" % table
    # A1 裁决：plan_templates 是 Epic 1 兼容镜像 —— 形状与内容一字未动
    assert _columns_of(db, "plan_templates") == ["id", "teacher_name", "content", "updated_at"]
    assert _count(db, "plan_templates") == 1

    # ④ §6.2 回填计数（真机预期 10/5/4/1；其余表按实表有行才回填）
    filled = _filled_counts(db)
    assert filled["patient_teachers"] == 10
    assert _count(db, "templates", "lineage_id <> ''") == 5  # templates 自带列，只回填
    assert filled["patient_records"] == 4
    assert filled["drafts"] == 1
    for table in ("complaints", "appointments", "prescriptions", "homework", "transcriptions", "record_tags"):
        assert filled[table] == 1, "%s 回填 %d 行" % (table, filled[table])
    assert filled["agent_tasks"] == 5
    assert filled["agent_action_log"] == 0 and filled["agent_stage_log"] == 0
    assert {r["lineage_id"] for r in _read(db, "SELECT lineage_id FROM patient_teachers")} == {REAL_LINEAGE_ID}

    # ⑤ 裁决③-A：阶段表结构不动（PK 仍 teacher_name），其 lineage_id 恒 ''
    pk = [r["name"] for r in _read(db, "PRAGMA table_info('agent_stage_state')") if r["pk"]]
    assert pk == ["teacher_name"]
    assert _count(db, "agent_stage_state", "lineage_id <> ''") == 0

    assert _one(db, "SELECT version_num FROM alembic_version")["version_num"] == ALEMBIC_HEAD


def test_0005_upgrade_is_idempotent(tmp_path):
    """§6.1 / §8 组①：head 再 upgrade = no-op；downgrade→upgrade 重跑本 revision 亦不重复补列 / 种子 / 回填。"""
    db = str(tmp_path / "m10.db")
    _seed_baseline_db(db)
    assert migrations_runner.run_upgrade(db_file=db) is True
    first = _filled_counts(db)
    lineage_first = _survivors(_lineage_row(db))

    assert migrations_runner.run_upgrade(db_file=db) is True  # 已在 head：no-op
    assert _filled_counts(db) == first
    assert _count(db, "lineage") == 1

    # 真正重跑本 revision：回 0004（业务列按裁决④保留）→ 再 upgrade
    migrations_runner.run_downgrade(PREVIOUS_REVISION, db_file=db)
    assert "lineage" not in _tables(db)
    assert migrations_runner.run_upgrade(db_file=db) is True
    assert _filled_counts(db) == first  # 已有值的行不被重算，候选为空 → 回填 0 行
    assert _count(db, "lineage") == 1  # 种子不重复（幂等）
    # 师门表的字段口径稳定（id 由 slugify 复现；created_at / updated_at 重跑时按新时间落，属预期）
    assert _survivors(_lineage_row(db)) == lineage_first
    assert _columns_of(db, "patient_teachers").count("lineage_id") == 1


def test_0005_orphan_rows_stay_unassigned(tmp_path):
    """§2.4 纪律 2 / §6.2：找不到映射的行留 `''`（未归属），不得兜底进默认师门；表不存在则跳过。"""
    db = str(tmp_path / "m11.db")
    _seed_small_db(db, orphan_rows=1)  # 非真机签名：2 行归属其中 1 行是孤儿；无 templates / patient_records

    assert migrations_runner.run_upgrade(db_file=db) is True

    filled = _filled_counts(db, ("patient_teachers", "drafts"))
    assert filled["patient_teachers"] == 1
    orphan = _one(db, "SELECT lineage_id FROM patient_teachers WHERE teacher_name = '無此老师'")
    assert orphan["lineage_id"] == ""  # 留 `''`（不 COALESCE 成默认师门）
    owned = _one(db, "SELECT lineage_id FROM patient_teachers WHERE teacher_name = ?", (REAL_TEACHER,))
    assert owned["lineage_id"] == REAL_LINEAGE_ID
    assert filled["drafts"] == 1
    assert _lineage_row(db)["id"] == REAL_LINEAGE_ID
    # 表不存在 → 0005 探测后跳过（不建表、不报错）
    assert "patient_records" not in _tables(db)


def test_0005_backfill_count_mismatch_aborts_revision(tmp_path, capsys):
    """CTO「回填计数校验」：真机基线签名命中但实填 ≠ 预期（10/5/4/1）→ 抛错 + 整 revision 回滚。"""
    db = str(tmp_path / "m12.db")
    _seed_baseline_db(db, orphan_rows=1)  # 签名命中（patient_teachers 共 10 行），但其中 1 行无映射 → 实填 9

    assert migrations_runner.run_upgrade(db_file=db) is False
    out = capsys.readouterr().out
    assert "回填计数校验失败" in out
    assert "patient_teachers" in out

    # 失败后的现场（step 4.1 实测）：`alembic_version` 停在 0004、业务数据零变更；
    # 但 SQLAlchemy / pysqlite 默认隔离级别下 **DDL 不在事务内**，空的 `lineage` 表与 `lineage_id` 列会残留。
    # 关键不变式（本用例真正要守的）：**版本号不前进、业务数据零变更、修好触发条件后重跑即收敛**。
    assert _one(db, "SELECT version_num FROM alembic_version")["version_num"] == PREVIOUS_REVISION
    assert _filled_counts(db)["patient_teachers"] == 0  # 没有任何一行被写上 lineage_id
    assert _count(db, "templates", "lineage_id <> ''") == 0
    assert _count(db, "lineage") == 0  # 种子未落地
    assert "lineage_id" in _columns_of(db, "patient_teachers")  # DDL 残留（pysqlite 不对 DDL 开事务）

    # 修好触发条件（孤儿行的老师改成真实老师）→ 重跑 0005：幂等探测跳过已有表 / 列，随后全部校验通过
    conn = sqlite3.connect(db)
    try:
        conn.execute(
            "UPDATE patient_teachers SET teacher_name = ? WHERE teacher_name = '無此老师'", (REAL_TEACHER,)
        )
        conn.commit()
    finally:
        conn.close()

    assert migrations_runner.run_upgrade(db_file=db) is True
    assert _one(db, "SELECT version_num FROM alembic_version")["version_num"] == ALEMBIC_HEAD
    assert _count(db, "lineage") == 1
    assert _filled_counts(db)["patient_teachers"] == 10  # 真机基线 10 行全部归属
    assert _columns_of(db, "patient_teachers").count("lineage_id") == 1  # 补列未重复


def test_0005_downgrade_keeps_business_columns(tmp_path):
    """§6.3 / 裁决④：downgrade 只回收结构（lineage 表 + 两个索引），12 张表的 lineage_id 与值全部保留。"""
    db = str(tmp_path / "m13.db")
    _seed_baseline_db(db)
    assert migrations_runner.run_upgrade(db_file=db) is True
    before = _filled_counts(db)
    lineage_id = _lineage_row(db)["id"]

    migrations_runner.run_downgrade(PREVIOUS_REVISION, db_file=db)

    assert "lineage" not in _tables(db)
    assert "idx_patient_teachers_lineage" not in _indexes(db)
    assert "idx_lineage_owner" not in _indexes(db)
    assert _filled_counts(db) == before  # 值原样保留
    for table in LINEAGE_ID_TABLES:
        assert "lineage_id" in _columns_of(db, table)
    assert _one(db, "SELECT lineage_id FROM drafts")["lineage_id"] == lineage_id
    assert _one(db, "SELECT version_num FROM alembic_version")["version_num"] == PREVIOUS_REVISION

    # 往返可用：再 upgrade → 表 / 索引回来、种子同 id、值不变
    assert migrations_runner.run_upgrade(db_file=db) is True
    assert "lineage" in _tables(db) and _lineage_row(db)["id"] == lineage_id
    assert _filled_counts(db) == before


def test_0005_downgrade_safety_gates(tmp_path):
    """§6.3 安全闸：① 师门数 > 老师数（自建 / 多门数据）→ 中止；② 有已退出师门记录 → 中止（不静默吃数据）。"""
    db = str(tmp_path / "m14.db")
    _seed_baseline_db(db)
    assert migrations_runner.run_upgrade(db_file=db) is True

    # ① 第 2 个师门（= 老师自建 / 多门数据）→ 中止，且一条 DROP 都不执行
    conn = sqlite3.connect(db)
    try:
        conn.execute(
            "INSERT INTO lineage (id, name, owner_teacher_name, description, status, created_at, updated_at) "
            "VALUES ('lin-wang', '王老师師門', '王老师', '', 'active', '2026-09-02T00:00:00', '2026-09-02T00:00:00')"
        )
        conn.commit()
    finally:
        conn.close()
    with pytest.raises(Exception) as excinfo:
        migrations_runner.run_downgrade(PREVIOUS_REVISION, db_file=db)
    assert "downgrade 已中止" in str(excinfo.value)
    assert "lineage" in _tables(db)
    assert _count(db, "lineage") == 2

    # ② 只剩「已退出师门」记录（lineage_id 非空 + status='inactive'）→ 同样中止
    conn = sqlite3.connect(db)
    try:
        conn.execute("DELETE FROM lineage WHERE id = 'lin-wang'")
        conn.execute("UPDATE patient_teachers SET status = 'inactive' WHERE patient_name = '患者01'")
        conn.commit()
    finally:
        conn.close()
    with pytest.raises(Exception) as excinfo:
        migrations_runner.run_downgrade(PREVIOUS_REVISION, db_file=db)
    assert "downgrade 已中止" in str(excinfo.value)
    assert "lineage" in _tables(db)

    # ③ 恢复 active → 闸门放行（证明闸门是唯一阻塞点）
    conn = sqlite3.connect(db)
    try:
        conn.execute("UPDATE patient_teachers SET status = 'active'")
        conn.commit()
    finally:
        conn.close()
    migrations_runner.run_downgrade(PREVIOUS_REVISION, db_file=db)
    assert "lineage" not in _tables(db)


def test_0005_init_db_then_upgrade(tmp_path, monkeypatch):
    """§8 组①「空库」：init_db() 建出存量表（数据极少）→ 全链 upgrade 跑通、每位老师都有默认师门。"""
    import database

    db_file = tmp_path / "empty_0005.db"
    monkeypatch.setattr(database, "DB_PATH", str(db_file))
    database.init_db()

    assert migrations_runner.run_upgrade(db_file=str(db_file)) is True

    db = str(db_file)
    assert _count(db, "lineage") == _count(db, "teachers")  # 每位老师一个默认师门
    for table in LINEAGE_ID_TABLES:
        if table in _tables(db):
            assert "lineage_id" in _columns_of(db, table), "%s 缺 lineage_id" % table
    assert "lineage_id" not in _columns_of(db, "plan_templates")  # A1：兼容镜像不师门化
    assert _one(db, "SELECT version_num FROM alembic_version")["version_num"] == ALEMBIC_HEAD


def test_0005_offline_sql_artifact_matches_migration():
    """§6.4 / CTO 约束 5：`docs/migrations/0005_add_lineage.sql` 的结构语句与回填语句与迁移内联常量逐字一致。"""
    module = _load_migration_0005()
    artifact = os.path.join(os.path.dirname(BACKEND_DIR), "docs", "migrations", "0005_add_lineage.sql")
    assert os.path.exists(artifact), "离线产物缺失：%s" % artifact
    text = open(artifact, encoding="utf-8-sig").read().replace("\r\n", "\n")

    assert module.LINEAGE_TABLE_DDL.strip() + ";" in text
    assert "CREATE INDEX IF NOT EXISTS idx_lineage_owner ON lineage (owner_teacher_name, status);" in text
    for ddl in module.PATIENT_TEACHERS_INDEX_DDL:
        assert ddl + ";" in text
    for table, _column in module.ADD_COLUMNS:
        assert (module.ADD_COLUMN_TPL % table) + ";" in text, "产物缺 %s 的补列语句" % table
    for table, owner_column in module.BACKFILL_SOURCES:
        assert module.backfill_sql(table, owner_column) + ";" in text, "产物缺 %s 的回填语句" % table
    # 种子语句：真机唯一老师的 lin-* id 必须以内联字面量出现（离线产物可直接人工预审）
    assert module.lineage_id_for(REAL_TEACHER) in text
    assert module.LINEAGE_NAME_SUFFIX in text
    # §6.3 / 裁决 ④：产物中不得出现任何删列语句
    assert "DROP COLUMN" not in text.upper()


def test_migration_0004_adds_patient_record_template_refs(tmp_path):
    """【Epic 2 步骤 3.0 · A1 批复】`patient_records` 补 `template_id` / `template_version`。

    老行落 0 = 未记录；可重跑；downgrade 按批复**删列**（本用例只回退到 0003，隔离本 revision，
    不牵动 0001 / 0002 / 0003 各自的回退闸），删列后表与存量行原样保留，且能再 upgrade 回来。
    """
    db = tmp_path / "m8.db"
    conn = sqlite3.connect(str(db))
    conn.execute(PATIENT_RECORDS_DDL)
    conn.execute(
        "INSERT INTO patient_records (patient_name, teacher_name, ai_draft, final_plan, doctor) "
        "VALUES ('张三', '李老师', 'AI 原稿', '老师定稿', '李老师')"
    )
    conn.commit()
    conn.close()

    assert migrations_runner.run_upgrade(db_file=str(db)) is True

    columns = _names(_read(str(db), "PRAGMA table_info('patient_records')"))
    assert {"template_id", "template_version"} <= set(columns)
    old_row = _one(str(db), "SELECT * FROM patient_records WHERE patient_name = '张三'")
    assert old_row["template_id"] == 0 and old_row["template_version"] == 0        # 老数据 = 未记录
    assert old_row["ai_draft"] == "AI 原稿" and old_row["final_plan"] == "老师定稿"  # 老行内容一字不动
    assert _one(str(db), "SELECT version_num FROM alembic_version")["version_num"] == ALEMBIC_HEAD

    # 可重跑：已在 head 再 upgrade 一次仍是 no-op（不重复加列、不报错）
    assert migrations_runner.run_upgrade(db_file=str(db)) is True
    cols = _names(_read(str(db), "PRAGMA table_info('patient_records')"))
    assert cols.count("template_id") == 1 and cols.count("template_version") == 1

    # downgrade 回 0003：A1 批复「可删列」→ 两列消失；表与存量行保留（只影响 Epic 2 的归因位）
    migrations_runner.run_downgrade("0003_add_agent_stage", db_file=str(db))
    remaining = _names(_read(str(db), "PRAGMA table_info('patient_records')"))
    assert "template_id" not in remaining and "template_version" not in remaining
    assert _one(str(db), "SELECT COUNT(*) AS c FROM patient_records")["c"] == 1
    assert _one(str(db), "SELECT final_plan FROM patient_records")["final_plan"] == "老师定稿"
    assert _one(str(db), "SELECT version_num FROM alembic_version")["version_num"] == (
        "0003_add_agent_stage"
    )

    # 回退后能再升级 → 往返可用、列定义一致（step 3.5 起由 sign_draft 写入这两列）
    assert migrations_runner.run_upgrade(db_file=str(db)) is True
    assert {"template_id", "template_version"} <= set(
        _names(_read(str(db), "PRAGMA table_info('patient_records')"))
    )


# ===========================================================================
# 【Epic 2 step-7 补测 · CTO 裁决 A】迁移 0003 守护测试：幂等重跑 + downgrade 审计安全闸
# 对齐：docs/epic2-agent-stage-design-v1.md §6.6 第 39 条（计划名 `test_migration_0003_idempotent`）
#       / 第 40 条（计划名 `test_migration_0003_downgrade_safety`）
#       / §1.4（DDL 唯一真相源 = 迁移 · 可重跑 · downgrade 带安全闸 + 两个快照列不删）
#       / §7.1-①（两个快照列）②（存量老师种子 = learning，脚本名 SEED_STAGE）。
# 纪律：tmp_path 自建独立 SQLite 文件，**绝不碰** backend/zhiheng.db 与 backend/test.db；
#       回退只到 **0002（本 revision 的上游）** → 隔离 0003 自身，不牵动 0004 / 0005 各自的回退闸
#       （与 0004 用例「只回退到 0003」、0005 用例「只回退到 PREVIOUS_REVISION」同一口径）。
# ===========================================================================

STAGE_TABLES = ("agent_stage_state", "agent_stage_log", "agent_stage_config")
STAGE_INDEXES = ("idx_agent_stage_state_scope", "idx_agent_stage_log_teacher_time")
STAGE_SNAPSHOT_COLUMNS = (("drafts", "ai_original_content"), ("patient_records", "ai_original_text"))


def _stage_snapshot(db_path):
    """0003 的「不变面」一次性取样：三表是否在 / 行数、两索引是否在、两快照列各出现几次。

    刻意**不含**时间列（`stage_since` / `updated_at` / `created_at` 每次种子按当时时刻落，属预期变化，
    与 0005 段的 `_survivors()` 同一取舍），也刻意不含 `alembic_version`（版本号各处单独断言）；
    表不存在时行数取 `None`（`_count()` 依赖 `_one()`，表缺失会断言失败，故先探表再计数）。
    """
    tables = _tables(db_path)
    indexes = _indexes(db_path)
    return {
        "tables": {table: table in tables for table in STAGE_TABLES},
        "counts": {table: (_count(db_path, table) if table in tables else None) for table in STAGE_TABLES},
        "indexes": {name: name in indexes for name in STAGE_INDEXES},
        "columns": {table: _columns_of(db_path, table).count(column)
                    for table, column in STAGE_SNAPSHOT_COLUMNS},
    }


def _stage_seed_db(tmp_path, monkeypatch, name):
    """造一份「`init_db()` 起库 + 2 位老师」的最小库，并升级到 **0003**（不继续升到 0004 / 0005）。

    用 `init_db()` 而非手抄 DDL：`teachers` / `drafts` / `patient_records` 三张宿主表与真机同形，
    零 DDL 复制（避免夹具漂移）；`INSERT OR IGNORE` + 主键去重 → 老师数恒 2（种子 ① 才有区分度，
    1 位老师时「种子重复」与「种子 1 行」无法区分）。
    """
    import database

    db_file = tmp_path / name
    monkeypatch.setattr(database, "DB_PATH", str(db_file))
    database.init_db()

    conn = sqlite3.connect(str(db_file))
    try:
        for teacher in ("李老师", "王老师"):
            conn.execute(
                "INSERT OR IGNORE INTO teachers (name, description, status, last_active_at, created_at) "
                "VALUES (?, '', 'active', '2026-09-01T00:00:00', '2026-09-01T00:00:00')",
                (teacher,),
            )
        conn.commit()
        teachers = conn.execute("SELECT COUNT(*) FROM teachers").fetchone()[0]
    finally:
        conn.close()
    # 夹具硬前置（与 `_seed_baseline_db` 的「基线失真」同款）：init_db() 的默认种子一旦漂移就当场失败
    assert teachers == 2, "夹具失真：teachers 应恰好 2 位（init_db 默认 1 位 + 本用例 1 位），实测 %d 位" % teachers

    db = str(db_file)
    assert migrations_runner.run_upgrade("0003_add_agent_stage", db_file=db) is True
    assert _one(db, "SELECT version_num FROM alembic_version")["version_num"] == "0003_add_agent_stage"
    return db


def test_0003_upgrade_is_idempotent(tmp_path, monkeypatch):
    """§6.6 第 39 条 / §1.4「可重跑」：建表 / 补列 / 种子全幂等 —— 重跑后三表行数与种子都不翻倍。

    三段：① 已在 0003 再 upgrade = no-op；② **真正重跑本 revision**（回上游 0002 → 再 upgrade）；
    ③ 重跑后与首跑逐项一致（种子不重复），且两个快照列**恰好一列**（不重复 ADD COLUMN）。
    """
    db = _stage_seed_db(tmp_path, monkeypatch, "m14.db")
    first = _stage_snapshot(db)

    # 首跑就位：三表 + 两索引 + 两快照列；种子 ① 每位老师一行（stage='learning' / source='default'）；
    # 种子 ② 全局配置行（teacher_name=''）恰好 1 行且 config_json='{}'（§7.1-② / §3.5）
    assert first["tables"] == {table: True for table in STAGE_TABLES}
    assert first["indexes"] == {name: True for name in STAGE_INDEXES}
    assert first["columns"] == {"drafts": 1, "patient_records": 1}
    assert first["counts"] == {"agent_stage_state": 2, "agent_stage_log": 0, "agent_stage_config": 1}
    assert {row["stage"] for row in _read(db, "SELECT stage FROM agent_stage_state")} == {"learning"}
    assert {row["stage_source"] for row in _read(db, "SELECT stage_source FROM agent_stage_state")} == {"default"}
    global_row = _one(db, "SELECT teacher_name, config_json FROM agent_stage_config")
    assert global_row["teacher_name"] == "" and global_row["config_json"] == "{}"

    # ① 已在 0003 再 upgrade 一次 = no-op（不重复建表 / 不重复补列 / 不重复种子；返回 True 即无异常）
    assert migrations_runner.run_upgrade("0003_add_agent_stage", db_file=db) is True
    assert _stage_snapshot(db) == first

    # ② 真正重跑本 revision：回上游 0002 → 三表与两索引消失，两个快照列按 §1.4 **保留**（列里有历史快照）
    migrations_runner.run_downgrade("0002_add_draft_template_refs", db_file=db)
    rolled_back = _stage_snapshot(db)
    assert rolled_back["tables"] == {table: False for table in STAGE_TABLES}
    assert rolled_back["counts"] == {table: None for table in STAGE_TABLES}
    assert rolled_back["indexes"] == {name: False for name in STAGE_INDEXES}
    assert rolled_back["columns"] == {"drafts": 1, "patient_records": 1}

    assert migrations_runner.run_upgrade("0003_add_agent_stage", db_file=db) is True
    # ③ 与首跑逐项一致 —— 种子不重复（状态行 = 老师数 2，而不是 4）、全局行仍 1 行、两列仍各 1 列
    assert _stage_snapshot(db) == first
    assert _one(db, "SELECT version_num FROM alembic_version")["version_num"] == "0003_add_agent_stage"


def test_0003_downgrade_aborts_with_audit_events(tmp_path, monkeypatch):
    """§6.6 第 40 条 / §1.4 安全闸：`agent_stage_log` 有审计事件时拒绝降级（不静默吃掉治理留痕）。

    三段：① 无日志时放行见 `test_0003_upgrade_is_idempotent` 的 ②/③ 段（本用例不重复）；
    ② 插 1 行审计事件 → **中止 + 提示导出**，且零副作用（三表 / 两索引 / 两快照列 / 审计行一字未动，
    版本号仍停在 0003）；③ 清空审计表后放行 → 证明闸门是唯一阻塞点，两快照列在 downgrade 后仍在。
    """
    db = _stage_seed_db(tmp_path, monkeypatch, "m15.db")

    conn = sqlite3.connect(db)
    try:
        conn.execute(
            "INSERT INTO agent_stage_log (teacher_name, event_type, from_stage, to_stage, capability, "
            "task_id, metrics_json, detail, created_at) "
            "VALUES ('李老师', 'upgrade_confirmed', 'learning', 'apprentice', 'draft_generation', "
            "7, '{}', '审计留痕', '2026-09-29T10:00:00')"
        )
        conn.commit()
    finally:
        conn.close()

    blocked = _stage_snapshot(db)
    assert blocked["counts"]["agent_stage_log"] == 1

    with pytest.raises(Exception) as excinfo:
        migrations_runner.run_downgrade("0002_add_draft_template_refs", db_file=db)
    assert "downgrade 已中止" in str(excinfo.value)
    assert "导出" in str(excinfo.value)  # 闸门必须给出「先导出留档」的处置提示，不是干瘪报错

    # ② 中止 = 零副作用：三表 / 两索引 / 两快照列 / 审计行原样，版本号仍停在 0003
    assert _stage_snapshot(db) == blocked
    audit_row = _one(db, "SELECT * FROM agent_stage_log")
    assert audit_row["event_type"] == "upgrade_confirmed" and audit_row["detail"] == "审计留痕"
    assert _one(db, "SELECT version_num FROM alembic_version")["version_num"] == "0003_add_agent_stage"

    # ③ 清空审计表 → 闸门放行（证明闸门是唯一阻塞点）；两快照列按 §1.4 保留
    conn = sqlite3.connect(db)
    try:
        conn.execute("DELETE FROM agent_stage_log")
        conn.commit()
    finally:
        conn.close()

    migrations_runner.run_downgrade("0002_add_draft_template_refs", db_file=db)
    passed = _stage_snapshot(db)
    assert passed["tables"] == {table: False for table in STAGE_TABLES}
    assert passed["indexes"] == {name: False for name in STAGE_INDEXES}
    assert passed["columns"] == {"drafts": 1, "patient_records": 1}
    assert _one(db, "SELECT version_num FROM alembic_version")["version_num"] == (
        "0002_add_draft_template_refs"
    )
