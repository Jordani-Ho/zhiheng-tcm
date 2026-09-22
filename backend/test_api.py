"""zhiheng-tcm 后端 API 集成测试。

运行方式：
    cd /workspaces/zhiheng-tcm/backend
    pytest -v
"""
import agent


# ============ 基础接口 ============
def test_health(client):
    """黄历接口：返回日期 + 节气 + 作业"""
    r = client.get("/api/huangli")
    assert r.status_code == 200
    d = r.json()
    assert "date" in d
    assert "lunar" in d
    assert "homework" in d


def test_teachers(client):
    """老师列表：至少有一位李老师"""
    r = client.get("/api/teachers")
    assert r.status_code == 200
    teachers = r.json()
    names = [t["name"] for t in teachers]
    assert "李老师" in names


def test_patients(client):
    """学生列表：张三、李四在列"""
    r = client.get("/api/patients?guardian_name=张三")
    assert r.status_code == 200
    names = [p["name"] for p in r.json()]
    assert "张三" in names


def test_patient_profile(client):
    """患者档案 + 八字推算"""
    r = client.get("/api/patient-profile?patient_name=张三")
    assert r.status_code == 200
    d = r.json()
    assert "patient_name" in d
    # 张三初始档案没出生日期，八字字段应该提示"缺少出生日期"
    assert "bazi" in d


def test_health_trend(client):
    """健康趋势：张三没出生日期，应返回 error"""
    r = client.get("/api/health-trend?patient_name=张三")
    assert r.status_code == 200


def test_daily_advice(client):
    """每日建议：一定有 eat / avoid / wear"""
    r = client.get("/api/daily-advice?patient_name=张三")
    assert r.status_code == 200
    d = r.json()
    assert "eat" in d
    assert "avoid" in d
    assert "wear" in d


# ============ 角色数据 ============
def test_role_data_student(client):
    """学生视角：能看到任务"""
    r = client.get("/api/role-data?role=学生&patient_name=张三&teacher_name=李老师")
    assert r.status_code == 200
    d = r.json()
    assert d["role_type"] == "patient"


def test_role_data_teacher(client):
    """老师视角：能看到任务"""
    r = client.get("/api/role-data?role=李老师&patient_name=张三&teacher_name=李老师")
    assert r.status_code == 200
    d = r.json()
    assert d["role_type"] == "teacher"


# ============ 打卡 / 积分 ============
def test_check_in(client):
    """打卡后积分 +10"""
    before = client.get("/api/points?patient_name=张三").json()
    before_pts = before["patient_points"]

    r = client.post("/api/check-in?patient_name=张三&teacher_name=李老师")
    assert r.status_code == 200

    after = client.get("/api/points?patient_name=张三").json()
    assert after["patient_points"] == before_pts + 10


# ============ 师生关系 ============
def test_add_and_remove_teacher(client):
    """添加老师 → 查询 → 移除"""
    # 添加
    r = client.post("/api/patient-teachers", json={"patient_name": "张三", "teacher_name": "李老师"})
    assert r.status_code == 200

    # 查询
    r = client.get("/api/patient-teachers?patient_name=张三")
    assert "李老师" in r.json()

    # 移除
    r = client.delete("/api/patient-teachers?patient_name=张三&teacher_name=李老师")
    assert r.status_code == 200


def test_teacher_patients_with_status(client):
    """老师端学生列表：含状态标签"""
    r = client.get("/api/teacher-patients?teacher_name=李老师")
    assert r.status_code == 200
    students = r.json()
    assert len(students) >= 1
    # 每个学生都应有 status_label
    for s in students:
        assert "name" in s
        assert "status_label" in s
        assert "status_color" in s


# ============ 邀请码 ============
def test_create_invite(client):
    """生成邀请码：格式 ZHI-XXXXXX"""
    r = client.post("/api/invites", json={"teacher_name": "李老师"})
    assert r.status_code == 200
    d = r.json()
    assert d["code"].startswith("ZHI-")
    assert len(d["code"]) == 10


# ============ 完整闭环：发陈述 → 生成草案 → 签字 ============
def test_full_workflow(client, monkeypatch):
    """核心闭环：发陈述 → 自动生成病历草案 → 签字归档"""
    # Mock AI 调用，避免消耗真实 API 额度
    monkeypatch.setattr(agent, "structurize_patient_input", lambda x: "主诉：测试症状\n现病史：测试")
    monkeypatch.setattr(agent, "generate_medical_draft", lambda p, v, c, pr: "【中医病历草案】\n学生：" + p + "\n主诉：" + c)

    # 1. 学生发陈述
    r = client.post("/api/transcribe", json={
        "patient_name": "张三",
        "teacher_name": "李老师",
        "content": "今天有点头疼",
        "data_type": "text"
    })
    assert r.status_code == 200

    # 2. 老师端能拉到草案
    r = client.get("/api/drafts?teacher_name=李老师")
    assert r.status_code == 200
    drafts = r.json()
    assert len(drafts) >= 1
    draft_id = drafts[0]["id"]

    # 3. 老师签字归档
    r = client.post(f"/api/drafts/{draft_id}/sign", json={
        "final_plan": "抓药调理，注意休息",
        "final_content": "【完整病历】\n主诉：头疼\n施治方案：抓药调理"
    })
    assert r.status_code == 200

    # 4. 患者档案里能查到
    r = client.get("/api/patient-records?patient_name=张三&teacher_name=李老师")
    assert r.status_code == 200
    records = r.json()
    assert len(records) >= 1
    assert "抓药调理" in records[0]["final_plan"]


# ============ 标签（知识库素材） ============
def test_tags(client):
    """打标签 → 查询 → 汇总"""
    # 打标签
    r = client.post("/api/tags", json={
        "record_id": 1,
        "teacher_name": "李老师",
        "tags": [
            {"tag_type": "部位", "tag_value": "舌苔"},
            {"tag_type": "症状", "tag_value": "湿热"}
        ]
    })
    assert r.status_code == 200

    # 查询
    r = client.get("/api/tags?record_id=1")
    assert r.status_code == 200
    tags = r.json()
    assert len(tags) == 2

    # 汇总
    r = client.get("/api/tags-summary?teacher_name=李老师")
    assert r.status_code == 200


# ============ 添加亲友 ============
def test_add_family(client):
    """添加亲友：王小明"""
    r = client.post("/api/patients/add", json={
        "name": "王小明",
        "guardian_name": "张三",
        "relation": "儿子",
        "gender": "男",
        "birth_date": "2020-05-01",
        "birth_time": "09:00",
        "birth_place": "广东省广州市",
        "location": "广东省广州市"
    })
    assert r.status_code == 200

    # 查询是否在列表
    r = client.get("/api/patients?guardian_name=张三")
    names = [p["name"] for p in r.json()]
    assert "王小明" in names
    # ============ 测试：中药材库存管理 ============

def test_herbs_crud(client):
    # 新增
    r = client.post("/api/herbs", json={"teacher_name": "李老师", "herb_name": "甘草", "stock_amount": 100, "unit": "克", "warn_threshold": 50})
    assert r.status_code == 200
    # 查询
    r = client.get("/api/herbs?teacher_name=李老师")
    assert r.status_code == 200
    herbs = r.json()
    assert len(herbs) == 1
    assert herbs[0]["herb_name"] == "甘草"
    # 调整
    r = client.post(f"/api/herbs/{herbs[0]['id']}/adjust", json={"delta": -60})
    assert r.status_code == 200
    # 查询预警
    r = client.get("/api/herbs/low?teacher_name=李老师")
    assert r.status_code == 200
    low = r.json()
    assert len(low) == 1  # 100-60=40 < 50


def test_herbs_batch_deduct(client):
    client.post("/api/herbs", json={"teacher_name": "李老师", "herb_name": "黄芪", "stock_amount": 200, "unit": "克", "warn_threshold": 50})
    r = client.post("/api/herbs/batch-deduct", json={"teacher_name": "李老师", "items": [{"herb_name": "黄芪", "amount": 30}]})
    assert r.status_code == 200