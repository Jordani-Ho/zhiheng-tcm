"""
【第44天】测试数据合成脚本
用法：cd /workspaces/zhiheng-tcm/backend && python seed_test_data.py
作用：为李老师生成 8 个虚拟学生，各自有不同的活跃度和积分，用于测试状态标签
注意：这是测试脚本，正式上线前可以删除
"""
import sqlite3
import os
from datetime import datetime, timedelta

DB_PATH = os.path.join(os.path.dirname(__file__), "zhiheng.db")

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


def seed():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()

    today = datetime.now().strftime("%Y-%m-%d")

    # 先删除同名的旧测试数据（防止重复运行）
    for name, *_ in TEST_STUDENTS:
        cursor.execute("DELETE FROM patients WHERE name = ?", (name,))
        cursor.execute("DELETE FROM patient_profiles WHERE patient_name = ?", (name,))
        cursor.execute("DELETE FROM patient_teachers WHERE patient_name = ?", (name,))
        cursor.execute("DELETE FROM accounts WHERE role_name = ?", (name,))

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
            "INSERT INTO accounts (role_name, points) VALUES (?, ?)",
            (name, points)
        )

    conn.commit()
    conn.close()
    print(f"✅ 已生成 {len(TEST_STUDENTS)} 个测试学生，全部绑定到李老师名下")


if __name__ == "__main__":
    seed()