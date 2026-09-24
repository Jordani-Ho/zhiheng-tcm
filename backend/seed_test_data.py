"""
【第44天】测试数据合成脚本
用法：cd /workspaces/zhiheng-tcm/backend && python seed_test_data.py
作用：为李老师生成 8 个虚拟学生，各自有不同的活跃度和积分，用于测试状态标签
注意：这是测试脚本，正式上线前可以删除
【第65天】顺带补齐财务账户种子数据：张三 100、李老师 500（账户不存在才创建）
【第73天】① 补 3 条远程问诊预约（appointments.is_remote=1：今天 1 条 + 明天 2 条，状态已确认）；
         ② 药材库存从 5 味扩到 37 味常用中药（库存 200~2000 随机，预警阈值 100，保留 3 味低于阈值）。
"""
import sqlite3
import os
import random
import sys
from datetime import datetime, timedelta

# 【第65天新增】复用后端的建表 / 迁移逻辑，保证财务表定义只有一处
import database

# 【第59天修复】Windows 控制台默认 GBK，直接 print 带 emoji 的提示会 UnicodeEncodeError，
# 这里把标准输出统一切成 UTF-8（不支持时静默跳过，不影响逻辑）。
try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass

# 【第65天修改】直接复用 database 模块解析出的库路径，保证脚本和 uvicorn 读写同一个库
DB_PATH = database.DB_PATH

# 8 个虚拟学生，每个学生用不同的活跃时间和积分
TEST_STUDENTS = [
    # (姓名, 关系, 性别, 出生日期, 出生时辰, 出生地, 居住地, 几天前活跃, 积分)
    ("王五", "学生", "男", "1985-03-12", "07:00", "北京市朝阳区", "北京市朝阳区", 0, 150),    # 今天活跃，正常
    ("赵六", "学生", "女", "1992-08-20", "13:00", "上海市浦东新区", "上海市浦东新区", 3, 80),   # 3天前活跃
    ("钱七", "学生", "男", "1978-11-05", "17:00", "广东省广州市", "广东省广州市", 12, 45),    # 12天前活跃
    ("孙八", "学生", "女", "2000-02-14", "09:00", "四川省成都市", "四川省成都市", 18, 20),    # 18天前活跃，余额低
    ("周九", "学生", "男", "1965-06-30", "11:00", "江苏省南京市", "江苏省南京市", 35, 100),   # 35天未活跃，沉默
    ("吴十", "学生", "女", "1995-09-08", "15:00", "浙江省杭州市", "浙江省杭州市", 60, 80),    # 60天未活跃，沉默
    ("郑一", "学生", "男", "1988-04-25", "23:00", "湖北省武汉市", "湖北省武汉市", 5, 0),      # 欠费预警
    ("冯二", "学生", "女", "1970-12-01", "01:00", "陕西省西安市", "陕西省西安市", None, 100), # 从未活跃
]

# 【第73天扩充】常用中药材名单（37 味，≥30 味，九宫格开方时够用）
COMMON_HERB_NAMES = [
    "黄芪", "当归", "党参", "白术", "茯苓", "甘草", "陈皮", "半夏", "柴胡", "白芍",
    "川芎", "熟地", "桂枝", "生姜", "大枣", "枸杞", "菊花", "金银花", "连翘", "桔梗",
    "杏仁", "麻黄", "石膏", "知母", "黄连", "黄芩", "黄柏", "栀子", "丹参", "红花",
    "桃仁", "牛膝", "杜仲", "山药", "山茱萸", "泽泻", "丹皮",
]

# 【第73天新增】库存克数随机区间 + 默认预警阈值
HERB_STOCK_MIN = 200
HERB_STOCK_MAX = 2000
HERB_WARN_THRESHOLD = 100

# 【第73天新增】故意保留 3 味低于预警阈值（库存 ≤ 预警阈值）的药材，方便测试“库存预警”
LOW_STOCK_HERBS = {
    "陈皮": 40,
    "当归": 60,
    "黄连": 80,
}


def build_test_herbs():
    """【第73天扩充】把药材名单展开成 (药材名, 库存量, 单位, 预警阈值) 种子数据。

    库存量在 200~2000 之间随机；随机种子写死 → 每次跑出来的库存量一致，方便复现问题。
    """
    rng = random.Random(20260923)
    herbs = []
    for herb_name in COMMON_HERB_NAMES:
        if herb_name in LOW_STOCK_HERBS:
            stock_amount = LOW_STOCK_HERBS[herb_name]
        else:
            stock_amount = rng.randint(HERB_STOCK_MIN, HERB_STOCK_MAX)
        herbs.append((herb_name, stock_amount, "克", HERB_WARN_THRESHOLD))
    return herbs


# 【第59天新增】中药材库存：(药材名, 库存量, 单位, 预警阈值)
TEST_HERBS = build_test_herbs()

# 【第59天新增】余额 / 充值消耗流水：(学生, 类型, 积分变动, 备注, 几天前)，按顺序累加得到余额
TEST_POINT_FLOWS = [
    ("张三", "recharge", 200, "9月微信充值 200 积分", 25),
    ("张三", "consume", -100, "9月面诊扣费 100 积分", 10),
    ("李四", "recharge", 150, "9月支付宝充值 150 积分", 20),
    ("李四", "consume", -50, "9月面诊扣费 50 积分", 6),
    ("孙八", "recharge", 50, "9月微信充值 50 积分", 15),
    ("孙八", "consume", -30, "9月面诊扣费 30 积分", 4),
]

# 【第59天新增】预约：(学生, 日期偏移天数, 时间, 事由, 状态)
TEST_APPOINTMENTS = [
    ("李四", 0, "10:00", "复诊：脾胃调理", "confirmed"),
    ("张三", 0, "15:00", "复诊：睡眠调理", "confirmed"),
    ("王五", 1, "09:00", "初诊：颈椎不适", "confirmed"),
]

# 【第73天新增】远程问诊预约：(学生, 日期偏移天数, 时间, 事由)→ 落库时 is_remote=1、状态固定 confirmed
# 事由里带“远程 / 视频”关键词：前端「诊室队列 → 💻 远程问诊」列本来就按 reason 关键词分列（REMOTE_APPT_KEYWORDS），
# 所以带关键词后前端零改动即可正确归到远程列；数据库这边再用 is_remote=1 做结构化标记（供查询 / 统计用）。
TEST_REMOTE_APPOINTMENTS = [
    ("王五", 0, "14:00", "远程问诊：颈椎不适复诊（视频问诊）"),   # 今天
    ("周九", 1, "10:00", "远程问诊：失眠多梦初诊（视频问诊）"),   # 明天
    ("吴十", 1, "15:00", "远程问诊：脾胃调理随访（视频问诊）"),   # 明天
]

# 【第59天新增】学生陈述（转述，未处理）：让老师补充完病历草案后点“保存病历修改”可以落库
TEST_TRANSCRIPTIONS = [
    ("张三", "主诉：近一周入睡困难、多梦易醒。\n现病史：白天精神差，饭后腹胀。\n舌象：舌淡红、苔薄白。\n脉象：脉弦细。"),
]

# 【第65天新增】财务账户种子数据：(用户名, 角色, 初始余额)——只在账户不存在时创建
TEST_FINANCE_ACCOUNTS = [
    ("张三", "student", 100),
    ("李老师", "teacher", 500),
]

# 老师名字统一常量（后面新增的种子数据都挂在李老师名下）
TEACHER_NAME = "李老师"


def ensure_extra_tables(cursor):
    """【第59天新增】中药材库存表（与 database.init_herb_table 定义保持一致）+ 余额流水表。
    【第73天新增】顺便把 appointments.is_remote 字段补上（与 database.init_db 的迁移逻辑一致），
    这样单独跑 seed（不重启 uvicorn）也能写入远程预约标记。
    """
    cursor.execute("CREATE TABLE IF NOT EXISTS herb_inventory (id INTEGER PRIMARY KEY AUTOINCREMENT, teacher_name TEXT, herb_name TEXT, stock_amount REAL DEFAULT 0, unit TEXT DEFAULT '克', warn_threshold REAL DEFAULT 50, updated_at TEXT, UNIQUE(teacher_name, herb_name))")
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS points_ledger (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        patient_name TEXT,
        teacher_name TEXT,
        change_type TEXT,        -- recharge=充值 / consume=消耗
        points INTEGER,          -- 正数=充值，负数=消耗
        balance_after INTEGER,   -- 这条流水之后的余额
        note TEXT,
        created_at TEXT
    )
    """)
    try:
        cursor.execute("ALTER TABLE appointments ADD COLUMN is_remote INTEGER DEFAULT 0")
    except sqlite3.OperationalError:
        pass  # 字段已存在（或表还不存在），重复执行不报错


def seed_herbs(cursor):
    """【第59天新增】中药材库存：先删同名药材再插入，可重复运行。"""
    for herb_name, stock_amount, unit, warn_threshold in TEST_HERBS:
        cursor.execute("DELETE FROM herb_inventory WHERE teacher_name = ? AND herb_name = ?", (TEACHER_NAME, herb_name))
        cursor.execute(
            "INSERT INTO herb_inventory (teacher_name, herb_name, stock_amount, unit, warn_threshold, updated_at) VALUES (?, ?, ?, ?, ?, ?)",
            (TEACHER_NAME, herb_name, stock_amount, unit, warn_threshold, datetime.now().isoformat())
        )
    low_count = len([h for h in TEST_HERBS if h[1] <= h[3]])
    print("✅ 已生成 %d 味中药材库存（其中 %d 味低于预警阈值，可在库存页看到预警）" % (len(TEST_HERBS), low_count))


def seed_points(cursor):
    """【第59天新增】充值 / 消耗流水，并按流水累加出最终余额写回 points_accounts（保证余额与流水一致）。"""
    balance = {}
    for patient_name, change_type, points, note, days_ago in TEST_POINT_FLOWS:
        balance[patient_name] = balance.get(patient_name, 0) + points
        created_at = (datetime.now() - timedelta(days=days_ago)).strftime("%Y-%m-%d")
        cursor.execute("DELETE FROM points_ledger WHERE patient_name = ? AND teacher_name = ? AND note = ?", (patient_name, TEACHER_NAME, note))
        cursor.execute(
            "INSERT INTO points_ledger (patient_name, teacher_name, change_type, points, balance_after, note, created_at) VALUES (?, ?, ?, ?, ?, ?, ?)",
            (patient_name, TEACHER_NAME, change_type, points, balance[patient_name], note, created_at)
        )
    for patient_name, final_balance in balance.items():
        cursor.execute("UPDATE points_accounts SET points = ? WHERE role_name = ?", (final_balance, patient_name))
    detail = "、".join(["%s(%d积分)" % (k, v) for k, v in balance.items()])
    print("✅ 已生成 %d 条余额流水，覆盖 %d 名学生：%s" % (len(TEST_POINT_FLOWS), len(balance), detail))


def seed_finance_accounts(cursor):
    """【第65天新增】财务账户：张三 100、李老师 500；账户已存在则保持原样不动。"""
    created = []
    for username, role, balance in TEST_FINANCE_ACCOUNTS:
        cursor.execute("SELECT balance FROM accounts WHERE username = ?", (username,))
        if cursor.fetchone() is None:
            cursor.execute(
                "INSERT INTO accounts (username, role, balance, updated_at) VALUES (?, ?, ?, ?)",
                (username, role, balance, datetime.now().isoformat())
            )
            created.append("%s(%d)" % (username, balance))
    if created:
        print("✅ 已创建 %d 个财务账户：%s" % (len(created), "、".join(created)))
    else:
        print("✅ 财务账户已存在（张三 / 李老师），余额未改动")


def _upsert_appointment(cursor, patient_name, day_offset, time_str, reason, status, is_remote, now):
    """【第73天新增】写一条测试预约（幂等，可重复跑）。

    幂等做法：先按「学生 + 老师 + 事由」删掉旧行——跨天重跑时 scheduled_date 会变，
    只按日期删会越积越多；再用 INSERT OR IGNORE 兜底（appointments 目前没有唯一约束，
    双保险防止重复行）。
    """
    date_str = (now + timedelta(days=day_offset)).strftime("%Y-%m-%d")
    cursor.execute(
        "DELETE FROM appointments WHERE patient_name = ? AND teacher_name = ? AND reason = ?",
        (patient_name, TEACHER_NAME, reason)
    )
    cursor.execute(
        "INSERT OR IGNORE INTO appointments (patient_name, teacher_name, initiator, scheduled_date, scheduled_time, reason, status, created_at, confirmed_at, is_remote) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
        (patient_name, TEACHER_NAME, "student", date_str, time_str, reason, status,
         now.strftime("%Y-%m-%d"), now.strftime("%Y-%m-%d") if status == "confirmed" else None,
         1 if is_remote else 0)
    )


def seed_appointments(cursor):
    """【第59天新增】今天 / 明天的已确认预约，让老师“诊室 → 面诊队列”有数据。
    【第73天新增】再补 3 条远程问诊预约（is_remote=1：今天 1 条 + 明天 2 条）。
    """
    now = datetime.now()
    for patient_name, day_offset, time_str, reason, status in TEST_APPOINTMENTS:
        _upsert_appointment(cursor, patient_name, day_offset, time_str, reason, status, 0, now)
    for patient_name, day_offset, time_str, reason in TEST_REMOTE_APPOINTMENTS:
        _upsert_appointment(cursor, patient_name, day_offset, time_str, reason, "confirmed", 1, now)

    today_count = len([a for a in TEST_APPOINTMENTS if a[1] == 0])
    remote_today = len([a for a in TEST_REMOTE_APPOINTMENTS if a[1] == 0])
    remote_tomorrow = len([a for a in TEST_REMOTE_APPOINTMENTS if a[1] == 1])
    print("✅ 已生成 %d 条预约（今天 %d 条已确认，老师“诊室 → 面诊队列”可见）" % (len(TEST_APPOINTMENTS), today_count))
    print("✅ 已生成 %d 条远程问诊预约（is_remote=1：今天 %d 条、明天 %d 条；“💻 远程问诊”列按 reason 关键词自动归列）" % (
        len(TEST_REMOTE_APPOINTMENTS), remote_today, remote_tomorrow))


def seed_transcriptions(cursor):
    """【第59天新增】学生陈述（未处理）：老师补充完病历草案后点“保存病历修改”即可落库。"""
    for patient_name, content in TEST_TRANSCRIPTIONS:
        cursor.execute("DELETE FROM transcriptions WHERE patient_name = ? AND teacher_name = ? AND content = ?", (patient_name, TEACHER_NAME, content))
        cursor.execute(
            "INSERT INTO transcriptions (patient_name, teacher_name, content, data_type, processed) VALUES (?, ?, ?, 'text', 0)",
            (patient_name, TEACHER_NAME, content)
        )
    print("✅ 已生成 %d 条学生陈述（未处理），可测试“保存病历修改”落库" % len(TEST_TRANSCRIPTIONS))


def seed():
    # 【第65天新增】先把财务两张表建好（内含老积分表 accounts → points_accounts 的自动迁移）。
    # 必须在写库之前调用：它用自己的连接做 DDL，避免和本脚本的事务抢锁。
    database.init_finance_tables()

    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()

    today = datetime.now().strftime("%Y-%m-%d")

    # 先删除同名的旧测试数据（防止重复运行）
    for name, *_ in TEST_STUDENTS:
        cursor.execute("DELETE FROM patients WHERE name = ?", (name,))
        cursor.execute("DELETE FROM patient_profiles WHERE patient_name = ?", (name,))
        cursor.execute("DELETE FROM patient_teachers WHERE patient_name = ?", (name,))
        cursor.execute("DELETE FROM points_accounts WHERE role_name = ?", (name,))

    for name, relation, gender, birth_date, birth_time, birth_place, location, days_ago, points in TEST_STUDENTS:
        # 1. 患者表
        if days_ago is None:
            last_active = None
        else:
            last_active = (datetime.now() - timedelta(days=days_ago)).strftime("%Y-%m-%d")

        cursor.execute(
            "INSERT INTO patients (name, guardian_name, relation, created_at, last_active_at) VALUES (?, 'self', ?, ?, ?)",
            (name, relation, today, last_active)
        )

        # 2. 患者档案表
        cursor.execute(
            "INSERT INTO patient_profiles (patient_name, gender, birth_date, birth_time, birth_place, location) VALUES (?, ?, ?, ?, ?, ?)",
            (name, gender, birth_date, birth_time, birth_place, location)
        )

        # 3. 师生关系表
        cursor.execute(
            "INSERT INTO patient_teachers (patient_name, teacher_name, status, created_at) VALUES (?, '李老师', 'active', ?)",
            (name, today)
        )

        # 4. 积分账户
        cursor.execute(
            "INSERT INTO points_accounts (role_name, points) VALUES (?, ?)",
            (name, points)
        )

    # ============ 【第59天新增】诊室二期测试数据 ============
    ensure_extra_tables(cursor)   # 中药材库存表 + 余额流水表（含 appointments.is_remote 补字段）
    seed_herbs(cursor)            # 中药材库存（37 味常用药，其中 3 味低于预警阈值）
    seed_points(cursor)           # 余额 + 充值/消耗流水
    seed_finance_accounts(cursor) # 【第65天新增】财务账户：张三 100、李老师 500
    seed_appointments(cursor)     # 今天/明天的已确认预约（含 3 条远程问诊）
    seed_transcriptions(cursor)   # 学生陈述（未处理）

    conn.commit()

    # 【第73天新增】落库后再查一遍真实数量，直接打印出来方便肉眼核对
    herb_total = cursor.execute(
        "SELECT COUNT(*) FROM herb_inventory WHERE teacher_name = ?", (TEACHER_NAME,)).fetchone()[0]
    herb_low = cursor.execute(
        "SELECT COUNT(*) FROM herb_inventory WHERE teacher_name = ? AND stock_amount <= warn_threshold", (TEACHER_NAME,)).fetchone()[0]
    remote_total = cursor.execute(
        "SELECT COUNT(*) FROM appointments WHERE teacher_name = ? AND is_remote = 1", (TEACHER_NAME,)).fetchone()[0]
    conn.close()
    print(f"✅ 已生成 {len(TEST_STUDENTS)} 个测试学生，全部绑定到李老师名下")
    print(f"🔎 落库校验：herbs={herb_total}（其中低于预警阈值 {herb_low} 味）、remote_appointments={remote_total} 条")
    print("")
    print("测试提示：")
    print("  1) 老师端 → 🩺 诊室 → 面诊队列：今天有 李四 10:00、张三 15:00 两场已确认预约")
    print("  2) 同页面右列「💻 远程问诊」：今天 王五 14:00，明天 周九 10:00、吴十 15:00（均 is_remote=1）")
    print("  3) 点队列里的学生 / 搜索学生选中后，若没有病历草案会自动生成本地草案，录音、拍照、把脉立即可用")
    print("  4) 张三已有一条学生陈述，补完病历点“保存病历修改”即可落库")
    print("  5) 财务账户已就绪：张三余额 100、李老师余额 500（GET /api/finance/accounts 可查）")
    print("  6) 药材库存共 %d 味（≥30 味，九宫格开方够用），其中 陈皮/当归/黄连 低于预警阈值，可测库存预警" % herb_total)


if __name__ == "__main__":
    seed()