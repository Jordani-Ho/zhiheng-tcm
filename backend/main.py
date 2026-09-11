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

# 黄历数据
@app.get("/api/huangli")
def get_huangli():
    return {
        "date": "2026年09月11日",
        "lunar": "农历八月初一",
        "solar_term": "白露",
        "health_trend": "宜养肺润燥，早卧早起",
        "homework": "今日酉时（17-19点）按揉太渊穴5分钟"
    }

# 四大角色数据
@app.get("/api/roles")
def get_roles():
    return [
        {"id": "teacher_li", "name": "李老师", "type": "老师"},
        {"id": "agent_li", "name": "李老师智能体", "type": "助理"},
        {"id": "patient_zhang", "name": "张三", "type": "患者"},
        {"id": "agent_zhang", "name": "张三智能体", "type": "顾问"}
    ]

# 根据角色ID获取不同数据
@app.get("/api/role/{role_id}")
def get_role_data(role_id: str):
    if role_id == "teacher_li":
        return {"title": "李老师的诊室", "content": "您今天有3位患者打卡需要审核。", "color": "#e6f2ff"}
    elif role_id == "patient_zhang":
        return {"title": "张三的作业", "content": "今日作业：按揉太渊穴5分钟。请记得在酉时完成。", "color": "#fff8e7"}
    elif role_id == "agent_li":
        return {"title": "李老师的智能助理", "content": "今日患者打卡率 85%，有1位患者未按时打卡。", "color": "#f0f0f0"}
    else:
        return {"title": "张三的智能顾问", "content": "正在采集您的身体数据，建议今日多喝水，注意保暖。", "color": "#f0f0f0"}
