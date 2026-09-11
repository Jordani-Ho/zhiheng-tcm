from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

app = FastAPI(title="zhiheng-tcm-backend")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)

# 四大核心角色的数据模型（模拟数据）
ROLE_DATA = {
    "patient_zhangsan": {
        "role_name": "患者张三",
        "role_type": "patient",
        "view_title": "📝 我的作业",
        "view_content": "今日作业：按揉太渊穴5分钟。请记得在酉时完成。",
        "can_check_in": True,
        "privacy_notice": "🔒 数据主权归你所有 · 阅后即焚"
    },
    "patient_agent": {
        "role_name": "张三智能体",
        "role_type": "patient_agent",
        "view_title": "🤖 智能体采集",
        "view_content": "已采集张三今日的打卡数据，等待老师审核。",
        "can_check_in": False,
        "privacy_notice": "🔒 数据仅由智能体采集上报，不存储"
    },
    "teacher_li": {
        "role_name": "李老师",
        "role_type": "teacher",
        "view_title": "📋 患者作业审核",
        "view_content": "张三：已完成白露节气穴位按摩，等待老师签字确认。",
        "can_check_in": False,
        "privacy_notice": "🔒 老师端阅后即焚，不存病历"
    },
    "teacher_agent": {
        "role_name": "李老师智能体",
        "role_type": "teacher_agent",
        "view_title": "🤖 智能体草案",
        "view_content": "已根据张三的打卡生成回复草案，等待老师审核签字。",
        "can_check_in": False,
        "privacy_notice": "🔒 草案由智能体生成，老师签字才生效"
    }
}

@app.get("/api/health")
def health():
    return {"status": "ok", "service": "zhiheng-tcm-backend"}

@app.get("/api/huangli")
def get_huangli():
    return {
        "date": "2026年09月11日",
        "lunar": "农历八月初一",
        "solar_term": "白露",
        "health_trend": "宜养肺润燥，早卧早起",
        "homework": "今日酉时（17-19点）按揉太渊穴5分钟"
    }

@app.get("/api/role/{role_key}")
def get_role_data(role_key: str):
    # 根据角色返回对应数据，如果角色不存在则返回默认值
    return ROLE_DATA.get(role_key, ROLE_DATA["patient_zhangsan"])