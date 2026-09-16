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
        teacher_name TEXT DEFAULT '李老师',
        guardian_name TEXT DEFAULT 'self',
        relation TEXT DEFAULT '本人'
    )
    """)

    # 2. 老师表（预留 status / last_active_at / complaint_count）
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS teachers (
        name TEXT PRIMARY KEY,
        description TEXT DEFAULT '',
        status TEXT DEFAULT 'active',
        last_active_at TEXT DEFAULT '',
        complaint_count INTEGER DEFAULT 0
    )
    """)

    # 3. 师生关系表
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS teacher_students (
        teacher_name TEXT,
        student_name TEXT,
        created_at TEXT,
        PRIMARY KEY (teacher_name, student_name)
    )
    """)

    # 4. 患者基础档案
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

    # 5. 作业表
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS homework (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        patient_name TEXT,
        teacher_name TEXT DEFAULT '李老师',
        task TEXT,
        detail TEXT,
        status TEXT DEFAULT 'pending',
        created_at TEXT
    )
    """)

    # 6. 转述表
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS transcriptions (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        patient_name TEXT,
        teacher_name TEXT DEFAULT '李老师',
        content TEXT,
        data_type TEXT,
        processed INTEGER DEFAULT 0
    )
    """)

    # 7. 病历草案表
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS drafts (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        transcript_id INTEGER,
        patient_name TEXT,
        teacher_name TEXT DEFAULT '李老师',
        content TEXT,
        signed INTEGER
    )
    """)

    # 8. 患者健康档案表
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS patient_records (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        patient_name TEXT,
        teacher_name TEXT DEFAULT '李老师',
        ai_draft TEXT,
        final_plan TEXT,
        doctor TEXT
    )
    """)

    # 9. 积分账户表
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS accounts (
        role_name TEXT PRIMARY KEY,
        points INTEGER DEFAULT 0
    )
    """)

    conn.commit()

    # 初始化数据
    cursor.execute("SELECT COUNT(*) as count FROM teachers")
    if cursor.fetchone()["count"] == 0:
        cursor.execute("INSERT INTO teachers (name, description) VALUES (?, ?)", ("李老师", "民间中医高手"))
        conn.commit()

    cursor.execute("SELECT COUNT(*) as count FROM patients")
    if cursor.fetchone()["count"] == 0:
        cursor.execute("INSERT INTO patients (name, teacher_name, guardian_name, relation) VALUES (?, ?, ?, ?)", ("张三", "李老师", "self", "本人"))
        cursor.execute("INSERT INTO patients (name, teacher_name, guardian_name, relation) VALUES (?, ?, ?, ?)", ("李四", "李老师", "self", "本人"))
        # 师生关系
        cursor.execute("INSERT INTO teacher_students (teacher_name, student_name, created_at) VALUES (?, ?, ?)", ("李老师", "张三", "2026-09-15"))
        cursor.execute("INSERT INTO teacher_students (teacher_name, student_name, created_at) VALUES (?, ?, ?)", ("李老师", "李四", "2026-09-15"))
        conn.commit()

    cursor.execute("SELECT COUNT(*) as count FROM homework")
    if cursor.fetchone()["count"] == 0:
        cursor.execute("INSERT INTO homework (patient_name, teacher_name, task, detail, status, created_at) VALUES (?, ?, ?, ?, ?, ?)",
                       ("张三", "李老师", "今日作业：按揉太渊穴5分钟", "请记得在酉时完成。", "pending", "2026-09-15"))
        conn.commit()

    cursor.execute("SELECT COUNT(*) as count FROM accounts")
    if cursor.fetchone()["count"] == 0:
        cursor.execute("INSERT INTO accounts (role_name, points) VALUES (?, ?)", ("张三", 100))
        cursor.execute("INSERT INTO accounts (role_name, points) VALUES (?, ?)", ("李四", 100))
        cursor.execute("INSERT INTO accounts (role_name, points) VALUES (?, ?)", ("李老师", 500))
        conn.commit()

    conn.close()

# ---------- 老师相关操作 ----------
def get_teachers():
    conn = get_connection()
    rows = conn.execute("SELECT * FROM teachers WHERE status = 'active'").fetchall()
    conn.close()
    return [dict(r) for r in rows]

# ---------- 师生关系操作 ----------
def get_teacher_students(teacher_name):
    """老师端：查看我的学生"""
    conn = get_connection()
    rows = conn.execute("""
        SELECT p.* FROM patients p
        INNER JOIN teacher_students ts ON p.name = ts.student_name
        WHERE ts.teacher_name = ?
    """, (teacher_name,)).fetchall()
    conn.close()
    return [dict(r) for r in rows]

def get_student_teachers(student_name):
    """学生端：查看我的老师"""
    conn = get_connection()
    rows = conn.execute("SELECT teacher_name FROM teacher_students WHERE student_name = ?", (student_name,)).fetchall()
    conn.close()
    return [r["teacher_name"] for r in rows]

def add_teacher_student(teacher_name, student_name):
    """老师添加学生（学生不存在时自动创建基础档案）"""
    conn = get_connection()
    # 自动创建患者账号（如果还没有）
    conn.execute("INSERT OR IGNORE INTO patients (name, teacher_name, guardian_name, relation) VALUES (?, ?, ?, ?)",
                 (student_name, teacher_name, "self", "本人"))
    try:
        conn.execute("INSERT INTO teacher_students (teacher_name, student_name, created_at) VALUES (?, ?, ?)",
                     (teacher_name, student_name, "2026-09-15"))
        conn.commit()
        conn.close()
        return {"message": "学生已添加"}
    except sqlite3.IntegrityError:
        conn.close()
        return {"error": "该学生已在您名下"}

def remove_teacher_student(teacher_name, student_name):
    """老师踢出学生"""
    conn = get_connection()
    conn.execute("DELETE FROM teacher_students WHERE teacher_name = ? AND student_name = ?",
                 (teacher_name, student_name))
    conn.commit()
    conn.close()
    return {"message": "学生已移除"}

def leave_teacher(student_name, teacher_name):
    """学生退出某位老师"""
    conn = get_connection()
    conn.execute("DELETE FROM teacher_students WHERE teacher_name = ? AND student_name = ?",
                 (teacher_name, student_name))
    conn.commit()
    conn.close()
    return {"message": "已退出该老师"}

# ---------- 患者相关操作 ----------
def get_patients(guardian_name=None):
    conn = get_connection()
    if guardian_name:
        rows = conn.execute("SELECT * FROM patients WHERE name = ? OR guardian_name = ?", (guardian_name, guardian_name)).fetchall()
    else:
        rows = conn.execute("SELECT * FROM patients").fetchall()
    conn.close()
    return [dict(r) for r in rows]

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

def delete_patient(name):
    conn = get_connection()
    for table in ["patients", "teacher_students", "patient_profiles", "homework", "transcriptions", "drafts", "patient_records", "accounts"]:
        col = "role_name" if table == "accounts" else ("student_name" if table == "teacher_students" else ("patient_name" if table != "patients" else "name"))
        conn.execute(f"DELETE FROM {table} WHERE {col} = ?", (name,))
    conn.commit()
    conn.close()

def get_patient_profile(patient_name):
    conn = get_connection()
    row = conn.execute("SELECT * FROM patient_profiles WHERE patient_name = ?", (patient_name,)).fetchone()
    conn.close()
    if row:
        return dict(row)
    return {"patient_name": patient_name, "gender": "", "birth_date": "", "birth_time": "", "birth_place": "", "location": ""}

def save_patient_profile(patient_name, gender, birth_date, birth_time, birth_place, location):
    conn = get_connection()
    existing = conn.execute("SELECT * FROM patient_profiles WHERE patient_name = ?", (patient_name,)).fetchone()
    if existing:
        new_gender = existing["gender"] if existing["gender"] else gender
        new_birth_date = existing["birth_date"] if existing["birth_date"] else birth_date
        new_birth_time = existing["birth_time"] if existing["birth_time"] else birth_time
        new_birth_place = birth_place if birth_place else existing["birth_place"]
        new_location = location
        conn.execute("""
        UPDATE patient_profiles SET gender = ?, birth_date = ?, birth_time = ?, birth_place = ?, location = ? WHERE patient_name = ?
        """, (new_gender, new_birth_date, new_birth_time, new_birth_place, new_location, patient_name))
    else:
        conn.execute("""
        INSERT INTO patient_profiles (patient_name, gender, birth_date, birth_time, birth_place, location)
        VALUES (?, ?, ?, ?, ?, ?)
        """, (patient_name, gender, birth_date, birth_time, birth_place, location))
    conn.commit()
    conn.close()

# ---------- 作业 ----------
def get_homework(patient_name, teacher_name="李老师"):
    conn = get_connection()
    row = conn.execute("SELECT * FROM homework WHERE patient_name = ? AND teacher_name = ? ORDER BY id DESC LIMIT 1",
                       (patient_name, teacher_name)).fetchone()
    conn.close()
    return dict(row) if row else None

def create_homework(patient_name, teacher_name, task, detail):
    conn = get_connection()
    conn.execute("INSERT INTO homework (patient_name, teacher_name, task, detail, status, created_at) VALUES (?, ?, ?, ?, ?, ?)",
                 (patient_name, teacher_name, task, detail, "pending", "2026-09-15"))
    conn.commit()
    conn.close()

def update_homework_status(patient_name, teacher_name, status):
    conn = get_connection()
    conn.execute("UPDATE homework SET status = ? WHERE id = (SELECT MAX(id) FROM homework WHERE patient_name = ? AND teacher_name = ?)",
                 (status, patient_name, teacher_name))
    conn.commit()
    conn.close()

# ---------- 转述 ----------
def insert_transcription(patient_name, teacher_name, content, data_type):
    conn = get_connection()
    conn.execute("INSERT INTO transcriptions (patient_name, teacher_name, content, data_type, processed) VALUES (?, ?, ?, ?, 0)",
                 (patient_name, teacher_name, content, data_type))
    conn.commit()
    conn.close()

def get_transcriptions(patient_name=None, teacher_name=None):
    conn = get_connection()
    conditions = ["processed = 0"]
    params = []
    if patient_name:
        conditions.append("patient_name = ?")
        params.append(patient_name)
    if teacher_name:
        conditions.append("teacher_name = ?")
        params.append(teacher_name)
    query = f"SELECT * FROM transcriptions WHERE {' AND '.join(conditions)} ORDER BY id DESC"
    rows = conn.execute(query, params).fetchall()
    conn.close()
    return [dict(r) for r in rows]

# ---------- 病历草案 ----------
def insert_draft(transcript_id, patient_name, teacher_name, content):
    conn = get_connection()
    cursor = conn.execute("INSERT INTO drafts (transcript_id, patient_name, teacher_name, content, signed) VALUES (?, ?, ?, ?, ?)",
                          (transcript_id, patient_name, teacher_name, content, 0))
    conn.execute("UPDATE transcriptions SET processed = 1 WHERE id = ?", (transcript_id,))
    conn.commit()
    draft_id = cursor.lastrowid
    conn.close()
    return draft_id

def get_drafts(teacher_name=None):
    conn = get_connection()
    if teacher_name:
        rows = conn.execute("SELECT * FROM drafts WHERE signed = 0 AND teacher_name = ?", (teacher_name,)).fetchall()
    else:
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

    conn.execute("INSERT INTO patient_records (patient_name, teacher_name, ai_draft, final_plan, doctor) VALUES (?, ?, ?, ?, ?)",
                 (draft["patient_name"], draft["teacher_name"], draft["content"], final_plan, draft["teacher_name"]))
    conn.execute("INSERT INTO homework (patient_name, teacher_name, task, detail, status, created_at) VALUES (?, ?, ?, ?, ?, ?)",
                 (draft["patient_name"], draft["teacher_name"], f"今日医嘱：{final_plan}", "请严格遵医嘱执行", "pending", "2026-09-15"))
    conn.execute("DELETE FROM transcriptions WHERE id = ?", (draft["transcript_id"],))
    conn.execute("DELETE FROM drafts WHERE id = ?", (draft_id,))
    
    conn.commit()
    conn.close()
    return draft["patient_name"]

# ---------- 患者健康档案 ----------
def get_patient_records(patient_name=None, teacher_name=None):
    conn = get_connection()
    conditions = []
    params = []
    if patient_name:
        conditions.append("patient_name = ?")
        params.append(patient_name)
    if teacher_name:
        conditions.append("teacher_name = ?")
        params.append(teacher_name)
    where = f"WHERE {' AND '.join(conditions)}" if conditions else ""
    query = f"SELECT * FROM patient_records {where} ORDER BY id DESC"
    rows = conn.execute(query, params).fetchall()
    conn.close()
    return [dict(r) for r in rows]

# ---------- 积分 ----------
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