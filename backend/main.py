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

checkins = [{"id": 1, "patient_name": "张三", "time": "16:30", "status": "已提交", "content": "太渊穴按揉完成"}]
drafts = []

@app.get("/api/huangli")
def get_huangli():
    return {"date": "2026年09月11日", "lunar": "农历八月初一", "solar_term": "白露", "health_trend": "宜养肺润燥，早卧早起", "homework": "今日酉时（17-19点）按揉太渊穴5分钟"}

@app.get("/api/roles")
def get_roles():
    return [{"id": "teacher_li", "name": "李老师"}, {"id": "agent_li", "name": "李老师智能体"}, {"id": "patient_zhang", "name": "张三"}, {"id": "agent_zhang", "name": "张三智能体"}]

@app.get("/api/role/{role_id}")
def get_role_data(role_id: str):
    if role_id == "teacher_li": return {"title": "李老师的诊室", "content": "您今天有患者打卡需要审核。", "color": "#e6f2ff"}
    if role_id == "patient_zhang": return {"title": "张三的作业", "content": "今日作业：按揉太渊穴5分钟。", "color": "#fff8e7"}
    if role_id == "agent_li": return {"title": "李老师的智能助理", "content": "根据患者数据，已为您生成今日审核草案。", "color": "#f0f0f0"}
    return {"title": "张三的智能顾问", "content": "正在采集身体数据。", "color": "#f0f0f0"}

@app.post("/api/checkin")
def do_checkin():
    checkins.append({"id": len(checkins) + 1, "patient_name": "张三", "time": "刚刚", "status": "已提交", "content": "今日作业：按揉太渊穴5分钟"})
    return {"status": "ok"}

@app.get("/api/checkins")
def get_checkins():
    return checkins

@app.post("/api/agent/draft")
def generate_draft():
    new_draft = {"id": len(drafts) + 1, "agent_name": "李老师智能体", "content": "建议：张三今日打卡完成，可以给予 10 积分奖励。", "status": "待审核"}
    drafts.append(new_draft)
    return {"status": "ok", "draft": new_draft}

@app.get("/api/drafts")
def get_drafts():
    return drafts

@app.post("/api/drafts/{draft_id}/approve")
def approve_draft(draft_id: int):
    global drafts
    for d in drafts:
        if d["id"] == draft_id:
            d["status"] = "已签字生效"
            approved = d.copy()
            drafts = [x for x in drafts if x["id"] != draft_id]
            return {"status": "ok", "message": "签字成功，草案已生效并焚毁", "approved": approved}
    return {"status": "error", "message": "草案不存在"}