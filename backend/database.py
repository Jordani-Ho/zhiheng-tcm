import sqlite3
import os
import json
import re
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
        doctor TEXT,
        visit_at TEXT  -- 【第77天新增】就诊时间（ISO 时间戳，如 2026-09-23T15:30:00）：老师签字落库时写入，供「复诊提醒」扫描用
    )
    """)
    # 【第77天新增】如果表已存在（旧库），补加 visit_at 字段：老记录留空串（= 没有就诊时间基准，
    # agent.check_recall_alerts 会整条跳过），不破坏已有数据；重复执行 / 列已存在时报 OperationalError，跳过即可。
    try:
        cursor.execute("ALTER TABLE patient_records ADD COLUMN visit_at TEXT DEFAULT ''")
    except sqlite3.OperationalError:
        pass  # 字段已存在

    # 9. 积分账户表
    # 【第65天修改】表名冲突处理：accounts 这个名字要让给财务管理的新账户表
    # （id / username / role / balance / updated_at），所以老的"积分账户表"统一改名成
    # points_accounts。老库（accounts 里存 role_name/points）的数据由
    # init_finance_tables() 里的自动迁移原样搬过来，不会丢数据。
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS points_accounts (
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
        confirmed_at TEXT,
        is_remote INTEGER DEFAULT 0  -- 【第73天新增】0=当面诊疗 1=远程问诊（视频/线上），与 prescriptions.is_remote 同一套语义
    )
    """)
    # 【第73天新增】如果表已存在（旧表），尝试补加 is_remote 字段（老库自动迁移，重复执行不报错）
    try:
        cursor.execute("ALTER TABLE appointments ADD COLUMN is_remote INTEGER DEFAULT 0")
    except sqlite3.OperationalError:
        pass

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

    # 10. 【预留】投诉表 / 学生陈述表
    # 【第82天启用】学生「十问歌」面诊前准备摘要由 agent.save_intake() 写进本表（status='pending'），
    # 老师端诊室页「📝 待处理陈述」卡片读本表；点「已处理」后 status → 'processed' 并写 resolved_at。
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS complaints (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        teacher_name TEXT,
        patient_name TEXT,
        content TEXT,
        created_at TEXT,
        status TEXT DEFAULT 'pending',  -- 【第82天新增】pending（待处理）/ processed（已处理）
        resolved_at TEXT                -- 【第82天新增】处理时间（老师点「已处理」时写入 ISO 时间戳）
    )
    """)
    # 【第82天新增】老库自动迁移（与 visit_at / is_remote / teacher_settings.holidays 的补列手法完全一致）：
    # 旧 complaints 表没有 status / resolved_at 列，这里补上；列已存在时 sqlite 抛 OperationalError，直接跳过。
    # 老记录补 status 后统一为 'pending'（默认值），符合「老陈述还待处理」的语义，不丢数据。
    try:
        cursor.execute("ALTER TABLE complaints ADD COLUMN status TEXT DEFAULT 'pending'")
    except sqlite3.OperationalError:
        pass  # 字段已存在
    try:
        cursor.execute("ALTER TABLE complaints ADD COLUMN resolved_at TEXT")
    except sqlite3.OperationalError:
        pass  # 字段已存在

    # 【第52天新增】药方表（结构化存储，便于后续按药方自动扣减库存）
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS prescriptions (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        teacher_name TEXT,
        patient_name TEXT DEFAULT '',
        items_json TEXT,       -- [{herb_name, amount, unit}]
        note TEXT DEFAULT '',  -- 药方备注，可空
        created_at TEXT,
        is_remote INTEGER DEFAULT 0  -- 【第53天新增】0=当面诊疗(扣库存) 1=远程诊疗(不扣库存)
    )
    """)
    # 【第53天新增】如果表已存在（旧表），尝试补加 is_remote 字段
    try:
        cursor.execute("ALTER TABLE prescriptions ADD COLUMN is_remote INTEGER DEFAULT 0")
    except sqlite3.OperationalError:
        pass

    # 【第74天新增 / 开方九宫格改造】药材的「君臣佐使(role)」与「煎法(cooking_method)」不加表列：
    # prescriptions 的药材是以 JSON 字符串存在 items_json 里的，一条药方有多味药、这两个字段是
    # 「每条药材」的属性，加表列会放错层级，所以直接加在每条药材记录的 JSON 里：
    #   {herb_name, amount, unit, role: '君'/'臣'/'佐'/'使'/'', cooking_method: '常规'/'先煎'/'后下'/'包煎'/'烊化'/'另煎'/'冲服'/''}
    # 等价于 ALTER TABLE 的兼容方案：历史药方由下面的函数补上这两个 key（默认 ''，只添 key、不改原值、可重复执行）。
    # 另外：该函数与相关常量定义在本文件的「药方」小节（模块加载时已定义，init_db() 调用时一定可用）。
    # 【注意】必须先 commit：该函数会另开一个连接去读 prescriptions，不先落盘的话新库会报
    # “no such table: prescriptions”（上面的建表语句还在当前事务里）；同时兜住异常，兼容性升级失败也不能挡住启动。
    conn.commit()
    try:
        migrate_prescription_items_role_cooking()
    except sqlite3.Error as exc:
        print("[warn] 药方 role/cooking_method 兼容性升级跳过：", exc)

    # 【第56天新增】老师智能体任务表（请示 / 汇报）
    # 【行政化核对】字段与设计文档一致，无需 ALTER（id / teacher_name / task_type / category /
    # title / content / action_data / status / created_at / resolved_at 共 10 列，无 CHECK 约束，
    # 所以 status 可自由使用 pending / approved / rejected / done / undone 五个取值）。
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS agent_tasks (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        teacher_name TEXT,
        task_type TEXT,       -- 'request'（请示）或 'report'（汇报）
        category TEXT,        -- 'student' / 'schedule' / 'inventory' / 'appointment' / 'billing'
        title TEXT,           -- 短标题（如"张三已沉默 35 天"）
        content TEXT,         -- 详细描述
        action_data TEXT,     -- JSON，可执行的行动参数
        status TEXT DEFAULT 'pending',  -- pending / approved / rejected / done / undone
        created_at TEXT,
        resolved_at TEXT
    )
    """)

    # 【第56天新增】智能体行动日志表（闭环留痕）
    # 【行政化核对】字段与设计文档一致，无需 ALTER（id / teacher_name / task_id / action /
    # detail / created_at 共 6 列）。
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS agent_action_log (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        teacher_name TEXT,
        task_id INTEGER,
        action TEXT,          -- 'send_notice' / 'approve' / 'reject'
        detail TEXT,
        created_at TEXT
    )
    """)

    conn.commit()

    # 【第75天新增】施治方案模板表（老师个人的“施治方案”常用模板记忆）
    # 一位老师一条（teacher_name UNIQUE）：选中的学生“施治方案”为空时，前端自动套用这条模板；
    # 老师点“保存病历修改”或“预览完整病历”时，把当前内容覆盖写回这里（越用越贴合老师的习惯写法）。
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS plan_templates (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        teacher_name TEXT UNIQUE,
        content TEXT DEFAULT '',
        updated_at TEXT
    )
    """)

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
    
    cursor.execute("SELECT COUNT(*) as count FROM points_accounts")
    if cursor.fetchone()["count"] == 0:
        cursor.execute("INSERT INTO points_accounts (role_name, points) VALUES (?, ?)", ("张三", 100))
        cursor.execute("INSERT INTO points_accounts (role_name, points) VALUES (?, ?)", ("李四", 100))
        cursor.execute("INSERT INTO points_accounts (role_name, points) VALUES (?, ?)", ("李老师", 500))
        conn.commit()

    conn.close()
    # 【第51天新增】中药材库存表
    init_herb_table()
    # 【第65天新增】财务管理：账户表 accounts + 流水表 transactions（含老积分表自动迁移）
    init_finance_tables()

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
        LEFT JOIN points_accounts a ON p.name = a.role_name
        WHERE pt.teacher_name = ? AND pt.status = 'active'
        ORDER BY p.name
    """, (teacher_name,)).fetchall()
    conn.close()
    return [dict(r) for r in rows]

def get_student_status(patient_name):
    """【第44天新增】根据最后活跃时间 + 积分，返回学生状态"""
    conn = get_connection()
    row = conn.execute("SELECT last_active_at FROM patients WHERE name = ?", (patient_name,)).fetchone()
    pts_row = conn.execute("SELECT points FROM points_accounts WHERE role_name = ?", (patient_name,)).fetchone()
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
    conn.execute("INSERT OR IGNORE INTO points_accounts (role_name, points) VALUES (?, 100)", (student_name,))
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
    for table in ["patients", "patient_teachers", "patient_profiles", "homework", "transcriptions", "drafts", "patient_records", "points_accounts"]:
        col = "role_name" if table == "points_accounts" else ("patient_name" if table != "patients" else "name")
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
    """【第45天修改】签字时同时保存 AI 原草案与老师最终版（学习轨迹）

    【第77天新增】落库时一并写入 visit_at = 当前时间（ISO 时间戳）—— 这是「复诊提醒」唯一可靠的
    就诊时间基准（以前只能从病历文本的签字行「李老师 · 2026年9月23日」里猜，漏签字行就失效）。
    """
    conn = get_connection()
    draft = conn.execute("SELECT * FROM drafts WHERE id = ?", (draft_id,)).fetchone()
    if not draft:
        conn.close()
        return None

    # 完整病历（如果传了）或退回到最终方案
    patient_record_content = final_content if final_content else final_plan

    # 【第77天新增】visit_at = 签字时刻（本机时间，ISO 格式）：agent.check_recall_alerts 按它判断该生多久没复诊
    conn.execute(
        "INSERT INTO patient_records (patient_name, teacher_name, ai_draft, final_plan, doctor, visit_at) VALUES (?, ?, ?, ?, ?, ?)",
        (draft["patient_name"], draft["teacher_name"], draft["content"], patient_record_content, draft["teacher_name"], datetime.now().isoformat())
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
    conn.execute("INSERT OR IGNORE INTO points_accounts (role_name, points) VALUES (?, 100)", (student_name,))
    # 标记邀请码已使用
    conn.execute("UPDATE invites SET used_by = ?, used_at = ? WHERE code = ?",
                 (student_name, datetime.now().strftime('%Y-%m-%d %H:%M:%S'), code))
    conn.commit()
    conn.close()
    return {"message": "加入成功", "teacher_name": invite["teacher_name"]}

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
# 【第65天说明】积分与财务余额是两套数：积分仍在 points_accounts 表，接口 /api/points 行为不变。
def get_points(role_name):
    conn = get_connection()
    row = conn.execute("SELECT points FROM points_accounts WHERE role_name = ?", (role_name,)).fetchone()
    conn.close()
    return row["points"] if row else 0

def add_points(role_name, amount):
    conn = get_connection()
    conn.execute("UPDATE points_accounts SET points = points + ? WHERE role_name = ?", (amount, role_name))
    conn.commit()
    conn.close()

def transfer_points(from_role, to_role, amount):
    conn = get_connection()
    conn.execute("UPDATE points_accounts SET points = points - ? WHERE role_name = ?", (amount, from_role))
    conn.execute("UPDATE points_accounts SET points = points + ? WHERE role_name = ?", (amount, to_role))
    conn.commit()
    conn.close()

# ============ 【第65天新增】财务管理：账户表 + 流水表 ============

def init_finance_tables():
    """财务两张表的建表语句，由 init_db() 在启动时调用，保证自动建表。

    accounts     财务账户表：id / username(唯一) / role / balance / updated_at
    transactions 财务流水表：id / username / type(recharge|gift|deduct) / amount
                             / balance_after / note / created_at

    兼容处理：老版本的 accounts 是"积分账户表"（role_name/points），
    这里若检测到老结构，先改名成 points_accounts 把数据原样搬走，再建新的 accounts。
    """
    conn = get_connection()
    cur = conn.cursor()
    _migrate_legacy_points_accounts(cur)
    cur.execute("""
    CREATE TABLE IF NOT EXISTS accounts (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        username TEXT UNIQUE,
        role TEXT DEFAULT 'student',
        balance INTEGER DEFAULT 0,
        updated_at TEXT
    )
    """)
    cur.execute("""
    CREATE TABLE IF NOT EXISTS transactions (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        username TEXT,
        type TEXT,
        amount INTEGER,
        balance_after INTEGER,
        note TEXT,
        created_at TEXT
    )
    """)
    conn.commit()
    conn.close()


def _migrate_legacy_points_accounts(cursor):
    """把老库里的"积分账户表 accounts(role_name, points)"改名成 points_accounts（数据原样保留）。"""
    existed = cursor.execute("SELECT name FROM sqlite_master WHERE type = 'table' AND name = 'accounts'").fetchone()
    if existed is None:
        return False  # 全新库，没有老表
    columns = [row["name"] for row in cursor.execute("PRAGMA table_info(accounts)").fetchall()]
    if "balance" in columns:
        return False  # 已经是新的财务账户表结构
    if "points" not in columns:
        return False  # 不认识的表结构，不擅自动它
    cursor.execute("CREATE TABLE IF NOT EXISTS points_accounts (role_name TEXT PRIMARY KEY, points INTEGER DEFAULT 0)")
    cursor.execute("INSERT OR REPLACE INTO points_accounts (role_name, points) SELECT role_name, points FROM accounts")
    cursor.execute("DROP TABLE accounts")
    return True


def _finance_role(conn, username):
    """role 规则：username 存在于 teachers 表就是 teacher，否则 student。"""
    row = conn.execute("SELECT 1 FROM teachers WHERE name = ?", (username,)).fetchone()
    return "teacher" if row else "student"


def _ensure_finance_account(conn, username):
    """账户不存在就自动创建（余额 0），返回当前余额。"""
    row = conn.execute("SELECT balance FROM accounts WHERE username = ?", (username,)).fetchone()
    if row is None:
        conn.execute(
            "INSERT OR IGNORE INTO accounts (username, role, balance, updated_at) VALUES (?, ?, 0, ?)",
            (username, _finance_role(conn, username), datetime.now().isoformat())
        )
        row = conn.execute("SELECT balance FROM accounts WHERE username = ?", (username,)).fetchone()
    return row["balance"] if row else 0


def _change_finance_balance(username, amount, change_type, note=""):
    """统一入账入口：余额不足（余额 + amount < 0）时整体回滚，不扣款也不记流水。"""
    conn = get_connection()
    try:
        balance = _ensure_finance_account(conn, username)
        if balance + amount < 0:
            conn.rollback()  # 撤销上面可能刚建的账户，保证"余额不足不扣款"
            return {"ok": False, "error": "余额不足"}
        new_balance = balance + amount
        now = datetime.now().isoformat()
        conn.execute("UPDATE accounts SET balance = ?, updated_at = ? WHERE username = ?", (new_balance, now, username))
        conn.execute(
            "INSERT INTO transactions (username, type, amount, balance_after, note, created_at) VALUES (?, ?, ?, ?, ?, ?)",
            (username, change_type, amount, new_balance, note or "", now)
        )
        conn.commit()
        return {"ok": True, "balance": new_balance}
    finally:
        conn.close()


def recharge_account(username, amount, note=""):
    """预存（充值）：余额 +amount，流水 amount 记正数。"""
    return _change_finance_balance(username, amount, "recharge", note)


def gift_account(username, amount, note=""):
    """赠送：余额 +amount，流水 amount 记正数。"""
    return _change_finance_balance(username, amount, "gift", note)


def deduct_account(username, amount, note=""):
    """扣费：余额 -amount，流水 type='deduct' 且 amount 记负数。"""
    return _change_finance_balance(username, -amount, "deduct", note)


def get_finance_accounts():
    """账户列表：role 由 username 是否存在于 teachers 表实时判断。"""
    conn = get_connection()
    rows = conn.execute("""
        SELECT a.username,
               CASE WHEN t.name IS NULL THEN 'student' ELSE 'teacher' END as role,
               a.balance
        FROM accounts a
        LEFT JOIN teachers t ON a.username = t.name
        ORDER BY a.username
    """).fetchall()
    conn.close()
    return [dict(r) for r in rows]

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


# ============ 药方（开方：中药首字联想 + 结构化存储） ============

# 【第74天新增 / 开方九宫格改造】君臣佐使（role）与煎法（cooking_method）的合法取值白名单，
# 与前端 App.tsx 的 HERB_ROLES / COOKING_METHODS 保持一致（不合法 / 空值一律落成空串 ''）。
PRESCRIPTION_ROLES = ("君", "臣", "佐", "使")
PRESCRIPTION_COOKING_METHODS = ("常规", "先煎", "后下", "包煎", "烊化", "另煎", "冲服")


def clean_prescription_role(value):
    """君臣佐使：只认 君/臣/佐/使，其它（含 None / 未标注 / 拼写错误）一律落成 ''。"""
    if not isinstance(value, str):
        return ""
    value = value.strip()
    return value if value in PRESCRIPTION_ROLES else ""


def clean_prescription_cooking_method(value):
    """煎法：只认 常规/先煎/后下/包煎/烊化/另煎/冲服，其它一律落成 ''。"""
    if not isinstance(value, str):
        return ""
    value = value.strip()
    return value if value in PRESCRIPTION_COOKING_METHODS else ""


def sanitize_prescription_items(items):
    """【第74天新增】落库前清洗药方里的每条药材：
    - 只清洗客户端真正传了的 role / cooking_method（老客户端不传这两个字段时，存进去的 JSON 与改造前完全一致，
      保证历史数据格式与既有测试不被破坏）；
    - 传了但值不合法 → 落成 ''（既不报错也不把脏值写进库）。
    返回新的 list，不改动入参。
    """
    cleaned = []
    for item in (items or []):
        entry = dict(item)
        if "role" in entry:
            entry["role"] = clean_prescription_role(entry.get("role"))
        if "cooking_method" in entry:
            entry["cooking_method"] = clean_prescription_cooking_method(entry.get("cooking_method"))
        cleaned.append(entry)
    return cleaned


def migrate_prescription_items_role_cooking():
    """【第74天新增 / 等效于 ALTER TABLE 的兼容方案】
    给历史药方的每条药材补上 role / cooking_method 两个 key（默认 ''）：
    - 只添加缺失的 key，已有的值原样保留，药材名 / 克数 / 单位完全不动 → 不破坏已有数据；
    - items_json 为空或不是合法 JSON 的脏数据直接跳过；
    - 可重复执行（补过一次的行下次会因 key 已存在而被跳过）。
    返回本次补过 key 的药方条数。
    """
    conn = get_connection()
    try:
        cur = conn.cursor()
        rows = cur.execute("SELECT id, items_json FROM prescriptions").fetchall()
        migrated = 0
        for row in rows:
            raw = row["items_json"]
            if not raw:
                continue
            try:
                items = json.loads(raw)
            except Exception:
                continue  # 脏数据不动它
            if not isinstance(items, list):
                continue
            changed = False
            for item in items:
                if not isinstance(item, dict):
                    continue
                if "role" not in item or "cooking_method" not in item:
                    item.setdefault("role", "")
                    item.setdefault("cooking_method", "")
                    changed = True
            if changed:
                cur.execute("UPDATE prescriptions SET items_json = ? WHERE id = ?", (json.dumps(items, ensure_ascii=False), row["id"]))
                migrated += 1
        conn.commit()
        return migrated
    finally:
        conn.close()   # 出错也要关连接：否则 Windows 上会锁住 db 文件（测试里表现为 PermissionError）


def search_herbs_by_prefix(teacher_name, prefix):
    """首字联想：只看药材名首字。输入「甘」匹配「甘草」，不匹配「炙甘草」。prefix 为空返回 []。"""
    if not prefix:
        return []
    conn = get_connection()
    cur = conn.cursor()
    cur.execute(
        "SELECT * FROM herb_inventory WHERE teacher_name = ? AND herb_name LIKE ? || '%' ORDER BY herb_name",
        (teacher_name, prefix)
    )
    rows = cur.fetchall()
    conn.close()
    return [{"id": r["id"], "herb_name": r["herb_name"], "stock_amount": r["stock_amount"], "unit": r["unit"]} for r in rows]


def create_prescription(teacher_name, patient_name, items, note="", is_remote=0):
    """保存药方：当面诊疗（is_remote=0）先原子扣减库存，扣成功才保存药方；
    远程诊疗（is_remote=1）只保存药方、不动库存。

    【第74天新增 / 开方九宫格改造】items 里每条药材可额外带 role（君臣佐使）与 cooking_method（煎法），
    落库前统一走 sanitize_prescription_items() 清洗；扣库存逻辑完全不变（仍然只用到 herb_name / amount）。
    """
    items = sanitize_prescription_items(items)
    # 1. 当面诊疗：先扣库存
    if not is_remote:
        deducted = batch_deduct_herbs(teacher_name, items)
        # 2. 扣失败 → 整体失败，不写药方
        if not deducted["success"]:
            return {"error": "库存不足：" + str(deducted["failed_herb"]), "failed_herb": deducted["failed_herb"]}
    # 3. 扣成功（或远程）→ 插入 prescriptions 表
    conn = get_connection()
    cur = conn.cursor()
    cur.execute(
        "INSERT INTO prescriptions (teacher_name, patient_name, items_json, note, is_remote, created_at) VALUES (?, ?, ?, ?, ?, ?)",
        (teacher_name, patient_name or "", json.dumps(items, ensure_ascii=False), note or "", 1 if is_remote else 0, datetime.now().isoformat())
    )
    conn.commit()
    prescription_id = cur.lastrowid
    conn.close()
    return {"message": "已保存", "id": prescription_id}


def _prescription_row_to_dict(row):
    """内部工具函数：一行 prescriptions 转 dict，并顺带把 items_json 解析成 items 列表。

    【第74天新增】解析出来的每条药材补上 role / cooking_method 默认值（''）：
    历史药方（改造前存的）也能被前端当成「未标注 + 常规」正常渲染，前端不必再做兼容判断。
    """
    d = dict(row)
    items = json.loads(d["items_json"]) if d["items_json"] else []
    if isinstance(items, list):
        for item in items:
            if isinstance(item, dict):
                item.setdefault("role", "")
                item.setdefault("cooking_method", "")
    d["items"] = items
    return d


def get_prescriptions(teacher_name, patient_name=None):
    """返回该老师的药方；给了 patient_name 就再按患者过滤。最新在前。"""
    conn = get_connection()
    conditions = ["teacher_name = ?"]
    params = [teacher_name]
    if patient_name:
        conditions.append("patient_name = ?")
        params.append(patient_name)
    where = " AND ".join(conditions)
    rows = conn.execute(f"SELECT * FROM prescriptions WHERE {where} ORDER BY id DESC", params).fetchall()
    conn.close()
    return [_prescription_row_to_dict(r) for r in rows]


# ============ 老师智能体（一期：沉默学生请示闭环） ============

def _agent_task_row_to_dict(row):
    """内部工具函数：一行 agent_tasks 转 dict，并把 action_data 解析成 action 参数字典。"""
    d = dict(row)
    try:
        d["action"] = json.loads(d["action_data"]) if d["action_data"] else {}
    except Exception:
        d["action"] = {}
    return d


def scan_silent_students(teacher_name, silent_days=30):
    """扫描该老师名下的「沉默学生」（last_active_at 为空，或距今 >= silent_days 天），
    给还没有 pending 同类请示的学生各建一条 agent_tasks 请示，返回新建任务数。"""
    conn = get_connection()
    cur = conn.cursor()
    students = cur.execute("""
        SELECT p.name AS name, p.last_active_at AS last_active_at
        FROM patients p
        INNER JOIN patient_teachers pt ON p.name = pt.patient_name
        WHERE pt.teacher_name = ? AND pt.status = 'active'
        ORDER BY p.name
    """, (teacher_name,)).fetchall()

    # 【行政化改造】先把该老师所有 pending 的「学生」类请示里的 patient_name 收集起来做去重集合。
    # 不用以前那种 action_data 字符串全等匹配 —— 这样历史旧格式
    # （{"action": "send_care_notice", ...}）也能命中，action_data 格式升级不会给同一学生重复建单。
    pending_patient_names = set()
    for pending in cur.execute(
        "SELECT action_data FROM agent_tasks WHERE teacher_name = ? AND category = 'student' AND status = 'pending'",
        (teacher_name,)
    ).fetchall():
        try:
            pending_patient_names.add((json.loads(pending["action_data"]) or {}).get("patient_name"))
        except Exception:
            continue

    now = datetime.now()
    created = 0
    for student in students:
        name = student["name"]
        last_active = student["last_active_at"]
        if last_active:
            # last_active_at 统一存 "YYYY-MM-DD"（见 insert_transcription / update_homework_status）
            try:
                last_dt = datetime.strptime(last_active[:10], "%Y-%m-%d")
                days = max(0, (now - last_dt).days)
            except Exception:
                days = silent_days  # 时间格式异常，按沉默阈值处理
            if days < silent_days:
                continue
        else:
            days = silent_days  # 从未互动过：按沉默阈值计

        # 该学生已有 pending 同类请示 → 不重复建
        if name in pending_patient_names:
            continue

        # 【行政化改造】按设计文档固定字段写入 agent_tasks：
        #   task_type = 'request'、category = 'student'、title = '张三已沉默 35 天'、
        #   content = '是否发送关怀通知？'、
        #   action_data = {"action": "send_care_notice", "patient_name": "张三", "template": "care"}、
        #   status = 'pending'（created_at 由后端补；resolved_at 等老师审批时再写）
        # 【通知命名规范】action 统一用 send_<类型>_notice 格式，一眼看出通知类型：
        #   沉默关怀 = send_care_notice、欠费催缴 = send_billing_notice、
        #   复诊提醒 = send_recall_notice、预约通知 = send_schedule_notice（后续新增按此格式）。
        action_data = json.dumps(
            {"action": "send_care_notice", "patient_name": name, "template": "care"},
            ensure_ascii=False
        )
        cur.execute("""
            INSERT INTO agent_tasks (teacher_name, task_type, category, title, content, action_data, status, created_at)
            VALUES (?, 'request', 'student', ?, ?, ?, 'pending', ?)
        """, (teacher_name, f"{name}已沉默 {days} 天", "是否发送关怀通知？",
              action_data, now.isoformat()))
        created += 1
        pending_patient_names.add(name)

    conn.commit()
    conn.close()
    return created


def get_agent_tasks(teacher_name, status='pending'):
    """按 created_at DESC 返回该老师的智能体任务；status 传空则不过滤状态。"""
    conn = get_connection()
    if status:
        rows = conn.execute(
            "SELECT * FROM agent_tasks WHERE teacher_name = ? AND status = ? ORDER BY created_at DESC, id DESC",
            (teacher_name, status)
        ).fetchall()
    else:
        rows = conn.execute(
            "SELECT * FROM agent_tasks WHERE teacher_name = ? ORDER BY created_at DESC, id DESC",
            (teacher_name,)
        ).fetchall()
    conn.close()
    return [_agent_task_row_to_dict(r) for r in rows]


def resolve_agent_task(task_id, decision):
    """老师决策：decision='approved' / 'rejected'。
    更新任务状态 + 记一条 agent_action_log；approved 且 action 为 send_care_notice 时再记一条发送日志（暂不真实推送）。"""
    conn = get_connection()
    cur = conn.cursor()
    task = cur.execute("SELECT * FROM agent_tasks WHERE id = ?", (task_id,)).fetchone()
    if task is None:
        conn.close()
        return None

    now = datetime.now().isoformat()
    new_status = 'approved' if decision == 'approved' else 'rejected'
    cur.execute("UPDATE agent_tasks SET status = ?, resolved_at = ? WHERE id = ?", (new_status, now, task_id))
    cur.execute("""
        INSERT INTO agent_action_log (teacher_name, task_id, action, detail, created_at)
        VALUES (?, ?, ?, ?, ?)
    """, (task["teacher_name"], task_id, 'approve' if new_status == 'approved' else 'reject',
          ("老师确认执行：" if new_status == 'approved' else "老师忽略：") + str(task["title"]), now))

    if new_status == 'approved':
        try:
            action = json.loads(task["action_data"]) if task["action_data"] else {}
        except Exception:
            action = {}
        # 标准命名 send_<类型>_notice（沉默关怀 = 'send_care_notice'）；同时容忍中途试写过的 'send_notice'
        if action.get("action") in ("send_care_notice", "send_notice"):
            cur.execute("""
                INSERT INTO agent_action_log (teacher_name, task_id, action, detail, created_at)
                VALUES (?, ?, 'send_notice', ?, ?)
            """, (task["teacher_name"], task_id, f"已发送关怀通知给 {action.get('patient_name')}", now))

    conn.commit()
    conn.close()
    return {"message": "已处理", "status": new_status}


def get_agent_action_log(teacher_name, limit=20):
    """【行政化改造】返回该老师的智能体行动日志，按 created_at 倒序（同一时间按 id 倒序）。

    limit：最多返回多少条（设计文档接口默认 20）：非正数按默认 20 处理，上限 200，防止一把拉爆。
    """
    if not teacher_name:
        return []
    if limit is None or limit <= 0:
        limit = 20
    limit = min(limit, 200)

    conn = get_connection()
    rows = conn.execute(
        "SELECT * FROM agent_action_log WHERE teacher_name = ? ORDER BY created_at DESC, id DESC LIMIT ?",
        (teacher_name, limit)
    ).fetchall()
    conn.close()
    return [dict(r) for r in rows]


# ============ 【第75天新增】施治方案模板（老师维度的模板记忆） ============

def get_plan_template(teacher_name):
    """取该老师的“施治方案”模板：没有记录（或内容为空）时统一返回空串，前端好判断。"""
    conn = get_connection()
    row = conn.execute("SELECT content FROM plan_templates WHERE teacher_name = ?", (teacher_name,)).fetchone()
    conn.close()
    if row is None:
        return ""
    return row["content"] or ""


def save_plan_template(teacher_name, content):
    """保存 / 覆盖该老师的“施治方案”模板（teacher_name 唯一：有则 UPDATE，无则 INSERT）。"""
    conn = get_connection()
    cur = conn.cursor()
    now = datetime.now().isoformat()
    cur.execute("SELECT id FROM plan_templates WHERE teacher_name = ?", (teacher_name,))
    existing = cur.fetchone()
    if existing:
        cur.execute("UPDATE plan_templates SET content = ?, updated_at = ? WHERE id = ?",
                    (content or "", now, existing["id"]))
    else:
        cur.execute("INSERT INTO plan_templates (teacher_name, content, updated_at) VALUES (?, ?, ?)",
                    (teacher_name, content or "", now))
    conn.commit()
    conn.close()
    return True


# ============ 【第82天新增】学生陈述（complaints）：老师端「📝 待处理陈述」 ============
# 数据链路：学生「十问歌」面诊前准备 → agent.save_intake() 落 complaints（status='pending'）
#           → 老师端 GET /api/complaints?teacher_name=…&status=pending 看到列表
#           → 点「已处理」POST /api/complaints/{id}/process → status='processed' + resolved_at。

def get_complaints(teacher_name, status="pending"):
    """查该老师名下的学生陈述：按 status 过滤，created_at 倒序（同一时间按 id 倒序）。

    status 传空串 / None = 不过滤状态（返回该老师全部陈述）。
    返回字段：id / patient_name / teacher_name / content / status / created_at。
    """
    conn = get_connection()
    if status:
        rows = conn.execute(
            "SELECT id, patient_name, teacher_name, content, status, created_at FROM complaints "
            "WHERE teacher_name = ? AND status = ? ORDER BY created_at DESC, id DESC",
            (teacher_name, status)
        ).fetchall()
    else:
        rows = conn.execute(
            "SELECT id, patient_name, teacher_name, content, status, created_at FROM complaints "
            "WHERE teacher_name = ? ORDER BY created_at DESC, id DESC",
            (teacher_name,)
        ).fetchall()
    conn.close()
    return [dict(r) for r in rows]


def process_complaint(complaint_id):
    """老师标记「已处理」：status → 'processed' 并写 resolved_at（ISO 时间戳）。

    返回 True；记录不存在返回 False（由接口回 404，不静默成功）。
    """
    conn = get_connection()
    cur = conn.cursor()
    row = cur.execute("SELECT id FROM complaints WHERE id = ?", (complaint_id,)).fetchone()
    if row is None:
        conn.close()
        return False
    now = datetime.now().isoformat()
    cur.execute("UPDATE complaints SET status = 'processed', resolved_at = ? WHERE id = ?",
                (now, complaint_id))
    conn.commit()
    conn.close()
    return True


# ============================================================================
# 【Epic 1 新增】四類模板（templates）：白名單 / 默認骨架 / 校驗層 / 存取與狀態機
# ============================================================================
# 對齊：docs/epic1-template-design-v1.md §3（狀態機）、§4（版本規則）、§9（四類 schema_json
#       字段級契約）、§10（CRUD 接口）、§11（發佈 / 歸檔 / 派生）、§12.4（legacy 兼容）。
#
# 本節五條紀律（寫在這裏即約束）：
#   1. `type` / `status` 不加 CHECK（存量全庫無 CHECK）→ Python 白名單 + 本層校驗，非法值一律 400，
#      **絕不清洗**（不對照 clean_prescription_role 的「不合法落成空串」語義）；
#   2. `schema_json` 原樣存 TEXT（`json.dumps(..., ensure_ascii=False)`，沿用 teacher_settings /
#      prescriptions.items_json 慣例）；未知鍵「忽略且原樣保留」，不補默認值、不刪鍵（前向兼容，§9.0）；
#   3. 校驗入口 `validate_template_schema(type, obj)` → `(ok, errors)`，errors = `[{"path","msg"}]`
#      （path 用 JS 風格，如 `fields[2].label`）；`validate_template_schema_for_publish()` 在其上疊加
#      「發佈級完整性」——草稿允許半成品，發佈必須完整（§9.0 校驗時機）；
#   4. `active` / `archived` 行內容不可原地改（§3.3，接口層回 409）；狀態機切換**全部在同一 SQLite
#      事務內**完成（先歸檔舊 active、再置新 active，順序不可換，否則瞬時違反 uq_templates_active_one，§11.1）；
#   5. 本模組是運行時讀寫入口，**不建表**：`templates` DDL 唯一來源是遷移 0001（§1.1 / §6.1）。
#
# 錯誤約定：服務層拋 `TemplateError(code, msg)`，由接口層（template_api.py）翻譯成真實 HTTP 狀態碼；
#           存在性 / 歸屬類錯誤由接口層在調用前攔（404 template_not_found / 403 template_forbidden）。

TEMPLATE_TYPES = ("inquiry", "record", "treatment", "prescription")
TEMPLATE_STATUSES = ("draft", "active", "archived")
# 顯示名（繁體古字，§9.1 表 / §13.2 頁簽文案）：新建時 name 的缺省值 + 前端頁簽徽章
TEMPLATE_TYPE_LABELS = {
    "inquiry": "問診",
    "record": "病歷",
    "treatment": "施治",
    "prescription": "開方",
}
TEMPLATE_SCHEMA_VERSION = 1                # 契約版本，Epic 1 恒為 1（§9.0）
TEMPLATE_MAX_STRING_LEN = 2000             # 單個字符串 ≤ 2000 字（§9.0）
TEMPLATE_MAX_SCHEMA_BYTES = 64 * 1024      # schema_json 序列化後 ≤ 64 KB（§9.0，超限 400 schema_too_large）
TEMPLATE_KEY_RE = re.compile(r"^[a-z][a-z0-9_]{0,31}$")   # fields[].key / sections[].key（§9.1 / §9.2）
ANSWER_TYPES = ("text", "number", "choice")               # inquiry fields[].answer_type
WRITABLE_BY_VALUES = ("ai", "teacher")                    # record sections[].writable_by（teacher = 智能體永不填）
TREATMENT_FORMATS = ("text",)                             # Epic 1 僅 text（blocks 預留，§9.3）
LEGACY_SOURCE_PLAN_TEMPLATES = "plan_templates"           # 與遷移 0001 的 meta.legacy_source 同名同值


class TemplateError(Exception):
    """模板服務層錯誤：帶機器碼，由接口層翻譯成 HTTP 狀態碼（映射表見 template_api.py）。"""

    def __init__(self, code, msg):
        super().__init__(msg)
        self.code = code
        self.msg = msg


# ---------- 默認骨架（§9.1 / §9.2 / §9.3 / §9.4）----------

# 十問歌默認骨架：key 與順序 = agent.TEN_QUESTIONS（agent.py:303-314），**順序不可變**；
# label / ask 按 §9.1 表給老師口徑的繁體古字（炁 / 氣 按語義區分，禁止全局簡繁替換）。
_DEFAULT_INQUIRY_FIELDS = (
    ("cold_heat", "寒熱", "你最近是怕冷多一點，還是怕熱多一點？"),
    ("sweat", "汗", "平時出汗多不多？是白天易汗，還是睡著了出汗？"),
    ("head_body", "頭身", "頭或身體有哪裏不舒服？頭暈、頭痛、身重痠沉？"),
    ("urine_stool", "二便", "大小便如何？有無乾結、稀軟、次數變多？"),
    ("diet", "飲食", "近來胃口與口味如何？吃東西香不香？"),
    ("chest_abdomen", "胸腹", "胸口或腹部有無發悶、發脹、隱隱作痛？"),
    ("ear", "耳", "耳朵有沒有響，或聽東西不太清楚？"),
    ("thirst", "口渴", "會覺得口渴嗎？想喝熱水還是涼水？"),
    ("old_illness", "舊病", "以前得過什麼病？有無長期服藥？"),
    ("cause", "病因", "這次不適大約從何時起？你覺得與什麼有關？"),
)

# 病歷默認骨架：對齊 agent.DOCTOR_PROMPT 的輸出模板 / main.build_draft_template（§9.2 表）。
# writable_by='teacher' = 智能體永不填內容（憲法硬約束：AI 永不辨證）。
_DEFAULT_RECORD_SECTIONS = (
    ("chief_complaint", "主訴（學生原話）", "ai"),
    ("past_records", "既往病歷參考", "ai"),
    ("tongue", "舌象", "teacher"),
    ("pulse", "脈象", "teacher"),
    ("pattern", "辨證", "teacher"),
    ("treatment_plan", "施治方案", "teacher"),
)

# tone.forbidden 默認值 = 術語鐵律詞表（agent.py:189-192「原文保留、不許換近義詞」，§9.2）
_DEFAULT_RECORD_FORBIDDEN = ("脈象", "舌象", "主訴", "現病史", "伴隨症狀", "辨證")


def default_template_schema(template_type):
    """該類型的默認骨架（每次返回全新副本，調用方可隨意改）。

    未知類型返回 None（由接口層回 400 `invalid_type`，本層不拋異常，方便探測調用）。
    """
    if template_type == "inquiry":
        return {
            "version": TEMPLATE_SCHEMA_VERSION,
            "fields": [
                {
                    "key": key,
                    "label": label,
                    "ask": ask,
                    "order": index + 1,
                    "required": False,
                    "answer_type": "text",
                    "choices": [],
                    "follow_up": "",
                }
                for index, (key, label, ask) in enumerate(_DEFAULT_INQUIRY_FIELDS)
            ],
            "meta": {},
        }
    if template_type == "record":
        return {
            "version": TEMPLATE_SCHEMA_VERSION,
            "sections": [
                {
                    "key": key,
                    "title": title,
                    "hint": "",
                    "order": index + 1,
                    "required": False,
                    "writable_by": writable_by,
                }
                for index, (key, title, writable_by) in enumerate(_DEFAULT_RECORD_SECTIONS)
            ],
            "tone": {"style": "", "forbidden": list(_DEFAULT_RECORD_FORBIDDEN)},
            "meta": {},
        }
    if template_type == "treatment":
        return {
            "version": TEMPLATE_SCHEMA_VERSION,
            "format": "text",
            "content": "",
            "placeholders": [],
            "meta": {},
        }
    if template_type == "prescription":
        return {
            "version": TEMPLATE_SCHEMA_VERSION,
            "herbs": [],
            "formulas": [],
            "defaults": {"cooking_method": "常规", "remote": False},
            "meta": {},
        }
    return None


# ---------- 校驗層（§9）：只攔截、不清洗 ----------

_MISSING = object()   # 區分「鍵缺失」與「值為 None / ''」


def _err(errors, path, msg):
    errors.append({"path": path, "msg": msg})


def _is_int(value):
    """布爾不是整數（`True` 會被 isinstance(..., int) 命中，必須排除）。"""
    return isinstance(value, int) and not isinstance(value, bool)


def _check_text(errors, path, value, *, required, max_len=None, min_len=0):
    """字串字段校驗。`required=True` 表示鍵必須存在（值可為空串，除非 min_len > 0）。"""
    if value is _MISSING or value is None:
        if required:
            _err(errors, path, "必填")
        return
    if not isinstance(value, str):
        _err(errors, path, "必須是字串")
        return
    if len(value) < min_len:
        _err(errors, path, "不得少於 %d 字" % min_len)
    if max_len is not None and len(value) > max_len:
        _err(errors, path, "不得超過 %d 字" % max_len)


def _check_bool(errors, path, value):
    if value is not _MISSING and value is not None and not isinstance(value, bool):
        _err(errors, path, "必須是布爾值")


def _check_order(errors, path, value):
    if value is _MISSING or value is None:
        _err(errors, path, "必填（>= 1 的整數）")
    elif not _is_int(value) or value < 1:
        _err(errors, path, "必須是 >= 1 的整數")


def _check_list(errors, path, value, *, max_items=None, min_items=None):
    """列表字段校驗；返回 True 表示類型正確（調用方可繼續逐項校驗）。"""
    if value is _MISSING or value is None:
        return False
    if not isinstance(value, list):
        _err(errors, path, "必須是陣列")
        return False
    if max_items is not None and len(value) > max_items:
        _err(errors, path, "最多 %d 項" % max_items)
    if min_items is not None and len(value) < min_items:
        _err(errors, path, "至少 %d 項" % min_items)
    return True


def _scan_items(items, errors, base, validator, unique_fields):
    """逐項校驗 + 組內唯一性（key / order / herb_name…）。`validator` 傳 None 表示只查唯一性。"""
    seen = {}
    for index, item in enumerate(items):
        path = "%s[%d]" % (base, index)
        if not isinstance(item, dict):
            _err(errors, path, "必須是 JSON 物件")
            continue
        if validator is not None:
            validator(item, errors, path)
        for field in unique_fields:
            value = item.get(field, _MISSING)
            if value is _MISSING or value is None or isinstance(value, bool) or not isinstance(value, (str, int)):
                continue
            bucket = seen.setdefault(field, {})
            if value in bucket:
                _err(errors, "%s.%s" % (path, field),
                     "%s 必須唯一（與 %s[%d] 重複）" % (field, base, bucket[value]))
            else:
                bucket[value] = index


def _validate_inquiry_field(item, errors, path):
    """§9.1 `fields[]` 一項。"""
    key = item.get("key", _MISSING)
    if key is _MISSING or key is None:
        _err(errors, path + ".key", "必填")
    elif not isinstance(key, str) or not TEMPLATE_KEY_RE.match(key):
        _err(errors, path + ".key", "鍵名需符合 ^[a-z][a-z0-9_]{0,31}$")
    _check_text(errors, path + ".label", item.get("label", _MISSING), required=True, min_len=1, max_len=16)
    _check_text(errors, path + ".ask", item.get("ask", _MISSING), required=False, max_len=120)
    _check_order(errors, path + ".order", item.get("order", _MISSING))
    _check_bool(errors, path + ".required", item.get("required", _MISSING))
    _check_text(errors, path + ".follow_up", item.get("follow_up", _MISSING), required=False, max_len=120)

    answer_type = item.get("answer_type", _MISSING)
    if answer_type is not _MISSING and answer_type is not None:
        if answer_type not in ANSWER_TYPES:
            _err(errors, path + ".answer_type", "只能是 text / number / choice")
        elif answer_type == "choice":
            _validate_choices(item.get("choices", _MISSING), errors, path + ".choices")


def _validate_choices(value, errors, path):
    """§9.1 `fields[].choices`：`answer_type='choice'` 時必填，2–12 項且去重。"""
    if value is _MISSING or value is None:
        _err(errors, path, "answer_type='choice' 時必填（2–12 項）")
        return
    if not _check_list(errors, path, value, min_items=2, max_items=12):
        return
    seen = set()
    for index, choice in enumerate(value):
        if not isinstance(choice, str) or not choice.strip():
            _err(errors, "%s[%d]" % (path, index), "選項必須是非空字串")
        elif choice in seen:
            _err(errors, "%s[%d]" % (path, index), "選項重複")
        else:
            seen.add(choice)


def _validate_record_section(item, errors, path):
    """§9.2 `sections[]` 一段。"""
    key = item.get("key", _MISSING)
    if key is _MISSING or key is None:
        _err(errors, path + ".key", "必填")
    elif not isinstance(key, str) or not TEMPLATE_KEY_RE.match(key):
        _err(errors, path + ".key", "鍵名需符合 ^[a-z][a-z0-9_]{0,31}$")
    _check_text(errors, path + ".title", item.get("title", _MISSING), required=True, min_len=1, max_len=20)
    _check_text(errors, path + ".hint", item.get("hint", _MISSING), required=False, max_len=120)
    _check_order(errors, path + ".order", item.get("order", _MISSING))
    _check_bool(errors, path + ".required", item.get("required", _MISSING))
    writable_by = item.get("writable_by", _MISSING)
    if writable_by is not _MISSING and writable_by is not None and writable_by not in WRITABLE_BY_VALUES:
        _err(errors, path + ".writable_by", "只能是 ai（智能體可填）/ teacher（留待老師）")


def _validate_herb_fields(item, errors, path, *, amount_key):
    """§9.4 藥味字段（`herbs[]` 與 `formulas[].composition[]` 共用，分量鍵名不同：default_amount / amount）。"""
    _check_text(errors, path + ".herb_name", item.get("herb_name", _MISSING), required=True, min_len=1, max_len=20)
    amount = item.get(amount_key, _MISSING)
    if amount is not _MISSING and amount is not None:
        if isinstance(amount, bool) or not isinstance(amount, (int, float)):
            _err(errors, path + "." + amount_key, "必須是數字")
        elif amount < 0 or amount > 1000:
            _err(errors, path + "." + amount_key, "只能是 0（未預填）或 0–1000 克")
    role = item.get("role", _MISSING)
    if role is not _MISSING and role is not None and role not in ("",) + PRESCRIPTION_ROLES:
        # 刻意「直接拒」：不走 clean_prescription_role 的清洗，否則老師會以為存成功了（§9.4）
        _err(errors, path + ".role", "君臣佐使只能是 君 / 臣 / 佐 / 使（或留空）")
    cooking_method = item.get("cooking_method", _MISSING)
    if cooking_method is not _MISSING and cooking_method is not None and cooking_method not in PRESCRIPTION_COOKING_METHODS:
        _err(errors, path + ".cooking_method", "煎法只能是 %s" % " / ".join(PRESCRIPTION_COOKING_METHODS))


def _validate_prescription_herb(item, errors, path):
    _validate_herb_fields(item, errors, path, amount_key="default_amount")
    order = item.get("order", _MISSING)
    if order is not _MISSING and order is not None and (not _is_int(order) or order < 1):
        _err(errors, path + ".order", "必須是 >= 1 的整數")


def _validate_formula(item, errors, path):
    """§9.4 `formulas[]`：`{name(≤20字), composition:[{herb_name, amount, role, cooking_method}]≤20}`。"""
    _check_text(errors, path + ".name", item.get("name", _MISSING), required=True, min_len=1, max_len=20)
    composition = item.get("composition", _MISSING)
    if composition is _MISSING or composition is None:
        return
    if not _check_list(errors, path + ".composition", composition, max_items=20):
        return
    for index, part in enumerate(composition):
        sub = "%s.composition[%d]" % (path, index)
        if not isinstance(part, dict):
            _err(errors, sub, "必須是 JSON 物件")
            continue
        _validate_herb_fields(part, errors, sub, amount_key="amount")
    _scan_items(composition, errors, path + ".composition", None, ("herb_name",))


def _validate_inquiry(schema_obj, errors):
    """§9.1：`3 ≤ len(fields) ≤ 20`（下限屬發佈級）；key / order 唯一，逐項見 `_validate_inquiry_field`。"""
    fields = schema_obj.get("fields", _MISSING)
    if fields is _MISSING or fields is None:
        _err(errors, "fields", "必填（陣列，發佈時 3–20 項）")
        return
    if not _check_list(errors, "fields", fields, max_items=20):
        return
    _scan_items(fields, errors, "fields", _validate_inquiry_field, ("key", "order"))


def _validate_record(schema_obj, errors):
    """§9.2：`2 ≤ len(sections) ≤ 12`（下限屬發佈級）+ `tone.style` / `tone.forbidden`。"""
    sections = schema_obj.get("sections", _MISSING)
    if sections is _MISSING or sections is None:
        _err(errors, "sections", "必填（陣列，發佈時 2–12 段）")
    elif _check_list(errors, "sections", sections, max_items=12):
        _scan_items(sections, errors, "sections", _validate_record_section, ("key", "order"))

    tone = schema_obj.get("tone", _MISSING)
    if tone is _MISSING or tone is None:
        return
    if not isinstance(tone, dict):
        _err(errors, "tone", "必須是 JSON 物件")
        return
    _check_text(errors, "tone.style", tone.get("style", _MISSING), required=False, max_len=120)
    forbidden = tone.get("forbidden", _MISSING)
    if forbidden is _MISSING or forbidden is None:
        return
    if not _check_list(errors, "tone.forbidden", forbidden, max_items=20):
        return
    for index, word in enumerate(forbidden):
        if not isinstance(word, str) or not word.strip():
            _err(errors, "tone.forbidden[%d]" % index, "必須是非空字串")


def _validate_treatment(schema_obj, errors):
    """§9.3：`format` 僅 text（Epic 1）；`content` 鍵必填（可為空串，發佈時不可為空）；`placeholders` ≤ 8 項。"""
    fmt = schema_obj.get("format", _MISSING)
    if fmt is not _MISSING and fmt is not None and fmt not in TREATMENT_FORMATS:
        _err(errors, "format", "Epic 1 僅支援 format='text'")
    _check_text(errors, "content", schema_obj.get("content", _MISSING), required=True, max_len=2000)
    placeholders = schema_obj.get("placeholders", _MISSING)
    if placeholders is _MISSING or placeholders is None:
        return
    if not _check_list(errors, "placeholders", placeholders, max_items=8):
        return
    for index, item in enumerate(placeholders):
        _check_text(errors, "placeholders[%d]" % index, item, required=True, min_len=1, max_len=60)


def _validate_prescription(schema_obj, errors):
    """§9.4：`len(herbs) ≤ 40`、`formulas ≤ 10`、`defaults` 白名單。"""
    herbs = schema_obj.get("herbs", _MISSING)
    if herbs is not _MISSING and herbs is not None and _check_list(errors, "herbs", herbs, max_items=40):
        _scan_items(herbs, errors, "herbs", _validate_prescription_herb, ("herb_name", "order"))
    formulas = schema_obj.get("formulas", _MISSING)
    if formulas is not _MISSING and formulas is not None and _check_list(errors, "formulas", formulas, max_items=10):
        _scan_items(formulas, errors, "formulas", _validate_formula, ("name",))
    defaults = schema_obj.get("defaults", _MISSING)
    if defaults is _MISSING or defaults is None:
        return
    if not isinstance(defaults, dict):
        _err(errors, "defaults", "必須是 JSON 物件")
        return
    cooking_method = defaults.get("cooking_method", _MISSING)
    if cooking_method is not _MISSING and cooking_method is not None and cooking_method not in PRESCRIPTION_COOKING_METHODS:
        _err(errors, "defaults.cooking_method", "煎法只能是 %s" % " / ".join(PRESCRIPTION_COOKING_METHODS))
    _check_bool(errors, "defaults.remote", defaults.get("remote", _MISSING))


def _check_string_lengths(node, errors, path):
    """§9.0：單個字符串 ≤ 2000 字（遞歸進未知鍵，防前端誤塞大文本）。"""
    if isinstance(node, str):
        if len(node) > TEMPLATE_MAX_STRING_LEN:
            _err(errors, path, "單個字串不得超過 %d 字" % TEMPLATE_MAX_STRING_LEN)
    elif isinstance(node, dict):
        for key, value in node.items():
            _check_string_lengths(value, errors, ("%s.%s" % (path, key)) if path else str(key))
    elif isinstance(node, list):
        for index, value in enumerate(node):
            _check_string_lengths(value, errors, "%s[%d]" % (path, index))


def validate_template_schema(template_type, schema_obj):
    """【格式校驗】§9 四類字段級契約。返回 `(ok, errors)`，errors = `[{"path","msg"}]`。

    只攔截、不清洗：非法值原樣報錯（例如 `role` 不在白名單 → 接口層 400 `schema_invalid`）；
    未知鍵忽略且原樣保留（前向兼容）；`version` 缺失視為 1（存量回填行沒有該鍵，派生後仍須可保存 / 發佈）。
    """
    errors = []
    if template_type not in TEMPLATE_TYPES:
        _err(errors, "type", "未知模板類型：%s" % template_type)
        return False, errors
    if not isinstance(schema_obj, dict):
        _err(errors, "", "schema_json 必須是 JSON 物件")
        return False, errors

    version = schema_obj.get("version", _MISSING)
    if version is not _MISSING and version is not None and (not _is_int(version) or version < 1):
        _err(errors, "version", "version 必須是 >= 1 的整數")
    meta = schema_obj.get("meta", _MISSING)
    if meta is not _MISSING and meta is not None and not isinstance(meta, dict):
        _err(errors, "meta", "meta 必須是 JSON 物件")

    if template_type == "inquiry":
        _validate_inquiry(schema_obj, errors)
    elif template_type == "record":
        _validate_record(schema_obj, errors)
    elif template_type == "treatment":
        _validate_treatment(schema_obj, errors)
    else:
        _validate_prescription(schema_obj, errors)

    _check_string_lengths(schema_obj, errors, "")
    return (not errors), errors


def validate_template_schema_for_publish(template_type, schema_obj):
    """【發佈級校驗】= 格式校驗 + 完整性（§9.1「至少 1 項必問」/ §9.2「至少 1 段留待老師」/ §9.3「content 非空」）。

    草稿允許半成品（`POST` / `PUT` 只跑格式校驗），發佈必須完整（§9.0 校驗時機）。
    """
    ok, errors = validate_template_schema(template_type, schema_obj)
    if not ok or not isinstance(schema_obj, dict):
        return False, errors

    if template_type == "inquiry":
        fields = schema_obj.get("fields") or []
        if len(fields) < 3:
            _err(errors, "fields", "發佈前至少要有 3 項問診（目前 %d 項）" % len(fields))
        if not any(isinstance(f, dict) and f.get("required") is True for f in fields):
            _err(errors, "fields", "發佈前請至少標記 1 項為「必問」")
    elif template_type == "record":
        sections = schema_obj.get("sections") or []
        if len(sections) < 2:
            _err(errors, "sections", "發佈前至少要有 2 段（目前 %d 段）" % len(sections))
        if not any(isinstance(s, dict) and s.get("writable_by") == "teacher" for s in sections):
            _err(errors, "sections", "發佈前請至少保留 1 段「留待老師」（智能體永不填寫）")
    elif template_type == "treatment":
        if not str(schema_obj.get("content") or "").strip():
            _err(errors, "content", "發佈前施治內容不可為空")
    return (not errors), errors


def serialize_template_schema(schema_obj):
    """序列化為 TEXT 存庫（§9.0）。超過 64 KB → `TemplateError('schema_too_large')`。"""
    text = json.dumps(schema_obj, ensure_ascii=False)
    if len(text.encode("utf-8")) > TEMPLATE_MAX_SCHEMA_BYTES:
        raise TemplateError(
            "schema_too_large",
            "模板內容超過 %d KB" % (TEMPLATE_MAX_SCHEMA_BYTES // 1024),
        )
    return text


def parse_template_schema(text):
    """反序列化；髒數據（非法 JSON / 非物件）一律降級為 `{}`，不讓列表 / 詳情接口 500。"""
    if not text:
        return {}
    try:
        parsed = json.loads(text)
    except (TypeError, ValueError):
        return {}
    return parsed if isinstance(parsed, dict) else {}


# ---------- 存取與狀態機（§10 / §11）----------

_SCOPE_WHERE = "lineage_id = ? AND teacher_id = ? AND type = ?"


def template_store_ready():
    """`templates` 表是否就位：遷移未跑（或表被改名）→ False，接口層回 503 `template_store_unavailable`（§7）。"""
    try:
        conn = get_connection()
        try:
            row = conn.execute(
                "SELECT name FROM sqlite_master WHERE type = 'table' AND name = 'templates'"
            ).fetchone()
        finally:
            conn.close()
        return row is not None
    except sqlite3.Error:
        return False


def _template_row_to_dict(row, include_schema=True):
    """模板行 → 接口響應物件（§10.1 表）。`is_legacy` = 存量回填而來（前端顯示「存量遷移」標籤）。"""
    data = dict(row)
    schema_obj = parse_template_schema(data.get("schema_json"))
    meta = schema_obj.get("meta")
    data["is_legacy"] = isinstance(meta, dict) and meta.get("legacy_source") == LEGACY_SOURCE_PLAN_TEMPLATES
    if include_schema:
        data["schema_json"] = schema_obj
    else:
        data.pop("schema_json", None)
    return data


def _fetch_template(cur, template_id):
    return cur.execute("SELECT * FROM templates WHERE id = ?", (template_id,)).fetchone()


def _find_scope_draft(cur, teacher_id, template_type, lineage_id=""):
    """同 scope 的草稿（語義上最多一條；取版本號最大者兜底）。§4.3 第 4 條：不產生第二份草稿。"""
    return cur.execute(
        "SELECT * FROM templates WHERE " + _SCOPE_WHERE + " AND status = 'draft' "
        "ORDER BY version DESC, id DESC LIMIT 1",
        (lineage_id, teacher_id, template_type),
    ).fetchone()


def _scope_max_version(cur, teacher_id, template_type, lineage_id=""):
    row = cur.execute(
        "SELECT MAX(version) AS v FROM templates WHERE " + _SCOPE_WHERE,
        (lineage_id, teacher_id, template_type),
    ).fetchone()
    return row["v"] or 0


def create_or_reuse_template(teacher_id, template_type, name, schema_obj, lineage_id=""):
    """§10.2 #4：同 scope 已有 `draft` → 複用（`reused=True`，不新建第二份草稿）；否則新建草稿。

    版本號：首次創建 = 1；同 scope 已有版本（例如存量回填的 v1 仍生效）→ 取下一號，
    保證鏈內 `version` 單調不重複（§4.2 公式在「無父版本」情形的退化，見 §4.2 公式說明）。
    返回 `(row, reused)`。
    """
    conn = get_connection()
    try:
        cur = conn.cursor()
        existing = _find_scope_draft(cur, teacher_id, template_type, lineage_id)
        if existing is not None:
            return _template_row_to_dict(existing), True
        version = _scope_max_version(cur, teacher_id, template_type, lineage_id) + 1
        now = datetime.now().isoformat()
        cur.execute(
            "INSERT INTO templates (type, lineage_id, teacher_id, name, schema_json, version, "
            "parent_template_id, status, created_at, updated_at) "
            "VALUES (?, ?, ?, ?, ?, ?, NULL, 'draft', ?, ?)",
            (template_type, lineage_id, teacher_id, name, serialize_template_schema(schema_obj), version, now, now),
        )
        new_id = cur.lastrowid
        conn.commit()
        return _template_row_to_dict(_fetch_template(cur, new_id)), False
    finally:
        conn.close()


def get_template(template_id):
    """單條模板（含解析後的 `schema_json`）；不存在返回 None（接口層回 404）。"""
    conn = get_connection()
    try:
        row = _fetch_template(conn.cursor(), template_id)
    finally:
        conn.close()
    return _template_row_to_dict(row) if row is not None else None


def list_templates(teacher_id, template_type=None, status=None, include_schema=True):
    """§10.2 #1：該老師的模板列表（排序 `type asc, version desc`）+ 四類總數 `counts`。

    `counts` 是「該老師該類型全部模板數」，**不受** type / status 過濾影響（前端頁簽徽章用）。
    """
    conn = get_connection()
    try:
        conditions = ["teacher_id = ?"]
        params = [teacher_id]
        if template_type:
            conditions.append("type = ?")
            params.append(template_type)
        if status:
            conditions.append("status = ?")
            params.append(status)
        rows = conn.execute(
            "SELECT * FROM templates WHERE " + " AND ".join(conditions) +
            " ORDER BY type ASC, version DESC, id DESC",
            params,
        ).fetchall()
        counts = {key: 0 for key in TEMPLATE_TYPES}
        for row in conn.execute(
            "SELECT type, COUNT(*) AS c FROM templates WHERE teacher_id = ? GROUP BY type", (teacher_id,)
        ):
            if row["type"] in counts:
                counts[row["type"]] = row["c"]
    finally:
        conn.close()
    return [_template_row_to_dict(row, include_schema) for row in rows], counts


def get_active_template(teacher_id, template_type, lineage_id=""):
    """§10.2 #3：該 scope 的生效模板；None = 無生效模板（生成側回落內置骨架，不報錯，§11.2）。"""
    conn = get_connection()
    try:
        row = conn.execute(
            "SELECT * FROM templates WHERE " + _SCOPE_WHERE + " AND status = 'active' LIMIT 1",
            (lineage_id, teacher_id, template_type),
        ).fetchone()
    finally:
        conn.close()
    return _template_row_to_dict(row) if row is not None else None


def list_template_chain(template_id):
    """§10.2 #2 的 `chain`：同 scope（lineage_id / teacher_id / type）全部版本，`version` 降序。

    Epic 1 `lineage_id` 恒為 `''`，故「鏈」= 該老師該類型的全部版本（§4.2 版本鏈）。
    """
    conn = get_connection()
    try:
        cur = conn.cursor()
        row = _fetch_template(cur, template_id)
        if row is None:
            return []
        rows = cur.execute(
            "SELECT id, version, status, updated_at FROM templates WHERE " + _SCOPE_WHERE +
            " ORDER BY version DESC, id DESC",
            (row["lineage_id"], row["teacher_id"], row["type"]),
        ).fetchall()
    finally:
        conn.close()
    return [dict(row) for row in rows]


def update_template_draft(template_id, name=None, schema_obj=None):
    """§10.2 #5：只允許改 `name` / `schema_json`，且只在 `draft` 狀態。

    `status != 'draft'` → `TemplateError('template_published_immutable')`（批復 3：已發佈版本不可原地改，
    前端據此改走「基於此版本修訂」→ §11.4 derive）。返回 `(row, changed)`。
    """
    conn = get_connection()
    try:
        cur = conn.cursor()
        row = _fetch_template(cur, template_id)
        if row is None:
            raise TemplateError("template_not_found", "找不到該模板")
        if row["status"] != "draft":
            raise TemplateError(
                "template_published_immutable",
                "已發佈或已歸檔的版本不可直接修改，請用「基於此版本修訂」派生新版本",
            )
        assignments = []
        params = []
        if name is not None:
            assignments.append("name = ?")
            params.append(name)
        if schema_obj is not None:
            assignments.append("schema_json = ?")
            params.append(serialize_template_schema(schema_obj))
        if not assignments:
            return _template_row_to_dict(row), False
        assignments.append("updated_at = ?")
        params.append(datetime.now().isoformat())
        params.append(template_id)
        cur.execute("UPDATE templates SET " + ", ".join(assignments) + " WHERE id = ?", params)
        conn.commit()
        return _template_row_to_dict(_fetch_template(cur, template_id)), True
    finally:
        conn.close()


def _scope_active_ids(cur, teacher_id, template_type, lineage_id, exclude_id):
    return [
        row["id"]
        for row in cur.execute(
            "SELECT id FROM templates WHERE " + _SCOPE_WHERE + " AND status = 'active' AND id != ?",
            (lineage_id, teacher_id, template_type, exclude_id),
        )
    ]


def set_template_active(template_id):
    """§11.1 publish / §11.3 activate 共用的**原子**切換（同一 SQLite 事務）：

    ① SELECT 該 scope 現有 `active`（排除本行）→ ② UPDATE 這些行 → `archived`，id 收進 `archived_ids`
    → ③ UPDATE 本行 → `active` → ④ COMMIT。順序不可換：否則瞬時違反 `uq_templates_active_one`；
    失敗整體回滾 → 不會出現「scope 無 active」的空窗。返回 `(row, archived_ids, changed)`。
    """
    conn = get_connection()
    try:
        cur = conn.cursor()
        row = _fetch_template(cur, template_id)
        if row is None:
            raise TemplateError("template_not_found", "找不到該模板")
        stale = _scope_active_ids(cur, row["teacher_id"], row["type"], row["lineage_id"], template_id)
        if row["status"] == "active":
            if not stale:
                # §11.1 冪等：本行已是 active 且 scope 無其它 active → 200 changed=False
                return _template_row_to_dict(row), [], False
            # 理論上不可達（部分唯一索引已擋住兩條 active）；兜底按併發衝突處理，不悄悄改數據。
            raise TemplateError("template_active_conflict", "同一類型已存在生效版本，請重試")

        now = datetime.now().isoformat()
        archived_ids = list(stale)
        if archived_ids:
            placeholders = ", ".join("?" for _ in archived_ids)
            cur.execute(
                "UPDATE templates SET status = 'archived', updated_at = ? WHERE id IN (" + placeholders + ")",
                [now] + archived_ids,
            )
        cur.execute("UPDATE templates SET status = 'active', updated_at = ? WHERE id = ?", (now, template_id))
        conn.commit()
        return _template_row_to_dict(_fetch_template(cur, template_id)), archived_ids, True
    except TemplateError:
        conn.rollback()
        raise
    except sqlite3.IntegrityError as exc:
        # §11.1 併發兜底：翻譯成 409 template_active_conflict（附「請重試」），不暴露原始錯誤
        conn.rollback()
        raise TemplateError("template_active_conflict", "同一類型已存在生效版本，請重試") from exc
    finally:
        conn.close()


def archive_template(template_id):
    """§11.2：`active` / `draft` → `archived`；已是 `archived` → 冪等 `changed=False`。返回 `(row, changed)`。"""
    conn = get_connection()
    try:
        cur = conn.cursor()
        row = _fetch_template(cur, template_id)
        if row is None:
            raise TemplateError("template_not_found", "找不到該模板")
        if row["status"] == "archived":
            return _template_row_to_dict(row), False
        cur.execute(
            "UPDATE templates SET status = 'archived', updated_at = ? WHERE id = ?",
            (datetime.now().isoformat(), template_id),
        )
        conn.commit()
        return _template_row_to_dict(_fetch_template(cur, template_id)), True
    finally:
        conn.close()


def derive_template_from(source_id, teacher_id, parent_template_id=None, name=None):
    """§11.4 派生新版本（前端「基於此版本修訂」）。返回 `(row, reused_draft)`。

    強校驗（§4.3 五條，全部走 TemplateError → 接口層 400 / 403）：
      ① 來源（即父版本）必須存在 → `template_parent_not_found`；
      ② 父與來源必須同 `teacher_id` / `lineage_id` / `type` → `template_parent_scope_mismatch`
         （`parent_template_id` 由前端可選上報，必須與路徑來源一致，禁跨老師 / 跨師門 / 跨類型掛鏈）；
      ③ 自引用（行的 `parent_template_id` 指向自身，髒數據）→ `template_parent_self_reference`；
      ④ 不可派生指向未來版本的行 → `template_parent_future_version`；
      ⑤ 同鏈已有 `draft` → **複用該行**（不產生第二份草稿）。

    版本號 = `max(父版本 + 1, 鏈內現有 max(version) + 1)`（§4.2：單調遞增，處理「歸檔草稿占用版本號」）。
    新草稿的 `schema_json` 逐字節複製父行（凍結快照，§4.4 歷史零回溯）。
    """
    conn = get_connection()
    try:
        cur = conn.cursor()
        source = _fetch_template(cur, source_id)
        if source is None:
            raise TemplateError("template_parent_not_found", "找不到要修訂的版本")
        if source["teacher_id"] != teacher_id:
            raise TemplateError("template_parent_scope_mismatch", "不可跨老師修訂模板")
        if parent_template_id is not None and parent_template_id != source_id:
            parent = _fetch_template(cur, parent_template_id)
            if parent is None:
                raise TemplateError("template_parent_not_found", "找不到指定的父版本")
            if (parent["teacher_id"], parent["lineage_id"], parent["type"]) != (
                source["teacher_id"], source["lineage_id"], source["type"]
            ):
                raise TemplateError("template_parent_scope_mismatch", "父版本與來源不屬於同一老師 / 師門 / 類型")
            raise TemplateError("template_parent_scope_mismatch", "parent_template_id 必須與來源模板一致")
        if source["parent_template_id"] == source["id"]:
            raise TemplateError("template_parent_self_reference", "父版本不可指向自身")
        scope_max = _scope_max_version(cur, source["teacher_id"], source["type"], source["lineage_id"])
        if source["version"] > scope_max:
            raise TemplateError("template_parent_future_version", "不可基於未來版本修訂")
        existing_draft = _find_scope_draft(cur, source["teacher_id"], source["type"], source["lineage_id"])
        if existing_draft is not None:
            return _template_row_to_dict(existing_draft), True

        now = datetime.now().isoformat()
        cur.execute(
            "INSERT INTO templates (type, lineage_id, teacher_id, name, schema_json, version, "
            "parent_template_id, status, created_at, updated_at) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, 'draft', ?, ?)",
            (
                source["type"],
                source["lineage_id"],
                source["teacher_id"],
                name or source["name"],
                source["schema_json"],
                max(source["version"] + 1, scope_max + 1),
                source_id,
                now,
                now,
            ),
        )
        new_id = cur.lastrowid
        conn.commit()
        return _template_row_to_dict(_fetch_template(cur, new_id)), False
    finally:
        conn.close()


def template_herb_warnings(teacher_name, schema_obj):
    """§9.4：`prescription` 模板裏的藥材不在該老師 `herb_inventory` → **200 通過** + `warnings` 黃字提醒。

    不阻斷保存（老師可能先配模板、後補庫存）。返回 `[{"code": "herb_not_in_inventory", "herb_name": …}]`。
    """
    if not isinstance(schema_obj, dict):
        return []
    names = []
    for herb in schema_obj.get("herbs") or []:
        if isinstance(herb, dict) and isinstance(herb.get("herb_name"), str) and herb["herb_name"]:
            names.append(herb["herb_name"])
    for formula in schema_obj.get("formulas") or []:
        if not isinstance(formula, dict):
            continue
        for part in formula.get("composition") or []:
            if isinstance(part, dict) and isinstance(part.get("herb_name"), str) and part["herb_name"]:
                names.append(part["herb_name"])
    if not names:
        return []
    conn = get_connection()
    try:
        known = {
            row["herb_name"]
            for row in conn.execute("SELECT herb_name FROM herb_inventory WHERE teacher_name = ?", (teacher_name,))
        }
    except sqlite3.Error:
        return []
    finally:
        conn.close()
    warnings = []
    seen = set()
    for herb_name in names:
        if herb_name in known or herb_name in seen:
            continue
        seen.add(herb_name)
        warnings.append({"code": "herb_not_in_inventory", "herb_name": herb_name})
    return warnings