import sqlite3
import os
from datetime import datetime, timedelta

DB_PATH = os.path.join(os.path.dirname(__file__), "zhiheng.db")

def get_connection():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn

def init_db():
    conn = get_connection()
    cursor = conn.cursor()

    # 1. 老师表（预留治理字段）
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS teachers (
        name TEXT PRIMARY KEY,
        description TEXT DEFAULT '',
        status TEXT DEFAULT 'active',
        last_active_at TEXT,
        complaint_count INTEGER DEFAULT 0,
        created_at TEXT
    )
    """)

    # 2. 患者表
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS patients (
        name TEXT PRIMARY KEY,
        guardian_name TEXT DEFAULT 'self',
        relation TEXT DEFAULT '本人',
        created_at TEXT
    )
    """)

    # 3. 师生关系表（核心）
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS patient_teachers (
        patient_name TEXT,
        teacher_name TEXT,
        status TEXT DEFAULT 'active',
        created_at TEXT,
        PRIMARY KEY (patient_name, teacher_name)
    )
    """)

    # 4. 患者基础档案表
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
        teacher_name TEXT,
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
        teacher_name TEXT,
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
        teacher_name TEXT,
        content TEXT,
        signed INTEGER
    )
    """)

    # 8. 患者健康档案表
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS patient_records (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        patient_name TEXT,
        teacher_name TEXT,
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

    # 【第38天新增】邀请码表
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS invites (
        code TEXT PRIMARY KEY,
        teacher_name TEXT,
        created_at TEXT,
        expires_at TEXT,
        used_by TEXT,
        used_at TEXT
    )
    """)

    # 10. 【预留】投诉表
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS complaints (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        teacher_name TEXT,
        patient_name TEXT,
        content TEXT,
        created_at TEXT
    )
    """)

    conn.commit()

    # 初始化默认数据
    cursor.execute("SELECT COUNT(*) as count FROM teachers")
    if cursor.fetchone()["count"] == 0:
        cursor.execute("INSERT INTO teachers (name, description, status, last_active_at, created_at) VALUES (?, ?, ?, ?, ?)",
                       ("李老师", "民间中医高手", "active", "2026-09-16", "2026-09-16"))
        conn.commit()

    cursor.execute("SELECT COUNT(*) as count FROM patients")
    if cursor.fetchone()["count"] == 0:
        cursor.execute("INSERT INTO patients (name, guardian_name, relation, created_at) VALUES (?, ?, ?, ?)", ("张三", "self", "本人", "2026-09-16"))
        cursor.execute("INSERT INTO patients (name, guardian_name, relation, created_at) VALUES (?, ?, ?, ?)", ("李四", "self", "本人", "2026-09-16"))
        conn.commit()

    cursor.execute("SELECT COUNT(*) as count FROM patient_teachers")
    if cursor.fetchone()["count"] == 0:
        cursor.execute("INSERT INTO patient_teachers (patient_name, teacher_name, status, created_at) VALUES (?, ?, ?, ?)", ("张三", "李老师", "active", "2026-09-16"))
        cursor.execute("INSERT INTO patient_teachers (patient_name, teacher_name, status, created_at) VALUES (?, ?, ?, ?)", ("李四", "李老师", "active", "2026-09-16"))
        conn.commit()

    cursor.execute("SELECT COUNT(*) as count FROM homework")
    if cursor.fetchone()["count"] == 0:
        cursor.execute("INSERT INTO homework (patient_name, teacher_name, task, detail, status, created_at) VALUES (?, ?, ?, ?, ?, ?)",
                       ("张三", "李老师", "今日作业：按揉太渊穴5分钟", "请记得在酉时完成。", "pending", "2026-09-16"))
        conn.commit()
    # 【第35天新增】给 patients 表加 last_active_at 字段，用于学生状态判断
    try:
        cursor.execute("ALTER TABLE patients ADD COLUMN last_active_at TEXT")
    except sqlite3.OperationalError:
        pass  # 字段已存在
    
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
def get_patient_teachers(patient_name):
    conn = get_connection()
    rows = conn.execute("SELECT teacher_name FROM patient_teachers WHERE patient_name = ? AND status = 'active'", (patient_name,)).fetchall()
    conn.close()
    return [r["teacher_name"] for r in rows]

def get_teacher_patients(teacher_name):
    conn = get_connection()
    rows = conn.execute("SELECT patient_name FROM patient_teachers WHERE teacher_name = ? AND status = 'active'", (teacher_name,)).fetchall()
    conn.close()
    return [r["patient_name"] for r in rows]

def add_patient_teacher(patient_name, teacher_name):
    conn = get_connection()
    existing = conn.execute("SELECT COUNT(*) as count FROM patient_teachers WHERE patient_name = ? AND status = 'active'", (patient_name,)).fetchone()
    if existing["count"] >= 3:
        conn.close()
        return {"error": "最多只能同时咨询 3 位老师"}
    try:
        conn.execute("INSERT INTO patient_teachers (patient_name, teacher_name, status, created_at) VALUES (?, ?, ?, ?)",
                     (patient_name, teacher_name, "active", "2026-09-16"))
        conn.commit()
        conn.close()
        return {"message": "已添加"}
    except sqlite3.IntegrityError:
        conn.close()
        return {"error": "该老师已在您的咨询列表中"}
    
# 【第34天新增】老师拉学生：创建学生账户并建立师生关系
def teacher_add_student(teacher_name, student_name):
    conn = get_connection()
    # 1. 创建学生账户（如果不存在）
    conn.execute("INSERT OR IGNORE INTO patients (name, guardian_name, relation, created_at) VALUES (?, 'self', '本人', ?)",
                 (student_name, "2026-09-17"))
    # 2. 建立师生关系
    try:
        conn.execute("INSERT INTO patient_teachers (patient_name, teacher_name, status, created_at) VALUES (?, ?, 'active', ?)",
                     (student_name, teacher_name, "2026-09-17"))
    except sqlite3.IntegrityError:
        pass  # 关系已存在
    # 3. 给新学生一个初始积分（如果账户不存在）
    conn.execute("INSERT OR IGNORE INTO accounts (role_name, points) VALUES (?, 100)", (student_name,))
    conn.commit()
    conn.close()
    return {"message": "学生添加成功"}    

def remove_patient_teacher(patient_name, teacher_name):
    conn = get_connection()
    conn.execute("UPDATE patient_teachers SET status = 'inactive' WHERE patient_name = ? AND teacher_name = ?", (patient_name, teacher_name))
    conn.commit()
    conn.close()
    return {"message": "已移除"}

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
    conn.execute("INSERT OR IGNORE INTO patients (name, guardian_name, relation, created_at) VALUES (?, ?, ?, ?)", 
                 (name, guardian_name, relation, "2026-09-16"))
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
    for table in ["patients", "patient_teachers", "patient_profiles", "homework", "transcriptions", "drafts", "patient_records", "accounts"]:
        col = "role_name" if table == "accounts" else ("patient_name" if table != "patients" else "name")
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

# ---------- 作业相关操作 ----------
def get_homework(patient_name, teacher_name):
    conn = get_connection()
    row = conn.execute("SELECT * FROM homework WHERE patient_name = ? AND teacher_name = ? ORDER BY id DESC LIMIT 1",
                       (patient_name, teacher_name)).fetchone()
    conn.close()
    return dict(row) if row else None

def create_homework(patient_name, teacher_name, task, detail):
    conn = get_connection()
    conn.execute("INSERT INTO homework (patient_name, teacher_name, task, detail, status, created_at) VALUES (?, ?, ?, ?, ?, ?)",
                 (patient_name, teacher_name, task, detail, "pending", "2026-09-16"))
    conn.commit()
    conn.close()

def update_homework_status(patient_name, teacher_name, status):
    conn = get_connection()
    conn.execute("UPDATE homework SET status = ? WHERE id = (SELECT MAX(id) FROM homework WHERE patient_name = ? AND teacher_name = ?)",
                 (status, patient_name, teacher_name))
    # 【第35天新增】更新学生的最近活跃时间
    conn.execute("UPDATE patients SET last_active_at = ? WHERE name = ?", ("2026-09-17", patient_name))
    conn.commit()
    conn.close()

# ---------- 转述相关操作 ----------
def insert_transcription(patient_name, teacher_name, content, data_type):
    conn = get_connection()
    conn.execute("INSERT INTO transcriptions (patient_name, teacher_name, content, data_type, processed) VALUES (?, ?, ?, ?, 0)",
                 (patient_name, teacher_name, content, data_type))
    # 【第35天新增】更新学生的最近活跃时间
    conn.execute("UPDATE patients SET last_active_at = ? WHERE name = ?", ("2026-09-17", patient_name))
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

# ---------- 病历草案相关操作 ----------
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
        rows = conn.execute("""
            SELECT d.* FROM drafts d
            INNER JOIN (
                SELECT patient_name, MAX(id) as max_id
                FROM drafts WHERE signed = 0 AND teacher_name = ?
                GROUP BY patient_name
            ) latest ON d.id = latest.max_id
        """, (teacher_name,)).fetchall()
    else:
        rows = conn.execute("""
            SELECT d.* FROM drafts d
            INNER JOIN (
                SELECT patient_name, MAX(id) as max_id
                FROM drafts WHERE signed = 0
                GROUP BY patient_name
            ) latest ON d.id = latest.max_id
        """).fetchall()
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
                 (draft["patient_name"], draft["teacher_name"], f"今日医嘱：{final_plan}", "请严格遵医嘱执行", "pending", "2026-09-16"))
    conn.execute("DELETE FROM transcriptions WHERE id = ?", (draft["transcript_id"],))
    conn.execute("DELETE FROM drafts WHERE id = ?", (draft_id,))
    
    conn.commit()
    conn.close()
    return draft["patient_name"]

# ---------- 患者健康档案相关操作 ----------
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

# ---------- 邀请码相关操作 ----------
def create_invite(code, teacher_name):
    conn = get_connection()
    now = datetime.now()
    expires = (now + timedelta(days=7)).strftime('%Y-%m-%d %H:%M:%S')
    conn.execute("INSERT INTO invites (code, teacher_name, created_at, expires_at) VALUES (?, ?, ?, ?)",
                 (code, teacher_name, now.strftime('%Y-%m-%d %H:%M:%S'), expires))
    conn.commit()
    conn.close()

def get_invites(teacher_name):
    conn = get_connection()
    rows = conn.execute("SELECT * FROM invites WHERE teacher_name = ? ORDER BY created_at DESC", (teacher_name,)).fetchall()
    conn.close()
    return [dict(r) for r in rows]

def accept_invite(code, student_name):
    conn = get_connection()
    invite = conn.execute("SELECT * FROM invites WHERE code = ?", (code,)).fetchone()
    if not invite:
        conn.close()
        return {"error": "邀请码不存在"}
    if invite["used_by"]:
        conn.close()
        return {"error": "邀请码已被使用"}
    if invite["expires_at"] < datetime.now().strftime('%Y-%m-%d %H:%M:%S'):
        conn.close()
        return {"error": "邀请码已过期"}

    # 创建学生账户
    conn.execute("INSERT OR IGNORE INTO patients (name, guardian_name, relation, created_at) VALUES (?, 'self', '本人', ?)",
                 (student_name, datetime.now().strftime('%Y-%m-%d')))
    # 建立师生关系
    try:
        conn.execute("INSERT INTO patient_teachers (patient_name, teacher_name, status, created_at) VALUES (?, ?, 'active', ?)",
                     (student_name, invite["teacher_name"], datetime.now().strftime('%Y-%m-%d')))
    except sqlite3.IntegrityError:
        pass
    # 初始积分
    conn.execute("INSERT OR IGNORE INTO accounts (role_name, points) VALUES (?, 100)", (student_name,))
    # 标记邀请码已使用
    conn.execute("UPDATE invites SET used_by = ?, used_at = ? WHERE code = ?",
                 (student_name, datetime.now().strftime('%Y-%m-%d %H:%M:%S'), code))
    conn.commit()
    conn.close()
    return {"message": "加入成功", "teacher_name": invite["teacher_name"]}

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