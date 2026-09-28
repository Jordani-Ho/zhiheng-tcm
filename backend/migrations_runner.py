"""Alembic 迁移运行器（Epic 1：Template 模型）

对齐：docs/epic1-template-design-v1.md §6.2「迁移运行接入点」
- `main.py` 与 `conftest.py` 复用**同一条**升级路径，避免两处拼命令；
- 失败**只打日志、不抛异常、不阻塞启动**（批复 1）：旧链路（病历 / 签字 / 九宫格开方）照常可用；
  `/api/templates*` 侧在表缺失时返回 503，由接口层负责提示。

手工路径（运维手册，同 §6.5）：
    cd backend
    ..\\venv\\Scripts\\alembic.exe upgrade head          # 升级
    ..\\venv\\Scripts\\alembic.exe downgrade base        # 回退（带安全闸）
    ..\\venv\\Scripts\\alembic.exe upgrade head --sql    # 只输出 SQL，人工预审
"""
import os

from alembic import command
from alembic.config import Config

BACKEND_DIR = os.path.dirname(os.path.abspath(__file__))
ALEMBIC_INI = os.path.join(BACKEND_DIR, "alembic.ini")


def _to_url(db_file):
    """把 sqlite 文件路径转成 SQLAlchemy URL（与 alembic/env.py 的拼法保持一致）。"""
    if not db_file:
        return None
    if "://" in db_file:
        return db_file
    path = db_file if os.path.isabs(db_file) else os.path.join(BACKEND_DIR, db_file)
    return "sqlite:///" + path.replace("\\", "/")


def build_config(db_file=None):
    """构造 Alembic Config。

    db_file 走 `alembic/env.py` 的 attributes["sqlalchemy_url"] 覆盖口，
    默认 None = 用 ZHIENG_DB（与 database.py 同源）。
    """
    cfg = Config(ALEMBIC_INI)
    cfg.set_main_option("script_location", os.path.join(BACKEND_DIR, "alembic"))
    url = _to_url(db_file)
    if url:
        cfg.attributes["sqlalchemy_url"] = url
    return cfg


def run_upgrade(revision="head", db_file=None):
    """执行迁移到 head。返回 True / False（失败不抛，只打日志）。"""
    try:
        cfg = build_config(db_file)
        command.upgrade(cfg, revision)
        return True
    except Exception as exc:  # noqa: BLE001 —— 启动路径必须容错
        print(
            "[warn] 模板表迁移失败（不阻塞启动，旧链路照常）：%s: %s"
            % (type(exc).__name__, exc)
        )
        return False


def run_downgrade(revision="base", db_file=None):
    """回退迁移（供运维 / 测试演练用）。失败抛异常，因为回退必须让人看到失败原因。"""
    command.downgrade(build_config(db_file), revision)


def current(db_file=None):
    """打印当前 revision（供运维自查 / 测试断言）。"""
    command.current(build_config(db_file))


if __name__ == "__main__":
    run_upgrade()
