"""五阶段状态机与权限矩阵的**数据底座**（Epic 2 · 设计 §0.4 / §2.3 **唯一真相源**）

对齐：docs/epic2-agent-stage-design-v1.md
  - §0.4 枚举与命名对照表（唯一口径，全栈共用）：五阶段枚举 / rank / 繁体徽章 / 能力键
  - §2.3 能力 → 阶段矩阵（L2 判定表，唯一真相源）
  - §4.5-① 本文件的公开符号清单（`STAGES` / `STAGE_RANK` / `STAGE_LABELS` /
    `CAPABILITIES` / `CAPABILITY_MIN_STAGE`）+ 总闸 flag 判定
    （`AGENT_STAGE_ENABLED_VALUES` / `agent_stage_enabled`，施工步骤 2.2 追加；
    默认 off 的口径见 §4.5-①，flag off 的逐字节语义见 §5.1 红线 ①）

**本步骤（施工步骤 1：数据底座）的边界**
  - 本文件目前**只放常量数据**：阶段枚举、等级、繁体徽章、能力枚举、能力→阶段矩阵，
    以及由矩阵派生的只读查询表 `CAPABILITY_MATRIX`。
  - **零 DB 访问、零 DDL**（3 张表由迁移 `0003_add_agent_stage` 建）；唯一的 import 是 stdlib `os`
    （读总闸环境变量）。本步骤仍是「纯常量 + 一个环境变量判读函数」。
  - **施工步骤 2.2 追加**（CTO 裁决②「方案 B」）：总闸 `AGENT_STAGE_ENABLED` 的取值语义与
    `agent_stage_enabled()` 提前落在服务层 —— 与 `template_service.template_api_enabled()`
    （`template_service.py:898-909`）同一先例：flag 真相源在服务层，接口层与非接口路径一律问服务层。
    **本文件对 `database` 零 import（模块级与函数级都没有）**：由 `database.py` 反向**函数内延迟
    import** 本文件（`_agent_stage_snapshot_enabled()`），循环依赖由此彻底断开。
  - 状态机与配置链（`current_stage` / `require_capability` / `DEFAULT_STAGE_CONFIG` /
    `load_stage_config` / `evaluate` / …，见 §4.5-①）属**施工步骤 3**，届时**追加**在本文件末尾，
    **不改**本段任何符号名与取值。
  - 三条铁律（AI 永不诊断 / 永不开方 / 永不签字）**不体现为常量**：它们是「不存在的能力」——
    §2.1 由**禁止 import 清单**（`create_prescription` / `sanitize_prescription_items` /
    `batch_deduct_herbs` / `sign_draft` / `update_draft_content` / `save_prescription`）+
    守护测试保证。本文件永远不得 import 上述任何符号。
"""

import os

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

# ---------------------------------------------------------------------------
# 【§4.5-① / §4.2 改 1】总闸 flag —— CTO 裁决②「方案 B」：真相源放服务层
# ---------------------------------------------------------------------------
# 与 `template_service.TEMPLATE_API_ENABLED_VALUES` / `template_api_enabled()` 逐字同款
# （`template_service.py:897-909`），**默认 off**。
AGENT_STAGE_ENABLED_VALUES = ("on", "1", "true", "yes")


def agent_stage_enabled():
    """总闸 `AGENT_STAGE_ENABLED`：**每次调用现读**（便于灰度切换 / 测试，不必重启 uvicorn）。**默认 off。**

    flag off = 与今天 1:1（§5.5-①）：不写 3 张新表、不写两个快照列、不建请示、不算指标、
    不改任何既有响应字段、`/api/agent/stage*` 全部 404 —— 既有链路一字不改。

    调用方（施工步骤 2.2 起）：
      · `database.insert_draft()` / `database.sign_draft()` 的**快照列双闸门**
        （经 `database._agent_stage_snapshot_enabled()` 函数内延迟 import 取用，方向单向）；
      · 接口层 `/api/agent/stage*` 的 404 闸门（施工步骤 4）。
      · 【施工步骤 2.3 起】**反向**：`database.sign_draft()` 末尾会 best-effort 调用本模块的
        `on_draft_signed(teacher_name)`（§4.2 改 2b）。它是施工步骤 3 的符号；落地时**首行必须自闸门**
        （`if not agent_stage_enabled(): return`）—— 库层只转发、**不替它判 flag**（否则会出现第二个
        flag 判断）。总闸语义因此仍然成立：flag off → 钩子立即返回 → 不算指标、不写新表（§5.1 红线 ①）。
      · 【施工步骤 2.4 起】**反向**：`database.resolve_agent_task()` 末尾会 best-effort 调用本模块的
        `apply_upgrade_confirmation(teacher_name, to_stage, task_id)`（老师 ✅确认升级）/
        `decline_upgrade(teacher_name, task_id)`（老师忽略升级）（§4.2 改 3）。两者同样是施工步骤 3
        的符号，**首行必须自闸门**；且调用发生在 `resolve_agent_task` **已 commit 之后** —— 钩子内部
        出错**不得**回滚老师已落定的决策，故服务层自行吞异常并只打日志（与 `on_draft_signed` 同口径）。
        `to_stage` 取自 `action_data["to"]`（缺键时为 `None`），服务层必须自行校验其合法性。

    **本函数只读环境变量**：不读库、不打日志、不抛异常、不缓存（读到的永远是当前 env）。
    """
    return os.environ.get("AGENT_STAGE_ENABLED", "off").strip().lower() in AGENT_STAGE_ENABLED_VALUES

