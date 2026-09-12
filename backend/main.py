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

# 模拟用户数据库（内存版本）
patient_data = {
    "name": "患者张三",
    "points": 100,
    "today_checked": False,
    "pending_approval": False,  # 是否有待审核的打卡
    "checkin_time": ""
}

@app.get("/api/health")
def health():
    return {"status": "ok", "service": "zhiheng-tcm-backend"}

# 登录接口（沿用之前的邀请码）
@app.post("/api/auth/login")
def login(payload: dict):
    code = payload.get("code", "").strip().upper()
    if code == "TEACHER888":
        return {"role": "teacher", "name": "李老师"}
    elif code == "PATIENT666":
        return {"role": "patient", "name": "患者张三"}
    else:
        return {"error": "邀请码无效，请联系您的老师获取"}

# 1. 患者打卡（提交待审核）
@app.post("/api/patient/checkin")
def patient_checkin():
    if patient_data["today_checked"]:
        return {"message": "今日已打卡，等待老师审核"}
    patient_data["today_checked"] = True
    patient_data["pending_approval"] = True
    patient_data["checkin_time"] = "酉时"
    return {"message": "打卡成功，已提交老师审核"}

# 2. 获取患者状态
@app.get("/api/patient/status")
def get_patient_status():
    return patient_data

# 3. 老师审核并通过（增加积分）
@app.post("/api/teacher/approve")
def teacher_approve():
    if not patient_data["pending_approval"]:
        return {"message": "当前没有待审核的打卡记录"}
    patient_data["pending_approval"] = False
    patient_data["points"] += 10  # 老师审核通过，积分+10
    return {"message": "审核通过，患者积分+10", "points": patient_data["points"]}