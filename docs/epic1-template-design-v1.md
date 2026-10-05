# 知衡社区 · Epic 1「四类模板完整版」设计方案

版本：v0.1
日期：2026-09-28
范围：**仅第一部分**（Template 模型 + Alembic 迁移策略）。第二、三部分待输出后追加，本文件不改历史结论，只追加新章节。
对齐：白皮书 2.0 第三章；`docs/development-plan-v1.md` §3.3 D1、§5 Epic 1
状态：第一部分已获批复（见 §0.3），可据此进入实施准备。

---

## 0. 前提与基线

### 0.1 前置已确认事项（不再复议）

1. **鉴权**：沿用 `teacher_name` 与 `teacher_id` 一致校验，不引入登录体系。
2. **`lineage_id`**：Epic 1 阶段仅加列 `TEXT NOT NULL DEFAULT ''`，不建表、不加外键。
3. **前端**：允许新建独立组件，`App.tsx` 只做挂载。不引入 vitest，用 `tsc build` + `oxlint` + 手工自测。
4. **古字原则**：新建页 UI 与新模板骨架用繁体古字（炁 vs 氣 按语义区分），存量不动。
5. **参照对象**：现有「施治模板」已完成，是本 Epic 的兼容与参照对象。

### 0.2 事实核验（实测，本设计的前提）

| 事实 | 实测结果 |
| :---- | :---- |
| Python / SQLite | 3.12.10 / SQLite **3.49.1**（支持部分唯一索引、DDL 事务内回滚） |
| alembic / sqlalchemy | **均未安装**（`requirements.txt` 无此二项）→ 迁移必须先解决依赖问题 |
| 存量库表 | `backend/zhiheng.db` **无 `alembic_version` 表**，已有 30+ 张旧表 |
| 施治模板存量数据 | `plan_templates` 现有 **1 行**（`李老师`，content 长度 43）→ 回填逻辑有真实数据可验 |
| 建表 / 补列惯例 | `CREATE TABLE IF NOT EXISTS` + `ALTER TABLE ... ADD COLUMN` 包 `try/except OperationalError`（`database.py:113-116`、`142-144`、`325-328`） |
| 零外键、零 CHECK | 存量 24 张表全部无 FK、无 CHECK（`agent_tasks` 注释明确写「无 CHECK 约束，所以 status 可自由使用」，`database.py:255-256`） |
| 测试入口 | `conftest.py` 每用例删 `test.db` 后只调 `database.init_db()`，**不经过 alembic** |
| DB 路径 | `ZHIENG_DB` 环境变量决定（`database.py:5`） |
| 时间 / JSON 惯例 | 时间列一律 `TEXT`（ISO 字符串），JSON 一律 `TEXT` 存（`work_schedule`、`items_json`） |

### 0.3 第一部分批复记录（2026-09-28）

| # | 事项 | 批复结论 |
| :---- | :---- | :---- |
| 1 | 迁移运行接入点 | **同意** 在 `conftest.py`（及 `main.py`）增加 `run_upgrade()`；**失败不阻塞启动，仅打日志**（§6.2） |
| 2 | `active` 发布语义 | **同意「自动归档旧 active」**。新版本置 `active` + 旧版本置 `archived` **必须在同一事务内完成**，响应返回 `archived_ids`，**不得返回 409**（§3.2、§3.3） |
| 3 | `active` 不可原地改 | **同意**。编辑 `active` 模板直接 409，前端按钮文案改为「**基於此版本修訂**」，强制派生新版本（§3.3、§4.2） |
| 4 | 存量回填命名 | **同意** 统一命名「**施治模板（存量迁移）**」，并在 `schema_json.meta` 写入 `legacy_source='plan_templates'` 作为幂等标记（§5.2） |
| 5 | 依赖引入 | 随方案一并通过（alembic + sqlalchemy）；§6.1 的自建迁移表退路条款保留，作为风险声明 |
| 6 | 文档落盘 | 落盘 `docs/epic1-template-design-v1.md`，**只写第一部分**，后续部分输出后再追加 |

> 命名口径说明：「施治模板（存量迁移）」是迁移生成的数据值（非 UI 文案），沿用批复原文的简体写法；新建页 UI 文案与新模板骨架一律繁体古字。

---

## 1. Template 模型

### 1.1 表命名与落库位置

- 表名：`templates`（与 `plan_templates` 并存；`plan_templates` 保留为兼容镜像，见 §5）。
  - **2026-10-04 修正**：原文写「与 `plan_templates`、规划中的 `student_rank_record` 并存」——**`student_rank_record` 已作废**（段位概念整体废弃，决策 **D-002**；Epic 5 废除，**D-017**）。该表**从未创建**，也不应创建。段位已从白皮书 v2.1 删除（附录 B 第 7 条）。
- 存储：继续 SQLite，列类型全部用 `TEXT` / `INTEGER`，与存量表完全同构（便于 `sqlite3.Row` 直接 `dict()` 返回给前端）。
- **DDL 唯一真相源 = 迁移脚本**（见 §6）：`database.py::init_db()` 不再重复写一份 `CREATE TABLE templates`，避免两处 DDL 漂移；建表由 `main.py` / `conftest.py` 在 `init_db()` 之后调用迁移运行器补齐。

### 1.2 字段定义

| 列名 | 类型 | 约束 / 默认值 | 说明 |
| :---- | :---- | :---- | :---- |
| `id` | INTEGER | PRIMARY KEY AUTOINCREMENT | 与存量所有业务表一致 |
| `type` | TEXT | NOT NULL DEFAULT `''` | 四类模板枚举：`inquiry` / `record` / `treatment` / `prescription`（§2）。**不加 DB 级 CHECK**，理由见 §1.4 |
| `lineage_id` | TEXT | NOT NULL DEFAULT `''` | 前置确认②：Epic 1 全为 `''`，仅占位；Epic 4 起成为强制隔离键 |
| `teacher_id` | TEXT | NOT NULL DEFAULT `''` | 语义 = `teachers.name`。接口层同时收 `teacher_name` 与 `teacher_id`，**两者必须一致**，不一致直接 403（沿用现有鉴权口径）。**不建 FK**（存量惯例） |
| `name` | TEXT | NOT NULL DEFAULT `''` | 模板名（老师可改，繁体古字）。仅用于展示与检索，**不参与唯一性判断**（唯一性由 scope 决定，见 §1.3） |
| `schema_json` | TEXT | NOT NULL DEFAULT `'{}'` | 模板骨架（按 `type` 定契约，第二部分展开）。沿用「JSON 存 TEXT」惯例，与 `prescriptions.items_json`、`teacher_settings.work_schedule` 同构 |
| `version` | INTEGER | NOT NULL DEFAULT 1 | 版本号，链内严格递增（§4） |
| `parent_template_id` | INTEGER | NULL（无默认） | 自引用上一版 `templates.id`。**不建 FK**；根版本为 `NULL`（与存量「空值即无」语义一致） |
| `status` | TEXT | NOT NULL DEFAULT `'draft'` | `draft` / `active` / `archived`（§3）。**不加 DB 级 CHECK** |
| `created_at` | TEXT | NOT NULL DEFAULT `''` | ISO 时间字符串（`datetime.now().isoformat()`，与 `plan_templates.updated_at` 写法一致） |
| `updated_at` | TEXT | NOT NULL DEFAULT `''` | 同上；所有写操作（内容、状态、版本）都刷新 |

**明确不加的列（防范围蔓延）**：`deleted_at`（删除语义 = `archived`）、`created_by`（= `teacher_id`）、`is_default`（默认 = scope 内唯一 `active`）、`schema_hash`（Epic 3 哈希链再谈）、`description`（可用 `schema_json.meta.note` 承载）。

**明确要改的存量表（不属本部分，第二部分执行）**：生成草案时「记录 `template_id + version`」需要给 `drafts` 加列（沿用 `try/except OperationalError` 补列手法，老数据留 `0` / `''` = 未记录）；本部分只保证模板侧数据满足「任何历史快照可还原」（§4.4）。

### 1.3 索引与约束（共 3 个，全部在迁移里创建）

| 名称 | 类型 | 列 | 用途 |
| :---- | :---- | :---- | :---- |
| `uq_templates_active_one` | **部分唯一索引** | UNIQUE(`lineage_id`, `teacher_id`, `type`) WHERE `status = 'active'` | 硬保证「同一老师 + 同一师门 + 同一类型最多一条 `active`」→ 智能体取模板结果唯一确定，不依赖并发运气。SQLite 3.49.1 支持 |
| `idx_templates_scope` | 普通索引 | (`lineage_id`, `teacher_id`, `type`, `status`, `updated_at` DESC) | 主力读路径：老师端「按类型列模板 + 按更新时间倒序」一次索引命中；`lineage_id` 前置，Epic 4 加隔离过滤时无需换索引 |
| `idx_templates_lineage` | 普通索引 | (`parent_template_id`, `version` DESC) | 版本链查询（沿 `parent_template_id` 上溯 / 取链内最新版） |

**索引设计取舍说明**

- 不建 `UNIQUE(teacher_id, lineage_id, type, version)`：老师在 draft 阶段反复废弃草稿时会导致同版本号复用，硬唯一会把「丢弃草稿」变成写失败。版本唯一性由**服务层规则**（§4）+ `uq_templates_active_one` 共同保证。
- 不建 `name` 索引：模板量级为「一位老师 × 4 类 × 若干版本」（百量级），前端本地过滤即可，避免过度设计。
- 索引全部交由迁移创建，不在 `init_db()` 里补，保证只有一条 DDL 路径（存量库手建 `CREATE INDEX` 使用量为 0）。

### 1.4 「不加 CHECK / 不加 FK」的显式决策与代价

| 决策 | 理由（对齐存量） | 代价与兜底 |
| :---- | :---- | :---- |
| `type` / `status` 不加 CHECK | 存量全库无 CHECK，且 `agent_tasks` 注释明确以此换取取值自由；SQLite 改 CHECK 需整表重建，改一处枚举要一次高成本迁移 | Python 常量白名单 `TEMPLATE_TYPES` / `TEMPLATE_STATUSES` + 服务层校验（非法值 400）；前端常量与后端白名单一一对应（沿用 `PRESCRIPTION_ROLES` ↔ `HERB_ROLES` 的双端同步注释惯例，`database.py:1157-1160` / `App.tsx:105-109`） |
| `teacher_id` / `parent_template_id` 不加 FK | 存量 24 张表零 FK；且 SQLite 需 `PRAGMA foreign_keys=ON` 才生效，本库从未开启，加了形同虚设 | 服务层校验：`teacher_id` 存在于 `teachers`；`parent_template_id` 存在且**同 `teacher_id` / 同 `lineage_id` / 同 `type`**，否则 400；`lineage_id` Epic 1 不校验（恒为 `''`） |
| `status` 默认 `draft` | 新模板默认不可被智能体使用，符合「AI 永不擅自替代老师」的宪法原则 | 老师端列表默认按状态分组展示，`draft` 显著标注「未發佈」 |


---

## 2. `type` 枚举：四类模板

| 枚举值 | 显示名（繁体古字） | 语义 | 与现有代码的映射（兼容锚点） | `schema_json` 基线形状（第一部分只锁定外壳） |
| :---- | :---- | :---- | :---- | :---- |
| `inquiry` | 問診 | 老师问诊的提问顺序、必问项、追问触发条件；供「问诊偏好一致性」比对 | 现有「十问歌」学生端结构化输入、`complaints` 陈述链路 | `{"fields":[{"key","label","ask":"","required":bool,"order":int}],"meta":{}}` |
| `record` | 病歷 | 病历草案的段落骨架与措辞偏好（五段式） | `main.py::build_draft_template`（`main.py:71+`）的固定骨架、`agent.clean_transcript` / `generate_medical_draft`、`drafts.content`、`patient_records.ai_draft` | `{"sections":[{"key","title","hint","order":int}],"tone":{"style":"","forbidden":[]},"meta":{}}` |
| `treatment` | 施治 | 辨证施治方案的常用写法（老师习惯用语、医嘱口径） | **兼容重点**：`plan_templates`（表）/ `/api/plan_template`（`main.py:518-531`）/ `App.tsx::savePlanTemplate`「已套用模板，可修改」逻辑 → 首版由存量回填而来（§5） | `{"format":"text","content":"","meta":{"legacy_source":"plan_templates"}}` = 直接承载旧 `content` |
| `prescription` | 開方 | 开方偏好：常用药集合、默认君臣佐使、默认煎法、常用方剂组合 | 「九宫格开方」：`herb_inventory` + `/api/herbs`、`PRESCRIPTION_ROLES`、`PRESCRIPTION_COOKING_METHODS`、前端 `HERB_ROLES` / `COOKING_METHODS` / `DEFAULT_COOKING_METHOD` | `{"herbs":[{"herb_name","default_amount","role","cooking_method"}],"formulas":[{"name","composition":[]}],"meta":{}}` |

### 2.1 枚举的硬边界（写入本设计即为约束）

1. **AI 永不诊断、永不开方、永不签字**：`prescription` 模板只能生成「预填的药材清单（草稿态，老师确认后才落 `prescriptions`）」；`record` 模板只产出草案；`treatment` 模板只作套用文本。模板**不含**任何自动签发路径。
2. **四类共用一个 `templates` 表**，不建四张表：类型差异全部收敛在 `schema_json` 契约（第二部分给出四类字段级契约 + 校验函数清单）。
3. **枚举值只用英文小写下划线**（`inquiry` / `record` / `treatment` / `prescription`），落库与 API 层不出现中文；中文（繁体）只出现在显示名与 UI 文案层。
4. **`type` 一经创建不可修改**（改类型 = 新建模板），避免版本链语义混乱。

---

## 3. `status` 状态机：`draft` / `active` / `archived`

### 3.1 语义定义

| 状态 | 语义 | 能否被智能体使用 | 内容可否原地修改 | 可否物理删除 |
| :---- | :---- | :---- | :---- | :---- |
| `draft` | 草稿（未發佈） | 否 | 可（就地编辑，`PUT`） | 否（可弃用为 `archived`） |
| `active` | 生效中（老師發佈） | **是，且 scope 内唯一** | **否**（不可原地改；须派生新版本） | 否 |
| `archived` | 已歸檔（历史快照 / 被顶替） | 否 | **否**（只读） | **否**（只增不删，保历史可回溯） |

### 3.2 允许的转换（唯一合法边集）

| 边 | 触发动作 | 附加规则 |
| :---- | :---- | :---- |
| `draft → active` | 發佈 | ① 先按 `type` 校验 `schema_json` 必填键（非法 400）；② **同一 scope 若已有 `active`，必须在同一事务内先把它置 `archived`，再置本行为 `active`**（顺序不可颠倒，否则瞬时违反 `uq_templates_active_one`）；③ 响应返回 `archived_ids`，前端据此提示「舊版本已歸檔」。**此路径成功即返回 200，不返回 409**（批复 2） |
| `active → archived` | 歸檔 / 被新版本顶替 | 内容不变，仅刷新 `updated_at`；`archived` 行**永不删除** |
| `active → draft` | 撤回發佈（继续编辑） | 视为下线：该 scope 立即无 `active`，智能体回落内置骨架（§3.4）；内容可继续就地编辑 |
| `draft → archived` | 棄用草稿 | 仅刷新 `updated_at`，不删行 |
| `archived → active` | 重新啟用 | 若 scope 已有 `active`，按 `draft → active` 的②同一规则在同一事务内先归档它；**内容不可改**（要改先派生新版本） |
| 目标状态 == 当前状态 | 重复点击 / 重试 | **幂等 no-op**，返回 200 + `{"changed": false}`（前端重复点「發佈」不报错） |

### 3.3 禁止的转换（写单测）

| 禁止项 | 返回 | 说明 |
| :---- | :---- | :---- |
| 修改 `active` / `archived` 行的 `schema_json` / `name` / `type` | **409 `template_published_immutable`** | 已发布内容不可原地改（保「历史病历零回溯」的根因）；前端按钮文案改为「**基於此版本修訂**」，走 `POST /api/templates/{id}/derive` |
| `archived → draft`（原地复活） | 409 `template_archived_immutable` | 归档为终态语义；要改内容请派生新版本 |
| 同 scope 出现第二条 `active`（绕过发布接口的写入） | 409 `template_active_conflict`（DB 层 `uq_templates_active_one` 兜底） | 服务层先查再写；捕获 SQLite 唯一约束异常后翻译成 409，不暴露原始错误 |
| 跨 `teacher_id` / 跨 `type` / 跨 `lineage_id` 的状态变更 | 403 | `teacher_name != teacher_id`，或目标行 `teacher_id` 与请求者不一致 |
| 对非本人模板的任何读写 | 403 | 沿用「请求参数里 `teacher_name` 与 `teacher_id` 必须一致」的鉴权口径 |

> 注意：**「发布新版本」不是禁止项**，而是 §3.2 的自动归档路径（批复 2 明确：不报 409）。409 只用于「绕过发布接口的直接内容篡改」。

### 3.4 「无 `active` 模板」时的降级（不破坏存量行为）

- 智能体取模板：`WHERE status='active' AND type=? AND teacher_id=? AND lineage_id=?`，**取不到就直接走今天的既有路径**（`record` → `build_draft_template` / `agent.generate_medical_draft`；`treatment` → 旧 `plan_templates` 自动套用逻辑）。即：**本 Epic 上线当天，即使老师一条模板都没配，产品行为与今天完全一致**。
- 这是「feature flag 关闭即回到今天」（`development-plan-v1.md:192`）的具体落地方式：flag 关闭 = 新接口不可见 + 取模板恒返回空 → 全部走旧路径。

### 3.5 状态变更的留痕（Epic 1 最小集）

- 仅写行内 `updated_at`，**不建审计表**（审计属 Epic 3 `agent_learning_events`，避免提前建表）。
- 状态变更接口的响应预留事件形状（`event` / `template_id` / `version` / `from` / `to` / `archived_ids`），Epic 3 只需把它接进哈希链，无需改接口契约。


---

## 4. 版本管理：`parent_template_id` 与 `version` 递进逻辑

### 4.1 两个概念先分清

| 概念 | 载体 | 定义 |
| :---- | :---- | :---- |
| **版本链**（同一逻辑模板的谱系） | 沿 `parent_template_id` 逐级上溯 | Epic 1 **不引入** `chain_root_id`，只用 `parent_template_id` 单链表达（少一列、少一次迁移） |
| **版本号** `version` | 行内 `INTEGER` | 链内序号，从 1 起严格递增 |

### 4.2 递进规则

| 场景 | `version` | `parent_template_id` | `status` |
| :---- | :---- | :---- | :---- |
| 首次创建 | `1` | `NULL` | `draft` |
| draft 就地编辑（scope 内无 `active`） | 不变 | 不变 | 不变（仍 `draft`） |
| 基于 `active` 修订（老师点「基於此版本修訂」） | `max(parent.version + 1, 链内现有 max(version) + 1)` | `= parent.id`（**直接父，不跳链**） | `draft` |
| 基于 `archived` 派生 | 同上 | `= 该 archived 行 id` | `draft` |
| 发布 draft | 不变 | 不变 | `active`（同 scope 旧 `active` → `archived`，同事务，见 §3.2） |

**公式说明**：取 `max(parent.version + 1, 链内 max(version) + 1)` 而非单纯 `parent.version + 1`，是为了处理「同链存在已归档草稿占用了下一个版本号」的情况，保证链内 `version` 永不重复、永不回退（单调递增），前端「版本 v1 / v2 / v3」展示不会跳号或撞号。

### 4.3 派生接口的强校验（全部 400，写单测）

1. `parent_template_id` 必须存在；不存在 → `template_parent_not_found`。
2. `parent_template_id` 的 `teacher_id` / `lineage_id` / `type` **必须与请求一致** → 否则 `template_parent_scope_mismatch`（禁止跨老师、跨师门、跨类型挂链）。
3. 自引用（`parent_template_id == 自身 id`）→ `template_parent_self_reference`。
4. 同链已存在 `draft` 时，**复用该 draft 行**（不派生第二份草稿）：既避免草稿爆炸，也让「老师改了三次才发布」只产生 1 条线性的新版本（版本语义 = 已发布快照，而非每次按键）。
5. 不可派生指向**未来版本**的行（父版本号必须 ≤ 请求行的版本号）。

### 4.4 「历史病历零回溯」的三条硬保障

| 保障 | 机制 |
| :---- | :---- |
| ① 行不可变 | `active` / `archived` 行内容不可原地改（§3.3，409 + 派生）→ 任何 `(template_id, version)` 指向的内容是**冻结快照** |
| ② 行不可删 | 无删除接口；状态机不含删除边；`downgrade` 也不动存量模板数据（§6.4） |
| ③ 生成时记引用 | 草案生成时把 `template_id + version` 落到 `drafts`（第二部分执行，补列手法同 `visit_at`）；由于 ①②，仅凭这两个数字即可 100% 还原当时模板 |

验收对应：`development-plan-v1.md:191`「模板变更不回溯历史病历」→ 单测断言：发布 v2 后，引用 v1 的 `patient_records.final_plan` / `drafts.content` **逐字节不变**，且 `templates` 中 v1 行仍在且 `status='archived'`。

---

## 5. 与现有「施治模板」的兼容策略（存量零破坏）

### 5.1 存量事实（实测）

| 项 | 现状 |
| :---- | :---- |
| 表 | `plan_templates(id, teacher_name UNIQUE, content, updated_at)`（`database.py:291-298`） |
| 数据 | 1 行：`李老师`，`content` 43 字符 |
| 接口 | `GET/POST /api/plan_template`（`main.py:518-531`） |
| 前端 | 学生选中时自动套用 + 「已套用模板，可修改」标记 + 保存病历/预览时回写（`App.tsx:1545-1558`、`1691-1692`、`4100`） |

### 5.2 兼容八条（不破坏 = 不删表、不删数据、不改旧接口行为）

1. **`plan_templates` 完全不改**：不加列、不改类型、不删数据、不删表；Epic 1 结束它依然可读写。
2. **旧接口原样保留**：`GET/POST /api/plan_template` 请求/响应结构 100% 不变（老前端包继续可用）。
3. **回填（迁移内的一次性动作，幂等）**：`plan_templates` 中 `TRIM(content) <> ''` 的行 → `templates` 插一行：`type='treatment'`、`status='active'`、`version=1`、`parent_template_id=NULL`、`name='施治模板（存量迁移）'`（批复 4）、`schema_json={"format":"text","content":<旧 content>,"meta":{"legacy_source":"plan_templates"}}`、`lineage_id=''`、`teacher_id=teacher_name`、`created_at=updated_at=COALESCE(plan_templates.updated_at, 迁移时刻)`。
   - 幂等判定：回填前先查该 scope 是否已有 `legacy_source='plan_templates'` 的行；有则跳过（支持 `downgrade → upgrade` 重跑，不产生重复行）。
   - `content` 为空的行**不迁移**（与 `get_plan_template` 返回空串的现有语义一致：空 = 没有模板）。
4. **单向双写（legacy → new），永不反向**：仅当 feature flag 打开时，`save_plan_template()` 内部在同一事务里同步写 `templates`（同 scope 无 `draft` 则更新其 `schema_json.content`；若该 scope 的 `active` 来自存量回填，则**派生 v2** 而不原地改 `active`，遵守 §3.3）。
   - 反向不写（新接口永不回写 `plan_templates`）→ 避免双向漂移。
   - 未发布就被 `active` 语义挡住的情况（老师直接在旧链路上改文案）→ 按「派生 v2 草稿」处理，并在响应里带 `derived_template_id`；前端旧逻辑对此字段无感（不解析即不影响）。
5. **feature flag `TEMPLATE_API_ENABLED`（默认 `off`，分两批放量）**：
   - `off`：`/api/templates*` 全部 404（或 503），老师端不渲染配置入口，全部走旧路径 → **今天行为 1:1**。
   - `on`：新接口启用；旧接口仍是「遗留写入通道」（双写）。
6. **`plan_templates` 的定位降级声明**：自本 Epic 起它是「兼容镜像」，Epic 2 起新代码只读、只由旧接口维护；**Epic 1 内不做删除**，等新配置页稳定 1 个迭代后再议（不在本 Epic 范围）。
7. **存量无破坏清单（回归即红线）**：不得触碰 `plan_templates` 数据、`drafts`、`patient_records`、`prescriptions.items_json` 结构（含 `role` / `cooking_method`）、`App.tsx` 旧套用逻辑、`seed_test_data.py`；`test_api.py` 现有全部用例必须保持全绿（当前含 `test_local_prescription_deducts_stock` / `test_remote_prescription_does_not_deduct` 等）。
8. **新增守护测试（第一部分即可落）**：
   - `test_migration_backfills_plan_template`：迁移后 `plan_templates` 行数与内容不变，且 `templates` 多出对应 `active` 行；
   - `test_templates_table_does_not_affect_legacy_api`：新表存在时旧 `GET/POST /api/plan_template` 响应结构不变；
   - `test_template_archive_does_not_touch_history`：归档 / 新版发布后历史 `patient_records.final_plan` 不变。


---

## 6. Alembic 迁移策略

### 6.1 前置决策：依赖与「不用 ORM」原则

- `alembic` **强依赖 SQLAlchemy**，二者当前都未安装（实测 `find_spec('alembic') → False`）。因此需在 `requirements.txt` 追加 `alembic` 与 `sqlalchemy`（建议 Alembic 1.16.x + SQLAlchemy 2.0.x，锁版本，与本项目 FastAPI 0.141.1 / pydantic 2.13.5 无冲突）。
- **不引入 ORM 模型**：本项目真源是 `database.py` 的裸 `sqlite3` SQL，若再写一份 SQLAlchemy `Table` 元数据就会变成第三份 DDL。因此：
  - **禁用 `--autogenerate`**（无 `target_metadata`），所有 revision 手写、走评审；
  - 迁移体内统一用 `op.execute(<原始 SQL>)` + `op.create_table` / `op.create_index` / `op.drop_table` / `op.drop_index` 的最小面，风格贴近 `database.py`；
  - 这样 `database.py` 仍是运行时读写入口，Alembic 只承担「版本化 DDL / 数据搬运」。
- **env.py 关键设置**：`script_location = alembic`；`sqlalchemy.url` 由 env.py 从 `ZHIENG_DB` 拼绝对路径覆盖（不依赖 `alembic.ini` 里的相对路径，否则从不同 cwd 调用 `alembic` 会连错库）；`render_as_batch=True`（为后续 SQLite 补列 / 改列预留）；`version_table='alembic_version'` 显式声明；`file_template` 用顺序号前缀（`0001_create_templates`）便于人读；env.py **不 import `database`、不调 `init_db()`**（避免隐式副作用）。
- **回退路（风险声明，批复 5）**：若评审不接受新增 SQLAlchemy 依赖，则自建 `schema_migrations(version TEXT PRIMARY KEY, applied_at TEXT)` 表 + `backend/migrations/NNNN_*.py` 脚本按序执行。本设计按执行计划 §4.2「引入 Alembic」执行，两者 revision 编号与操作步骤语义完全一致，切换成本仅限运行器。

### 6.2 迁移运行接入点（三处，保证「测试 / 本地 / 生产」同一条路径）

| 接入点 | 改动 | 说明 |
| :---- | :---- | :---- |
| `backend/migrations_runner.py`（新增） | 提供 `run_upgrade()`：用 Alembic 编程式 API（`Config` + `command.upgrade(cfg, "head")`）执行到 head | 供 `main.py` 与 `conftest.py` 复用，避免两处拼命令 |
| `backend/main.py` | `database.init_db()` 之后加 `migrations_runner.run_upgrade()`，包 `try/except` 只 `print("[warn] …")` 不抛出 | 单机本地 SQLite 项目，启动即自愈；迁移失败**不阻塞**旧链路启动（与 `database.py:248-251` 现有「兼容升级失败也不能挡住启动」手法一致） |
| `backend/conftest.py` | `database.init_db()` 之后调 `run_upgrade()`（`ZHIENG_DB=test.db` 已在文件顶部设置） | 保证 pytest 每用例重建 `test.db` 后 `templates` 表存在；也让「自动 upgrade」路径本身被测试覆盖（批复 1：失败不阻塞、仅打日志） |

生产 / 手工路径同时保留：`cd backend; ..\venv\Scripts\alembic.exe upgrade head`（PowerShell 下若要用测试库：`$env:ZHIENG_DB='test.db'; alembic upgrade head`）。

### 6.3 Revision `0001_create_templates` 的 `upgrade` 操作步骤

> `down_revision = None`；`revision = "0001_create_templates"`。全步骤设计为**可重跑**（每步先探测再执行）。

1. **探测**（`sqlalchemy.inspect(conn)`）
   - 1.1 读 `sqlite_master`：`templates` 表是否已存在（覆盖「某 dev 库手建过」的脏状态）→ 已存在则跳过步骤 2；
   - 1.2 读 `alembic_version` 当前值（Alembic 自动管理，仅用于日志打印「本次从 X 升到 0001」）。
2. **建表 `op.create_table('templates', …)`**：按 §1.2 表格逐列声明，`server_default` 与默认值一致（`''` / `'{}'` / `1` / `'draft'`），主键 `id INTEGER PRIMARY KEY AUTOINCREMENT`；**不声明任何 ForeignKey / CheckConstraint**。
3. **建索引（顺序：先唯一后普通；索引名与 §1.3 一致）**
   - 3.1 `op.create_index('uq_templates_active_one', 'templates', ['lineage_id','teacher_id','type'], unique=True, sqlite_where=<status='active'>)`；
   - 3.2 `op.create_index('idx_templates_scope', 'templates', ['lineage_id','teacher_id','type','status','updated_at'], …)`（`updated_at` 以 DESC 声明）；
   - 3.3 `op.create_index('idx_templates_lineage', 'templates', ['parent_template_id','version'], …)`；
   - 每个 `create_index` 前先 `PRAGMA index_list('templates')` 探测，已存在则跳过。
4. **存量回填**：`op.execute` 一条 `INSERT INTO templates (...) SELECT ... FROM plan_templates WHERE TRIM(COALESCE(content,'')) <> '' AND NOT EXISTS (同 scope 已有 legacy 行)`。
   - 关键点：**只 INSERT 到 `templates`**，对 `plan_templates` 零写操作 → `downgrade` 天然无损；
   - `created_at` / `updated_at` 取 `COALESCE(plan_templates.updated_at, <迁移时刻 ISO>)`；
   - 用 `NOT EXISTS` 保证可重跑不重复（配合 §5.2 第 3 条的幂等标记 `schema_json.meta.legacy_source`）。
5. **不触碰任何存量表**（不 ALTER、不改 `drafts` / `patient_records` / `prescriptions`）——本 revision 的「写入面」仅 `templates` + `alembic_version` 两张新表。
6. **收尾校验（迁移内 assert，失败即抛异常整体回滚）**：`SELECT COUNT(*) FROM templates WHERE type='treatment' AND status='active'` 等于回填前的有效 `plan_templates` 行数。
7. **事务性说明**：SQLite 3.49 支持 DDL 事务，配合 SQLAlchemy 连接，步骤 2–4 在同一事务内；若中途失败则 `templates` 与索引一并回滚，不会留下半张表。**回填必须放在建表与索引之后**（否则索引缺失期若有并发写入会漏约束）。

### 6.4 同 revision 的 `downgrade` 操作步骤（可回退 + 防误删）

1. **前置安全闸**：`SELECT COUNT(*) FROM templates`；若大于「回填行数」（即老师已新建过模板）→ **抛异常中止 downgrade**，错误信息提示「请先用 `GET /api/templates` 导出 JSON 备份，或改用 feature flag 回退」。理由：满足 `development-plan-v1.md:316`「Alembic 可回退，旧数据备份」的风险应对，不让降级悄悄吃掉老师配好的模板。
2. **`op.drop_index('idx_templates_lineage')`**（先普通后唯一）。
3. **`op.drop_index('idx_templates_scope')`**。
4. **`op.drop_index('uq_templates_active_one')`**（部分唯一索引同样走 `drop_index`，无需特殊处理）。
5. **`op.drop_table('templates')`**：回填产生的行随表消失；**`plan_templates` 原表与原数据毫发无损**（因为 upgrade 从未写它）。
6. **不动 `alembic_version`**（Alembic 自动把版本回退到 base，即删除版本行、保留空表）。若需彻底移除迁移框架痕迹：额外运维步骤 `DROP TABLE alembic_version`，**默认不执行**（保留它才能再 `upgrade head`）。
7. 每步 `drop_*` 前同样先探测存在性，保证 downgrade 可重跑。


### 6.5 三类库的执行步骤（照抄即可的操作手册）

| 库 | 步骤 |
| :---- | :---- |
| **A. 全新库**（无 `zhiheng.db`） | ① 备份（无数据，可跳）→ ② `python main.py` 启动：`init_db()` 建存量表 → `run_upgrade()` 建 `templates`；或手工 `cd backend; alembic upgrade head` |
| **B. 存量生产库**（本机 `backend/zhiheng.db`，实测无 `alembic_version`，含 1 行 `plan_templates`） | ① 备份：`Copy-Item backend\zhiheng.db backend\backups\zhiheng_<日期>.db`（先建 backups 目录，且 `backups/` 需进 `.gitignore`）→ ② 预审 SQL：`alembic upgrade head --sql > docs\migrations\0001.sql` 人工过一遍（**不动数据库**）→ ③ 正式升级：`cd backend; alembic upgrade head`（或启动服务自动升级）→ ④ 校验（§6.6）→ ⑤ 比对 `plan_templates` 行数与 content 未变 |
| **C. 已升级库** | 重复 `alembic upgrade head` 为 no-op（`alembic current` 输出 `0001_create_templates (head)`）；日常新迁移只追加 `0002+` |

> 注：库 B **不需要** baseline / `alembic stamp`，因为 `0001` 只做「建新表 + 建新索引 + 新表回填」，与存量 30+ 张旧表零交集，不依赖任何「基线快照」。

### 6.6 升级后校验清单（可执行命令）

| # | 校验 | 命令 / 断言 |
| :---- | :---- | :---- |
| 1 | 版本表就位 | `alembic current` → `0001_create_templates (head)`；`alembic history` 可见该 revision |
| 2 | 表与索引 | `PRAGMA index_list('templates')` 含 3 个索引；`SELECT sql FROM sqlite_master WHERE name='uq_templates_active_one'` 含 `WHERE status = 'active'` |
| 3 | 回填一致 | `SELECT COUNT(*) FROM templates WHERE type='treatment' AND status='active'` == `SELECT COUNT(*) FROM plan_templates WHERE TRIM(COALESCE(content,'')) <> ''`（本机当前预期 = 1） |
| 4 | 存量未动 | `SELECT teacher_name, length(content), updated_at FROM plan_templates` 与升级前逐行一致 |
| 5 | 约束生效 | 手工插第二条 `active` 同 scope → 报唯一约束（说明部分索引真的生效），随后删除该测试行 |
| 6 | 双向演练 | `alembic downgrade base` → 确认 `templates` 消失、`plan_templates` 仍在 → `alembic upgrade head` 再次成功且回填行数不变（幂等验证） |
| 7 | 回归 | `cd backend; ..\venv\Scripts\python.exe -m pytest` → 现有全绿 + §5.2 第 8 条新增 3 个用例通过 |
| 8 | 前端 | `cd frontend; npm run build`（`tsc` 通过）+ `npm run lint`（oxlint）通过 —— 本部分不改前端，此条为后续部分的固定入口 |

### 6.7 迁移纪律（写进 PR 模板 / 评审清单）

1. 一次 schema 变更 = 一个 revision，`0001 → 0002 → …` 顺序递增，禁用 autogenerate、禁用「顺手合并两个改动」。
2. 每个 revision 必须自带可重跑的 `upgrade` 与「有安全闸」的 `downgrade`。
3. 每个 revision 的评论头写明：对齐白皮文章节、回退方案、涉及存量表清单（本 revision：仅新增，不涉存量）。
4. `backend/backups/` 进 `.gitignore`（迁移前备份的落点）。

---

## 7. 本部分风险与对策

| 风险 | 触发条件 | 对策 |
| :---- | :---- | :---- |
| 新增 SQLAlchemy 依赖被否 | 评审认为体积 / 约束不可接受 | §6.1 末条退路（自建 `schema_migrations` + 版本化 SQL）；两者 revision 编号与步骤语义完全一致，切换成本仅限运行器 |
| 部分唯一索引不被支持 | SQLite < 3.8 | 已实测 3.49.1；迁移内加 `sqlite_version` 断言，低于 3.8 直接报错中止（不静默降级成普通索引） |
| `templates` DDL 双写漂移 | 有人在 `init_db()` 里又 `CREATE TABLE` | 设计层面禁止（§1.1 / §6.1）；加守护测试断言 `sqlite_master` 中 `templates` 的定义与迁移生成的一致 |
| 双写导致新旧数据漂移 | legacy 接口与新版配置页并发写同一 scope | 双写仅 legacy → new 单向；新版配置页写 `active` 走「不可原地改 + 派生 v2」，天然不与旧链路的「覆盖同一行 content」冲突；Epic 1 内加 `test_legacy_write_does_not_mutate_active_content` |
| downgrade 吃掉老师新配的模板 | 老师已在 flag 打开期建了模板后回退 | §6.4 第 1 条安全闸（先导出再降级） |
| 自动升级失败悄悄上线 | `run_upgrade()` 失败仅打日志 | 失败时 `/api/templates*` 返回 503 + 明确文案「模板表未就绪」；旧链路不受影响（这就是选择「不阻塞启动」的代价） |

---

## 8. 后续部分（本文件待追加章节）

- **第二部分：接口契约 + 前端结构** —— 四类 `schema_json` 字段级契约；模板 CRUD 接口（路径 / 方法 / 请求 / 响应）；状态机接口（发布、归档、派生）；草案生成接入 `template_id + version` 的接口改动；老师端模板配置页组件结构与交互流转（繁体古字文案）；测试清单（前端手工自测 + 后端单测）。
- **第三部分（如需）：实施顺序与验收** —— 按子任务拆分的提交节奏、回归矩阵、上线与回退操作单。

---

第一部分 完。

---

# Epic 1 设计方案 · 第二部分：接口契约 + 前端结构

版本：v0.1（第二部分）
承接：第一部分（本文件 §1–§8）；本部分所有接口/字段命名与第一部分一致。
已落实的批复：① `run_upgrade()` 接入（§6.2）；② 发布 = 同事务自动归档旧 `active` + 返回 `archived_ids`（不报 409）；③ `active` 不可原地改，409 + 「基於此版本修訂」；④ 回填名「施治模板（存量迁移）」+ `legacy_source='plan_templates'`。

---

## 9. 四类 `schema_json` 字段级契约

### 9.0 通用约定（四类共用）

| 项 | 约定 |
| :---- | :---- |
| 序列化 | `json.dumps(obj, ensure_ascii=False)` 存 `TEXT`（沿用 `database.py` 现有惯例：`teacher_settings` 的 `work_schedule` / `prescriptions.items_json`） |
| 外层结构 | 一律含 `version`（契约版本，Epic 1 恒为 `1`）、`meta`（自由对象，不参与校验）、以及一个类型专属的主键数组 |
| 未知键 | **忽略且原样保留**（前向兼容：Epic 2/3 新增字段时旧代码不报错） |
| 未知 `schema_json.version` | 大于当前支持版本 → 允许保存，但生成时**降级为不用模板**并记日志（不报错、不影响出稿） |
| 校验入口 | `database.py` 新增常量 `TEMPLATE_TYPES` / `TEMPLATE_STATUSES` 与 `validate_template_schema(type, schema_obj)` → 返回 `(ok, errors)`；`errors` 为 `[{path, msg}]`（`path` 用 JS 风格，如 `fields[2].label`） |
| 校验时机 | `POST /api/templates`（创建）、`PUT /api/templates/{id}`（改草稿）→ **格式校验**；`publish` → **发布级校验**（草稿允许半成品，发布必须完整） |
| `meta` 保留键 | `meta.legacy_source`（存量迁移标记）、`meta.note`（老师备注）、`meta.updated_hint`（前端未保存提示用，可清空） |
| 中文文案 | `label` / `title` / `hint` / `ask` 一律繁体古字；**炁 / 氣 按语义区分**，禁止全局简繁替换（例：`先天之炁`、`後天之氣`、`調理氣機`） |
| 长度上限 | 单个字符串 ≤ 2000 字；`schema_json` 序列化后 ≤ 64 KB（超限 400 `schema_too_large`，防前端误塞大文本） |

---

### 9.1 `inquiry`（問診）

外层：`{"version":1,"fields":[…],"meta":{}}`

| 字段 | 类型 | 必填 | 默认 | 约束 | 语义 |
| :---- | :---- | :---- | :---- | :---- | :---- |
| `fields[].key` | string | 是 | — | `^[a-z][a-z0-9_]{0,31}$`，同模板内唯一 | 机器键（**建议沿用十问歌英文键**，见下表） |
| `fields[].label` | string | 是 | — | 1–16 字，繁体 | 显示名（`寒熱` / `汗` / `頭身`…） |
| `fields[].ask` | string | 否 | `''` | ≤ 120 字 | 老师口径的问法（覆盖默认问法） |
| `fields[].order` | int | 是 | — | ≥ 1，同模板内唯一 | 提问顺序 |
| `fields[].required` | bool | 否 | `false` | — | 是否必问（未答不允许「已問全」） |
| `fields[].answer_type` | string | 否 | `text` | `text` / `number` / `choice` | 学生端作答控件类型 |
| `fields[].choices` | string[] | 条件 | `[]` | `answer_type='choice'` 时必填，2–12 项、去重 | 选项 |
| `fields[].follow_up` | string | 否 | `''` | ≤ 120 字 | 追问触发条件（自然语言描述，Epic 1 只存不执行） |

**数量约束**：`3 ≤ len(fields) ≤ 20`；发布时至少 1 条 `required=true`。

**默认骨架（新建时预填，来自 `agent.TEN_QUESTIONS`，`agent.py:303-314`，顺序不可变）**

| `key` | `label` | 默认 `ask`（可改为老师口径） |
| :---- | :---- | :---- |
| `cold_heat` | 寒熱 | 你最近是怕冷多一點，還是怕熱多一點？ |
| `sweat` | 汗 | 平時出汗多不多？是白天易汗，還是睡著了出汗？ |
| `head_body` | 頭身 | 頭或身體有哪裏不舒服？頭暈、頭痛、身重痠沉？ |
| `urine_stool` | 二便 | 大小便如何？有無乾結、稀軟、次數變多？ |
| `diet` | 飲食 | 近來胃口與口味如何？吃東西香不香？ |
| `chest_abdomen` | 胸腹 | 胸口或腹部有無發悶、發脹、隱隱作痛？ |
| `ear` | 耳 | 耳朵有沒有響，或聽東西不太清楚？ |
| `thirst` | 口渴 | 會覺得口渴嗎？想喝熱水還是涼水？ |
| `old_illness` | 舊病 | 以前得過什麼病？有無長期服藥？ |
| `cause` | 病因 | 這次不適大約從何時起？你覺得與什麼有關？ |

**与现有链路**：`agent.TEN_QUESTIONS` 常量**不动**（存量原则）；模板存在且 flag 打开时，Epic 2 的追问链路改读模板（Epic 1 只做「配置 + 存储 + 读接口」，不接管生成，见 §12 的口径与 §15 待确认 4）。

### 9.2 `record`（病歷）

外层：`{"version":1,"sections":[…],"tone":{…},"meta":{}}`

| 字段 | 类型 | 必填 | 默认 | 约束 | 语义 |
| :---- | :---- | :---- | :---- | :---- | :---- |
| `sections[].key` | string | 是 | — | 同上正则，唯一 | 机器键 |
| `sections[].title` | string | 是 | — | 1–20 字，繁体 | 段落标题（如 `主訴（學生原話）`） |
| `sections[].hint` | string | 否 | `''` | ≤ 120 字 | 给智能体的填充提示（缺失留空，禁止编造） |
| `sections[].order` | int | 是 | — | ≥ 1，唯一 | 段落顺序 |
| `sections[].required` | bool | 否 | `false` | — | 必须出现的段 |
| `sections[].writable_by` | string | 否 | `ai` | `ai`（可填）/ `teacher`（仅老师填，留空） | 硬约束：`teacher` 段**智能体永不留内容**，只留 `标题：` |
| `tone.style` | string | 否 | `''` | ≤ 120 字 | 措辞偏好（口语 / 文言） |
| `tone.forbidden` | string[] | 否 | `[]` | ≤ 20 项 | 禁止替换/删除的词（默认含中医术语铁律） |

**数量约束**：`2 ≤ len(sections) ≤ 12`；发布时至少 1 条 `writable_by='teacher'`（保证「待老师补充」语义不被抹掉）。

**默认骨架（对齐 `agent.DOCTOR_PROMPT` 输出模板 `agent.py:89-101` 与 `main.build_draft_template` `main.py:72-89`）**

| `key` | `title` | `order` | `writable_by` | 备注 |
| :---- | :---- | :---- | :---- | :---- |
| `chief_complaint` | 主訴（學生原話） | 1 | `ai` | 学生原话，禁止改写（`agent.py` 铁律） |
| `past_records` | 既往病歷參考 | 2 | `ai` | 取该学生同老师的历史 `final_plan` 摘要 |
| `tongue` | 舌象 | 3 | `teacher` | 智能体只留空 |
| `pulse` | 脈象 | 4 | `teacher` | 智能体只留空 |
| `pattern` | 辨證 | 5 | `teacher` | **AI 永不辨证**（宪法硬约束） |
| `treatment_plan` | 施治方案 | 6 | `teacher` | 由 `treatment` 模板套用后由老师确认 |

`tone.forbidden` 默认值 = 术语铁律词表：`脈象` / `舌象` / `主訴` / `現病史` / `伴隨症狀` / `辨證`（对应 `agent.py:189-192` 的「原文保留、不许换近义词」）。

**无模板时的黄金断言**：生成结果必须与今天 `build_draft_template` 的输出**逐字节一致**（回归测试写死）。

---

### 9.3 `treatment`（施治）

外层：`{"version":1,"format":"text","content":"","placeholders":[],"meta":{}}`

| 字段 | 类型 | 必填 | 默认 | 约束 | 语义 |
| :---- | :---- | :---- | :---- | :---- | :---- |
| `format` | string | 否 | `text` | Epic 1 仅 `text`（预留 `blocks`） | 内容形态 |
| `content` | string | 是 | `''` | ≤ 2000 字；**发布时 `trim()` 非空** | 施治方案模板正文（= 旧 `plan_templates.content`） |
| `placeholders` | string[] | 否 | `[]` | ≤ 8 项，每项 ≤ 60 字 | 生成时提醒老师补的空位（Epic 1 只存不执行） |
| `meta.legacy_source` | string | 否 | — | 仅迁移写入 `plan_templates` | 回填幂等标记（第一部分 §5.2(3)） |

**与现有链路映射（逐字段）**

| 旧通道 | 新契约 | 关系 |
| :---- | :---- | :---- |
| `plan_templates.content`（`database.py:291-298`） | `schema_json.content` | 回填时 1:1 复制，永不反向写 |
| `GET /api/plan_template`（`main.py:522-525`） | `GET /api/templates/active?type=treatment` | 新旧并存；前端 flag on 时优先新接口，旧接口做兜底 |
| `POST /api/plan_template`（`main.py:527-531`） | `POST/PUT /api/templates*` | 旧通道保留为「遗留写入通道」（单向双写，见 §12.4） |
| 前端「已套用模板，可修改」提示（`App.tsx:4100`） | 不变 | 显示文案不动（存量 UI 不动），仅数据来源切换 |

---

### 9.4 `prescription`（開方）

外层：`{"version":1,"herbs":[…],"formulas":[…],"defaults":{…},"meta":{}}`

| 字段 | 类型 | 必填 | 默认 | 约束 | 语义 |
| :---- | :---- | :---- | :---- | :---- | :---- |
| `herbs[].herb_name` | string | 是 | — | 1–20 字，同模板内唯一 | 药材名（与 `herb_inventory.herb_name` 同名） |
| `herbs[].default_amount` | number | 否 | `0` | `0` 或 `(0,1000]`；`0` = 未预填 | 预填克数 |
| `herbs[].role` | string | 否 | `''` | 白名单 `PRESCRIPTION_ROLES` = 君臣佐使（`database.py:1159`） | 默认君臣佐使 |
| `herbs[].cooking_method` | string | 否 | `常规` | 白名单 `PRESCRIPTION_COOKING_METHODS`（`database.py:1160`） | 默认煎法 |
| `herbs[].order` | int | 否 | 数组下标+1 | 唯一 | 九宫格预选顺序 |
| `formulas[]` | object[] | 否 | `[]` | ≤ 10；`{name(≤20字), composition:[{herb_name, amount, role, cooking_method}]≤20}` | 常用方剂组合（见 §15 待确认 3） |
| `defaults.cooking_method` | string | 否 | `常规` | 同上白名单 | 新选药材的默认煎法 |
| `defaults.remote` | bool | 否 | `false` | — | 是否默认勾「遠程診療（學生自採，不扣庫存）」 |

**数量约束**：`len(herbs) ≤ 40`。

**校验的两级策略（不阻断老师）**

| 情形 | 处理 |
| :---- | :---- |
| `role` / `cooking_method` 不在白名单 | 400 `schema_invalid`（沿用 `clean_prescription_role` 的清洗语义，但**模板侧直接拒**，避免悄悄变成 `''` 让老师误解） |
| `herb_name` 不在该老师 `herb_inventory` 中 | **200 通过 + `warnings: [{code:'herb_not_in_inventory', herb_name}]`**，前端黄字提示「未入庫，開方時將無法扣減庫存」；理由：老师可能先配模板、后补库存（`herb_inventory` 有 `UNIQUE(teacher_name, herb_name)`，`database.py:1045`） |

**硬边界（对齐宪法与存量）**：模板只产出「**九宫格预选 + 预填分量**」；`prescriptions` 落库仍必须老师点「保存藥方」（`handleSavePrescription`），**AI 永不自动开方、永不自动发送**。

---

## 10. 模板 CRUD 接口定义

### 10.1 公共约定

| 项 | 约定 |
| :---- | :---- |
| 前缀 | `/api/templates`（新命名空间，与旧 `/api/plan_template` 并存） |
| 鉴权 | 每个接口都必须带 `teacher_name` 与 `teacher_id`（GET 走 query，POST/PUT 走 body），**两者不等 → 403 `teacher_mismatch`**；只允许操作 `teacher_id` 自己的行 |
| `lineage_id` | Epic 1 一律 `''`；请求若传非空值 → 400 `lineage_not_supported`（防止前端提前误用留白字段） |
| 成功响应 | 200/201 + `{"template": {…}}` 或 `{"templates": […]}`（`schema_json` 返回**解析后的对象**，不给前端 JSON 字符串） |
| 错误响应 | 真实 HTTP 状态码；body 沿用 FastAPI 的 `HTTPException(detail=…)` 包装：`{"detail": {"error": "<code>", "msg": "<繁中說明>", "errors":[…],"warnings":[…]}}`（前端读 `res.detail.error`） |
| flag/就绪 | `TEMPLATE_API_ENABLED=off` → 全部 **404 `templates_disabled`**；`templates` 表缺失（迁移未跑）→ **503 `template_store_unavailable`**（第一部分 §7） |
| 不做的事 | **不提供 DELETE**；不提供改 `type` / `teacher_id` / `lineage_id` / `parent_template_id` / `version` 的通用 PUT |

**模板对象（所有模板类响应共用）**

| 键 | 类型 | 说明 |
| :---- | :---- | :---- |
| `id` / `type` / `teacher_id` / `lineage_id` | — | 直出 |
| `name` | string | 模板名 |
| `schema_json` | object | 解析后的骨架对象 |
| `version` / `parent_template_id` | int / int\|null | 版本信息 |
| `status` | string | `draft` / `active` / `archived` |
| `created_at` / `updated_at` | string | ISO |
| `is_legacy` | bool | 是否存量回填而来（`meta.legacy_source == 'plan_templates'`），前端用于显示「存量遷移」标签 |

### 10.2 接口清单

| # | 方法 | 路径 | 请求 | 成功响应 | 主要错误 |
| :---- | :---- | :---- | :---- | :---- | :---- |
| 1 | GET | `/api/templates` | query：`teacher_name`、`teacher_id`、`type?`（缺省=四类全返）、`status?`（缺省=全部）、`include_schema?`（默认 `1`；列表页可传 `0` 省流量） | `{"templates":[…], "counts":{"inquiry":3,…}}`，排序：`type asc, version desc` | 403 / 400 `invalid_type` |
| 2 | GET | `/api/templates/{id}` | query：`teacher_name`、`teacher_id` | `{"template":{…}, "chain":[{"id","version","status","updated_at"}], "generated_count": <引用该 link 的草案数（可选，Epic3 细化）>}` | 404 `template_not_found` / 403 |
| 3 | GET | `/api/templates/active` | query：`teacher_name`、`teacher_id`、**`type`（必填）** | `{"template": {…}\|null}`（`null` = 无生效模板 → 生成侧走旧路径） | 403 / 400 |
| 4 | POST | `/api/templates` | body：`teacher_name`、`teacher_id`、`type`、`name?`（缺省 = 该类型显示名，如 `施治`）、`schema_json?`（缺省 = 该类型默认骨架） | **201** `{"template":{…}, "reused": false}`；若同 scope 已有 `draft` → **200** `{"template":<既有草稿>, "reused": true}`（幂等，不产生第二份草稿） | 400 `invalid_type` / `schema_invalid` / `schema_too_large` |
| 5 | PUT | `/api/templates/{id}` | body：`teacher_name`、`teacher_id`、`name?`、`schema_json?`（**只能改这些**） | 200 `{"template":{…}}` | **409 `template_published_immutable`**（`status != 'draft'`，批复 3）/ 400 `schema_invalid` |
| 6 | POST | `/api/templates/{id}/publish` | body：`teacher_name`、`teacher_id` | 200 `{"template":{…}, "archived_ids":[…], "changed": true, "event":"template_configured"}` | 400 `schema_invalid`（发布级校验）/ 409 `template_active_conflict`（并发兜底） |
| 7 | POST | `/api/templates/{id}/archive` | body：`teacher_name`、`teacher_id` | 200 `{"template":{…}, "changed": <bool>}` | 403 / 404 |
| 8 | POST | `/api/templates/{id}/activate` | body：`teacher_name`、`teacher_id` | 200 `{"template":{…}, "archived_ids":[…], "changed": <bool>}` | 409 `template_active_conflict` |
| 9 | POST | `/api/templates/{id}/derive` | body：`teacher_name`、`teacher_id`、`name?` | **201** `{"template":<新草稿>, "reused_draft": false}`；同链已有 `draft` → 200 + `reused_draft: true`（复用） | 400 `template_parent_*`（§4.3 五条）/ 403 |
| 10 | GET | `/api/plan_template` | 不变（存量） | 不变 | 不变 |
| 11 | POST | `/api/plan_template` | 不变（存量） | 不变（flag on 时附 `derived_template_id?`，前端不解析也不影响） | 不变 |

**示例（`POST /api/templates/{id}/publish` 响应，展示批复 2 的返回形状）**

| 键 | 值示例 |
| :---- | :---- |
| `template.id` / `version` / `status` | `12` / `2` / `"active"` |
| `archived_ids` | `[7]`（同 scope 被顶替的旧 `active`，同事务归档；前端据此提示「舊版本 v1 已歸檔」） |
| `event` | `"template_configured"`（Epic 3 哈希链接口预留，§3.5） |
| `changed` | `true`（重复点发布 → `false`，200 幂等） |

---

## 11. 状态机接口（发布 / 归档 / 派生）

### 11.1 `publish`（草稿 → 生效，同事务自动归档旧 active）

**前置**：`status='draft'`；`teacher_name == teacher_id`；行属本人；发布级 schema 校验通过。

**执行顺序（同一 SQLite 事务，顺序不可换 —— 否则瞬时违反 `uq_templates_active_one`）**

1. `SELECT` 该 scope 现有 `status='active'` 行（`WHERE lineage_id=? AND teacher_id=? AND type=? AND status='active' AND id != ?`）。
2. `UPDATE` 这些行 → `status='archived'`, `updated_at=now`；把 id 收进 `archived_ids`。
3. `UPDATE` 本行 → `status='active'`, `updated_at=now`。
4. `COMMIT`；失败则整体回滚（旧 `active` 仍是 `active`，不会出现「scope 无 active」的空窗）。

**幂等**：本行已是 `active` 且 scope 无其它 `active` → 200 `{"changed": false, "archived_ids": []}`。
**并发兜底**：捕获 SQLite 唯一约束异常（`sqlite3.IntegrityError`）→ 翻译成 409 `template_active_conflict`（附提示「請重試」），不暴露原始错误。
**响应**：见 §10.2 #6。
**副作用**：无其它表写操作（不碰 `drafts` / `patient_records`）。

### 11.2 `archive`（生效/草稿 → 已歸檔）

- `active → archived`：该 scope 变为「无生效模板」→ 后续生成回落内置骨架（§3.4，不报错）。
- `draft → archived`：弃用草稿。
- `archived → archived`：200 `changed:false`（幂等）。
- 二次确认文案见 §13.6。

### 11.3 `activate`（已歸檔 → 生效，内容不可改）

- 与 `publish` 完全相同的「同事务归档旧 active」规则；**不校验 schema_json**（它当初已通过发布校验且此后 `archived` 不可改 → 天然合法）。
- 若该行 `is_legacy=true`（存量回填）同样允许激活。

### 11.4 `derive`（派生新版本 = 前端「基於此版本修訂」）

**前置**：源行可为 `active` 或 `archived`（`draft` 不必派生 —— 直接 `PUT` 编辑）。
**版本计算**：`new_version = max(source.version + 1, 同链现有 max(version) + 1)`（第一部分 §4.2）。
**强制继承（不可由请求覆盖）**：`type` / `teacher_id` / `lineage_id` / `name`（默认继承，请求可改名）。
**复用规则**：同链已存在 `draft` → 返回既有草稿（`reused_draft: true`），不新建第二份草稿（§4.3 第 4 条）。
**校验**：§4.3 五条（父不存在 / scope 不符 / 自引用 / 未来版本 / 非法父）。
**响应**：201 + 新草稿（`status='draft'`, `parent_template_id=source.id`）。
**与 409 的联动（批复 3）**：前端捕获 `template_published_immutable` 后**自动改走本接口**并在 UI 上把按钮显示为「基於此版本修訂」，不向老师弹原始错误。

---

## 12. 草案生成接入 `template_id + version`

### 12.1 schema 变更（revision `0002_add_draft_template_refs`）

| 表 | 变更 | 说明 |
| :---- | :---- | :---- |
| `drafts` | `ADD COLUMN template_id INTEGER DEFAULT 0`、`ADD COLUMN template_version INTEGER DEFAULT 0` | `0` = 未记录（老数据 / 无模板生成）；DDL 单一来源仍为迁移（第一部分 §1.1），`init_db()` 不重复写 |

- `patient_records` **不改**：`sign_draft()`（`database.py:595+`）已同时落 `ai_draft`（AI 原草案）与 `final_plan`（老师最终版），生成时的文本快照已存在 → 「历史病历零回溯」无需再动该表（防范围蔓延）。
- 迁移可重跑：`PRAGMA table_info('drafts')` 探测后再 `ADD COLUMN`。
- `downgrade`：SQLite 3.49 支持 `DROP COLUMN`，但**默认不删列**（删列会丢引用信息）→ downgrade 只把版本号回退，列保留（文档标注）。

### 12.2 后端接线点（三条生成路径，全部「取不到模板即走旧逻辑」）

| 现有入口 | 现状 | 接线方式 |
| :---- | :---- | :---- |
| `POST /api/transcribe`（`main.py:533-554`） | `agent.generate_medical_draft(...)` → `insert_draft(...)` | 生成前取 `active` 的 `record` 模板；有模板 → 把模板骨架作为段落骨架提示交给生成（`agent` 侧新增可选参数，缺省行为不变）；`insert_draft` 带 `template_id/template_version` |
| `POST /api/upload-image`（`main.py:556-586` 内图片分支，574 行） | 同上传音路径 | 同上 |
| `POST /api/generate-draft`（`main.py:601-617`） | `build_draft_template(...)` | 同上（此路径是纯本地骨架，无 LLM） |

**关键约定**
1. **不改 `insert_draft` 既有位置参数**：扩展为 `insert_draft(transcript_id, patient_name, teacher_name, content, template_id=0, template_version=0)`，老调用方（含 `seed_test_data.py`）不改也能跑。
2. **flag off / 无 active 模板 / schema 版本不支持** → 三条路径输出与今天**逐字节一致**（回归红线）。
3. `GET /api/drafts` 返回体新增 `template_id` / `template_version` 两键（**只增不改**，旧前端忽略即可）；老师端可在草案卡显示小灰字「依 施治模板 v2 生成」（繁体）。
4. **AI 权限边界**：模板只决定「骨架与措辞参考」，`record` 中 `writable_by='teacher'` 的段（舌象/脉象/辨证/施治方案）智能体永不填内容。

### 12.3 施治方案套用路径的切换（前端）

| flag | 数据来源 | 行为 |
| :---- | :---- | :---- |
| `off` | `GET /api/plan_template` | 与今天 1:1（含「已套用模板，可修改」标记、`planTemplateFilledRef` 只套一次语义） |
| `on` | `GET /api/templates/active?type=treatment` → `schema_json.content`；**失败/为空则回退旧接口** | 套用逻辑（`App.tsx:591-602`）与标记逻辑不改，仅换取值来源 |

### 12.4 对第一部分 §5.2(4) 的细化修正（请一并确认）

第一部分写「`save_plan_template()` 内部在同一事务里同步写 `templates`」。落地时更安全的做法是 **best-effort 两段式**：

1. 先写 `plan_templates` 并 `COMMIT` → 保证旧接口行为 100% 不变（旧前端无论如何都能成功）。
2. 再写 `templates`（同 scope 无 `draft` 则更新该草稿的 `schema_json.content`；该 scope 的 `active` 是回填行 → 走派生 v2 草稿）；**失败只打日志**，不影响旧接口返回。

理由：flag 打开但 `templates` 表异常（例如迁移失败 → 503）时，不能让旧通道连带失败。新接口侧仍是严格事务（§11.1），只有 legacy 兼容通道放宽。

---

## 13. 前端：老师端模板配置页

### 13.1 挂载点与开关

| 项 | 决定 |
| :---- | :---- |
| 位置 | 老师端 **「管理」页签**（`teacherTab === 'manage'`，`App.tsx:2775/3287/3303/3381` 已有多张卡片）新增一张卡片，插在「學生管理」之后、「中藥材庫存」之前 |
| 卡片标题（繁体） | `📜 模板傳承（四類）` |
| flag off 行为 | 卡片**不渲染**（启动时用一次探测请求判定：`GET /api/templates?type=inquiry&include_schema=0` → 404/503 即视为关闭；结果缓存在 state，不重复探测） |
| `App.tsx` 改动量 | 仅两处：① `import TemplateStudio` + 在 manage 页签渲染 `<TemplateStudio teacherName={selectedTeacher} teacherId={selectedTeacher} />`；② 施治方案取值来源切换（§12.3） |
| 依赖 | 不新增任何 npm 依赖（沿用内联 style + `serif` 字体 + 主色 `#8b4513`，与存量视觉一致） |

### 13.2 组件结构（新文件 `frontend/src/TemplateStudio.tsx`，内部子组件同文件导出）

| 组件 | 职责 | 调用的接口 |
| :---- | :---- | :---- |
| `TemplateStudio`（外层） | 加载三态（載入中 / 載入失敗 / 就緒）、全局错误条、`warnings` 展示、保存后刷新 | 列表 + 默认探测 |
| `TemplateTypeTabs` | 四類切换：`問診` / `病歷` / `施治` / `開方`；徽章显示各类型 `active` 的版本号 | 无（数据来自列表） |
| `TemplateList` | 该类型全部版本：`v{n}`、状態徽章（`草稿` / `生效中` / `已歸檔`）、更新時間、操作按钮（`檢視` / `編輯草稿` / `發佈` / `歸檔` / `重新啟用` / `基於此版本修訂`） | `GET /api/templates?type=` |
| `TemplateEditor` | 按 `type` 分派到四个表单；统一「儲存草稿 / 發佈 / 取消」 | `POST /api/templates`、`PUT /api/templates/{id}`、`POST …/publish` |
| `InquiryForm` | 十問项列表：拖排序（上下移按钮，不引拖拽库）、`label` / `ask` / `required` / `answer_type` / `choices` 编辑、增删项（3–20） | 同上 |
| `RecordForm` | 段落列表：`title` / `hint` / `order` / `writable_by`（`ai`=智能體可填、`teacher`=留待老師）；`tone.forbidden` 词表编辑 | 同上 |
| `TreatmentForm` | 大文本域（`content`，计数器 / 2000 字）+ `placeholders` 列表 + 「存量遷移」标签（`is_legacy`） | 同上 |
| `PrescriptionForm` | 药材预选：复用现有药材搜索/网格交互（首字过滤 `GET /api/herbs/search`，`App.tsx:817-823` 同语义）；每味设 `default_amount` / `role` / `cooking_method`；缺库存显示黄字 `warnings` | 同上 + `GET /api/herbs` |
| `TemplateVersions` | 版本链时间线（`GET /api/templates/{id}` 的 `chain`）；每行一个「基於此版本修訂」按钮 | `POST …/derive` |
| `TemplatePreview` | 只读预览：`record` → 提交后草案骨架文本；`treatment` → 套用后文本；`prescription` → 药单草表（**仅预览，不落库**） | 纯前端渲染 |

### 13.3 交互流转（主流程）

| # | 步骤 | 前端动作 | 后端接口 | 界面反馈（繁体） |
| :---- | :---- | :---- | :---- | :---- |
| 1 | 进入「管理」页签 | 挂载 `TemplateStudio` → 探测 + 拉列表 | `GET /api/templates` | 載入中 → 四類徽章 + 版本列表 |
| 2 | 新建模板 | 选类型 → 用默认骨架预填 → 编辑 → 存草稿 | `POST /api/templates` | `草稿已儲存（未發佈）` |
| 3 | 发布草稿 | 点「發佈」 | `POST …/publish` | `已發佈：v2 生效中`；若 `archived_ids` 非空 → 灰条 `舊版本 v1 已歸檔（歷史病歷不受影響）` |
| 4 | 检视生效模板 | 点「檢視」→ 只读展示 | `GET /api/templates/{id}` | 顶部標籤 `生效中 · v2` |
| 5 | 修订生效模板 | 点「基於此版本修訂」 | `POST …/derive` | 跳到新草稿 `v3 草稿`；若 `reused_draft` → `已回到未發佈的修訂版` |
| 6 | 误点编辑（直改 active） | 前端拦截 + 自动改走派生 | `PUT` 得 409 → 立即 `POST …/derive` | `已發佈的版本不可直接修改，已為你開啟修訂版`（**不暴露 409**） |
| 7 | 归档 | 二次确认 → 归档 | `POST …/archive` | `已歸檔：不再用於新病歷，歷史病歷不受影響` |
| 8 | 重新启用 | 「重新啟用」→ 二次确认 | `POST …/activate` | `已重新啟用`；若有顶替 → 灰条提示旧版本归档 |
| 9 | 缺库存药材 | 保存时读 `warnings` | — | 黄字 `「{藥名}」未入庫，開方時將無法扣減庫存` |
| 10 | 接口关闭 / 未就绪 | 404 `templates_disabled` → 卡片整体隐藏；503 → 卡片内红字 `模板表未就緒，請聯絡管理員` | — | 不弹窗、不阻塞其它页签 |

### 13.4 文案规范（繁体古字，逐条给词）

| 场景 | 文案 |
| :---- | :---- |
| 卡片标题 | `📜 模板傳承（四類）` |
| 四類 tab | `問診`、`病歷`、`施治`、`開方` |
| 状態徽章 | `草稿`、`生效中`、`已歸檔` |
| 主要按钮 | `新建模板`、`儲存草稿`、`發佈`、`檢視`、`編輯草稿`、`基於此版本修訂`、`歸檔`、`重新啟用` |
| 提示 | `已發佈的版本不可直接修改，請基於此版本修訂`、`發布後舊版本將自動歸檔，歷史病歷不受影響`、`歸檔後不再用於新病歷，歷史病歷不受影響`、`模板只提供骨架與參考，診斷、辨證、開方、簽字皆由老師決定` |
| 术语区分（炁 / 氣，示范） | `先天之炁`（先天稟賦）、`後天之氣`（後天水穀）、`調理氣機`；**禁止全局简繁转换**，一律人工术语表（附录 A 待补） |
| 边界声明（固定展示于卡片底部） | `智能體永不診斷、永不開方、永不簽字` |

### 13.5 前端状态与数据流（不引状态库）

| state | 类型 | 用途 |
| :---- | :---- | :---- |
| `listByType` | `Record<type, Template[]>` | 列表数据 |
| `activeTabType` | `type` | 当前 tab |
| `editing` | `{mode:'create'\|'draft', type, id?}` \| null | 编辑器开关 |
| `draftForm` | 当前编辑中的 `name` + `schema_json` 对象 | 受控编辑 |
| `warnings` / `error` | `[{code,msg}]` / `string` | 黄字 / 红字 |
| `probeState` | `'unknown'\|'on'\|'off'\|'unavailable'` | flag 判定（§13.1） |

### 13.6 二次确认文案（防误操作）

- 歸檔：`歸檔「施治 · v2」？歸檔後不再用於新病歷，歷史病歷不受影響。`
- 發佈（同 scope 已有 active）：`發佈後「v1」將自動歸檔，新病歷改用 v2，歷史病歷不受影響。`
- 重新啟用：`重新啟用「v1」？若該類型已有生效版本，將一併歸檔。`

---

## 14. 测试清单

### 14.1 后端单测（pytest，文件 `backend/test_templates.py`，沿用 `client` fixture；`test_api.py` 不动）

**A. 迁移与模型（4 条）**

| 用例 | 断言要点 |
| :---- | :---- |
| `test_templates_table_created_by_migration` | `sqlite_master` 有 `templates` + 3 索引；部分唯一索引 SQL 含 `WHERE status = 'active'` |
| `test_migration_backfills_plan_template` | 预置 `plan_templates` 行 → 迁移后 `templates` 有对应 `active` v1 行、`name='施治模板（存量迁移）'`、`meta.legacy_source='plan_templates'`；`plan_templates` 行数与内容不变 |
| `test_migration_backfill_idempotent` | 连续两次 upgrade（或重跑回填）不产生重复行 |
| `test_active_unique_partial_index_enforced` | 直插两条同 scope `active` → `IntegrityError`；接口侧收到 409 `template_active_conflict` |

**B. CRUD（5 条）**

| 用例 | 断言要点 |
| :---- | :---- |
| `test_create_default_skeleton_per_type` | 四类分别 `POST`（不传 `schema_json`）→ 默认骨架符合 §9 契约（inquiry 10 项、record 6 段、treatment 空 content、prescription 空 herbs） |
| `test_create_reuses_existing_draft` | 同 scope 二次 `POST` → 200 + `reused=True`，`id` 相同 |
| `test_list_filter_by_type_and_status` | 四类过滤、`status` 过滤、排序 `type asc, version desc` |
| `test_get_single_with_chain` | `chain` 含链上全部版本，按 `version` 降序 |
| `test_no_delete_endpoint` | `DELETE /api/templates/{id}` → 405/404（无该路由） |

**C. 鉴权与参数（3 条）**

| 用例 | 断言要点 |
| :---- | :---- |
| `test_teacher_name_id_mismatch_403` | `teacher_name != teacher_id` → 403 `teacher_mismatch` |
| `test_cross_teacher_access_403` | 用另一老师身份读写他人模板 → 403，且不泄露行内容 |
| `test_lineage_id_non_empty_400` | 传 `lineage_id='x'` → 400 `lineage_not_supported` |

**D. 状态机（6 条）**

| 用例 | 断言要点 |
| :---- | :---- |
| `test_publish_auto_archives_old_active_same_tx` | 旧 `active` → `archived`、新行 `active`、响应 `archived_ids=[旧 id]`；**HTTP 200（不是 409）**；两者 `updated_at` 一致（同事务） |
| `test_publish_idempotent` | 重复 publish → `changed=False`、`archived_ids=[]` |
| `test_update_active_returns_409` | `PUT` 改 `active` 行 → 409 `template_published_immutable`；行内容与 `updated_at` 未变 |
| `test_update_archived_returns_409` | 同上（`archived` 只读） |
| `test_archive_active_then_generation_falls_back` | 归档后 `GET /api/templates/active` 返回 `null` |
| `test_activate_archived_requires_no_schema_check` | 重新启用成功且 `changed=True`；已有 active 时 `archived_ids` 非空 |

**E. 版本（5 条）**

| 用例 | 断言要点 |
| :---- | :---- |
| `test_derive_from_active_version_monotonic` | 新草稿 `version = max(parent+1, 链内 max+1)`、`parent_template_id=parent.id`、`status='draft'` |
| `test_derive_reuses_existing_draft` | 同链已有 draft → 200 + `reused_draft=True` |
| `test_derive_parent_scope_mismatch_400` | 父为别的 `type` / `teacher_id` → 400 `template_parent_scope_mismatch` |
| `test_derive_parent_not_found_and_self_reference` | 400 `template_parent_not_found` / `template_parent_self_reference` |
| `test_version_chain_no_duplicate_version` | 连续 derive → 版本序列严格递增且不重复（含「归档草稿占用版本号」场景） |

**F. 兼容与零回溯（5 条）**

| 用例 | 断言要点 |
| :---- | :---- |
| `test_legacy_plan_template_api_unchanged` | `GET/POST /api/plan_template` 请求/响应结构与迁移前一致（键集合 + 值） |
| `test_legacy_write_dual_write_creates_draft_v2` | flag on 时旧接口写 → 同 scope 出现 `draft` v2（不改 `active` 内容） |
| `test_legacy_write_succeeds_when_templates_broken` | 模拟 `templates` 表不可用 → 旧接口仍 200，仅日志告警（§12.4） |
| `test_template_archive_does_not_touch_history` | 发布 v2 后，引用 v1 的草案 `content` 与 `patient_records.final_plan` 逐字节不变 |
| `test_templates_flag_off_returns_404` | `TEMPLATE_API_ENABLED=off` → 全部 `/api/templates*` 404 `templates_disabled` |

**G. 生成接入（4 条）**

| 用例 | 断言要点 |
| :---- | :---- |
| `test_generate_draft_records_template_ref` | 有 active `record` 模板时，`drafts.template_id/version` = 模板行列值 |
| `test_generate_draft_without_template_unchanged` | 无模板 → 输出与 `build_draft_template` 黄金文本逐字节一致，`template_id=0` |
| `test_insert_draft_backward_compatible` | 不传新参数（老调用方签名）仍成功，两列为 0 |
| `test_inquiry_template_not_wired_in_epic1` | 配置 `inquiry` 模板不影响学生端追问输出（Epic 1 只存不用） |

**H. 既有回归（红线）**：`cd backend; ..\venv\Scripts\python.exe -m pytest` → `test_api.py` 现有用例**全部保持通过**（含 `test_local_prescription_deducts_stock` / `test_remote_prescription_does_not_deduct`）。

### 14.2 前端手工自测（`tsc build` + `oxlint` + 手工；不引 vitest）

| # | 步骤 | 预期 |
| :---- | :---- | :---- |
| 1 | `cd frontend; npm run build` / `npm run lint` | `tsc -b` 与 `oxlint` 零报错 |
| 2 | 老师端 → 管理 → 模板傳承卡片 | 卡片出现；四類 tab 可切换；文案全繁体 |
| 3 | 新建 `施治` 模板（默认骨架）→ 存草稿 → 發佈 | `草稿` → `生效中`；无旧 active 时 `archived_ids` 为空 |
| 4 | 再建并发布 `施治` v2 | 出现灰条「舊版本 v1 已歸檔」；v1 徽章变 `已歸檔` |
| 5 | 点 v1 的「基於此版本修訂」 | 生成 v3 草稿，`parent_template_id` 指向 v1；再点一次 → 回到同一草稿（不复用第二份） |
| 6 | 尝试直改「生效中」模板（模拟旧路径） | 不弹 409，而是自动打开修訂版并提示「已發佈的版本不可直接修改…」 |
| 7 | 歸檔 → 二次确认 | 徽章 `已歸檔`；诊室再次出稿走内置骨架（无报错） |
| 8 | 「重新啟用」v1 | 变为 `生效中`；若已有生效版本 → 提示旧版本归档 |
| 9 | 开方模板：选 3 味药 + 设 default_amount/role/cooking_method | 保存后重进，预选与预填完整；`role` / `cooking_method` 选项与九宫格下拉一致 |
| 10 | 开方模板：加一味未入库存的药 | 保存成功 + 黄字提示「未入庫，開方時將無法扣減庫存」 |
| 11 | 问诊模板：改顺序 / 增删项（含 3 与 20 的边界） | 顺序与项数保存正确；越界（<3 / >20）有明确提示不提交 |
| 12 | 病历模板：把 `辨證` 段设 `teacher` | 预览中该段只留 `辨證：`，无任何 AI 填充文案 |
| 13 | 存量治理核对 | 「施治」列表里存在「施治模板（存量迁移）」`v1` `生效中`（`is_legacy` 标签） |
| 14 | 施治方案自动套用回归 | 选中学生、方案为空 → 自动套用当前生效模板内容；「已套用模板，可修改」提示仍在；清空后不会被再次填回（`planTemplateFilledRef` 语义不变） |
| 15 | flag off 回归 | 卡片不渲染；`plan_template` 旧链路、九宫格开方、病历签字链路一切如常 |
| 16 | 迁移未就绪（手工把 `templates` 改名） | 卡片内红字「模板表未就緒」；其它页签功能不受影响 |

### 14.3 提交门禁（每条 PR 都要过）

1. `cd backend; ..\venv\Scripts\python.exe -m pytest`（全绿，含新增 `test_templates.py`）。
2. `cd backend; alembic upgrade head` + `alembic downgrade base` + `upgrade head` 三连演练通过；`plan_templates` 数据前后一致。
3. `cd frontend; npm run build`、`npm run lint` 零报错。
4. PR 说明含：对齐白皮文章节、验收标准、回退方案（`development-plan-v1.md:306`）。

---

## 15. 第二部分待确认清单

| # | 事项 | 建议 | 备选 |
| :---- | :---- | :---- | :---- |
| 1 | 模板配置页挂载位置 | **「管理」页签**新增「📜 模板傳承（四類）」卡片 | 放「設定」页签（与排班/预约并列） |
| 2 | `prescription` 模板里库存缺失的药材 | **200 + `warnings` 黄字提示**（不拦截） | 400 硬拒（须先补库存） |
| 3 | `formulas`（常用方剂） | Epic 1 **只定契约、不做 UI**（界面只做 `herbs` 预选） | Epic 1 就做方剂增删 UI（工作量+1 天） |
| 4 | `inquiry` 模板是否接管学生端追问 | Epic 1 **只做配置 + 存储 + 读接口**，生成路径不动（存量零风险） | Epic 1 即接管学生端追问顺序（触碰学生端存量） |
| 5 | `drafts` 补列方式 | 走迁移 `0002_add_draft_template_refs`（DDL 单一真相源） | 沿用 `init_db()` 的 `try/except ADD COLUMN` 手法（与第一部分 §1.1 冲突） |
| 6 | 错误响应包装 | `HTTPException(detail={"error":…,"msg":…})` → 前端读 `res.detail.error` | 200 + `{"error":…}`（与存量老接口一致，但失去状态码语义） |

---

第二部分 完。第三部分（实施顺序与验收）待需要时输出并追加。

