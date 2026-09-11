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

# 全局状态（实际生产环境会存患者端本地，这里为了演示先放内存）
patient_state = {
    "raw_data": "",
    "ai_draft": "",
    "is_approved": False,
    "status": "待患者打卡"
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
        "homework": "今日酉时（17-19点）按揉太渊穴5分钟",
        "current_shi": "酉时"
    }

# 1. 患者智能体：采集上报
@app.post("/api/agent/patient/report")
def patient_report():
    patient_state["raw_data"] = "患者张三：今日酉时完成按揉太渊穴5分钟，感受微酸。"
    patient_state["status"] = "已上报，待老师智能体处理"
    return patient_state

# 2. 老师智能体：生成草案
@app.post("/api/agent/teacher/generate_draft")
def teacher_generate_draft():
    if "已上报" not in patient_state["status"]:
        return {"error": "患者尚未上报数据"}
    patient_state["ai_draft"] = "根据张三今日打卡反馈，建议明日减量至3分钟，并注意保暖。"
    patient_state["status"] = "待老师审核签字"
    return patient_state

# 3. 老师（真人）：审核签字
@app.post("/api/agent/teacher/approve")
def teacher_approve():
    if "待老师审核签字" not in patient_state["status"]:
        return {"error": "当前没有待审核的草案"}
    patient_state["is_approved"] = True
    patient_state["status"] = "已签字生效，阅后即焚"
    return patient_state

# 4. 获取当前状态（前端轮询用）
@app.get("/api/agent/state")
def get_agent_state():
    return patient_state