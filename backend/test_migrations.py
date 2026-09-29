"""【Epic 1】Template 模型迁移守护测试

对齐：docs/epic1-template-design-v1.md §6.5（三类库执行步骤）/ §6.6（升级后校验清单）/ §14.1 A
- 全部用例都在 tmp_path 下自建独立 SQLite 文件，不碰 backend/zhiheng.db 与 backend/test.db；
- 直接调用 migrations_runner（与 main.py / conftest.py 同一条路径），另有一条真实 CLI 用例。
"""
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

