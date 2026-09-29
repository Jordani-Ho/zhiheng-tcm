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

import difflib
import json
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


# ============================================================================
# 【施工步骤 3.2】配置链（① 内置默认 / ② 四层读取链 / ③ 只拦不清的校验层）
#              + 阶段真值读取（④ `current_stage` / ⑤ `describe_stage`）
# ----------------------------------------------------------------------------
# CTO 2026-09-28 放行 step 3.2 的六条约束，本段逐条对应：
#   约束 1「配置链三符号」→ `DEFAULT_STAGE_CONFIG` / `load_stage_config` / `validate_stage_config`；
#   约束 2「阶段真值两符号」→ `current_stage` / `describe_stage`，四条路径（行在内且合法 / 行值非法 /
#     无行 / 读库异常）全部 **fail-closed 到 `default_stage`**；
#   约束 3「`load_stage_config` 三态」→ 行存在 / 行缺失 / JSON 损坏（外加 0003 未跑的 `sqlite3.Error`）；
#   约束 4「校验层只拦不清」→ 不回写入参、不删未知键、不补默认值；
#   约束 5「flag off 逐字节不变」→ 本段**不读 flag、不发写语句**：读数只发 SELECT，脏行不修、
#     审计不写（⑨ ⑪ ⑫ 组的改动前基线继续逐字节全绿）；
#   约束 6「⑭ 组即验收」→ 本段**零接线**（`database.py` / `main.py` / `agent_stage_api.py` 一字不动），
#     只有 ⑭ 组用例直接调用本段的 5 个符号。
#
# 三条 CTO 口径（2026-09-28 裁决，落地时不得自行改动）：
#   ① **读路径零写入**：§1.5 第 1 条写的「非法值记 `evaluation` 事件」**不在本步做** ——
#      `describe_stage` 撞见脏行只打告警 + 兜底，**一行不写**（⑭ 组 `test_stage_read_path_only_selects_
#      and_writes_nothing` / `test_describe_stage_illegal_row_value_degrades_to_default_stage` 都是硬断言）。
#      该留痕属施工步骤 3.4 的 `evaluate()`；口径已写进 `describe_stage` 的 docstring。
#   ② **`schema_version` 两条路径不矛盾**：`load_stage_config` 读到 ≠1 → **整份回落内置默认 + 告警、不抛**
#      （§3.5「未知版本 → 只用内置默认 + 告警，不抛错」）；`validate_stage_config` 被**直接调用**时
#      → `(False, [{"path": "schema_version", ...}])`（§3.4 第 5 条：写入校验必须拦住）。两条口径
#      分别写进两个函数的 docstring。
#   ③ **`config_source` 不在本步**：§3.4 第 4 条的 `{"global","teacher_override","env_override"}`
#      是「哪一层生效」的可回答性，属 step 4 的接口层返回体（§4.6）；本步只落 5 个符号 —— 现在塞一个
#      「名字在、行为不全」的 `config_source`，就正是 3.1 段警告过的那种假实现。
#
# 三条测试未覆盖的判定点（CTO 2026-09-28 裁决，落地口径）：
#   A. `pending_task_id` 坏值 → `degraded=False` + `[warn]`：`degraded` 的语义是「阶段**真值**读取失败」，
#      此处真值（`stage`）仍来自状态行，只有附带的请示号退化为 0，故不算降级（告警只为可定位）。
#   B. `template_match_weights` 只给部分键 → **放行**：校验层「只拦不清」，不做部分合并、不补默认权重
#      （补默认 = 静默清洗，正是 §3.4 第 5 条禁止的「部分生效」）。
#   C. `AGENT_STAGE_ENABLED` → **静默忽略**：它是已知总闸（`agent_stage_enabled()` 的唯一真相源），
#      不是配置键 —— 混进「未知环境变量」告警会误导运维去「配」它。
#
# 告警只有一个出口：`_config_warn()`（CTO 追加要求 1：不许散落 `print`）。文案一律繁体
# （CTO 追加要求 2），且含测试钉死的子串：損壞 / 不是 JSON 對象 / 未知的環境變量 X / 無法解析 /
# 非法 / 失敗。
# ============================================================================

# ---------------------------------------------------------------------------
# 【3.2-①】内置兜底默认（§3.5 键表，**全 Epic 唯一硬编码点**）
# 16 键逐字对齐 §3.5；键表增删**必须**同步设计文档（⑭ 组会拿文档原文交叉核对，见
# `test_default_stage_config_matches_design_key_table`）。本常量只读：`load_stage_config`
# 每次返回**新建对象**（含嵌套的 `template_match_weights`），调用方改它不得污染这里。
# ---------------------------------------------------------------------------
DEFAULT_STAGE_CONFIG = {
    "schema_version": 1,                    # 配置契约版本（§3.5）
    "default_stage": "learning",            # 未初始化老师的兜底阶段（只允许 observation / learning）
    "window_days": 90,                      # 指标统计窗口（天）
    "max_samples": 50,                      # 每指标最多取样本数（性能上限）
    "min_samples": 5,                       # 允许推荐升级的最少样本数
    "min_template_match": 0.75,             # ① 模板匹配度达标阈值
    "min_modification_consistency": 0.80,   # ② 病历修改一致率达标阈值
    "max_violations": 0,                    # 窗口内允许的铁律违规样本数
    "max_permission_denials": 0,            # 窗口内允许的越权次数
    "recommend_cooldown_hours": 24,         # 推荐 / 被拒后的冷却小时数
    "demote_consistency_floor": 0.50,       # 规则降级水位
    "demote_streak": 3,                     # 连续命中多少次才降级
    "truncate_chars": 2000,                 # 相似度计算前的文本截断长度
    "template_match_weights": {"section_hit": 0.6, "section_order": 0.4},   # ① 内部权重
    "metrics_ttl_hours": 24,                # `last_metrics_json` 的「新鲜」窗口
    "matrix_enforced": True,                # §2.5 的临时运维闸
}

# ---------------------------------------------------------------------------
# 【3.2-②】校验表（§3.4 第 5 条范围表的唯一真相源）
#   整数键 → (下界, 上界)；上界 None = 设计未给上界 → 只拦负数。
#   比率键 → 闭区间 [0, 1]；布尔键必须真的是 `bool`（`True` 是 `int` 子类，静默当 1 用＝静默清洗）。
# ---------------------------------------------------------------------------
_STAGE_CONFIG_INT_RANGES = {
    "window_days": (1, 3650),
    "max_samples": (1, 500),
    "min_samples": (1, 500),
    "truncate_chars": (200, 4000),
    "demote_streak": (1, 10),
    "max_violations": (0, 50),
    "max_permission_denials": (0, 100),
    "recommend_cooldown_hours": (0, None),
    "metrics_ttl_hours": (0, None),
}

_STAGE_CONFIG_RATIO_KEYS = (
    "min_template_match", "min_modification_consistency", "demote_consistency_floor",
)

# §1.5 结尾的 fail-safe 方向声明：`default_stage` 只能是这两个 —— 放行更高的阶段，
# 「读不到状态行」就等于「自动提权」。
_STAGE_CONFIG_DEFAULT_STAGES = ("observation", "learning")

# 契约版本（CTO 裁决②）：读取路径遇到别的版本 → 整份回落 + 告警；直接校验 → 报错。
_STAGE_CONFIG_VERSION = 1

# §3.4 第 2 条：env 白名单（**只含标量键**）。`schema_version` 是契约版本、`template_match_weights`
# 是复合键（env 的字符串无法无损表达它）→ 两者都只能走配置行。
_ENV_CONFIG_PREFIX = "AGENT_STAGE_"
_ENV_FLAG_NAME = "AGENT_STAGE_ENABLED"      # 总闸：已知，静默跳过（CTO 裁决 C）
_ENV_FALSY_VALUES = ("off", "0", "false", "no")   # 真值集合复用 AGENT_STAGE_ENABLED_VALUES（on/off 语义）
_ENV_CONFIG_VALUE_TYPES = {
    "default_stage": "str",
    "window_days": "int",
    "max_samples": "int",
    "min_samples": "int",
    "min_template_match": "float",
    "min_modification_consistency": "float",
    "max_violations": "int",
    "max_permission_denials": "int",
    "recommend_cooldown_hours": "int",
    "demote_consistency_floor": "float",
    "demote_streak": "int",
    "truncate_chars": "int",
    "matrix_enforced": "bool",
    "metrics_ttl_hours": "int",
}

# 告警里的层名（⑭ 组按子串断言「全局」/「老師專屬」）
_CONFIG_LAYER_GLOBAL = "全局"
_CONFIG_LAYER_TEACHER = "老師專屬"


def _config_warn(msg):
    """配置链 / 真值读取的**唯一**告警出口（CTO 追加要求 1：不允许散落 `print`）。

    走 stdout（与 `database.py` 的 `_agent_stage_snapshot_enabled()` 等既有「静默降级 + 留痕」
    同一先例：不引 logging 配置、不动 root logger），⑭ 组用 `capsys` 抓它，运维在 uvicorn
    控制台也能看见。文案一律繁体，且必须带**可定位信息**（原值 / 层名 / 键名 / 路径）——
    脏数据排查全靠它。
    """
    print("[warn] %s" % msg)


# ---------------------------------------------------------------------------
# 【3.2-③】校验层（§3.4 第 5 条）：返回 `(ok, errors)`，`errors: [{"path","msg"}]`
#   · **只拦不清**：不把坏值改成好值、不删未知键、不补缺失键（缺失 = 回落上一级，未知 = 前向兼容）；
#   · **一次全报**（不短路）→ 接口层 400 的 `errors` 直接给老师看，不用挤牙膏式修一处报一处；
#   · `path` 指名道姓（`template_match_weights.section_hit` 这种子路径也要精确）。
# ---------------------------------------------------------------------------
def _type_name(value):
    """错误文案里报类型（`NoneType` / `int` / `str` …），比 `%r` 更像人话。"""
    return type(value).__name__


def _is_number(value):
    """`True` / `False` **不是**数字：`bool` 是 `int` 子类，静默当 1 / 0 用就是静默清洗。"""
    return isinstance(value, (int, float)) and not isinstance(value, bool)


def _append_error(errors, path, msg):
    errors.append({"path": path, "msg": msg})


def _validate_int_key(key, value, errors):
    """整数键：类型必须是 `int`（拒 `bool` / 字符串 / 浮点）且落在 §3.4 的区间内。"""
    low, high = _STAGE_CONFIG_INT_RANGES[key]
    if not isinstance(value, int) or isinstance(value, bool):
        _append_error(errors, key, "必須是整數（收到 %s：%r）" % (_type_name(value), value))
        return
    if value < low:
        _append_error(errors, key, "必須 >= %d（收到 %d）" % (low, value))
    elif high is not None and value > high:
        _append_error(errors, key, "必須 <= %d（收到 %d）" % (high, value))


def _validate_ratio_key(key, value, errors):
    """比率键：闭区间 [0, 1]（`NaN` 落进「不在区间内」分支 → 报错，天然 fail-closed）。"""
    if not _is_number(value):
        _append_error(errors, key, "必須是 0 ~ 1 之間的數（收到 %s：%r）" % (_type_name(value), value))
        return
    if not 0.0 <= value <= 1.0:
        _append_error(errors, key, "必須在 0 ~ 1 之間（收到 %r）" % (value,))


def _validate_weights(weights, errors):
    """① 内部权重（§3.4 第 5 条：各项非负且和 > 0）。

    只校验**给出来的项**（部分键放行 —— CTO 裁决 B）：不补默认权重、不做部分合并。
    """
    if not isinstance(weights, dict):
        _append_error(errors, "template_match_weights",
                      "必須是物件（收到 %s：%r）" % (_type_name(weights), weights))
        return
    total = 0.0
    for name in sorted(weights, key=str):
        value = weights[name]
        path = "template_match_weights.%s" % (name,)
        if not _is_number(value):
            _append_error(errors, path, "權重必須是數（收到 %s：%r）" % (_type_name(value), value))
            continue
        if value < 0:
            _append_error(errors, path, "權重不得為負（收到 %r）" % (value,))
            continue
        total += value
    if total <= 0:
        _append_error(errors, "template_match_weights", "各項權重之和必須大於 0")


def validate_stage_config(cfg):
    """§3.4 第 5 条「两层校验」的校验器（写入前 + 读取后都跑），返回 `(ok, errors)`。

    校验口径（逐条对齐 §3.4 第 5 条）：
      · 根必须是 JSON 对象；否则 → **一条**错误、`path = ""`（「请求体本身就不是配置对象」）；
      · `schema_version` 必须是整数 `1`；
      · 整数键见 `_STAGE_CONFIG_INT_RANGES`；跨键要求 `min_samples <= max_samples`；
      · 比率键 ∈ [0, 1]；`template_match_weights` 各项非负且和 > 0；
      · `default_stage` ∈ {observation, learning}（fail-closed 的关键一条：兜底不许自动提权）；
      · `matrix_enforced` 必须真的是 `bool`。

    `schema_version` 口径（CTO 裁决②，两条路径并存、不矛盾）：**直接调用本函数**时未知版本要报错
    （写入校验必须拦住）；而 `load_stage_config` 读到未知版本走的是「整份回落内置默认 + 告警、
    **不抛**」（§3.5：不让脏数据炸掉整条链路）。

    **只拦不清**（⑭ 组 `test_validate_stage_config_reports_all_errors_and_never_cleans` 硬断言）：
    入参一个字节都不改 —— 不删非法键、不改坏值、不补默认值、不合并部分权重；缺失键视为合法
    （回落上一级）、未知键视为合法（前向兼容）。多处非法**一次全报**，不短路。
    """
    if not isinstance(cfg, dict):
        return False, [{"path": "", "msg": "階段配置必須是一個 JSON 物件（收到 %s：%r）"
                        % (_type_name(cfg), cfg)}]

    errors = []

    if "schema_version" in cfg:
        version = cfg["schema_version"]
        if isinstance(version, bool) or not isinstance(version, int) or version != _STAGE_CONFIG_VERSION:
            _append_error(errors, "schema_version",
                          "只支援 schema_version = %d（收到 %s：%r）"
                          % (_STAGE_CONFIG_VERSION, _type_name(version), version))

    for key in sorted(_STAGE_CONFIG_INT_RANGES):
        if key in cfg:
            _validate_int_key(key, cfg[key], errors)

    # 跨键关系（§3.4 第 5 条：1 <= min_samples <= max_samples <= 500）
    min_samples = cfg.get("min_samples")
    max_samples = cfg.get("max_samples")
    if (isinstance(min_samples, int) and not isinstance(min_samples, bool)
            and isinstance(max_samples, int) and not isinstance(max_samples, bool)
            and min_samples > max_samples):
        _append_error(errors, "min_samples",
                      "不得大於 max_samples（%d > %d）" % (min_samples, max_samples))

    for key in _STAGE_CONFIG_RATIO_KEYS:
        if key in cfg:
            _validate_ratio_key(key, cfg[key], errors)

    if "default_stage" in cfg:
        stage = cfg["default_stage"]
        if stage not in _STAGE_CONFIG_DEFAULT_STAGES:
            _append_error(errors, "default_stage",
                          "只允許 observation / learning（fail-closed，收到 %r）" % (stage,))

    if "matrix_enforced" in cfg and not isinstance(cfg["matrix_enforced"], bool):
        _append_error(errors, "matrix_enforced",
                      "必須是布林值（收到 %s：%r）"
                      % (_type_name(cfg["matrix_enforced"]), cfg["matrix_enforced"]))

    if "template_match_weights" in cfg:
        _validate_weights(cfg["template_match_weights"], errors)

    return (not errors), errors


# ---------------------------------------------------------------------------
# 【3.2-④】读取链（§3.4 第 1–3 条）：内置默认 ← 全局行 ← 老师专属行 ← env 白名单
#   · 逐键**浅合并**；未知键原样保留（前向兼容）；缺失键回落上一级；
#   · **每次现读、不缓存**（灰度调参不必重启 uvicorn）；
#   · **只发 SELECT**（读数零写入 —— ⑭ 组有语句级断言）：脏行不修、审计不写。
# ---------------------------------------------------------------------------
def _copy_config(config):
    """配置对象的**深拷贝**（JSON 往返）：`load_stage_config` 每次返回新对象，调用方改它
    （含嵌套的 `template_match_weights`）不得污染 `DEFAULT_STAGE_CONFIG` / 上一次的结果。"""
    return json.loads(json.dumps(config, ensure_ascii=False))


def _parse_env_value(key, raw):
    """把 env 字符串按该键的类型转成配置值：成功 → `(值, True)`；无法解析 → `(None, False)`。

    · 整数 / 浮点键：`int()` / `float()` 失败即「無法解析」（**只忽略该键**，不炸整条链路）；
    · 布尔键（`matrix_enforced`）：`on` / `1` / `true` / `yes` → `True`，`off` / `0` / `false` /
      `no` → `False`（与总闸 `agent_stage_enabled()` 同一套 on/off 语义），其余一律「無法解析」；
    · 阶段名（`default_stage`）：去前后空白 + 统一小写（`"  Observation  "` → `observation`）；
      **合法性不在这一层判** —— 交给校验层，于是 `AGENT_STAGE_DEFAULT_STAGE=apprentice` 只会导致
      「整份回落内置默认 + 告警」，绝不会被静默采纳成兜底阶段。
    """
    kind = _ENV_CONFIG_VALUE_TYPES[key]
    text = raw.strip()
    if kind == "int":
        try:
            return int(text), True
        except ValueError:
            return None, False
    if kind == "float":
        try:
            return float(text), True
        except ValueError:
            return None, False
    if kind == "bool":
        lowered = text.lower()
        if lowered in AGENT_STAGE_ENABLED_VALUES:
            return True, True
        if lowered in _ENV_FALSY_VALUES:
            return False, True
        return None, False
    return text.lower(), True


def _merge_config_layer(merged, row, layer):
    """把某一层的 `config_json` 逐键合并进 `merged`。

    损坏（非法 JSON）/ 非对象（数组 / 字符串 / null / 数字）→ 该层按「无覆盖」处理 + 告警，
    **只丢坏的那一层**：全局行坏了，老师专属行照样生效（不是整份回落内置默认）。
    """
    raw = row.get("config_json")
    if isinstance(raw, str):
        try:
            parsed = json.loads(raw)
        except ValueError:
            _config_warn("配置行損壞（%s行的 config_json 不是合法 JSON），該層按無覆蓋處理：%r"
                         % (layer, raw))
            return
    else:
        parsed = raw
    if not isinstance(parsed, dict):
        _config_warn("配置行不是 JSON 對象（%s行的 config_json 是 %s），該層按無覆蓋處理"
                     % (layer, _type_name(parsed)))
        return
    for key, value in parsed.items():
        merged[key] = value


def _format_errors(errors):
    """把 `[{"path","msg"}]` 压成一行人话（告警 / 日志用），保留可定位的路径。"""
    return "；".join("%s（%s）" % (item["path"] or "<根>", item["msg"]) for item in errors)


def _apply_env_overrides(merged):
    """§3.4 第 2 条：env 白名单覆盖（四层里的最高一层）。

    `AGENT_STAGE_` 前缀的**每一个**环境变量都会被看到（⑭ 组用 typo 键 `AGENT_STAGE_WINDOWDAYS`
    钉住这条）：
      · 不在白名单 → 告警「未知的環境變量 X」（防 typo 静默生效）；
      · 在白名单但值无法解析 → 告警「無法解析」并**只忽略该键**，其余层照常；
      · `AGENT_STAGE_ENABLED`（总闸）→ **静默跳过**（CTO 裁决 C：它是 `agent_stage_enabled()` 的
        真相源、不是配置键，混进「未知」告警会误导运维去「配」它）。
    """
    for name in sorted(os.environ):
        if not name.startswith(_ENV_CONFIG_PREFIX):
            continue
        if name == _ENV_FLAG_NAME:
            continue
        key = name[len(_ENV_CONFIG_PREFIX):].lower()
        if key not in _ENV_CONFIG_VALUE_TYPES:
            _config_warn("未知的環境變量 %s（不在白名單內，已忽略）" % name)
            continue
        raw = os.environ[name]
        value, parsed_ok = _parse_env_value(key, raw)
        if not parsed_ok:
            _config_warn("無法解析環境變量 %s 的值 %r（已忽略該鍵，其餘層照常）" % (name, raw))
            continue
        merged[key] = value


def load_stage_config(teacher_name):
    """§3.4 的四层读取链：内置默认 ← 全局行（`teacher_name=''`）← 老师专属行 ← env 白名单。

    返回**新建**配置对象（含嵌套权重）；**每次调用现读**（不缓存 → 改 env / 改行立刻生效）。

    三态降级（**绝不抛**，与 §1.5 第 3 条同方向）：
      · **行缺失** → 该层无覆盖（正常态：新老师还没有专属行 / 全局行尚未种子 → **零告警**）；
      · **JSON 损坏 / 不是 JSON 对象** → 只丢坏的那一层 + 告警；
      · **库层异常**（`sqlite3.Error`：0003 未跑 / 库被锁）→ 该层无覆盖 + 告警「失敗」。
    合并完再跑一次 `validate_stage_config`：**非法值整份回落内置默认 + 告警**（§3.4 第 5 条
    「读取时非法 → 回落内置默认」）—— 刻意不「只丢那一个键」：半脏值 + 半默认混在一起，老师看到的
    阈值来源就再也解释不清了。

    `schema_version` 口径（CTO 裁决②）：读到未知版本 → 校验层报 `schema_version` → **整份回落
    内置默认 + 告警、不抛**（§3.5）；需要「直接拿到错误清单」的写入路径走 `validate_stage_config`。

    本函数**只读**：全程只发 SELECT（⑭ 组 `sql_log` 语句级断言），不建行 / 不改行 / 不写审计。
    """
    import database      # 只在**函数体内**延迟 import（§4.5-①；方向守护见 ⑩ 组）

    merged = _copy_config(DEFAULT_STAGE_CONFIG)

    for layer, name in ((_CONFIG_LAYER_GLOBAL, ""), (_CONFIG_LAYER_TEACHER, teacher_name)):
        if layer == _CONFIG_LAYER_TEACHER and not teacher_name:
            continue        # 全局行就是这一行，不重复读
        try:
            row = database.get_agent_stage_config_row(name)
        except sqlite3.Error as exc:
            _config_warn("讀取%s配置失敗（%s），該層按無覆蓋處理（改用內置默認）" % (layer, exc))
            continue
        if row is None:
            continue
        _merge_config_layer(merged, row, layer)

    _apply_env_overrides(merged)

    ok, errors = validate_stage_config(merged)
    if not ok:
        _config_warn("合併後的階段配置非法，已整份回落內置默認：%s" % _format_errors(errors))
        return _copy_config(DEFAULT_STAGE_CONFIG)
    return merged


# ---------------------------------------------------------------------------
# 【3.2-⑤】阶段真值读取（§1.5 四条路径，fail-closed 到 `default_stage`）
#   ① 行在内且合法 → 原样采用（**只发那一条 SELECT**：不调配置链、不产生无关告警）；
#   ② 行在但 `stage` 白名单外（人手 SQL 写坏 / 高版本数据）→ 告警 + 兜底 + `degraded=True`；
#   ③ 无行（未初始化，正常态）→ 配置链的 `default_stage`、`degraded=False`、**不写库**；
#   ④ 读库异常（0003 未跑 / 库被锁）→ 配置链的 `default_stage` + `degraded=True`、**绝不抛**。
#   只有 ② ③ ④ 走配置链；四条路径的返回体形状完全一致（接口层直出）。
# ---------------------------------------------------------------------------
def _coerce_pending_task_id(value):
    """`pending_task_id` 的读数兜底：库列无 CHECK（§1.2），被人手 SQL 写成字符串时不炸 500。

    降级成 `0` **不算 `degraded`**（CTO 裁决 A）：`degraded` 的语义是「阶段**真值**读取失败」，
    而此处真值（`stage`）仍来自状态行；只留一条告警用于定位。
    """
    try:
        return int(value)
    except (TypeError, ValueError):
        _config_warn("狀態行的 pending_task_id 無法解析：%r，已降級為 0（庫列無 CHECK，屬人手 SQL 寫壞）"
                     % (value,))
        return 0


def _describe_stage_fallback(teacher_name, degraded, failure=None):
    """② ③ ④ 三条路径的公共返回体：阶段取**配置链**的 `default_stage`（fail-closed）。

    `failure` 非空 = 需要留痕的降级（② 行值非法 / ④ 读库异常）；③ 无行属正常态 → 传 `None`、零告警。
    兜底阶段过了配置链的校验，只可能是 `observation` / `learning`，权限因此永远不会被放大。
    """
    config = load_stage_config(teacher_name)
    stage = config.get("default_stage")
    if stage not in STAGES:     # 理论不可达：配置链已整份校验过 default_stage
        stage = DEFAULT_STAGE_CONFIG["default_stage"]
    if failure is not None:
        _config_warn("%s（兜底階段「%s」）" % (failure, STAGE_LABELS[stage]))
    return {
        "teacher_name": teacher_name,
        "stage": stage,
        "stage_label": STAGE_LABELS[stage],
        "stage_since": "",
        "stage_source": "default",
        "pending_stage": "",
        "pending_task_id": 0,
        "degraded": degraded,
    }


def describe_stage(teacher_name):
    """§1.5 的阶段真值读取（**接口层直出体**，固定 8 键：`teacher_name` / `stage` / `stage_label` /
    `stage_since` / `stage_source` / `pending_stage` / `pending_task_id` / `degraded`）。

    `stage_label` 走唯一真相源 `STAGE_LABELS`（繁体徽章）；`stage_source` 取值见 §1.2
    （`default` / `teacher_confirm` / `manual_demote` / `rule_demote` / `rule_reset`）；
    `degraded` **只有「阶段真值读不到」才为 True**（② 行值非法 / ④ 读库异常）—— 无行（③）
    与 `pending_task_id` 坏值都不算降级（后者见 `_coerce_pending_task_id`）。

    四条路径（§1.5）：
      ① **行在内且 `stage` 合法** → 原样采用：**只发那一条 SELECT**，不调配置链、不产生无关告警；
      ② 行在但 `stage` 白名单外 → `[warn]`（**含原值**，便于定位）+ 兜底 `default_stage` +
        `degraded=True`，且 **`stage_since` 一并不采用**（阶段已不是那一行的阶段，带上它的时间会
        误导前端）；
      ③ 无行（未初始化 = 正常态）→ 配置链的 `default_stage` + `degraded=False`，**不写库**
        （写一行假状态会把「未初始化」变成「已初始化成默认值」，将来想区分就再也分不清了）；
      ④ 读库异常（0003 未跑 / 库被锁）→ `[warn]` + 兜底 + `degraded=True`，**绝不抛**
        （§1.5 第 3 条：不许把存储故障抛给既有链路）。

    **本函数零写入**（CTO 裁决①）：撞见非法行**只告警、不修行、不打审计** —— ⑭ 组用
    「`agent_stage_state` 行数不变 + `agent_stage_log` 增量为零 + 全程只发 SELECT」三条硬断言钉住。
    §1.5 第 1 条提到的「非法值记 `evaluation` 事件」属**施工步骤 3.4 的 `evaluate()`** 职责
    （评估流程 + 审计），读路径不做。
    """
    import database      # 只在**函数体内**延迟 import（§4.5-①；方向守护见 ⑩ 组）

    name = teacher_name or ""
    try:
        row = database.get_agent_stage_state(name)
    except sqlite3.Error as exc:
        return _describe_stage_fallback(
            name, True, "讀取智能體階段狀態失敗（%s），已降級到配置鏈的兜底階段" % (exc,))
    if row is None:
        return _describe_stage_fallback(name, False)

    stage = row.get("stage")
    if stage not in STAGES:
        _config_warn("狀態行的 stage 值非法：%r 不在五階段枚舉內（白名單外 / 高版本數據），"
                     "已降級到配置鏈的兜底階段；本函數零寫入，髒行留痕屬評估流程職責" % (stage,))
        return _describe_stage_fallback(name, True)

    return {
        "teacher_name": name,
        "stage": stage,
        "stage_label": STAGE_LABELS[stage],
        "stage_since": row.get("stage_since") or "",
        "stage_source": row.get("stage_source") or "default",
        "pending_stage": row.get("pending_stage") or "",
        "pending_task_id": _coerce_pending_task_id(row.get("pending_task_id")),
        "degraded": False,
    }


def current_stage(teacher_name):
    """当前阶段的**标量**视图（恒为 `STAGES` 内的字符串）—— 唯一读库实现仍是 `describe_stage`。

    给内部判定用（3.3 的 `require_capability` / 3.4 的评估）：它们只关心「哪个阶段」，不需要 8 键
    视图；两条读路径必须**同源**（⑭ 组 `test_current_stage_is_scalar_matching_describe`），
    所以本函数不写第二份读库实现 —— 免得将来两处 fail-closed 口径漂移。
    """
    return describe_stage(teacher_name)["stage"]



# ============================================================================
# 【施工步骤 3.3】能力闸门（`require_capability`，§2.2 / §2.3 的**唯一**判定点）
# ----------------------------------------------------------------------------
# CTO 2026-09-28 放行 step 3.3 的六条约束，本段逐条对应：
#   约束 1「矩阵必须是显式数据结构」→ 判定表复用 step 1 已落地的 `CAPABILITY_MATRIX`（§2.3 逐格
#     字面量）；本段只补两个**枚举常量**（flag off 的既有行为例外 / `matrix_enforced=False` 的
#     放宽范围），`require_capability` 体内**只有查表**：零 `if capability == "…"` 分支
#     （源码级守护见 ⑮ 组 `test_require_capability_body_has_no_capability_branches`）；
#   约束 2「白名单、默认拒绝」→ 判定四步写在函数 docstring 里；矩阵**缺格一律拒**
#     （`.get(stage, {}).get(cap, False)`：将来新增阶段忘了补表也是 fail-closed）；
#   约束 3「拒绝同点写审计」→ `_stage_audit()` 在**同一个拒绝点**写 `permission_denied` 事件
#     （当前阶段 / 被拒能力 / 时间三要素齐全），写失败只告警、**绝不改变判定结果**（§2.4
#     「拒绝先于日志」）；
#   约束 4「三不铁律独立于开关」→ 三不是「**不存在的能力**」（§2.1：永不诊断 / 永不开方 /
#     永不签字）：代码级形态 = 能力键不在 `CAPABILITIES` 内 → 枚举外**恒拒**，与 flag、
#     `matrix_enforced` 都无关（配置只能放宽 §2.3 表内已有的格子，造不出不存在的格子）；
#   约束 5「返回 bool、拒绝不抛」→ 本函数只返回 `bool`；`AgentStageError('stage_forbidden')`
#     的抛出点在接口层（step 4，§4.6：`if not require_capability(...): raise`）；
#   约束 6「⑮ 组即验收」→ 本段**零接线**（`main.py` / `database.py` / `agent_stage_api.py`
#     一字不动），只有 ⑮ 组用例直接调用本函数。
#
# 三条落地口径（本段自行钉死，⑮ 组逐条覆盖）：
#   A. **flag off → 零 DB 访问、零审计**：总闸 off 时只放行 §2.3 指定的既有能力例外
#      （`LEGACY_ALLOWED_WHEN_DISABLED`），其余一律拒，且**连 SELECT 都不发**、不写审计 ——
#      此时拒绝的语义是「功能没开」（接口层第一步就 404 `agent_stage_disabled`，走不到本函数），
#      而 §5.1 红线① 要求 flag off 不许写任何新表；
#   B. **`matrix_enforced=False` 只放宽 §2.5 逐项枚举的三个新能力**（`predict_pattern` /
#      `suggest_prescription` / `generate_predraft`）：`generate_draft` 在 `observation` 期仍为
#      `False` —— 那一格表达的不是「越权门」而是 §5.3 的本地骨架路径（观察期智能体不参与，
#      属产品语义，不是权限）。放宽下的**放行也留痕**（§2.5 ③ 的反向事件 `permission_relaxed`），
#      避免「静默放宽」；
#   C. 开关 `matrix_enforced` **取自四层配置链**（`load_stage_config`，每调用现读）：配置读坏 →
#      整份回落内置默认（`True` = 继续强制）→ 「读不到配置」永远不会变成「权限放大」（fail-closed）。
#
# 告警统一走 3.2 落地的 `_config_warn()`（单一出口，本段不新增 `print`）；文案一律繁体。
# ----------------------------------------------------------------------------
# 【事件名已裁决 · 2026-09-29】设计文档 §1.3 / §2.4 / §6.2-14 **三处一致**写 `permission_denied`，
# CTO 裁决以**文档契约**为准（事件名是契约，历史数据不能分裂）；step 3.3 期间的临时名
# `capability_denied` **已废弃**，本段一律用文档名（同样收敛成常量；§1.3 已补 `permission_relaxed`，
# 9 类 → 10 类，对应 §2.5 ③ 的权限放宽反向事件）。
_LOG_EVENT_PERMISSION_DENIED = "permission_denied"
_LOG_EVENT_PERMISSION_RELAXED = "permission_relaxed"

# flag off 时的既有行为例外（§2.3：「flag off 的特例：`cap == 'generate_draft'` 恒放行 …… 该特例
# **只写一处**，不得散落」）：名字与语义逐字对齐设计伪码，收敛成这**唯一**一处定义。
LEGACY_ALLOWED_WHEN_DISABLED = {"generate_draft"}

# `matrix_enforced=False` 的放宽范围（§2.5 作用域「只关闭 L2 阶段门控」并**逐项枚举**的三项）。
# 刻意不含 `generate_draft`（理由见上文口径 B）与 `record_observation`（它本就全员可用）。
_MATRIX_RELAXED_CAPABILITIES = ("predict_pattern", "suggest_prescription", "generate_predraft")


def _matrix_allows(stage, capability):
    """查表（约束 1：判定只有查表）：`CAPABILITY_MATRIX[stage][capability]`，**缺阶段 / 缺格 → False**。

    单点转调（而非在闸门里内联下标）让「矩阵是数据」在源码层也成立：将来新增阶段或能力只需改
    常量表，判定逻辑零改动；忘了补表也只是该格恒拒（fail-closed），不会变成放行。
    """
    return bool(CAPABILITY_MATRIX.get(stage, {}).get(capability, False))


def _audit_capability(value):
    """审计 `capability` 列的取值（TEXT 列）：未知 / 非字符串入参（`None` / 数字 / 拼写错的键）也留痕。"""
    return value if isinstance(value, str) else repr(value)


def _permission_denied_detail(capability, stage):
    """越权拒绝的**可解释文案**（繁体，§2.4 的「未達階段」口径）：`[warn]` 与审计 `detail` 共用。

    只用 §4.5-① 已公开的两个真相源（`CAPABILITY_MIN_STAGE` / `STAGE_LABELS`）拼出「差多少」，
    不新增标签常量 —— step 4 接口层拼 403 文案的同样是这两个常量。
    """
    label = STAGE_LABELS.get(stage, stage)
    # 入参可能不是字符串（接口层传错类型 / 请求体里塞了别的类型）：`dict.get()` 只接受可哈希键，
    # 传 list / dict 会抛 `TypeError: unhashable type`；闸门「永不抛」是硬约束（CTO 约束 5），
    # 故非字符串一律按「枚舉外的鍵」处理（下面的 `%r` 照旧留下可读值）。
    need = CAPABILITY_MIN_STAGE.get(capability) if isinstance(capability, str) else None
    if need is None:
        return ("智能體越權被拒：能力鍵 %r 不在能力枚舉內（未知 / 拼寫錯誤 / 憲法層禁止的能力），"
                "白名單外一律拒絕；當前階段「%s」" % (capability, label))
    return ("智能體越權被拒：能力「%s」需達「%s」，當前階段為「%s」，尚未開放"
            % (capability, STAGE_LABELS[need], label))


def _stage_audit(event_type, teacher_name, capability, from_stage, detail):
    """`agent_stage_log` 的 best-effort 单条写入（CTO 约束 3：拒绝**同点**写审计）。

    字段口径照 §1.3：`from_stage` = 当前阶段、`capability` = 被拒 / 被放宽的能力键、`to_stage` =
    `''`（非变更类事件）、`task_id` = `0`（与升级请示无关）、`metrics_json` = `{}`（§1.3 明写
    「`permission_denied` 也为空对象 `{}`，不做特例」）、`created_at` 由库层补（= 时间要素）。
    只增不改（① 组「审计表无 update / delete 函数」守护照旧成立）。

    **写失败不得改变判定结果**（§2.4「拒绝先于日志，日志包 try/except」）：`sqlite3.Error`
    （0003 未跑 / 库被锁）与任何载荷异常都在此吞掉、只留一条繁体告警；返回 `None` 时调用方
    **照旧**返回原判定。捕获面刻意放宽到 `Exception`：审计是旁路，任何情况下都不许把「拒绝」
    变成 500，更不许把「放行」变成拒绝。
    """
    try:
        import database      # 只在**函数体内**延迟 import（§4.5-①；方向守护见 ⑩ 组）
        return database.insert_agent_stage_log(
            teacher_name, event_type,
            from_stage=from_stage, to_stage="", capability=capability,
            task_id=0, metrics_json={}, detail=detail,
        )
    except Exception as exc:
        _config_warn("寫入階段審計失敗（%s）：event_type=%r capability=%r，判定結果不受影響"
                     % (exc, event_type, capability))
        return None


def require_capability(teacher_name, capability):
    """**唯一能力闸门**（§2.2：接口层、生成路径接入点与内部嵌套调用都必须经它）—— 返回 `bool`，
    **永不抛**（CTO 约束 5）。越权语义（403 `stage_forbidden`）由接口层翻译，本函数只回答「能不能」。

    判定四步（全部 fail-closed）：

      ① **总闸**（§2.3 / §5.1 红线①）：`AGENT_STAGE_ENABLED` off → 只放行
         `LEGACY_ALLOWED_WHEN_DISABLED` 里的既有能力（今天的生成路径必须 1:1），其余一律 `False`；
         off 时**零 DB 访问、零审计** —— 此时拒绝的语义是「功能没开」，接口层第一步就 404
         `agent_stage_disabled`，走不到这里；而「flag off 不写任何新表」是红线① 的硬要求。
      ② **能力白名单**（约束 2 / 约束 4）：`capability` 不在 `CAPABILITIES` 内（未知 / 拼写错 /
         非字符串 / 三不铁律的键）→ `False`。这是 §2.1 三条铁律（永不诊断 / 永不开方 / 永不签字）
         的**代码级形态**：铁律不是「可放宽的阶段门」，而是**不存在的能力键**。
      ③ **阶段矩阵**（§2.3）：`current_stage(teacher_name)`（§1.5 fail-closed 到 `default_stage`）→
         `CAPABILITY_MATRIX[stage][capability]`，缺格 = `False`。
      ④ **放宽开关**（§2.5）：`matrix_enforced=False` 时，仅 `_MATRIX_RELAXED_CAPABILITIES` 里的
         三个新能力放行，且**放行也留痕**（反向事件 `permission_relaxed`，不许静默放宽）。开关现读
         四层配置链：配置读坏 → 整份回落内置 `True` → 继续强制（fail-closed，读不到配置绝不放大权限）。

    拒绝的留痕（约束 3）：一行 `[warn]`（走 `_config_warn` 单一出口）+ `agent_stage_log` 一条事件
    （事件名 `_LOG_EVENT_PERMISSION_DENIED` = §1.3 契约名，含当前阶段 / 被拒能力 / 时间）；**写失败不影响返回值**。

    调用约定（step 4 起）：`if not require_capability(teacher, cap): raise AgentStageError(
    'stage_forbidden', ...)` —— 403 的可解释文案由接口层用 `describe_stage` + `STAGE_LABELS` +
    `CAPABILITY_MIN_STAGE` 组装（本步不新增符号，签名按约束 5 钉死为「返回 bool」）。
    """
    name = teacher_name or ""
    cap = capability if isinstance(capability, str) else None

    if not agent_stage_enabled():
        if cap in LEGACY_ALLOWED_WHEN_DISABLED:
            return True
        _config_warn("智能體階段功能未啟用（AGENT_STAGE_ENABLED off），能力 %r 不予放行"
                     "（此路徑不讀庫、不寫審計）" % (capability,))
        return False

    stage = current_stage(name)         # ③ 真值读取（§1.5 四条路径，fail-closed 到 default_stage）

    if cap is None or cap not in CAPABILITIES:
        detail = _permission_denied_detail(capability, stage)
        _config_warn(detail)
        _stage_audit(_LOG_EVENT_PERMISSION_DENIED, name, _audit_capability(capability), stage, detail)
        return False

    if _matrix_allows(stage, cap):
        return True

    if cap in _MATRIX_RELAXED_CAPABILITIES and not load_stage_config(name).get("matrix_enforced", True):
        detail = ("權限矩陣已由管理員放寬（臨時，matrix_enforced=False）：能力「%s」本應在「%s」"
                  "才開放，當前階段「%s」予以放行"
                  % (cap, STAGE_LABELS[CAPABILITY_MIN_STAGE[cap]], STAGE_LABELS.get(stage, stage)))
        _config_warn(detail)
        _stage_audit(_LOG_EVENT_PERMISSION_RELAXED, name, cap, stage, detail)
        return True

    detail = _permission_denied_detail(cap, stage)
    _config_warn(detail)
    _stage_audit(_LOG_EVENT_PERMISSION_DENIED, name, cap, stage, detail)
    return False


# ============================================================================
# 【施工步骤 3.4-a】指标层：① 模板匹配度 + ② 病历修改一致率（§3.2 / §3.3）
# ----------------------------------------------------------------------------
# CTO 2026-09-29 放行 step 3.4-a 的边界，本段逐条对应：
#   约束 1「3.4 含 ①②，批 1 = 3.4-a」→ 本段落 §4.5-① 的两个公开符号
#     `compute_template_match(teacher_name, cfg)` /
#     `compute_modification_consistency(teacher_name, cfg)`，
#     外加库层一个**只读**原语 `database.get_draft_samples()`（批复 C-1：窗口 + 类型过滤 + LIMIT）。
#     批复 C-2 的 `get_agent_stage_log_stats()`（越权计数 / 推荐冷却）属 **3.4-b**，与 `evaluate`
#     同批落地 —— 本步不放「名字在、无人调」的空壳（3.1 段已定过这条纪律：假实现比缺席更坏）。
#   约束 2「空集语义 `value=None` ≠ 0」→ 两个指标各有 `_BLOCKER_*_NO_SAMPLES` 分支；
#     「空值不得通过任何阈值」的**判定侧**属 3.4-b，本步用 ⑯ 组钉住不变量：`value is None`
#     且 `None` 与阈值比较会抛 `TypeError`（3.4-b 只能显式 `is not None`，没有静默通过的空间）。
#   约束 3「本批只做 3.4-a」→ 不改 `database.py` 既有函数签名 / `main.py` / `agent_stage_api.py`；
#     只**追加**一个库层只读函数（批复 C）。本段**零写入**：不发 INSERT / UPDATE / DELETE，
#     不写状态行、不写审计（落盘与事件属 `evaluate`，3.4-b）。
#   约束 4「不引依赖」→ 只用 stdlib `difflib`（§3.3 的 `SequenceMatcher`）；§3.2 的 `LCS` 用
#     20 × 20 的 DP 表算**严格** LCS（括号里的 `difflib` 是实现提示：它的块匹配会系统性低估
#     `order_rate`，口径与实测见 `_lcs_length()`）。
#
# 三条口径（本段自行钉死，⑯ 组逐条覆盖，汇报里列清）：
#   口径 A「当前 active `record` 模板」= `template_service.get_active_record_template(teacher_name)`
#     （§4.5-① 允许服务层只读它）：该函数自带 `TEMPLATE_API_ENABLED` 闸门 + 表就绪探测 +
#     schema 版本判定 → 返回 `None` 即「此刻没有生效病历模板」= ① **无基准** →
#     `value=None` + `blockers=["no_active_record_template"]`。**不算 0 分**：0 分会变成
#     「智能体不守模板」的错误指控（空值 ≠ 差评，§3.2 空集语义的同一方向）。
#   口径 B「① 的标题识别是纯文本规则、零 LLM」（§3.2）：允许的写法差异**只**有三类，全部写死在
#     `_normalize_section_text()` / `_split_heading()` / `_heading_matches()` 里 ——
#       ① 行首列表符（`- ` / `* ` / `· `）与 `【】` / `[]` / `〔〕` / `《》` 包裹；
#       ② `（留待老師）` 这类**提示性尾巴**（`_SECTION_HEADING_TAILS` 逐条枚举，含简体写法）；
#       ③ 句末标点。
#     **不做**简繁互换、**不做**缩写匹配、**不做**相似度匹配：模糊化会静默放大指标，而模板标题
#     是 §9.2 规定的 1–20 字完整标签（`_section_metas()` 按 `order` 取值）。
#   口径 C「样本一律走库层那一条只读原语」：服务层不拼 SQL、不认识 `sqlite3.Row` 的列形状；
#     `max_samples` 的「取前 N 条」由两个指标**各自**完成（① 只看命中当前模板的样本、② 只看
#     已签字病历），于是同一个样本集能同时服务两个指标而互不挤占（读取原语每个来源各取 `limit` 行）。
#
# 告警统一走 3.2 落地的 `_config_warn()`（单一出口，本段不新增 `print`）；文案一律繁体。
# ============================================================================

# 样本行的「类型」标记（与 `database.get_draft_samples()` 的 `source` 键**同字面量**）
_SAMPLE_SOURCE_RECORD = "record"    # 已签字病历（`patient_records`）
_SAMPLE_SOURCE_DRAFT = "draft"      # 未签字草案（`drafts`）

# `blockers` 文案（§3.2 / §3.3 逐字；`no_active_record_template` 见上文口径 A）
_BLOCKER_TEMPLATE_MATCH_NO_SAMPLES = "template_match_no_samples"
_BLOCKER_MODIFICATION_NO_SAMPLES = "modification_consistency_no_samples"
_BLOCKER_NO_ACTIVE_TEMPLATE = "no_active_record_template"

# 行首列表符（归一化时剥掉；`- 舌象：…` / `* 脈象` / `· 辨證` 这些写法因此可识别）。
# **刻意不含** `【` / `[` / `〔` / `《`：包裹符由 `_split_heading()` 按「配对的首尾」成对剥，
# 在这里逐字符剥会把 `【主訴（學生原話）】` 切成 `主訴（學生原話）】`（留下半个 `】`）→ 标题比对全错。
_SECTION_LINE_PREFIXES = ("-", "*", "·", "•", "|", "丨")

# 「留待老師」提示语的词元（违规判定的白名单：这些词被剔除后仍为空 → **不算**填了内容）
_PLACEHOLDER_WORDS = ("留待老師", "留待老师", "智能體永不填", "智能体永不填", "智能體永不填寫")

# 允许出现在标题后的**提示性尾巴**（逐条枚举，不做通配 —— 口径 B 不允许模糊匹配）
_SECTION_HEADING_TAILS = (
    "（留待老師）", "(留待老師)", "（留待老师）", "(留待老师)",
    "（智能體永不填）", "(智能體永不填)", "（留待老師，智能體永不填）",
    "← 留待老師（智能體永不填）", "← 留待老師", "←留待老師",
)

# 句末标点（标题比对前剥掉；模板标题按 §9.2 是「標籤」，不含句末标点）
_SENTENCE_TAILS = " 。，、；:;."

# 违规判定里**不算内容**的字符：纯标点 / 留白 / 提示箭头。
# 刻意**不**含汉字与字母 —— 「舌紅苔薄白」这类真内容必然留下非空残料 → 判违规。


def _metric_int(value, default):
    """配置 / 样本行的整数读数兜底：非整数（含 `bool`、`None`、字符串）→ 返回 `default`。

    `bool` 明确拒绝：`True` 是 `int` 子类，静默当 1 用就是静默清洗（与 3.2 校验层同一口径）。
    """
    if isinstance(value, int) and not isinstance(value, bool):
        return value
    return default


def _metric_float(value, default):
    """配置项的浮点读数兜底（`bool` 同样拒绝；非数 → `default`）。"""
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        return float(value)
    return default


def _normalize_metric_text(text, truncate_chars=None):
    """② 的文本归一化（§3.3）：`\\r\\n` / `\\r` → `\\n`、首尾裁剪、连续空白折叠为单空格、双侧截断。

    · 非字符串（`None` / 数字 / dict）→ `""`（§3.3「两个文本任一为空 / 非字符串 → 排除」由调用方计数）；
    · `truncate_chars` 缺失 / 非正整数 → **不截断**；
    · 刻意与 ① 的 `_normalize_section_text()` 分开：相似度计算必须把换行折叠成空格（否则同一份
      病历的换行差异会污染 ②），而 ① 的「行首标题」与「段序」依赖换行结构。
    """
    if not isinstance(text, str):
        return ""
    normalized = " ".join(text.replace("\r\n", "\n").replace("\r", "\n").split())
    limit = _metric_int(truncate_chars, 0)
    if limit > 0:
        normalized = normalized[:limit]
    return normalized


def _normalize_section_text(text):
    """① 的文本归一化（§3.2）：**保留换行** —— 逐行去首尾空白、行内连续空白折叠为单空格、
    全角冒号 → 半角（统一后续 `partition` 切分）、剥掉行首列表符、丢掉空行。

    口径细节：
      · **包裹符不在这里剥**（`【主訴（學生原話）】`）：那是 `_split_heading()` 的职责 ——
        它按「**配对**的首尾包裹符」成对剥；在这里逐字符剥会留下半个 `】`，把标题切坏
        （step 3.4-a 的 ⑯ 组就抓到了这个 bug）；
      · 空行一律丢掉：① 只关心「段标题 + 该标题之后到下一个段标题之前的行」，空行是噪声；
      · 非字符串 → `""`。
    """
    if not isinstance(text, str):
        return ""
    lines = []
    for raw in text.replace("\r\n", "\n").replace("\r", "\n").split("\n"):
        line = " ".join(raw.replace("：", ":").replace("\u3000", " ").split())
        while line[:1] in _SECTION_LINE_PREFIXES:
            line = line[1:].strip()
        if line:
            lines.append(line)
    return "\n".join(lines)


def _split_heading(line):
    """归一化后的一行 → `(heading, rest)`：`heading` = 首个冒号前的标题（无冒号则整行），
    `rest` = 冒号之后的内容（无冒号则空串）；标题两侧的 `【】` / `[]` / `〔〕` / `《》` 在此剥掉。
    """
    head, sep, rest = line.partition(":")
    heading = head.strip()
    for start, end in (("【", "】"), ("[", "]"), ("〔", "〕"), ("《", "》")):
        if len(heading) > len(start) + len(end) and heading.startswith(start) and heading.endswith(end):
            heading = heading[len(start):-len(end)].strip()
            break
    return heading, (rest.strip() if sep else "")


def _strip_heading_tail(heading):
    """剥掉标题后的**提示性尾巴**与句末标点（`舌象（留待老師）` → `舌象`；支持多重尾巴）。"""
    text = heading
    changed = True
    while changed and text:
        changed = False
        for tail in _SECTION_HEADING_TAILS:
            if text.endswith(tail):
                text = text[: -len(tail)].strip()
                changed = True
        while text and text[-1] in _SENTENCE_TAILS:
            text = text[:-1].strip()
            changed = True
    return text


def _heading_matches(heading, title):
    """行首标题是否命中模板段标题（§3.2「`s.title` 作为行首标题出现」的精确实现）。

    命中 = **完全相等**，或「剥掉提示性尾巴后完全相等」；其余一律不算（口径 B：不模糊匹配）。
    """
    return heading == title or _strip_heading_tail(heading) == title


def _teacher_section_is_filled(text):
    """`writable_by='teacher'` 的段在草案里是否**被填了内容**（§3.2 的铁律违规判定）。

    口径：剔除提示语词元（`留待老師` / `智能體永不填` …）与纯标点 / 留白后仍有残料 → 填了内容。
    于是 `舌象：` / `舌象：（留待老師）` / `舌象：　← 留待老師（智能體永不填）` 都不算违规，
    而 `舌象：舌紅苔薄白` 一定违规（AI 永不辨证 / 永不填舌脈，§0.2 铁律）。
    """
    cleaned = text if isinstance(text, str) else ""
    for word in _PLACEHOLDER_WORDS:
        cleaned = cleaned.replace(word, "")
    for char in _NON_CONTENT_CHARS:
        cleaned = cleaned.replace(char, "")
    return bool(cleaned.strip())


def _section_metas(template_row):
    """active `record` 模板行 → 段落元数据（按 `order` 升序；`order` 缺失 / 非法 → 数组下标兜底）。

    真相源 = `schema_json.sections`（Epic 1 §9.2：`title` / `order` / `writable_by`）。
    与 `template_service.record_section_skeleton()` 是**同一份数据的两条渲染路径**：那条给生成
    智能体（提示文本），本函数给指标（结构化）—— 服务层不重新实现模板读取，只用
    `get_active_record_template()` 的返回行（§4.5-① 允许的只读调用）。
    形状不对（`None` / 非 dict / 无有效段落）→ `[]`（调用方据此判「无基准可比」）。
    """
    schema = (template_row or {}).get("schema_json")
    if not isinstance(schema, dict):
        return []
    metas = []
    for index, section in enumerate(schema.get("sections") or []):
        if not isinstance(section, dict):
            continue
        title = section.get("title") or section.get("key") or ""
        if not isinstance(title, str) or not title.strip():
            continue
        order = _metric_int(section.get("order"), index + 1)
        metas.append({
            "title": title.strip(),
            "order": order,
            "index": index,
            "writable_by": section.get("writable_by") or "ai",
        })
    metas.sort(key=lambda meta: (meta["order"], meta["index"]))
    return metas


def _lcs_length(left, right):
    """两个段序列表的**严格最长公共子序列**长度（§3.2 的 `LCS(模板段序, 草案段序)`）。

    实现口径（本段自行钉死，⑯ 组覆盖）：**不 import 任何东西**，用 20 × 20 的 DP 表算严格 LCS。
    §3.2 括号里写的是 `difflib`，那是「标准库、零依赖、开销可忽略」的实现提示；但
    `difflib.SequenceMatcher.get_matching_blocks()` 给的是**块匹配启发式**、不保证等于 LCS ——
    实测模板堆 `[A,B,C,D,E]` vs 草案堆 `[A,C,E,D,B]`：块匹配只得 2，严格 LCS = 3（⑯ 组有回归用例），
    于是 `order_rate` 会被系统性低估、① 整体偏严（更难达标）。文档公式是契约、括号是实现提示，
    故取严格 LCS；`difflib` 仍按 §3.3 用于 ② 的相似度。段数 ≤ 20 → 400 格，开销可忽略。
    """
    columns = len(right)
    previous = [0] * (columns + 1)
    for row_item in left:
        current = [0]
        for index, column_item in enumerate(right):
            if row_item == column_item:
                current.append(previous[index] + 1)
            else:
                current.append(max(previous[index + 1], current[index]))
        previous = current
    return previous[columns]


def _match_weights(cfg):
    """① 的内部权重（§3.2 `template_match_weights`，配置化、不硬编码）。

    · 整个键缺失 / 非 dict → 回落内置默认（`DEFAULT_STAGE_CONFIG`，全 Epic 唯一硬编码点）；
    · 只给了部分子键（CTO 3.2 裁决 B「只校验给出来的项」）→ 未给出的子键按 `0.0` 计：
      **不做部分合并、不补默认权重**（补默认 = 静默清洗）；于是「只给 `section_hit`」的老师
      得到的 ① 就是**命中率本身**，比「悄悄掺进一个他没配的 0.4」更可解释。
    """
    weights = (cfg or {}).get("template_match_weights")
    if not isinstance(weights, dict):
        weights = DEFAULT_STAGE_CONFIG["template_match_weights"]
    return {
        "hit": _metric_float(weights.get("section_hit"), 0.0),
        "order": _metric_float(weights.get("section_order"), 0.0),
    }


def _blank_template_match():
    """① 的返回体骨架（9 键，⑯ 组逐键钉住）：提前建好 → 各条降级路径都能 `return` 同一个形状。"""
    return {
        "value": None,                      # 空集 → None（**不是 0**，CTO 硬约束 2）
        "samples": 0,                       # 入选样本数（命中当前 active 模板且文本非空）
        "violations": 0,                    # 铁律违规样本数（AI 填了 teacher 段）
        "skipped_no_template": 0,           # `template_id = 0`（生成时没有生效模板）
        "skipped_stale_template": 0,        # `template_id` ≠ 当前 active（老师换过版本）
        "skipped_empty": 0,                 # AI 侧文本为空的样本（不静默丢，§3.2「显式计数」）
        "hit_rate": None,                   # 入选样本的段命中率均值（便于运维复核总分来源）
        "order_rate": None,                 # 入选样本的段序一致率均值
        "blockers": [],
    }


def _blank_modification_consistency():
    """② 的返回体骨架（6 键，⑯ 组逐键钉住）。"""
    return {
        "value": None,                      # 空集 → None（**不是 0**）
        "samples": 0,                       # 入选配对样本数（strict + approx）
        "approx_samples": 0,                # 其中「旧数据」近似样本数（只有 `ai_draft`）
        "skipped_empty": 0,                 # 任一侧文本为空的排除数
        "min": None,                        # 最差一份（便于发现异常样本）
        "blockers": [],
    }


def _template_match_sample(text, metas, weights):
    """单样本 ①（§3.2）：返回 `(match, hit_rate, order_rate, violation)`。

    · `hit_rate` = 命中的段数 / 模板段数（标题按**行首**匹配，见 `_heading_matches()`）；
    · `order_rate` = `LCS(模板段序, 草案中实际出现的段序) / 段数`（顺序敏感；草案多出的无关行
      不影响 LCS —— 它们不参与段序）；
    · `violation` = 某个 `writable_by='teacher'` 的段在「它的标题行之后、下一个段标题之前」
      被填了内容 → 该样本 `match = 0.0`（§3.2 铁律违规直接判 0，不按比例折算）；
    · 同名段只认**第一次**出现（§9.2 `sections[].title` 是标签；同标题后续行按普通内容处理）。
    """
    normalized = _normalize_section_text(text)
    lines = normalized.split("\n") if normalized else []
    meta_by_title = {meta["title"]: meta for meta in metas}

    hits = []       # [(行号, 段标题)]，按行号升序
    rests = {}      # 段标题 → 该标题行「冒号之后」的内容
    for line_index, line in enumerate(lines):
        heading, rest = _split_heading(line)
        if not heading:
            continue
        for meta in metas:
            title = meta["title"]
            if title in rests:
                continue
            if _heading_matches(heading, title):
                hits.append((line_index, title))
                rests[title] = rest
                break

    hit_rate = len(hits) / len(metas)
    order_rate = _lcs_length([meta["title"] for meta in metas],
                             [title for _, title in hits]) / len(metas)

    violation = False
    for position, (line_index, title) in enumerate(hits):
        if meta_by_title[title]["writable_by"] != "teacher":
            continue
        end = hits[position + 1][0] if position + 1 < len(hits) else len(lines)
        content = "\n".join([rests.get(title, "")] + lines[line_index + 1:end])
        if _teacher_section_is_filled(content):
            violation = True
            break

    if violation:
        return 0.0, hit_rate, order_rate, True
    return weights["hit"] * hit_rate + weights["order"] * order_rate, hit_rate, order_rate, False


def compute_template_match(teacher_name, cfg):
    """① 模板匹配度（§3.2）—— **只算不判**（阈值判定 / 落盘 / 事件属 `evaluate`，3.4-b）。

    返回体 9 键（形状即契约，⑯ 组逐键钉住）：`value` / `samples` / `violations` /
    `skipped_no_template` / `skipped_stale_template` / `skipped_empty` / `hit_rate` /
    `order_rate` / `blockers`。

    样本集合（§3.2，来自 `database.get_draft_samples()` 的两类来源：未签字草案 + 已签字病历）：
      · `template_id = 0`（生成时没有生效模板）→ `skipped_no_template`；
      · `template_id` ≠ 当前 active 模板 id（老师换过版本）→ `skipped_stale_template`
        （拿旧模板的输出比新模板骨架不公平）；
      · `template_id` == 当前 active id 且 AI 侧文本非空 → **入选**，按「时间倒序取前
        `max_samples` 条」计均值；AI 侧文本为空 → `skipped_empty`。
      排除项一律**显式计数**（§3.2「不静默丢」）。

    三条降级（都**不抛**、都**不写库**，返回体形状不变）：
      · 无生效模板（口径 A：`get_active_record_template()` 返回 `None`，含 `TEMPLATE_API_ENABLED`
        off / 模板表未就绪 / schema 版本不支持 / schema 无有效段落）→ `value=None` +
        `blockers=["no_active_record_template"]`（**不**算 0 分）；
      · 有模板但无入选样本 → `value=None` + `blockers=["template_match_no_samples"]`；
      · 读样本抛 `sqlite3.Error`（0003 未跑 / 库被锁）→ 一行告警 → 按「无样本」处理
        （fail-closed：空值不可能通过任何阈值，§3.4-⑤ 同一方向）。

    阈值 / 权重 / 窗口 / 样本上限**全部来自 `cfg`**（§3.4：不硬编码；`cfg` 缺失键回落
    `DEFAULT_STAGE_CONFIG`）。配置闸门（flag / `matrix_enforced`）不在本函数：它不发写语句，
    没有「绕过闸门」的副作用；真正的闸门与判定在 `evaluate`（3.4-b）。
    """
    import database
    import template_service

    config = cfg if isinstance(cfg, dict) else {}
    result = _blank_template_match()

    template_row = template_service.get_active_record_template(teacher_name)
    active_id = _metric_int(template_row.get("id"), 0) if isinstance(template_row, dict) else 0
    metas = _section_metas(template_row)
    if active_id <= 0 or not metas:
        result["blockers"].append(_BLOCKER_NO_ACTIVE_TEMPLATE)
        return result

    window_days = _metric_int(config.get("window_days"), DEFAULT_STAGE_CONFIG["window_days"])
    max_samples = _metric_int(config.get("max_samples"), DEFAULT_STAGE_CONFIG["max_samples"])
    if max_samples <= 0:
        max_samples = DEFAULT_STAGE_CONFIG["max_samples"]
    try:
        samples = database.get_draft_samples(teacher_name, window_days, max_samples)
    except sqlite3.Error as exc:
        _config_warn("讀取階段指標樣本失敗（%s），① 模板匹配度本次按無樣本處理" % (exc,))
        result["blockers"].append(_BLOCKER_TEMPLATE_MATCH_NO_SAMPLES)
        return result

    weights = _match_weights(config)
    values, hit_rates, order_rates = [], [], []
    for row in samples or []:
        template_id = _metric_int(row.get("template_id"), 0)
        if template_id <= 0:
            result["skipped_no_template"] += 1
            continue
        if template_id != active_id:
            result["skipped_stale_template"] += 1
            continue
        if not (row.get("ai_text") or "").strip():
            result["skipped_empty"] += 1
            continue
        if len(values) >= max_samples:
            continue        # 已取满「前 max_samples 条」；继续跑完是为了把排除项计数干净
        match, hit_rate, order_rate, violation = _template_match_sample(
            row["ai_text"], metas, weights)
        values.append(match)
        hit_rates.append(hit_rate)
        order_rates.append(order_rate)
        if violation:
            result["violations"] += 1

    result["samples"] = len(values)
    if not values:
        result["blockers"].append(_BLOCKER_TEMPLATE_MATCH_NO_SAMPLES)
        return result
    result["value"] = sum(values) / len(values)
    result["hit_rate"] = sum(hit_rates) / len(hit_rates)
    result["order_rate"] = sum(order_rates) / len(order_rates)
    return result


def compute_modification_consistency(teacher_name, cfg):
    """② 病历修改一致率（§3.3）—— **只算不判**（阈值判定 / 落盘 / 事件属 `evaluate`，3.4-b）。

    返回体 6 键（形状即契约，⑯ 组逐键钉住）：`value` / `samples` / `approx_samples` /
    `skipped_empty` / `min` / `blockers`。

    样本与口径（§3.3）：
      · **只看 `source == 'record'`**（已签字病历）：未签字草案的老师编辑还没定稿，
        「改了多少」不成立（草案的后续编辑会写进 `drafts.content`）；
      · 单样本相似度 = `difflib.SequenceMatcher(None, norm(ai_text), norm(final_text),
        autojunk=False).ratio()`（§3.3 选它而非编辑距离：标准库、零新依赖、与 Epic 3 的字段级
        diff 复用同一套归一化）；`norm()` = `_normalize_metric_text()` + `truncate_chars` 双侧截断
        → 耗时有界；
      · `strict`（`ai_original_text` 非空，`has_snapshot=True`）与 `approx`（存量旧数据只有
        `ai_draft`，**会系统性高估**）**都进均值**，但 `approx_samples` 单独计数
        （前端显示「含 N 份近似樣本（舊數據）」）；
      · 任一侧文本为空 / 非字符串 → `skipped_empty`（不进均值，也不静默丢）；
      · `min` = 入选样本的最小相似度（最差一份，便于发现异常样本）。

    窗口与样本上限来自 `cfg`（`window_days` / `max_samples` 直接传给库层只读原语，
    由它做「时间锚倒序 + LIMIT」）。两条降级（都不抛、都不写库，返回体形状不变）：
      · 无入选样本（含窗口内一份都没有）→ `value=None` +
        `blockers=["modification_consistency_no_samples"]`（**不是 0**，CTO 硬约束 2）；
      · 读样本抛 `sqlite3.Error`（0003 未跑 / 库被锁）→ 一行告警 → 按「无样本」处理（fail-closed）。
    """
    import database

    config = cfg if isinstance(cfg, dict) else {}
    result = _blank_modification_consistency()

    window_days = _metric_int(config.get("window_days"), DEFAULT_STAGE_CONFIG["window_days"])
    max_samples = _metric_int(config.get("max_samples"), DEFAULT_STAGE_CONFIG["max_samples"])
    if max_samples <= 0:
        max_samples = DEFAULT_STAGE_CONFIG["max_samples"]
    truncate_chars = _metric_int(config.get("truncate_chars"), DEFAULT_STAGE_CONFIG["truncate_chars"])

    try:
        samples = database.get_draft_samples(teacher_name, window_days, max_samples)
    except sqlite3.Error as exc:
        _config_warn("讀取階段指標樣本失敗（%s），② 病歷修改一致率本次按無樣本處理" % (exc,))
        result["blockers"].append(_BLOCKER_MODIFICATION_NO_SAMPLES)
        return result

    similarities = []
    for row in samples or []:
        if row.get("source") != _SAMPLE_SOURCE_RECORD:
            continue
        ai_text = row.get("ai_text")
        final_text = row.get("final_text")
        if not isinstance(ai_text, str) or not isinstance(final_text, str) \
                or not ai_text.strip() or not final_text.strip():
            result["skipped_empty"] += 1
            continue
        if len(similarities) >= max_samples:
            continue        # 已取满「前 max_samples 条」；继续跑完是为了把排除项计数干净
        similarities.append(difflib.SequenceMatcher(
            None,
            _normalize_metric_text(ai_text, truncate_chars),
            _normalize_metric_text(final_text, truncate_chars),
            autojunk=False,
        ).ratio())
        if not row.get("has_snapshot"):
            result["approx_samples"] += 1

    result["samples"] = len(similarities)
    if not similarities:
        result["blockers"].append(_BLOCKER_MODIFICATION_NO_SAMPLES)
        return result
    result["value"] = sum(similarities) / len(similarities)
    result["min"] = min(similarities)
    return result
_NON_CONTENT_CHARS = " \t\u3000\r\n（）()[]［］【】<>《》←→-—*·:：、,，。.。;；|丨"

