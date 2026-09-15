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

    cursor.execute("""
    CREATE TABLE IF NOT EXISTS patients (
        name TEXT PRIMARY KEY,
        teacher_name TEXT DEFAULT '李老师',
        guardian_name TEXT DEFAULT 'self',
        relation TEXT DEFAULT '本人'
    )
    """)

    # 【第29天修改】新增出生地字段
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS patient_profiles (
        patient_name TEXT PRIMARY KEY,
        gender TEXT,
        birth_date TEXT,
        birth_time TEXT,
        birth_place TEXT,
        location TEXT
    )
    """)

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

    cursor.execute("""
    CREATE TABLE IF NOT EXISTS transcriptions (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        patient_name TEXT,
        content TEXT,
        data_type TEXT,
        processed INTEGER DEFAULT 0
    )
    """)

    cursor.execute("""
    CREATE TABLE IF NOT EXISTS drafts (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        transcript_id INTEGER,
        patient_name TEXT,
        content TEXT,
        signed INTEGER
    )
    """)

    cursor.execute("""
    CREATE TABLE IF NOT EXISTS patient_records (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        patient_name TEXT,
        ai_draft TEXT,
        final_plan TEXT,
        doctor TEXT
    )
    """)

    cursor.execute("""
    CREATE TABLE IF NOT EXISTS accounts (
        role_name TEXT PRIMARY KEY,
        points INTEGER DEFAULT 0
    )
    """)

    conn.commit()

    cursor.execute("SELECT COUNT(*) as count FROM patients")
    if cursor.fetchone()["count"] == 0:
        cursor.execute("INSERT INTO patients (name, teacher_name, guardian_name, relation) VALUES (?, ?, ?, ?)", ("张三", "李老师", "self", "本人"))
        cursor.execute("INSERT INTO patients (name, teacher_name, guardian_name, relation) VALUES (?, ?, ?, ?)", ("李四", "李老师", "self", "本人"))
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

def get_patients(guardian_name=None):
    conn = get_connection()
    if guardian_name:
        rows = conn.execute("SELECT * FROM patients WHERE name = ? OR guardian_name = ?", (guardian_name, guardian_name)).fetchall()
    else:
        rows = conn.execute("SELECT * FROM patients").fetchall()
    conn.close()
    return [dict(r) for r in rows]

# 【第29天修改】添加出生地
def add_patient(name, guardian_name, relation, gender, birth_date, birth_time, birth_place, location):
    conn = get_connection()
    conn.execute("INSERT OR IGNORE INTO patients (name, teacher_name, guardian_name, relation) VALUES (?, ?, ?, ?)", 
                 (name, "李老师", guardian_name, relation))
    conn.execute("""
    INSERT INTO patient_profiles (patient_name, gender, birth_date, birth_time, birth_place, location)
    VALUES (?, ?, ?, ?, ?, ?)
    ON CONFLICT(patient_name) DO UPDATE SET
        gender=excluded.gender,
        birth_date=excluded.birth_date,
        birth_time=excluded.birth_time,
        birth_place=excluded.birth_place,
        location=excluded.location
    """, (name, gender, birth_date, birth_time, birth_place, location))
    conn.commit()
    conn.close()

def get_patient_profile(patient_name):
    conn = get_connection()
    row = conn.execute("SELECT * FROM patient_profiles WHERE patient_name = ?", (patient_name,)).fetchone()
    conn.close()
    if row:
        return dict(row)
    return {"patient_name": patient_name, "gender": "", "birth_date": "", "birth_time": "", "birth_place": "", "location": ""}

# 【第29天修改】保存出生地
def save_patient_profile(patient_name, gender, birth_date, birth_time, birth_place, location):
    conn = get_connection()
    conn.execute("""
    INSERT INTO patient_profiles (patient_name, gender, birth_date, birth_time, birth_place, location)
    VALUES (?, ?, ?, ?, ?, ?)
    ON CONFLICT(patient_name) DO UPDATE SET
        gender=excluded.gender,
        birth_date=excluded.birth_date,
        birth_time=excluded.birth_time,
        birth_place=excluded.birth_place,
        location=excluded.location
    """, (patient_name, gender, birth_date, birth_time, birth_place, location))
    conn.commit()
    conn.close()

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
    conn.execute("UPDATE homework SET status = ? WHERE id = (SELECT MAX(id) FROM homework WHERE patient_name = ?)", (status, patient_name))
    conn.commit()
    conn.close()

def insert_transcription(patient_name, content, data_type):
    conn = get_connection()
    conn.execute("INSERT INTO transcriptions (patient_name, content, data_type, processed) VALUES (?, ?, ?, 0)",
                 (patient_name, content, data_type))
    conn.commit()
    conn.close()

def get_transcriptions(patient_name=None):
    conn = get_connection()
    if patient_name:
        rows = conn.execute("SELECT * FROM transcriptions WHERE patient_name = ? AND processed = 0 ORDER BY id DESC", (patient_name,)).fetchall()
    else:
        rows = conn.execute("SELECT * FROM transcriptions WHERE processed = 0 ORDER BY id DESC").fetchall()
    conn.close()
    return [dict(r) for r in rows]

def insert_draft(transcript_id, patient_name, content):
    conn = get_connection()
    cursor = conn.execute("INSERT INTO drafts (transcript_id, patient_name, content, signed) VALUES (?, ?, ?, ?)",
                          (transcript_id, patient_name, content, 0))
    conn.execute("UPDATE transcriptions SET processed = 1 WHERE id = ?", (transcript_id,))
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

    conn.execute("INSERT INTO patient_records (patient_name, ai_draft, final_plan, doctor) VALUES (?, ?, ?, ?)",
                 (draft["patient_name"], draft["content"], final_plan, "李老师"))
    
    conn.execute("INSERT INTO homework (patient_name, task, detail, status, created_at) VALUES (?, ?, ?, ?, ?)",
                 (draft["patient_name"], f"今日医嘱：{final_plan}", "请严格遵医嘱执行", "pending", "2026-09-11"))
    
    conn.execute("DELETE FROM transcriptions WHERE id = ?", (draft["transcript_id"],))
    conn.execute("DELETE FROM drafts WHERE id = ?", (draft_id,))
    
    conn.commit()
    conn.close()
    return draft["patient_name"]

def get_patient_records(patient_name=None):
    conn = get_connection()
    if patient_name:
        rows = conn.execute("SELECT * FROM patient_records WHERE patient_name = ? ORDER BY id DESC", (patient_name,)).fetchall()
    else:
        rows = conn.execute("SELECT * FROM patient_records ORDER BY id DESC").fetchall()
    conn.close()
    return [dict(r) for r in rows]

def is_latest_record(record_id, patient_name):
    conn = get_connection()
    latest = conn.execute(
        "SELECT id FROM patient_records WHERE patient_name = ? ORDER BY id DESC LIMIT 1",
        (patient_name,)
    ).fetchone()
    conn.close()
    return latest and latest["id"] == record_id

def update_patient_record(record_id, patient_name, new_content):
    if not is_latest_record(record_id, patient_name):
        return False
    conn = get_connection()
    conn.execute("UPDATE patient_records SET final_plan = ? WHERE id = ?", (new_content, record_id))
    conn.commit()
    conn.close()
    return True

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