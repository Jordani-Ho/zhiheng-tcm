from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

app = FastAPI(title="zhiheng-tcm-backend")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)

@app.get("/api/health")
def health():
    return {"status": "ok", "service": "zhiheng-tcm-backend"}

@app.post("/api/auth/login")
def login(payload: dict):
    code = payload.get("code", "").strip().upper()
    if code == "TEACHER888":
        return {"role": "teacher", "name": "李老师"}
    elif code == "PATIENT666":
        return {"role": "patient", "name": "患者张三"}
    else:
        return {"error": "邀请码无效，请联系您的老师获取"}

# 核心：模拟 LangGraph 的多节点推理过程
@app.post("/api/agent/think")
def agent_think(payload: dict):
    raw_data = payload.get("raw_data", "")
    if not raw_data:
        return {"error": "没有收到患者数据"}

    # 节点 1：提取症状
    symptoms = []
    if "苔白" in raw_data or "苔偏白" in raw_data: symptoms.append("苔白")
    if "畏寒" in raw_data or "怕冷" in raw_data: symptoms.append("畏寒")
    if "脉细" in raw_data or "脉弱" in raw_data: symptoms.append("脉细")
    if not symptoms: symptoms = ["症状不明确"]

    # 节点 2：中医辨证推理
    syndrome = ""
    if "苔白" in symptoms and "畏寒" in symptoms:
        syndrome = "寒湿困脾"
    elif "脉细" in symptoms:
        syndrome = "气血不足"
    else:
        syndrome = "需进一步问诊"

    # 节点 3：生成调理草案
    prescription = "建议温阳化湿，可适当艾灸足三里、中脘穴。"
    if syndrome == "气血不足":
        prescription = "建议益气养血，可适当食用红枣、桂圆，并注意休息。"

    # 节点 4：组装最终草案（带思考过程的透明化）
    draft = f"【辨证】：{syndrome}。\n【症状】：{'、'.join(symptoms)}。\n【建议】：{prescription}"

    return {
        "status": "success",
        "draft": draft,
        "symptoms": symptoms,
        "syndrome": syndrome
    }