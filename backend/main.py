from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from datetime import datetime

app = FastAPI(title="zhiheng-tcm-backend")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)

# 系统状态（内存模拟，真实场景存患者端本地）
state = {
    "status": "待患者打卡",
    "patient_data": "",
    "current_shi": "",
    "ai_draft": "",
    "is_signed": False,
    "signed_content": ""
}

# 子午流注时辰算法
def get_shi_chen():
    hour = datetime.now().hour
    if 23 <= hour or hour < 1: return "子时", "胆经当令，宜入睡"
    if 1 <= hour < 3: return "丑时", "肝经当令，宜深睡"
    if 3 <= hour < 5: return "寅时", "肺经当令，宜熟睡"
    if 5 <= hour < 7: return "卯时", "大肠经当令，宜排便"
    if 7 <= hour < 9: return "辰时", "胃经当令，宜吃早餐"
    if 9 <= hour < 11: return "巳时", "脾经当令，宜工作"
    if 11 <= hour < 13: return "午时", "心经当令，宜小憩"
    if 13 <= hour < 15: return "未时", "小肠经当令，宜多喝水"
    if 15 <= hour < 17: return "申时", "膀胱经当令，宜运动"
    if 17 <= hour < 19: return "酉时", "肾经当令，宜按揉太渊穴"
    if 19 <= hour < 21: return "戌时", "心包经当令，宜散步"
    return "亥时", "三焦经当令，宜准备入睡"

@app.get("/api/health")
def health():
    return {"status": "ok", "service": "zhiheng-tcm-backend"}

@app.post("/api/auth/login")
def login(payload: dict):
    code = payload.get("code", "").strip().upper()
    if code == "TEACHER888": return {"role": "teacher", "name": "李老师"}
    elif code == "PATIENT666": return {"role": "patient", "name": "患者张三"}
    return {"error": "邀请码无效"}

# 1. 患者智能体：采集上报（自动获取当前时辰）
@app.post("/api/patient/collect")
def patient_collect(payload: dict):
    data = payload.get("data", "")
    if not data: return {"error": "请输入健康数据"}
    shi, advice = get_shi_chen()
    state["status"] = "已上报，待老师智能体推理"
    state["patient_data"] = data
    state["current_shi"] = f"{shi}（{advice}）"
    state["is_signed"] = False
    state["signed_content"] = ""
    return state

# 2. 老师智能体：生成草案
@app.post("/api/teacher/generate")
def teacher_generate():
    if not state["patient_data"]: return {"error": "无患者数据"}
    data = state["patient_data"]
    # 简单的中医辨证规则引擎
    syndrome = "需进一步问诊"
    if "苔白" in data and "畏寒" in data: syndrome = "寒湿困脾"
    elif "脉细" in data: syndrome = "气血不足"
    
    state["ai_draft"] = f"【辨证】：{syndrome}\n【症状】：{data}\n【建议】：建议温阳化湿，艾灸足三里、中脘穴。"
    state["status"] = "待老师审核签字"
    return state

# 3. 老师真人：签字生效
@app.post("/api/teacher/sign")
def teacher_sign():
    if "待老师审核签字" not in state["status"]: return {"error": "当前没有待签字的草案"}
    state["is_signed"] = True
    state["signed_content"] = state["ai_draft"]
    state["status"] = "已签字生效，阅后即焚"
    return state

# 4. 获取状态（轮询用）
@app.get("/api/status")
def get_status():
    return state

# 5. 阅后即焚（清空所有数据）
@app.post("/api/burn")
def burn():
    state.update({
        "status": "待患者打卡", "patient_data": "", "current_shi": "",
        "ai_draft": "", "is_signed": False, "signed_content": ""
    })
    return state