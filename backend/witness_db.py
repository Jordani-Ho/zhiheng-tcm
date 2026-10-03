"""D 板块 M2：治理见证只读数据库连接。

独立于 database.py 的读写连接（D v1.3 §4.2.1）：
- 复用 database.DB_PATH（单一来源）
- 使用 SQLite URI 模式强制 RO：file:<path>?mode=ro + uri=True
- 不复用 database.get_connection()

调用方负责 conn.close()。
"""

from pathlib import Path
import sqlite3

import database


def get_ro_connection():
    """返回只读连接。

    SQLite URI 模式：
    - file:<绝对路径>?mode=ro → 只读
    - uri=True                → 启用 URI 解析

    Windows 路径用 as_posix() 转正斜杠（SQLite URI 需 POSIX 格式）。
    """
    db_path = Path(database.DB_PATH).resolve()
    uri = f"file:{db_path.as_posix()}?mode=ro"
    conn = sqlite3.connect(uri, uri=True)
    conn.row_factory = sqlite3.Row
    return conn
