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

@app.get("/api/health")
def health():
    return {"status": "ok", "service": "zhiheng-tcm-backend"}

@app.post("/api/auth/login")
def login(payload: dict):
    code = payload.get("code", "").strip().upper()
    if code == "TEACHER888":
        return {"role": "teacher", "name": "李老师"}
    elif code == "PATIENT666":
        return {"role": "patient", "name": "患者张三"}
    else:
        return {"error": "邀请码无效，请联系您的老师获取"}

# 老师智能体：接收前端传来的数据，生成草案（纯运算，不存储）
@app.post("/api/agent/teacher/draft")
def generate_draft(payload: dict):
    raw_data = payload.get("raw_data", "")
    if not raw_data:
        return {"error": "没有收到患者数据"}
    # 模拟智能体推理（后续这里会接入真实的 LangGraph/LLM）
    draft = f"根据患者反馈【{raw_data}】，建议明日减量至3分钟，注意保暖。"
    return {"draft": draft}