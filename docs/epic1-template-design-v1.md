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

- 表名：`templates`（与 `plan_templates`、规划中的 `student_rank_record` 并存；`plan_templates` 保留为兼容镜像，见 §5）。
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

第一部分 完。后续部分输出并获批后追加至本文件。

