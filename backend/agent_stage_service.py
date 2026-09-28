"""五阶段状态机与权限矩阵的**数据底座**（Epic 2 · 设计 §0.4 / §2.3 **唯一真相源**）

对齐：docs/epic2-agent-stage-design-v1.md
  - §0.4 枚举与命名对照表（唯一口径，全栈共用）：五阶段枚举 / rank / 繁体徽章 / 能力键
  - §2.3 能力 → 阶段矩阵（L2 判定表，唯一真相源）
  - §4.5-① 本文件的公开符号清单（`STAGES` / `STAGE_RANK` / `STAGE_LABELS` /
    `CAPABILITIES` / `CAPABILITY_MIN_STAGE`）

**本步骤（施工步骤 1：数据底座）的边界**
  - 本文件目前**只放常量数据**：阶段枚举、等级、繁体徽章、能力枚举、能力→阶段矩阵，
    以及由矩阵派生的只读查询表 `CAPABILITY_MATRIX`。
  - **零业务逻辑、零 DB 访问、零 import、零 DDL**（3 张表由迁移 `0003_add_agent_stage` 建）。
  - 状态机与配置链（`current_stage` / `require_capability` / `DEFAULT_STAGE_CONFIG` /
    `load_stage_config` / `evaluate` / …，见 §4.5-①）属**施工步骤 3**，届时**追加**在本文件末尾，
    **不改**本段任何符号名与取值。
  - 三条铁律（AI 永不诊断 / 永不开方 / 永不签字）**不体现为常量**：它们是「不存在的能力」——
    §2.1 由**禁止 import 清单**（`create_prescription` / `sanitize_prescription_items` /
    `batch_deduct_herbs` / `sign_draft` / `update_draft_content` / `save_prescription`）+
    守护测试保证。本文件永远不得 import 上述任何符号。
"""

# ---------------------------------------------------------------------------
# 五阶段枚举（§0.4）：顺序固定，**不可跳级**（§1.1：只允许 to_rank - from_rank == 1 的升级）
# ---------------------------------------------------------------------------
STAGES = ("observation", "learning", "apprentice", "assistant", "authorized")

# 等级 rank（§0.4）：升级只看 rank+1；降级允许 to_rank < from_rank
STAGE_RANK = {
    "observation": 0,
    "learning": 1,
    "apprentice": 2,
    "assistant": 3,
    "authorized": 4,
}

# 阶段徽章（**繁体古字**，前端直接用；§0.4「所有 UI 文案一律繁体古字」）
STAGE_LABELS = {
    "observation": "觀察期",
    "learning": "學習期",
    "apprentice": "見習期",
    "assistant": "助手期",
    "authorized": "授權期",
}

# ---------------------------------------------------------------------------
# 能力枚举（§0.4 / §2.3）
# ---------------------------------------------------------------------------
CAPABILITIES = (
    "record_observation",      # 只记录 / 统计（零 LLM 输出；observation 期即具备）
    "generate_draft",          # 生成病历草案（= 系统今天已有能力，§5.2）
    "predict_pattern",         # 证型候选（只返回候选，不落库）
    "suggest_prescription",    # 建议方剂（无剂量药单）
    "generate_predraft",       # 生成预处方（仅供前端预填；永不落库 / 发送 / 签字）
)

# 能力 → 最低阶段（§2.3 矩阵的等价压缩：capability 可用 ⟺ rank(stage) >= rank(本值)）
CAPABILITY_MIN_STAGE = {
    "record_observation": "observation",
    "generate_draft": "learning",
    "predict_pattern": "apprentice",
    "suggest_prescription": "assistant",
    "generate_predraft": "authorized",
}

# ---------------------------------------------------------------------------
# 能力 → 阶段矩阵（§2.3，**逐格字面量** —— 便于与设计表格逐行人工对照）
#   True  = 该阶段允许该能力（L2 阶段门控放行）
#   False = 拒绝 → `AgentStageError(code='stage_forbidden')` → 接口层 403 + 审计 permission_denied
# 注意：本表**不含** L1 三条铁律、也不含 flag `AGENT_STAGE_ENABLED` 总闸 ——
#      铁律永不放宽（§2.1），flag off 时 `generate_draft` 有既有行为的兼容例外（§2.3 / §5.1 红线 1）。
# ---------------------------------------------------------------------------
CAPABILITY_MATRIX = {
    "observation": {
        "record_observation": True,
        "generate_draft": False,       # §5.3：observation 期降级为本地骨架，不走 LLM
        "predict_pattern": False,
        "suggest_prescription": False,
        "generate_predraft": False,
    },
    "learning": {
        "record_observation": True,
        "generate_draft": True,
        "predict_pattern": False,
        "suggest_prescription": False,
        "generate_predraft": False,
    },
    "apprentice": {
        "record_observation": True,
        "generate_draft": True,
        "predict_pattern": True,
        "suggest_prescription": False,
        "generate_predraft": False,
    },
    "assistant": {
        "record_observation": True,
        "generate_draft": True,
        "predict_pattern": True,
        "suggest_prescription": True,
        "generate_predraft": False,
    },
    "authorized": {
        "record_observation": True,
        "generate_draft": True,
        "predict_pattern": True,
        "suggest_prescription": True,
        "generate_predraft": True,
    },
}
