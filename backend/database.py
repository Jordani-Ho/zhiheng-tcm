import sqlite3
import os
from datetime import datetime, timedelta
DB_PATH = os.path.join(os.path.dirname(__file__), os.environ.get("ZHIENG_DB", "zhiheng.db"))


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

       # 【第48天新增】老师工作时间设置（work_schedule 存 JSON）
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS teacher_settings (
        teacher_name TEXT PRIMARY KEY,
        work_days TEXT DEFAULT '1,2,3,4,5',
        work_hours TEXT DEFAULT '9,10,11,14,15,16',
        work_schedule TEXT DEFAULT '',
        holidays TEXT DEFAULT '[]'
    )
    """)
    # 【第49天新增】如果表已存在，尝试加 holidays 字段
    try:
        cursor.execute("ALTER TABLE teacher_settings ADD COLUMN holidays TEXT DEFAULT '[]'")
    except sqlite3.OperationalError:
        pass
    cursor.execute("SELECT COUNT(*) as count FROM teacher_settings WHERE teacher_name = '李老师'")
    if cursor.fetchone()["count"] == 0:
        cursor.execute("INSERT INTO teacher_settings (teacher_name, work_days, work_hours, work_schedule, holidays) VALUES ('李老师', '1,2,3,4,5', '9,10,11,14,15,16', '', '[]')")

    # 【第47天新增】预约表
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS appointments (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        patient_name TEXT,
        teacher_name TEXT,
        initiator TEXT,
        scheduled_date TEXT,
        scheduled_time TEXT,
        reason TEXT,
        status TEXT DEFAULT 'pending',
        created_at TEXT,
        confirmed_at TEXT
    )
    """)

    # 【第46天新增】病历标签表（知识库素材）
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS record_tags (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        record_id INTEGER,
        teacher_name TEXT,
        tag_type TEXT,
        tag_value TEXT,
        created_at TEXT
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
    # 【第51天新增】中药材库存表
    init_herb_table()

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
    rows = conn.execute("""
        SELECT p.name, p.last_active_at,
               COALESCE(a.points, 0) as points
        FROM patients p
        INNER JOIN patient_teachers pt ON p.name = pt.patient_name
        LEFT JOIN accounts a ON p.name = a.role_name
        WHERE pt.teacher_name = ? AND pt.status = 'active'
        ORDER BY p.name
    """, (teacher_name,)).fetchall()
    conn.close()
    return [dict(r) for r in rows]

def get_student_status(patient_name):
    """【第44天新增】根据最后活跃时间 + 积分，返回学生状态"""
    conn = get_connection()
    row = conn.execute("SELECT last_active_at FROM patients WHERE name = ?", (patient_name,)).fetchone()
    pts_row = conn.execute("SELECT points FROM accounts WHERE role_name = ?", (patient_name,)).fetchone()
    conn.close()

    points = pts_row["points"] if pts_row else 0
    last_active = row["last_active_at"] if row else None

    # 积分规则
    if points <= 0:
        return {"status": "warning", "label": "欠费预警", "color": "#c0392b"}
    if points < 30:
        return {"status": "low", "label": "余额偏低", "color": "#e67e22"}

    # 活跃度规则
    if not last_active:
        return {"status": "silent", "label": "从未活跃", "color": "#999"}
    try:
        last_dt = datetime.strptime(last_active, "%Y-%m-%d")
        days = (datetime.now() - last_dt).days
        if days >= 30:
            return {"status": "silent", "label": f"沉默 {days} 天", "color": "#999"}
        if days >= 14:
            return {"status": "inactive", "label": f"{days} 天未活跃", "color": "#e67e22"}
    except Exception:
        pass

    return {"status": "active", "label": "活跃", "color": "#5a7d5a"}

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

def sign_draft(draft_id, final_plan, final_content=None):
    """【第45天修改】签字时同时保存 AI 原草案与老师最终版（学习轨迹）"""
    conn = get_connection()
    draft = conn.execute("SELECT * FROM drafts WHERE id = ?", (draft_id,)).fetchone()
    if not draft:
        conn.close()
        return None

    # 完整病历（如果传了）或退回到最终方案
    patient_record_content = final_content if final_content else final_plan

    conn.execute(
        "INSERT INTO patient_records (patient_name, teacher_name, ai_draft, final_plan, doctor) VALUES (?, ?, ?, ?, ?)",
        (draft["patient_name"], draft["teacher_name"], draft["content"], patient_record_content, draft["teacher_name"])
    )
    conn.execute(
        "INSERT INTO homework (patient_name, teacher_name, task, detail, status, created_at) VALUES (?, ?, ?, ?, ?, ?)",
        (draft["patient_name"], draft["teacher_name"], f"今日医嘱：{final_plan}", "请严格遵医嘱执行", "pending", "2026-09-19")
    )
    conn.execute("DELETE FROM transcriptions WHERE id = ?", (draft["transcript_id"],))
    conn.execute("DELETE FROM drafts WHERE id = ?", (draft_id,))

    conn.commit()
    conn.close()
    return draft["patient_name"]

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
# ---------- 【第48天扩展】老师工作时间（按天 + 半小时粒度） ----------
import json

def get_teacher_holidays(teacher_name):
    """【第49天新增】获取老师节假日列表"""
    conn = get_connection()
    row = conn.execute("SELECT holidays FROM teacher_settings WHERE teacher_name = ?", (teacher_name,)).fetchone()
    conn.close()
    if not row or not row["holidays"]:
        return []
    try:
        return json.loads(row["holidays"])
    except Exception:
        return []

def save_teacher_holidays(teacher_name, holidays):
    """【第49天新增】保存老师节假日列表"""
    conn = get_connection()
    conn.execute("""
        INSERT INTO teacher_settings (teacher_name, holidays) VALUES (?, ?)
        ON CONFLICT(teacher_name) DO UPDATE SET holidays = excluded.holidays
    """, (teacher_name, json.dumps(holidays)))
    conn.commit()
    conn.close()
    return {"message": "节假日已保存"}

# ---------- 【第48天扩展】老师工作时间（按天 + 半小时粒度） ----------
ALL_SLOTS = [
    "08:00","08:30","09:00","09:30","10:00","10:30","11:00","11:30",
    "12:00","12:30","13:00","13:30","14:00","14:30","15:00","15:30",
    "16:00","16:30","17:00","17:30","18:00","18:30","19:00","19:30","20:00"
]

def _default_schedule():
    weekday_slots = [s for s in ALL_SLOTS if ("09:00" <= s <= "11:30") or ("14:00" <= s <= "16:30")]
    return {
        "0": [],
        "1": list(weekday_slots),
        "2": list(weekday_slots),
        "3": list(weekday_slots),
        "4": list(weekday_slots),
        "5": list(weekday_slots),
        "6": []
    }

def get_teacher_schedule(teacher_name):
    """返回该老师按天划分的半小时时段"""
    conn = get_connection()
    row = conn.execute("SELECT * FROM teacher_settings WHERE teacher_name = ?", (teacher_name,)).fetchone()
    conn.close()
    if not row:
        return _default_schedule()
    d = dict(row)
    if d.get("work_schedule"):
        try:
            parsed = json.loads(d["work_schedule"])
            for k in ["0","1","2","3","4","5","6"]:
                if k not in parsed:
                    parsed[k] = []
            return parsed
        except Exception:
            pass
    days = [int(x) for x in d["work_days"].split(",") if x]
    hours = [int(x) for x in d["work_hours"].split(",") if x]
    slots = []
    for h in hours:
        slots.append(f"{h:02d}:00")
        slots.append(f"{h:02d}:30")
    schedule = {}
    for day in range(7):
        schedule[str(day)] = list(slots) if day in days else []
    return schedule

def save_teacher_schedule(teacher_name, schedule):
    conn = get_connection()
    conn.execute("""
        INSERT INTO teacher_settings (teacher_name, work_schedule) VALUES (?, ?)
        ON CONFLICT(teacher_name) DO UPDATE SET work_schedule = excluded.work_schedule
    """, (teacher_name, json.dumps(schedule)))
    conn.commit()
    conn.close()
    return {"message": "工作时间已保存"}

# ---------- 老师工作时间 ----------
def get_teacher_settings(teacher_name):
    conn = get_connection()
    row = conn.execute("SELECT * FROM teacher_settings WHERE teacher_name = ?", (teacher_name,)).fetchone()
    conn.close()
    if not row:
        return {"teacher_name": teacher_name, "work_days": "1,2,3,4,5", "work_hours": "9,10,11,14,15,16"}
    d = dict(row)
    d["work_days_list"] = [int(x) for x in d["work_days"].split(",") if x]
    d["work_hours_list"] = [int(x) for x in d["work_hours"].split(",") if x]
    return d

def save_teacher_settings(teacher_name, work_days, work_hours):
    conn = get_connection()
    conn.execute("""
        INSERT INTO teacher_settings (teacher_name, work_days, work_hours) VALUES (?, ?, ?)
        ON CONFLICT(teacher_name) DO UPDATE SET work_days = excluded.work_days, work_hours = excluded.work_hours
    """, (teacher_name, work_days, work_hours))
    conn.commit()
    conn.close()
    return {"message": "工作时间已保存"}

# ---------- 预约相关操作 ----------
def get_appointments(patient_name=None, teacher_name=None, start_date=None, end_date=None):
    conn = get_connection()
    conditions = []
    params = []
    if patient_name:
        conditions.append("patient_name = ?")
        params.append(patient_name)
    if teacher_name:
        conditions.append("teacher_name = ?")
        params.append(teacher_name)
    if start_date:
        conditions.append("scheduled_date >= ?")
        params.append(start_date)
    if end_date:
        conditions.append("scheduled_date <= ?")
        params.append(end_date)
    where = f"WHERE {' AND '.join(conditions)}" if conditions else ""
    rows = conn.execute(f"SELECT * FROM appointments {where} ORDER BY scheduled_date, scheduled_time", params).fetchall()
    conn.close()
    return [dict(r) for r in rows]


def check_slot_available(teacher_name, scheduled_date, scheduled_time, exclude_appt_id=None):
    """【第49天新增】检查某个时段是否已被预约"""
    conn = get_connection()
    if exclude_appt_id:
        row = conn.execute("""
            SELECT COUNT(*) as count FROM appointments
            WHERE teacher_name = ? AND scheduled_date = ? AND scheduled_time = ?
              AND status != 'cancelled' AND id != ?
        """, (teacher_name, scheduled_date, scheduled_time, exclude_appt_id)).fetchone()
    else:
        row = conn.execute("""
            SELECT COUNT(*) as count FROM appointments
            WHERE teacher_name = ? AND scheduled_date = ? AND scheduled_time = ?
              AND status != 'cancelled'
        """, (teacher_name, scheduled_date, scheduled_time)).fetchone()
    conn.close()
    return row["count"] == 0


def create_appointment(patient_name, teacher_name, initiator, scheduled_date, scheduled_time, reason):
    # 【第49天新增】先检查冲突
    if not check_slot_available(teacher_name, scheduled_date, scheduled_time):
        return {"error": "该时段已被预约，请选择其他时间"}
    conn = get_connection()
    conn.execute(
        "INSERT INTO appointments (patient_name, teacher_name, initiator, scheduled_date, scheduled_time, reason, status, created_at) VALUES (?, ?, ?, ?, ?, ?, 'pending', ?)",
        (patient_name, teacher_name, initiator, scheduled_date, scheduled_time, reason, "2026-09-21")
    )
    conn.commit()
    conn.close()
    return {"message": "预约已提交"}

def update_appointment_status(appt_id, status):
    conn = get_connection()
    conn.execute("UPDATE appointments SET status = ?, confirmed_at = ? WHERE id = ?",
                 (status, "2026-09-20", appt_id))
    conn.commit()
    conn.close()
    return {"message": "预约状态已更新"}

# ---------- 标签/知识库相关操作 ----------
def insert_tag(record_id, teacher_name, tag_type, tag_value):
    conn = get_connection()
    conn.execute(
        "INSERT INTO record_tags (record_id, teacher_name, tag_type, tag_value, created_at) VALUES (?, ?, ?, ?, ?)",
        (record_id, teacher_name, tag_type, tag_value, "2026-09-20")
    )
    conn.commit()
    conn.close()

def get_tags_for_record(record_id):
    conn = get_connection()
    rows = conn.execute("SELECT * FROM record_tags WHERE record_id = ?", (record_id,)).fetchall()
    conn.close()
    return [dict(r) for r in rows]

def get_teacher_tags_summary(teacher_name):
    """返回该老师所有标签的汇总（用于知识库视图）"""
    conn = get_connection()
    rows = conn.execute("""
        SELECT tag_type, tag_value, COUNT(*) as count
        FROM record_tags
        WHERE teacher_name = ?
        GROUP BY tag_type, tag_value
        ORDER BY count DESC
    """, (teacher_name,)).fetchall()
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
    # ============ 中药材库存管理 ============

def init_herb_table():
    """建表语句，需要在现有的建表初始化流程里调用一次（和其他15张表的建表放在一起）。"""
    conn = get_connection()
    cur = conn.cursor()
    cur.execute("CREATE TABLE IF NOT EXISTS herb_inventory (id INTEGER PRIMARY KEY AUTOINCREMENT, teacher_name TEXT, herb_name TEXT, stock_amount REAL DEFAULT 0, unit TEXT DEFAULT '克', warn_threshold REAL DEFAULT 50, updated_at TEXT, UNIQUE(teacher_name, herb_name))")
    conn.commit()
    conn.close()


def _herb_row_to_dict(row):
    """内部工具函数：把一行 herb_inventory 转成带 is_low 字段的 dict。"""
    d = dict(row)
    d["is_low"] = d["stock_amount"] <= d["warn_threshold"]
    return d


def get_herbs(teacher_name):
    conn = get_connection()
    cur = conn.cursor()
    cur.execute("SELECT * FROM herb_inventory WHERE teacher_name = ? ORDER BY herb_name", (teacher_name,))
    rows = cur.fetchall()
    conn.close()
    return [_herb_row_to_dict(r) for r in rows]


def upsert_herb(teacher_name, herb_name, stock_amount, unit, warn_threshold):
    conn = get_connection()
    cur = conn.cursor()
    now = datetime.now().isoformat()
    cur.execute("SELECT id FROM herb_inventory WHERE teacher_name = ? AND herb_name = ?", (teacher_name, herb_name))
    existing = cur.fetchone()
    if existing:
        cur.execute("UPDATE herb_inventory SET stock_amount = ?, unit = ?, warn_threshold = ?, updated_at = ? WHERE id = ?", (stock_amount, unit, warn_threshold, now, existing["id"]))
        herb_id = existing["id"]
    else:
        cur.execute("INSERT INTO herb_inventory (teacher_name, herb_name, stock_amount, unit, warn_threshold, updated_at) VALUES (?, ?, ?, ?, ?, ?)", (teacher_name, herb_name, stock_amount, unit, warn_threshold, now))
        herb_id = cur.lastrowid
    conn.commit()
    cur.execute("SELECT * FROM herb_inventory WHERE id = ?", (herb_id,))
    row = cur.fetchone()
    conn.close()
    return _herb_row_to_dict(row)


def adjust_herb(herb_id, delta):
    """delta 正数入库，负数出库。不允许调整后 stock_amount < 0，此时抛出 ValueError（由 main.py 捕获并返回 400）。"""
    conn = get_connection()
    cur = conn.cursor()
    cur.execute("SELECT * FROM herb_inventory WHERE id = ?", (herb_id,))
    row = cur.fetchone()
    if row is None:
        conn.close()
        return None
    new_amount = row["stock_amount"] + delta
    if new_amount < 0:
        conn.close()
        raise ValueError("库存不足，无法调整：" + row["herb_name"])
    now = datetime.now().isoformat()
    cur.execute("UPDATE herb_inventory SET stock_amount = ?, updated_at = ? WHERE id = ?", (new_amount, now, herb_id))
    conn.commit()
    cur.execute("SELECT * FROM herb_inventory WHERE id = ?", (herb_id,))
    updated = cur.fetchone()
    conn.close()
    return _herb_row_to_dict(updated)


def delete_herb(herb_id):
    conn = get_connection()
    cur = conn.cursor()
    cur.execute("SELECT id FROM herb_inventory WHERE id = ?", (herb_id,))
    existing = cur.fetchone()
    if existing is None:
        conn.close()
        return False
    cur.execute("DELETE FROM herb_inventory WHERE id = ?", (herb_id,))
    conn.commit()
    conn.close()
    return True


def get_low_herbs(teacher_name):
    conn = get_connection()
    cur = conn.cursor()
    cur.execute("SELECT * FROM herb_inventory WHERE teacher_name = ? AND stock_amount <= warn_threshold ORDER BY herb_name", (teacher_name,))
    rows = cur.fetchall()
    conn.close()
    return [_herb_row_to_dict(r) for r in rows]


def batch_deduct_herbs(teacher_name, items):
    """原子批量扣减：先逐一检查库存是否充足，任一不足则整体失败、不做任何修改；全部充足才真正执行扣减。"""
    conn = get_connection()
    cur = conn.cursor()

    checked = []
    for item in items:
        herb_name = item["herb_name"]
        amount = item["amount"]
        cur.execute("SELECT * FROM herb_inventory WHERE teacher_name = ? AND herb_name = ?", (teacher_name, herb_name))
        row = cur.fetchone()
        if row is None or row["stock_amount"] < amount:
            conn.close()
            return {"success": False, "failed_herb": herb_name}
        checked.append((row["id"], row["stock_amount"], amount))

    now = datetime.now().isoformat()
    for herb_id, current_amount, amount in checked:
        new_amount = current_amount - amount
        cur.execute("UPDATE herb_inventory SET stock_amount = ?, updated_at = ? WHERE id = ?", (new_amount, now, herb_id))
    conn.commit()
    conn.close()
    return {"success": True, "failed_herb": None}