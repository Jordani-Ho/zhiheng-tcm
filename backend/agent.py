import json
import os
import re
import sqlite3
from datetime import datetime
from dotenv import load_dotenv
from langchain_openai import ChatOpenAI
from langgraph.graph import StateGraph, END
from typing import TypedDict

# 【行政化改造 B3】新增「欠费预存 / 复诊提醒」请示扫描：要读 accounts / patient_records 并写 agent_tasks，
# 这里复用 database 的连接与表（不新增依赖）。patient_records.visit_at（就诊时间）由 database.init_db()
# 自动迁移补列、由 database.sign_draft() 签字落库时写入，本文件只读。
import database

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


def generate_medical_draft(patient_name: str, visit_date: str, student_complaint: str, past_records: str,
                           section_template: str = None) -> str:
    """医生智能体入口：把学生主诉和过往病历整理成病历草案。

    【Epic 1 §12.2 新增可选参数】`section_template` = 老师生效「病历」模板的段落骨架提示
    （`database.record_section_skeleton()` 产出的多行文本；缺省 None → 提示词与今天逐字节一致）。
    只决定「按老师的段落顺序与标题写」，**不放宽任何禁区**：标「留待老师」的段（舌象 / 脉象 /
    辨证 / 施治方案）智能体永不填内容（§12.2 第 4 条）。
    LLM 调用失败时的本地兜底文本不含模板骨架（降级路径保持与今天一致）。
    """
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
        if section_template:
            # 【Epic 1 §12.2】老師生效「病歷」模板的段落骨架：只規定「按什麼段落順序與標題寫」，
            # 一個字都不放寬禁區 —— 「（留待老師）」的段必須只留標題、內容留空。
            prompt = prompt + (
                "\n【本診室病歷段落骨架（依老師模板，段落順序照寫）】\n" + section_template +
                "\n凡標記「（留待老師）」的段落只保留標題，內容一律留空，不要替老師補寫。\n"
            )
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


# ============ 【第76天新增】老师端「辨证施治方案」（医嘱）录音转写清洗 ============
# 场景：老师用语音输入施治方案（如“三碗水泡20分钟，大火烧开转小火煲30分钟，饭后服”）。
# 医嘱没有病历五段式的结构，若复用 clean_transcript 会被套进“主诉/舌象/脉象”里，
# 甚至被当成寒暄删掉，所以单独一个 prompt + 接口：只去噪，不做任何结构化分节。
CLEAN_PLAN_PROMPT = (
    "你是一名中医老师的【施治方案口述清洗员】。老师刚刚口述了施治方案（医嘱、煎法、服法、忌口等），"
    "语音识别出来的原始转写里夹杂着寒暄、语气词和重复。你的任务只有一个："
    "只删掉废话，所有医嘱信息一个字都不能少，再输出成一段连贯的医嘱文本。\n\n"
    "【铁律：医嘱关键信息必须原文保留，不得删除、不得改写】\n"
    "1. 剂量与用量：如“三碗水”“20分钟”“每次100毫升”“一天两次”里的数字和单位，一个字都不能改\n"
    "2. 时间：浸泡时长、煎煮时长、服药时间、疗程（如“饭后服”“早晚各一次”“连服七天”）必须原样保留\n"
    "3. 煎法：先煎、后下、包煎、另煎、烊化、冲服、捣碎、泡水等煎煮要求必须原样保留\n"
    "4. 火候：大火、小火、武火、文火、烧开、转小火等火候描述必须原样保留\n"
    "5. 服法：温服、冷服、饭前、饭后、睡前、分几次服等服用方法必须原样保留\n"
    "6. 忌口与注意事项：忌辛辣、忌生冷、忌油腻、忌茶、孕妇慎用、不适停服等必须原样保留\n"
    "7. 药材名与症状原词必须照抄原词（如“黄芪”“白芍”“小柴胡汤”），不许换成近义词或简称\n\n"
    "【只允许删除这些】\n"
    "1. 寒暄、客套、称呼、与本次施治方案无关的闲聊（如“你好”“坐吧”“外面下雨了”）\n"
    "2. 语气词与口头禅（如“嗯”“啊”“那个”“就是说”“然后呢”）\n"
    "3. 结巴、重复、自我更正、说了半句又重来的无意义片段\n"
    "4. 删词只删“语气”，绝不删任何剂量、时间、煎法、火候、服法、忌口、注意事项\n\n"
    "【绝对禁止】\n"
    "1. 不能做诊断、辨证、开方或任何推理判断\n"
    "2. 不能虚构、推测或“顺手补全”老师没说过的药材、剂量、用法或注意事项\n"
    "3. 不能改写、概括、合并或删除任何具体数字和时间\n"
    "4. 不要分节、不要五段式，不要出现“主诉”“现病史”“伴随症状”“舌象”“脉象”等病历结构\n\n"
    "【输出格式】\n"
    "只输出清洗后的文本本身：一段连贯的医嘱文本（按老师口述的顺序，可含标点与停顿），"
    "不要分节、不要小标题、不要项目符号、不要任何前缀（如“施治方案：”“医嘱：”）、"
    "不要解释说明、不要 markdown 标记。\n\n"
    "老师原话：{raw_text}"
)


def clean_plan(raw_text: str) -> str:
    """【第76天新增】老师端施治方案（医嘱）录音转写清洗入口：只去噪，保留全部医嘱细节。

    与 clean_transcript 的区别：这里不做五段式结构化，输出一段连贯的医嘱文本，
    防止剂量、时间、煎法、火候、服法、忌口等医嘱信息被套进病历结构或被当闲聊删掉。

    注意：这里不吞异常——LLM 调用失败（网络 / 鉴权 / 超时）或返回空内容时直接抛出，
    由调用方（main.py 的 POST /api/agent/clean_plan）降级返回原文，保证不阻塞老师操作。
    """
    prompt = CLEAN_PLAN_PROMPT.replace("{raw_text}", raw_text)
    response = llm.invoke(prompt)
    cleaned = (response.content or "").strip()
    if not cleaned:
        raise ValueError("clean_plan: 智能体返回内容为空")
    return cleaned


# ============ 【第80天新增】学生智能体「十问歌」主动追问（面诊前准备） ============
# 场景：学生约好老师、面诊之前，学生智能体主动把还没说清的症状一项一项问出来，
# 面诊时老师直接读到一份「问诊前摘要」，不用再从头问一遍。
# 十问歌：一问寒热二问汗，三问头身四问便，五问饮食六问胸，七聋八渴俱当辨，九问旧病十问因。
#
# TEN_QUESTIONS 一份数据两处用（都在下面）：
#   ① 喂给 LLM 当「固定十项清单」——LLM 逐项对照学生已回答内容，挑第一个没明确回答的问；
#   ② LLM 调用失败时的静态兜底——直接按已答轮次取第 N 问（第（N+1）项），保证前端永远拿得到问题。
# 顺序 = 十问歌原顺序，不能改（改了会和老师的阅读习惯错位）。
TEN_QUESTIONS = [
    ("寒热", "你最近是怕冷多一点，还是怕热多一点？"),
    ("汗", "你平时出汗多不多，是白天容易出汗，还是睡着了出汗？"),
    ("头身", "头或者身体有没有哪里不舒服，比如头晕、头痛、身上发酸发沉？"),
    ("二便", "大小便情况怎么样，有没有干结、稀软或者次数变多？"),
    ("饮食", "最近胃口和口味怎么样，吃东西香不香？"),
    ("胸腹", "胸口或者肚子有没有发闷、发胀、隐隐作痛？"),
    ("耳", "耳朵有没有响，或者听东西不太清楚？"),
    ("口渴", "会觉得口渴吗，平时更想喝热水还是凉水？"),
    ("旧病", "以前得过什么病，有没有长期在吃的药？"),
    ("病因", "这次不舒服大概是从什么时候开始的，你觉得可能和什么有关？"),
]

# 十项里「学生明确说没有」也算已经问到（不重复问）；十项都覆盖 → 返回 done。
ASK_NEXT_QUESTION_PROMPT = (
    "你是一名中医学生智能体的【问诊前追问员】。这位学生已经约好了老师的面诊，"
    "在面诊之前，你要按中医「十问歌」把还没问到的症状一项一项问清楚，"
    "帮老师把学生的零散说法攒成一份面诊时能快速读懂的「问诊前摘要」。\n\n"
    "【十问歌 · 固定十项（顺序不能变，也不许增删）】\n"
    "{checklist}\n\n"
    "【你要做的】\n"
    "1. 先通读下面的「学生已经回答过的内容」，逐项判断这十项里哪些已经明确回答"
    "（学生说到了、或明确说「没有 / 还好」，都算已回答）\n"
    "2. 【严格按顺序扫描】从第 1 项开始逐项往下看：已经明确回答的 → 跳过看下一项；"
    "遇到第一项没明确回答的，就问它，绝对不要先问后面的项"
    "（例如第 9 项「旧病」还没问到，就不许先问第 10 项「病因」）\n"
    "3. 措辞口语化，像关心的同学在聊天：不要出现「寒热」「二便」「问汗」这类学术说法，"
    "可以结合学生前面回答里提到的症状把问题问得更贴人（例如学生说头晕，就问「头晕的时候是一阵一阵还是一直晕」）\n"
    "4. 一次只问一个问题，一两句话说完就行，不要列清单、不要带序号\n\n"
    "【绝对禁止】\n"
    "1. 不能诊断、辨证、开方，不能推荐药、食疗、穴位、养生方法\n"
    "2. 不能评价或安慰学生的回答（如「这很常见」「别担心」）\n"
    "3. 不能一次抛出多个问题，不能要求学生拍照、上传资料或去做检查\n"
    "4. 不能重复学生已经明确回答过的项\n\n"
    "【输出格式】\n"
    "· 还有没问到的项：只输出这一个问题本身（一句口语化的问句），"
    "不要序号、不要「问题：」这类前缀、不要引号、不要解释、不要 markdown。\n"
    "· 十项都已经明确回答（或学生已明确表示没有更多可说的）：只输出 {done} 三个字，不要别的内容。\n\n"
    "【学生姓名】{patient_name}\n"
    "【学生已经回答过的内容】\n"
    "{current_answers}"
)

# 「十问已问全」的固定输出标记（LLM 按约定输出这三个字；解析时原样识别）
ASK_DONE_MARK = "已问全"

# 十问歌 → 结构化摘要的固定十行（供 save_intake 的 prompt 用，与 TEN_QUESTIONS 同序同名）
INTAKE_SUMMARY_LINES = "\n".join(f"{label}：..." for label, _ in TEN_QUESTIONS)

# 保存前的整理 prompt：只做格式化（补标点 / 归类 / 删语气词），不许推理、不许补充、不许给建议。
SAVE_INTAKE_PROMPT = (
    "你是一名中医问诊的【记录整理员】。学生已经在面诊前按「十问歌」回答完了一轮问题，"
    "你的任务只有一个：把这些零散的回答整理成一份老师面诊时 10 秒钟能读完的「问诊前摘要」。\n\n"
    "【绝对禁止】\n"
    "1. 不能做任何诊断、辨证、开方、推理判断\n"
    "2. 不能添加学生没说过的内容，也不能替学生「推测」或「补全」\n"
    "3. 不能给出任何建议（吃药、食疗、作息、穴位、复诊都一个字都不要提）\n\n"
    "【必须做的】\n"
    "1. 只做格式化：给学生的原话补标点、删掉语气词、按下面固定十项归类\n"
    "2. 学生原话照抄（如「手脚冰凉」「大便两天一次」「夜里两点醒」），不要改写成术语\n"
    "3. 学生某项完全没提到 → 该项写「未提及」，绝对不能填补\n"
    "4. 一项里说了多件事就保留在同一行，用逗号或分号隔开，不要自己分小节、加小标题\n\n"
    "【输出格式】严格按下面第一行的标题 + 固定十行，顺序不增不减，不要任何别的内容"
    "（不要前言、不要总结、不要 markdown 标记）\n"
    "【面诊前摘要】\n"
    "{summary_lines}\n\n"
    "【学生姓名】{patient_name}\n"
    "【学生的问答记录】\n"
    "{answers}"
)


def _parse_next_question(raw_text):
    """解析 LLM 的追问输出。

    · 返回 None：LLM 没给可用内容（空串 / 全是标点）→ 调用方走静态兜底，避免把「追问」变成「无话可说」；
    · 返回 {"question": "", "done": True}：命中「已问全」标记 → 十问已覆盖；
    · 返回 {"question": "…", "done": False}：拿到下一个问题（已做轻量清洗：去序号 / 去「问题：」前缀 / 只留第一句）。
    """
    text = (raw_text or "").strip().strip("`*# \t\r\n")
    if not text:
        return None
    if ASK_DONE_MARK in text:
        return {"question": "", "done": True}
    text = re.sub(r"^\s*(?:[-*•·]\s*|\d+\s*[.、)）:：]\s*)", "", text)   # 去列表符号 / 序号
    text = re.sub(r"^(?:问题|下一个问题|追问|问)\s*[:：]\s*", "", text)      # 去常见前缀
    first_q = re.search(r"[？?]", text)
    if first_q:
        text = text[:first_q.end()]     # 问号后还有内容 = LLM 一次多问了 → 只留第一句
    text = text.strip().strip('"“”\'‘’')
    if not text:
        return None
    if ASK_DONE_MARK in text:
        return {"question": "", "done": True}
    return {"question": text, "done": False}


def _fallback_next_question(answered_rounds):
    """LLM 调用失败 / 输出无法解析时的静态兜底：按已答轮次取十问歌里的下一项。

    前端按「问：…\\n答：…」累积 current_answers，所以「答：」出现几次就是已经答了几轮；
    轮次超出十项 → 视为十问已覆盖（done）。
    """
    if answered_rounds >= len(TEN_QUESTIONS):
        return {"question": "", "done": True}
    return {"question": TEN_QUESTIONS[answered_rounds][1], "done": False}


def ask_next_question(patient_name: str, current_answers: str) -> dict:
    """【改动1】学生智能体「十问歌」主动追问入口。

    入参：patient_name（学生姓名，只用于让提问更贴人）、current_answers（学生已回答的内容，第一次为空串）。
    返回：{"question": str, "done": bool}
      · done=False → question 是下一个问题（一句话、口语化，不带诊断/开方/建议）；
      · done=True  → 十问已覆盖，question 为空串。

    越界防护：这里只产出「问什么」，不产出任何诊断、辨证、开方或建议；
    即使 LLM 不听话多问了，_parse_next_question 也只会留下第一句话，保证「一次只问一个」。
    """
    answers_text = (current_answers or "").strip()
    # 确定性上限：十项都答过就不再问（同时兜住「LLM 万一绕圈」导致前端永远问不完的情况）
    answered_rounds = answers_text.count("答：")
    if answered_rounds >= len(TEN_QUESTIONS):
        return {"question": "", "done": True}

    checklist = "\n".join(f"{i}. 问{label}：{example}" for i, (label, example) in enumerate(TEN_QUESTIONS, 1))
    prompt = (ASK_NEXT_QUESTION_PROMPT
              .replace("{checklist}", checklist)
              .replace("{done}", ASK_DONE_MARK)
              .replace("{patient_name}", patient_name or "这位学生")
              .replace("{current_answers}", answers_text or "（学生还没有回答过任何内容，请从第 1 项开始问）"))
    try:
        response = llm.invoke(prompt)
    except Exception:
        return _fallback_next_question(answered_rounds)   # LLM 挂了也不能让学生卡在这里

    parsed = _parse_next_question(response.content)
    if parsed is None:
        return _fallback_next_question(answered_rounds)
    if parsed["done"]:
        return {"question": "", "done": True}
    return parsed


def _ensure_complaints_status_column():
    """保证 complaints 有 status 列（改动2 要求落 status='pending'）。

    【为什么写在这里】complaints 表定义在 database.py（本次改动范围之外，不动它），
    老库里没有 status 列，所以这里做一次幂等补列（与 database.py 里 visit_at / is_remote 的
    ALTER TABLE 补列手法完全一致：列已存在时 sqlite 抛 OperationalError，直接跳过）。
    """
    conn = database.get_connection()
    try:
        conn.execute("ALTER TABLE complaints ADD COLUMN status TEXT DEFAULT 'pending'")
        conn.commit()
    except sqlite3.OperationalError:
        pass   # 列已存在（重复调用）
    finally:
        conn.close()


def _format_intake(patient_name: str, answers: str) -> str:
    """把学生的问答记录整理成「问诊前摘要」（LLM 只做格式化；失败就降级成原文，绝不丢内容）。"""
    raw = (answers or "").strip()
    if not raw:
        return "【面诊前摘要】\n（学生未填写内容）"
    prompt = (SAVE_INTAKE_PROMPT
              .replace("{summary_lines}", INTAKE_SUMMARY_LINES)
              .replace("{patient_name}", patient_name or "这位学生")
              .replace("{answers}", raw))
    try:
        response = llm.invoke(prompt)
        text = (response.content or "").strip()
        if text:
            return text
    except Exception:
        pass
    return "【面诊前摘要】\n" + raw   # 降级：原样保留学生问答记录，老师照样能读


def save_intake(patient_name: str, teacher_name: str, answers: str) -> dict:
    """【改动2】保存「面诊前准备」结果：整理成结构化文本 → 写入 complaints（学生陈述表）。

    · status 固定 'pending'（老师尚未在面诊中处理）；
    · created_at 用 datetime.now().isoformat()，与库内其它 created_at 写法一致；
    · 只管格式化，不做任何推理 / 补充（见 SAVE_INTAKE_PROMPT）。
    返回：{"ok": True, "id": 新记录 id}
    """
    content = _format_intake(patient_name, answers)
    _ensure_complaints_status_column()
    conn = database.get_connection()
    cur = conn.cursor()
    try:
        cur.execute(
            "INSERT INTO complaints (teacher_name, patient_name, content, status, created_at) "
            "VALUES (?, ?, ?, 'pending', ?)",
            (teacher_name, patient_name, content, datetime.now().isoformat())
        )
    except sqlite3.OperationalError:
        # 兜底：补列失败（权限 / 锁 / 极旧库）时也不让学生白准备，先按老字段写进去
        cur.execute(
            "INSERT INTO complaints (teacher_name, patient_name, content, created_at) VALUES (?, ?, ?, ?)",
            (teacher_name, patient_name, content, datetime.now().isoformat())
        )
    new_id = cur.lastrowid
    conn.commit()
    conn.close()
    return {"ok": True, "id": new_id}


# ============ 【行政化改造 B3】学生管理请示：欠费预存 + 复诊提醒 ============
# 复用 B1 的 agent_tasks 表：老师名下学生的三类请示统一由 agent_tasks 承载 ——
#   send_care_notice（沉默关怀，B1 已有）/ send_billing_notice（欠费预存）/ send_recall_notice（复诊提醒）。
# action 命名沿用 database.scan_silent_students 里定下的 send_<类型>_notice 规范。

BILLING_LOW_BALANCE = 100   # 【可配置阈值】学生余额低于该值 → 生成「预存提醒」请示
RECALL_DAYS = 60            # 【可配置阈值】学生距上次就诊超过该天数 → 生成「复诊提醒」请示

# 【第77天新增】「就诊时间」的唯一来源 = patient_records.visit_at（签字落库时写的 datetime.now().isoformat()）。
# 旧做法是从病历文本的签字行「李老师 · 2026年9月23日」里解析日期：学生没走签字流程、签字行被删、
# 日期格式一改就整个失效，所以废弃文本解析，改为直接读 visit_at 列；visit_at 为空的旧记录没有就诊基准，不参与扫描。


def _teacher_student_names(cur, teacher_name, lineage_id=None):
    """该老师名下所有在读学生姓名（升序），学生口径与 database.scan_silent_students 保持一致。

    【Epic 4 §3.2 P1】flag on 时 `pt.lineage_id = ? AND pt.teacher_name = ?`；flag off 时
    语句字面量与参数与改动前逐字节相同（`database.lineage_read_scope` 返回 `(False, "")` 时零 SQL）。
    """
    filter_on, lineage_id = database.lineage_read_scope(teacher_name, lineage_id)
    owner_where = "pt.lineage_id = ? AND pt.teacher_name = ?" if filter_on else "pt.teacher_name = ?"
    owner_params = (lineage_id, teacher_name) if filter_on else (teacher_name,)
    rows = cur.execute("""
        SELECT p.name AS name
        FROM patients p
        INNER JOIN patient_teachers pt ON p.name = pt.patient_name
        WHERE """ + owner_where + """ AND pt.status = 'active'
        ORDER BY p.name
    """, owner_params).fetchall()
    return [row["name"] for row in rows]


def _pending_task_exists(cur, teacher_name, task_type, category, action, patient_name, lineage_id=None):
    """去重判断：【task_type + category + action_data.action + patient_name + status='pending'】
    五个条件全中才算「已有同类请示」，否则可以再建一条。

    做法：SQL 先按 teacher_name / task_type / category / status 过滤（条件明确、不扫全表），
    再在 Python 侧解析 action_data 比对 action + patient_name —— 这样 action_data 里以后
    增减字段（如 amount / days）也不会漏判，同一学生的不同类型请示（关怀 / 欠费 / 复诊）互不影响。

    【Epic 4 §3.2 P1】flag on 时 WHERE 再加 `lineage_id = ?`：别师门的同类 pending 请示
    不能把本师门学生的请示「顶掉」（否则本师门该建的单不建 = 漏建）。
    """
    filter_on, lineage_id = database.lineage_read_scope(teacher_name, lineage_id)
    owner_where = "lineage_id = ? AND teacher_name = ?" if filter_on else "teacher_name = ?"
    owner_params = (lineage_id, teacher_name) if filter_on else (teacher_name,)
    rows = cur.execute("""
        SELECT action_data FROM agent_tasks
        WHERE """ + owner_where + """ AND task_type = ? AND category = ? AND status = 'pending'
    """, owner_params + (task_type, category)).fetchall()
    for row in rows:
        try:
            data = json.loads(row["action_data"]) if row["action_data"] else {}
        except Exception:
            continue
        if data.get("action") == action and data.get("patient_name") == patient_name:
            return True
    return False


def _insert_student_request(cur, teacher_name, title, content, action_data, created_at):
    """往 agent_tasks 写一条待审批请示（字段与 B1 一致：task_type='request'、category='student'、status='pending'）。"""
    cur.execute("""
        INSERT INTO agent_tasks (teacher_name, task_type, category, title, content, action_data, status, created_at)
        VALUES (?, 'request', 'student', ?, ?, ?, 'pending', ?)
    """, (teacher_name, title, content, json.dumps(action_data, ensure_ascii=False), created_at))


def check_billing_alerts(teacher_name, low_balance=BILLING_LOW_BALANCE, lineage_id=None):
    """【B3-改动1：欠费请示】扫描该老师名下学生的余额（accounts.balance），余额 < low_balance 的生成请示。

    · 余额来源：accounts 表（username = 学生姓名）。
    · 只有「在 accounts 里开过户」的学生（= 预存制学生）才参与欠费扫描：没有账户的学生从未预存过，
      不属于「余额告急」场景，不生成请示（否则每个没充过钱的学生都会刷一条「余额仅剩 0 分」，把
      待你确认区刷爆）。老师真要给他建账户，走「💰 财务管理 → 预存」。余额被扣到 0 的已开户学生照常提醒。
    · 去重：同 teacher + task_type='request' + category='student' + action='send_billing_notice'
      + patient_name + status='pending' 已存在 → 跳过，不重复建单。
    返回：本次新建的请示条数。

    【Epic 4 §3.2 P1】flag on 时：names 由 `_teacher_student_names` 带 lineage 过滤（学生名集合），
    去重查询由 `_pending_task_exists` 带 lineage 过滤。本函数**不自己发 SQL**，故只透传 `lineage_id`
    （作用域校验的入口仍是 `database.lineage_read_scope`，由上面两个函数执行，不重复判断）。
    **但校验必须前置到「开连接」之前**（与 `check_recall_alerts` 同序）：否则 flag on + 缺 / 跨门
    `lineage_id` 时，被调函数在校验处抛 `LineageError`，本函数已经开出的连接再也走不到
    `conn.close()` → 连接泄漏（Windows 上会一直锁住库文件）。flag off 时这次调用零 SQL、零变化。
    """
    database.lineage_read_scope(teacher_name, lineage_id)   # 先校驗（fail-loud 不佔連接）
    conn = database.get_connection()
    cur = conn.cursor()
    now = datetime.now()
    created = 0
    for name in _teacher_student_names(cur, teacher_name, lineage_id):
        row = cur.execute("SELECT balance FROM accounts WHERE username = ?", (name,)).fetchone()
        if row is None or row["balance"] is None:
            continue  # 没开过户 → 不是预存制学生，不进欠费扫描
        balance = row["balance"]
        if balance >= low_balance:
            continue
        if _pending_task_exists(cur, teacher_name, "request", "student", "send_billing_notice", name, lineage_id):
            continue
        _insert_student_request(
            cur, teacher_name,
            f"{name}余额仅剩 {balance} 分",
            "是否发送预存提醒？",
            {"action": "send_billing_notice", "patient_name": name, "amount": balance},
            now.isoformat()
        )
        created += 1
    conn.commit()
    conn.close()
    return created


def _parse_visit_at(value):
    """【第77天新增】把 patient_records.visit_at 解析成 datetime；为空 / 解析不了 → None。

    主格式是 database.sign_draft 落的 datetime.now().isoformat()（如 2026-09-23T15:30:00），
    顺带兼容纯日期「2026-09-23」与空格分隔的「2026-09-23 15:30:00」（手工造数据 / 早期写法）。
    带时区的值去掉时区后按本地时间参与比较，保证能和 datetime.now()（naive）相减。
    """
    text = (value or "").strip()
    if not text:
        return None
    for fmt in (None, "%Y-%m-%d %H:%M:%S", "%Y-%m-%d"):
        try:
            parsed = datetime.fromisoformat(text) if fmt is None else datetime.strptime(text, fmt)
        except ValueError:
            continue
        return parsed.replace(tzinfo=None)  # 统一成 naive，方便和 now 相减
    return None


def check_recall_alerts(teacher_name, recall_days=RECALL_DAYS, lineage_id=None):
    """【B3-改动2：复诊提醒请示】按 patient_records.visit_at 里每个学生最后一次就诊时间，超过 recall_days 天生成请示。

    · 「最后一次就诊时间」= 该老师在 patient_records 里的 MAX(visit_at)（按 patient_name 分组）：
      一次 SQL 聚合就拿到每个学生最近一次就诊时间，不再解析病历文本（ISO 字符串字典序 == 时间先后）。
    · visit_at 为空 / 解析不了的记录（第77天之前的老数据）→ 没有就诊基准，整条跳过，不生成请示。
    · 去重：同 teacher + task_type='request' + category='student' + action='send_recall_notice'
      + patient_name + status='pending' 已存在 → 跳过，不重复建单。
    返回：本次新建的请示条数。

    【Epic 4 §3.2 P1】本函数**自己发一条 SQL**（patient_records 聚合），故按 flag on/off 拼 `owner_where`：
      · flag on：`lineage_id = ? AND teacher_name = ?`（学生集合与去重查询由被调函数各自带过滤）；
      · flag off：字面量/参数与改动前逐字节相同。
    """
    filter_on, lineage_id = database.lineage_read_scope(teacher_name, lineage_id)
    recall_where = "lineage_id = ? AND teacher_name = ?" if filter_on else "teacher_name = ?"
    recall_params = (lineage_id, teacher_name) if filter_on else (teacher_name,)
    conn = database.get_connection()
    cur = conn.cursor()
    now = datetime.now()
    created = 0

    # 每个学生的最近一次就诊时间（只取该老师的病历；visit_at 为空的旧记录直接排除）
    latest_rows = cur.execute("""
        SELECT patient_name, MAX(visit_at) AS last_visit_at
        FROM patient_records
        WHERE """ + recall_where + """ AND visit_at IS NOT NULL AND visit_at != ''
        GROUP BY patient_name
    """, recall_params).fetchall()
    last_visit_map = {row["patient_name"]: row["last_visit_at"] for row in latest_rows}

    for name in _teacher_student_names(cur, teacher_name, lineage_id):
        last_visit = _parse_visit_at(last_visit_map.get(name))
        if last_visit is None:
            continue  # 没有病历 / 旧记录 visit_at 为空 → 没有就诊基准，不算「久未复诊」
        days = (now - last_visit).days
        if days <= recall_days:
            continue
        if _pending_task_exists(cur, teacher_name, "request", "student", "send_recall_notice", name, lineage_id):
            continue
        _insert_student_request(
            cur, teacher_name,
            f"{name}距上次就诊已 {days} 天",
            "是否发送复诊提醒？",
            {"action": "send_recall_notice", "patient_name": name, "days": days},
            now.isoformat()
        )
        created += 1
    conn.commit()
    conn.close()
    return created


def scan_student_requests(teacher_name, lineage_id=None):
    """【B3-改动3：统一扫描入口】把该老师名下学生的三类请示一次扫完，返回本次新建任务总数。

    顺序与设计文档一致：沉默关怀（B1 已有的 database.scan_silent_students）→ 欠费预存 → 复诊提醒。
    三类都写进同一张 agent_tasks（category='student'），各自按 action 独立去重，互不干扰。

    【Epic 4 §3.2 P1】`lineage_id` 一路透传到三类扫描（三者各自经 `database.lineage_read_scope`
    做存在性 + 归属校验）；flag off 时三个调用与改动前逐字节等价（多传一个 `lineage_id=None` 而已）。
    """
    if not teacher_name:
        return 0
    created = database.scan_silent_students(teacher_name, lineage_id=lineage_id)
    created += check_billing_alerts(teacher_name, lineage_id=lineage_id)
    created += check_recall_alerts(teacher_name, lineage_id=lineage_id)
    return created

    

# =====【Epic 2】老師智能體五階段：新增能力（追加，既有段落一字不改）=====
# 对齐：docs/epic2-agent-stage-design-v1.md §4.3（追加位置 / 输出契约 / 禁区段 / 不 import database）
#       + §8 step 5（施工步骤 4c-1：`agent.py` 末尾 3 组能力 + 服务侧入口 + 守护测试）。
# 三条纪律（本段自我约束，⑩ / ㉑ 组的源码级守护钉住）：
#   ① **既有代码零改动**：本段只往文件末尾追加 —— 六个既有 prompt 常量与既有函数一字不改，
#      `generate_medical_draft()` 仍是唯一病历生成入口（§5.1 红线②），本段不新增第二条生成路径；
#   ② **不碰 `database`**：三个新函数零 `database.*` 调用（第 14 行既有的 import 不改、也不新增），
#      入参全部是纯文本 / dict，AI 层只产文本 —— 落库永远由服务层
#      （`agent_stage_service.build_suggestion()` / `build_predraft()`）在老师确认路径上完成（§4.3 末条）；
#   ③ **绝不编造**：LLM 调用失败 / 输出解析不出来，唯一出口是「空结果 + `error='parse_failed'`」
#      （§4.3 的输出契约），绝不把模型没给的症状、药材、剂量补进去。
# 文案口径：prompt 正文与本文件既有段落同用简体；`disclaimer` 值按设计 §4.3 **逐字**（繁体），
#           与 `agent_stage_service.DISCLAIMER_*` 三常量互为同一份字面量（㉑ 组交叉钉住）。

# ---- 能力 1/3【見習期 `predict_pattern`】證型候選 ----

PATTERN_CANDIDATE_PROMPT = (
    "你是一名中医老师的【证型候选提示员】。你唯一的任务是：根据学生的病历材料，提示 1–3 个"
    "候选证型，供老师参考。\n\n"
    "【绝对禁止】\n"
    "1. 不能做诊断、下结论：不得输出「诊断为」「确诊」「辨证为……」这类结论性表述，"
    "只许输出「候选证型」并标注仅供参考\n"
    "2. 不得自行开具处方：不给方剂、不给药材、不给剂量、不给煎服法\n"
    "3. 不能添加材料里没有说过的症状、舌象、脉象、既往史（材料不足就少给候选，绝不补齐）\n"
    "4. 不能生成任何可以自动发送给学生 / 患者的文字\n"
    "5. 不能代替老师签字，也不能要求老师直接采用\n\n"
    "【必须做的】\n"
    "1. 每条候选都必须带 basis：至少 1 条**病历原文片段**（照抄材料原话，一个字都不许改）；"
    "抄不到原文片段的候选一律不要输出\n"
    "2. confidence 只能是 high / medium / low（证据越直接越高）\n"
    "3. 最多 3 条候选；材料不足时宁可只给 1 条或 0 条\n"
    "4. note 用一句话说明这条候选提示的是什么，不要写成结论\n\n"
    "【输出格式】只输出一个 JSON 对象，不要任何前缀、后缀、解释或 markdown 标记：\n"
    "{\"candidates\":[{\"name\":\"候选证型名\",\"confidence\":\"medium\","
    "\"basis\":[\"病历原文片段\"],\"note\":\"一句话提示\"}],"
    "\"disclaimer\":\"僅供參考，非診斷\"}\n\n"
    "【学生姓名】\n{patient_name}\n\n"
    "【主诉（学生原话）】\n{complaint}\n\n"
    "【病历材料（草案正文，含老师已补充内容）】\n{transcript}\n\n"
    "【既往病历参考】\n{past_records}\n\n"
    "【本诊室病历段落骨架（依老师模板，仅供按段落顺序阅读材料）】\n{teacher_skeleton}"
)

# ---- 能力 2/3【助手期 `suggest_prescription`】方劑建議 ----

FORMULA_SUGGESTION_PROMPT = (
    "你是一名中医老师的【方剂建议员】。你唯一的任务是：根据学生的病历材料，提示 1–3 个"
    "**可参考的方剂方向**（方名 + 加减思路 + 组成药材名），供老师参考。\n\n"
    "【绝对禁止】\n"
    "1. 不能做诊断、下结论：不得输出「诊断为」「确诊」「辨证为……」这类结论性表述\n"
    "2. **不能给剂量**：任何数字都不许出现（不给 9g / 3钱 / 10ml，也不给「每次多少」）\n"
    "3. **不能给煎服法**：不给煎煮时间、火候、服用时间、疗程、忌口（那是老师的施治方案）\n"
    "4. 不得自行开具处方：不能输出任何可以落库 / 可以自动发送的字段（患者名、处方号、金额、发送对象一律不要）\n"
    "5. 不能添加材料里没有说过的症状、舌象、脉象；不给中成药、西药建议\n"
    "6. 不能代替老师签字，也不能要求老师直接采用\n\n"
    "【必须做的】\n"
    "1. 只写方名 / 加减思路 / 组成药材**名单**；药名照抄标准药名，不带剂量、不带炮制用量\n"
    "2. modification 写「按什么症状怎么加减」的一句话思路（同样不许出现数字）\n"
    "3. composition 是药材名字符串数组（如 [\"柴胡\",\"黃芩\"]），不带剂量、不带括号备注\n"
    "4. usage 恒为「僅供參考」；最多 3 个方剂；材料不足时宁可只给 1 个或 0 个\n\n"
    "【输出格式】只输出一个 JSON 对象，不要任何前缀、后缀、解释或 markdown 标记：\n"
    "{\"formulas\":[{\"name\":\"小柴胡湯\",\"modification\":\"口干者加天花粉\","
    "\"composition\":[\"柴胡\",\"黃芩\"],\"usage\":\"僅供參考\"}],"
    "\"disclaimer\":\"僅供參考，非處方\"}\n\n"
    "【学生姓名】\n{patient_name}\n\n"
    "【主诉（学生原话）】\n{complaint}\n\n"
    "【病历材料（草案正文，含老师已补充内容）】\n{transcript}\n\n"
    "【既往病历参考】\n{past_records}\n\n"
    "【本诊室病历段落骨架（依老师模板，仅供按段落顺序阅读材料）】\n{teacher_skeleton}"
)

# ---- 能力 3/3【授權期 `generate_predraft`】預處方預填 ----

PREDRAFT_PROMPT = (
    "你是一名中医老师的【预处方预填员】。你唯一的任务是：根据学生的病历材料，把「预处方」"
    "的表格字段**预填**出来（方名 + 药味 / 剂量 / 君臣佐使 + 煎服法），供老师逐项核对与修改。\n\n"
    "【绝对禁止】\n"
    "1. 不能做诊断、下结论：不得输出「诊断为」「确诊」「辨证为……」这类结论性表述"
    "（证型只能作为你选药的内部依据，一个字都不许写进返回的数据里）\n"
    "2. 不得自行开具处方：**不能落库、不能发送、不能签字**，你只返回一段数据，存处方必须由老师本人在系统里操作\n"
    "3. 不能编造材料里没有依据的药材或剂量：拿不准的剂量留空字符串，等老师补\n"
    "4. 不能把这份预填当成处方结论，也不能生成任何面向学生 / 患者的文字\n"
    "5. 不能添加材料里没有说过的症状、舌象、脉象\n\n"
    "【必须做的】\n"
    "1. items 每项三个字段：herb（药材名）；dose（剂量，照常规写如 9g，没有依据就写空串）；"
    "role（君 / 臣 / 佐 / 使，判断不了就写空串）\n"
    "2. decoction 写煎服法提示（如「水煎服，日一剂」）；拿不准就写「由老師填寫」\n"
    "3. formula_name 与老师指定的方名一致；老师未指定时按材料给一个常用方名"
    "（只是预填，不得当成结论）\n"
    "4. 药味数量克制（一般 4–12 味）；材料不足时宁可少给，不要凑数\n\n"
    "【输出格式】只输出一个 JSON 对象，不要任何前缀、后缀、解释或 markdown 标记：\n"
    "{\"predraft\":{\"formula_name\":\"方名\",\"items\":[{\"herb\":\"柴胡\",\"dose\":\"9g\","
    "\"role\":\"君\"}],\"decoction\":\"水煎服，日一剂\"},"
    "\"disclaimer\":\"僅供參考，須老師確認並自行開方\"}\n\n"
    "【老师指定的方名（可为空，空则按材料拟一个）】\n{formula_name}\n\n"
    "【学生姓名】\n{patient_name}\n\n"
    "【主诉（学生原话）】\n{complaint}\n\n"
    "【病历材料（草案正文，含老师已补充内容）】\n{transcript}\n\n"
    "【既往病历参考】\n{past_records}\n\n"
    "【本诊室病历段落骨架（依老师模板，仅供按段落顺序阅读材料）】\n{teacher_skeleton}"
)

# ---------------------------------------------------------------------------
# 三个能力的契约常量（§4.3 输出契约的**逐字**字面量）
# ---------------------------------------------------------------------------
# `disclaimer` 三值：服务层 `DISCLAIMER_PATTERN` / `DISCLAIMER_FORMULA` / `DISCLAIMER_PREDRAFT`
# 与这里同字面量（㉑ 组交叉钉住：两处必须逐字节同字，改一处要同步另一处）。
PATTERN_DISCLAIMER = "僅供參考，非診斷"
FORMULA_DISCLAIMER = "僅供參考，非處方"
PREDRAFT_DISCLAIMER = "僅供參考，須老師確認並自行開方"
# 方劑建議的 `usage` 是**契约值**，恒为这一句（不采用模型给的值，免得模型写进剂量 / 疗程）。
FORMULA_USAGE = "僅供參考"
# 置信度白名单：模型写了别的值（含大小写变形）→ 一律降为 low（绝不把不确定放成「高」）。
PATTERN_CONFIDENCE_LEVELS = ("high", "medium", "low")
# 上限：§4.3 / §4.6-⑥⑦ 的「最多 3 条」；药味上限是防 prompt 回包失控的兜底（不是业务规则）。
MAX_PATTERN_CANDIDATES = 3
MAX_FORMULA_CANDIDATES = 3
MAX_PREDRAFT_ITEMS = 20
# 入参文本上限：与 `agent_stage_service.truncate_chars()` 的默认值同口径（2000 字），
# 服务层会先截一次，这里是模型侧的兜底（免得一份超长草案把提示词撑爆）。
PROMPT_TEXT_LIMIT = 2000
# 解析失败的唯一标记（服务层据此提示「本次没有产出」，而不是假装成功）。
PARSE_FAILED = "parse_failed"
# ---------------------------------------------------------------------------
# 三个能力的**共享小工具**（纯函数：无副作用、零 `database.*` 调用、不新增 import）
# ---------------------------------------------------------------------------

# 图片 / 录音的 URL 段落：与既有 `generate_medical_draft()` 第 122–125 行**同一套正则**（同口径）。
# 理由同该处：模型读不到本地文件，URL 喂进提示词只是噪声 / 幻觉来源。
_MEDIA_SECTION_PATTERNS = (
    r"【上传的图片】[\s\S]*?(?=【|$)",
    r"【上传的录音】[\s\S]*?(?=【|$)",
    r"【学生上传的图片】[\s\S]*?(?=【|$)",
    r"【学生上传的录音】[\s\S]*?(?=【|$)",
)


def _clip_text(text, limit=PROMPT_TEXT_LIMIT):
    """通用收敛：非字符串（`None` / 数字 / list）→ 空串；去首尾空白；过长截断。"""
    value = text if isinstance(text, str) else ""
    return value.strip()[:limit]


def _plain_text(text, limit=PROMPT_TEXT_LIMIT):
    """提示词入参清洗：剥掉图片 / 录音 URL 段落（口径与既有生成路径同款），再去空白 + 截断。"""
    value = text if isinstance(text, str) else ""
    for pattern in _MEDIA_SECTION_PATTERNS:
        value = re.sub(pattern, "", value)
    return _clip_text(value, limit)


def _load_json_object(raw_text):
    """从模型回包里取出一个 JSON 对象（§4.3「严格 JSON → 纯文本兜底」）：

      ① 原样 `json.loads`（prompt 已要求「只输出一个 JSON 对象」）；
      ② 失败则取**第一个 `{` 到最后一个 `}`** 再试一次（剥掉 ```json 围栏与前后解说）；
      ③ 仍失败 → `None`（调用方据此返回空结果 + `PARSE_FAILED`）。
    只认对象（`dict`）：数组 / 标量一律当解析失败 —— 契约里没有第二种形状，不猜。
    """
    value = raw_text if isinstance(raw_text, str) else ""
    attempts = [value]
    left, right = value.find("{"), value.rfind("}")
    if left != -1 and right > left:
        attempts.append(value[left:right + 1])
    for attempt in attempts:
        try:
            data = json.loads(attempt)
        except (ValueError, TypeError):
            continue
        if isinstance(data, dict):
            return data
    return None


def _text_list(value, limit=200):
    """把 `basis` / `composition` 这类字段收敛成**非空字符串数组**：

      · 字符串 → 单元素数组（模型偶尔给字符串而不是数组，宽松兼容）；
      · 其它类型（`None` / dict / 数字）→ 空数组；
      · 每项去空白 + 截断，空串丢掉（**不补内容**：宁可短，不编造）。
    """
    if isinstance(value, str):
        value = [value]
    if not isinstance(value, list):
        return []
    items = []
    for item in value:
        text = _clip_text(item, limit)
        if text:
            items.append(text)
    return items


def _dose_free(text, limit=300):
    """去掉**剂量 / 用量数字写法**（§4.3 方剂建议「不含剂量、不含煎法用量」的代码级保证）：
    `柴胡 9g` → `柴胡`；`9 克` / `10ml` / `3錢` 同理；残留的阿拉伯数字一并去掉
    —— 方剂建议整份没有数字字段，连「日一剂」这种写法也留不下来。
    单位按**长在前**排列（`mg` 先于 `g`），免得 `mg` 被认成 `m` + `g`。
    """
    value = text if isinstance(text, str) else ""
    value = re.sub(r"\s*\d+(?:\.\d+)?\s*(?:mg|kg|ml|g|毫克|千克|毫升|克|錢|钱|兩|两)", "",
                   value, flags=re.I)
    return _clip_text(re.sub(r"\d", "", value), limit)


def _herb_name(text, limit=60):
    """药味名收敛：先过 `_dose_free()`，再去掉括号备注（「(炒)」「（先煎）」只留药名）
    与串尾分隔符（「、」「,」「+」），最后截断。"""
    value = re.sub(r"[（(][^）)]*[）)]", "", _dose_free(text, limit))
    return value.strip().strip("、,，;；+｜|").strip()[:limit]


def _blank_predraft():
    """预处方的**空预填**（解析失败时的出口形状）：逐键与成功体同形，一个药味都不编。"""
    return {"formula_name": "", "items": [], "decoction": ""}


# ---------------------------------------------------------------------------
# 三个能力的**输出规范化**（模型说什么不算数，契约说什么才算数）
# ---------------------------------------------------------------------------

def _normalize_pattern_candidates(data):
    """模型输出 → §4.3 的严格形状（`candidates` + `disclaimer`），不满足契约的候选一律丢掉：

      · `name` 为空 → 丢；`basis` 少于 1 条**非空原文片段** → 丢（「必带病历原文依据」是硬契约）；
      · `confidence` 不在白名单（high / medium / low，大小写不敏感）→ 降为 `low`；
        `note` 允许为空（只是提示语，不构成依据）；
      · 最多 `MAX_PATTERN_CANDIDATES`（3）条。
    一条都不剩（含 `data is None`，即解析失败）→ `{"candidates": [], "error": PARSE_FAILED, ...}`：
    空结果 + 免责声明，**绝不拿模型的原话补出一条**（§4.3「绝不编造」）。
    """
    if not isinstance(data, dict):
        return {"candidates": [], "error": PARSE_FAILED, "disclaimer": PATTERN_DISCLAIMER}
    raw_items = data.get("candidates")
    candidates = []
    for item in (raw_items if isinstance(raw_items, list) else [])[:MAX_PATTERN_CANDIDATES]:
        if not isinstance(item, dict):
            continue
        name = _clip_text(item.get("name"), 100)
        basis = _text_list(item.get("basis"), 200)
        if not name or not basis:
            continue
        confidence = item.get("confidence")
        confidence = confidence.strip().lower() if isinstance(confidence, str) else ""
        if confidence not in PATTERN_CONFIDENCE_LEVELS:
            confidence = "low"
        candidates.append({"name": name, "confidence": confidence, "basis": basis,
                           "note": _clip_text(item.get("note"), 200)})
    if not candidates:
        return {"candidates": [], "error": PARSE_FAILED, "disclaimer": PATTERN_DISCLAIMER}
    return {"candidates": candidates, "disclaimer": PATTERN_DISCLAIMER}


def _normalize_formula_suggestions(data):
    """模型输出 → §4.3 的严格形状（`formulas` + `disclaimer`）：

      · `name` 为空 或 `composition` 全空 → 丢（没方名 / 没药味的「方剂建议」没有意义）；
      · `composition` 逐项过 `_herb_name()`（去剂量、去括号备注、去分隔符），空项丢掉；
      · `modification` 过 `_dose_free()`（加减思路里也不许有数字）；
      · `usage` 恒用 `FORMULA_USAGE` 契约值（不采用模型给的值 —— 免得模型借这栏写剂量 / 疗程）；
      · 最多 `MAX_FORMULA_CANDIDATES`（3）个方剂。
    一个都不剩 → `{"formulas": [], "error": PARSE_FAILED, ...}`（同證型候选：空，不编造）。
    """
    if not isinstance(data, dict):
        return {"formulas": [], "error": PARSE_FAILED, "disclaimer": FORMULA_DISCLAIMER}
    raw_items = data.get("formulas")
    formulas = []
    for item in (raw_items if isinstance(raw_items, list) else [])[:MAX_FORMULA_CANDIDATES]:
        if not isinstance(item, dict):
            continue
        name = _dose_free(_clip_text(item.get("name"), 100), 100)
        composition = [_herb_name(text) for text in _text_list(item.get("composition"), 60)]
        composition = [herb for herb in composition if herb]
        if not name or not composition:
            continue
        formulas.append({
            "name": name,
            "modification": _dose_free(_clip_text(item.get("modification"), 300), 300),
            "composition": composition,
            "usage": FORMULA_USAGE,
        })
    if not formulas:
        return {"formulas": [], "error": PARSE_FAILED, "disclaimer": FORMULA_DISCLAIMER}
    return {"formulas": formulas, "disclaimer": FORMULA_DISCLAIMER}


def _normalize_predraft(data, formula_name=""):
    """模型输出 → §4.3 的严格形状（`predraft` + `disclaimer`）：

      · 只认 `{"predraft": {...}}` 这一层（契约里没有第二种形状 —— 严格，不猜字段语义）；
      · `items` 逐项：`herb` 为空 → 丢；`dose` / `role` 允许空串（拿不准就空着，等老师补）；
      · `formula_name` 为空时用**老师指定的** `formula_name` 兜底（老师自己写的方名不算编造）；
      · 药味上限 `MAX_PREDRAFT_ITEMS`（20），防回包失控。
    没有方名或没有药味 → 空预填 + `error=PARSE_FAILED`（同两款建议：绝不编造）。
    """
    inner = data.get("predraft") if isinstance(data, dict) else None
    if not isinstance(inner, dict):
        return {"predraft": _blank_predraft(), "error": PARSE_FAILED, "disclaimer": PREDRAFT_DISCLAIMER}
    formula = _clip_text(inner.get("formula_name"), 100) or _clip_text(formula_name, 100)
    raw_items = inner.get("items")
    items = []
    for item in (raw_items if isinstance(raw_items, list) else [])[:MAX_PREDRAFT_ITEMS]:
        if not isinstance(item, dict):
            continue
        herb = _clip_text(item.get("herb"), 60)
        if not herb:
            continue
        items.append({"herb": herb, "dose": _clip_text(item.get("dose"), 40),
                      "role": _clip_text(item.get("role"), 20)})
    if not formula or not items:
        return {"predraft": _blank_predraft(), "error": PARSE_FAILED, "disclaimer": PREDRAFT_DISCLAIMER}
    return {"predraft": {"formula_name": formula, "items": items,
                         "decoction": _clip_text(inner.get("decoction"), 300)},
            "disclaimer": PREDRAFT_DISCLAIMER}


# ---------------------------------------------------------------------------
# 三个**公开能力入口**（服务层唯一入口：`agent_stage_service.build_suggestion()` / `build_predraft()`）
# ---------------------------------------------------------------------------
# 签名与返回体**就是契约**（§4.3 符号表；能力键见 §2.1）：
#   · `predict_pattern_candidates(patient_name, complaint, transcript, past_records, teacher_skeleton)`
#     ← 見習期 `predict_pattern`；→ `{"candidates":[…],"disclaimer":…}`（≤3 条，每条必带 `basis` 原文依据）
#   · `suggest_formula(patient_name, complaint, transcript, past_records, teacher_skeleton)`
#     ← 助手期 `suggest_prescription`；→ `{"formulas":[…],"disclaimer":…}`（方名 + 加减思路 + 药名，
#       **不含剂量 / 煎服法**）。函数名照 §4.3 符号表，与能力键 `suggest_prescription` 是同一件事的
#       两个名字（服务层按能力键做能力判定、按函数名调模型）。
#   · `generate_predraft(patient_name, formula_name, complaint, transcript, past_records, teacher_skeleton)`
#     ← 授權期 `generate_predraft`；→ `{"predraft":{…},"disclaimer":…}`（预填数据，含剂量；
#       **永不落库、永不发送、永不签字**）
# 共同契约：入参纯文本；LLM 异常 / 解析失败 → 空结果 + `error='parse_failed'`（绝不编造）；
#           返回值只有文本与数字，**没有任何数据库字段**（患者名 / 处方号 / 金额一律不产）。
# 调用方式：`agent_stage_service` 用关键字参数调（`formula_name=` / `transcript=` …），
#          免得日后调参顺序时出现「位置参数错位」这种静默事故。

def predict_pattern_candidates(patient_name, complaint, transcript, past_records, teacher_skeleton):
    """【見習期 `predict_pattern` / §4.3】证型候选提示（≤3 条，每条必带病历原文片段 `basis`）。

    只产文本：**不写库、不发消息、不签字**（落库由服务层在老师确认路径上做）。LLM 抛异常与
    解析失败走**同一条出口** —— 空候选 + `error='parse_failed'`：调用方据此回「本次没有产出」，
    而不是把半句模型输出当真。`patient_name` 只用于提示词，不参与任何判定。
    """
    prompt = (PATTERN_CANDIDATE_PROMPT
              .replace("{patient_name}", _clip_text(patient_name, 100))
              .replace("{complaint}", _plain_text(complaint))
              .replace("{transcript}", _plain_text(transcript))
              .replace("{past_records}", _plain_text(past_records))
              .replace("{teacher_skeleton}", _clip_text(teacher_skeleton, 1000)))
    try:
        response = llm.invoke(prompt)
        raw_text = getattr(response, "content", "") or ""
    except Exception:
        return {"candidates": [], "error": PARSE_FAILED, "disclaimer": PATTERN_DISCLAIMER}
    return _normalize_pattern_candidates(_load_json_object(raw_text))


def suggest_formula(patient_name, complaint, transcript, past_records, teacher_skeleton):
    """【助手期 `suggest_prescription` / §4.3】方剂建议（≤3 个方，方名 + 加减思路 + 药名名单）。

    与 `generate_predraft()` **刻意区分**：这里**一个剂量都不给**（`_dose_free()` 是代码级保证，
    不只靠提示词），也不给煎服法 —— 「无剂量药单」。同 `predict_pattern_candidates()`：
    只产文本、出口唯一（异常 / 解析失败 → 空方剂 + `error='parse_failed'`）。
    """
    prompt = (FORMULA_SUGGESTION_PROMPT
              .replace("{patient_name}", _clip_text(patient_name, 100))
              .replace("{complaint}", _plain_text(complaint))
              .replace("{transcript}", _plain_text(transcript))
              .replace("{past_records}", _plain_text(past_records))
              .replace("{teacher_skeleton}", _clip_text(teacher_skeleton, 1000)))
    try:
        response = llm.invoke(prompt)
        raw_text = getattr(response, "content", "") or ""
    except Exception:
        return {"formulas": [], "error": PARSE_FAILED, "disclaimer": FORMULA_DISCLAIMER}
    return _normalize_formula_suggestions(_load_json_object(raw_text))


def generate_predraft(patient_name, formula_name, complaint, transcript, past_records, teacher_skeleton):
    """【授權期 `generate_predraft` / §4.3】预处方**预填**（方名 + 药味 / 剂量 / 君臣佐使 + 煎服法）。

    这是三个能力里**唯一含剂量**的一个（授权期专属），但它的纪律比另两个更硬：
    **只返回一段数据** —— 不写库、不发送、不签字；存处方必须由老师在系统里逐项核对后自己操作
    （§4.6-⑦ 的 `note` 文案把这件事写给老师看）。`formula_name` 是老师指定的方名（可空串）：
    为空时允许模型按材料拟一个（预填不是结论）；模型给了方名时以模型为准。
    同前两个：只产文本、出口唯一（异常 / 解析失败 → 空预填 + `error='parse_failed'`，绝不编造）。
    """
    prompt = (PREDRAFT_PROMPT
              .replace("{formula_name}", _clip_text(formula_name, 100))
              .replace("{patient_name}", _clip_text(patient_name, 100))
              .replace("{complaint}", _plain_text(complaint))
              .replace("{transcript}", _plain_text(transcript))
              .replace("{past_records}", _plain_text(past_records))
              .replace("{teacher_skeleton}", _clip_text(teacher_skeleton, 1000)))
    try:
        response = llm.invoke(prompt)
        raw_text = getattr(response, "content", "") or ""
    except Exception:
        return {"predraft": _blank_predraft(), "error": PARSE_FAILED, "disclaimer": PREDRAFT_DISCLAIMER}
    return _normalize_predraft(_load_json_object(raw_text), formula_name)




