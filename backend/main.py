from fastapi import FastAPI, UploadFile, File, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel
from datetime import datetime
import lunardate
import cnlunar
import database
import agent
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
    teacher_name: str
    content: str
    data_type: str

class DraftUpdate(BaseModel):
    content: str

class SignInput(BaseModel):
    final_plan: str
    final_content: str = ""

class HomeworkInput(BaseModel):
    patient_name: str
    teacher_name: str
    task: str
    detail: str

class ProfileInput(BaseModel):
    patient_name: str
    gender: str
    birth_date: str
    birth_time: str
    birth_place: str
    location: str

class AddPatientInput(BaseModel):
    name: str
    guardian_name: str
    relation: str
    gender: str
    birth_date: str
    birth_time: str
    birth_place: str
    location: str

class TeacherLinkInput(BaseModel):
    patient_name: str
    teacher_name: str

def build_draft_template(patient_name, content_desc, past_content):
    lines = [
        "【中医病历草案】",
        "学生姓名：" + patient_name,
        "就诊时间：" + datetime.now().strftime('%Y年%m月%d日'),
        "",
        "【主诉（学生原话）】",
        content_desc,
        "",
        "【既往病历参考】",
        past_content,
        "",
        "【待老师补充】",
        "- 舌象：",
        "- 脉象：",
        "- 辨证：",
        "- 施治方案：",
    ]
    return "\n".join(lines)

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

@app.get("/api/teachers")
def get_teachers():
    return database.get_teachers()

@app.get("/api/patient-teachers")
def get_patient_teachers(patient_name: str):
    return database.get_patient_teachers(patient_name)

@app.get("/api/teacher-patients")
def get_teacher_patients(teacher_name: str):
    # 【第44天修改】返回学生列表 + 状态标记
    students = database.get_teacher_patients(teacher_name)
    result = []
    for s in students:
        status = database.get_student_status(s["name"])
        result.append({
            "name": s["name"],
            "points": s["points"],
            "last_active_at": s["last_active_at"],
            "status_label": status["label"],
            "status_color": status["color"],
        })
    return result

@app.post("/api/patient-teachers")
def add_patient_teacher(input_data: TeacherLinkInput):
    return database.add_patient_teacher(input_data.patient_name, input_data.teacher_name)

@app.delete("/api/patient-teachers")
def remove_patient_teacher(patient_name: str, teacher_name: str):
    return database.remove_patient_teacher(patient_name, teacher_name)

@app.get("/api/patients")
def get_patients(guardian_name: str = None):
    return database.get_patients(guardian_name)

@app.post("/api/patients/add")
def add_patient(input_data: AddPatientInput):
    database.add_patient(input_data.name, input_data.guardian_name, input_data.relation,
                         input_data.gender, input_data.birth_date, input_data.birth_time,
                         input_data.birth_place, input_data.location)
    return {"message": "亲友档案添加成功"}


class TeacherAddStudentInput(BaseModel):
    teacher_name: str
    student_name: str


@app.post("/api/teacher/add-student")
def teacher_add_student(input_data: TeacherAddStudentInput):
    return database.teacher_add_student(input_data.teacher_name, input_data.student_name)

@app.delete("/api/patients/{name}")
def delete_patient(name: str):
    database.delete_patient(name)
    return {"message": "亲友已删除"}

@app.get("/api/patient-profile")
def get_patient_profile(patient_name: str):
    profile = database.get_patient_profile(patient_name)
    if profile and profile["birth_date"]:
        try:
            time_str = profile["birth_time"] if profile["birth_time"] else "00:00"
            birth_dt = datetime.strptime(f"{profile['birth_date']} {time_str}", "%Y-%m-%d %H:%M")
            lunar_obj = cnlunar.Lunar(birth_dt, godType='8char')
            profile["bazi"] = f"{lunar_obj.year8Char} {lunar_obj.month8Char} {lunar_obj.day8Char} {lunar_obj.twohour8Char}"
            wuxing_str = "五行推算暂不可用"
            if hasattr(lunar_obj, 'baziFiveElements') and lunar_obj.baziFiveElements:
                elems = lunar_obj.baziFiveElements
                if isinstance(elems, dict):
                    wuxing_str = " ".join([f"{k}:{v}" for k, v in elems.items()])
                else:
                    wuxing_str = str(elems)
            else:
                bazi_chars = [lunar_obj.year8Char[0], lunar_obj.month8Char[0], lunar_obj.day8Char[0], lunar_obj.twohour8Char[0]]
                wuxing_map = {'甲':'木','乙':'木','丙':'火','丁':'火','戊':'土','己':'土','庚':'金','辛':'金','壬':'水','癸':'水'}
                counts = {"木":0, "火":0, "土":0, "金":0, "水":0}
                for c in bazi_chars:
                    if c in wuxing_map:
                        counts[wuxing_map[c]] += 1
                wuxing_str = " ".join([f"{k}:{v}" for k, v in counts.items()])
            profile["wuxing"] = wuxing_str
        except Exception:
            profile["bazi"] = "八字推算失败"
            profile["wuxing"] = "五行推算失败"
    else:
        profile["bazi"] = "缺少出生日期，无法推算八字"
        profile["wuxing"] = "缺少出生日期，无法推算五行"
    return profile

@app.post("/api/patient-profile")
def save_patient_profile(input_data: ProfileInput):
    database.save_patient_profile(input_data.patient_name, input_data.gender, input_data.birth_date,
                                  input_data.birth_time, input_data.birth_place, input_data.location)
    return {"message": "档案保存成功"}

@app.get("/api/health-trend")
def get_health_trend(patient_name: str):
    profile = database.get_patient_profile(patient_name)
    if not profile or not profile["birth_date"]:
        return {"error": "缺少出生日期，无法推算"}

    time_str = profile["birth_time"] if profile["birth_time"] else "00:00"
    birth_dt = datetime.strptime(f"{profile['birth_date']} {time_str}", "%Y-%m-%d %H:%M")
    lunar_obj = cnlunar.Lunar(birth_dt, godType='8char')

    tiangan_wuxing = {'甲':'木','乙':'木','丙':'火','丁':'火','戊':'土','己':'土','庚':'金','辛':'金','壬':'水','癸':'水'}
    dizhi_wuxing = {'子':'水','丑':'土','寅':'木','卯':'木','辰':'土','巳':'火','午':'火','未':'土','申':'金','酉':'金','戌':'土','亥':'水'}
    yang_gan = ['甲','丙','戊','庚','壬']
    yin_gan = ['乙','丁','己','辛','癸']
    yang_zhi = ['子','寅','辰','午','申','戌']
    yin_zhi = ['丑','卯','巳','未','酉','亥']

    bazi = [lunar_obj.year8Char, lunar_obj.month8Char, lunar_obj.day8Char, lunar_obj.twohour8Char]

    counts = {"木": 0, "火": 0, "土": 0, "金": 0, "水": 0}
    yang_count = 0
    yin_count = 0

    for pillar in bazi:
        for char in pillar:
            if char in tiangan_wuxing:
                counts[tiangan_wuxing[char]] += 1
                if char in yang_gan: yang_count += 1
                if char in yin_gan: yin_count += 1
            if char in dizhi_wuxing:
                counts[dizhi_wuxing[char]] += 1
                if char in yang_zhi: yang_count += 1
                if char in yin_zhi: yin_count += 1

    weakest = min(counts, key=counts.get)
    strongest = max(counts, key=counts.get)

    wuxing_organ = {"木": "肝胆", "火": "心小肠", "土": "脾胃", "金": "肺大肠", "水": "肾膀胱"}
    wuxing_zang = {"木": "肝", "火": "心", "土": "脾", "金": "肺", "水": "肾"}

    if counts[weakest] == 0:
        tendency = f"{wuxing_organ[weakest]}系统先天偏虚，建议重点养护{wuxing_zang[weakest]}"
    elif counts[strongest] >= 3:
        tendency = f"{wuxing_organ[strongest]}系统先天偏旺，注意疏导{wuxing_zang[strongest]}"
    else:
        tendency = "五行相对平衡，保持日常养护即可"

    if yang_count > yin_count + 1:
        yinyang = "偏阳体质"
    elif yin_count > yang_count + 1:
        yinyang = "偏阴体质"
    else:
        yinyang = "阴阳相对平衡"

    return {
        "bazi": " ".join(bazi),
        "counts": counts,
        "weakest": weakest,
        "strongest": strongest,
        "tendency": tendency,
        "yinyang": yinyang,
        "yang_count": yang_count,
        "yin_count": yin_count,
    }

@app.get("/api/daily-advice")
def get_daily_advice(patient_name: str):
    profile = database.get_patient_profile(patient_name)

    now = datetime.now()
    lunar_obj = cnlunar.Lunar(now, godType='8char')
    today_term = lunar_obj.todaySolarTerms or "平气"
    if today_term == "无":
        today_term = "平气"

    term_advice = {
        "立春": {"eat": "韭菜、豆芽、香椿", "avoid": "生冷、油腻", "wear": "不宜过早减衣"},
        "惊蛰": {"eat": "梨、菠菜、山药", "avoid": "辛辣、暴怒", "wear": "注意防风"},
        "清明": {"eat": "荠菜、香椿、青团", "avoid": "发物、海鲜", "wear": "早晚添衣"},
        "谷雨": {"eat": "薏米、赤小豆、冬瓜", "avoid": "甜腻、久坐", "wear": "注意祛湿"},
        "立夏": {"eat": "绿豆、苦瓜、莲子", "avoid": "大热、暴晒", "wear": "轻薄透气"},
        "小满": {"eat": "冬瓜、丝瓜、绿豆汤", "avoid": "寒凉冰饮", "wear": "勤换衣"},
        "芒种": {"eat": "青梅、薏米、西瓜", "avoid": "甜食、熬夜", "wear": "棉麻为宜"},
        "夏至": {"eat": "苦瓜、莲子、绿豆", "avoid": "贪凉、冷饮", "wear": "注意遮阳"},
        "小暑": {"eat": "冬瓜、丝瓜、荷叶粥", "avoid": "烈酒、辛辣", "wear": "透气散热"},
        "大暑": {"eat": "绿豆、莲子、薏米", "avoid": "大汗、贪凉", "wear": "防晒防暑"},
        "立秋": {"eat": "百合、银耳、莲藕", "avoid": "辛辣、燥热", "wear": "早晚添衣"},
        "处暑": {"eat": "梨、蜂蜜、银耳", "avoid": "燥热、熬夜", "wear": "防秋燥"},
        "白露": {"eat": "银耳、百合、雪梨、山药", "avoid": "辛辣、燥热、凉性瓜果", "wear": "早晚添衣、护住肚脐"},
        "秋分": {"eat": "莲藕、银耳、芝麻", "avoid": "辛辣、熬夜", "wear": "昼夜温差大，添衣"},
        "寒露": {"eat": "芝麻、核桃、红枣", "avoid": "寒凉、生冷", "wear": "注意足部保暖"},
        "霜降": {"eat": "萝卜、栗子、山药", "avoid": "生冷、久坐", "wear": "护膝护脚"},
        "立冬": {"eat": "羊肉、核桃、黑芝麻", "avoid": "寒凉、过咸", "wear": "保暖护肾"},
        "小雪": {"eat": "羊肉、红枣、黑豆", "avoid": "生冷、熬夜", "wear": "厚衣厚袜"},
        "大雪": {"eat": "黑豆、核桃、山药", "avoid": "寒凉、大汗", "wear": "严冬保暖"},
        "冬至": {"eat": "饺子、羊肉、枸杞", "avoid": "寒凉、久坐", "wear": "护住头颈"},
        "小寒": {"eat": "红枣、桂圆、羊肉", "avoid": "生冷、烈酒", "wear": "全副武装"},
        "大寒": {"eat": "羊肉、核桃、黑芝麻", "avoid": "寒凉、大汗", "wear": "防寒保暖"},
    }

    base = term_advice.get(today_term, {"eat": "当季新鲜食材", "avoid": "过度油腻", "wear": "顺应天气增减衣物"})

    wuxing_supplement = {
        "木": {"eat": "绿色蔬菜、枸杞、菊花茶", "avoid": "久视屏幕", "wear": "早睡养肝"},
        "火": {"eat": "莲子、百合、苦瓜", "avoid": "熬夜、辛辣", "wear": "静心养神"},
        "土": {"eat": "小米、山药、南瓜", "avoid": "生冷、思虑过度", "wear": "三餐规律"},
        "金": {"eat": "银耳、雪梨、百合", "avoid": "悲伤、燥热", "wear": "润肺养气"},
        "水": {"eat": "黑豆、核桃、黑芝麻、海带", "avoid": "寒凉、熬夜", "wear": "护腰养肾"},
    }

    wuxing_tip = {"eat": "均衡饮食", "avoid": "寒凉生冷", "wear": "注意保暖"}
    tendency_note = ""
    if profile and profile.get("birth_date"):
        time_str = profile["birth_time"] if profile["birth_time"] else "00:00"
        try:
            birth_dt = datetime.strptime(f"{profile['birth_date']} {time_str}", "%Y-%m-%d %H:%M")
            lunar_birth = cnlunar.Lunar(birth_dt, godType='8char')
            tiangan_wuxing = {'甲':'木','乙':'木','丙':'火','丁':'火','戊':'土','己':'土','庚':'金','辛':'金','壬':'水','癸':'水'}
            dizhi_wuxing = {'子':'水','丑':'土','寅':'木','卯':'木','辰':'土','巳':'火','午':'火','未':'土','申':'金','酉':'金','戌':'土','亥':'水'}
            bazi = [lunar_birth.year8Char, lunar_birth.month8Char, lunar_birth.day8Char, lunar_birth.twohour8Char]
            counts = {"木": 0, "火": 0, "土": 0, "金": 0, "水": 0}
            for pillar in bazi:
                for char in pillar:
                    if char in tiangan_wuxing:
                        counts[tiangan_wuxing[char]] += 1
                    if char in dizhi_wuxing:
                        counts[dizhi_wuxing[char]] += 1
            weakest = min(counts, key=counts.get)
            wuxing_tip = wuxing_supplement[weakest]
            tendency_note = f"您的五行中「{weakest}」最弱，今日特别照顾"
        except Exception:
            pass

    return {
        "solar_term": today_term,
        "date": now.strftime("%Y年%m月%d日"),
        "eat": base["eat"] + "，另可补充：" + wuxing_tip["eat"],
        "avoid": base["avoid"] + "，" + wuxing_tip["avoid"],
        "wear": base["wear"] + "；" + wuxing_tip["wear"],
        "tendency_note": tendency_note,
    }

@app.get("/api/role-data")
def get_role_data(role: str, patient_name: str = "张三", teacher_name: str = "李老师"):
    hw = database.get_homework(patient_name, teacher_name)

    if role == "李老师":
        if not hw:
            return {"role_type": "teacher", "name": teacher_name, "task": "待审核", "detail": f"{patient_name}尚未打卡。"}
        if hw["status"] == "pending":
            return {"role_type": "teacher", "name": teacher_name, "task": "待审核", "detail": f"{patient_name}尚未打卡。"}
        elif hw["status"] == "checked_in":
            return {"role_type": "teacher", "name": teacher_name, "task": "待审核", "detail": f"{patient_name}：{hw['task']}（已打卡，待签字确认）"}
        else:
            return {"role_type": "teacher", "name": teacher_name, "task": "已审核", "detail": f"{patient_name}的作业已签字确认。"}
    elif role in ["学生", "学生智能体", "患者", "患者智能体"]:
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
    database.create_homework(input_data.patient_name, input_data.teacher_name, input_data.task, input_data.detail)
    return {"message": "作业已布置"}

@app.post("/api/check-in")
def check_in(patient_name: str = "张三", teacher_name: str = "李老师"):
    database.update_homework_status(patient_name, teacher_name, "checked_in")
    database.add_points(patient_name, 10)
    return {"message": "打卡成功"}

@app.post("/api/approve")
def approve(patient_name: str = "张三", teacher_name: str = "李老师"):
    database.update_homework_status(patient_name, teacher_name, "approved")
    return {"message": "审核通过"}

# 【第41天新增】患者端智能体：整理患者原话（带标点、结构化）
class PatientStructurizeInput(BaseModel):
    patient_name: str
    raw_text: str

@app.post("/api/patient-structurize")
def patient_structurize(input_data: PatientStructurizeInput):
    result = agent.structurize_patient_input(input_data.raw_text)
    return {"structured": result}

# ============ 【第80天新增】学生智能体「十问歌」主动追问（面诊前准备） ============
# 两个接口是配套的一问一答：ask_next_question 只负责「下一问是什么」，save_intake 负责「问完之后落库」。
# 两者都只走 agent.py 里现成的 LLM（deepseek-chat），不新增任何依赖、不改数据库表定义。

class AskNextQuestionInput(BaseModel):
    patient_name: str
    current_answers: str = ""   # 学生已回答的内容；第一次为空字符串（不传也当空串，前端首次调用更省事）


class SaveIntakeInput(BaseModel):
    patient_name: str
    teacher_name: str
    answers: str


@app.post("/api/agent/ask_next_question")
def api_ask_next_question(input_data: AskNextQuestionInput):
    """【改动1】按「十问歌」返回下一个该问的问题。

    请求体：{"patient_name": "张三", "current_answers": "问：…\\n答：…"}（第一次 current_answers 为空串）
    响应体：{"question": "一句口语化的问句", "done": false}；十问都覆盖时 {"question": "", "done": true}
    越界防护：问题里不会出现诊断、辨证、开方、建议；一次只返回一个问题。
    """
    return agent.ask_next_question(input_data.patient_name, input_data.current_answers)


@app.post("/api/agent/save_intake")
def api_save_intake(input_data: SaveIntakeInput):
    """【改动2】把「面诊前准备」的问答记录整理成结构化文本，写进 complaints（学生陈述表）。

    请求体：{"patient_name": "张三", "teacher_name": "李老师", "answers": "问：…\\n答：…"}
    响应体：{"ok": true}；整理只做格式化（不推理、不补充），status 固定 'pending'。
    """
    agent.save_intake(input_data.patient_name, input_data.teacher_name, input_data.answers)
    return {"ok": True}


# 【第42天新增】老师端现场口述整理
class TeacherStructurizeInput(BaseModel):
    raw_text: str

@app.post("/api/teacher-structurize")
def teacher_structurize(input_data: TeacherStructurizeInput):
    result = agent.structurize_teacher_note(input_data.raw_text)
    return {"structured": result}

# 【第68天新增】老师端录音转写智能体清洗：录音停止后，原始转写先在这里去噪 + 提炼 + 结构化，
# 前端拿到 cleaned_text 后再追加到“现场辅助记录”文本框（老师点“追加到病历”才进病历草案）。
class CleanTranscriptInput(BaseModel):
    raw_text: str

@app.post("/api/agent/clean_transcript")
def clean_transcript(input_data: CleanTranscriptInput):
    """清洗录音转写文本；清洗失败（异常）时降级返回原文，不阻塞前端。"""
    try:
        cleaned_text = agent.clean_transcript(input_data.raw_text)
    except Exception:
        cleaned_text = input_data.raw_text
    return {"cleaned_text": cleaned_text}

# 【第76天新增】老师端「辨证施治方案」语音输入专用清洗：
# 医嘱（剂量/时间/煎法/火候/服法/忌口）没有病历五段式结构，复用 clean_transcript 会被套错结构
# 甚至被当闲聊删掉，所以单独走本接口——只去噪、不改写、不分节，输出一段连贯医嘱文本。
class CleanPlanInput(BaseModel):
    raw_text: str

@app.post("/api/agent/clean_plan")
def clean_plan(input_data: CleanPlanInput):
    """清洗施治方案口述转写；清洗失败（异常）时降级返回原文，不阻塞前端。"""
    try:
        cleaned_text = agent.clean_plan(input_data.raw_text)
    except Exception:
        cleaned_text = input_data.raw_text
    return {"cleaned_text": cleaned_text}

# 【第75天新增】施治方案模板记忆（老师维度）：
# 老师在“辨证施治方案”里写的常用内容记一条模板，下次选中的学生施治方案为空时前端自动套用；
# 老师点“保存病历修改”或“预览完整病历”时，前端把当前内容 POST 回来覆盖这条模板。
class PlanTemplateInput(BaseModel):
    teacher_name: str
    content: str

@app.get("/api/plan_template")
def get_plan_template(teacher_name: str):
    """取该老师的施治方案模板；没有记录（或内容为空）时返回空串。"""
    return {"content": database.get_plan_template(teacher_name)}

@app.post("/api/plan_template")
def save_plan_template(input_data: PlanTemplateInput):
    """保存 / 覆盖该老师的施治方案模板（teacher_name 唯一），返回 {\"ok\": true}。"""
    database.save_plan_template(input_data.teacher_name, input_data.content)
    return {"ok": True}

@app.post("/api/transcribe")
def transcribe(input_data: TranscriptionInput):
    database.insert_transcription(input_data.patient_name, input_data.teacher_name, input_data.content, input_data.data_type)

    transcripts = database.get_transcriptions(input_data.patient_name, input_data.teacher_name)
    if not transcripts:
        return {"message": "转述失败"}
    latest = transcripts[0]

    patient_name = latest['patient_name']
    teacher_name = latest['teacher_name']
    past_records = database.get_patient_records(patient_name, teacher_name)
    past_content = "\n".join([f"- {r['final_plan']}" for r in past_records]) if past_records else "暂无过往病历"

    # 【第41天修复】学生端已做过结构化，后端不再调 structurize，直接交给老师智能体
    content_desc = str(latest['content'])

    visit_date = datetime.now().strftime('%Y年%m月%d日')
    template = agent.generate_medical_draft(patient_name, visit_date, content_desc, past_content)
    database.insert_draft(latest['id'], patient_name, teacher_name, template.strip())

    return {"message": "转述成功，病历草案已自动生成"}

@app.post("/api/upload")
async def upload_image(patient_name: str = "张三", teacher_name: str = "李老师", file: UploadFile = File(...)):
    ext = os.path.splitext(file.filename)[1] if file.filename else ".jpg"
    unique_name = f"{uuid.uuid4().hex}{ext}"
    file_path = os.path.join(UPLOAD_DIR, unique_name)
    with open(file_path, "wb") as buffer:
        shutil.copyfileobj(file.file, buffer)
    file_url = f"/uploads/{unique_name}"
    database.insert_transcription(patient_name, teacher_name, file_url, "image")

    transcripts = database.get_transcriptions(patient_name, teacher_name)
    if transcripts:
        latest = transcripts[0]
        past_records = database.get_patient_records(patient_name, teacher_name)
        past_content = "\n".join([f"- {r['final_plan']}" for r in past_records]) if past_records else "暂无过往病历"
        content_desc = "[学生上传了图片：" + file_url + "]"
        visit_date = datetime.now().strftime('%Y年%m月%d日')
        template = agent.generate_medical_draft(patient_name, visit_date, content_desc, past_content)
        database.insert_draft(latest['id'], patient_name, teacher_name, template.strip())

    return {"message": "图片转述成功", "url": file_url}

@app.post("/api/upload-temp")
async def upload_temp(file: UploadFile = File(...)):
    ext = os.path.splitext(file.filename)[1] if file.filename else ".jpg"
    unique_name = f"{uuid.uuid4().hex}{ext}"
    file_path = os.path.join(UPLOAD_DIR, unique_name)
    with open(file_path, "wb") as buffer:
        shutil.copyfileobj(file.file, buffer)
    file_url = f"/uploads/{unique_name}"
    return {"message": "临时上传成功", "url": file_url}

@app.post("/api/upload-audio")
async def upload_audio(file: UploadFile = File(...)):
    ext = os.path.splitext(file.filename)[1] if file.filename else ".webm"
    unique_name = f"audio_{uuid.uuid4().hex}{ext}"
    file_path = os.path.join(UPLOAD_DIR, unique_name)
    with open(file_path, "wb") as buffer:
        shutil.copyfileobj(file.file, buffer)
    return {"url": f"/uploads/{unique_name}"}

@app.get("/api/transcriptions")
def get_transcriptions(patient_name: str = None, teacher_name: str = None):
    return database.get_transcriptions(patient_name, teacher_name)

@app.post("/api/generate-draft")
def generate_draft(transcript_id: int):
    transcripts = database.get_transcriptions()
    transcript = next((t for t in transcripts if t["id"] == transcript_id), None)
    if not transcript:
        return {"error": "找不到该转述"}
    patient_name = transcript['patient_name']
    teacher_name = transcript['teacher_name']
    past_records = database.get_patient_records(patient_name, teacher_name)
    past_content = "\n".join([f"- {r['final_plan']}" for r in past_records]) if past_records else "暂无过往病历"
    if transcript['data_type'] == 'image':
        content_desc = "[学生上传了图片：" + str(transcript['content']) + "]"
    else:
        content_desc = str(transcript['content'])
    template = build_draft_template(patient_name, content_desc, past_content)
    draft_id = database.insert_draft(transcript_id, patient_name, teacher_name, template.strip())
    return {"message": "病历草案生成成功", "draft_id": draft_id}

@app.get("/api/drafts")
def get_drafts(teacher_name: str = None):
    return database.get_drafts(teacher_name)

@app.put("/api/drafts/{draft_id}")
def update_draft(draft_id: int, update_data: DraftUpdate):
    database.update_draft_content(draft_id, update_data.content)
    return {"message": "病历已更新"}

@app.post("/api/drafts/{draft_id}/sign")
def sign_draft_endpoint(draft_id: int, input_data: SignInput):
    # 【第45天修改】签字前，先提取音频URL并删除物理文件（音频转文字已确认，即销毁）
    import re
    conn = database.get_connection()
    draft = conn.execute("SELECT content FROM drafts WHERE id = ?", (draft_id,)).fetchone()
    conn.close()
    if not draft:
        return {"error": "找不到该草案"}

    audio_urls = re.findall(r'/uploads/audio_[a-zA-Z0-9._-]+', draft["content"])
    for url in audio_urls:
        filename = url.replace('/uploads/', '')
        file_path = os.path.join(UPLOAD_DIR, filename)
        if os.path.exists(file_path):
            try:
                os.remove(file_path)
            except Exception:
                pass

    # 签字
    patient_name = database.sign_draft(draft_id, input_data.final_plan, input_data.final_content)
    if not patient_name:
        return {"error": "找不到该病历"}
    database.transfer_points(patient_name, "李老师", 50)
    return {"message": "签字成功，完整病历已归档，音频已销毁，积分已支付"}

# ---------- 【第46天新增】病历标签 ----------
class TagInput(BaseModel):
    record_id: int
    teacher_name: str
    tags: list  # [{"tag_type": "部位", "tag_value": "舌苔"}, ...]

@app.post("/api/tags")
def add_tags(input_data: TagInput):
    for tag in input_data.tags:
        database.insert_tag(input_data.record_id, input_data.teacher_name, tag["tag_type"], tag["tag_value"])
    return {"message": "标签已保存"}

@app.get("/api/tags")
def get_tags(record_id: int):
    return database.get_tags_for_record(record_id)

@app.get("/api/tags-summary")
def get_tags_summary(teacher_name: str):
    return database.get_teacher_tags_summary(teacher_name)

@app.get("/api/patient-records")
def get_patient_records(patient_name: str = None, teacher_name: str = None):
    return database.get_patient_records(patient_name, teacher_name)
# ---------- 邀请码 ----------
class InviteInput(BaseModel):
    teacher_name: str

class AcceptInviteInput(BaseModel):
    code: str
    student_name: str

@app.post("/api/invites")
def create_invite(input_data: InviteInput):
    import random
    import string
    code = "ZHI-" + "".join(random.choices(string.ascii_uppercase + string.digits, k=6))
    database.create_invite(code, input_data.teacher_name)
    return {"code": code, "message": "邀请码已生成"}

@app.get("/api/invites")
def get_invites(teacher_name: str):
    return database.get_invites(teacher_name)

@app.post("/api/invites/accept")
def accept_invite(input_data: AcceptInviteInput):
    return database.accept_invite(input_data.code, input_data.student_name)

# ---------- 【第48天新增】老师工作时间 ----------
class TeacherSettingsInput(BaseModel):
    teacher_name: str
    work_days: str
    work_hours: str

@app.get("/api/teacher-settings")
def get_teacher_settings(teacher_name: str):
    return database.get_teacher_settings(teacher_name)

@app.post("/api/teacher-settings")
def save_teacher_settings(input_data: TeacherSettingsInput):
    return database.save_teacher_settings(input_data.teacher_name, input_data.work_days, input_data.work_hours)

# ---------- 【第48天扩展】按天的工作时间 ----------
class TeacherScheduleInput(BaseModel):
    teacher_name: str
    schedule: dict

@app.get("/api/teacher-schedule")
def get_teacher_schedule(teacher_name: str):
    return database.get_teacher_schedule(teacher_name)

@app.post("/api/teacher-schedule")
# ---------- 【第49天新增】节假日 ----------
class HolidaysInput(BaseModel):
    teacher_name: str
    holidays: list

@app.get("/api/teacher-holidays")
def get_teacher_holidays(teacher_name: str):
    return database.get_teacher_holidays(teacher_name)

@app.post("/api/teacher-holidays")
def save_teacher_holidays(input_data: HolidaysInput):
    return database.save_teacher_holidays(input_data.teacher_name, input_data.holidays)

def save_teacher_schedule(input_data: TeacherScheduleInput):
    return database.save_teacher_schedule(input_data.teacher_name, input_data.schedule)

# ---------- 【第48天扩展】按天的工作时间 ----------
class TeacherScheduleInput(BaseModel):
    teacher_name: str
    schedule: dict

@app.get("/api/teacher-schedule")
def get_teacher_schedule(teacher_name: str):
    return database.get_teacher_schedule(teacher_name)

@app.post("/api/teacher-schedule")
def save_teacher_schedule(input_data: TeacherScheduleInput):
    return database.save_teacher_schedule(input_data.teacher_name, input_data.schedule)

# ---------- 【第47天新增】预约 ----------
class AppointmentInput(BaseModel):
    patient_name: str
    teacher_name: str
    initiator: str
    scheduled_date: str
    scheduled_time: str
    reason: str

@app.post("/api/appointments")
def create_appointment(input_data: AppointmentInput):
    return database.create_appointment(
        input_data.patient_name, input_data.teacher_name, input_data.initiator,
        input_data.scheduled_date, input_data.scheduled_time, input_data.reason
    )

@app.get("/api/appointments")
def get_appointments(
    patient_name: str = None,
    teacher_name: str = None,
    start_date: str = None,
    end_date: str = None
):
    return database.get_appointments(patient_name, teacher_name, start_date, end_date)

@app.get("/api/appointments/calendar")
def get_appointments_calendar(teacher_name: str):
    """【第49天】返回未来 7 天 × 所有时段 的预约情况，供可视化网格用"""
    from datetime import timedelta
    today = datetime.now()
    end = today + timedelta(days=7)
    start_str = today.strftime("%Y-%m-%d")
    end_str = end.strftime("%Y-%m-%d")

    # 该老师的排班
    schedule = database.get_teacher_schedule(teacher_name)
    holidays = database.get_teacher_holidays(teacher_name)

    # 未来 7 天该老师的所有预约
    appts = database.get_appointments(teacher_name=teacher_name, start_date=start_str, end_date=end_str)

    # 生成 7 天数据
    days = []
    for i in range(7):
        d = today + timedelta(days=i)
        date_str = d.strftime("%Y-%m-%d")
        day_of_week = d.weekday()  # 0=周一...6=周日
        # 注意：Python weekday 与 JS getDay 不同，转换一下
        js_day = (day_of_week + 1) % 7
        day_key = str(js_day)

        slots_available = schedule.get(day_key, []) if date_str not in holidays else []

        # 该天已被预约的时段
        booked = {}
        for a in appts:
            if a["scheduled_date"] == date_str and a["status"] != "cancelled":
                booked[a["scheduled_time"]] = {
                    "patient_name": a["patient_name"],
                    "status": a["status"],
                    "id": a["id"]
                }

        days.append({
            "date": date_str,
            "weekday": js_day,
            "is_holiday": date_str in holidays,
            "slots": slots_available,
            "booked": booked
        })

    return {"teacher_name": teacher_name, "days": days, "holidays": holidays}

@app.post("/api/appointments/{appt_id}/confirm")
def confirm_appointment(appt_id: int):
    return database.update_appointment_status(appt_id, "confirmed")

@app.post("/api/appointments/{appt_id}/cancel")
def cancel_appointment(appt_id: int):
    return database.update_appointment_status(appt_id, "cancelled")

@app.get("/api/points")
def get_points(patient_name: str = "张三"):
    return {
        "patient_points": database.get_points(patient_name),
        "teacher_points": database.get_points("李老师")
    }
# ============ Pydantic 模型：中药材库存 ============

class HerbInput(BaseModel):
    teacher_name: str
    herb_name: str
    stock_amount: float = 0
    unit: str = "克"
    warn_threshold: float = 50


class HerbAdjustInput(BaseModel):
    delta: float


class HerbBatchDeductInput(BaseModel):
    teacher_name: str
    items: list  # [{herb_name: str, amount: float}]


# ============ 接口：中药材库存 ============

@app.get("/api/herbs")
def api_get_herbs(teacher_name: str):
    return database.get_herbs(teacher_name)


@app.get("/api/herbs/low")
def api_get_low_herbs(teacher_name: str):
    return database.get_low_herbs(teacher_name)


@app.post("/api/herbs")
def api_upsert_herb(data: HerbInput):
    herb = database.upsert_herb(data.teacher_name, data.herb_name, data.stock_amount, data.unit, data.warn_threshold)
    return {"message": "已保存", "herb": herb}


@app.post("/api/herbs/batch-deduct")
def api_batch_deduct_herbs(data: HerbBatchDeductInput):
    result = database.batch_deduct_herbs(data.teacher_name, data.items)
    if not result["success"]:
        return {"message": "扣减失败，库存不足", "failed_herb": result["failed_herb"]}
    return {"message": "批量扣减成功", "failed_herb": None}


@app.post("/api/herbs/{herb_id}/adjust")
def api_adjust_herb(herb_id: int, data: HerbAdjustInput):
    try:
        herb = database.adjust_herb(herb_id, data.delta)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    if herb is None:
        raise HTTPException(status_code=404, detail="药材不存在")
    return {"message": "已调整", "herb": herb}


@app.delete("/api/herbs/{herb_id}")
def api_delete_herb(herb_id: int):
    ok = database.delete_herb(herb_id)
    if not ok:
        raise HTTPException(status_code=404, detail="药材不存在")
    return {"message": "已删除"}


# ============ Pydantic 模型：开方 ============

class PrescriptionItem(BaseModel):
    """【第74天新增 / 开方九宫格改造】一味药材：药材名 + 克数 + 君臣佐使 + 煎法。

    - role：君 / 臣 / 佐 / 使，空串 '' = 未标注；
    - cooking_method：常规 / 先煎 / 后下 / 包煎 / 烊化 / 另煎 / 冲服，空串 '' = 未指定；
    - 两个字段都有默认值，老调用方（只传 herb_name / amount / unit）无需改动。
    """
    herb_name: str
    amount: float
    unit: str = "克"
    role: str = ""              # 【第74天新增】君臣佐使
    cooking_method: str = ""    # 【第74天新增】煎法


class PrescriptionInput(BaseModel):
    teacher_name: str
    patient_name: str = ""
    items: list[PrescriptionItem]  # [{herb_name: str, amount: float, unit: str, role: str, cooking_method: str}]
    note: str = ""
    is_remote: bool = False  # 【第53天新增】True=远程诊疗（学生自采，不扣库存）；默认当面诊疗（扣库存）


# ============ 接口：开方（中药材首字联想 + 药方结构化存储） ============

@app.get("/api/herbs/search")
def api_search_herbs(teacher_name: str, prefix: str = ""):
    """药材首字联想：prefix 为空时返回空数组。"""
    return database.search_herbs_by_prefix(teacher_name, prefix)


@app.post("/api/prescriptions")
def api_create_prescription(data: PrescriptionInput):
    """【第53天新增】当面诊疗（默认）先扣库存，扣失败返回 {"error": ...} 且不保存；远程诊疗只存药方。

    【第74天新增 / 开方九宫格改造】每条药材额外接收 role（君臣佐使）与 cooking_method（煎法）：
    exclude_unset=True 只把「客户端真正传了的字段」交给数据库 —— 不传这两个字段的老调用方
    （以及历史数据格式）行为完全不变，传了就按白名单清洗后落进 items_json。
    """
    items = [item.model_dump(exclude_unset=True) for item in data.items]
    return database.create_prescription(data.teacher_name, data.patient_name, items, data.note, data.is_remote)


@app.get("/api/prescriptions")
def api_get_prescriptions(teacher_name: str, patient_name: str = ""):
    return database.get_prescriptions(teacher_name, patient_name or None)


# ============ Pydantic 模型：老师智能体 ============

class AgentResolveInput(BaseModel):
    decision: str  # 'approved'（确认执行）或 'rejected'（忽略）


# ============ 接口：老师智能体（一期：沉默学生请示闭环） ============

class AgentScanInput(BaseModel):
    teacher_name: str = ""


@app.post("/api/agent/scan")
def api_agent_scan(data: AgentScanInput | None = None, teacher_name: str = ""):
    """【行政化 B3】统一扫描入口：一次扫完该老师名下学生的三类请示 ——
    沉默关怀（send_care_notice，B1 已有）+ 欠费预存（send_billing_notice）+ 复诊提醒（send_recall_notice），
    都写进同一张 agent_tasks（category='student'、task_type='request'、status='pending'）。

    请求体：{"teacher_name": "李老师"}；返回：{"ok": true, "created": N}（N = 本次新创建的任务数）。
    兼容旧调用：不接受请求体时仍认查询参数 ?teacher_name=，响应里保留 new_tasks（与 created 同值），
    这样前端「智能体工作台」和已有测试的老调用方式都不用改。
    """
    name = (data.teacher_name if data else "") or teacher_name
    if not name:
        raise HTTPException(status_code=400, detail="teacher_name 不能为空")
    created = agent.scan_student_requests(name)
    return {"ok": True, "created": created, "new_tasks": created}


@app.get("/api/agent/tasks")
def api_get_agent_tasks(teacher_name: str, status: str = "pending"):
    """老师智能体待办列表。"""
    return database.get_agent_tasks(teacher_name, status)


@app.post("/api/agent/tasks/{task_id}/resolve")
def api_resolve_agent_task(task_id: int, data: AgentResolveInput):
    """老师决策：确认执行 / 忽略。"""
    if data.decision not in ("approved", "rejected"):
        raise HTTPException(status_code=400, detail="decision 只能是 approved 或 rejected")
    result = database.resolve_agent_task(task_id, data.decision)
    if result is None:
        raise HTTPException(status_code=404, detail="任务不存在")
    return {"message": "已处理"}


# ============ 【行政化改造】任务表接口（设计文档 4 个接口） ============
# 说明：上面的 /api/agent/*（scan、tasks、tasks/{id}/resolve）是前端「智能体工作台」在用的老接口，
# 保持原样不动，避免改前端；这里按设计文档再提供一套更符合 REST 语义的资源路径：
#   GET  /api/agent_tasks            任务列表（含 request 请示 / report 汇报，可按 status 过滤）
#   POST /api/agent_tasks/approve    批准（status → approved + resolved_at + 日志）
#   POST /api/agent_tasks/reject     驳回（status → rejected + resolved_at + 日志）
#   GET  /api/agent_action_log       行动日志（倒序 + limit）
# 两套接口读写同一张表（agent_tasks / agent_action_log），不是两套数据。

class AgentTaskIdInput(BaseModel):
    task_id: int


@app.get("/api/agent_tasks")
def api_list_agent_tasks(teacher_name: str, status: str = ""):
    """该老师的智能体任务列表；status 不传（或传空串）= 返回全部。

    可选值按设计文档：pending / approved / rejected / done / undone。
    """
    return database.get_agent_tasks(teacher_name, status)


@app.post("/api/agent_tasks/approve")
def api_approve_agent_task(data: AgentTaskIdInput):
    """批准请示：status → approved、写 resolved_at、往 agent_action_log 记一条日志。"""
    result = database.resolve_agent_task(data.task_id, "approved")
    if result is None:
        raise HTTPException(status_code=404, detail="任务不存在")
    return {"ok": True}


@app.post("/api/agent_tasks/reject")
def api_reject_agent_task(data: AgentTaskIdInput):
    """驳回请示：status → rejected、写 resolved_at、往 agent_action_log 记一条日志。"""
    result = database.resolve_agent_task(data.task_id, "rejected")
    if result is None:
        raise HTTPException(status_code=404, detail="任务不存在")
    return {"ok": True}


@app.get("/api/agent_action_log")
def api_get_agent_action_log(teacher_name: str, limit: int = 20):
    """该老师的智能体行动日志，按 created_at 倒序，默认最多 20 条。"""
    return database.get_agent_action_log(teacher_name, limit)


# ============ Pydantic 模型：财务管理（预存 / 赠送 / 扣费） ============

class FinanceInput(BaseModel):
    username: str
    amount: int
    note: str = ""


# ============ 接口：财务管理（第65天新增，接前端"💰 财务管理"面板三个按钮） ============

@app.post("/api/finance/recharge")
def api_finance_recharge(data: FinanceInput):
    """预存（充值）：账户余额 +amount，记一条 type='recharge' 流水。"""
    if data.amount <= 0:
        raise HTTPException(status_code=400, detail="金额必须大于 0")
    return database.recharge_account(data.username, data.amount, data.note)


@app.post("/api/finance/gift")
def api_finance_gift(data: FinanceInput):
    """赠送：账户余额 +amount，记一条 type='gift' 流水。"""
    if data.amount <= 0:
        raise HTTPException(status_code=400, detail="金额必须大于 0")
    return database.gift_account(data.username, data.amount, data.note)


@app.post("/api/finance/deduct")
def api_finance_deduct(data: FinanceInput):
    """扣费：账户余额 -amount；余额不足返回 {ok: false, error: '余额不足'} 且不扣款。"""
    if data.amount <= 0:
        raise HTTPException(status_code=400, detail="金额必须大于 0")
    return database.deduct_account(data.username, data.amount, data.note)


@app.get("/api/finance/accounts")
def api_finance_accounts():
    """账户列表：role 由 username 是否存在于 teachers 表判断。"""
    return {"accounts": database.get_finance_accounts()}
