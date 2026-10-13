"""迁移 `0009` 的守护（P-102 / D-089）。

`0009` 是**数据清理**迁移，且带**安全闸**（默认不删数据）。这类迁移最容易出两种事故：
  ① **静默毁数据** —— 一声不响把历史行删了
  ② **静默放行** —— 该删的没删，迁移却标记成功

本文件同时钉住这两条，外加幂等（可重跑）与「无数据时不报错」。

⚠️ 每个用例用**独立临时库**（`tmp_path`），不碰 `test.db` —— 迁移会改 `alembic_version`。
"""

import os
import sqlite3
import sys

import pytest

BACKEND_DIR = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, BACKEND_DIR)

import database
import migrations_runner

PURGE_ENV = "P102_PURGE_LEGACY_STUDENT_REFERRALS"


@pytest.fixture
def fresh_db(tmp_path, monkeypatch):
    """独立临时库：删库 → init_db → 迁移到最新。返回库路径。

    同时清掉放行开关，保证每个用例从「默认不放行」起步。

    注意：`migrations_runner.run_upgrade()` **默认走 `ZHIENG_DB`**（conftest 里是 test.db），
    故凡对临时库跑迁移，必须显式传 `db_file=` —— 否则会误伤/误读 test.db。
    """
    db_path = tmp_path / "mig.db"
    monkeypatch.setattr(database, "DB_PATH", str(db_path))
    monkeypatch.delenv(PURGE_ENV, raising=False)
    database.init_db()
    migrations_runner.run_upgrade(db_file=str(db_path))
    return str(db_path)


def _version(db_path):
    conn = sqlite3.connect(db_path)
    try:
        row = conn.execute("SELECT version_num FROM alembic_version").fetchone()
        return row[0] if row else None
    finally:
        conn.close()


def _insert_referral(db_path, referral_id, referrer_type, referee_type):
    conn = sqlite3.connect(db_path)
    try:
        conn.execute(
            "INSERT INTO referral_chain (referral_id, referrer_id, referrer_type, "
            "referee_id, referee_type, lineage_id, referral_reason, created_at) "
            "VALUES (?, ?, ?, ?, ?, NULL, NULL, '2026-10-12T00:00:00')",
            (referral_id, "R-001", referrer_type, "E-001", referee_type),
        )
        conn.commit()
    finally:
        conn.close()


def _count_legacy(db_path):
    conn = sqlite3.connect(db_path)
    try:
        return conn.execute(
            "SELECT COUNT(*) FROM referral_chain "
            "WHERE referrer_type = 'STUDENT' OR referee_type IN ('STUDENT','DEPENDENT')"
        ).fetchone()[0]
    finally:
        conn.close()


def test_migration_reaches_0009_on_clean_db(fresh_db):
    """空库迁移到最新 -> 版本落在 0009（且无数据时不该报错）。"""
    assert _version(fresh_db) == "0009_p102_referral_student_cleanup"


def test_no_legacy_rows_is_a_noop(fresh_db):
    """无学生引荐数据时，重跑迁移应幂等通过（最常见路径）。"""
    assert _count_legacy(fresh_db) == 0
    assert migrations_runner.run_upgrade(db_file=fresh_db) is True   # 重跑
    assert _version(fresh_db) == "0009_p102_referral_student_cleanup"


def test_safety_gate_aborts_when_legacy_rows_present(fresh_db, monkeypatch):
    """**安全闸**：表内确有学生引荐行、且未放行 -> 迁移**不推进**且数据**未被删**。

    这是本迁移最重要的守护：防止"一声不响毁数据"。

    注：`migrations_runner.run_upgrade` 是**启动路径**，设计上吞异常并返回 False
    （见其 docstring「失败只打日志、不阻塞启动」）。故此处断言 `False` +
    **版本未推进** + **数据仍在**，三者共同证明"闸生效且没有半删"。
    """
    _insert_referral(fresh_db, "ref-legacy-1", "STUDENT", "STUDENT")
    assert _count_legacy(fresh_db) == 1

    # 把库退回 0008，模拟"迁移尚未应用"
    conn = sqlite3.connect(fresh_db)
    conn.execute("UPDATE alembic_version SET version_num = '0008_add_referral_chain'")
    conn.commit()
    conn.close()

    monkeypatch.delenv(PURGE_ENV, raising=False)
    assert migrations_runner.run_upgrade(db_file=fresh_db) is False, (
        "未放行时迁移必须失败（安全闸生效）")

    # **数据必须还在**（中止 ≠ 半删），版本必须没动
    assert _count_legacy(fresh_db) == 1, "中止后数据不得被改动"
    assert _version(fresh_db) == "0008_add_referral_chain", "中止后版本不得推进"


def test_purge_proceeds_when_explicitly_allowed(fresh_db, monkeypatch):
    """显式放行 -> 学生引荐行被删除，版本推进到 0009，收尾探测确认清空。"""
    _insert_referral(fresh_db, "ref-legacy-1", "STUDENT", "STUDENT")
    _insert_referral(fresh_db, "ref-legacy-2", "TEACHER", "DEPENDENT")
    # 一行正当的老师引荐，**不得被误删**
    _insert_referral(fresh_db, "ref-keep-1", "TEACHER", "TEACHER")
    assert _count_legacy(fresh_db) == 2

    conn = sqlite3.connect(fresh_db)
    conn.execute("UPDATE alembic_version SET version_num = '0008_add_referral_chain'")
    conn.commit()
    conn.close()

    monkeypatch.setenv(PURGE_ENV, "on")
    assert migrations_runner.run_upgrade(db_file=fresh_db) is True

    assert _version(fresh_db) == "0009_p102_referral_student_cleanup"
    assert _count_legacy(fresh_db) == 0, "放行后学生引荐行应被清空"

    conn = sqlite3.connect(fresh_db)
    try:
        total = conn.execute("SELECT COUNT(*) FROM referral_chain").fetchone()[0]
        kept = conn.execute(
            "SELECT COUNT(*) FROM referral_chain WHERE referral_id = 'ref-keep-1'"
        ).fetchone()[0]
    finally:
        conn.close()
    assert total == 1, "只应剩老师引荐那一行"
    assert kept == 1, "**正当的老师引荐不得被误删**"


def test_purge_is_idempotent(fresh_db, monkeypatch):
    """放行清理后再重跑 -> 无副作用（DELETE 幂等）。"""
    monkeypatch.setenv(PURGE_ENV, "on")
    assert migrations_runner.run_upgrade(db_file=fresh_db) is True
    assert migrations_runner.run_upgrade(db_file=fresh_db) is True
    assert _version(fresh_db) == "0009_p102_referral_student_cleanup"
    assert _count_legacy(fresh_db) == 0
