# 【Epic 1 新增】Alembic 运行环境
# 对齐：docs/epic1-template-design-v1.md §6.1
#   ① 不 import database、不调 init_db()（避免隐式副作用）；
#   ② target_metadata 恒为 None → --autogenerate 被禁用（无 ORM 元数据可对）；
#   ③ sqlalchemy.url 优先取调用方指定的 attributes["sqlalchemy_url"]，其次 ini，最后从 ZHIENG_DB 拼绝对路径。
import os

import sqlalchemy
from alembic import context

# backend/ 目录（env.py 在 backend/alembic/ 下）
BACKEND_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

# 无 ORM 元数据：本项目真源是 database.py 的裸 sqlite3 SQL，迁移只承担「版本化 DDL / 数据搬运」
target_metadata = None


def build_sqlalchemy_url(config):
    """按优先级解析数据库 URL：显式覆盖 > ini 里的 sqlalchemy.url > ZHIENG_DB 拼绝对路径。"""
    override = config.attributes.get("sqlalchemy_url")
    if override:
        return override

    ini_url = (config.get_main_option("sqlalchemy.url") or "").strip()
    if ini_url:
        return ini_url

    # 与 database.py:5 完全同源：DB_PATH = backend/ + os.environ.get("ZHIENG_DB", "zhiheng.db")
    db_file = os.environ.get("ZHIENG_DB", "zhiheng.db")
    if not os.path.isabs(db_file):
        db_file = os.path.join(BACKEND_DIR, db_file)
    return "sqlite:///" + db_file.replace("\\", "/")


def run_migrations_offline():
    """离线模式：alembic upgrade head --sql 只输出 SQL，不连库（用于上线前人工预审）。"""
    url = build_sqlalchemy_url(context.config)
    context.configure(
        url=url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
        render_as_batch=True,
        version_table="alembic_version",
        compare_type=False,
    )
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online():
    """在线模式：同一个连接、同一个事务内跑完所有迁移（SQLite 3.49 支持 DDL 事务）。

    注意：必须 try/finally 释放引擎 —— 迁移中途抛错（例如 downgrade 的安全闸）时，
    若不 dispose，Windows 下 SQLite 文件句柄会滞留，后续脚本无法删除 / 覆盖该库文件。
    """
    url = build_sqlalchemy_url(context.config)
    connectable = sqlalchemy.create_engine(url, future=True)
    try:
        with connectable.connect() as connection:
            context.configure(
                connection=connection,
                target_metadata=target_metadata,
                render_as_batch=True,
                version_table="alembic_version",
                compare_type=False,
                transaction_per_migration=False,  # 整个 upgrade/downgrade 一个事务：失败即整体回滚
            )
            with context.begin_transaction():
                context.run_migrations()
    finally:
        connectable.dispose()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
