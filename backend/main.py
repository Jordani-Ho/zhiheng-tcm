from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from datetime import datetime
import lunardate
import cnlunar

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
patient_records_db = []

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

    # 计算节气
    lunar_obj = cnlunar.Lunar(now, godType='8char')
    term_list = sorted(lunar_obj.thisYearSolarTermsDic.items(), key=lambda x: str(x[1]))
    today_str = now.strftime('%Y-%m-%d')
    
    prev_term = None
    next_term = None
    
    for name, date_val in term_list:
        date_str_val = str(date_val)[:10] 
        if date_str_val <= today_str:
            prev_term = (name, date_str_val)
        elif date_str_val > today_str and next_term is None:
            next_term = (name, date_str_val)

    # 【修改点1】组装提示语时，过滤掉“无”和空白
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
    past_records = [r for r in patient_records_db if r["patient_name"] == patient_name]
    past_content = "\n".join([f"- {r['content']}" for r in past_records]) if past_records else "暂无过往病历"

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

@app.post("/api/drafts/{draft_id}/sign")
def sign_draft(draft_id: int, input_data: SignInput):
    draft = next((d for d in drafts_db if d["id"] == draft_id), None)
    if not draft:
        return {"error": "找不到该病历"}
    
    patient_record = {
        "id": len(patient_records_db) + 1,
        "patient_name": draft["patient_name"],
        "content": input_data.final_plan,
        "doctor": "李老师"
    }
    patient_records_db.append(patient_record)
    drafts_db.remove(draft)
    
    return {"message": "签字确认成功，最终方案已归档至患者健康档案"}

@app.get("/api/patient-records")
def get_patient_records():
    return patient_records_db