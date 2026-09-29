# 知衡社区 · Epic 2「老师智能体五阶段」设计方案

版本：v1.0
日期：2026-09-28
范围：**仅设计方案（Markdown），不含代码**。Epic 2 全部内容一次成文，待 CTO 一次性审核。
对齐：白皮书 2.0 第二章 2.3.4 / 2.3.5；`docs/development-plan-v1.md` §3.3 D2、§5 Epic 2
前置：Epic 1 已闭环（`docs/epic1-template-design-v1.md`，迁移 0001 / 0002 已落库）
状态：待审核。**本文件不含「原文缺失」类待办** —— §0.1 的三条基准为最高优先级设计依据。

---

## 0. 前提与基线

### 0.1 设计基准（CTO 已确认 · 最高优先级 · 不再复议）

1. 老师智能体五阶段（固定顺序，不可跳级）：
   **观察期（只记录）→ 学习期（生成草案）→ 见习期（预测证型）→ 助手期（建议方剂）→ 授权期（生成预处方）**。
2. **权限矩阵铁律**：**AI 永不诊断、永不开方、永不签字**。此三条是宪法级硬约束，**任何阶段、任何开关、任何配置都不能解锁**（§2.1）。
3. 以上两条即为设计依据，本文件不再寻找其它出处、不再产生「基准缺失」误报。

### 0.2 CTO 批复执行对照表（2026-09-28，直接执行）

| # | 批复原文要点 | 本设计落地位置 | 执行结论 |
| :---- | :---- | :---- | :---- |
| 1 | 一致率阈值必须配置化，不能硬编码；Flag 统一命名 `AGENT_STAGE_ENABLED`，默认 off | §3.4 阈值读取链 / §3.5 配置表契约 / §4.5 flag 实现 | 已执行：阈值 + 权重 + 样本下限全部来自 `agent_stage_config.config_json`（按老师行 → 全局行 → 环境变量 → 内置兜底默认值）；代码内只允许存在**一份**兜底默认值常量，且它在读取链末端、可被覆盖 |
| 2 | 升级交互：系统计算 → 老师端推送通知 → 老师点击确认后生效；不弹窗打断 | §3.6 升级触发链路 | 已执行：复用**现存**请示通道 —— 写一条 `agent_tasks`（`status='pending'`），自动出现在工作台「⏳ 待你确认」区块，老师点 ✅ 走**现存** `POST /api/agent_tasks/approve` 生效（实测 `App.tsx:2507-2518` 渲染该区块时**不按 category 过滤**，只用 `title` / `content` + ✅/❌ → 确认流程**零前端改动**） |
| 3 | 一致率指标排期：Epic 2 只做 ①模板匹配度 和 ②病历修改一致率；③问诊偏好一致性移入 Epic 3 | §3.1 指标范围与排期 | 已执行：③ 只在返回体里保留**恒为 `null` 的占位键** + `deferred_to_epic3` 原因，不实现算法、不建表、不产生事件（保证接口形状一次成型，后续只填值不改形） |
| 4 | 未截图到的「前 3 项」：按最稳妥技术方案直接写入设计，不阻塞，事后一次审核 | §7.1 已决技术选择表（每条含：结论 / 理由 / 备选 / 影响面） | 已执行：全部给出可推翻的单条结论；若批复 4 所指范围与 §7.1 不同，请逐条批注，任一条被推翻不影响其它条目 |

### 0.3 事实核验（实测当前代码，本设计的前提）

| 事实 | 实测结果 |
| :---- | :---- |
| 阶段概念现状 | 全库**无** `agent_stage` 列 / 表；`agent_tasks` 只承载学生类请示（`database.py:342-354`） |
| 智能体工作台 | 三区块读接口固定：`GET /api/agent_tasks?status=pending|approved` + `GET /api/agent_action_log`（`App.tsx:355-361`、`875-892`） |
| 请示确认通道 | ✅/❌ → `POST /api/agent_tasks/approve|reject` → `database.resolve_agent_task()`（`main.py:1083-1099`、`database.py:1520-1554`）；**渲染不分 category**（`App.tsx:2507-2518`） |
| 草案生成三条路径 | `/api/transcribe`（`main.py:590-610`）、`/api/upload` 图片分支（`612-631`）、`/api/generate-draft`（`656-677`）→ 全部经 `insert_draft()`（`database.py:654-673`） |
| 老师修改草案 | `PUT /api/drafts/{id}` → `update_draft_content()`：**原地覆盖 `drafts.content`**（`database.py:698-702`）→ 原始 AI 文本**今天没有留存列**（②指标的必要前提，见 §3.3 / §3.5） |
| 签字落库 | `sign_draft()` 把 `drafts.content` 写入 `patient_records.ai_draft`、老师最终版写入 `final_plan`，随后**删除该草案行**（`database.py:704-733`）→ 签字后 `drafts` 行不可再查 |
| Flag 惯例 | `template_service.template_api_enabled()`（`template_service.py:898-909`）：`os.environ.get(..., "off").strip().lower() in ("on","1","true","yes")`，**每次调用现读**、默认 off |
| 服务层错误惯例 | `TemplateError(code,msg)` + 接口层映射表 + 统一错误体 `{detail:{error,msg,errors,warnings}}`（`template_api.py:36-79`） |
| 迁移惯例 | 新表 DDL 唯一真相源 = Alembic（`epic1 §1.1`）；补列用 `PRAGMA table_info` 探测后 `ADD COLUMN` 幂等；`downgrade` **默认不删列**（`alembic/versions/0002_add_draft_template_refs.py:24-90`）；运行器失败只打日志不阻塞启动（`migrations_runner.py:47-58`） |
| 存量「自动迁移」惯例 | `try: ALTER TABLE ... ADD COLUMN except sqlite3.OperationalError: pass`（`database.py:197-200`、`409-412`）—— 本 Epic 的补列**不**走此路，走迁移（与 Epic 1 §12.1 一致） |
| 测试入口 | `conftest.py`：删 `test.db` → `init_db()` → `migrations_runner.run_upgrade()`；`TEMPLATE_API_ENABLED=on` 由 conftest 注入（`conftest.py:6-29`） |
| DB / 时间 / JSON 惯例 | `ZHIENG_DB` 决定库文件（`database.py:6`）；时间列一律 `TEXT` ISO；JSON 一律 `TEXT` 存；全库**无 FK、无 CHECK** |
| 前端 flag 惯例 | `TemplateStudio.tsx` 自带探測（404 → 整卡不渲染；503 → 卡内红字，实测 `TemplateStudio.tsx:1047-1110`、`1307`），`App.tsx` 只 import + 挂载（`App.tsx:3`、`3308-3310`） |
| 依赖现状 | 后端不新增任何 pip 依赖（相似度用标准库 `difflib`）；前端不新增 npm 依赖（沿用内联 style + serif + `#8b4513`） |

### 0.4 枚举与命名对照表（唯一口径，全栈共用）

| 中文阶段 | 枚举值 | 等级 `rank` | 阶段徽章（繁体古字） | 本阶段「智能体能做什么」 |
| :---- | :---- | :---- | :---- | :---- |
| 观察期 | `observation` | 0 | `觀察期` | 只记录（学生陈述 / 老师编辑 / 签字事件入审计），**零 LLM 输出** |
| 学习期 | `learning` | 1 | `學習期` | 生成病历草案（= 系统今天已具备的能力，见 §5.2） |
| 见习期 | `apprentice` | 2 | `見習期` | 预测证型**候选**（附依据 + 免责，仅供参考，不写入病历） |
| 助手期 | `assistant` | 3 | `助手期` | 建议方剂（方名 + 组成参考，**不含可落库药单**） |
| 授权期 | `authorized` | 4 | `授權期` | 生成**预处方**（含剂量 / 君佐使 / 煎法，**仅供前端预填**，落库仍由老师点保存） |

- 能力键（capability）枚举：`record_observation` / `generate_draft` / `predict_pattern` / `suggest_prescription` / `generate_predraft`。
- 阶段中文名（简体）仅用于本设计文档叙述；**所有 UI 文案一律繁体古字**（沿用 Epic 1 §13.4 口径）。
- 命名纪律：**不新增同义词**。日志 / 配置 / 接口 / 前端一律使用上表枚举字面量。

---

## 1. 五阶段状态机

### 1.1 状态机总览

```
                 （系统评估达标）
  observation ──▶ learning ──▶ apprentice ──▶ assistant ──▶ authorized
       ▲              ▲              ▲              ▲              │
       └──────────────┴──────────────┴──────────────┴──────────────┘
                  老师手动降级（任意 → 任意更低阶段）
                  违反铁律 / 规则触发降级（自动，逐级下降）
```

- **升级**：只向前、只升一级、**必须老师确认**（系统只推荐，§3.6）。
- **降级**：老师手动（立即生效，无需确认——限制方向永远即时）；或规则触发（自动逐级，§3.7）。
- **不改级**：同阶段重复操作幂等（`changed=false`，记一条 no-op 日志）。
- **不跳级**：`to_rank - from_rank == 1` 才允许升级；`to_rank < from_rank` 才允许降级；其余 → 409 `stage_transition_invalid`。

### 1.2 字段定义（运行时读写的状态行）

| 字段 | 类型 | 约束 / 默认 | 说明 |
| :---- | :---- | :---- | :---- |
| `teacher_name` | TEXT | PRIMARY KEY | 语义 = `teachers.name`，与全库鉴权口径一致（`teacher_name` 即身份，不引登录体系） |
| `lineage_id` | TEXT | NOT NULL DEFAULT `''` | 与 `templates.lineage_id` 同构；Epic 2 恒为 `''`，Epic 4 起成为隔离键（**不建 FK、不加 CHECK**） |
| `stage` | TEXT | NOT NULL DEFAULT `observation` | 五阶段枚举（§0.4）；非法值由服务层白名单拦截，**不加 DB 级 CHECK**（存量全库无 CHECK） |
| `stage_since` | TEXT | NOT NULL DEFAULT `''` | 进入当前阶段的时刻（ISO 字符串） |
| `stage_source` | TEXT | NOT NULL DEFAULT `default` | `default` / `teacher_confirm` / `manual_demote` / `rule_demote` / `rule_reset`（铁律违反回落观察期） |
| `pending_stage` | TEXT | NOT NULL DEFAULT `''` | 系统已推荐、老师尚未确认的目标阶段（空 = 无待确认） |
| `pending_task_id` | INTEGER | DEFAULT 0 | 对应 `agent_tasks.id`（可追溯「这条推荐是哪条请示」） |
| `last_evaluated_at` | TEXT | NOT NULL DEFAULT `''` | 最近一次评估时刻（评估=算 ①② + 判定可否推荐） |
| `last_metrics_json` | TEXT | NOT NULL DEFAULT `'{}'` | 最近一次评估结果快照（`GET /api/agent/stage` 直接返回，避免每次重算，§3.8） |
| `updated_at` | TEXT | NOT NULL DEFAULT `''` | 任意字段变更都刷新 |

### 1.3 审计日志表字段（只增不改不删）

| 字段 | 类型 | 说明 |
| :---- | :---- | :---- |
| `id` | INTEGER PRIMARY KEY AUTOINCREMENT | |
| `teacher_name` | TEXT | |
| `event_type` | TEXT | `stage_upgraded` / `stage_demoted` / `upgrade_recommended` / `upgrade_declined` / `permission_denied` / `evaluation` / `config_changed` / `suggestion_generated` / `predraft_generated` / `permission_relaxed` | 共 **10 类**（第 10 类 `permission_relaxed` 见下方补白） |
| `from_stage` / `to_stage` | TEXT | 变更类事件必填，其余为空串 |
| `capability` | TEXT | 越权类事件必填（被拒的能力键），其余为空串 |
| `task_id` | INTEGER | 关联请示（升级推荐 / 确认 / 拒绝）；无则 0 |
| `metrics_json` | TEXT | 该次事件的指标快照（`permission_denied` 也为空对象 `{}`，不做特例） |
| `detail` | TEXT | 人类可读说明（进「行动日志」区块的就是它） |
| `created_at` | TEXT | ISO 字符串 |

> **`permission_relaxed`（第 10 类事件，2026-09-29 补）**：**对应 §2.5 ③ 的权限放宽事件** —— `matrix_enforced=false` 时，`require_capability` 对 `predict_pattern` / `suggest_prescription` / `generate_predraft` 三个新能力的**放行**写这条反向事件（`capability` = 被放宽的能力键、`from_stage` = 当前阶段、`to_stage=''`、`task_id=0`、`metrics_json={}`），防「静默放宽」；矩阵本来就放行的格子**不写**（那里不存在「放宽」）。
> **事件名契约（2026-09-29 裁决）**：越权拒绝一律用本表原有的 **`permission_denied`**（§1.3 / §2.4 / §6.2-14 三处一致；step 3.3 施工期间的临时名 `capability_denied` **已废弃**，不得再出现在代码或数据里 —— 事件名是契约，历史数据不能分裂）。

> **与 Epic 3 的边界（防重叠）**：本表是**治理审计**（阶段 / 权限 / 配置）；Epic 3 的 `agent_learning_events` 是**学习事件流**（生成 / 修改 / 哈希链）。Epic 2 **不建哈希链**，只保证本表「只增」。Epic 3 如需把本表纳入链，属其范围，不影响本表结构。

### 1.4 持久化表结构（DDL 唯一真相源 = 迁移 `0003_add_agent_stage`）

| 对象 | 变更 | 说明 |
| :---- | :---- | :---- |
| `agent_stage_state` | 新建表 + 索引 `(lineage_id, stage)` | 一位老师一行；无行 = 未初始化（按 §1.5 的默认值兜底，**不报错**） |
| `agent_stage_log` | 新建表 + 索引 `(teacher_name, created_at DESC)` | 只增；`created_at` 同秒靠 `id` 兜底排序（沿用 `get_agent_action_log` 的排序口径） |
| `agent_stage_config` | 新建表 | `teacher_name` 为主键：`''` = 全局默认行；其余 = 老师专属覆盖行 |
| `drafts` | `ADD COLUMN ai_original_content TEXT DEFAULT ''` | ②指标基准：**AI 原始输出不可变快照**，生成时写入，老师编辑只改 `content`（§3.3） |
| `patient_records` | `ADD COLUMN ai_original_text TEXT DEFAULT ''` | ②指标基准：签字时把快照一并落进历史表（草案行签字后会被删除，历史侧必须自带） |

- 全部列类型 `TEXT` / `INTEGER`、**零外键、零 CHECK**，与存量 24+ 张表同构。
- 迁移可重跑：建表 `IF NOT EXISTS`、补列先 `PRAGMA table_info` 探测（沿用迁移 0002 的实现口径）。
- **种子**：`INSERT INTO agent_stage_state (teacher_name, stage, stage_since, stage_source, updated_at) SELECT name, 'learning', <now>, 'default', <now> FROM teachers WHERE NOT EXISTS (SELECT 1 FROM agent_stage_state s WHERE s.teacher_name = teachers.name)`；`agent_stage_config` 种子写一行 `teacher_name=''`、`config_json='{}'`（显式承载「全局行存在但用内置默认」）。
- **seed 口径说明**：存量老师初始化成 `learning` 而不是 `observation`，理由见 §5.2（存量不可降级）。想「严格从未观察期开始」只需把种子值与该老师的 `default_stage` 配置改成 `observation`，其余零改动。
- **downgrade**：`DROP TABLE agent_stage_log`（若存在非种子事件则**中止并提示先导出**，沿用迁移 0001 的安全闸口径）、`DROP TABLE agent_stage_state`、`DROP TABLE agent_stage_config`；**两个新列不删**（列里是历史快照，删了就永久丢失 ② 的口径，沿用 0002 的纪律）。
- 离线预审产物：`docs/migrations/0003_add_agent_stage.sql`（`alembic upgrade head --sql` 输出，与 0001 产物同一套运维习惯）。

### 1.5 状态真值读取（fail-safe 方向）

`agent_stage_service.current_stage(teacher_name)` 的读取顺序：

1. `agent_stage_state` 有行 → 取 `stage`（并校验是否在白名单内，非法值视为 `default_stage` 并记 `evaluation` 事件）。
2. 无行（未初始化）→ 取配置 `default_stage`（内置默认 `learning`，见 §5.2），**不写库、不报错**，返回结果里 `stage_source='default'`。
3. 读库异常（表未就绪 / 库被锁）→ `default_stage`，并在响应里带 `degraded=true` + 打日志；**绝不抛异常给既有链路**。

fail-safe 方向声明：任何「读不到」都**不会**把权限放大（`default_stage` 是唯一被允许的兜底，且它只能是 `observation` 或 `learning`；配置校验层拒绝把 `default_stage` 设成 `apprentice` 及以上，见 §3.5 校验）。

### 1.6 状态转移动作清单

| 动作 | 触发者 | 前置 | 效果 | 落库 |
| :---- | :---- | :---- | :---- | :---- |
| `recommend_upgrade` | 系统（评估） | 达标 + 无待确认 + 冷却已过 | 写 `pending_stage` + 建 `agent_tasks` 请示 | `agent_stage_state` + `agent_stage_log` + `agent_tasks` |
| `confirm_upgrade` | 老师（点 ✅） | 存在对应 `pending` 请示且 `to` = `current+1` | `stage` → 新阶段、`pending_stage` 清空、`stage_source='teacher_confirm'` | `agent_stage_state` + 两张日志 |
| `decline_upgrade` | 老师（点 ❌） | 同上 | `pending_stage` 清空、记 `upgrade_declined`、进入冷却 | `agent_stage_state` + `agent_stage_log` |
| `manual_demote` | 老师（显式接口） | `to_rank < from_rank` | 立即降级（可一次降到任意更低阶段） | `agent_stage_state` + 两张日志 |
| `rule_demote` | 系统（评估） | 规则命中（§3.7） | 降一级（不低于 `observation`） | `agent_stage_state` + 两张日志 |
| `rule_reset` | 系统（评估） | 铁律违反（§2.1 / §3.2 违规） | **直接回 `observation`** | `agent_stage_state` + 两张日志 |

---

## 2. 权限矩阵

### 2.1 L1 宪法层：三条铁律（永不开关、永不因阶段而放宽）

| 铁律 | 具体含义（代码级口径） | 强制手段 |
| :---- | :---- | :---- |
| **AI 永不诊断** | 不输出「诊断为 X」类结论；只允许输出**候选**证型（见习期起），文案固定含「僅供參考，非診斷」；**不得自动写入** `drafts.content` 的辨证段、**不得写入** `patient_records.final_plan` | ① 新 prompt 内置禁区段（照抄 `agent.py:79-104` `DOCTOR_PROMPT` 的「【绝对禁止】」段落写法）；② 服务层只**返回**建议体，不提供任何写病历接口；③ 守护测试断言 `agent_stage_service` 不引用 `update_draft_content` / `sign_draft` |
| **AI 永不开方** | 不调用 `database.create_prescription()`、不扣库存（`batch_deduct_herbs`）、不写 `prescriptions` 行、不向学生发送任何内容 | ① `agent_stage_service` **禁止** import `create_prescription` / `sanitize_prescription_items` / `batch_deduct_herbs`（守护测试按 AST/源码扫描断言）；② 授权期「预处方」只作为**前端预填数据**返回，落库必须由老师点九宫格「保存开方」走既有 `POST /api/prescriptions`（`main.py:998-1008`，其身份是老师本人） |
| **AI 永不签字** | 不调用 `sign_draft()`、不写 `patient_records`、不置 `drafts.signed=1`、不代老师提交任何表单 | ① 同上禁止 import；② `sign_draft` 的调用方只有 `main.py` 的 `POST /api/drafts/{id}/sign`（老师端）；③ Epic 2 新增的所有写路径白名单限于 `agent_stage_state` / `agent_stage_log` / `agent_stage_config` / `agent_tasks`(仅升级推荐) |

> 三条铁律在**任何** `matrix_enforced=false`、任何 flag、任何阶段的组合下**都保持有效**（§2.5）。

### 2.2 三层强制点（哪一层做强制）

| 层 | 位置 | 职责 | 失败方向 |
| :---- | :---- | :---- | :---- |
| **L1 宪法层** | `agent_stage_service` 的写入边界 + 新 prompts 的禁区段 + 守护测试 | 铁律：永不诊断 / 开方 / 签字 | 任何可疑 → 不产出、写审计日志 |
| **L2 阶段门控层（后端 service，唯一强制点）** | `agent_stage_service.require_capability(teacher_name, capability)` —— **全项目唯一能力闸门**；`agent_stage_api` 新接口、`main.py` 生成路径接入点、以及服务层内部嵌套调用**都必须**经它 | 阶段 → 能力映射（§2.3）；越权 → 拒绝 + 审计 | **fail-closed**：判定不出（读到异常 / 能力键未知）一律拒绝（`generate_draft` 在 flag off 时的兼容例外，见 §5.1 红线 1） |
| **L3 接口层 / 前端** | `agent_stage_api` 的 `_guard()`（照抄 `template_api.py:62-79`）+ 前端只**展示**能力开关 | 统一鉴权（`teacher_name` / `teacher_id` 一致）、flag → 404、表未就绪 → 503、错误体统一 | 前端按钮置灰只是 UI 提示；**服务端一律重判**，前端不可信 |

**为什么强制点只有一个**：`require_capability()` 是唯一读 `agent_stage_state` 做放行判定的函数。新增能力若绕过它，等价于绕过整个矩阵 → 用**守护测试**兜住：扫描 `agent_stage_service` / `agent_stage_api` 之外的文件不得直接出现 `current_stage` 的调用（`test_matrix_single_choke_point`）。

### 2.3 能力 → 阶段矩阵（L2 判定表，唯一真相源）

| 能力 capability | observation | learning | apprentice | assistant | authorized | 说明 |
| :---- | :----: | :----: | :----: | :----: | :----: | :---- |
| `record_observation`（只记录 / 统计） | ✅ | ✅ | ✅ | ✅ | ✅ | 写入本 Epic 新表与两个快照列；不含任何 LLM 输出 |
| `generate_draft`（生成病历草案） | ❌（降级为本地骨架，§5.3） | ✅ | ✅ | ✅ | ✅ | LLM 路径；输出契约与今天一致 |
| `predict_pattern`（证型候选） | ❌ | ❌ | ✅ | ✅ | ✅ | 只返回候选，不落库、不自动填病历 |
| `suggest_prescription`（建议方剂） | ❌ | ❌ | ❌ | ✅ | ✅ | 只给方名 / 组成参考，**无剂量药单** |
| `generate_predraft`（生成预处方） | ❌ | ❌ | ❌ | ❌ | ✅ | 含剂量的预填数据；**永不落库、永不发送、永不签字** |

判定伪码（服务层）：
```
require_capability(teacher, cap):
    if cap not in CAPABILITIES:            deny("stage_capability_unknown")   # fail-closed
    if not agent_stage_enabled():          deny("agent_stage_disabled")       # §5.1 红线 1 的例外见下
    stage = current_stage(teacher)          # §1.5，失败 → default_stage
    return rank(cap) <= rank(stage)
```
flag off 的特例：`cap == 'generate_draft'` **恒放行**（因为这是今天的既有行为，必须 1:1）；其余四项在 flag off 时恒拒绝。该特例**只写一处**（`require_capability` 内部的 `LEGACY_ALLOWED_WHEN_DISABLED = {"generate_draft"}` 常量），不得散落。

### 2.4 越权拒绝与日志

- **拒绝动作**：抛服务层 `AgentStageError(code='stage_forbidden', msg=...)`（新错误类，与 `TemplateError` 同构造），由接口层翻译成 **403**。
- **审计**：每次拒绝写 `agent_stage_log(event_type='permission_denied', capability=…, from_stage=当前, detail=…)` + 一行 `print("[warn] 智能體越權被拒…")`（与存量日志风格一致）。**审计写入失败不得改变拒绝结果**（拒绝先于日志，日志包 try/except）。
- **可解释文案**（繁体，前端直接用）：
  - 未達階段：`智能體當前為「學習期」，辨證建議屬「見習期」能力，尚未開放。`
  - 功能关闭：`智能體階段功能未啟用。`
- **升级阻断联动**：窗口内 `permission_denied` 次数 > `max_permission_denials`（默认 0）→ 本次评估**不得推荐升级**（防「前端错调 + 系统照升」的荒诞路径），并在 `blockers` 里给出 `permission_denied_in_window`。

### 2.5 `matrix_enforced=false` 的语义边界（回退开关，来自 Epic 2「回退」条款）

- 来源：`development-plan-v1.md` §5 Epic 2「回退：阶段默认 observation，权限矩阵可配置关闭」。
- **作用域**：只关闭 **L2 阶段门控**（`require_capability` 对 `predict_pattern` / `suggest_prescription` / `generate_predraft` 放行）。
- **不放开的**：① 三条铁律；② flag `AGENT_STAGE_ENABLED` 仍是总闸（off → 新接口 404、零副作用）；③ 越权审计照写（`matrix_enforced=false` 下的放行也记 `permission_denied` 的反向事件 `permission_relaxed`，便于事后审计）。
- **风险声明**：`matrix_enforced=false` 是**临时运维闸**，不是产品态；前端在该配置下必须在阶段卡上显示红字 `權限矩陣已由管理員放寬（臨時）`，不允许静默。

---

## 3. 一致率计算方案

### 3.1 指标范围与排期（批复 3）

| # | 指标 | Epic 2 | 数据来源 | 说明 |
| :---- | :---- | :---- | :---- | :---- |
| ① | 模板匹配度 `template_match` | ✅ 实现 | `templates`（Epic 1）+ `drafts.ai_original_content`（本 Epic 新增快照） | 智能体输出 vs 老师生效 `record` 模板骨架 |
| ② | 病历修改一致率 `modification_consistency` | ✅ 实现 | `patient_records.ai_original_text` / `ai_draft` / `final_plan` | 老师改得越少 = 一致率越高 |
| ③ | 问诊偏好一致性 `inquiry_preference_consistency` | ⛔ 移 Epic 3 | 依赖 Epic 3 的 diff 数据（问诊答案 vs 模板 `fields` 偏好） | **Epic 2 只保留恒为 `null` 的占位键** + `reason: "deferred_to_epic3"`；不写算法、不写表、不产事件 |

接口返回体三个键**一次成型**（①②为数值对象，③为 `null` 占位），后续 Epic 3 只把 ③ 从 `null` 变成对象（**只增不改**）。

### 3.2 ① 模板匹配度（`template_match`）

**用途**：衡量「智能体按老师生效病历模板的骨架与顺序输出」的程度（Epic 1 §12.2 已接入骨架提示，本指标验收它是否真的起作用）。

**权重配置化**：`config_json.template_match_weights = {"section_hit": 0.6, "section_order": 0.4}`（与阈值同源，不硬编码）。

**单样本（一份 AI 原始草案 vs 一个模板版本）**

```
sections   = 模板 schema_json.sections（按 order 排序）
hit_rate   = |{s : s.title 在草案文本中作为行首标题出现}| / |sections|
order_rate = LCS(模板段序, 草案中实际出现的段序) / |sections|   # 顺序敏感，允许草案多出无关行
violation  = 是否存在 writable_by='teacher' 的段在草案里被填了非空内容
match      = w_hit * hit_rate + w_order * order_rate            # 权重来自配置
match      = 0.0   if violation                                 # 铁律违规直接判 0
```

- **标题识别口径**（文本层纯规则、零 LLM）：先归一化（去首尾空白、`\r`、全角/半角冒号统一、连续空白折叠），再匹配 `(?:^|\n)\s*[-*·]?\s*{title}\s*[:：]`；`（留待老師）` 后缀可有可无。
- **段序提取**：按标题在草案文本中出现的字符位置升序。
- **LCS**：标准库实现（`difflib`），模板段数 ≤ 20，开销可忽略。
- **样本集合**：`drafts`（未签字）+ `patient_records`（已签字，取其 `ai_original_text` / 兜底 `ai_draft`）中，`template_id > 0` 且 `template_id == 当前 active record 模板 id` 的行；窗口 = 近 `window_days`（默认 90）天，按时间倒序取前 `max_samples`（默认 50）。
- **排除样本（必须显式计数，不静默丢）**：
  - `skipped_no_template`：`template_id = 0`（当时没有生效病历模板）→ 对该指标无意义；
  - `skipped_stale_template`：`template_id` ≠ 当前 active 模板 id（老师换过版本）→ 用旧模板输出比对新模板骨架不公平，剔除并计数（前端显示 `已略過 N 份舊模板樣本`）。
- **空集语义**：`samples = 0` → `value = null`（**不是 0**）+ `blockers: template_match_no_samples`；空值**不得**通过任何阈值判定（§3.6）。
- **违规样本**：`violations > max_violations`（默认 0）→ 触发 `rule_reset`（回观察期）+ 汇报（§3.7）。

### 3.3 ② 病历修改一致率（`modification_consistency`）

**用途**：衡量「智能体生成的病历，老师改了多少」。改得少 = 智能体越贴合老师，这是升级的核心依据。

**基准数据（关键前置，缺则指标无意义）**

| 时点 | 数据 | 来源 |
| :---- | :---- | :---- |
| 生成时 | `drafts.ai_original_content` = AI 原始输出（**不可变**） | 本 Epic `insert_draft()` 追加写入（§4.2-1） |
| 老师编辑 | `drafts.content` = 老师编辑中的最新文本 | 既有 `update_draft_content()`，语义**一字不改** |
| 签字时 | `patient_records.ai_original_text` = 上述快照；`ai_draft` / `final_plan` = 既有语义 | 本 Epic `sign_draft()` 追加写入（§4.2-2） |

**单样本相似度（只用标准库，不引依赖）**

```
sim = difflib.SequenceMatcher(None, norm(ai_text), norm(final_text), autojunk=False).ratio()   # ∈ [0,1]
```
- `norm()`：`\r\n → \n`、首尾空白裁剪、连续空白折叠为单空格、每侧截断到 `truncate_chars`（默认 2000 字符）→ **耗时有界**（样本上限 50 时本地 SQLite 场景可接受）。
- 选 `SequenceMatcher` 而非编辑距离：标准库、零新依赖（§0.3）、对整段文本的总体相似度判定稳定，且 Epic 3 的字段级 diff 会复用同一套归一化 → **同一把尺子**。

**成对样本口径（窗口 = 近 `window_days` 天，按 `patient_records.visit_at` 倒序取前 `max_samples`）**

| 类别 | 条件 | 处理 |
| :---- | :---- | :---- |
| `strict` 样本 | `ai_original_text != ''` 且 `final_plan != ''` | 计入均值 |
| `approx` 样本（存量历史） | `ai_original_text == ''` 但 `ai_draft != ''` 且 `final_plan != ''`（`ai_draft` 是签字时刻的文本，老师签字前的编辑已在 `drafts.content` 里被消化 → **会系统性高估一致率**） | 计入均值，**单独计数** `approx_samples`，前端显示 `含 N 份近似樣本（舊數據）` |
| 排除 | 两个文本任一为空 / 非字符串 | 计数 `skipped_empty`，不进均值 |

**② = mean(入选样本的 `sim`)**，同时返回 `min`（最差一份，便于发现异常）与 `samples` / `approx_samples` / `skipped_empty`；`samples = 0` → `value = null` + `blockers: modification_consistency_no_samples`。

### 3.4 阈值读取链（配置化，不硬编码 —— 批复 1）

```
最终配置 = 内置兜底默认值（唯一硬编码点：DEFAULT_STAGE_CONFIG 常量）
           ← 覆盖：agent_stage_config 全局行（teacher_name = ''）
           ← 覆盖：agent_stage_config 老师专属行（teacher_name = 当前老师）
           ← 覆盖：环境变量 AGENT_STAGE_<KEY 大寫>（仅白名单标量键）
```

规则：
1. **逐键覆盖的浅合并**；未知键**原样保留**（前向兼容，沿用 Epic 1「不删未知键」口径）；缺失键回落上一级。
2. **环境变量只对白名单键生效**（`default_stage` / `window_days` / `max_samples` / `min_samples` / `min_template_match` / `min_modification_consistency` / `max_violations` / `max_permission_denials` / `recommend_cooldown_hours` / `demote_consistency_floor` / `demote_streak` / `truncate_chars` / `matrix_enforced` / `metrics_ttl_hours`）；白名单外一律忽略并打日志（防止 typo 静默生效）。
3. **每次评估现读**（与 `template_api_enabled()` 的「现读、不缓存」纪律一致 → 灰度调参不必重启）。
4. **来源必须可回答**：`GET /api/agent/stage` 返回 `config_source = {"global": bool, "teacher_override": bool, "env_override": [键…]}`，供老师 / 运维核对「到底用的哪个阈值」。
5. **两层校验（写入时 + 读取时都跑）**：比率类 ∈ [0,1]；`1 ≤ min_samples ≤ max_samples ≤ 500`；`1 ≤ window_days ≤ 3650`；`truncate_chars ∈ [200,4000]`；`demote_streak ∈ [1,10]`；`max_permission_denials ∈ [0,100]`；`max_violations ∈ [0,50]`；`default_stage ∈ {observation, learning}`；`template_match_weights` 各项非负且和 > 0。非法 → **400 `stage_config_invalid`**（`errors: [{path, msg}]`，沿用 Epic 1 错误体形状）+ **整体不写入**（不允许部分生效）；读取时非法 → 回落内置默认 + 打日志（不让脏数据炸整条链路）。
6. **改动留痕**：`PUT` 成功写 `agent_stage_log(event_type='config_changed', detail='min_template_match 0.75→0.80 …')`。

### 3.5 配置表契约（`agent_stage_config`）

| 字段 | 类型 | 说明 |
| :---- | :---- | :---- |
| `teacher_name` | TEXT PRIMARY KEY | `''` = 全局默认行；其余 = 该老师专属行 |
| `config_json` | TEXT NOT NULL DEFAULT `'{}'` | 配置对象（JSON 存 TEXT，全库惯例） |
| `updated_at` | TEXT NOT NULL DEFAULT `''` | |

`config_json` 键表（★ = 与升级判定直接相关）：

| 键 | 默认值 | 含义 |
| :---- | :---- | :---- |
| `schema_version` | `1` | 配置契约版本（未知版本 → 只用内置默认 + 告警，不抛错） |
| `default_stage` | `learning` | 未初始化老师的兜底阶段（只允许 `observation` / `learning`） |
| `window_days` ★ | `90` | 指标统计窗口（天） |
| `max_samples` ★ | `50` | 每指标最多取样本数（性能上限） |
| `min_samples` ★ | `5` | 允许推荐升级的最少样本数 |
| `min_template_match` ★ | `0.75` | ① 达标阈值 |
| `min_modification_consistency` ★ | `0.80` | ② 达标阈值 |
| `max_violations` ★ | `0` | 窗口内允许的铁律违规样本数（超过即 `rule_reset`） |
| `max_permission_denials` ★ | `0` | 窗口内允许的越权次数（超过则该轮不得推荐升级） |
| `recommend_cooldown_hours` | `24` | 上次推荐 / 被拒后的冷却小时数 |
| `demote_consistency_floor` | `0.50` | 规则降级水位 |
| `demote_streak` | `3` | 连续命中次数才降级 |
| `truncate_chars` | `2000` | 相似度计算前的文本截断长度 |
| `template_match_weights` | `{"section_hit":0.6,"section_order":0.4}` | ① 内部权重 |
| `metrics_ttl_hours` | `24` | `last_metrics_json` 的「新鲜」窗口（只影响前端 `stale` 标记） |
| `matrix_enforced` | `true` | §2.5 的临时运维闸 |

**写入权限**：`PUT /api/agent/stage/config` **只允许写调用者自己那一行**（`teacher_name = 调用者`）；全局行 `''` 由迁移种子 + 运维 SQL 维护（**Epic 2 不引入管理员角色**，理由见 §7.1-④）。

### 3.6 升级触发链路（系统计算 → 推送通知 → 老师确认 → 生效 —— 批复 2）

```
[1] 评估触发点（三处，全部 best-effort，失败只打日志，绝不影响既有链路）
    · POST /api/agent/scan（既有统一扫描入口 main.py:1027-1042）→ 追加一次评估
    · sign_draft() 成功后（database.py:704-733 末尾）→ 追加一次评估（新病历 = 新样本）
    · POST /api/agent/stage/evaluate（老师手动，前端「立即評估」按钮）

[2] 评估 agent_stage_service.evaluate(teacher_name)
    · 读配置（§3.4）→ 算 ①②（§3.2/§3.3）→ 写 last_metrics_json + last_evaluated_at
    · 判定 can_recommend（下方伪码）→ 写 agent_stage_log(event_type='evaluation')

[3] 系统推荐（仅当 can_recommend 为真，且尚无待确认推荐时）
    · agent_stage_state.pending_stage = next_stage；pending_task_id = 新建请示 id
    · 写一条 agent_tasks（本 Epic 唯一新增的 agent_tasks 写入）：
        task_type = 'request'   category = 'agent'   status = 'pending'
        title     = '智能體可升入「見習期」'
        content   = '模板匹配度 82%（達標 75%）、病歷修改一致率 91%（達標 80%），樣本 7 份；'
                    '確認後生效，你可隨時降級。'
        action_data = {"action":"upgrade_agent_stage","from":"learning","to":"apprentice",
                       "metrics":{…},"config_source":{…}}
    · 去重：同老师 + action='upgrade_agent_stage' + status='pending' 已存在 → 不重复建单
    · 写 agent_stage_log(event_type='upgrade_recommended', task_id=…)

[4] 老师端推送（零新增通知系统、零弹窗打断）
    · 该行自动出现在老师端首页「🤖 智能体工作台 → ⏳ 待你确认」（App.tsx:2507-2518：
      该区块不按 category 过滤，只用 title/content + ✅/❌ 按钮，已实测）
    · 关页再回仍在（DB 持久化），不阻塞老师任何操作

[5] 老师点击确认（复用既有接口，零改动）
    · ✅ → POST /api/agent_tasks/approve {task_id} → database.resolve_agent_task(id,'approved')
           → 追加钩子（§4.2-3）：action == 'upgrade_agent_stage' → apply_stage_change(...)
           → stage 生效；写 agent_stage_log('stage_upgraded') + agent_action_log（人话 detail）
    · ❌ → POST /api/agent_tasks/reject → pending_stage 清空 + 记 'upgrade_declined' + 进冷却
```

`can_recommend` 判定（全真才推荐；任一不满足 → 进 `blockers` 列表，前端逐条展示原因）：
```
flag on
and matrix_enforced                        # 放宽态不推荐升级（§2.5）
and current_stage != 'authorized'          # 已是最高阶段 → next = null
and pending_stage == ''                    # 无待确认推荐
and now - last_recommend_or_decline > recommend_cooldown_hours
and template_match is not None and >= min_template_match
and modification_consistency is not None and >= min_modification_consistency
and samples >= min_samples
and violations <= max_violations
and permission_denials_in_window <= max_permission_denials
```

**为什么「必须老师确认」不可省**：升阶 = 老师把病历中的部分决策动作授权给智能体。系统只能**举证**（指标 + 样本数 + 阈值），授权必须由人给。代码上体现为：`stage` 的**向上写**只有 `confirm_upgrade` 一条路径（`manual_demote` / `rule_demote` / `rule_reset` 只能向下或不动）→ 守护测试 `test_stage_never_self_upgrades`：直接调 `evaluate()` 后断言 `stage` 不变、只新增 `pending_stage` 与请示行。

### 3.7 规则触发降级（自动，只降不升）

| 规则 | 触发条件 | 动作 |
| :---- | :---- | :---- |
| `rule_reset`（铁律回退） | 窗口内 ① 违规样本数 > `max_violations`（AI 填了 `writable_by='teacher'` 的段），或守护测试捕获非法写入尝试 | `stage → observation`、`stage_source='rule_reset'`、清 `pending_stage`、写 `agent_action_log`（`[stage_reset] 智能體輸出觸及禁區，已回退至觀察期`） |
| `rule_demote`（表现回退） | ② 有值且 `< demote_consistency_floor`（默认 0.50）连续 `demote_streak`（默认 3）次评估 | 降一级（不低于 `observation`）、`stage_source='rule_demote'`、清 `pending_stage`、写 `agent_action_log` |
| **不降级的情形** | 样本不足 / 指标为 `null` / flag off / 评估失败 | **什么都不做**（不能因为「数据不够」惩罚老师） |

自动降级属**限制方向**，故无需老师确认；但必须留 `agent_stage_log` + `agent_action_log`（工作台「📜 行动日志」区块自然可见）。

### 3.8 计算时机、性能与缓存

| 项 | 决定 |
| :---- | :---- |
| 触发时机 | 三处（§3.6 step 1）；**不在** `GET /api/agent/stage` 里重算（GET 恒快、无副作用、不改状态） |
| 缓存 | 评估结果写 `agent_stage_state.last_metrics_json`；`GET` 直接返回，并带 `stale = (now - last_evaluated_at) > metrics_ttl_hours` |
| 性能预算 | 每次评估 ≤ 3 次聚合查询 + ≤ `2 × max_samples` 次相似度计算；文本截断 2000 字符、样本上限 50 → 目标 **< 200 ms**（本地 SQLite） |
| 失败处理 | 评估整体包 `try/except`：异常 → 打日志 + `agent_stage_log(event_type='evaluation', detail='failed: …')` + **不改变任何阶段状态**；`sign_draft` / scan 调用方**绝不**因此失败 |
| 并发 | 状态表按 `teacher_name` 主键，评估在单连接单事务内读-改-写；同老师并发以「后写覆盖」为可接受语义（指标是快照，不是账本） |
| 采样成本上限 | 聚合查询只取窗口内 ≤ `max_samples` 行的两列文本，不做全表文本扫描 |

---

## 4. 现有代码盘点（改哪里 / 新建什么）

### 4.1 总览

| 文件 | 动作 | 一句话 |
| :---- | :---- | :---- |
| `backend/database.py` | **改 3 处 + 增 8 个函数** | 快照落库（生成 / 签字）、请示确认钩子、阶段相关读写函数 |
| `backend/agent.py` | **改 0 处既有代码，只追加**（文件末尾新段落） | 三个新能力的 prompt + LLM 薄封装（不碰任何既有字符串/函数） |
| `backend/main.py` | **改 3 处**（include_router、生成路径能力判定、scan 追加评估） | 挂载新路由 + 两处接入点 |
| `backend/models.py` | **追加** 3 个请求体（不改既有） | `AgentStageConfigInput` / `AgentStageActionInput` / `AgentStageSuggestInput` |
| `backend/conftest.py` | **改 1 行** | 注入 `AGENT_STAGE_ENABLED=on`（与 Epic 1 注入 template flag 同款） |
| `backend/agent_stage_service.py` | **新建** | 状态机 + 权限矩阵 + 配置读取 + ①②计算 + 推荐/生效/降级 |
| `backend/agent_stage_api.py` | **新建** | `/api/agent/stage*` 路由 + flag / 鉴权 / 错误体（照抄 `template_api.py` 骨架） |
| `backend/alembic/versions/0003_add_agent_stage.py` | **新建** | 3 张新表 + 2 个新列 + 种子（幂等 + 安全 downgrade） |
| `backend/test_agent_stage.py` | **新建** | Epic 2 验收测试（§6） |
| `frontend/src/AgentStagePanel.tsx` | **新建** | 阶段与一致率展示卡（自带 flag 探測，照 `TemplateStudio` 的探测口径） |
| `frontend/src/App.tsx` | **改 3 行**（import + 挂载 + 刷新计数） | 挂载阶段卡并随工作台刷新 |
| `docs/migrations/0003_add_agent_stage.sql` | **新建** | 离线预审 SQL（`--sql` 导出产物） |
| `template_service.py` / `template_api.py` / `templates` 表 | **零改动** | Epic 2 **只读** `get_active_record_template(teacher)` 用于 ①，写路径一字不碰 |
| `test_templates.py` / `test_api.py` / `test_migrations.py` | **零改动** | Epic 1 / 存量回归红线（§5.5） |
| `migrations_runner.py` | **零改动** | 通用 head 升级，自动带上 0003 |

### 4.2 `database.py` 改动点（逐条，含行号）

**改 1：`insert_draft()`（现状 `database.py:654-673`）—— 写入 AI 原始快照**

- 定位：函数内 `INSERT INTO drafts (…)` 附近；**不改函数签名、不改参数顺序、不改返回值**（既有调用方 `main.py:559-588` / `612-631` / `656-677` 零改动）。
- 改动：当 `drafts` 具备 `ai_original_content` 列（用 §0.3 同款探测辅助 `_drafts_supports_ai_original(cur)`，参照 `_drafts_supports_template_refs`，`database.py:640-651`）时，把同一份 `content` 同时写入 `ai_original_content`；否则退化为原 7 列插入。
- 纪律：**AI 原始快照 = 生成时刻的 `content`**，此后任何老师编辑都不再触碰它（②的基准）。

**改 2：`sign_draft()`（现状 `database.py:704-733`）—— 快照进历史 + best-effort 评估**

- 定位：插入 `patient_records` 的 SQL 附近（`visit_at` 等列同一批），以及函数末尾 `DELETE FROM drafts` 之后。
- 改动 a：`patient_records` 具备 `ai_original_text` 列时，写入"草案的 `ai_original_content`（为空则回落 `content`）"；否则走原 SQL。
- 改动 b：末尾追加 `try: import agent_stage_service; agent_stage_service.on_draft_signed(teacher_name) except Exception: print(warn)`。
  - 延迟 import（与 `save_plan_template` 里 `import template_service`，`database.py:1611-1613` 同款），回避循环引用。
  - **返回值、删除草案、`signed` 语义、`patient_records` 既有字段全部不变**。

**改 3：`resolve_agent_task()`（现状 `database.py:1520-1554`）—— 升级确认钩子**

- 定位：更新任务状态 + 写 `agent_action_log` 之后的末尾。
- 改动：追加分支 —— 若 `action_data.action == 'upgrade_agent_stage'`：`approved` → `agent_stage_service.apply_upgrade_confirmation(teacher_name, to_stage, task_id)`；`rejected` → `agent_stage_service.decline_upgrade(teacher_name, task_id)`。
- 纪律：整段包 `try/except`，**采纳失败只打日志**；`resolve_agent_task` 的返回值与既有语义（含学生类请示的 `deduct_herbs` / `send_notice` 分支）**一字不改**。

**新增 8 个函数**（追加到 `database.py` 的智能体区段末尾，紧邻 `resolve_agent_task` / `get_agent_action_log`，`database.py:1503-1576`）：

| 函数 | 作用 |
| :---- | :---- |
| `get_agent_stage_state(teacher_name)` | 读状态行（无行 → `None`，由服务层兜底，不在库里塞默认行） |
| `upsert_agent_stage_state(teacher_name, **fields)` | 单事务 upsert（`INSERT … ON CONFLICT(teacher_name) DO UPDATE`），只接受白名单字段 |
| `insert_agent_stage_log(teacher_name, event_type, **fields)` | 只增写入审计（**不提供 update/delete 函数**，从代码层面保证只增） |
| `get_agent_stage_logs(teacher_name, limit=20)` | 倒序读审计（前端调试 / 运维核对用） |
| `get_agent_stage_config_row(teacher_name)` | 读单行 `config_json`（无行 → `None`） |
| `upsert_agent_stage_config(teacher_name, config_json)` | 写单行（服务层已校验） |
| `find_pending_upgrade_task(teacher_name)` | 升级推荐去重：查 `agent_tasks` 里 `status='pending'` 且 `action_data` 含 `upgrade_agent_stage` 的行 |
| `insert_agent_stage_upgrade_task(teacher_name, title, content, action_data)` | 写升级推荐请示（返回新 `task_id`；字段顺序与既有两处裸 INSERT 一致） |

- 风格纪律：`sqlite3` 裸 SQL、`TEXT` 时间、`json.dumps(..., ensure_ascii=False)`、`try/except sqlite3.Error` + `print` 日志 —— 与既有 24+ 张表函数完全一致；**不新增 ORM、不新增依赖**。
- **请示写入方式（实测后修正）**：全库**没有** `create_agent_task()` 这类封装，`agent_tasks` 写入是两处裸 INSERT（`agent.py:578` 的 `_insert_student_request`、`database.py:1491` 的沉默学生扫描）。Epic 2 的处置：**不动既有两处**（零回归风险），在新增函数 `insert_agent_stage_upgrade_task(teacher_name, task_id_out…)` 内按同一字段顺序裸 INSERT（`task_type='request'` / `category='agent'` / `status='pending'`），字段集与既有请示**完全同构** → 既有前端渲染、`resolve_agent_task`、`get_agent_tasks` 全部无需改动即可适配。
- **去重实现**：不复用 `agent.py:553` 的私有 `_pending_task_exists`（跨模块调用私有函数会制造隐式耦合），改为在 `database.py` 新增 `find_pending_upgrade_task(teacher_name)`（同 SQL 逻辑、`action_data LIKE '%upgrade_agent_stage%'`）。

### 4.3 `agent.py` 改动点（**既有代码零改动，仅末尾追加**）

- 现有 `agent.py` 结构（实测）：`PATIENT_PROMPT:33`、`DOCTOR_PROMPT:79`、`structurize_teacher_note:187`、`CLEAN_TRANSCRIPT_PROMPT:200`、`CLEAN_PLAN_PROMPT:262`、`TEN_QUESTIONS:318`、`ask_next_question:426`、`save_intake:498`、学生请示区段 `541-698`（含 `scan_student_requests:685`）。
- **追加位置**：文件**末尾**新增一段注释标题 `# =====【Epic 2】老師智能體五階段：新增能力（追加，既有段落一字不改）=====`，其下追加 3 组「prompt 常量 + 薄封装函数」：

| 新增符号 | 对应阶段能力 | 输出契约（严格 JSON → 纯文本兜底） |
| :---- | :---- | :---- |
| `PATTERN_CANDIDATE_PROMPT` + `predict_pattern_candidates(patient_name, complaint, transcript, past_records, teacher_skeleton)` | 见习期 `predict_pattern` | `{"candidates":[{"name":"…","confidence":"high|medium|low","basis":["症状…"],"note":"…"}],"disclaimer":"僅供參考，非診斷"}`；**最多 3 条候选**；`basis` 至少 1 条且必须引用病历原文片段；解析失败 → `{"candidates":[],"error":"parse_failed"}`（**绝不编造**） |
| `FORMULA_SUGGESTION_PROMPT` + `suggest_formula(…)` | 助手期 `suggest_prescription` | `{"formulas":[{"name":"小柴胡湯","modification":"加減…","composition":["柴胡","黃芩",…],"usage":"僅供參考"}],"disclaimer":"僅供參考，非處方"}`；**不含剂量、不含煎法用量、不含落库字段**（与授权期预处方刻意区分） |
| `PREDRAFT_PROMPT` + `generate_predraft(…)` | 授权期 `generate_predraft` | `{"predraft":{"formula_name":"…","items":[{"herb":"柴胡","dose":"9g","role":"君"}],"decoction":"…"},"disclaimer":"僅供參考，須老師確認並自行開方"}`；**仅返回数据，不落库、不发送、不签字** |

- 三个新 prompt **必须**包含禁区段（写法照抄 `PATIENT_PROMPT:35` / `DOCTOR_PROMPT:81` 的 `【绝对禁止】` 段落），额外加两条专属禁区：
  - 「不得輸出『診斷為』『確診』等結論性表述；只可輸出候選證型並標註僅供參考」；
  - 「不得自行開具處方、不得生成可自動發送的內容、不得代替老師簽字」。
- 所有新函数：入参全部为**纯文本 / dict**，**不 import `database`**（现有 `agent.py` 顶部依赖 `database` 的引用与用法不新增、不改动）→ 保证「AI 层只能产出文本，落库永远由服务层在老师确认路径上完成」。
- **既有函数与 prompt 字符串一字不改**（`generate_medical_draft` 仍是唯一病历生成入口 → §5.1 红线 2）。

### 4.4 `main.py` 改动点（逐条，含行号）

| # | 位置 | 改动 | 纪律 |
| :---- | :---- | :---- | :---- |
| 1 | `main.py:44-49`（`include_router(template_api.router)` 旁） | 追加 `app.include_router(agent_stage_api.router)` | 只增一行；`template_api` 的注册与异常处理器不动 |
| 2 | `main.py:559-588` `_record_template_ref` / `_generate_and_store_llm_draft`（三条生成路径的共同出口） | 入口处追加 `if not agent_stage_service.require_capability(teacher_name, "generate_draft"): 走本地骨架路径（§5.3）` | **flag off 时 `require_capability` 恒返回 True** → 今天行为逐字节不变；flag on 且阶段 = `observation` 时才走骨架 |
| 3 | `main.py:1027-1042` `POST /api/agent/scan` | 末尾追加 `stage = agent_stage_service.evaluate(teacher_name)`（best-effort，try/except），响应体**只增** `stage` 字段 | 既有的 `alerts` / `scan_student_requests` 逻辑与响应字段不动；失败仍返回原结构 |
| 4 | `main.py:1051-1064` `POST /api/agent/tasks/{task_id}/resolve` 与 `1083-1099` approve/reject | **零改动** | 升级确认复用它们（钩子落在 `database.resolve_agent_task` 内，见 §4.2 改 3） |

- 新增路由统一走 `agent_stage_api.py`（不往 `main.py` 里塞新 endpoint，沿用 Epic 1 的 `template_api.py` 分文件纪律）。
- `main.py` **不 import** `agent_stage_service` 之外的新模块；`AgentStageError` 的翻译放在 `agent_stage_api` 内部（`main.py` 只需保证该 router 已挂载）。

### 4.5 新建文件清单（职责与公开符号）

**① `backend/agent_stage_service.py`**（纯业务，**零 DDL**，DDL 全归迁移 0003）

| 公开符号 | 职责 |
| :---- | :---- |
| `AGENT_STAGE_ENABLED_VALUES` / `agent_stage_enabled()` | flag 判定（默认 off），照抄 `template_service.py:898-909` 实现 |
| `STAGES` / `STAGE_RANK` / `STAGE_LABELS` / `CAPABILITIES` / `CAPABILITY_MIN_STAGE` | 五阶段与能力矩阵常量（§0.4 / §2.3，**唯一真相源**） |
| `DEFAULT_STAGE_CONFIG` | 内置兜底默认（§3.5，**唯一硬编码点**） |
| `load_stage_config(teacher_name)` / `validate_stage_config(cfg)` | 读取链 + 校验（§3.4） |
| `current_stage(teacher_name)` / `describe_stage(teacher_name)` | 真值读取（§1.5，fail-safe） |
| `require_capability(teacher_name, capability)` | **唯一能力闸门**（§2.2 / §2.3） |
| `compute_template_match(teacher_name, cfg)` / `compute_modification_consistency(teacher_name, cfg)` | ①② 指标（§3.2 / §3.3） |
| `evaluate(teacher_name)` | 评估 + 推荐 + 规则降级（§3.6 / §3.7），返回指标快照与 `blockers` |
| `on_draft_signed(teacher_name)` | `sign_draft` 后的薄钩子（best-effort，内部 try/except） |
| `apply_upgrade_confirmation(teacher_name, to_stage, task_id)` / `decline_upgrade(...)` | 老师确认 / 忽略后的生效与回退 |
| `demote(teacher_name, to_stage, reason, source='manual_demote')` | 老师手动降级 |
| `build_suggestion(teacher_name, draft_id, kind)` / `build_predraft(teacher_name, draft_id, formula_name='')` | 三个新能力的服务侧入口（含能力校验 + 审计） |
| `AgentStageError(code, msg, errors=None, warnings=None)` | 服务层异常，形状与 `TemplateError` 一致 |

- **禁止 import 清单**（守护测试断言）：`create_prescription` / `sanitize_prescription_items` / `batch_deduct_herbs` / `sign_draft` / `update_draft_content` / `save_prescription`（§2.1）。
- 允许 import：`database`（只调 §4.2 的 8 个新函数 + `get_drafts` / `get_agent_action_log` 等只读函数 + `insert_agent_action_log`）、`template_service`（只读 `get_active_record_template` / `record_section_skeleton`）、标准库 `json` / `os` / `difflib` / `datetime`。

**② `backend/agent_stage_api.py`**（路由 + 门卫，骨架照抄 `template_api.py`）

| 公开符号 | 职责 |
| :---- | :---- |
| `router = APIRouter(prefix="/api/agent/stage", tags=["agent-stage"])` | 新路由前缀（**与 `/api/agent/tasks*`、`/api/agent/scan` 无冲突**，实测无重叠前缀） |
| `_enabled()` / `_fail(status, code, msg, errors, warnings)` / `_guard(teacher_name, teacher_id)` | flag → 404 `agent_stage_disabled`；`teacher_name` 必填 → 400；`teacher_id` 与 `teacher_name` 不一致 → 403 `teacher_mismatch`；表未就绪（`sqlite3.Error`）→ 503 `agent_stage_store_unavailable`；错误体一律 `{detail:{error,msg,errors,warnings}}` |
| 7 个 endpoint 函数 | §4.6 |

**③ `backend/alembic/versions/0003_add_agent_stage.py`**：`revision='0003'` / `down_revision='0002'`；`upgrade()` 建 3 表 + 索引 + 2 列（探测幂等）+ 种子；`downgrade()` 带安全闸（§1.4）。文件头注释写清「DDL 唯一真相源」与「不删列」理由（照 0002 的文件头风格）。

**④ `backend/test_agent_stage.py`**：§6 全部用例（约 34 条）。

**⑤ `frontend/src/AgentStagePanel.tsx`**：老师端首页「🧭 智能體階段」卡。

- 探測：`GET /api/agent/stage?teacher_name=&teacher_id=` → 404/503 → **整卡不渲染**（与 `TemplateStudio` 一致）；成功才渲染。
- 展示：阶段徽章（繁体）、`stage_since`、① ② 数值（百分比 + 样本数 + `approx` 提示）、下一阶段与 `blockers`（例如 `模板匹配度 0.62 < 0.75`）、`config_source` 若有 `teacher_override`/`env_override` 显示来源角标、`stale` 时显示 `指標可能已過時，可點「立即評估」`。
- 按钮：`🔄 立即評估`（POST evaluate）、`⬇ 降級`（先弹**卡内**二次确认区，不打断页面；带 `reason` 输入，默认 `由老師主動降級`）。
- 能力区（按 `capabilities` 渲染）：见习期/助手期/授权期各自的「建議」入口按钮 `🧪 證型候選` / `📜 方劑建議` / `🧾 預處方預填`，未开放时按钮置灰 + 繁体原因文案（`尚未開放（需「見習期」）`）。
- 铁律文案（固定显示在卡片底部，不可省略）：`智能體永不診斷、永不開方、永不簽字；一切建議僅供參考，採用即為你的決定。`
- 样式复用：内联 style + `#8b4513` / `#fdfcf0` / serif（与 `TemplateStudio` / `App.tsx` 一致），**不新增 npm 依赖、不引 UI 库**。

**⑥ `docs/migrations/0003_add_agent_stage.sql`**：`alembic upgrade head --sql` 产物，供 DBA / CTO 离线预审（沿用 0001 的产物习惯）。

> **CTO 追补（2026-09-28）**：step 2.2 按 §7 裁决②方案 B，在 `agent_stage_service.py` **提前落地** `AGENT_STAGE_ENABLED_VALUES` 与 `agent_stage_enabled()`（供 `database.py` 延迟 import 使用）。符号口径**照抄 `template_service.py:897-909`**。

### 4.6 接口清单（新增 7 个，全部 `AGENT_STAGE_ENABLED` 门后）

| # | 方法 / 路径 | 入参 | 出参（要点） | 主要错误码 |
| :---- | :---- | :---- | :---- | :---- |
| 1 | `GET /api/agent/stage` | `teacher_name`、`teacher_id` | `{teacher_name, stage, stage_label, stage_since, stage_source, pending_stage, pending_task_id, capabilities{…}, metrics{template_match, modification_consistency, inquiry_preference_consistency:null}, thresholds, next_stage, blockers[], config_source, stale, degraded}` | 404 `agent_stage_disabled`／400 `teacher_required`／403 `teacher_mismatch`／503 `agent_stage_store_unavailable` |
| 2 | `POST /api/agent/stage/evaluate` | `{teacher_name, teacher_id}` | 同 #1 结构 + `changed:{stage_changed, recommended, demoted, reason}` | 同上（+ 无 403 `stage_forbidden`：`record_observation` 全员可用） |
| 3 | `GET /api/agent/stage/config` | `teacher_name`、`teacher_id` | `{effective{…}, source{global, teacher_override, env_override}, defaults{…}}` | 同 #1 |
| 4 | `PUT /api/agent/stage/config` | `{teacher_name, teacher_id, config{…}}` | `{effective{…}, source{…}, warnings[]}` | 400 `stage_config_invalid`（`errors:[{path,msg}]`）／403 `teacher_mismatch` |
| 5 | `POST /api/agent/stage/demote` | `{teacher_name, teacher_id, to_stage, reason}` | `{stage, previous_stage, stage_since, stage_source:'manual_demote'}` | 409 `stage_transition_invalid`（同阶段 / 高于当前）／400 `stage_invalid_value` |
| 6 | `POST /api/agent/stage/suggest` | `{teacher_name, teacher_id, draft_id, kind:'pattern'\|'formula'}` | `{kind, draft_id, payload{…候选/方剂…}, disclaimer, generated_at}` | **403 `stage_forbidden`**（阶段不足，含越权审计）／400 `stage_kind_invalid`／404 `stage_draft_not_found` |
| 7 | `POST /api/agent/stage/predraft` | `{teacher_name, teacher_id, draft_id, formula_name?}` | `{draft_id, predraft{formula_name, items[{herb,dose,role}], decoction}, disclaimer, note:'僅供預填，儲存處方仍須老師操作'}` | **403 `stage_forbidden`**／404 `stage_draft_not_found` |

- 服务端数据来源**只信 DB**：`suggest` / `predraft` 用 `draft_id` 反查 `drafts`（取 `patient_name` / `content` / 病史），**不接受客户端上传的病历文本**（防注入伪造与越权样本污染指标）。
- 「採用」动作**不设新接口**：前端把候选/预处方填入既有编辑框，落库一律走既有 `PUT /api/drafts/{id}`（老师编辑）或 `POST /api/prescriptions`（老师开方）→ **AI 永不落库**由路由面直接保证。
- 越权语义统一：能力不足 → **403 `stage_forbidden`**（不是 404，便于前端区分「功能没开」与「阶段不够」；也不静默降级产出，避免老师误以为 AI「正在思考」）。

### 4.7 前端改动（`App.tsx` 精确到 3 处，其余全在新组件里）

| # | 位置 | 改动 |
| :---- | :---- | :---- |
| 1 | `App.tsx:3`（`import TemplateStudio from './TemplateStudio'` 旁） | 追加 `import AgentStagePanel from './AgentStagePanel'` |
| 2 | `App.tsx:359-361`（三区块 state 声明旁） | 追加 `const [agentStageRefreshKey, setAgentStageRefreshKey] = useState(0)`；并在 `fetchAgentWorkbench()`（`App.tsx:879`）末尾追加 `setAgentStageRefreshKey(k => k + 1)` → 老师点 ✅ 确认 / ❌ 忽略后（既有 `handleApproveAgentTask` 会调 `fetchAgentWorkbench`，`App.tsx:969-990`）阶段卡自动刷新 |
| 3 | `App.tsx:2554`（智能体工作台卡 `{…}` 结束之后） | 追加 `{(currentRole === '李老师' || currentRole === '李老师智能体') && teacherTab === 'home' && (<AgentStagePanel teacherName={selectedTeacher} teacherId={selectedTeacher} refreshKey={agentStageRefreshKey} />)}` |

- 既有三区块的 JSX、`handleApproveAgentTask` / `handleRejectAgentTask`、`handleAgentScan` **一行不改** → 「推送 → 确认 → 生效」全程复用既有 UI（批复 2 的「不弹窗打断」天然满足）。
- 全部 UI 文案为繁体古字；探測失败（404 / 503 / 网络异常）一律**整卡不渲染**，不影响首页其它区块。


---

## 5. 与 Epic 1（及存量病历链路）的兼容策略

### 5.1 四条红线

| 红线 | 具体承诺 | 验证方式 |
| :---- | :---- | :---- |
| **① flag off = 逐字节 1:1** | `AGENT_STAGE_ENABLED` 未设置 / off 时：不写任何新表、不写两个快照列、不建请示、不算指标、不改任何响应字段、`/api/agent/stage*` 全部 **404 `agent_stage_disabled`** | 用例：清空 flag 后跑「生成 → 编辑 → 签字」全链路，断言草案内容与签字后 `patient_records` 字段**与改动前完全一致**；断言两张新表行数为 0、`ai_original_content` / `ai_original_text` 仍为空串 |
| **② 提示词不改** | `agent.py` 中 `PATIENT_PROMPT` / `DOCTOR_PROMPT` / `CLEAN_TRANSCRIPT_PROMPT` / `CLEAN_PLAN_PROMPT` / `TEN_QUESTIONS` / 问诊 prompt **一字不改**；病历草案仍只由 `generate_medical_draft()` 产出 | 用例：断言上述常量的字符串哈希与 Epic 1 基线一致（写死期望值，防误改） |
| **③ 既有函数签名与语义不改** | `insert_draft` / `update_draft_content` / `sign_draft` / `resolve_agent_task` / `get_agent_tasks` / `get_drafts` 的**参数、返回值、事务语义、删除草案行为**全部不变（只做「追加列写入」与「末尾 best-effort 钩子」） | 用例：Epic 1 与存量测试全绿（§5.5）+ 针对签字后 `drafts` 行被删的既有断言 |
| **④ 新能力必须新入口** | 见习期 / 助手期 / 授权期能力**不嵌入**既有生成路径，全部走 `/api/agent/stage/*` 新接口；既有三条生成路径（`/api/transcribe`、`/api/upload`、`/api/generate-draft`）在 flag on + 阶段 ≥ learning 时**输出与今天一致** | 用例：`apprentice`/`assistant`/`authorized` 三种阶段下跑既有生成路径，断言草案内容与 `learning` 阶段一致（阶段只影响增量能力，不影响既有输出） |

### 5.2 存量老师初始化：默认 `learning`（**不降级、不破坏**）

- 今天系统对**所有**老师都已提供「生成病历草案」→ 存量老师的能力等级天然是 `learning`。
- 因此：迁移 0003 种子把现存老师写成 `learning`；配置 `default_stage` 默认 `learning`（未初始化老师同样按 `learning` 兜底）。
- 结果：**打开 flag 的那一刻，存量老师的能力集合与之前完全相同**（只是多了一张阶段卡与指标计算）→ 符合「Epic 2 不得破坏 Epic 1 / 存量病历生成」。
- `observation` 的真实适用对象是**新加入的老师**（尚未积累任何草案/签字样本）：从 `observation` 起，靠样本 + 一致率自动进入 `learning`（仍需老师确认，§3.6）。
- 若要「全体老师一律从观察期起」：把种子 UPDATE 成 `observation` + 把 `default_stage` 配成 `observation` 即可，**零代码改动**（§7.1-②）。届时这些老师会走 §5.3 的降级生成路径，需先与业务确认（因此**不作为默认**）。

### 5.3 `observation` 期的生成路径（只在 flag on 且该老师处于观察期时生效）

```
POST /api/transcribe / /api/upload / /api/generate-draft
        │
        ├─ require_capability(teacher, "generate_draft")
        │        ├─ True  → 既有 LLM 路径（与今天完全一致，含 template 骨架提示）
        │        └─ False → 本地骨架路径：build_draft_template(...)（main.py:92 既有函数）
        │                   · 不调用任何 LLM（智能体零输出）
        │                   · 草案正文首行加提示：『【觀察期】智能體尚未參與，以下為本地骨架，請老師自行填寫。』
        │                   · 仍走 insert_draft 落库（含快照列）→ 老师可正常编辑 / 签字
        └─ 两条路径的后续步骤（记录模板引用、返回结构、老师编辑、签字）完全一致
```

- **为什么不让观察期直接不出草案**：会让老师端「接收学生陈述」出现空窗（既有关键链路断裂）。降级为本地骨架既保持链路可用，又严格保证**智能体不参与**（铁律精神一致）。
- 该路径仅对 `observation` 阶段的老师生效；`learning` 及以上与 flag off 时**永不触发**（用例锁定）。

### 5.4 `templates` / `template_service` / `template_api` 零改动

- Epic 2 对 Epic 1 的依赖**只有两个只读调用**：`template_service.get_active_record_template(teacher_name)` 与 `record_section_skeleton(schema)`（`template_service.py:912-959`）→ 用于 ① 的基准骨架。
- **不**读写 `templates` 表任何写路径、**不**调用 `template_api` 的任何 endpoint、**不**改 `draft.template_id` / `template_version` 语义（它们仍由 Epic 1 的 `_record_template_ref` 与 `save_plan_template` 维护）。
- 若老师**没有**生效病历模板：① 变为 `value=null` + `blockers: no_active_record_template`，不报错、不阻断（与 Epic 1「模板可缺省」口径一致）。

### 5.5 回归与灰度清单

| 项 | 要求 |
| :---- | :---- |
| Epic 1 测试 | `test_templates.py` **一字不改、全绿** |
| 存量测试 | `test_api.py`（病历全链路）、`test_migrations.py` 全绿；`pytest.ini` 不改 |
| 迁移顺序 | `init_db()` → `run_upgrade()`（`conftest.py` 现状）→ 0003 自动生效；重复启动幂等 |
| 灰度顺序 | ① 迁移先上（flag off，零行为变化）→ ② 代码上（flag off，仍零行为变化）→ ③ 单老师 lab 打开 `AGENT_STAGE_ENABLED=on`（该老师已在 `learning`）→ ④ 观察指标卡 → ⑤ 全量 |
| 回退顺序 | ① flag 置 off（新接口立即 404、阶段评估停止、既有链路不变）→ ② 如需回收：`alembic downgrade 0002`（删 3 张新表，保留两个快照列）→ ③ 无需回滚病历 / 模板数据（全程未触碰） |

修正（2026-09-28 CTO 批复）：§5.5「test_migrations.py 零改动」的语义是「不改测试断言」。为配合 Alembic head 演进，允许将硬编码的 head 字面量改为动态查询（ScriptDirectory.from_config），属必要的健壮性打磨，不违反本节。

---

## 6. 验收与测试清单（`backend/test_agent_stage.py`，约 34 条）

### 6.1 状态机（8 条）

1. `test_default_stage_when_no_row` —— 无状态行 → `default_stage`（`learning`）+ `stage_source='default'`，且**不写库**。
2. `test_default_stage_rejects_high_value` —— 配置 `default_stage='authorized'` → 400 `stage_config_invalid`（fail-safe 方向）。
3. `test_invalid_stage_value_falls_back` —— 手动把库里改成 `'vip'` → 读取回落 `default_stage` + 记 `evaluation` 日志。
4. `test_stage_never_self_upgrades` —— 调 `evaluate()` 达标后，`stage` 不变、`pending_stage='apprentice'`、请示行 `status='pending'`。
5. `test_confirm_upgrade_applies` —— 走 `POST /api/agent_tasks/approve` → `stage='apprentice'`、`stage_source='teacher_confirm'`、`pending_stage=''`。
6. `test_reject_upgrade_keeps_stage` —— ❌ → `stage` 不变、`pending_stage=''`、`upgrade_declined` 日志、冷却生效。
7. `test_upgrade_recommend_dedup` —— 连续两次 `evaluate()` → 请示仅 1 条。
8. `test_no_skip_levels` —— 直接请求升到 `authorized`（`POST /api/agent/stage/demote` 反方向 / 内部 `apply_upgrade_confirmation` 越级）→ 409 `stage_transition_invalid`。

### 6.2 权限矩阵（10 条，Epic 2 核心验收）

9–13. `test_matrix_<stage>_capabilities`（五个阶段各 1 条）—— 断言 `capabilities` 五键组合与 §2.3 表格**完全一致**（参数化：`observation=[T,F,F,F,F]` … `authorized=[T,T,T,T,T]`）。
14. `test_deny_logs_permission_denied` —— `learning` 调 `suggest(kind='pattern')` → 403 `stage_forbidden` + `agent_stage_log` 有 `permission_denied`（含 `capability='predict_pattern'`）。
15. `test_deny_does_not_touch_business_tables` —— 越权调用前后 `drafts` / `patient_records` / `prescriptions` 行数与内容不变。
16. `test_matrix_single_choke_point` —— 源码扫描：`current_stage(` 除 `agent_stage_service.py` / `agent_stage_api.py` 外无调用点。
17. `test_no_forbidden_imports` —— 源码扫描 `agent_stage_service.py` 不含 `create_prescription` / `sign_draft` / `update_draft_content` / `batch_deduct_herbs`。
18. `test_matrix_disabled_relaxes_only_l2` —— `matrix_enforced=false` → 三个新能力放行，但铁律守护测试仍全绿。
19. `test_permission_denied_blocks_upgrade` —— 窗口内 1 次越权 + 指标全达标 → 不推荐升级（`blockers` 含 `permission_denied_in_window`）。

### 6.3 一致率计算（8 条）

20. `test_template_match_perfect` —— 草案完全按模板段名与段序 → `value ≈ 1.0`。
21. `test_template_match_missing_sections` —— 缺 2 段 → 命中率 0.6（按 5 段算）+ 段序一致率下降，落值可复算。
22. `test_template_match_teacher_section_filled_is_violation` —— AI 填了 `writable_by='teacher'` 的段 → 该样本 `match=0`、`violations+1`。
23. `test_template_match_skips_stale_and_no_template` —— `template_id=0` 与旧版 `template_id` 分别计入 `skipped_no_template` / `skipped_stale_template`，不进均值。
24. `test_modification_consistency_strict_pair` —— 新数据（`ai_original_text` 有值）→ ② 与手算 `SequenceMatcher` 一致。
25. `test_modification_consistency_approx_pair` —— 旧数据（只有 `ai_draft`）→ 计入均值且 `approx_samples=1`。
26. `test_metrics_null_when_no_samples` —— 无样本 → `value is None`（**不是 0**）+ 对应 `blockers`。
27. `test_inquiry_metric_is_null_placeholder` —— ③ 恒为 `null` 且 `reason='deferred_to_epic3'`。

### 6.4 配置化阈值与升级判定（5 条）

28. `test_thresholds_read_from_config_row` —— 全局行 / 老师行 / env 三级覆盖顺序正确（参数化 3 条断言）。
29. `test_threshold_change_alters_decision` —— 把 `min_template_match` 调到 0.99 → 原本达标变为不推荐（**证明没有硬编码**）。
30. `test_config_validation_rejects_bad_values` —— 越界值 → 400 `stage_config_invalid` + **整体未写入**（读回仍是旧值）。
31. `test_config_write_logged` —— 成功 PUT → 有 `config_changed` 日志。
32. `test_demote_rules` —— 铁律违规 → `rule_reset` 回 `observation`；② 连续 3 次低于水位 → `rule_demote` 降一级；样本不足时**不降级**。

### 6.5 兼容与回归（含 Epic 1 红线，6 条）

33. `test_flag_off_is_byte_identical` —— flag off：三条生成路径输出与基线一致、两张新表 0 行、两个快照列为空串、`/api/agent/stage` → 404。
34. `test_flag_off_transcribe_full_flow` —— 生成 → 老师编辑（`PUT /api/drafts/{id}`）→ 签字：`patient_records` 字段与既有断言一致（含 `ai_draft` / `final_plan` / `visit_at`）。
35. `test_prompts_unchanged` —— 6 个 prompt 常量哈希等于写死的 Epic 1 基线值。
36. `test_existing_generation_same_across_stages` —— `learning` / `apprentice` / `assistant` / `authorized` 四阶段下既有生成输出一致（阶段不影响既有链路）。
37. `test_observation_uses_local_skeleton` —— 观察期老师生成 → 草案含『【觀察期】』提示、`llm` 未被调用（monkeypatch 断言）、仍可编辑签字。
38. `test_epic1_and_legacy_suites_still_pass` —— 由 CI/命令行整体跑（`pytest backend -q`），`test_templates.py` 与 `test_api.py` 零改动零失败。

### 6.6 迁移（2 条）

39. `test_migration_0003_idempotent` —— `run_upgrade()` 连跑两次无异常；三表存在、两列存在、种子 1 行不重复。
40. `test_migration_0003_downgrade_safety` —— 无业务日志时可 `downgrade 0002`；有业务日志时**中止并提示导出**；两个快照列在 downgrade 后仍在。

> 说明：以上 40 项按功能归为 6 组（编号含参数化展开前的条目），落在 `test_agent_stage.py` 中实际约 34 个测试函数。

---

## 7. 已决技术选择（CTO 一次审核）与风险

### 7.1 已决技术选择表（批复 4：按最稳妥方案直接给定，可单条推翻）

| # | 议题 | 结论 | 理由 | 备选（未采用） | 影响面 |
| :---- | :---- | :---- | :---- | :---- | :---- |
| ① | ② 指标的数据基准 | **新增两个不可变快照列**：`drafts.ai_original_content`（生成时写）+ `patient_records.ai_original_text`（签字时写） | 今天的 `update_draft_content` 是**原地覆盖**、`sign_draft` 会**删掉草案行** → AI 原始文本无处存取，② 无从计算；快照是唯一可靠基准 | 在 `agent_learning_events`（Epic 3 表）里存 → **越界**：Epic 2 不该建 Epic 3 的表，且表未建则 ② 无法实现 | 2 个 `ADD COLUMN`（`DEFAULT ''`，零回填、零迁移风险）；`insert_draft` / `sign_draft` 各加一段追加写 |
| ② | 存量老师的初始阶段 | **迁移种子 = `learning`**，`default_stage` 默认 `learning` | 今天所有老师都已有「生成病历草案」能力 → 打开 flag 时能力集合不变，才叫「不破坏 Epic 1」 | 一律 `observation` → 会让存量老师立刻失去 LLM 草案（业务中断），需业务先确认 | 一个 INSERT…SELECT；想改成 `observation` 只改种子 + 配置，零代码 |
| ③ | 观察期的「只记录」如何落地 | 观察期**关闭 LLM 生成**，改走 `build_draft_template` 本地骨架 + 繁体提示语（链路不断，智能体零输出） | 既守住「只记录」，又不让老师端的收诊链路出现空窗 | ①完全不生成草案（链路断 3~5 天新师体验差）；②照旧生成但标「仅供参考」（违反阶段语义） | 只在 flag on + `observation` 生效；`learning` 及以上与 flag off 完全不触发 |
| ④ | 阈值配置的写入权限 | 老师**只能写自己那行**；全局行由迁移种子 + 运维 SQL 维护 | Epic 2 无管理员角色体系，**不新造角色**（造了就是范围外的新鉴权设施） | 新增 admin 角色 / 全局行接口 → 引入未定义鉴权，风险大于收益 | `PUT config` 加一行身份断言；全局行不可经 API 写（返回 403 `teacher_mismatch`） |
| ⑤ | 升级推荐的落点 | 复用**既有** `agent_tasks` + 既有 ✅/❌ 通道（`category='agent'`） | 实测工作台「⏳ 待你确认」区块**不按 category 过滤**（`App.tsx:2507-2518`）→ 零前端改动即满足「推送通知、不弹窗」 | 新建通知表 / 前端弹窗 → 前者重复造轮子，后者明确被 CTO 否掉（不打断） | 新增 1 个裸 INSERT 函数 + `resolve_agent_task` 末尾 1 个钩子分支 |
| ⑥ | 阶段审计的形态 | 新增 `agent_stage_log`（只增、无 update/delete 函数），另在**少数关键节点**写一行 `agent_action_log` 供工作台「行动日志」直接显示 | 治理审计需结构化可查；同时保持零前端改动。**不建哈希链**（Epic 3 范围） | 复用 `agent_action_log` 单表 → 结构不足以查询「越权/配置变更/降级原因」 | 1 张新表 + 1 个只读函数；`agent_action_log` 只写 3 类事件 |
| ⑦ | 相似度算法与依赖 | 标准库 `difflib.SequenceMatcher.ratio()` + 归一化 + 双侧截断 2000 字符 | 零新依赖（符合 §0.3）；与 Epic 3 的字段级 diff 共用同一套归一化 | 手写 Levenshtein（更慢、更长代码）；`python-Levenshtein`（新依赖，需过供应链） | 后端依赖清单不变；样本上限 50、目标 < 200 ms |
| ⑧ | 阶段真值读取失败的方向 | **fail-closed 到 `default_stage`**，且 `default_stage` 仅允许 `observation` / `learning` | 「读不到」绝不能变成权限放大；同时不能因 DB 抖动阻断既有生成 | 读取失败即拒绝一切能力 → 会打断既有病历生成（不可接受） | 配置校验加一条枚举限制；`degraded` 标记回传前端 |
| ⑨ | 三个新能力的入口位置 | 全部走 `/api/agent/stage/*` **新接口**，不嵌入既有生成路径 | 「新能力 = 新入口」才能保证既有输出 1:1（§5.1 红线 ④），也让权限拒绝点清晰 | 在 `/api/transcribe` 响应里塞候选证型 → 既有响应体变化 + 拒绝语义混乱 | 7 个新 endpoint；`main.py` 只加 2 处接入 |
| ⑩ | `matrix_enforced=false` 的边界 | 只放宽 L2 阶段门控；**铁律、flag 总闸、审计一律不放宽** | 「可配置关闭」是运维闸而非产品态；铁律任何情况不放开 | 连铁律一起放宽 → 直接违背 CTO 三条基准 | 前端必须红字提示「權限矩陣已由管理員放寬（臨時）」 |
| ⑪ | 迁移 vs `init_db()` 建表 | 新表 DDL 走 **Alembic 0003**，`init_db()` 不新增 DDL | 延续 Epic 1 §1.1「DDL 唯一真相源 = 迁移脚本」纪律；`conftest.py` 已跑 `run_upgrade()` | 沿用 `CREATE TABLE IF NOT EXISTS` → 与 Epic 1 的迁移纪律冲突（§0.3 已列为遗留例外，不再扩大） | 1 个迁移文件 + 1 份离线 SQL；`init_db()` 零改动 |
| ⑫ | 两处「越权语义」的 HTTP 码 | 能力不足 = **403 `stage_forbidden`**；功能未开 = **404 `agent_stage_disabled`** | 前端需区分「阶段不够（可解释、可引导）」与「功能没开（不渲染）」 | 统一 404 → 前端无法给老师「差多少」的解释 | 前端阶段卡的置灰/引导文案 |

### 7.2 请 CTO 一次审核的 5 项（**均不阻塞开工**，任一被推翻只改对应局部）

| # | 待确认 | 我的默认处置（已写入本设计） | 若被推翻的改动面 |
| :---- | :---- | :---- | :---- |
| 1 | 病历正文是否需要标注「此段由智能體建議、老師採用」 | **不标注**（本 Epic 不加来源标记），仅把「老师点採用」留在 `agent_stage_log` 的 `suggestion_generated` 里；病历正文与今天同构 | 若要求标注 → `drafts.content` 需带来源元数据（草案段落级标记），会影响老师编辑体验与 Epic 3 事件流设计，需单独小设计 |
| 2 | 「老师点採用」是否需要回写审计事件（`suggestion_adopted`） | **Epic 2 不做**，交由 Epic 3 用 diff 数据推断（③ 指标同理） | 若要求做 → 加 1 个 ack 接口 + 前端 1 次调用（约 40 行） |
| 3 | 阶段卡是否需要向老师展示阈值细节 | **展示**（`thresholds` + `blockers` 逐条），理由是「升级可解释 = 授权更可信」 | 若要求隐藏 → 只去掉前端展示，接口字段保留（后端不删字段） |
| 4 | 新老师是否需要「导入历史病例」以加速从观察期升到学习期 | **不做**（观察期按真实样本积累；升级需老师确认） | 若要求做 → 需历史数据导入与样本归因的口径设计（范围明显扩大，建议独立小 Epic） |
| 5 | `agent_stage_log` 是否本 Epic 就加哈希链（防篡改） | **不加**（Epic 3 的 `agent_learning_events` 才做哈希链；两表审计域不同） | 若要求做 → 全库仅 Epic 2 的表带链会形成「半个审计体系」，仍需 Epic 3 统一，建议维持现结论 |

### 7.3 风险与缓解

| 风险 | 等级 | 缓解 |
| :---- | :---- | :---- |
| `insert_draft` / `sign_draft` 的追加写引入回归 | 中 | 全部用「列存在探测 + 追加写」；不改签名与返回；`test_api.py` 全绿为硬门槛；改动点各配 1 条回归用例 |
| 相似度计算在病历过长时变慢 | 低 | 双侧截断 2000 字符 + 样本上限 50；只在 scan / 签字 / 手动触发；目标 < 200 ms |
| 阶段配置被误调（阈值调到极低即「放水升级」） | 中 | 校验 + 每次改动写 `config_changed` 日志 + 前端显示 `config_source` 角标 + 全局行只能运维改 |
| 存量老师看到「学习期」卡但指标样本不足 | 低 | `blockers` 明确显示「样本 2/5 份」，不出现「差一点升级」的诱导；`stale` 与 `approx_samples` 如实标注 |
| 前端误调越权接口导致老师困惑 | 低 | 403 + 繁体原因文案 + 审计联动阻断升级（§2.4） |
| 迁移在已有库上执行失败 | 低 | 幂等建表 / 探测补列（沿用 0002）；`run_upgrade()` 失败只打日志不阻塞启动（既有行为）；提供离线 SQL 预审 |
| 「AI 建议」被误当作诊断结论使用 | **中** | 铁律文案固定展示；候选必附 `disclaimer`；采用动作 = 老师本人在编辑框操作；升级必须老师确认 |

---

## 8. 施工顺序（每步可独立验证，完成后停下汇报）

| 步 | 内容 | 完成判据 |
| :---- | :---- | :---- |
| 1 | 迁移 0003 + `docs/migrations/0003_add_agent_stage.sql` | `pytest backend/test_migrations.py -q` 全绿；`run_upgrade()` 幂等；flag off 下既有测试全绿 |
| 2 | `database.py` 8 个新函数 + 3 处追加改 | 新函数单测通过；`test_api.py` 全绿（含 flag off 逐字节一致） |
| 3 | `agent_stage_service.py`（状态机 + 矩阵 + 配置 + ①②） | §6.1–§6.4 用例全绿（此时尚无新接口，纯服务层测试） |
| 4 | `agent_stage_api.py` + `models.py` + `main.py` 挂载 | §6.2 / §6.4 接口层用例全绿；404 / 403 / 400 / 409 各码有断言 |
| 5 | `agent.py` 末尾追加 3 组能力 | `test_prompts_unchanged` 通过（既有 prompt 哈希不变）；三个新能力各 1 条「解析失败不编造」用例 |
| 6 | `AgentStagePanel.tsx` + `App.tsx` 3 行 | flag off 时整卡不渲染；五阶段徽章与指标/阻塞原因正确显示；手工跑通「推荐 → ✅确认 → 生效」全链路 |
| 7 | 全量回归 | `pytest backend -q` 全绿（含 Epic 1 的 `test_templates.py`）；前端 `npm run build` 通过 |

---

## 9. 结论

- Epic 2 的全部内容（五阶段状态机、权限矩阵、一致率 ①②+③占位、代码盘点、Epic 1 兼容）已在本设计一次成文，**无「基准缺失」遗留项**。
- 三条铁律（永不诊断 / 永不开方 / 永不签字）在代码层有**唯一能力闸门 + 禁止 import 清单 + 守护测试 + 路由面不落库**四重保障，且不受任何 flag / 配置 / 阶段影响。
- 升级一律「系统举证 → 老师确认 → 生效」，降级一律即时；阈值与权重全部配置化，flag `AGENT_STAGE_ENABLED` 默认 off → **flag off 即零行为变化**。
- 待办：§7.2 五项请 CTO 一次审核（不阻塞开工）。审核通过后按 §8 顺序施工，**本文件不含代码改动**。














