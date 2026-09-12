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

# 模拟病历数据（真实场景存在患者端本地，这里为了演示放内存）
patient_record = {
    "content": "",
    "is_burned": False,
    "message": ""
}

@app.get("/api/health")
def health():
    return {"status": "ok", "service": "zhiheng-tcm-backend"}

# 1. 患者提交病历
@app.post("/api/record/save")
def save_record(payload: dict):
    patient_record["content"] = payload.get("content", "")
    patient_record["is_burned"] = False
    patient_record["message"] = "病历已安全发送至老师端"
    return patient_record

# 2. 老师端查看病历（每次查看都确保是未焚毁状态）
@app.get("/api/record/view")
def view_record():
    if patient_record["is_burned"]:
        return {"content": "", "is_burned": True, "message": "该病历已阅后即焚，老师端无法再查看"}
    return patient_record

# 3. 老师点击“阅后即焚”
@app.post("/api/record/burn")
def burn_record():
    if not patient_record["content"]:
        return {"message": "没有可焚毁的病历"}
    patient_record["content"] = ""
    patient_record["is_burned"] = True
    patient_record["message"] = "病历已阅后即焚，老师端数据已清空"
    return patient_record