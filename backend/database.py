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

    # 1. 患者表
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS patients (
        name TEXT PRIMARY KEY,
        teacher_name TEXT DEFAULT '李老师'
    )
    """)

    # 2. 作业表（绑定到具体患者）
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS homework (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        patient_name TEXT,
        task TEXT,
        detail TEXT,
        status TEXT DEFAULT 'pending',
        created_at TEXT
    )
    """)

    # 3. 转述表
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS transcriptions (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        patient_name TEXT,
        content TEXT,
        data_type TEXT
    )
    """)

    # 4. 病历草案表
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS drafts (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        transcript_id INTEGER,
        patient_name TEXT,
        content TEXT,
        signed INTEGER
    )
    """)

    # 5. 患者健康档案表
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS patient_records (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        patient_name TEXT,
        content TEXT,
        doctor TEXT
    )
    """)

    # 6. 积分账户表
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS accounts (
        role_name TEXT PRIMARY KEY,
        points INTEGER DEFAULT 0
    )
    """)

    conn.commit()

    # 初始化默认数据
    cursor.execute("SELECT COUNT(*) as count FROM patients")
    if cursor.fetchone()["count"] == 0:
        cursor.execute("INSERT INTO patients (name, teacher_name) VALUES (?, ?)", ("张三", "李老师"))
        cursor.execute("INSERT INTO patients (name, teacher_name) VALUES (?, ?)", ("李四", "李老师"))
        conn.commit()

    cursor.execute("SELECT COUNT(*) as count FROM homework")
    if cursor.fetchone()["count"] == 0:
        cursor.execute("INSERT INTO homework (patient_name, task, detail, status, created_at) VALUES (?, ?, ?, ?, ?)",
                       ("张三", "今日作业：按揉太渊穴5分钟", "请记得在酉时完成。", "pending", "2026-09-11"))
        conn.commit()

    cursor.execute("SELECT COUNT(*) as count FROM accounts")
    if cursor.fetchone()["count"] == 0:
        cursor.execute("INSERT INTO accounts (role_name, points) VALUES (?, ?)", ("张三", 100))
        cursor.execute("INSERT INTO accounts (role_name, points) VALUES (?, ?)", ("李四", 100))
        cursor.execute("INSERT INTO accounts (role_name, points) VALUES (?, ?)", ("李老师", 500))
        conn.commit()

    conn.close()

# ---------- 患者相关操作 ----------
def get_patients():
    conn = get_connection()
    rows = conn.execute("SELECT * FROM patients").fetchall()
    conn.close()
    return [dict(r) for r in rows]

# ---------- 作业相关操作 ----------
def get_homework(patient_name):
    conn = get_connection()
    row = conn.execute("SELECT * FROM homework WHERE patient_name = ? ORDER BY id DESC LIMIT 1", (patient_name,)).fetchone()
    conn.close()
    return dict(row) if row else None

def create_homework(patient_name, task, detail):
    conn = get_connection()
    conn.execute("INSERT INTO homework (patient_name, task, detail, status, created_at) VALUES (?, ?, ?, ?, ?)",
                 (patient_name, task, detail, "pending", "2026-09-11"))
    conn.commit()
    conn.close()

def update_homework_status(patient_name, status):
    conn = get_connection()
    # 更新该患者最新的那条作业
    conn.execute("UPDATE homework SET status = ? WHERE id = (SELECT MAX(id) FROM homework WHERE patient_name = ?)", (status, patient_name))
    conn.commit()
    conn.close()

# ---------- 转述相关操作 ----------
def insert_transcription(patient_name, content, data_type):
    conn = get_connection()
    conn.execute("INSERT INTO transcriptions (patient_name, content, data_type) VALUES (?, ?, ?)",
                 (patient_name, content, data_type))
    conn.commit()
    conn.close()

def get_transcriptions(patient_name=None):
    conn = get_connection()
    if patient_name:
        rows = conn.execute("SELECT * FROM transcriptions WHERE patient_name = ? ORDER BY id DESC", (patient_name,)).fetchall()
    else:
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

    conn.execute("INSERT INTO patient_records (patient_name, content, doctor) VALUES (?, ?, ?)",
                 (draft["patient_name"], final_plan, "李老师"))
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

# ---------- 积分相关操作 ----------
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
    conn = get_connection()
    conn.execute("UPDATE accounts SET points = points - ? WHERE role_name = ?", (amount, from_role))
    conn.execute("UPDATE accounts SET points = points + ? WHERE role_name = ?", (amount, to_role))
    conn.commit()
    conn.close()