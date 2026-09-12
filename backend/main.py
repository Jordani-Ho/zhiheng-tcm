from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

app = FastAPI(title="zhiheng-tcm-backend")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)

# 模拟数据库
homework_db = {
    "patient_name": "张三",
    "task": "今日作业：按揉太渊穴5分钟",
    "detail": "请记得在酉时完成。",
    "status": "pending"
}

# 转述记录（模拟患者智能体的转述本）
transcriptions_db = []

# 定义接收数据的格式
class TranscriptionInput(BaseModel):
    patient_name: str
    content: str
    data_type: str  # text, image, audio

@app.get("/api/huangli")
def get_huangli():
    return {
        "date": "2026年09月11日",
        "lunar": "农历八月初一",
        "solar_term": "白露",
        "health_trend": "宜养肺润燥，早卧早起",
        "homework": "今日酉时（17-19点）按揉太渊穴5分钟"
    }

@app.get("/api/role-data")
def get_role_data(role: str):
    if role == "李老师":
        if homework_db["status"] == "pending":
            return {"role_type": "teacher", "name": "李老师", "task": "待审核", "detail": "患者尚未打卡。"}
        elif homework_db["status"] == "checked_in":
            return {"role_type": "teacher", "name": "李老师", "task": "待审核", "detail": f"{homework_db['patient_name']}：{homework_db['task']}（已打卡，待签字确认）"}
        else:
            return {"role_type": "teacher", "name": "李老师", "task": "已审核", "detail": f"{homework_db['patient_name']}的作业已签字确认。"}
    
    elif role == "患者张三":
        if homework_db["status"] == "pending":
            return {"role_type": "patient", "name": "张三", "task": homework_db["task"], "detail": homework_db["detail"]}
        elif homework_db["status"] == "checked_in":
            return {"role_type": "patient", "name": "张三", "task": homework_db["task"], "detail": "已打卡，等待老师签字确认。"}
        else:
            return {"role_type": "patient", "name": "张三", "task": homework_db["task"], "detail": "老师已签字确认，完成！"}
    
    return {"role_type": "unknown", "name": role, "task": "暂无任务", "detail": "数据加载中..."}

@app.post("/api/check-in")
def check_in():
    homework_db["status"] = "checked_in"
    return {"message": "打卡成功"}

@app.post("/api/approve")
def approve():
    homework_db["status"] = "approved"
    return {"message": "审核通过"}

# 患者智能体转述接口
@app.post("/api/transcribe")
def transcribe(input_data: TranscriptionInput):
    # 【铁律】：这里只做记录和转述，不做任何推理、诊断、修改。
    # 只是把患者的输入原样保存下来，准备转交给老师。
    transcriptions_db.append({
        "id": len(transcriptions_db) + 1,
        "patient_name": input_data.patient_name,
        "content": input_data.content,
        "data_type": input_data.data_type
    })
    return {"message": "转述成功", "total": len(transcriptions_db)}

# 老师获取转述列表接口
@app.get("/api/transcriptions")
def get_transcriptions():
    return transcriptions_db