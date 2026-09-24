import json
import os
import re
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


# ============ 【行政化改造 B3】学生管理请示：欠费预存 + 复诊提醒 ============
# 复用 B1 的 agent_tasks 表：老师名下学生的三类请示统一由 agent_tasks 承载 ——
#   send_care_notice（沉默关怀，B1 已有）/ send_billing_notice（欠费预存）/ send_recall_notice（复诊提醒）。
# action 命名沿用 database.scan_silent_students 里定下的 send_<类型>_notice 规范。

BILLING_LOW_BALANCE = 100   # 【可配置阈值】学生余额低于该值 → 生成「预存提醒」请示
RECALL_DAYS = 60            # 【可配置阈值】学生距上次就诊超过该天数 → 生成「复诊提醒」请示

# 【第77天新增】「就诊时间」的唯一来源 = patient_records.visit_at（签字落库时写的 datetime.now().isoformat()）。
# 旧做法是从病历文本的签字行「李老师 · 2026年9月23日」里解析日期：学生没走签字流程、签字行被删、
# 日期格式一改就整个失效，所以废弃文本解析，改为直接读 visit_at 列；visit_at 为空的旧记录没有就诊基准，不参与扫描。


def _teacher_student_names(cur, teacher_name):
    """该老师名下所有在读学生姓名（升序），学生口径与 database.scan_silent_students 保持一致。"""
    rows = cur.execute("""
        SELECT p.name AS name
        FROM patients p
        INNER JOIN patient_teachers pt ON p.name = pt.patient_name
        WHERE pt.teacher_name = ? AND pt.status = 'active'
        ORDER BY p.name
    """, (teacher_name,)).fetchall()
    return [row["name"] for row in rows]


def _pending_task_exists(cur, teacher_name, task_type, category, action, patient_name):
    """去重判断：【task_type + category + action_data.action + patient_name + status='pending'】
    五个条件全中才算「已有同类请示」，否则可以再建一条。

    做法：SQL 先按 teacher_name / task_type / category / status 过滤（条件明确、不扫全表），
    再在 Python 侧解析 action_data 比对 action + patient_name —— 这样 action_data 里以后
    增减字段（如 amount / days）也不会漏判，同一学生的不同类型请示（关怀 / 欠费 / 复诊）互不影响。
    """
    rows = cur.execute("""
        SELECT action_data FROM agent_tasks
        WHERE teacher_name = ? AND task_type = ? AND category = ? AND status = 'pending'
    """, (teacher_name, task_type, category)).fetchall()
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


def check_billing_alerts(teacher_name, low_balance=BILLING_LOW_BALANCE):
    """【B3-改动1：欠费请示】扫描该老师名下学生的余额（accounts.balance），余额 < low_balance 的生成请示。

    · 余额来源：accounts 表（username = 学生姓名）。
    · 只有「在 accounts 里开过户」的学生（= 预存制学生）才参与欠费扫描：没有账户的学生从未预存过，
      不属于「余额告急」场景，不生成请示（否则每个没充过钱的学生都会刷一条「余额仅剩 0 分」，把
      待你确认区刷爆）。老师真要给他建账户，走「💰 财务管理 → 预存」。余额被扣到 0 的已开户学生照常提醒。
    · 去重：同 teacher + task_type='request' + category='student' + action='send_billing_notice'
      + patient_name + status='pending' 已存在 → 跳过，不重复建单。
    返回：本次新建的请示条数。
    """
    conn = database.get_connection()
    cur = conn.cursor()
    now = datetime.now()
    created = 0
    for name in _teacher_student_names(cur, teacher_name):
        row = cur.execute("SELECT balance FROM accounts WHERE username = ?", (name,)).fetchone()
        if row is None or row["balance"] is None:
            continue  # 没开过户 → 不是预存制学生，不进欠费扫描
        balance = row["balance"]
        if balance >= low_balance:
            continue
        if _pending_task_exists(cur, teacher_name, "request", "student", "send_billing_notice", name):
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


def check_recall_alerts(teacher_name, recall_days=RECALL_DAYS):
    """【B3-改动2：复诊提醒请示】按 patient_records.visit_at 里每个学生最后一次就诊时间，超过 recall_days 天生成请示。

    · 「最后一次就诊时间」= 该老师在 patient_records 里的 MAX(visit_at)（按 patient_name 分组）：
      一次 SQL 聚合就拿到每个学生最近一次就诊时间，不再解析病历文本（ISO 字符串字典序 == 时间先后）。
    · visit_at 为空 / 解析不了的记录（第77天之前的老数据）→ 没有就诊基准，整条跳过，不生成请示。
    · 去重：同 teacher + task_type='request' + category='student' + action='send_recall_notice'
      + patient_name + status='pending' 已存在 → 跳过，不重复建单。
    返回：本次新建的请示条数。
    """
    conn = database.get_connection()
    cur = conn.cursor()
    now = datetime.now()
    created = 0

    # 每个学生的最近一次就诊时间（只取该老师的病历；visit_at 为空的旧记录直接排除）
    latest_rows = cur.execute("""
        SELECT patient_name, MAX(visit_at) AS last_visit_at
        FROM patient_records
        WHERE teacher_name = ? AND visit_at IS NOT NULL AND visit_at != ''
        GROUP BY patient_name
    """, (teacher_name,)).fetchall()
    last_visit_map = {row["patient_name"]: row["last_visit_at"] for row in latest_rows}

    for name in _teacher_student_names(cur, teacher_name):
        last_visit = _parse_visit_at(last_visit_map.get(name))
        if last_visit is None:
            continue  # 没有病历 / 旧记录 visit_at 为空 → 没有就诊基准，不算「久未复诊」
        days = (now - last_visit).days
        if days <= recall_days:
            continue
        if _pending_task_exists(cur, teacher_name, "request", "student", "send_recall_notice", name):
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


def scan_student_requests(teacher_name):
    """【B3-改动3：统一扫描入口】把该老师名下学生的三类请示一次扫完，返回本次新建任务总数。

    顺序与设计文档一致：沉默关怀（B1 已有的 database.scan_silent_students）→ 欠费预存 → 复诊提醒。
    三类都写进同一张 agent_tasks（category='student'），各自按 action 独立去重，互不干扰。
    """
    if not teacher_name:
        return 0
    created = database.scan_silent_students(teacher_name)
    created += check_billing_alerts(teacher_name)
    created += check_recall_alerts(teacher_name)
    return created

    