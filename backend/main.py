from fastapi import FastAPI, UploadFile, File
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel
from datetime import datetime
import lunardate
import cnlunar
import database
import os
import shutil
import uuid

app = FastAPI(title="zhiheng-tcm-backend")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)

UPLOAD_DIR = os.path.join(os.path.dirname(__file__), "uploads")
os.makedirs(UPLOAD_DIR, exist_ok=True)
app.mount("/uploads", StaticFiles(directory=UPLOAD_DIR), name="uploads")

database.init_db()

class TranscriptionInput(BaseModel):
    patient_name: str
    content: str
    data_type: str

class DraftUpdate(BaseModel):
    content: str

class SignInput(BaseModel):
    final_plan: str

class HomeworkInput(BaseModel):
    patient_name: str
    task: str
    detail: str

# 【第17天新增】患者档案输入模型
class ProfileInput(BaseModel):
    patient_name: str
    gender: str
    birth_date: str
    birth_time: str
    location: str

@app.get("/api/huangli")
def get_huangli():
    now = datetime.now()
    date_str = now.strftime("%Y年%m月%d日")
    lunar_date = lunardate.LunarDate.fromSolarDate(now.year, now.month, now.day)
    lunar_month = f"闰{lunar_date.month}月" if lunar_date.isLeapMonth else f"{lunar_date.month}月"
    lunar_day_str = f"初{lunar_date.day}" if lunar_date.day < 10 else f"{lunar_date.day}"
    if lunar_date.day == 1: lunar_day_str = "初一"
    if lunar_date.day == 15: lunar_day_str = "十五"
    lunar_str = f"农历{lunar_month}{lunar_day_str}"

    hour = now.hour
    shichen_index = (hour + 1) // 2 % 12
    shichen_names = ["子", "丑", "寅", "卯", "辰", "巳", "午", "未", "申", "酉", "戌", "亥"]
    current_shi = shichen_names[shichen_index] + "时"

    lunar_obj = cnlunar.Lunar(now, godType='8char')
    term_list = sorted(lunar_obj.thisYearSolarTermsDic.items(), key=lambda x: str(x[1]))
    today_str = now.strftime('%Y-%m-%d')
    
    prev_term = None
    next_term = None
    for name, date_val in term_list:
        if isinstance(date_val, tuple):
            date_str_val = f"{now.year}-{date_val[0]:02d}-{date_val[1]:02d}"
        else:
            date_str_val = str(date_val)[:10]
        if date_str_val <= today_str:
            prev_term = (name, date_str_val)
        elif date_str_val > today_str and next_term is None:
            next_term = (name, date_str_val)

    term_tip = ""
    today_term = lunar_obj.todaySolarTerms
    if today_term and today_term != '无':
        term_tip = f"今日{today_term}"
    else:
        parts = []
        if prev_term:
            prev_date = datetime.strptime(prev_term[1], '%Y-%m-%d')
            days_from_prev = (now - prev_date).days
            parts.append(f"{prev_term[0]}后第{days_from_prev}天")
        if next_term:
            next_date = datetime.strptime(next_term[1], '%Y-%m-%d')
            days_to_next = (next_date - now).days
            parts.append(f"离{next_term[0]}还有{days_to_next}天")
        term_tip = "，".join(parts)

    current_solar_term_name = today_term if (today_term and today_term != '无') else (prev_term[0] if prev_term else "")

    return {
        "date": date_str,
        "lunar": lunar_str,
        "solar_term": current_solar_term_name,
        "solar_term_tip": term_tip,
        "health_trend": "宜养肺润燥，早卧早起",
        "homework": f"今日{current_shi}（{hour}-{(hour+2)%24}点）按揉太渊穴5分钟",
        "current_shi": current_shi
    }

@app.get("/api/patients")
def get_patients():
    return database.get_patients()

# 【第17天新增】获取患者档案
@app.get("/api/patient-profile")
def get_patient_profile(patient_name: str):
    return database.get_patient_profile(patient_name)

# 【第17天新增】保存患者档案
@app.post("/api/patient-profile")
def save_patient_profile(input_data: ProfileInput):
    database.save_patient_profile(
        input_data.patient_name,
        input_data.gender,
        input_data.birth_date,
        input_data.birth_time,
        input_data.location
    )
    return {"message": "档案保存成功"}

@app.get("/api/role-data")
def get_role_data(role: str, patient_name: str = "张三"):
    hw = database.get_homework(patient_name)
    
    if role == "李老师":
        if not hw:
            return {"role_type": "teacher", "name": "李老师", "task": "待审核", "detail": f"{patient_name}尚未打卡。"}
        if hw["status"] == "pending":
            return {"role_type": "teacher", "name": "李老师", "task": "待审核", "detail": f"{patient_name}尚未打卡。"}
        elif hw["status"] == "checked_in":
            return {"role_type": "teacher", "name": "李老师", "task": "待审核", "detail": f"{patient_name}：{hw['task']}（已打卡，待签字确认）"}
        else:
            return {"role_type": "teacher", "name": "李老师", "task": "已审核", "detail": f"{patient_name}的作业已签字确认。"}
    elif role == "患者" or role == "患者智能体":
        if not hw:
            return {"role_type": "patient", "name": patient_name, "task": "暂无作业", "detail": "等待老师布置作业。"}
        if hw["status"] == "pending":
            return {"role_type": "patient", "name": patient_name, "task": hw["task"], "detail": hw["detail"]}
        elif hw["status"] == "checked_in":
            return {"role_type": "patient", "name": patient_name, "task": hw["task"], "detail": "已打卡，等待老师签字确认。"}
        else:
            return {"role_type": "patient", "name": patient_name, "task": hw["task"], "detail": "老师已签字确认，完成！"}
    return {"role_type": "unknown", "name": role, "task": "暂无任务", "detail": "数据加载中..."}

@app.post("/api/homework")
def create_homework(input_data: HomeworkInput):
    database.create_homework(input_data.patient_name, input_data.task, input_data.detail)
    return {"message": "作业已布置"}

@app.post("/api/check-in")
def check_in(patient_name: str = "张三"):
    database.update_homework_status(patient_name, "checked_in")
    database.add_points(patient_name, 10)
    return {"message": "打卡成功"}

@app.post("/api/approve")
def approve(patient_name: str = "张三"):
    database.update_homework_status(patient_name, "approved")
    return {"message": "审核通过"}

@app.post("/api/transcribe")
def transcribe(input_data: TranscriptionInput):
    database.insert_transcription(input_data.patient_name, input_data.content, input_data.data_type)
    return {"message": "转述成功"}

@app.post("/api/upload")
async def upload_image(patient_name: str = "张三", file: UploadFile = File(...)):
    ext = os.path.splitext(file.filename)[1] if file.filename else ".jpg"
    unique_name = f"{uuid.uuid4().hex}{ext}"
    file_path = os.path.join(UPLOAD_DIR, unique_name)
    
    with open(file_path, "wb") as buffer:
        shutil.copyfileobj(file.file, buffer)
    
    file_url = f"/uploads/{unique_name}"
    database.insert_transcription(patient_name, file_url, "image")
    return {"message": "图片转述成功", "url": file_url}

@app.get("/api/transcriptions")
def get_transcriptions(patient_name: str = None):
    return database.get_transcriptions(patient_name)

@app.post("/api/generate-draft")
def generate_draft(transcript_id: int):
    transcripts = database.get_transcriptions()
    transcript = next((t for t in transcripts if t["id"] == transcript_id), None)
    if not transcript:
        return {"error": "找不到该转述"}

    patient_name = transcript['patient_name']
    past_records = database.get_patient_records(patient_name)
    past_content = "\n".join([f"- {r['final_plan']}" for r in past_records]) if past_records else "暂无过往病历"

    if transcript['data_type'] == 'image':
        content_desc = f"[患者上传了图片：{transcript['content']}]"
    else:
        content_desc = transcript['content']

    template = f"""【{patient_name}过往病历】
{past_content}

【{patient_name}最新陈述】
{content_desc}

（以上内容仅供老师辨证参考）"""

    draft_id = database.insert_draft(transcript_id, patient_name, template.strip())
    return {"message": "病历草案生成成功", "draft_id": draft_id}

@app.get("/api/drafts")
def get_drafts():
    return database.get_drafts()

@app.put("/api/drafts/{draft_id}")
def update_draft(draft_id: int, update_data: DraftUpdate):
    database.update_draft_content(draft_id, update_data.content)
    return {"message": "病历已更新"}

@app.post("/api/drafts/{draft_id}/sign")
def sign_draft_endpoint(draft_id: int, input_data: SignInput):
    patient_name = database.sign_draft(draft_id, input_data.final_plan)
    if not patient_name:
        return {"error": "找不到该病历"}
    database.transfer_points(patient_name, "李老师", 50)
    return {"message": "签字确认成功，已归档至患者健康档案，学费已支付"}

@app.get("/api/patient-records")
def get_patient_records(patient_name: str = None):
    return database.get_patient_records(patient_name)

@app.get("/api/points")
def get_points(patient_name: str = "张三"):
    return {
        "patient_points": database.get_points(patient_name),
        "teacher_points": database.get_points("李老师")
    }