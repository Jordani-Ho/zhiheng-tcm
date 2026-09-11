from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

app = FastAPI(title="zhiheng-tcm-backend")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)

# 1. 定义四大角色数据模型
class Role(BaseModel):
    id: str
    name: str
    role_type: str  # teacher, teacher_agent, patient, patient_agent
    description: str

# 模拟数据库
roles_db = [
    Role(id="t1", name="李老师", role_type="teacher", description="民间针灸高手，擅长治未病"),
    Role(id="ta1", name="李老师智能体", role_type="teacher_agent", description="李老师的徒弟，负责生成病历草案"),
    Role(id="p1", name="张三", role_type="patient", description="失眠患者，李老师拉入"),
    Role(id="pa1", name="张三智能体", role_type="patient_agent", description="张三的镜子，负责采集上报数据"),
]

@app.get("/api/health")
def health():
    return {"status": "ok", "service": "zhiheng-tcm-backend"}

@app.get("/api/huangli")
def get_huangli():
    return {
        "date": "2026年09月11日",
        "lunar": "农历八月初一",
        "solar_term": "白露",
        "health_trend": "宜养肺润燥，早卧早起",
        "homework": "今日酉时（17-19点）按揉太渊穴5分钟",
        "current_shi": "酉时"
    }

# 2. 新增获取角色列表的接口
@app.get("/api/roles")
def get_roles():
    return roles_db