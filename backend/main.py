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

# 全局用户状态（真实业务会存患者端本地，这里模拟）
user_state = {
    "points": 120,  # 初始积分
    "today_checked": False,  # 今日是否已打卡
    "checkin_time": ""
}

@app.get("/api/health")
def health():
    return {"status": "ok", "service": "zhiheng-tcm-backend"}

@app.get("/api/user/status")
def get_user_status():
    return user_state

# 打卡接口
@app.post("/api/user/checkin")
def checkin():
    if user_state["today_checked"]:
        return {"message": "今日已打卡，不可重复操作"}
    
    user_state["today_checked"] = True
    user_state["points"] += 10  # 完成一次奖励10积分
    user_state["checkin_time"] = "酉时" # 模拟当前时辰
    return {"message": "打卡成功！积分+10", "points": user_state["points"]}