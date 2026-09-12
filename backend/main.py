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

# 模拟邀请码验证
@app.post("/api/auth/login")
def login(payload: dict):
    code = payload.get("code", "").strip().upper()
    
    # 老师邀请码
    if code == "TEACHER888":
        return {"role": "teacher", "name": "李老师"}
    # 患者邀请码
    elif code == "PATIENT666":
        return {"role": "patient", "name": "患者张三"}
    else:
        return {"error": "邀请码无效，请联系您的老师获取"}