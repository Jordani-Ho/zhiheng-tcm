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


# ============ 【第68天新增】老师端录音转写清洗（去噪 / 提炼 / 结构化） ============
# 场景：诊室“现场辅助记录”录音（Web Speech API）识别出来的原始文本，夹杂“嗯、啊、寒暄、重复”。
# 这段文本在追加到病历草案之前，先经过本智能体清洗：去掉废话、提炼关键描述、按中医病历结构排版。
CLEAN_TRANSCRIPT_PROMPT = (
    "你是一名中医老师的【录音转写清洗员】。老师刚刚口述了望闻问切的内容，"
    "语音识别出来的原始转写里夹杂着寒暄、语气词和重复。你的任务只有一个："
    "只删掉废话，医学信息一个字都不能少，再按五段式排版。\n\n"
    "【铁律：中医术语与症状原词必须原文保留，不得删除、不得改写】\n"
    "1. “脉象”“舌象”“主诉”“现病史”“伴随症状”“辨证”等中医关键词一律原文保留，"
    "既不能删，也不能换成近义词（如“舌象”不许写成“舌诊”，“脉象”不许写成“脉诊”）\n"
    "2. 症状的原始描述必须照抄原词，例如“弦细”“浮紧”“舌苔厚腻”“细沉”，"
    "一个字都不能改，也不许概括成上位概念\n"
    "3. 若原文出现“脉象细沉”这类描述，段值里必须照抄症状原词“细沉”，"
    "严禁把“脉象”改写成“脉诊”或其他说法（去掉段名重复见【段值不得重复段名】）\n"
    "4. 若原文出现“辨证”相关内容（如“辨证为肝郁脾虚”），保留原词原句，归入“现病史”段，同样不许删改\n\n"
    "【只允许删除这些】\n"
    "1. 寒暄、客套、称呼、与本次诊疗无关的闲聊（如“你好”“坐吧”“外面下雨了”）\n"
    "2. 语气词与口头禅（如“嗯”“啊”“那个”“就是说”“然后呢”）\n"
    "3. 结巴、重复、自我更正、说了半句又重来的无意义片段\n"
    "4. 删词只删“语气”，绝不删任何症状、部位、程度、时间、舌脉描述\n\n"
    "【绝对禁止】\n"
    "1. 不能做诊断、辨证、开方或任何推理判断\n"
    "2. 不能虚构、推测或“顺手补全”老师没说过的症状、舌象、脉象\n"
    "3. 不能为了“规范用语”把老师的原词改写成别的术语，从而丢掉原始描述\n\n"
    "【段值不得重复段名】\n"
    "五段式每一段冒号后面的值，不要再重复本段段名；段名只出现在冒号前面（固定段名），\n"
    "段值里必须去掉开头的段名本身（或与段名等价的引导词，如“舌苔”“舌质”之于“舌象”）。\n"
    "1. 原文说“脉象细沉”，应输出“脉象：细沉”，不许输出“脉象：脉象细沉”\n"
    "2. 原文说“舌苔薄白”，应输出“舌象：薄白”，不许输出“舌象：舌苔薄白”\n"
    "3. 若原文说的就是“脉象细沉”，则段值里去掉开头的“脉象”两字，只保留“细沉”\n"
    "4. “主诉”“现病史”“伴随症状”同理：原文说“主诉头痛”就写“主诉：头痛”，\n"
    "原文说“伴随症状口干”就写“伴随症状：口干”\n"
    "5. 本条只去掉段名/段名等价引导词，症状原词（细沉、薄白、弦细、浮紧等）一个字都不能少；\n"
    "段名本身仍保留在该段冒号前面，信息没有丢失，与上文的“术语原文保留”不冲突\n\n"
    "【输出格式】严格按下面五项，每项一行，顺序固定，不增不减：\n"
    "主诉：...\n"
    "现病史：...\n"
    "伴随症状：...\n"
    "舌象：...\n"
    "脉象：...\n\n"
    "【缺失处理】只有该项内容在老师原话里确实完全没有出现，才写（未提及）；"
    "只要原文出现过该段相关的关键词或描述，就必须原文写出来，绝不允许写成（未提及）。\n\n"
    "【输出要求】只输出上述五段结构化文本本身，不要任何前缀、解释、说明、前言、后缀或 markdown 标记。\n\n"
    "老师原话：{raw_text}"
)


def clean_transcript(raw_text: str) -> str:
    """【第68天新增】老师端录音转写清洗入口：去噪、提炼、格式化。

    注意：这里不吞异常——LLM 调用失败（网络 / 鉴权 / 超时）或返回空内容时直接抛出，
    由调用方（main.py 的 POST /api/agent/clean_transcript）降级返回原文，保证不阻塞老师操作。
    """
    prompt = CLEAN_TRANSCRIPT_PROMPT.replace("{raw_text}", raw_text)
    response = llm.invoke(prompt)
    cleaned = (response.content or "").strip()
    if not cleaned:
        raise ValueError("clean_transcript: 智能体返回内容为空")
    return cleaned

    