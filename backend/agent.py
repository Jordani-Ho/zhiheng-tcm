import os
from dotenv import load_dotenv
from langchain_openai import ChatOpenAI
from langgraph.graph import StateGraph, END
from typing import TypedDict

load_dotenv()

# ============ LLM 初始化 ============
llm = ChatOpenAI(
    model="deepseek-chat",
    api_key=os.getenv("DEEPSEEK_API_KEY"),
    base_url="https://api.deepseek.com",
    temperature=0.1,
    timeout=30
)

# ============ 患者智能体 ============
class PatientState(TypedDict):
    raw_input: str
    data_type: str
    structured: str

PATIENT_PROMPT = (
    "你是一名中医问诊的【录音笔 + 整理员】。你唯一的任务是：把患者的原话整理成结构化的中医主诉。\n\n"
    "【绝对禁止】\n"
    "1. 不能做任何诊断、辨证、开方或推理判断\n"
    "2. 不能添加患者没说过的任何内容\n"
    "3. 不能修改患者的原意或替患者下结论\n\n"
    "【必须做的】\n"
    "0. 给患者的原话补充标点符号，让语句通顺易读\n"
    "1. 忠实保留患者原话\n"
    "2. 按以下结构归类：主诉、现病史、伴随症状、饮食二便、睡眠\n"
    "3. 如果某项信息患者没提，写【患者未提及】，绝对不能填补\n\n"
    "【输出格式】\n"
    "主诉：...\n"
    "现病史：...\n"
    "伴随症状：...\n"
    "饮食二便：...\n"
    "睡眠：...\n\n"
    "患者原话：{raw_input}"
)

def patient_structurize(state: PatientState) -> dict:
    try:
        prompt = PATIENT_PROMPT.replace("{raw_input}", state["raw_input"])
        response = llm.invoke(prompt)
        return {"structured": response.content}
    except Exception as e:
        # 降级：调用失败时，原样返回
        return {"structured": state["raw_input"]}

patient_graph = StateGraph(PatientState)
patient_graph.add_node("structurize", patient_structurize)
patient_graph.set_entry_point("structurize")
patient_graph.add_edge("structurize", END)
patient_agent = patient_graph.compile()


def structurize_patient_input(raw_input: str) -> str:
    """患者智能体入口：把患者原话整理成结构化主诉。"""
    try:
        result = patient_agent.invoke({"raw_input": raw_input, "data_type": "text", "structured": ""})
        return result["structured"]
    except Exception:
        return raw_input


# ============ 医生智能体 ============
DOCTOR_PROMPT = (
    "你是一名中医老师的【病历助理】。你唯一的任务是：把学生的结构化主诉和过往病历，套用成标准化病历草案，供老师补充。\n\n"
    "【绝对禁止】\n"
    "1. 不能诊断、辨证、开方、推理\n"
    "2. 不能替老师补充舌象、脉象、辨证、施治方案\n"
    "3. 不能修改学生的原话\n\n"
    "4. 不要试图访问、读取或播放图片、音频文件（它们只是学生上传的附件 URL，你无法访问）\n"
    "【必须做的】\n"
    "1. 严格按下面模板填空\n"
    "2. 缺失的信息留空，等老师补充\n\n"
    "【输出模板】\n"
    "【中医病历草案】\n"
    "学生姓名：{patient_name}\n"
    "就诊时间：{visit_date}\n\n"
    "【主诉（学生原话）】\n"
    "{student_complaint}\n\n"
    "【既往病历参考】\n"
    "{past_records}\n\n"
    "【待老师补充】\n"
    "- 舌象：\n"
    "- 脉象：\n"
    "- 辨证：\n"
    "- 施治方案：\n"
)


def generate_medical_draft(patient_name: str, visit_date: str, student_complaint: str, past_records: str) -> str:
    """医生智能体入口：把学生主诉和过往病历整理成病历草案。"""
    import re

    # 【第41天修复】把图片/录音 URL 从学生内容里抽出来，Python 直接拼接，不让 LLM 处理
    image_urls = list(dict.fromkeys(re.findall(r'/uploads/[a-zA-Z0-9._-]+\.(?:jpg|jpeg|png|gif|webp)', student_complaint)))
    audio_urls = list(dict.fromkeys(re.findall(r'/uploads/audio_[a-zA-Z0-9._-]+', student_complaint)))
    
    # 从 student_complaint 里删掉图片/录音部分，得到纯文字
    text_only = re.sub(r'【上传的图片】[\s\S]*?(?=【|$)', '', student_complaint)
    text_only = re.sub(r'【上传的录音】[\s\S]*?(?=【|$)', '', text_only)
    text_only = re.sub(r'【学生上传的图片】[\s\S]*?(?=【|$)', '', text_only)
    text_only = re.sub(r'【学生上传的录音】[\s\S]*?(?=【|$)', '', text_only)
    text_only = text_only.strip()

    try:
        prompt = (DOCTOR_PROMPT
                  .replace("{patient_name}", patient_name)
                  .replace("{visit_date}", visit_date)
                  .replace("{student_complaint}", text_only)
                  .replace("{past_records}", past_records))
        response = llm.invoke(prompt)
        llm_output = response.content
    except Exception:
        llm_output = (
            "【中医病历草案】\n"
            "学生姓名：" + patient_name + "\n"
            "就诊时间：" + visit_date + "\n\n"
            "【主诉（学生原话）】\n" + text_only + "\n\n"
            "【既往病历参考】\n" + past_records + "\n\n"
            "【待老师补充】\n"
            "- 舌象：\n"
            "- 脉象：\n"
            "- 辨证：\n"
            "- 施治方案：\n"
        )

    # 【关键】图片和录音的 URL 由 Python 直接拼接到末尾，不经过 LLM
    image_section = ""
    if image_urls:
        image_section = "\n\n【学生上传的图片】\n" + "\n".join([f"图片{i+1}：{u}" for i, u in enumerate(image_urls)])

    audio_section = ""
    if audio_urls:
        audio_section = "\n\n【学生上传的录音】\n" + "\n".join([f"录音{i+1}：{u}" for i, u in enumerate(audio_urls)])

    return llm_output + image_section + audio_section

# ============ 老师端现场记录整理 ============
TEACHER_LIVE_PROMPT = (
    "你是一名中医老师的【口述整理员】。老师刚刚口述了现场望闻问切的内容，你需要把它整理成结构化的临床记录。\n\n"
    "【绝对禁止】\n"
    "1. 不能做诊断、辨证、开方\n"
    "2. 不能添加老师没说过的内容\n"
    "3. 不能修改老师的原意\n\n"
    "【必须做的】\n"
    "1. 给老师的原话补充标点符号\n"
    "2. 按以下结构归类：舌象、脉象、问诊补充、其他观察\n"
    "3. 老师没提到的项目写【未提及】\n\n"
    "【输出格式】\n"
    "舌象：...\n"
    "脉象：...\n"
    "问诊补充：...\n"
    "其他观察：...\n\n"
    "老师原话：{raw_text}"
)

def structurize_teacher_note(raw_text: str) -> str:
    """老师端现场口述整理入口。"""
    try:
        prompt = TEACHER_LIVE_PROMPT.replace("{raw_text}", raw_text)
        response = llm.invoke(prompt)
        return response.content
    except Exception:
        return raw_text

    