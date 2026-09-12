from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from datetime import datetime
import lunardate
import cnlunar
import database

app = FastAPI(title="zhiheng-tcm-backend")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)

database.init_db()

class TranscriptionInput(BaseModel):
    patient_name: str
    content: str
    data_type: str

class DraftUpdate(BaseModel):
    content: str

class SignInput(BaseModel):
    final_plan: str

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

@app.get("/api/role-data")
def get_role_data(role: str):
    hw = database.get_homework()
    if not hw:
        return {"role_type": "unknown", "name": role, "task": "暂无任务", "detail": "数据加载中..."}

    if role == "李老师":
        if hw["status"] == "pending":
            return {"role_type": "teacher", "name": "李老师", "task": "待审核", "detail": "患者尚未打卡。"}
        elif hw["status"] == "checked_in":
            return {"role_type": "teacher", "name": "李老师", "task": "待审核", "detail": f"{hw['patient_name']}：{hw['task']}（已打卡，待签字确认）"}
        else:
            return {"role_type": "teacher", "name": "李老师", "task": "已审核", "detail": f"{hw['patient_name']}的作业已签字确认。"}
    elif role == "患者张三":
        if hw["status"] == "pending":
            return {"role_type": "patient", "name": "张三", "task": hw["task"], "detail": hw["detail"]}
        elif hw["status"] == "checked_in":
            return {"role_type": "patient", "name": "张三", "task": hw["task"], "detail": "已打卡，等待老师签字确认。"}
        else:
            return {"role_type": "patient", "name": "张三", "task": hw["task"], "detail": "老师已签字确认，完成！"}
    return {"role_type": "unknown", "name": role, "task": "暂无任务", "detail": "数据加载中..."}

@app.post("/api/check-in")
def check_in():
    database.update_homework_status("checked_in")
    database.add_points("张三", 10) # 【第12天新增】患者打卡 +10 积分
    return {"message": "打卡成功"}

@app.post("/api/approve")
def approve():
    database.update_homework_status("approved")
    return {"message": "审核通过"}

@app.post("/api/transcribe")
def transcribe(input_data: TranscriptionInput):
    database.insert_transcription(input_data.patient_name, input_data.content, input_data.data_type)
    return {"message": "转述成功"}

@app.get("/api/transcriptions")
def get_transcriptions():
    return database.get_transcriptions()

@app.post("/api/generate-draft")
def generate_draft(transcript_id: int):
    transcripts = database.get_transcriptions()
    transcript = next((t for t in transcripts if t["id"] == transcript_id), None)
    if not transcript:
        return {"error": "找不到该转述"}

    patient_name = transcript['patient_name']
    past_records = database.get_patient_records(patient_name)
    past_content = "\n".join([f"- {r['content']}" for r in past_records]) if past_records else "暂无过往病历"

    template = f"""【{patient_name}过往病历】
{past_content}

【{patient_name}最新陈述】
{transcript['content']}

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
    result = database.sign_draft(draft_id, input_data.final_plan)
    if not result:
        return {"error": "找不到该病历"}
    # 【第12天新增】签字后，患者支付 50 积分学费给老师
    database.transfer_points("张三", "李老师", 50)
    return {"message": "签字确认成功，已归档至患者健康档案，学费已支付"}

@app.get("/api/patient-records")
def get_patient_records():
    return database.get_patient_records()

# 【第12天新增】获取积分接口
@app.get("/api/points")
def get_points():
    return {
        "patient_points": database.get_points("张三"),
        "teacher_points": database.get_points("李老师")
    }