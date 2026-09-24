"""
【第44天】测试数据合成脚本
用法：cd /workspaces/zhiheng-tcm/backend && python seed_test_data.py
作用：为李老师生成 8 个虚拟学生，各自有不同的活跃度和积分，用于测试状态标签
注意：这是测试脚本，正式上线前可以删除
【第65天】顺带补齐财务账户种子数据：张三 100、李老师 500（账户不存在才创建）
"""
import sqlite3
import os
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

# 【第59天新增】中药材库存：(药材名, 库存量, 单位, 预警阈值)
TEST_HERBS = [
    ("黄芪", 500, "克", 100),
    ("当归", 300, "克", 100),
    ("枸杞", 1000, "克", 200),
    ("甘草", 200, "克", 50),
    ("陈皮", 40, "克", 60),    # 低于预警阈值，用于测试“库存预警”
]

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
    """【第59天新增】中药材库存表（与 database.init_herb_table 定义保持一致）+ 余额流水表。"""
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


def seed_appointments(cursor):
    """【第59天新增】今天 / 明天的已确认预约，让老师“诊室 → 面诊队列”有数据。"""
    now = datetime.now()
    for patient_name, day_offset, time_str, reason, status in TEST_APPOINTMENTS:
        date_str = (now + timedelta(days=day_offset)).strftime("%Y-%m-%d")
        cursor.execute(
            "DELETE FROM appointments WHERE patient_name = ? AND teacher_name = ? AND scheduled_date = ? AND scheduled_time = ?",
            (patient_name, TEACHER_NAME, date_str, time_str)
        )
        cursor.execute(
            "INSERT INTO appointments (patient_name, teacher_name, initiator, scheduled_date, scheduled_time, reason, status, created_at, confirmed_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (patient_name, TEACHER_NAME, "student", date_str, time_str, reason, status,
             now.strftime("%Y-%m-%d"), now.strftime("%Y-%m-%d") if status == "confirmed" else None)
        )
    today_count = len([a for a in TEST_APPOINTMENTS if a[1] == 0])
    print("✅ 已生成 %d 条预约（今天 %d 条已确认，老师“诊室 → 面诊队列”可见）" % (len(TEST_APPOINTMENTS), today_count))


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
    ensure_extra_tables(cursor)   # 中药材库存表 + 余额流水表
    seed_herbs(cursor)            # 中药材库存（黄芪/当归/枸杞/甘草/陈皮）
    seed_points(cursor)           # 余额 + 充值/消耗流水
    seed_finance_accounts(cursor) # 【第65天新增】财务账户：张三 100、李老师 500
    seed_appointments(cursor)     # 今天/明天的已确认预约（面诊队列）
    seed_transcriptions(cursor)   # 学生陈述（未处理）

    conn.commit()
    conn.close()
    print(f"✅ 已生成 {len(TEST_STUDENTS)} 个测试学生，全部绑定到李老师名下")
    print("")
    print("测试提示：")
    print("  1) 老师端 → 🩺 诊室 → 面诊队列：今天有 李四 10:00、张三 15:00 两场已确认预约")
    print("  2) 点队列里的学生 / 搜索学生选中后，若没有病历草案会自动生成本地草案，录音、拍照、把脉立即可用")
    print("  3) 张三已有一条学生陈述，补完病历点“保存病历修改”即可落库")
    print("  4) 财务账户已就绪：张三余额 100、李老师余额 500（GET /api/finance/accounts 可查）")


if __name__ == "__main__":
    seed()