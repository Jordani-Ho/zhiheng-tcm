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


# ---------- 【Epic 4 §3.2 / §4.4】老師端讀點的作用域校驗（單一入口） ----------
def lineage_read_scope(teacher_name, lineage_id=None):
    """老師端讀點的**統一作用域校驗**：本檔所有帶師門隔離的讀函數只經這一個入口。

    返回 `(filter_on, lineage_id)`：
      · flag off（`LINEAGE_ENABLED` 未設 / off，默認）→ `(False, "")`：**不發任何 SQL**、
        不校驗、不拋異常，調用方的語句與參數**逐字節不變**（§4.4「flag off = 零行為變化」）；
      · flag on → `(True, <合法 lineage_id>)`，調用方把 `lineage_id = ?` 加進 WHERE。

    校驗口徑（存在性 + 歸屬雙因子）與錯誤碼契約全在 `lineage_service`（單一真相源）：
    空 → 400 `lineage_required` / 格式非法 → 400 `lineage_invalid` / 表缺失 → 503
    `lineage_store_unavailable` / 不存在 → 404 `lineage_not_found` / 不屬於該師門 → 403
    `lineage_forbidden`。

    **`import lineage_service` 放在函數體內**：與 `_agent_stage_snapshot_enabled()` 同口徑，
    保證模組載入期 `database` ↔ `lineage_service` 兩個方向都不成立循環依賴。
    """
    import lineage_service
    return lineage_service.lineage_read_scope(teacher_name, lineage_id)


# ============================================================================
# 【Epic 1 結構重構】向後兼容 re-export：本檔自此只保留「引擎 / 連接 / 建表」職責
#   backend/template_service.py : 白名單 / 默認骨架 / schema_json 校驗層 / 存取與狀態機
#   backend/models.py           : /api/templates 的 Pydantic 請求體
# 舊調用點 `database.xxx`（main.py / template_api.py / test_templates.py / test_migrations.py）
# 與既有測試、文檔、遷移腳本**一字不改**；兩處搬移皆為純結構重構、零邏輯改動。
# 依賴方向單向（database → template_service）：模板層只在「呼叫時」延遲取回 database 的連接與
# 白名單常數，因此不存在循環 import。
# 注意：**不要** 在此 re-export `template_service.get_connection` —— 那是同名延遲 shim，
#       會蓋掉本檔的真實現。
# ============================================================================
from models import (  # noqa: F401  (向後兼容：請求體舊入口)
    TemplateActionInput,
    TemplateCreateInput,
    TemplateDeriveInput,
    TemplateUpdateInput,
)
from template_service import (  # noqa: F401  (向後兼容：模板服務層舊入口)
    TEMPLATE_TYPES,
    TEMPLATE_STATUSES,
    TEMPLATE_TYPE_LABELS,
    TEMPLATE_SCHEMA_VERSION,
    TEMPLATE_MAX_STRING_LEN,
    TEMPLATE_MAX_SCHEMA_BYTES,
    TEMPLATE_KEY_RE,
    ANSWER_TYPES,
    WRITABLE_BY_VALUES,
    TREATMENT_FORMATS,
    LEGACY_SOURCE_PLAN_TEMPLATES,
    TemplateError,
    _DEFAULT_INQUIRY_FIELDS,
    _DEFAULT_RECORD_SECTIONS,
    _DEFAULT_RECORD_FORBIDDEN,
    default_template_schema,
    _MISSING,
    _err,
    _is_int,
    _check_text,
    _check_bool,
    _check_order,
    _check_list,
    _scan_items,
    _validate_inquiry_field,
    _validate_choices,
    _validate_record_section,
    _validate_herb_fields,
    _validate_prescription_herb,
    _validate_formula,
    _validate_inquiry,
    _validate_record,
    _validate_treatment,
    _validate_prescription,
    _check_string_lengths,
    validate_template_schema,
    validate_template_schema_for_publish,
    serialize_template_schema,
    parse_template_schema,
    _SCOPE_WHERE,
    template_store_ready,
    _template_row_to_dict,
    _fetch_template,
    _find_scope_draft,
    _scope_max_version,
    create_or_reuse_template,
    get_template,
    list_templates,
    get_active_template,
    list_template_chain,
    update_template_draft,
    _scope_active_ids,
    set_template_active,
    archive_template,
    derive_template_from,
    template_herb_warnings,
    TEMPLATE_API_ENABLED_VALUES,
    template_api_enabled,
    get_active_record_template,
    record_section_skeleton,
    sync_legacy_plan_template,
)


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

def get_teacher_patients(teacher_name, lineage_id=None):
    """【Epic 4 §3.2 P0-①】老師端學生列表：flag on 時必須**同時**命中 `pt.lineage_id`。

    `(False, "")` 分支（flag off / 默認）下 `owner_where` 拼出的字面量與改動前**逐字節相同**：
    `WHERE pt.teacher_name = ? AND pt.status = 'active'`。
    """
    filter_on, lineage_id = lineage_read_scope(teacher_name, lineage_id)
    owner_where = "pt.lineage_id = ? AND pt.teacher_name = ?" if filter_on else "pt.teacher_name = ?"
    owner_params = (lineage_id, teacher_name) if filter_on else (teacher_name,)
    conn = get_connection()
    rows = conn.execute("""
        SELECT p.name, p.last_active_at,
               COALESCE(a.points, 0) as points
        FROM patients p
        INNER JOIN patient_teachers pt ON p.name = pt.patient_name
        LEFT JOIN points_accounts a ON p.name = a.role_name
        WHERE """ + owner_where + """ AND pt.status = 'active'
        ORDER BY p.name
    """, owner_params).fetchall()
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
def get_homework(patient_name, teacher_name, lineage_id=None):
    """【Epic 4 §3.2 P0-④】聯絡簿：flag on 時須 `lineage_id = ? AND patient_name = ? AND teacher_name = ?`。"""
    filter_on, lineage_id = lineage_read_scope(teacher_name, lineage_id)
    owner_where = "lineage_id = ? AND patient_name = ? AND teacher_name = ?" if filter_on \
        else "patient_name = ? AND teacher_name = ?"
    owner_params = (lineage_id, patient_name, teacher_name) if filter_on else (patient_name, teacher_name)
    conn = get_connection()
    row = conn.execute("SELECT * FROM homework WHERE " + owner_where + " ORDER BY id DESC LIMIT 1",
                       owner_params).fetchone()
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

def get_transcriptions(patient_name=None, teacher_name=None, lineage_id=None):
    """【Epic 4 §3.2 P0-⑤】待處理轉述：flag on 且帶 teacher_name 時**前置** `lineage_id = ?`。

    位置在條件列表**最前**（`conditions` 首元素仍是 `processed = 0`，lineage 只插在
    teacher_name 之前），故 flag off 時 `' AND '.join(conditions)` 結果與改動前逐字節相同。
    只傳 `patient_name` 不傳 `teacher_name`（學生端讀法）→ flag on 時 `lineage_read_scope`
    按 §3.2「teacher_name 可空 = 高危」直接 400，**不退化為跨師門查詢**。
    """
    filter_on, lineage_id = lineage_read_scope(teacher_name, lineage_id)
    conn = get_connection()
    conditions = ["processed = 0"]
    params = []
    if patient_name:
        conditions.append("patient_name = ?")
        params.append(patient_name)
    if teacher_name:
        if filter_on:
            conditions.append("lineage_id = ?")
            params.append(lineage_id)
        conditions.append("teacher_name = ?")
        params.append(teacher_name)
    query = f"SELECT * FROM transcriptions WHERE {' AND '.join(conditions)} ORDER BY id DESC"
    rows = conn.execute(query, params).fetchall()
    conn.close()
    return [dict(r) for r in rows]

# ---------- 病历草案相关操作 ----------
# 【Epic 1 §12.1 / §12.2】`drafts` 的模板引用两列由迁移 0002 添加（DDL 单一真相源，init_db() 不写）；
# 下面的探测让「迁移未跑的老库」依旧走五列 INSERT —— 旧链路行为一字不变（§12.2 第 2 条回归红线）。
_DRAFT_TEMPLATE_REF_COLUMNS = ("template_id", "template_version")


def _drafts_supports_template_refs(conn):
    """`drafts.template_id / template_version` 是否就位（迁移 0002 未跑 / drafts 未建 → False）。"""
    try:
        columns = {row["name"] for row in conn.execute("PRAGMA table_info('drafts')")}
    except sqlite3.Error:
        return False
    return set(_DRAFT_TEMPLATE_REF_COLUMNS) <= columns


def _table_has_columns(conn, table, columns):
    """表列探测的**唯一实现**（Epic 2 两个快照列共用；迁移未跑 / 表未建 → False，不抛异常）。

    · 施工步骤 2.3 起由 `_drafts_supports_ai_original()` 与 `_patient_records_supports_ai_original()`
      共用 —— CTO step 2.3 追加要求 1 的同一条纪律：**同一个判断只许有一份实现**。
    · `table` 只接受本模块内写死的表名常量，**不是**用户输入（故 f-string 拼接无注入面）；
      探测语句的形状（`PRAGMA table_info('drafts')`）是 Epic 1 / step 2.2 既有基线依赖的，改不得。
    """
    try:
        existing = {row["name"] for row in conn.execute(f"PRAGMA table_info('{table}')")}
    except sqlite3.Error:
        return False
    return set(columns) <= existing


# 【Epic 2 §4.2 改 1 / §7.1-①】`drafts.ai_original_content` = AI 原始输出的**不可变快照**，由迁移 0003 添加。
# 写入条件是**双闸门**（CTO 裁决①）：总闸 flag **on** 且 该列已就位；两者任一为假 → 原 SQL 一字不改。
_DRAFT_AI_SNAPSHOT_COLUMNS = ("ai_original_content",)

# 【Epic 2 §4.2 改 2a】`patient_records.ai_original_text` = 签字时从草案带过来的**同一份快照**（迁移 0003 添加）。
# 写入条件同款双闸门：flag **on** 且 该列已就位；任一为假 → 改动前的 6 列 INSERT 一字不改（§5.1 红线①）。
_PATIENT_RECORD_AI_SNAPSHOT_COLUMNS = ("ai_original_text",)


def _drafts_supports_ai_original(conn):
    """`drafts.ai_original_content` 是否就位（迁移 0003 未跑 / drafts 未建 → False）。"""
    return _table_has_columns(conn, "drafts", _DRAFT_AI_SNAPSHOT_COLUMNS)


def _patient_records_supports_ai_original(conn):
    """`patient_records.ai_original_text` 是否就位（迁移 0003 未跑 / patient_records 未建 → False）。"""
    return _table_has_columns(conn, "patient_records", _PATIENT_RECORD_AI_SNAPSHOT_COLUMNS)


def _agent_stage_snapshot_enabled():
    """总闸 `AGENT_STAGE_ENABLED`（§4.5-① flag 判定，**默认 off**）—— 两个快照列（改 1 / 改 2a）的共用闸门。

    真相源在服务层（CTO 裁决②「方案 B」：`agent_stage_service.agent_stage_enabled()`），此处**函数内延迟
    import**，两个理由：
      · `agent_stage_service` 对 `database` 零 import（那条依赖已断）→ 本函数反向延迟取用，**无循环依赖**；
      · 被延迟取用的模块是「纯常量 + 一个 env 判读函数」（零 DB、零副作用），import 本身不改动任何行为；
        **flag off 时本函数只读 env、一条 SQL 都不发**（调用方必须把它放在列探测之前以短路）→
        既有链路的执行语句序列与改动前逐字节一致（§5.5-① 硬门槛，测试有逐字节比对）。

    两态纪律（沿用裁决④）：服务层缺失 / 无该函数 → **静默按 off**（闸门不可知时绝不写新列）；
    闸门自身抛异常 → 打一行 warn 后按 off，**绝不打断**既有生成 / 签字链路。
    """
    try:
        import agent_stage_service
    except Exception:
        return False
    checker = getattr(agent_stage_service, "agent_stage_enabled", None)
    if not callable(checker):
        return False
    try:
        return bool(checker())
    except Exception as exc:
        print(f"[warn] AGENT_STAGE_ENABLED 闸门读取失败，按 off 处理：{exc}")
        return False


def _draft_ai_snapshot(draft):
    """【Epic 2 §4.2 改 2a】要落进 `patient_records.ai_original_text` 的值 = 草案的不可变快照。

    真相源是 `drafts.ai_original_content`（改 1 落库时写下的**生成时刻** content）；只在下面两种
    「根本拿不到快照」的情形才回落 `content`（设计 §4.2 改 2a 原文：「为空则回落 content」）：
      ① 快照是空串 —— 该草案落库时 flag 关（或迁移前的老草案），§1.4「不删列」的既有数据；
      ② 快照列不存在 —— 迁移 0003 未跑的老库（`sqlite3.Row` 取未知键抛 IndexError）。

    边界（与 CTO 裁决③「不回落 content」不冲突）：**快照非空时永远以快照为准**，老师编辑后的
    `content` 绝不覆盖它 —— 否则学习轨迹会把「有快照」污成「零修改」。也就是说本函数只会
    在「无快照」时借用 content，不会在「有快照」时用 content 顶替。
    """
    try:
        snapshot = draft["ai_original_content"]
    except (IndexError, KeyError):
        return draft["content"]
    return snapshot or draft["content"]


def _call_agent_stage_hook(hook_name, *args):
    """【Epic 2 §4.2 改 2b】签字 / 请示落定后**best-effort** 通知服务层（延迟 import，两态显式）。

    库层只做转发：一行延迟 import + 一次 `getattr` 调用；flag 判定、样本、指标全在服务层
    （§5.1 红线①「flag off → 不算指标」由钩子自身首行闸门负责，库层不替它判 —— 否则就会出现
    第二个 flag 判断，违背 CTO step 2.3 追加要求 1）。延迟 import 与 `save_plan_template()`
    里 `import template_service`（§4.2 改 2 引注）同款，回避循环引用。

    两态纪律（CTO step 2.3 追加要求 2，与 `_agent_stage_snapshot_enabled()` 逐字同款）：
      · 服务层不可导入 / 该属性不存在 → `getattr(..., None)` + `callable()` 判 false →
        **静默 no-op**（不留任何输出）。`on_draft_signed` 属施工步骤 3，本步落地时**尚不存在**，
        走的正是这一态 —— 因此今天的 `sign_draft()` 与改动前行为一致（§5.1 红线③）。
      · 钩子存在但抛异常 → `print` 一行 warn，**绝不冒泡**：签字已经 commit，不得因评估失败
        而让老师看到失败（红线③「返回值 / 删除草案 / signed 语义不变」）。

    返回「是否真的调用了钩子」（仅供测试断言用，生产调用方一律忽略）。
    """
    try:
        import agent_stage_service
    except Exception:
        return False
    hook = getattr(agent_stage_service, hook_name, None)
    if not callable(hook):
        return False
    try:
        hook(*args)
        return True
    except Exception as exc:
        print(f"[warn] agent_stage_service.{hook_name} 调用失败（已忽略，签字结果不受影响）：{exc}")
        return False


def insert_draft(transcript_id, patient_name, teacher_name, content, template_id=0, template_version=0):
    """新增病历草案，返回 draft_id。

    【Epic 1 §12.2 第 1 条】前四个位置参数**不变**：老调用方（`seed_test_data.py` 等）原样可跑，
    新增的 `template_id` / `template_version` 缺省 0 = 未记录（老数据 / 无模板生成）。

    【Epic 2 §4.2 改 1】**只追加一个快照列，签名 / 参数顺序 / 返回值一概不变**：
    双闸门（flag on 且 `drafts.ai_original_content` 列就位）为真时，把**同一份 `content`** 同时写进
    快照列（= AI 原始输出 = 落库时刻的 content；此后任何老师编辑只改 `content`，快照不可变，§3.3 / §4.2-1）；
    任一闸门为假 → 走**改动前逐字节一致**的原 SQL（老库 / flag off 两条路都零变化，§5.5-①）。
    """
    conn = get_connection()
    # 【Epic 2 §4.2 改 1 · 双闸门，CTO 裁决①】flag 先判（廉价、零 SQL），再探列：
    # flag off 时连列的 PRAGMA 都不发 → 「探测 + INSERT + UPDATE」三条语句与改动前逐字节一致（§5.5-① 硬门槛）。
    ai_snapshot_enabled = _agent_stage_snapshot_enabled() and _drafts_supports_ai_original(conn)
    supports_template_refs = _drafts_supports_template_refs(conn)
    if supports_template_refs and ai_snapshot_enabled:           # ① 模板引用列 + 快照列
        cursor = conn.execute(
            "INSERT INTO drafts (transcript_id, patient_name, teacher_name, content, signed, "
            "template_id, template_version, ai_original_content) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
            (transcript_id, patient_name, teacher_name, content, 0, template_id or 0, template_version or 0, content))
    elif supports_template_refs:                                # ② 原 7 列：字面量逐字不变
        cursor = conn.execute(
            "INSERT INTO drafts (transcript_id, patient_name, teacher_name, content, signed, "
            "template_id, template_version) VALUES (?, ?, ?, ?, ?, ?, ?)",
            (transcript_id, patient_name, teacher_name, content, 0, template_id or 0, template_version or 0))
    elif ai_snapshot_enabled:                                   # ③ 只有快照列（无模板引用列）
        cursor = conn.execute("INSERT INTO drafts (transcript_id, patient_name, teacher_name, content, signed, ai_original_content) VALUES (?, ?, ?, ?, ?, ?)",
                              (transcript_id, patient_name, teacher_name, content, 0, content))
    else:                                                       # ④ 原 5 列：字面量逐字不变
        cursor = conn.execute("INSERT INTO drafts (transcript_id, patient_name, teacher_name, content, signed) VALUES (?, ?, ?, ?, ?)",
                              (transcript_id, patient_name, teacher_name, content, 0))
    conn.execute("UPDATE transcriptions SET processed = 1 WHERE id = ?", (transcript_id,))
    conn.commit()
    draft_id = cursor.lastrowid
    conn.close()

    # 【Epic 3 §4.2 改 1 · 施工步骤 3.3-c】草案已落库 → best-effort 追加 `draft_generated` 学习事件。
    # 纪律五条（与 `sign_draft()` 末尾那段同款，转发器本体见 `_call_agent_stage_hook`）：
    #   · **只经唯一转发点** `_call_agent_stage_hook()`（钩子名 = `on_draft_generated`，按**名字**
    #     `getattr` 派发）—— 库层不 import 学习服务层、不判 flag、不拼 payload、不自行吞写入异常；
    #   · 放在 commit/close **之后**：事件写入失败绝不回滚草案落库，`return draft_id` 一字不改
    #     （§9-声明一 / 与 §5.1 红线③ 同口径）；
    #   · **归一化在调用方做**（CTO 3.3-a 追加 1 方案 c）：`_normalize_metric_text(text, 2000)`
    #     —— 只为它在本函数内**局部** import 服务层（本档模块顶层不新增 import）；
    #   · **参数按位置传**（转发器签名是 `(hook_name, *args)`，没有 kwargs）：第 6 位 = 适配器的
    #     `content_hash` 槽，3.3-c 口径 = **归一化后的正文**（截断 2000，不是哈希）；
    #     `template_id` / `template_version` 与落库口径一致（`or 0`）；
    #   · 整段 try/except 静默兜底 —— 钩子缺失 / 归一化拿不到服务层时都只是「不发事件」，绝不影响
    #     上面那个返回值。
    try:
        import agent_stage_service
        normalized_content = agent_stage_service._normalize_metric_text(content, 2000)
        _call_agent_stage_hook("on_draft_generated", teacher_name, draft_id, patient_name,
                               template_id or 0, template_version or 0, normalized_content)
    except Exception:
        pass
    return draft_id

def get_drafts(teacher_name=None, lineage_id=None):
    """【Epic 4 §3.2 P0-②】未簽草案：flag on 時**子查詢內部**就帶 `lineage_id = ?`。

    子查詢決定「每個學生的最新未簽草案」，只在外層過濾會把「本師門沒有草案、別師門有」的
    學生整行漏掉 —— 這是「越權」的另一面（漏行），故過濾條件必須與 `teacher_name` 一起進子查詢。
    flag off 時**仍走原兩個分支**（`(teacher_name,)` / 無參），SQL 逐字節不變。
    """
    filter_on, lineage_id = lineage_read_scope(teacher_name, lineage_id)
    conn = get_connection()
    if filter_on:
        rows = conn.execute("""
            SELECT d.* FROM drafts d
            INNER JOIN (
                SELECT patient_name, MAX(id) as max_id
                FROM drafts WHERE signed = 0 AND lineage_id = ? AND teacher_name = ?
                GROUP BY patient_name
            ) latest ON d.id = latest.max_id
        """, (lineage_id, teacher_name)).fetchall()
    elif teacher_name:
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
    """【Epic 3 §4.2 改 4 · 施工步骤 3.3-c】老师修改草案正文 → best-effort 追加 `draft_modified` 学习事件。

    既有语义**零变化**（Epic 2 §5.1 红线③）：`UPDATE` 语句文本、`commit`、`close`、返回 `None`
    一概一字不改。本步只加两件事，位置固定：

      · **UPDATE 之前**：一条**只读** `SELECT * FROM drafts WHERE id = ?`（`draft_modified` 是四环节里
        唯一零既有落点的环节，`before` 只能在这里现读）→ 取老师改之前的正文与事件定位键
        （`teacher_name` / `patient_name`）。读失败 / 草案不存在（今天那次 UPDATE 也只是静默 0 行）
        → `before = None`：UPDATE 照发，事件**不发**；
      · **commit/close 之后**：经唯一转发点 `_call_agent_stage_hook()`（钩子名 = `on_draft_modified`）
        追加事件：两侧正文各跑一次 `_normalize_metric_text(text, 2000)`（归一化在调用方做 ——
        CTO 3.3-a 追加 1 方案 c；适配器**不**代劳，传原文会造成假阳性）。逐字相同的编辑由适配器
        自己的幂等分支跳过，库层不替它判（同一判断只许有一份实现）。参数按位置传（转发器是
        `(hook_name, *args)`）。

    best-effort：整段 try/except 静默兜底（含服务层不可用）—— 老师的修改结果与返回值不受影响。
    """
    conn = get_connection()
    before = None
    try:
        before = conn.execute("SELECT * FROM drafts WHERE id = ?", (draft_id,)).fetchone()
    except Exception:
        before = None
    conn.execute("UPDATE drafts SET content = ? WHERE id = ?", (content, draft_id))
    conn.commit()
    conn.close()

    # 【施工步骤 3.3-c】改了才说得上「有变化」：没有 before 就没有可比的基准 → 不发事件。
    if before is not None:
        try:
            import agent_stage_service                       # 仅归一化用（函数内局部 import）
            template_id = before["template_id"] if "template_id" in before.keys() else 0
            normalized_before = agent_stage_service._normalize_metric_text(before["content"], 2000)
            normalized_after = agent_stage_service._normalize_metric_text(content, 2000)
            _call_agent_stage_hook("on_draft_modified", before["teacher_name"], draft_id,
                                   before["patient_name"], normalized_before, normalized_after,
                                   template_id)
        except Exception:
            pass

def sign_draft(draft_id, final_plan, final_content=None):
    """【第45天修改】签字时同时保存 AI 原草案与老师最终版（学习轨迹）

    【第77天新增】落库时一并写入 visit_at = 当前时间（ISO 时间戳）—— 这是「复诊提醒」唯一可靠的
    就诊时间基准（以前只能从病历文本的签字行「李老师 · 2026年9月23日」里猜，漏签字行就失效）。

    【Epic 2 §4.2 改 2】**只追加两件事，既有语义零变化**（§5.1 红线③）：
      · 改动 a：`patient_records.ai_original_text` 落「草案的 AI 原始快照」（空则回落 `content`）——
        **双闸门**（CTO 裁决①：flag on 且该列就位）任一为假 → 走**改动前逐字节一致**的原 6 列 SQL；
        原因：草案行签字后会被 `DELETE`，快照不落历史表就永久丢失（§1.4 / §4.2-2a）。
      · 改动 b：函数末尾 best-effort 调服务层 `on_draft_signed(teacher_name)`（延迟 import + 两态，
        见 `_call_agent_stage_hook`）—— **在 commit 之后**调用，评估失败绝不回滚签字。
    返回值（`draft["patient_name"]`）、删除草案、`signed` 语义、`patient_records` 既有字段全部不变。
    """
    conn = get_connection()
    draft = conn.execute("SELECT * FROM drafts WHERE id = ?", (draft_id,)).fetchone()
    if not draft:
        conn.close()
        return None

    # 完整病历（如果传了）或退回到最终方案
    patient_record_content = final_content if final_content else final_plan

    # 【Epic 2 §4.2 改 2a · 双闸门，CTO 裁决①】flag 先判（廉价、零 SQL），再探列：
    # 任一为假 → 下面走**改动前逐字节一致**的原 6 列 INSERT（§5.1 红线① / §5.5-① 硬门槛，有专项用例）。
    ai_snapshot_enabled = _agent_stage_snapshot_enabled() and _patient_records_supports_ai_original(conn)

    # 【第77天新增】visit_at = 签字时刻（本机时间，ISO 格式）：agent.check_recall_alerts 按它判断该生多久没复诊
    if ai_snapshot_enabled:                                     # 7 列：+ AI 原始快照（改 2a）
        conn.execute(
            "INSERT INTO patient_records (patient_name, teacher_name, ai_draft, final_plan, doctor, visit_at, ai_original_text) VALUES (?, ?, ?, ?, ?, ?, ?)",
            (draft["patient_name"], draft["teacher_name"], draft["content"], patient_record_content, draft["teacher_name"], datetime.now().isoformat(), _draft_ai_snapshot(draft))
        )
    else:                                                       # 原 6 列：SQL 与参数逐字不变（仅缩进 +4 空格）
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

    # 【Epic 2 §4.2 改 2b】签字已落库 → best-effort 通知服务层（延迟 import + 两态见 `_call_agent_stage_hook`）。
    # 放在 commit/close 之后：评估失败绝不回滚签字；返回值一字不改（§5.1 红线③）。
    _call_agent_stage_hook("on_draft_signed", draft["teacher_name"])

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
def get_patient_records(patient_name=None, teacher_name=None, lineage_id=None):
    """【Epic 4 §3.2 P0-③】病歷歷史：flag on 時 `lineage_id = ?` **前置**於其它條件。

    学生端（`/api/patient-records?patient_name=...`，不帶 teacher_name）flag on 時直接 400，
    不退化為全庫查詢；flag off 時 `conditions` / `where` / `query` 組合結果逐字節不變。
    """
    filter_on, lineage_id = lineage_read_scope(teacher_name, lineage_id)
    conn = get_connection()
    conditions = []
    params = []
    if filter_on:
        conditions.append("lineage_id = ?")
        params.append(lineage_id)
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
def get_appointments(patient_name=None, teacher_name=None, start_date=None, end_date=None, lineage_id=None):
    """【Epic 4 §3.2 P2】預約列表：flag on 且帶 teacher_name 時**前置** `lineage_id = ?`。

    學生端（只給 `patient_name`）flag on 時 400（§3.2「teacher_name 可空 = 高危」）；
    flag off 時 `conditions` 內容與順序不變 → SQL 字面量逐字節不變。
    """
    filter_on, lineage_id = lineage_read_scope(teacher_name, lineage_id)
    conn = get_connection()
    conditions = []
    params = []
    if filter_on:
        conditions.append("lineage_id = ?")
        params.append(lineage_id)
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

def get_teacher_tags_summary(teacher_name, lineage_id=None):
    """返回该老师所有标签的汇总（用于知识库视图）

    【Epic 4 §3.2 P1】flag on 时须 `lineage_id = ? AND teacher_name = ?`（标签也是师门数据）；
    flag off 时 `owner_where` 拼出的字面量与改动前逐字节相同。
    """
    filter_on, lineage_id = lineage_read_scope(teacher_name, lineage_id)
    owner_where = "lineage_id = ? AND teacher_name = ?" if filter_on else "teacher_name = ?"
    owner_params = (lineage_id, teacher_name) if filter_on else (teacher_name,)
    conn = get_connection()
    rows = conn.execute("""
        SELECT tag_type, tag_value, COUNT(*) as count
        FROM record_tags
        WHERE """ + owner_where + """
        GROUP BY tag_type, tag_value
        ORDER BY count DESC
    """, owner_params).fetchall()
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


def get_prescriptions(teacher_name, patient_name=None, lineage_id=None):
    """返回该老师的药方；给了 patient_name 就再按患者过滤。最新在前。

    【Epic 4 §3.2 P1】flag on 时条件列表前两项固定为 `lineage_id = ? AND teacher_name = ?`；
    flag off 时仍是原来的 `["teacher_name = ?"]` + 可选 patient_name，SQL 逐字节不变。
    """
    filter_on, lineage_id = lineage_read_scope(teacher_name, lineage_id)
    conn = get_connection()
    if filter_on:
        conditions = ["lineage_id = ?", "teacher_name = ?"]
        params = [lineage_id, teacher_name]
    else:
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


def scan_silent_students(teacher_name, silent_days=30, lineage_id=None):
    """扫描该老师名下的「沉默学生」（last_active_at 为空，或距今 >= silent_days 天），
    给还没有 pending 同类请示的学生各建一条 agent_tasks 请示，返回新建任务数。

    【Epic 4 §3.2 P1】flag on 时**两条读语句**都要加 `lineage_id = ?`：
      ① 学生列表（`patient_teachers`）；
      ② pending 去重集合（`agent_tasks`）—— 漏改 ② 会让别师门的「已建单」把本师门学生误判为
         「已有 pending」从而**不再建单**（漏建，越权的镜像面）。
    注意：本函数**只**改这两条读语句；下面建单的 INSERT 与 `insert_agent_action_log` 一字不动。
    """
    filter_on, lineage_id = lineage_read_scope(teacher_name, lineage_id)
    owner_where = "pt.lineage_id = ? AND pt.teacher_name = ?" if filter_on else "pt.teacher_name = ?"
    owner_params = (lineage_id, teacher_name) if filter_on else (teacher_name,)
    task_where = "lineage_id = ? AND teacher_name = ?" if filter_on else "teacher_name = ?"
    task_params = (lineage_id, teacher_name) if filter_on else (teacher_name,)
    conn = get_connection()
    cur = conn.cursor()
    students = cur.execute("""
        SELECT p.name AS name, p.last_active_at AS last_active_at
        FROM patients p
        INNER JOIN patient_teachers pt ON p.name = pt.patient_name
        WHERE """ + owner_where + """ AND pt.status = 'active'
        ORDER BY p.name
    """, owner_params).fetchall()

    # 【行政化改造】先把该老师所有 pending 的「学生」类请示里的 patient_name 收集起来做去重集合。
    # 不用以前那种 action_data 字符串全等匹配 —— 这样历史旧格式
    # （{"action": "send_care_notice", ...}）也能命中，action_data 格式升级不会给同一学生重复建单。
    pending_patient_names = set()
    for pending in cur.execute(
        "SELECT action_data FROM agent_tasks WHERE " + task_where +
        " AND category = 'student' AND status = 'pending'",
        task_params
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


def get_agent_tasks(teacher_name, status='pending', lineage_id=None):
    """按 created_at DESC 返回该老师的智能体任务；status 传空则不过滤状态。

    【Epic 4 §3.2 P1】flag on 时 `lineage_id = ?` 与 `teacher_name = ?` 一起进 WHERE
    （两个分支都要改，漏掉任一分支 = 漏改即越权）；flag off 时两条 SQL 逐字节不变。
    """
    filter_on, lineage_id = lineage_read_scope(teacher_name, lineage_id)
    owner_where = "lineage_id = ? AND teacher_name = ?" if filter_on else "teacher_name = ?"
    owner_params = (lineage_id, teacher_name) if filter_on else (teacher_name,)
    conn = get_connection()
    if status:
        rows = conn.execute(
            "SELECT * FROM agent_tasks WHERE " + owner_where + " AND status = ? ORDER BY created_at DESC, id DESC",
            owner_params + (status,)
        ).fetchall()
    else:
        rows = conn.execute(
            "SELECT * FROM agent_tasks WHERE " + owner_where + " ORDER BY created_at DESC, id DESC",
            owner_params
        ).fetchall()
    conn.close()
    return [_agent_task_row_to_dict(r) for r in rows]


def resolve_agent_task(task_id, decision):
    """老师决策：decision='approved' / 'rejected'。
    更新任务状态 + 记一条 agent_action_log；approved 且 action 为 send_care_notice 时再记一条发送日志（暂不真实推送）。

    【Epic 2 §4.2 改 3】（施工步骤 2.4）任务落定后**追加** best-effort 通知服务层：
    `action_data.action == 'upgrade_agent_stage'` 时，approved → `apply_upgrade_confirmation(
    teacher_name, to, task_id)`；rejected → `decline_upgrade(teacher_name, task_id)`。
    纪律：**返回值 / SQL / 既有分支语义一字不改**（逐条见函数末尾那段注释）；两态实现只有
    `_call_agent_stage_hook()` 一份，本函数不重复判断。"""
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

    # ---------- 【Epic 2 §4.2 改 3】升级请示落定 → best-effort 通知服务层（施工步骤 2.4）----------
    # 位置：状态 UPDATE + 行动日志 INSERT + `commit` + `close` **之后**（与改 2b 同款时序）
    #       → 钩子即便炸了，也不可能污染已落定的任务状态与审计日志。
    # 纪律（对应 CTO step 2.4 四条追加要求）：
    #   · 要求 1 / 4：两态判断**复用**改 2b 的同一个调用器 `_call_agent_stage_hook()`
    #     （函数内延迟 import → `getattr` + `callable` 缺失即静默 → 异常只 print warn）。
    #     本段**不写第二份**两态判断，也不自己 import 服务层。
    #   · 要求 2：本段**不参与**任何返回值构造 —— 下面那一行 `return` 与改动前一字不差；
    #     上面学生类请示的 `send_care_notice` 分支同样一字未动。
    #   · 要求 3：本段在 flag **on / off 下都发零条 SQL**（钩子缺失时 `_call_agent_stage_hook`
    #     在 import 之前就返回 False）→ 语句序列与参数逐字节不变；⑫ 组有专门用例守，
    #     且改动前后各有一次实测捕获留档（%TEMP%\epic2_resolve_baseline_*.txt）。
    #   · **本段不判 flag**（CTO 2026-09-28 批复①，与改 2b 同口径）：flag off 时算不算指标 /
    #     写不写新表，由服务层 `apply_upgrade_confirmation` / `decline_upgrade` 的**首行自闸门**
    #     负责；库层只转发 —— 否则这里就会出现第二个 flag 判断。
    #   · 既有 approved 分支里的局部 `action` 只活在那个分支作用域内（那几行一字不动），故此处
    #     另做一次**防御式解析**（与上面那段同款写法；纯读、零副作用、零 SQL）：rejected 路径
    #     也能拿到 action_data，且 `action_data` 坏掉时绝不冒泡（§4.2 改 3「整段包 try/except」）。
    #   · 多一层 `isinstance` 兜底的必要性：rejected 路径在改动前**根本不解析** action_data，
    #     若这里是 JSON 数组 / 字符串 / 数字，`.get` 会 AttributeError —— 那就成了本步引入的回归。
    #     （approved 路径上的同类脏数据在改动前就会在这条语句**之前**炸，本步不改变那个既有行为。）
    try:
        resolved_action = json.loads(task["action_data"]) if task["action_data"] else {}
        if not isinstance(resolved_action, dict):
            resolved_action = {}
    except Exception:
        resolved_action = {}
    if resolved_action.get("action") == "upgrade_agent_stage":
        if new_status == "approved":
            _call_agent_stage_hook("apply_upgrade_confirmation", task["teacher_name"],
                                   resolved_action.get("to"), task_id)
        else:
            _call_agent_stage_hook("decline_upgrade", task["teacher_name"], task_id)

    return {"message": "已处理", "status": new_status}


def get_agent_action_log(teacher_name, limit=20, lineage_id=None):
    """【行政化改造】返回该老师的智能体行动日志，按 created_at 倒序（同一时间按 id 倒序）。

    limit：最多返回多少条（设计文档接口默认 20）：非正数按默认 20 处理，上限 200，防止一把拉爆。

    【Epic 4 §3.2 P1】flag on 时 `lineage_id = ? AND teacher_name = ?`（老师在旗标 on 时
    必须带师门上下文；空 teacher_name 依然按原样「早返回空列表」——那是**已存在的 fail-closed**
    行为，不是越权面，故 `teacher_name` 判空**先于**作用域校驗，保持与改动前同序）。
    """
    if not teacher_name:
        return []
    filter_on, lineage_id = lineage_read_scope(teacher_name, lineage_id)
    owner_where = "lineage_id = ? AND teacher_name = ?" if filter_on else "teacher_name = ?"
    owner_params = (lineage_id, teacher_name) if filter_on else (teacher_name,)
    if limit is None or limit <= 0:
        limit = 20
    limit = min(limit, 200)

    conn = get_connection()
    rows = conn.execute(
        "SELECT * FROM agent_action_log WHERE " + owner_where + " ORDER BY created_at DESC, id DESC LIMIT ?",
        owner_params + (limit,)
    ).fetchall()
    conn.close()
    return [dict(r) for r in rows]


# ============ 【Epic 2 §4.2】智能体五阶段：状态 / 审计 / 配置 的库访问函数 ============
# 说明（设计 §1.2 / §1.3 / §4.2 / §7.1-⑥，CTO 五项裁决 2026-09-28）：
#   · 本区段**只做库的「门」**：裸 SQL + TEXT 时间 + json.dumps(..., ensure_ascii=False)，
#     与既有 24+ 张表的函数同款；**不吞 sqlite3.Error**，读 / 写异常一律冒泡给
#     agent_stage_service 与接口层（表未就绪 → 503 agent_stage_store_unavailable，裁决⑤）；
#     `None` 只表示「查询成功但没有行」。
#   · **flag 闸门（AGENT_STAGE_ENABLED）不在本区段**：阶段门控属服务层
#     （agent_stage_service.agent_stage_enabled），调用方过了闸门才进这里（裁决②）。
#     库层唯一与总闸打交道的地方是**快照列双闸门** `_agent_stage_snapshot_enabled()`
#     （定义在 `insert_draft` 上方；改 1 / 改 2a 共用；**函数内延迟 import** 服务层，断开循环依赖）。
#   · 审计表 agent_stage_log 只提供 insert + get，**永不提供 update / delete**
#     → 「只增」由代码层强制，不靠约定（§1.3）。
#   · 共 8 + 1 个函数：+1 是 insert_agent_action_log —— §4.5-① 已把该函数列为服务层可调用的
#     既有函数，但全库原本不存在；工作台「行动日志」区块要靠它写入，故在此一并补齐（§7.1-⑥）。
#   · 列名全部来自下列白名单 → 无 SQL 注入面。

# ---------- 白名单常量（与 0003_add_agent_stage.py 的建表列一一对应，测试有逐列一致性守护）----------

# agent_stage_state 可写列（不含主键 teacher_name）
AGENT_STAGE_STATE_UPSERT_FIELDS = (
    "lineage_id", "stage", "stage_since", "stage_source", "pending_stage",
    "pending_task_id", "last_evaluated_at", "last_metrics_json", "updated_at",
)
# agent_stage_log 可写列（不含主键 id 与 event_type）
AGENT_STAGE_LOG_INSERT_FIELDS = (
    "from_stage", "to_stage", "capability", "task_id", "metrics_json", "detail", "created_at",
)
# `*_json` 列允许直接传 dict / list（自动序列化）
_AGENT_STAGE_JSON_COLUMNS = ("last_metrics_json", "metrics_json")


def _agent_stage_column_value(column, value):
    """`*_json` 列：非字符串入参自动 json.dumps(..., ensure_ascii=False)；其余列原样透传。

    故意**不做 None 兜底**：NOT NULL 列传 None 时由 SQLite 抛 IntegrityError（属 sqlite3.Error，
    按裁决⑤冒泡），比静默替换成 '' 更容易定位调用方 bug。
    """
    if column in _AGENT_STAGE_JSON_COLUMNS and not isinstance(value, str):
        return json.dumps(value if value is not None else {}, ensure_ascii=False)
    return value


def get_agent_stage_state(teacher_name):
    """读该老师的状态行：无行 → None（不塞默认行，兜底由服务层按 default_stage 完成，§1.2 / §1.5）。"""
    conn = get_connection()
    row = conn.execute(
        "SELECT * FROM agent_stage_state WHERE teacher_name = ?", (teacher_name or "",)
    ).fetchone()
    conn.close()
    if row is None:
        return None
    return dict(row)


def upsert_agent_stage_state(teacher_name, **fields):
    """单事务 upsert 状态行（INSERT ... ON CONFLICT(teacher_name) DO UPDATE），只接受白名单字段。

    · 白名单外的键 → `ValueError`（调用方只有服务层，属编程错误，立刻炸出来比静默丢字段好）；
    · **只写本次传入的列**：没传的列在 INSERT 时走建表默认值、在 UPDATE 时保持原值（不做隐式清零）；
    · `updated_at` 未传时自动补当前时间（全库 TEXT 时间惯例）；
    · 列名全部来自白名单 → 无 SQL 注入面。
    """
    unknown = [k for k in fields if k not in AGENT_STAGE_STATE_UPSERT_FIELDS]
    if unknown:
        raise ValueError("upsert_agent_stage_state 不支持这些字段：%s" % ", ".join(sorted(unknown)))

    payload = [(name, _agent_stage_column_value(name, fields[name]))
               for name in AGENT_STAGE_STATE_UPSERT_FIELDS if name in fields]
    if "updated_at" not in fields:
        payload.append(("updated_at", datetime.now().isoformat()))

    columns = ", ".join(["teacher_name"] + [name for name, _ in payload])
    placeholders = ", ".join("?" for _ in range(len(payload) + 1))
    assignments = ", ".join("%s = excluded.%s" % (name, name) for name, _ in payload)

    conn = get_connection()
    conn.execute(
        "INSERT INTO agent_stage_state (%s) VALUES (%s) ON CONFLICT(teacher_name) DO UPDATE SET %s"
        % (columns, placeholders, assignments),
        tuple([teacher_name or ""] + [value for _, value in payload]),
    )
    conn.commit()
    conn.close()


def insert_agent_stage_log(teacher_name, event_type, **fields):
    """【只增审计】往 agent_stage_log 追加一条事件，返回新 log_id（§1.3）。

    · `event_type` 的取值白名单属服务层（§1.3 共 **10 类**：补 `permission_relaxed` 后），本函数只校验非空；
    · 白名单外字段 → `ValueError`；`created_at` 未传时自动补当前时间；
    · 本区段永不提供 update / delete —— 「只增」由代码层强制。
    """
    if not event_type:
        raise ValueError("insert_agent_stage_log 必须给 event_type")
    unknown = [k for k in fields if k not in AGENT_STAGE_LOG_INSERT_FIELDS]
    if unknown:
        raise ValueError("insert_agent_stage_log 不支持这些字段：%s" % ", ".join(sorted(unknown)))

    payload = [(name, _agent_stage_column_value(name, fields[name]))
               for name in AGENT_STAGE_LOG_INSERT_FIELDS if name in fields]
    if "created_at" not in fields:
        payload.append(("created_at", datetime.now().isoformat()))

    columns = ", ".join(["teacher_name", "event_type"] + [name for name, _ in payload])
    placeholders = ", ".join("?" for _ in range(len(payload) + 2))

    conn = get_connection()
    cursor = conn.execute(
        "INSERT INTO agent_stage_log (%s) VALUES (%s)" % (columns, placeholders),
        tuple([teacher_name or "", str(event_type)] + [value for _, value in payload]),
    )
    conn.commit()
    log_id = cursor.lastrowid
    conn.close()
    return log_id


def get_agent_stage_logs(teacher_name, limit=20):
    """倒序读该老师的阶段审计（created_at DESC，同秒按 id DESC）；limit 口径与 get_agent_action_log 一致。"""
    if not teacher_name:
        return []
    if limit is None or limit <= 0:
        limit = 20
    limit = min(limit, 200)

    conn = get_connection()
    rows = conn.execute(
        "SELECT * FROM agent_stage_log WHERE teacher_name = ? ORDER BY created_at DESC, id DESC LIMIT ?",
        (teacher_name, limit)
    ).fetchall()
    conn.close()
    return [dict(r) for r in rows]


# ---------- 配置表 agent_stage_config（teacher_name='' 为全局默认行，§3.4 / §3.5）----------

def get_agent_stage_config_row(teacher_name):
    """读单行配置：无行 → None（读取链由服务层继续往「全局行 → env → 内置默认」，§3.4 / §3.5）。"""
    conn = get_connection()
    row = conn.execute(
        "SELECT * FROM agent_stage_config WHERE teacher_name = ?", (teacher_name or "",)
    ).fetchone()
    conn.close()
    if row is None:
        return None
    return dict(row)


def upsert_agent_stage_config(teacher_name, config_json):
    """写单行配置（`teacher_name=''` 即全局行）：内容合法性由服务层校验（§3.4），本函数只落库。

    `config_json` 传 dict 时自动 json.dumps(..., ensure_ascii=False)（库列是 TEXT，与全库惯例一致）。
    """
    if not isinstance(config_json, str):
        config_json = json.dumps(config_json if config_json is not None else {}, ensure_ascii=False)
    conn = get_connection()
    conn.execute(
        "INSERT INTO agent_stage_config (teacher_name, config_json, updated_at) VALUES (?, ?, ?) "
        "ON CONFLICT(teacher_name) DO UPDATE SET "
        "config_json = excluded.config_json, updated_at = excluded.updated_at",
        (teacher_name or "", config_json, datetime.now().isoformat()),
    )
    conn.commit()
    conn.close()


# ---------- 升级推荐请示（复用既有 agent_tasks 通道，§3.6 / §4.2）----------

def find_pending_upgrade_task(teacher_name):
    """该老师是否已有 pending 的升级请示：有 → dict（复用 _agent_task_row_to_dict），无 → None。

    去重判据（§3.6 第 3 步）：`status='pending'` 且 action_data 含 upgrade_agent_stage。
    不复用 agent.py 的 _pending_task_exists（模块私有函数，跨模块调用会造隐式耦合）。
    """
    conn = get_connection()
    row = conn.execute(
        "SELECT * FROM agent_tasks WHERE teacher_name = ? AND status = 'pending' "
        "AND action_data LIKE '%upgrade_agent_stage%' ORDER BY created_at DESC, id DESC LIMIT 1",
        (teacher_name or "",)
    ).fetchone()
    conn.close()
    if row is None:
        return None
    return _agent_task_row_to_dict(row)


def insert_agent_stage_upgrade_task(teacher_name, title, content, action_data):
    """写一条升级推荐请示，返回新 task_id。

    字段集与既有两处裸 INSERT 完全同构（agent.py 的 _insert_student_request、本文件 scan_silent_students）：
    task_type='request' / category='agent' / status='pending' → 既有前端渲染、GET /api/agent/tasks、
    resolve_agent_task 与 approve / reject 两个接口**零改动**即可适配（§4.2 / §7.1-⑤）。
    """
    if not isinstance(action_data, str):
        action_data = json.dumps(action_data if action_data is not None else {}, ensure_ascii=False)
    conn = get_connection()
    cursor = conn.execute(
        "INSERT INTO agent_tasks (teacher_name, task_type, category, title, content, action_data, status, created_at) "
        "VALUES (?, 'request', 'agent', ?, ?, ?, 'pending', ?)",
        (teacher_name or "", title or "", content or "", action_data, datetime.now().isoformat()),
    )
    conn.commit()
    task_id = cursor.lastrowid
    conn.close()
    return task_id


def insert_agent_action_log(teacher_name, action, detail, task_id=0, created_at=None):
    """往既有 agent_action_log（工作台「行动日志」区块）追加一行，返回新 id。

    §7.1-⑥：阶段升级 / 降级 / 推荐升级等关键节点要写一行人话，让工作台该区块**零改动**就能显示；
    §4.5-① 把它列为服务层可调用的既有函数，但它此前并不存在 —— 本区段补齐「写入」这一个动作。
    """
    conn = get_connection()
    cursor = conn.execute(
        "INSERT INTO agent_action_log (teacher_name, task_id, action, detail, created_at) VALUES (?, ?, ?, ?, ?)",
        (teacher_name or "", task_id or 0, action or "", detail or "",
         created_at or datetime.now().isoformat()),
    )
    conn.commit()
    log_id = cursor.lastrowid
    conn.close()
    return log_id


# ---------- 【施工步骤 3.4-a】指标样本的只读读取原语（§3.2 / §3.3；CTO 2026-09-29 批复 C-1）----------
# 背景：①② 两个指标需要的样本散布在**两张表**（未签字 `drafts` + 已签字 `patient_records`），
# 服务层不拼 SQL（§4.5-① 只允许它调库层函数）→ 库层给**唯一**的只读入口。
# 批复 C 的四条约束逐条落地：只读 / 不改现有签名 / 不动表结构 / 必带 LIMIT。
# 同批批复的 `get_agent_stage_log_stats()`（越权计数 + 推荐冷却）属 3.4-b，与 `evaluate` 一起落地
# —— 此处不预先占名（服务层 3.4-a 段头已记「假实现比缺席更坏」这条纪律）。

# `patient_records.template_id / template_version`（迁移 0004 添加）—— 探测口径与
# `_DRAFT_TEMPLATE_REF_COLUMNS` 同款：迁移未跑 → 该列读作 0，服务层按 §3.2 把这些样本
# 计入 `skipped_no_template`（「指标可降级，存储没坏」，§4.5-①）。
_PATIENT_RECORD_TEMPLATE_REF_COLUMNS = ("template_id", "template_version")

# 样本读取的 LIMIT 兜底与上限（与 `get_agent_action_log` / `get_agent_stage_logs` 的 20 / 200 同款风格；
# 上限 500 = §3.4 第 5 条给 `max_samples` 定的上界，两者不许分叉）
_STAGE_SAMPLE_LIMIT_DEFAULT = 50
_STAGE_SAMPLE_LIMIT_MAX = 500


def _agent_stage_sample_int(value):
    """样本行的整型列读数兜底（库列无 CHECK，人手 SQL 可能写坏）：非整数 → `0` + 一行 warn。

    与 `agent_stage_service._coerce_pending_task_id()` 同向：**不抛**，只留痕
    （指标不因脏行炸掉整条评估链路）。
    """
    try:
        return int(value)
    except (TypeError, ValueError):
        print("[warn] 階段指標樣本的整型列無法解析：%r，已按 0 處理（庫列無 CHECK）" % (value,))
        return 0


def get_draft_samples(teacher_name, window_days, limit):
    """【Epic 2 §3.2 / §3.3】指标样本的**统一只读入口**（3.4-a 新增，CTO 批复 C-1）。

    返回该老师的可用样本行（未签字草案 + 已签字病历**两类**，「类型」由每行的 `source` 键标出），
    每行固定 9 键（形状即契约，服务层两个指标函数直接消费）：

      `source`           `'record'`（已签字病历）/ `'draft'`（未签字草案）
      `id`               该表主键
      `patient_name`     患者名
      `ai_text`          AI 侧文本：草案 = `ai_original_content` 为空则回落 `content`；
                         病历 = `ai_original_text` 为空则回落 `ai_draft`（§3.2 / §3.3 的基准列）
      `final_text`       老师侧文本：草案 = `content`；病历 = `final_plan`
      `template_id`      生成时的生效模板 id（列未就位 → `0` = 未记录）
      `template_version` 同上（版本号）
      `has_snapshot`     AI 侧文本是否来自**不可变快照**（② 据此分 strict / approx）
      `at`               时间锚：病历 = `visit_at`；草案 = `''`（`drafts` **无时间列**）

    五条口径（写死在这里，服务层不得再补一套）：
      1. **只读 + 必带 LIMIT**（批复 C 约束）：两条 SELECT 各带 `LIMIT ?`；本函数不写任何表
         （不发 INSERT / UPDATE / DELETE，不建索引、不改表结构）；
      2. **窗口只对有时间的来源生效**：病历按 `visit_at >= date('now','localtime','-N days')`
         过滤（`N = window_days`，非正整数 → 不过滤）；`drafts` 无时间列 → **不受窗口约束**，
         按 `id DESC` 取最近 `limit` 条（`id` 单调递增 = 插入序，是这张表唯一的「新近」信号；
         设计 §3.2 假设 `drafts` 有时间列，实测没有 → 服务层把草案当「无时间锚样本」处理）；
      3. **`visit_at` 为空的老行照收**：`''` = 迁移前的历史签字，§3.3 明确把这类行算作
         `approx` 样本 ——「没有时间基准」不等于「不是样本」（不降级、不惩罚）；
      4. **缺列降级**（§4.5-①「指标可降级，存储没坏」）：`drafts` 模板引用列（迁移 0002）、
         `patient_records` 模板引用列（迁移 0004）、两个快照列（迁移 0003）任一未跑 →
         该列读作 `0` / `''`，**不抛异常**；
      5. **每个来源各取 `limit` 行**（最多返回 `2 * limit` 行）：`max_samples` 的「取前 N 条」
         由两个指标各自再截断（① 只看命中当前模板的样本、② 只看已签字病历）→ 两个指标
         **互不挤占**同一份额度。返回顺序 = 已签字病历（`visit_at` 倒序）→ 未签字草案（`id` 倒序）。

    调用方（3.4-a 起）：`agent_stage_service.compute_template_match()` /
    `compute_modification_consistency()`；`sqlite3.Error` **不吞**（裁决⑤：表未就绪冒泡给服务层，
    由服务层降级成「无样本」+ 一行告警）。
    """
    if not teacher_name:
        return []

    limit = _agent_stage_sample_int(limit)
    if limit <= 0:
        limit = _STAGE_SAMPLE_LIMIT_DEFAULT
    limit = min(limit, _STAGE_SAMPLE_LIMIT_MAX)
    days = _agent_stage_sample_int(window_days)

    conn = get_connection()
    try:
        drafts_have_refs = _table_has_columns(conn, "drafts", _DRAFT_TEMPLATE_REF_COLUMNS)
        drafts_have_snapshot = _drafts_supports_ai_original(conn)
        records_have_refs = _table_has_columns(conn, "patient_records",
                                               _PATIENT_RECORD_TEMPLATE_REF_COLUMNS)
        records_have_snapshot = _patient_records_supports_ai_original(conn)

        draft_rows = conn.execute(
            "SELECT id, patient_name, content, %s AS ai_original_content, "
            "%s AS template_id, %s AS template_version FROM drafts "
            "WHERE teacher_name = ? AND signed = 0 ORDER BY id DESC LIMIT ?"
            % ("ai_original_content" if drafts_have_snapshot else "''",
               "template_id" if drafts_have_refs else "0",
               "template_version" if drafts_have_refs else "0"),
            (teacher_name, limit),
        ).fetchall()

        record_filter = ""
        if days > 0:
            record_filter = (" AND (visit_at IS NULL OR visit_at = '' OR "
                             "date(visit_at) >= date('now', 'localtime', '-%d days'))" % days)
        record_rows = conn.execute(
            "SELECT id, patient_name, final_plan, ai_draft, %s AS ai_original_text, "
            "%s AS template_id, %s AS template_version, visit_at FROM patient_records "
            "WHERE teacher_name = ?%s ORDER BY visit_at DESC, id DESC LIMIT ?"
            % ("ai_original_text" if records_have_snapshot else "''",
               "template_id" if records_have_refs else "0",
               "template_version" if records_have_refs else "0",
               record_filter),
            (teacher_name, limit),
        ).fetchall()
    finally:
        conn.close()

    samples = []
    for row in record_rows:         # 已签字病历优先：完成的学习轨迹（② 只吃这一类）
        snapshot = row["ai_original_text"] or ""
        samples.append({
            "source": "record",
            "id": row["id"],
            "patient_name": row["patient_name"] or "",
            "ai_text": snapshot or (row["ai_draft"] or ""),
            "final_text": row["final_plan"] or "",
            "template_id": _agent_stage_sample_int(row["template_id"]),
            "template_version": _agent_stage_sample_int(row["template_version"]),
            "has_snapshot": bool(snapshot),
            "at": row["visit_at"] or "",
        })
    for row in draft_rows:          # 未签字草案（① 用得到；② 忽略）
        snapshot = row["ai_original_content"] or ""
        samples.append({
            "source": "draft",
            "id": row["id"],
            "patient_name": row["patient_name"] or "",
            "ai_text": snapshot or (row["content"] or ""),
            "final_text": row["content"] or "",
            "template_id": _agent_stage_sample_int(row["template_id"]),
            "template_version": _agent_stage_sample_int(row["template_version"]),
            "has_snapshot": bool(snapshot),
            "at": "",
        })
    return samples


# ---------- 【施工步骤 3.4-b】阶段审计的**只读统计**（§2.4 越权计数 + §3.6 冷却判定；批复 C-2）----------
# 评估判定链需要两样「按事件类型的统计」，两者都只读 `agent_stage_log`（只增审计）：
#   · §2.4 / §3.6 can_recommend 第 10 条：窗口内 `permission_denied` 次数 > max_permission_denials → 阻断；
#   · §3.6 can_recommend 第 5 条：距上次「推荐 / 被拒」不足 recommend_cooldown_hours → 阻断。
# 批复 C 的四条约束逐条落地：**只读** / **不改现有签名** / **不动表结构** / **必带 LIMIT**。
# 行上限沿用 `get_agent_stage_logs()` 的 200（同为「倒序取最近 N 条」口径），落成**内部常量**：
# 批复 C-2 已把签名钉死为 `(teacher_name, event_types, since)` 三个参数 → 不新增公开入参。

_STAGE_LOG_STATS_LIMIT = 200


def get_agent_stage_log_stats(teacher_name, event_types, since):
    """【§2.4 / §3.6】按事件类型统计窗口内的阶段审计条数 —— 只读、必带 LIMIT（批复 C-2）。

    入参（签名与批复逐字一致）：
      · `teacher_name` 空 → 直接返回空统计（**连 SQL 都不发**，与 `get_draft_samples` 同款）；
      · `event_types` = 要统计的事件名序列（单个 `str` 按「一个事件名」处理；`None` / 空 → 空统计）；
      · `since` = 时间下界（ISO 串，**含边界**）；空 / 非字符串 → 不过滤（全历史，仍受 LIMIT 约束）。

    返回固定 6 键（形状即契约）：
      `since`     归一化后的时间下界（`''` = 未过滤）
      `counts`    {事件名: 条数}；**请求了但一条都没有的事件名也在，值为 0** → 调用方不必兜 KeyError，
                  也看得见「名字拼错」（值恒为 0）而不是静默通过
      `total`     命中条数（`sum(counts.values())`）
      `last_at`   命中行里最新的 `created_at`（无命中 → `''`）—— §3.6 冷却判定用
      `truncated` 是否撞上行上限（`True` = 更早的行没扫到 → 计数是「最近 N 条内」的下界）
      `limit`     本次生效的行上限（`_STAGE_LOG_STATS_LIMIT`）

    三条口径：
      1. **只读 + 必带 LIMIT**：只发**一条** `SELECT ... LIMIT ?`；不写任何表（不发 INSERT / UPDATE /
         DELETE，不建索引、不改表结构）；
      2. **倒序扫描**：`ORDER BY created_at DESC, id DESC`（与 `get_agent_stage_logs` 同款；`created_at`
         是 TEXT、同秒靠 `id` 兜底）→ `last_at` 恒为真正的「最近一次」，与是否被截断无关；
      3. **不做时间算术**：`since` 由调用方（服务层按 `window_days`）算好传入 —— 本函数不认识
         「窗口」语义，只做字符串下界比较（全库 TEXT 时间惯例）。

    `sqlite3.Error` **不吞**（裁决⑤：表未就绪 → 503 / 由服务层降级成「按 0 次处理」）。
    """
    types = []
    source = event_types if isinstance(event_types, (list, tuple, set, frozenset)) else \
        ([event_types] if event_types else [])
    for item in source:
        if isinstance(item, str) and item and item not in types:
            types.append(item)
    since_text = since if isinstance(since, str) else ""

    stats = {
        "since": since_text,
        "counts": {name: 0 for name in types},
        "total": 0,
        "last_at": "",
        "truncated": False,
        "limit": _STAGE_LOG_STATS_LIMIT,
    }
    if not teacher_name or not types:
        return stats

    placeholders = ", ".join("?" for _ in types)
    sql = ("SELECT event_type, created_at FROM agent_stage_log "
           "WHERE teacher_name = ? AND event_type IN (%s)" % placeholders)
    params = [teacher_name] + types
    if since_text:
        sql += " AND created_at >= ?"
        params.append(since_text)
    sql += " ORDER BY created_at DESC, id DESC LIMIT ?"
    params.append(_STAGE_LOG_STATS_LIMIT)

    conn = get_connection()
    rows = conn.execute(sql, tuple(params)).fetchall()
    conn.close()

    stats["truncated"] = len(rows) >= _STAGE_LOG_STATS_LIMIT
    if rows:
        stats["last_at"] = rows[0]["created_at"] or ""
    for row in rows:
        name = row["event_type"]
        if name in stats["counts"]:
            stats["counts"][name] += 1
    stats["total"] = sum(stats["counts"].values())
    return stats


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
    """保存 / 覆盖该老师的“施治方案”模板（teacher_name 唯一：有则 UPDATE，无则 INSERT）。

    【Epic 1 §5.2 第 4 条 / §12.4】本通道自此是「遗留写入通道」，采用 best-effort 两段式：
    ① 先写 `plan_templates` 并 COMMIT —— 旧接口的成功 100% 不依赖模板表，行为与今天一字不差；
    ② 再调 `template_service.sync_legacy_plan_template()` 单向双写 `templates`
       （同 scope 无 draft → 派生 v2 草稿，不原地改 active；永不反向回写 `plan_templates`）；
    ③ 双写失败（例如 `templates` 表缺失 / 库被锁）**只打日志**，绝不改变本函数的返回值。
    """
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

    # 第二段：best-effort 双写（flag off 时 sync 内部直接返回 None，不做任何读写）
    try:
        import template_service  # 函数内延迟导入：与文件顶部的 re-export 同源，不新增 import 期依赖

        template_service.sync_legacy_plan_template(teacher_name, content)
    except Exception as exc:  # noqa: BLE001 —— legacy 通道必须容忍模板侧任何异常（§12.4）
        print(
            "[warn] 施治模板双写 templates 失败（不影响旧接口返回）：%s: %s"
            % (type(exc).__name__, exc)
        )
    return True


# ============ 【第82天新增】学生陈述（complaints）：老师端「📝 待处理陈述」 ============
# 数据链路：学生「十问歌」面诊前准备 → agent.save_intake() 落 complaints（status='pending'）
#           → 老师端 GET /api/complaints?teacher_name=…&status=pending 看到列表
#           → 点「已处理」POST /api/complaints/{id}/process → status='processed' + resolved_at。

def get_complaints(teacher_name, status="pending", lineage_id=None):
    """查该老师名下的学生陈述：按 status 过滤，created_at 倒序（同一时间按 id 倒序）。

    status 传空串 / None = 不过滤状态（返回该老师全部陈述）。
    返回字段：id / patient_name / teacher_name / content / status / created_at。

    【Epic 4 §3.2 P1】flag on 时两个分支都要 `lineage_id = ? AND teacher_name = ?`
    （学生陈述里可能有身份信息）；flag off 时两条 SQL 逐字节不变。
    """
    filter_on, lineage_id = lineage_read_scope(teacher_name, lineage_id)
    owner_where = "lineage_id = ? AND teacher_name = ?" if filter_on else "teacher_name = ?"
    owner_params = (lineage_id, teacher_name) if filter_on else (teacher_name,)
    conn = get_connection()
    if status:
        rows = conn.execute(
            "SELECT id, patient_name, teacher_name, content, status, created_at FROM complaints "
            "WHERE " + owner_where + " AND status = ? ORDER BY created_at DESC, id DESC",
            owner_params + (status,)
        ).fetchall()
    else:
        rows = conn.execute(
            "SELECT id, patient_name, teacher_name, content, status, created_at FROM complaints "
            "WHERE " + owner_where + " ORDER BY created_at DESC, id DESC",
            owner_params
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
# 【Epic 3 step 3.2】学习事件（agent_learning_events）库层原语
# ----------------------------------------------------------------------------
# CTO 2026-09-30 裁决（step 3.2 补充 2）：Epic 3 全程走「SQL 全在 database.py、服务层
# `learning_service.py` 零 SQL 字面量 + 零直接 sqlite3 调用」的分层（Epic 1 / Epic 2 模式）。
# Epic 4 `lineage_service` 自己写 SQL 属偏离，已由 CTO 登记 TD-018；本 Epic 不跟随，也不动它。
#
# 本段四个函数 = `learning_service.py` 四个薄封装的**唯一下游**（设计 §2.5 / §2.6）：
#   next_seq / get_last_learning_event / get_learning_events / insert_learning_event
#
# 三条纪律：
#   · **零 DDL**：表 + 2 个索引的唯一真相源 = 迁移 `0006_add_agent_learning_events`；
#     `init_db()` 不建本表（与 0003 / 0005 同款）。
#   · **只增 + 只读**：本段零 UPDATE / 零 DELETE —— 链的「不可改」是它唯一的价值
#     （设计 §4-② 口径冻结声明：改 / 删只能走 CTO 单独裁决 + 数据迁移方案）。
#   · **本段不做哈希、不分配 seq、不校准 prev_hash**：链的口径唯一真相源是 `learning_service`
#     （纯函数）+ 迁移 0006（冻结常量）；库层多算一次就是长出第二个真相。
# ============================================================================

# 表名（唯一真相源 = 迁移 0006 的 `EVENTS_TABLE`；本常量只供本段 SQL 复用）
LEARNING_EVENTS_TABLE = "agent_learning_events"

# INSERT 白名单：与迁移 0006 的 `ALL_COLUMNS` 去掉 `id` / `teacher_name` / `event_type` 后**逐列一一对应**
# （`test_learning.py` 有逐列一致性守护）。`id` 由 AUTOINCREMENT 分配；`teacher_name` / `event_type`
# 走位置参数；`created_at` 未传则自动补当前时间（与 templates / lineage 同款）。
LEARNING_EVENT_INSERT_FIELDS = (
    "seq",
    "lineage_id",
    "patient_name_hash",
    "draft_id",
    "template_id",
    "payload_json",
    "payload_hash",
    "prev_hash",
    "created_at",
)

# 必填四列（其余列都有 DDL DEFAULT：`''` / `0`）
LEARNING_EVENT_REQUIRED_FIELDS = ("seq", "payload_json", "payload_hash", "prev_hash")


def next_seq(teacher_name):
    """【A2 / 设计 §2.5-2】分配该老师链上的下一个 `seq`：`SELECT COALESCE(MAX(seq), 0) + 1 ...`。

    三条口径（写死在这里，后续子步不得改）：
      · **按老师各自一条链**：`teacher_name = ''` 也算一位「老师」（空名由服务层拒绝），
        返回 1 表示「空链的下一个号」；
      · **只读、单语句**：不写任何行、不开显式事务、不预留号 —— 「分配 + INSERT 的原子性」
        由调用方（`learning_service.insert_learning_event`）负责；真并发下的兜底是**索引级**的
        （迁移 0006 的 `uq_agent_learning_events_teacher_seq`）：抢到同一个号时后到者 `IntegrityError`，
        **绝不静默丢事件**（§2.5-3）；
      · 跳号 / 复用的唯一可能来源是「人手 SQL 改库」，链校验（`verify_learning_chain`）会报 `seq_gap`。
    """
    conn = get_connection()
    try:
        row = conn.execute(
            "SELECT COALESCE(MAX(seq), 0) + 1 FROM " + LEARNING_EVENTS_TABLE
            + " WHERE teacher_name = ?",
            (teacher_name or "",),
        ).fetchone()
    finally:
        conn.close()
    return int(row[0])


def get_last_learning_event(teacher_name):
    """该老师链上 **`seq` 最大**的一行 → dict；一次都没有 → None（= 空链，调用方以 `GENESIS_HASH` 起链）。

    为什么不是「按 `created_at` 取最近」：链的先后由 `seq` 定义（§2.5-4），`created_at` 只是审计时间；
    同一微秒内两次写入用时间排序会得到不确定的行。
    """
    conn = get_connection()
    try:
        row = conn.execute(
            "SELECT * FROM " + LEARNING_EVENTS_TABLE
            + " WHERE teacher_name = ? ORDER BY seq DESC LIMIT 1",
            (teacher_name or "",),
        ).fetchone()
    finally:
        conn.close()
    return dict(row) if row is not None else None


def get_learning_events(teacher_name, limit=20):
    """按 **`seq` 升序**（= 链序）读该老师的事件 → `[dict]`；`limit` 为 `None` / `<= 0` → **全量**。

    为什么要留全量口子：链校验必须看到**整条链**（`LIMIT` 会静默截断 → 缺行被误判成 ok，§2.4）。
    因此「必带 LIMIT」的纪律落成：默认 20，**只有显式传 None** 才全量 —— 调用点必须把这个意图写出来
    （`learning_service.verify_learning_chain` 是当前唯一的全量调用点）。
    倒序 / 时间窗（`created_at DESC` 索引）展示由调用方自行排序，本原语只承诺链序。
    """
    if not teacher_name:
        return []
    conn = get_connection()
    try:
        if limit is None or limit <= 0:
            rows = conn.execute(
                "SELECT * FROM " + LEARNING_EVENTS_TABLE
                + " WHERE teacher_name = ? ORDER BY seq ASC",
                (teacher_name,),
            ).fetchall()
        else:
            rows = conn.execute(
                "SELECT * FROM " + LEARNING_EVENTS_TABLE
                + " WHERE teacher_name = ? ORDER BY seq ASC LIMIT ?",
                (teacher_name, int(limit)),
            ).fetchall()
    finally:
        conn.close()
    return [dict(r) for r in rows]


def insert_learning_event(teacher_name, event_type, **fields):
    """【只增】往 `agent_learning_events` 追加一条事件，返回新行 `id`（`lastrowid`）。

    形制照 `insert_agent_stage_log`：白名单外的键 → `ValueError`；必填四列缺一 → `ValueError`；
    `created_at` 未传 → 自动补 `datetime.now().isoformat()`。

    【两条不得放宽的硬口径】
      1. `seq` / `payload_json` / `payload_hash` / `prev_hash` **必须由调用方算好传进来** ——
         本函数不做哈希、不分配 `seq`、不校准 `prev_hash`（见段头第三条纪律）。
      2. `payload_json` **必须是非空 `str`**（= `learning_service.canonical_json()` 的产物），
         **不接受 dict**：`json.dumps(dict)` 会按插入序输出，与 canonical 字节不同 →
         `payload_hash` 与 `payload_json` **当场对不上**（链第 1 层校验必红）。
         宁可在这里报错，也不写进一条自相矛盾的行（§2.3 的 canonical 字节是链的基石）。
    """
    if not teacher_name:
        raise ValueError("insert_learning_event 必须给 teacher_name（按老师单链，§2.5）")
    if not event_type:
        raise ValueError("insert_learning_event 必须给 event_type")
    unknown = [key for key in fields if key not in LEARNING_EVENT_INSERT_FIELDS]
    if unknown:
        raise ValueError("insert_learning_event 不支持这些字段：%s" % ", ".join(sorted(unknown)))

    missing = [name for name in LEARNING_EVENT_REQUIRED_FIELDS
               if fields.get(name) is None or fields.get(name) == ""]
    if missing:
        raise ValueError("insert_learning_event 缺少必填字段：%s" % ", ".join(missing))

    payload_json = fields["payload_json"]
    if not isinstance(payload_json, str):
        raise ValueError(
            "insert_learning_event 的 payload_json 必须是字符串（canonical_json() 的产物），"
            "不接受 %s：否则 payload_hash 与 payload_json 对不上" % type(payload_json).__name__
        )
    for name in ("payload_hash", "prev_hash"):
        if not isinstance(fields[name], str):
            raise ValueError("insert_learning_event 的 %s 必须是字符串" % name)
    if not isinstance(fields["seq"], int) or isinstance(fields["seq"], bool) or fields["seq"] < 1:
        raise ValueError("insert_learning_event 的 seq 必须是 >= 1 的 int（§2.5）")

    values = [(name, fields[name]) for name in LEARNING_EVENT_INSERT_FIELDS if name in fields]
    if "created_at" not in fields:
        values.append(("created_at", datetime.now().isoformat()))

    columns = ", ".join(["teacher_name", "event_type"] + [name for name, _ in values])
    placeholders = ", ".join("?" for _ in range(len(values) + 2))

    conn = get_connection()
    try:
        cursor = conn.execute(
            "INSERT INTO " + LEARNING_EVENTS_TABLE + " (%s) VALUES (%s)" % (columns, placeholders),
            tuple([teacher_name, str(event_type)] + [value for _, value in values]),
        )
        conn.commit()
        row_id = cursor.lastrowid
    finally:
        conn.close()
    return row_id


# ============================================================================
# 【B 板塊 B5-1】學生數據導出：唯讀查詢原語（純新增，不動上方任何函數）
# ----------------------------------------------------------------------------
# 本段只服務 `export_api.py`（`GET /api/export/patient` 的「一次性打包」）：
#   · 全部 `SELECT`：零寫入 / 零 DDL / 零事務；
#   · 命名一律 `<資源>_by_patient(patient_name)`，與上方既有的窄口徑讀函數
#     （帶 `teacher_name` / `lineage_id` 過濾，服務端入口用）並存、互不影響；
#   · 既有同名函數（`get_patient_profile` / `get_patient_teachers` / `get_patients`）
#     直接復用，不在此重複定義。
# ============================================================================

def get_patient_by_name(patient_name):
    """按主鍵 `patients.name` 取一行 → dict；不存在 → None（導出端據此回 404）。"""
    conn = get_connection()
    row = conn.execute("SELECT * FROM patients WHERE name = ?", (patient_name,)).fetchone()
    conn.close()
    return dict(row) if row else None


def get_transcriptions_by_patient(patient_name):
    """該患者的全部轉述（**含已處理 / 未處理**，導出要全量而非「待處理」）。"""
    conn = get_connection()
    rows = conn.execute(
        "SELECT * FROM transcriptions WHERE patient_name = ? ORDER BY id DESC",
        (patient_name,)
    ).fetchall()
    conn.close()
    return [dict(r) for r in rows]


def get_drafts_by_patient(patient_name):
    """該患者的全部病歷草案（含已簽 / 未簽）。"""
    conn = get_connection()
    rows = conn.execute(
        "SELECT * FROM drafts WHERE patient_name = ? ORDER BY id DESC",
        (patient_name,)
    ).fetchall()
    conn.close()
    return [dict(r) for r in rows]


def get_patient_records_by_patient(patient_name):
    """該患者的全部健康檔案（已簽病歷）。"""
    conn = get_connection()
    rows = conn.execute(
        "SELECT * FROM patient_records WHERE patient_name = ? ORDER BY id DESC",
        (patient_name,)
    ).fetchall()
    conn.close()
    return [dict(r) for r in rows]


def get_prescriptions_by_patient(patient_name):
    """該患者的全部藥方（不分老師）。"""
    conn = get_connection()
    rows = conn.execute(
        "SELECT * FROM prescriptions WHERE patient_name = ? ORDER BY id DESC",
        (patient_name,)
    ).fetchall()
    conn.close()
    return [dict(r) for r in rows]


def get_homework_by_patient(patient_name):
    """該患者的全部作業（不分老師 / 不分狀態）。"""
    conn = get_connection()
    rows = conn.execute(
        "SELECT * FROM homework WHERE patient_name = ? ORDER BY id DESC",
        (patient_name,)
    ).fetchall()
    conn.close()
    return [dict(r) for r in rows]


def get_appointments_by_patient(patient_name):
    """該患者的全部預約（不分老師 / 不分狀態）。"""
    conn = get_connection()
    rows = conn.execute(
        "SELECT * FROM appointments WHERE patient_name = ? "
        "ORDER BY scheduled_date, scheduled_time",
        (patient_name,)
    ).fetchall()
    conn.close()
    return [dict(r) for r in rows]


def get_record_tags_by_patient(patient_name):
    """該患者病歷上的全部標籤。

    注意：`record_tags` 表**沒有** `patient_name` 列（見 `init_db()` 的 record_tags：
    只有 `record_id` / `teacher_name` / `tag_type` / `tag_value` / `created_at`，
    遷移 0005 另補 `lineage_id`），故不能照其他 `_by_patient` 那樣直接
    `WHERE patient_name = ?`（會 `no such column`）。這裡經
    `record_tags.record_id = patient_records.id` 關聯到患者，語義等價於
    「先在 `patient_records` 取本患者的 id、再查其標籤」。
    """
    conn = get_connection()
    rows = conn.execute(
        "SELECT rt.* FROM record_tags rt "
        "INNER JOIN patient_records pr ON rt.record_id = pr.id "
        "WHERE pr.patient_name = ? ORDER BY rt.id DESC",
        (patient_name,)
    ).fetchall()
    conn.close()
    return [dict(r) for r in rows]


def get_complaints_by_patient(patient_name):
    """該患者的全部學生陳述（不分老師 / 不分狀態）。"""
    conn = get_connection()
    rows = conn.execute(
        "SELECT * FROM complaints WHERE patient_name = ? ORDER BY created_at DESC, id DESC",
        (patient_name,)
    ).fetchall()
    conn.close()
    return [dict(r) for r in rows]


# ============================================================================
# 【B 板塊 B4-b】數據封存事件：寫入 + 讀取原語（純新增，不動上方任何函數）
# ----------------------------------------------------------------------------
# 對齊 docs/phase2-data-sovereignty-design.md §3.5（數據封存）：
#   · 表結構唯一真相源 = 遷移 0007（`seal_events`）；本段只做增 / 讀，**零 DDL**；
#   · §3.5.5：`action` 取值只含 `seal` / `readmit`（**不含** `remove` —— B 板塊不定義除名事件）；
#   · 「只增」由代碼層強制：本段**永不**提供 update / delete；
#   · 階段二不判定、不攔截、不實際上鏈：`chain_ready` / `chain_hash` 本步**不填**
#     （走建表默認 FALSE / NULL），填充歸階段四（§3.5.7 / IR-4）。
# ============================================================================

# 表名（唯一真相源 = 遷移 0007 的 `SEAL_EVENTS_TABLE`；本常量只供本段 SQL 復用）
SEAL_EVENTS_TABLE = "seal_events"

# 主體類型白名單（§3.5.4：只允許「患者」與「老師」兩類主體）
SEAL_SUBJECT_TYPES = ("patient", "teacher")

# 動作白名單（§3.5.5：**不含** `remove`）
SEAL_ACTIONS = ("seal", "readmit")


def insert_seal_event(subject_type, subject_name, action, reason=None, operator=None):
    """【只增】往 `seal_events` 追加一條事件，返回新行 `id`（`lastrowid`）。

    形制照 `insert_agent_stage_log`：入參先過白名單 / 非空校驗（不合法 → `ValueError`），
    再 `try/finally` 關連接；`created_at` 自動補 `datetime.now().isoformat()`（全庫 TEXT 時間慣例）。

    【階段二硬口徑】（§3.5.1 / §3.5.5 / §3.5.7）
      · `subject_type` ∈ {'patient', 'teacher'}，`action` ∈ {'seal', 'readmit'}（**不含** remove）；
      · `subject_name` 非空（空主體名無法回溯「封存了誰」）；
      · `reason` / `operator` 可省（None → 落 NULL）；
      · `chain_ready` / `chain_hash` 本步**不寫**（建表默認 FALSE / NULL），填充歸階段四；
      · 本區段永不提供 update / delete —— 「只增」由代碼層強制。
    """
    if subject_type not in SEAL_SUBJECT_TYPES:
        raise ValueError(
            "insert_seal_event 的 subject_type 必須是 patient 或 teacher，實得：%r" % (subject_type,)
        )
    if not subject_name:
        raise ValueError("insert_seal_event 必須給 subject_name")
    if action not in SEAL_ACTIONS:
        raise ValueError(
            "insert_seal_event 的 action 必須是 seal 或 readmit，實得：%r" % (action,)
        )

    conn = get_connection()
    try:
        cursor = conn.execute(
            "INSERT INTO " + SEAL_EVENTS_TABLE
            + " (subject_type, subject_name, action, reason, operator, created_at) "
            "VALUES (?, ?, ?, ?, ?, ?)",
            (subject_type, subject_name, action, reason, operator, datetime.now().isoformat()),
        )
        conn.commit()
        event_id = cursor.lastrowid
    finally:
        conn.close()
    return event_id


def get_seal_events(subject_type, subject_name, limit=None):
    """按 `subject_type` + `subject_name` 查封存事件 → `[dict]`，**`id` 倒序**（最近事件在前）。

    形制照 `get_learning_events`：空參數（缺類型或名字）**短路**返回 `[]`（不發 SQL）；
    `limit` 預設 `None`（**全量**），`None` / `<= 0` 亦視為全量 —— 封存歷史是數據主權的
    見證記錄（何時 / 由誰 / 為何），讀取口徑默認不截斷（與 `idx_seal_events_subject` 的
    `(subject_type, subject_name, id DESC)` 讀路徑同口徑）。
    """
    if not subject_type or not subject_name:
        return []
    conn = get_connection()
    try:
        if limit is None or limit <= 0:
            rows = conn.execute(
                "SELECT * FROM " + SEAL_EVENTS_TABLE
                + " WHERE subject_type = ? AND subject_name = ? ORDER BY id DESC",
                (subject_type, subject_name),
            ).fetchall()
        else:
            rows = conn.execute(
                "SELECT * FROM " + SEAL_EVENTS_TABLE
                + " WHERE subject_type = ? AND subject_name = ? ORDER BY id DESC LIMIT ?",
                (subject_type, subject_name, int(limit)),
            ).fetchall()
    finally:
        conn.close()
    return [dict(r) for r in rows]

