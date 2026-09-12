import sqlite3
import os

DB_PATH = os.path.join(os.path.dirname(__file__), "zhiheng.db")

def get_connection():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn

def init_db():
    conn = get_connection()
    cursor = conn.cursor()

    # 1. 作业表
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS homework (
        patient_name TEXT PRIMARY KEY,
        task TEXT,
        detail TEXT,
        status TEXT
    )
    """)

    # 2. 转述表
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS transcriptions (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        patient_name TEXT,
        content TEXT,
        data_type TEXT
    )
    """)

    # 3. 病历草案表
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS drafts (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        transcript_id INTEGER,
        patient_name TEXT,
        content TEXT,
        signed INTEGER
    )
    """)

    # 4. 患者健康档案表
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS patient_records (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        patient_name TEXT,
        content TEXT,
        doctor TEXT
    )
    """)

    # 5. 【第12天新增】积分账户表
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS accounts (
        role_name TEXT PRIMARY KEY,
        points INTEGER DEFAULT 0
    )
    """)

    conn.commit()

    # 初始化默认数据
    cursor.execute("SELECT COUNT(*) as count FROM homework")
    if cursor.fetchone()["count"] == 0:
        cursor.execute("INSERT INTO homework (patient_name, task, detail, status) VALUES (?, ?, ?, ?)",
                       ("张三", "今日作业：按揉太渊穴5分钟", "请记得在酉时完成。", "pending"))
        conn.commit()

    # 给患者和老师初始积分
    cursor.execute("SELECT COUNT(*) as count FROM accounts WHERE role_name = '张三'")
    if cursor.fetchone()["count"] == 0:
        cursor.execute("INSERT INTO accounts (role_name, points) VALUES (?, ?)", ("张三", 100)) # 患者初始100分
    cursor.execute("SELECT COUNT(*) as count FROM accounts WHERE role_name = '李老师'")
    if cursor.fetchone()["count"] == 0:
        cursor.execute("INSERT INTO accounts (role_name, points) VALUES (?, ?)", ("李老师", 500)) # 老师初始500分
    conn.commit()

    conn.close()

# ---------- 作业相关操作 ----------
def get_homework():
    conn = get_connection()
    row = conn.execute("SELECT * FROM homework LIMIT 1").fetchone()
    conn.close()
    return dict(row) if row else None

def update_homework_status(status):
    conn = get_connection()
    conn.execute("UPDATE homework SET status = ?", (status,))
    conn.commit()
    conn.close()

# ---------- 转述相关操作 ----------
def insert_transcription(patient_name, content, data_type):
    conn = get_connection()
    conn.execute("INSERT INTO transcriptions (patient_name, content, data_type) VALUES (?, ?, ?)",
                 (patient_name, content, data_type))
    conn.commit()
    conn.close()

def get_transcriptions():
    conn = get_connection()
    rows = conn.execute("SELECT * FROM transcriptions ORDER BY id DESC").fetchall()
    conn.close()
    return [dict(r) for r in rows]

# ---------- 病历草案相关操作 ----------
def insert_draft(transcript_id, patient_name, content):
    conn = get_connection()
    cursor = conn.execute("INSERT INTO drafts (transcript_id, patient_name, content, signed) VALUES (?, ?, ?, ?)",
                          (transcript_id, patient_name, content, 0))
    conn.commit()
    draft_id = cursor.lastrowid
    conn.close()
    return draft_id

def get_drafts():
    conn = get_connection()
    rows = conn.execute("SELECT * FROM drafts WHERE signed = 0").fetchall()
    conn.close()
    return [dict(r) for r in rows]

def update_draft_content(draft_id, content):
    conn = get_connection()
    conn.execute("UPDATE drafts SET content = ? WHERE id = ?", (content, draft_id))
    conn.commit()
    conn.close()

def sign_draft(draft_id, final_plan):
    conn = get_connection()
    draft = conn.execute("SELECT * FROM drafts WHERE id = ?", (draft_id,)).fetchone()
    if not draft:
        conn.close()
        return None

    # 1. 归档到患者健康档案
    conn.execute("INSERT INTO patient_records (patient_name, content, doctor) VALUES (?, ?, ?)",
                 (draft["patient_name"], final_plan, "李老师"))

    # 2. 阅后即焚
    conn.execute("DELETE FROM drafts WHERE id = ?", (draft_id,))
    
    conn.commit()
    conn.close()
    return draft["patient_name"]

# ---------- 患者健康档案相关操作 ----------
def get_patient_records(patient_name=None):
    conn = get_connection()
    if patient_name:
        rows = conn.execute("SELECT * FROM patient_records WHERE patient_name = ? ORDER BY id DESC", (patient_name,)).fetchall()
    else:
        rows = conn.execute("SELECT * FROM patient_records ORDER BY id DESC").fetchall()
    conn.close()
    return [dict(r) for r in rows]

# ---------- 【第12天新增】积分相关操作 ----------
def get_points(role_name):
    conn = get_connection()
    row = conn.execute("SELECT points FROM accounts WHERE role_name = ?", (role_name,)).fetchone()
    conn.close()
    return row["points"] if row else 0

def add_points(role_name, amount):
    conn = get_connection()
    conn.execute("UPDATE accounts SET points = points + ? WHERE role_name = ?", (amount, role_name))
    conn.commit()
    conn.close()

def transfer_points(from_role, to_role, amount):
    """模拟患者支付学费给老师"""
    conn = get_connection()
    # 扣患者
    conn.execute("UPDATE accounts SET points = points - ? WHERE role_name = ?", (amount, from_role))
    # 加老师
    conn.execute("UPDATE accounts SET points = points + ? WHERE role_name = ?", (amount, to_role))
    conn.commit()
    conn.close()