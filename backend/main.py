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

homework_db = {"patient_name": "张三", "task": "今日作业：按揉太渊穴5分钟", "detail": "请记得在酉时完成。", "status": "pending"}
transcriptions_db = []
drafts_db = []
patient_records_db = [] # 患者健康档案

class TranscriptionInput(BaseModel):
    patient_name: str
    content: str
    data_type: str

class DraftUpdate(BaseModel):
    content: str

# 【新增】签字时接收最终方案
class SignInput(BaseModel):
    final_plan: str

@app.get("/api/huangli")
def get_huangli():
    return {"date": "2026年09月11日", "lunar": "农历八月初一", "solar_term": "白露", "health_trend": "宜养肺润燥，早卧早起", "homework": "今日酉时（17-19点）按揉太渊穴5分钟"}

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

@app.post("/api/transcribe")
def transcribe(input_data: TranscriptionInput):
    transcriptions_db.append({"id": len(transcriptions_db) + 1, "patient_name": input_data.patient_name, "content": input_data.content, "data_type": input_data.data_type})
    return {"message": "转述成功"}

@app.get("/api/transcriptions")
def get_transcriptions():
    return transcriptions_db

@app.post("/api/generate-draft")
def generate_draft(transcript_id: int):
    transcript = next((t for t in transcriptions_db if t["id"] == transcript_id), None)
    if not transcript:
        return {"error": "找不到该转述"}

    patient_name = transcript['patient_name']
    # 1. 获取该患者过往已签字病历
    past_records = [r for r in patient_records_db if r["patient_name"] == patient_name]
    past_content = "\n".join([f"- {r['content']}" for r in past_records]) if past_records else "暂无过往病历"

    # 2. 拼接最新陈述和过往病历（仅供老师参考）
    template = f"""【{patient_name}过往病历】
{past_content}

【{patient_name}最新陈述】
{transcript['content']}

（以上内容仅供老师辨证参考）"""

    draft = {
        "id": len(drafts_db) + 1,
        "transcript_id": transcript_id,
        "patient_name": patient_name,
        "content": template.strip(),
        "signed": False
    }
    drafts_db.append(draft)
    return {"message": "病历草案生成成功", "draft": draft}

@app.get("/api/drafts")
def get_drafts():
    return drafts_db

@app.put("/api/drafts/{draft_id}")
def update_draft(draft_id: int, update_data: DraftUpdate):
    draft = next((d for d in drafts_db if d["id"] == draft_id), None)
    if not draft:
        return {"error": "找不到该病历"}
    draft["content"] = update_data.content
    return {"message": "病历已更新", "draft": draft}

# 【修改】老师签字时，只归档最终方案给患者
@app.post("/api/drafts/{draft_id}/sign")
def sign_draft(draft_id: int, input_data: SignInput):
    draft = next((d for d in drafts_db if d["id"] == draft_id), None)
    if not draft:
        return {"error": "找不到该病历"}
    
    # 1. 归档到患者健康档案（只存最终方案，不含过往病历和陈述）
    patient_record = {
        "id": len(patient_records_db) + 1,
        "patient_name": draft["patient_name"],
        "content": input_data.final_plan, # 只存老师给的方案
        "doctor": "李老师"
    }
    patient_records_db.append(patient_record)
    
    # 2. 从老师待办列表中移除（阅后即焚）
    drafts_db.remove(draft)
    
    return {"message": "签字确认成功，最终方案已归档至患者健康档案", "destroyed": True}

@app.get("/api/patient-records")
def get_patient_records():
    return patient_records_db