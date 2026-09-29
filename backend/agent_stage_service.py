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
  - **零 DDL**（3 张表由迁移 `0003_add_agent_stage` 建；两个引用列由迁移
    `0004_add_patient_record_template_refs` 补）。**施工步骤 1 / 2 期间零 DB 访问**：import 只有
    stdlib `os`，本文件当时是「纯常量 + 一个环境变量判读函数」。
    【**施工步骤 3.1 起**】追加「存储就绪探针」+「服务层错误类型」，import 相应增加 stdlib
    `sqlite3` 与**函数体内延迟**的 `database`（见文末「施工步骤 3.1」段）。
  - **施工步骤 2.2 追加**（CTO 裁决②「方案 B」）：总闸 `AGENT_STAGE_ENABLED` 的取值语义与
    `agent_stage_enabled()` 提前落在服务层 —— 与 `template_service.template_api_enabled()`
    （`template_service.py:898-909`）同一先例：flag 真相源在服务层，接口层与非接口路径一律问服务层。
    **施工步骤 1 / 2 期间本文件对 `database` 零 import（模块级与函数级都没有）**：由 `database.py`
    反向**函数内延迟 import** 本文件（`_agent_stage_snapshot_enabled()`），循环依赖由此彻底断开。
    【**施工步骤 3.1 起**】`database` 只在**函数体内**延迟 import（`_store_connection()`；§4.5-①
    明确允许服务层 import `database`）→ 两个方向都恒在函数体内，循环依赖在两条方向上都不成立
    （方向守护：`test_database_to_service_import_stays_inside_function_bodies`）。
  - 状态机与配置链（`current_stage` / `require_capability` / `DEFAULT_STAGE_CONFIG` /
    `load_stage_config` / `evaluate` / …，见 §4.5-①）属**施工步骤 3**，届时**追加**在本文件末尾，
    **不改**本段任何符号名与取值 —— 3.1 先落地「存储就绪探针 + 服务层错误类型」，
    状态机本体（含 `on_draft_signed` / `apply_upgrade_confirmation` / `decline_upgrade` 三个钩子）
    依次在 3.2–3.4 追加（边界与理由见文末「施工步骤 3.1」段）。
  - 三条铁律（AI 永不诊断 / 永不开方 / 永不签字）**不体现为常量**：它们是「不存在的能力」——
    §2.1 由**禁止 import 清单**（`create_prescription` / `sanitize_prescription_items` /
    `batch_deduct_herbs` / `sign_draft` / `update_draft_content` / `save_prescription`）+
    守护测试保证。本文件永远不得 import 上述任何符号。
"""

import os
import sqlite3

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


# ============================================================================
# 【施工步骤 3.1】服务层骨架 ①：存储就绪探针（先做）+ ② 服务层错误类型
# ----------------------------------------------------------------------------
# CTO 2026-09-28 放行 step 3.1 的三条要求，本段逐条对应：
#   要求 1「**先**做 `agent_stage_store_ready()`，**再**做骨架」→ 本段顺序就是探针在前、错误类型在后；
#   要求 2「服务层骨架**不接线任何调用点**」→ 探针今天**只**被本文件的守护用例（⑬ 组）调用；
#     未来的调用点是接口层门卫（施工步骤 4：`agent_stage_api._guard()` 在 flag 与鉴权之后用它映射
#     503 `agent_stage_store_unavailable`，§4.5-② / §4.6）。本步**不动** `main.py` / `database.py` /
#     `agent_stage_api.py`，也不在 `database.py` 里预先 re-export（Epic 1 的 `template_store_ready`
#     是 database 侧 re-export 服务层实现，但那是「接口层已在用」之后的事 —— 无人调用的 re-export
#     属死代码；接口层落地时再按同一先例决定调用哪个模块）。
#   要求 3「flag off 逐字节一致保持」→ 本段不读 flag、不发写语句、不 import 任何既有链路符号，
#     flag off 下既有行为与改动前逐字节相同（⑨ ⑪ ⑫ 组的比对用例继续全绿）。
#
# 本步**不**落地的符号（避免「名字在、行为不在」的假实现）：
#   `DEFAULT_STAGE_CONFIG` / `load_stage_config` / `validate_stage_config` / `current_stage` /
#   `describe_stage` / `require_capability` / `compute_template_match` /
#   `compute_modification_consistency` / `evaluate` / `demote` / `build_suggestion` /
#   `build_predraft` / `on_draft_signed` / `apply_upgrade_confirmation` / `decline_upgrade`
#   —— 按 §4.5-① 属施工步骤 3.2–3.4，落地时**追加**在本段之后（文件即「施工图谱」）。
#   为什么不在 3.1 先放空壳：`database.sign_draft()` / `database.resolve_agent_task()` 的转发段自
#   step 2.3 / 2.4 起就已存在，且对「钩子不存在」有专门用例（静默 no-op）。若现在用空实现把
#   `on_draft_signed(...)` / `apply_upgrade_confirmation(...)` 的名字占住，flag on 时真实调用会被
#   吞成「假装成功」—— 老师点 ✅ 确认升级会静默不生效，而全部用例仍绿。故骨架只收**行为完整且
#   可验证**的符号；「两态纪律」（缺席 = 静默 / 在场 = 真实生效）由此继续对未来子步有效。
# ============================================================================

# 3 张新表的表名（唯一真相源 = 迁移 `0003_add_agent_stage` 的建表语句，§1.4 / §4.2）：
# 本常量只用于「存储就绪」探测与守护用例，**不产生任何 DDL**。
AGENT_STAGE_STORE_TABLES = ("agent_stage_state", "agent_stage_config", "agent_stage_log")


def _store_connection():
    """延迟取 `database.get_connection()`：库路径 / `row_factory` 仍由 `database.py` 单点持有。

    与 `template_service.get_connection()`（`template_service.py:21-27`）同一先例的**同向**写法：
    服务层不自己拼路径、不自己 `sqlite3.connect()`，一律走 `database` 的口子 —— 于是
    `ZHIENG_DB` 环境变量与测试里的 `monkeypatch.setattr(database, "DB_PATH", ...)` 对本探针同样生效。

    `import database` 放在**函数体内**（§4.5-① 允许服务层 import `database`）：`database.py` 侧对本
    文件的 import（`_agent_stage_snapshot_enabled()` / `_call_agent_stage_hook()`）同样恒在函数体内，
    两个方向都延迟 → 循环依赖在任一条路径上都不成立。本函数**只取连接**，不做任何校验 / 建表 / 写库。
    """
    import database
    return database.get_connection()


def agent_stage_store_ready():
    """3 张新表（`agent_stage_state` / `agent_stage_config` / `agent_stage_log`）是否**全部**就位。

    返回 `True` = 迁移 `0003_add_agent_stage` 已跑（三表齐备）；`False` = 迁移未跑 / 只跑了一半 /
    表被改名 / 库不可读（`sqlite3.Error`）→ 接口层回 **503 `agent_stage_store_unavailable`**
    （§4.5-② / §4.6；与 Epic 1 `template_store_ready()` → 503 `template_store_unavailable` 同款先例）。

    三条口径（写死在这里，后续子步不得改）：
      1. **不读 flag**：flag 与「存储就绪」是**两件事**，不许合并成一个布尔 —— flag off → 接口整体
         404 `agent_stage_disabled`（门卫第一道，§7.1-⑫）；flag on 但表缺失 → 503（门卫第二道）。
         合并了前端就分不清「功能没开（整卡不渲染）」与「迁移没跑（请运维）」，这正是 §7.1-⑫
         要求区分 403 / 404 / 503 的同一条理由。
      2. **只看 0003 的三张表，不看 0004 的两个列**：`patient_records.template_id` /
         `template_version` 是**追加型引用列**，缺列时 ① 指标按 `template_id = 0` 的既有口径
         把这些样本计入 `skipped_no_template`（§3.2「排除样本」）—— 指标可降级，存储没坏。
         把它们绑进本探针，会让「少一个指标基准」升级成「阶段功能整体 503」，属方向性错误。
      3. **绝不建库 / 建表 / 写入，异常一律吞成 `False`**（只捕 `sqlite3.Error`，不 print、不抛）：
         接口层因此可以无条件调用它。注：库文件不存在时 `sqlite3.connect()` 会落地一个 0 字节文件
         —— 这是 `template_store_ready()` 同样存在的既有行为，本函数不额外做「路径存在性」判断，
         避免与 `database.DB_PATH` 的口径分叉。
    """
    try:
        conn = _store_connection()
        try:
            rows = conn.execute(
                "SELECT name FROM sqlite_master WHERE type = 'table' AND name IN (?, ?, ?)",
                AGENT_STAGE_STORE_TABLES,
            ).fetchall()
        finally:
            conn.close()
    except sqlite3.Error:
        return False
    return {row["name"] for row in rows} == set(AGENT_STAGE_STORE_TABLES)


# ----------------------------------------------------------------------------
# 骨架 ②：服务层错误类型（只定义形状，本步不产生任何实例）
# 形状与统一错误体一一对应，接口层可直出：
#     detail = {"error": exc.code, "msg": exc.msg, "errors": exc.errors, "warnings": exc.warnings}
# ----------------------------------------------------------------------------
class AgentStageError(Exception):
    """智能體階段服務層錯誤：帶機器碼，由接口層（`agent_stage_api.py`）翻譯成 HTTP 狀態碼（§4.5-① / §4.6）。

    形状与 `TemplateError`（`template_service.py:82-88`）**同构并各加一对**：除 `code` / `msg` 外再带
    `errors` / `warnings`，正好凑齐统一错误体 `{detail: {error, msg, errors, warnings}}`（§0.3 接口惯例）
    的四个键 —— 接口层不必再补键、也不必判断某键是否存在。

    四条边界（本步只定义形状）：
      · **只做浅拷贝、不校验元素形状**：`errors` 的元素形状由抛错方决定（配置校验用
        `[{"path", "msg"}]`，§3.4 第 5 条；阶段门控 / 状态机冲突用 `[]`），本类不做二次清洗。
      · `None` → `[]`（不是 `None`）：接口层直出 detail 时不允许出现 `null`，与 `TemplateError`
        的 `errors` / `warnings` 缺省口径一致（§4.5-② 统一错误体）。
      · **不继承 `TemplateError`**：那是 Epic 1 已验收代码，本 Epic 不复用、不改它；两条错误链各自由
        各自的接口层映射（§4.5-① 零改动清单：`template_service` / `template_api` 零改动）。
      · **不与 flag 绑定**：本异常在 flag off 时不会被抛出（接口层第一道门卫直接 404
        `agent_stage_disabled`），flag off 的单例语义由门卫保证，不由本类保证。
    """

    def __init__(self, code, msg, errors=None, warnings=None):
        super().__init__(msg)
        self.code = code
        self.msg = msg
        self.errors = list(errors or [])
        self.warnings = list(warnings or [])



