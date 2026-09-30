# Epic 4 设计：多师管理（师门归属与隔离）v1

> 状态：**step 4.0 已交付、step 4.1 已放行**（CTO 2026-09-29 批复六项裁决 + 附录 A 五项；step 4.1 交付见附录 B）。本文件是 Epic 4 的**设计唯一真相源**：step 4.0 交付时纯文档、零代码；step 4.1 的迁移与用例不在本文件内，见 `backend/alembic/versions/0005_add_lineage.py` 与 `docs/migrations/0005_add_lineage.sql`。
> 对齐：白皮书 2.0 第四章 4.2（原文 §1.3）、§1.2 双主权（原文 §1.4）。
> 本文是 Epic 4 的**唯一设计真相源**；**DDL 唯一真相源 = 迁移 `0005`**（沿用 Epic 1 §1.1 纪律：`database.py::init_db()` 不重复写一份 DDL）。
> 语言纪律：叙述用简体；**所有 UI 文案一律繁体古字**（沿用 Epic 1 §13.4 与决策 11）。
> 施工顺序：step 4.0 → 4.1 →（4.2 ∥ 4.3）→ 4.4（§9）。
> 铁律：AI 永不诊断、永不开方、永不签字（决策 3 / Epic 2 §2.1）在本 Epic 内**一字不动**。

---

## 0. 术语与范围

### 0.1 术语表

| 术语 | 定义 | 实现载体 |
| :---- | :---- | :---- |
| `lineage`（师门） | 老师开创的传承单元；**阶段一一师一门** | 新表 `lineage`（§2.1） |
| `student_lineage`（**概念名**） | 学生 × 师门的归属关系（学生可属多师门） | **实现名 = `patient_teachers` 升级版，不新建表**（裁决①，§2.2） |
| 师门归属 | **访问范围**，不是数据所有权（裁决⑤，§5.5） | 各业务表 `lineage_id` 列 |
| 默认师门 | 每位老师一个，`id = 'lin-' + slugify(teacher_name)` | `lineage` 种子行（§6.1-③） |
| 未归属 | `lineage_id = ''`（**唯一哨兵**，且 **≠** 默认师门） | 列默认值（裁决②，§2.4） |
| 当前师门 | 请求上下文中的师门：老师端 = 其唯一师门；学生端 = 当前视图所选 | 请求参数 `lineage_id` + 服务层校验（§4.3） |
| `slugify` | 老师名 → 小写 ASCII 安全串；非 ASCII 字符统一转 `-`；连续 `-` 折叠；首尾 `-` 去除；空结果回落 `u<sha1(名)[:8]>`（稳定、可复现、跨机一致） | `lineage` 种子生成（§6.1-③） |

### 0.2 范围

**做**（对齐 `development-plan-v1.md` §3.3-D4 与 §5-Epic 4）

1. 新建 `lineage` 实体表 + 每位老师一个默认师门；`patient_teachers` 升级为事实上的 `student_lineage`。
2. 病历 / 草案 / 临床周边 / 智能体派生数据绑定 `lineage_id`。
3. 老师端查询**强制**带 `lineage_id`，只返回本师门数据。
4. 学生端师门视图切换 + 跨师门汇总 + 退出师门（`status='inactive'`，**不删数据**）。
5. 前端**两个维度并存**：人的维度（老师关系，`我的老師（n/3）`）+ 组织维度（师门关系）（裁决⑥，§7.1）。

**不做**（防范围蔓延）

- 段位系统（Epic 5）；治理见证入口（独立子任务，Epic 4 之后）；引荐链 / 存活门限 / 协议底线（阶段三）。
- 登录体系与鉴权（§5.1）；加密 / 思想指纹 / 监护模式 / 导出迁移（阶段二）。
- `herb_inventory` / `teacher_settings` / `invites` / `points_*` / `transactions` 的师门化。
- **不改** `agent_stage_state` 主键、**不改**阶段语义与五阶段矩阵（裁决③，§5.3）。

### 0.3 三条不可动不变量（本 Epic 红线）

1. **双主权不可削弱**：师门归属只是访问范围（§1.4 / §5.5）。
2. **AI 三铁律**：永不诊断、永不开方、永不签字（决策 3）。
3. **阶段是老师的能力画像**：`agent_stage_state` 保持 `teacher_name` 单列 PK、`lineage_id` 恒 `''`（§5.3）。

---

## 1. 依据：六项裁决与白皮书原文

### 1.1 六项裁决（CTO 2026-09-29 批复，逐条落地）

| # | 裁决 | 依据 | 落点 |
| :-- | :---- | :---- | :---- |
| ① | `student_lineage` 口径选 **A**：升级 `patient_teachers` 为事实上的 `student_lineage`，**不新建表**；概念名 = `student_lineage`，实现名 = `patient_teachers`（升级版） | 「同一个判断只许有一份实现」（Epic 2 step 2.3 追加要求）；`patient_teachers` 已具备 `status`/`inactive`/3 上限语义（`database.py:124-132`、`:486-525`）；新建表 = 两处真相（双写漂移） | 本文 §2.2；`development-plan-v1.md` §3.3-D4（L134-137）与 §5-Epic 4（L226-228）已同步 |
| ② | 空串语义选 **②**：`''` = **未归属**；默认师门用**显式 id**（`lin-<slug>`） | 若 `''` = 默认师门，则任何遗漏 lineage 的写入会**静默**落进默认师门（污染且不可区分） | 本文 §2.4 / §5.4；迁移 §6.1-② / §6.2 |
| ③ | `agent_stage_state` PK 选 **A + C**：阶段保持**老师全局**（`teacher_name` 单列 PK 不变、`lineage_id` 恒 `''`）；另在 `agent_stage_log` **补 `lineage_id` 列**做审计区分 | 「不推倒重来」+ 0003 已验收；step 3.4-c 已建守护（唯一向上写路径、⑱ 组断言 `stage=` 写点恰 3 处）；改 PK 需整表重建 = 变更已验收交付物 | 本文 §5.3；迁移 §6.1-④ |
| ④ | 全库 downgrade 口径**统一**为「**不删业务列，只回收结构（表、索引）**」；0004 为**已存在例外**，不追溯修改；Epic 4 的 `0005` 采用新口径 | 统一运维直觉（避免「回退丢列」）；0004 已验收，改它属变更已验收交付物 | 本文 §6.3；`docs/tech-debt.md` TD-003 已更新 |
| ⑤ | 白皮书 §4.2 / §1.2 原文由 CTO 补齐（§1.3 / §1.4）；`lineage` 表按裁决①定稿：TEXT 主键、同构 `templates.lineage_id`、一师一门（`id = 'lin-' + slugify(teacher_name)`） | TEXT 主键 → 与既有两处 `lineage_id` 列零类型转换；一师一门 → 默认师门可由 `owner_teacher_name` 唯一确定 | 本文 §1.3 / §1.4 / §2.1 |
| ⑥ | 前端「师门」与「我的老师（n/3）」**并存**，两个维度：人的维度（老师关系）+ 组织维度（师门关系）；Epic 4 阶段一师一门 → 3 老师上限 = 3 师门上限 | 不破坏已验收 UI 与语义；「人」与「组织」在概念上正交 | 本文 §7.1 / §7.3 |

### 1.2 本次 step 4.0 落点速查

| 文件 | 变更 |
| :---- | :---- |
| `docs/epic4-lineage-design-v1.md` | **新建**（本文，step 4.0 唯一交付物） |
| `docs/development-plan-v1.md` | §3.3-D4（L134-137）+ §5-Epic 4 子任务（L226-228）改为 `patient_teachers` 升级口径；技术决策 12（L176）已落盘 |
| `docs/backlog-white-paper-v2.1.md` | R-009 / R-010 已落盘（L21-22） |
| `docs/tech-debt.md` | TD-003 更新为全库统一口径（裁决④） |

### 1.3 白皮书 2.0 §4.2 原文（CTO 2026-09-29 补）

> 「学生可同时跟随多位老师。档案按师门隔离。老师端查询强制带 `lineage_id`，只返回本师门数据。学生端可切换师门视图，也可看汇总。学生退出某师门，标记 inactive，不删除数据。学生可自行退出，不设出师认证。」

**逐句对 Epic 4 的约束**：① 多师是**学生侧**权利；② 隔离粒度 = **师门**（不是老师）；③ 老师端强制 `lineage_id`；④ 学生端视图切换 + 汇总；⑤ 退出 = `inactive` + **数据保留**；⑥ **不设出师**（与回流候选 R-006 一致）。

### 1.4 白皮书 2.0 §1.2 原文（CTO 2026-09-29 补）与双主权约束

> 「社区有两个主权，两个对象，互不冲突。数据主权归患者：患者拥有姓名 + 家庭关系，有权删除「张三」这个标识，但不能删除知识。知识产权归老师：老师拥有从原材料中抽象出的知识，可以传承、署名、带走。平台不拥有知识，不拥有数据，只提供协议、身份、路由、存储、结算。」

**CTO 对 Epic 4 的硬约束（原话照录）**：

- 师门归属是**访问范围**，不是数据所有权。
- 患者对病历经文的主权**不可被师门归属削弱**。
- `patient_records` / `drafts` 加 `lineage_id` 是**过滤维度**，不是所有权标记。
- 患者可携权（导出、删除）**不受师门归属影响**。

**推论（写入后续 Epic 的接口约定）**：

1. 学生退出师门后其病历**仍在库中**：老师端 `inactive` 后不可访问，学生端仍可读/可导出。
2. 患者行使删除权时，删除的是**身份标识与对象关联**，**不**删除已抽象的知识（阶段二实现；本 Epic 的义务是**不阻塞** —— 不得引入任何以 `lineage_id` 为前提的硬约束去阻止导出/删除）。
3. 老师可带走的是**知识**（模板、施治经验），**不得**包含患者标识。

---

## 2. 数据模型

### 2.1 `lineage` 表（定稿 DDL，裁决⑤）

**唯一真相源 = 迁移 `0005`**（本处仅抄录契约；施工时以迁移为准。`database.py::init_db()` **不**再写一份 `CREATE TABLE lineage`，沿用 Epic 1 §1.1 纪律）。

```sql
CREATE TABLE IF NOT EXISTS lineage (
    id                  TEXT PRIMARY KEY,
    name                TEXT NOT NULL,
    owner_teacher_name  TEXT NOT NULL,
    description         TEXT DEFAULT '',
    status              TEXT NOT NULL DEFAULT 'active',
    created_at          TEXT NOT NULL DEFAULT '',
    updated_at          TEXT NOT NULL DEFAULT ''
);
CREATE INDEX IF NOT EXISTS idx_lineage_owner ON lineage (owner_teacher_name, status);
```

| 项 | 口径 |
| :---- | :---- |
| 主键 | `id TEXT PRIMARY KEY` = `'lin-' + slugify(teacher_name)`；与 `templates.lineage_id`、`agent_stage_state.lineage_id`（均 TEXT）**同构** → 全链零类型转换 |
| 一师一门（阶段一） | 由**服务层**保证 `owner_teacher_name` 唯一（沿用 `uq_templates_active_one` 的「服务层规则 + 索引」纪律）；**不加** DB 级 UNIQUE —— 全库零 CHECK/FK，SQLite 加约束需整表重建（Epic 1 §1.4 已论证） |
| 明确不加的列 | `deleted_at`（删除语义 = `status='archived'`）、`is_default`（默认师门 = 该老师唯一师门，冗余）、`settings_json`（无需求，防范围蔓延） |
| 不加 FK / CHECK | 全库 24+ 张表零 FK/CHECK，`PRAGMA foreign_keys` 从未开启（加了形同虚设） |
| `status` 白名单 | Python 常量 `LINEAGE_STATUSES = ("active", "archived")`，服务层校验（非法值 → 400 `lineage_invalid`） |
| 时间列 | ISO 字符串（`datetime.now().isoformat()`，与 `templates.created_at/updated_at` 同款） |
| `slugify` 口径 | 小写化 → 非 `[a-z0-9]` 字符转 `-` → 折叠连续 `-` → 去首尾 `-` → 空结果回落 `u<sha1(名)[:8]>`（稳定、可复现：同一老师在任一机器得到同一 id） |
| 与 `teachers` 的关系 | 不加 `teachers` 列、不建 FK；`owner_teacher_name` 语义 = `teachers.name`（与全库「`teacher_name` 即身份」口径一致，Epic 2 §1.2） |

### 2.2 `patient_teachers` 升级（= `student_lineage` 的实现，裁决①）

现状（已核对 `database.py:124-132`）：列 `patient_name, teacher_name, status, created_at`；PK `(patient_name, teacher_name)`；已具备 `status='active'|'inactive'`、3 老师上限（`:489`）、两条归属入口（`add_patient_teacher` `:486-500`、`teacher_add_student` `:503-518`）、退出 = `inactive` 不删行（`:520-525`）。

| 变更 | 内容 |
| :---- | :---- |
| 补列 | `ADD COLUMN lineage_id TEXT NOT NULL DEFAULT ''`（探测式补列、可重跑） |
| 回填 | 按 `teacher_name` → 该老师默认师门 id（§6.2） |
| 语义 | 一行 = 「学生 × 师门」归属；`status` **复用**：`active` = 在师门内、`inactive` = 已退出（**不删行、不删数据**） |
| 上限 | 「最多 3 位老师」→「**最多 3 个师门**」（阶段一一师一门，数值等价；文案见 §7.3） |
| 唯一性 | PK `(patient_name, teacher_name)` **不变**；**不加** `UNIQUE(patient_name, lineage_id)`（阶段一两者一一对应，约束无收益却增加迁移成本） |
| 两条入口硬要求 | `add_patient_teacher()` / `teacher_add_student()` 在 **flag on** 时必须写入并校验 `lineage_id`；`teacher_add_student` 现有 `except sqlite3.IntegrityError: pass`（`:512-513`）静默路径需在 flag on 时改为「已存在则更新 `lineage_id`/`status`」；**flag off 时两条入口语句一字不改** |
| 命名纪律 | 设计文档、注释、日志统一写「`student_lineage`（实现：`patient_teachers` 升级版）」，避免后人误以为存在同名表 |

### 2.3 补 `lineage_id` 的表清单

| 分类 | 表 | 变更 | 理由 |
| :---- | :---- | :---- | :---- |
| **必须**（越权核心） | `patient_records` | ADD `lineage_id` | 病历正文与历史档案 = 老师端可见的实质内容（`database.py:899`） |
| **必须**（越权核心） | `drafts` | ADD `lineage_id` | 未签字草案（`database.py:804`） |
| **必须**（临床周边） | `complaints`、`appointments`、`prescriptions`、`homework`、`transcriptions`、`record_tags` | 各 ADD `lineage_id` | 皆「老师 × 患者」配对的业务数据，漏一处即漏一类 |
| **必须**（智能体派生） | `agent_tasks`、`agent_action_log` | 各 ADD `lineage_id` | 请示与行动日志是老师可见的派生数据（`:1660/:1665`、`:1762`） |
| **必须**（裁决③-C） | `agent_stage_log` | ADD `lineage_id` | **审计区分**用（阶段本身仍老师全局，§5.3） |
| **已在**（语义升级） | `templates` | 不 ADD | 由「恒 `''`」升为「必填且必须存在于 `lineage`」（§3.3） |
| **升级** | `patient_teachers` | ADD（§2.2） | = `student_lineage` 实现 |
| **不加**（明确） | `patients`、`patient_profiles` | — | 患者是**跨师门主体**；给「人」加师门归属与 §1.4 数据主权直接冲突 |
| **不加**（明确） | `teachers` | — | 一师一门由 `lineage.owner_teacher_name` 表达，冗余列无收益 |
| **不加**（明确） | `agent_stage_state` | — | 已有列但**恒 `''`**，不改结构（裁决③-A，§5.3） |
| **不加**（明确） | `agent_stage_config` | — | 阈值配置同属**老师维度**（全局行 `''` + 老师覆盖行）；加师门维度 = 「按师门分阶段」，属裁决③-A 明确排除 |
| **不加**（明确） | `teacher_settings`、`herb_inventory`、`invites`、`accounts`、`points_*`、`transactions` | — | 老师私有资源 / 凭据 / 财务库存，与师门隔离无关（本 Epic 不做「师门共用库存」） |
| **不加**（引用既有定位） | `plan_templates` | — | Epic 1 §7.6 已定位为**兼容镜像**（Epic 2 起只读、只由旧接口维护），其内容 flag on 下已**单向双写**进 `templates`（带 lineage）。**A1 已裁决（CTO 2026-09-29）：不加** —— 补列会连带触发旧接口改动，属变更已验收交付物；缺口登记为 `docs/tech-debt.md` **TD-005**，触发条件 = 开放「一师多门」或白皮书要求旧接口过滤 |

### 2.4 空串语义（裁决②）

| 值 | 含义 | 允许出现的位置 |
| :---- | :---- | :---- |
| `''` | **未归属**（唯一哨兵：脏数据 / 迁移未覆盖 / 外部写入） | 只允许作列默认值与异常兜底，**不允许**作为业务正常态 |
| `lin-*` | **显式师门**（含每位老师的默认师门） | 所有正常写入（flag on） |

三条硬纪律：

1. **写侧**：flag on 时缺 `lineage_id` → 服务层 **4xx 报错**，**不许**静默兜底成默认师门。
2. **读侧**：flag off → 不过滤（`''` 与 `lin-*` 行为完全同旧）；flag on → 只按请求师门过滤（`''` 的行**对任何师门都不可见**）。
3. **明令禁止**：`COALESCE(lineage_id, 'lin-...')`、`OR lineage_id = ''` 式「兼容过滤」——它们把「未归属」偷换成「默认师门」。

### 2.5 索引

| 索引 | 决策 | 理由 |
| :---- | :---- | :---- |
| `idx_lineage_owner (owner_teacher_name, status)` | **建**（随 `lineage` 表，§2.1 DDL） | 「某老师的师门」「活跃师门清单」是 P0 读路径 |
| `idx_patient_teachers_lineage (lineage_id, teacher_name, status)` | **建议建** | 老师端「本师门学生名单」是 P0 读路径；既有 PK `(patient_name, teacher_name)` 帮不上 `lineage_id` 前缀查询 |
| 其余业务表的 `lineage_id` 索引 | **默认不建**，由 step 4.1 以 `EXPLAIN QUERY PLAN` 实测决定 | 百量级数据下无收益索引只增迁移成本；沿用 Epic 1 §1.3 克制口径（「不建 `name` 索引」同款理由） |
| `agent_stage_log` 的 lineage 索引 | **不建** | 阶段是老师维度（§5.3），lineage 只作审计标注，不进主力读路径 |

---

## 3. 归属语义与读路径

### 3.1 归属 = 访问范围（不是所有权）

```
患者（patients / patient_profiles：跨师门主体，不带 lineage_id）
  └─ patient_teachers（= student_lineage 实现）：patient_name × lineage_id × status
        └─ 决定「谁在哪个师门里」→ 决定「老师能看见哪些患者的行」
业务行（patient_records / drafts / …）：teacher_name + lineage_id
  └─ lineage_id = 过滤维度（裁决⑤）；导出 / 删除权归患者，不受此影响
```

- **归属显式落库**（不每次 JOIN 推导）：便于读路径与审计；推导规则 = `teacher_name` →（该老师唯一师门）→ `lineage_id`。
- **学生可见性**：由 `patient_teachers(patient_name, lineage_id, status='active')` 决定，**不**由行内 `lineage_id` 单独决定。
- **老师可见性**：请求老师必须属于该 `lineage_id`，且上下文师门 = 该 `lineage_id`（双因子）。

### 3.2 老师端读路径改造清单（flag on 后）

**P0（漏改即越权）**

| 位置 | 现状（参数可空 = 高危） | flag on 后 |
| :---- | :---- | :---- |
| `database.py:899` `get_patient_records` ← `main.py:735` `/api/patient-records` | `teacher_name` 可空 → 空 = 该患者**所有老师**的记录 | 强制 `lineage_id` + `teacher_name`；`teacher_name` 空 → 400（**不许**退化为全量） |
| `database.py:804` `get_drafts` ← `main.py:679` `/api/drafts` | `teacher_name` 可空 → 空 = **全库**所有患者最新未签草案 | 同上；并把「未归属行」排除在结果外 |
| `database.py:624` `get_transcriptions` ← `main.py:653` | 可空 | 强制 `lineage_id` |
| `database.py:1065` `get_appointments` ← `main.py:831` | 可空 | 强制 `lineage_id` |
| `database.py:441` `get_teacher_patients` ← `main.py:181` | 只按老师取学生 | 按 `(lineage_id, teacher_name)` 取，且只取该师门内 `is_active` 的归属行 |

**P1（派生数据 / 提醒）**：`database.py:449`（师生 active 判定）、`:593/:607`（homework）、`agent.py:547`（`_teacher_student_names`）、`:658`（复诊提醒 `MAX(visit_at)`）、`agent.py:583-619`（欠费提醒）、`agent.py:685-695`（`/api/agent/scan` 三扫描）、`database.py:1592/:1601`（silent 扫描与请示去重）、`:1660/:1665`（`agent_tasks`）、`:1762`（`agent_action_log`）、`:1945`（pending 去重）、`:2281/:2287`（`complaints`）、`:1560`（`prescriptions`）、`:1149`（tags-summary）、`:2223/:2242`（`plan_templates`，见 §2.3 待确认项）。

**P2（指标口径，最隐蔽）**：`database.py:2082/:2096`（`get_draft_samples` / 记录样本）、`:2195`（stage log stats）——flag on 后按师门取样，否则阶段评估读进别师门样本。

**不改**：`herb_inventory`（`:1321/:1331/:1385/:1400/:1505`）、`teacher_settings`（`:965/:1007/:1045`）、`accounts` / `points_*` / `transactions`、`agent_stage_state`（`:1815`）。

### 3.3 模板线（`templates`）

| 项 | 现状 | Epic 4 动作 |
| :---- | :---- | :---- |
| scope 唯一真相源 | `template_service.py:527` `_SCOPE_WHERE = "lineage_id = ? AND teacher_id = ? AND type = ?"` | **一字不改**（`lineage_id` 已在 WHERE 首位；Epic 1 已为此前置） |
| 接口层收口 | `template_api.py:89-92` `_check_lineage`：非空 → 400 `lineage_not_supported` | 由「**拒**」改为「**校验**」：flag on 时必须非空、必须存在、请求老师必须属于该师门；否则 `lineage_required` / `lineage_not_found` / `lineage_forbidden`。四个调用点：`template_api.py:146/167/193/280` |
| 部分唯一索引 | `uq_templates_active_one (lineage_id, teacher_id, type) WHERE status='active'` | **无需改**：天然支持「同一老师在不同师门各有一条 active」 |
| 智能体取模板 | `template_service.py:648` `get_active_template(teacher_id, type, lineage_id)` | 调用点补齐 lineage 参数（**漏传即取错师门模板** → 智能体拿别家模板生成草案） |
| 派生 / 发布 | `template_service.py:742`、`:797-839`（derive 的 scope 一致性） | 继承既有 scope 校验口径，**不改语句形状**，只把请求里的 lineage 从「必须为空」放开为「必须合法」 |

### 3.4 学生端（功能 → 接口 → 规则）

| 能力 | 接口（§4.2） | 规则 |
| :---- | :---- | :---- |
| 我的师门清单 | `GET /api/student-lineages?student_name=` | 返回 `active` + `inactive`（含退出历史），带 `lineage.name` 与老师名 |
| 参与某师门 | `POST /api/student-lineages` | 学生自加（沿用 `add_patient_teacher` 语义 + 师门校验）或老师拉入（`teacher_add_student`） |
| 退出师门 | `DELETE /api/student-lineages` | = `patient_teachers.status='inactive'`；**不删数据**；退出后该老师不可访问该学生在**该师门**的行 |
| 跨师门汇总 | `GET /api/lineages/summary?student_name=` | **只读聚合**（各师门就诊数 / 未签草案数 / 最近活动）；**不做**单一合成等级（段位属 Epic 5 §D5） |
| 视图切换 | 前端本地状态（§7.3） | 切换师门 = 换 `lineage_id` 上下文 → 重拉数据并**清场** |
| 导出 / 删除 | **不属本 Epic**（阶段二） | 本 Epic 义务 = **不阻塞**：不得让 `lineage_id` 成为导出/删除的前置条件（§1.4 推论 2） |

---

## 4. 接口契约

**错误体形状**：沿用 Epic 1 `_fail`（`template_api.py:67-71`）—— FastAPI `HTTPException.detail = {"error": <code>, "msg": <人类可读>, "errors": [], "warnings": []}`；配置类（若涉及）沿用 Epic 2 的 `errors: [{path, msg}]`。

### 4.1 错误码契约

| HTTP | `error` | 触发条件 | 备注 |
| :---- | :---- | :---- | :---- |
| 400 | `lineage_required` | flag on，老师端接口缺 `lineage_id`（含 `teacher_name` 为空的历史「全量」调用） | **不许**退化为全量返回 |
| 403 | `lineage_forbidden` | `lineage_id` 合法，但请求老师不属于该师门（或学生不在该师门） | 双因子校验失败 |
| 404 | `lineage_not_found` | `lineage_id` 在 `lineage` 表中不存在 | 含拼写错误 / 已删除的假想 id |
| 404 | `lineage_disabled` | flag off 时访问全部 `/api/lineages*` / `/api/student-lineages*` | 照抄 `templates_disabled` / `agent_stage_disabled` 口径 |
| 400 | `lineage_invalid` | 师门创建/修改字段校验失败（`status` 不在 `LINEAGE_STATUSES`、`name` 空等） | 沿用 Epic 1 错误体 |
| 409 | `student_lineage_limit` | 加入师门超过上限（3 个） | 沿用既有「最多 3 位老师」业务语义 |
| 400 | `lineage_not_supported` | **仅 flag off 保留**（Epic 1 既有语义：传非空 `lineage_id` 即拒） | flag on 后**不再返回**此码 |
| 503 | `lineage_store_unavailable` | flag on 但 `lineage` 表不存在（迁移未跑） | 照抄 `template_store_unavailable` |

### 4.2 新增接口（7 个，全部 flag 门后，第一道 = 404 `lineage_disabled`）

| 方法 | 路径 | 用途 | 关键参数 |
| :---- | :---- | :---- | :---- |
| GET | `/api/lineages` | 师门清单（老师＝自己开创的；学生＝已加入的） | `teacher_name` **或** `student_name`（二选一） |
| POST | `/api/lineages` | 开山门（阶段一：一师一门，重复 → 409 或幂等返回既有行，step 4.2 定稿） | `teacher_name` + `teacher_id`（一致校验）+ `name` |
| POST | `/api/lineages/{id}/archive` | 封存（**不提供 DELETE**，沿用 Epic 1 §10.1） | `teacher_name` + `teacher_id` |
| GET | `/api/student-lineages` | 我的师门（含退出历史） | `student_name` |
| POST | `/api/student-lineages` | 加入师门（学生自加 / 老师拉入） | `student_name` + `lineage_id`（+ 老师身份） |
| DELETE | `/api/student-lineages` | 退出师门（`status` → `inactive`，**不删数据**） | `student_name` + `lineage_id` |
| GET | `/api/lineages/summary` | 学生端跨师门只读汇总 | `student_name` |

**不提供**：`DELETE /api/lineages/{id}`（删除语义 = `archived`）、任何「改师门 id / 换 owner」接口（改归属 = 退出 + 加入两步）。

### 4.3 既有接口改造（路径不变，只加参数与校验）

| 组 | 接口 | flag on 动作 | flag off |
| :---- | :---- | :---- | :---- |
| 老师端读 | `/api/drafts`、`/api/patient-records`、`/api/transcriptions`、`/api/appointments`、`/api/teacher/patients` 等 §3.2 P0/P1 | 必带 `lineage_id`，SQL 加过滤；缺 → 400 `lineage_required` | **零行为变化**（含「参数可空 = 全量」的既有行为） |
| 老师端写 | `insert_draft`、`sign_draft`、`save_*` 等写入点 | 写侧落 `lineage_id`；缺 → 4xx（§2.4 纪律 1） | 零行为变化（不写新列，或写 `''`） |
| 归属 | `/api/patient-teachers`（POST/DELETE）、`/api/teacher/add-student` | 校验并写 `patient_teachers.lineage_id`；`teacher_add_student` 的静默 `IntegrityError` 分支改为「已存在则更新」 | 零行为变化（两条 SQL 一字不改） |
| 模板 | `/api/templates`（4 入口） | `_check_lineage` 由「拒」改「校验」（§3.3） | 保持「非空 → 400 `lineage_not_supported`」 |

### 4.4 feature flag：`LINEAGE_ENABLED`

- 常量与判定函数照抄既有两套（**同一份实现口径**）：`LINEAGE_ENABLED_VALUES = ("on", "1", "true", "yes")` + `lineage_enabled()` **每次调用现读**（便于灰度切换 / 测试，不必重启）；**默认 off**（参照 `template_service.py:898-909`、`agent_stage_service.py:137-163`）。
- **off（默认）**：`/api/lineages*` 与 `/api/student-lineages*` 全部 404 `lineage_disabled`；所有新增过滤条件**不生效**；写侧不要求 lineage；既有 SQL 与响应**逐字节不变**。
- **on**：新接口可用 + 老师端强制过滤 + 写侧强制 lineage + 模板侧转新校验。
- 灰度顺序：迁移先上（flag off，零行为变化）→ 代码上（flag off）→ 单老师 lab 打开 → 观察 → 全量（§10）。

---

## 5. 边界与风险

### 5.1 已知边界：后端没有鉴权（必须写明，避免误判隔离强度）

**事实**：全库唯一凭据是 DeepSeek `api_key`；无 `Authorization` 头校验、无依赖注入的 `current_user`、无会话；老师身份 = 前端传参 `teacher_name`（Epic 2 §1.2 已明示「`teacher_name` 即身份，不引登录体系」）。

| 能力 | Epic 4 能否做到 |
| :---- | :---- |
| **能防** | ① 同一客户端**切错师门**（前端状态 + 后端过滤）；② **服务端漏过滤**（SQL 强制带 `lineage_id`，漏传即 4xx 而非全量）；③ 越权**留痕**（`agent_action_log` / 后续审计） |
| **防不住** | 直连 `127.0.0.1:8000` 伪造 `teacher_name` / `lineage_id` 的调用者（**本 Epic 不引入登录体系，此边界在阶段一内不可能消除**） |
| **必须做**（在此边界内的最低限度） | 服务层**存在性 + 归属**双校验（老师∈师门、学生∈师门），而不是「只要参数带了就放行」；写侧缺 lineage 一律 4xx；flag off 时为**零行为变化** |

### 5.2 漏改即越权的查询（按危险度排序）

| # | 风险 | 后果 | 依据 |
| :-- | :---- | :---- | :---- |
| 1 | `/api/patient-records` 的 `teacher_name` 可空 | 该患者**全部老师**的病历外泄 | `database.py:899`（参数可空） |
| 2 | `/api/drafts` 的 `teacher_name` 可空 | **全库**患者的未签草案外泄 | `database.py:804`（参数可空） |
| 3 | 智能体三扫描（`/api/agent/scan`、复诊提醒、欠费提醒） | 为**别师门**学生生成请示 / 提醒（脏**写**，不只是泄露） | `agent.py:685-695`、`:639-683`、`:583-619`（只看 `pt.status='active'`） |
| 4 | 指标口径（`get_draft_samples` / 记录样本 / stage log stats） | 阶段评估读进别师门样本 → 阶段误判（**最隐蔽**：不报错、不泄露，只是结论错） | `database.py:2082/:2096/:2195` |
| 5 | 其余 P1 读点 | 单类数据泄露 | §3.2 P1 清单 |
| 6 | 前端**切错师门**（后端已挡则为空/4xx） | 展示错数据 | §7 |

> 施工判据：**「漏改」的表现必须是 4xx，而不是「返回全量」**（§4.1 的 `lineage_required` 就是为此存在）。

### 5.3 边界声明：阶段是老师的能力画像，不是师门的资产（裁决③）

- `agent_stage_state` 保持 **`teacher_name` 单列 PK**（一位老师一行）；`lineage_id` 列保留但**恒 `''`**，不参与过滤、不参与唯一性。
- **不**重建该表、**不**改 `upsert_agent_stage_state` 的字段口径、**不**动 3.4-c 的**唯一向上写路径**及其守护用例（⑱ 组：`stage=` 写点恰 3 处、写前现场校验 `to_stage == _next_stage(current)`）。
- `agent_stage_log` 补 `lineage_id`（裁决③-C）：**只作审计标注**——写侧尽力带上当时上下文；读取与统计**不按 lineage 过滤**（沿用既有 action log / stats 口径）。
- 落地含义：同一老师在多个师门之间**共享同一阶段**；师门**不**产生独立阶段画像。若未来白皮书明确要求「一师多门、独立阶段」，需**单独立项**（整表重建 + 回改 ⑱ 守护用例 + 重新验收 0003）。
- 违反本声明的典型误写：给 `agent_stage_state` 的查询加 `lineage_id = ?`、给 `stage` 升级逻辑加「按师门各算一次」。

### 5.4 默认师门污染高危点

| # | 危险动作 | 禁令 / 对策 |
| :-- | :---- | :---- |
| 1 | 用 `''` 表示默认师门 | 禁止（裁决②）；默认师门一律显式 `lin-*` |
| 2 | 写侧 `COALESCE` / 兜底成默认师门 | 禁止；缺 lineage → 4xx（§2.4 纪律 1） |
| 3 | `teacher_add_student` 的 `except sqlite3.IntegrityError: pass`（`:512-513`） | flag on 时改为「已存在则更新 `lineage_id`/`status`」；flag off 保持原状 |
| 4 | 回填时把「找不到映射」的行硬塞进默认师门 | 禁止：留 `''` + 出清单（§6.2） |
| 5 | 给列表加了过滤、却漏了同表的**统计**（或反之） | §3.2 把列表与统计列在**同一张清单**，就是为了防这种反向漂移 |
| 6 | 把默认师门 id 写成代码常量 | 禁止：id 由 `slugify(teacher_name)` **计算**得出，不落常量 |

### 5.5 双主权对 Epic 4 的约束（自检清单，每个施工步骤收口时逐条过）

| # | 检查 | 判据 |
| :-- | :---- | :---- |
| 1 | 患者数据主权 | 导出 / 删除路径**不**新增 `lineage_id` 前置条件 |
| 2 | 归属 ≠ 所有权 | 代码与注释**不得**把 `lineage_id` 表述为「所有权 / 归属某人」 |
| 3 | 退出不丢数据 | 退出后行仍在（`status='inactive'`），学生端仍可读自己的病历 |
| 4 | 知识产权归老师 | 老师可带走知识（模板 / 施治经验）；模板导出**不得**含患者标识 |
| 5 | 平台不拥有数据 | 不得新增跨师门的**平台侧**聚合（唯一例外 = 治理见证入口，独立子任务、只读） |

---

## 6. 迁移 `0005`（Epic 4 step 4.1）

### 6.1 upgrade（七步，全部幂等）

| 步 | 动作 | 要点 |
| :-- | :---- | :---- |
| ① | `CREATE TABLE IF NOT EXISTS lineage` + `idx_lineage_owner` | DDL = §2.1；**本迁移即 DDL 唯一真相源** |
| ② | `CREATE INDEX IF NOT EXISTS idx_patient_teachers_lineage` | §2.5 建议索引 |
| ③ | 种子默认师门 | `INSERT ... SELECT ... FROM teachers`：`id='lin-'+slug(name)`、`name=name+'師門'`、`owner_teacher_name=name`、`status='active'`。**slug 由 Python 侧算**（SQLite 无 slugify；`sha1` 回落同理），逐老师生成后 INSERT；真机 1 位老师 → 1 行 |
| ④ | 业务表补 `lineage_id` 列（12 张） | §2.3「必须」清单：`drafts、patient_records、complaints、appointments、prescriptions、homework、transcriptions、record_tags、agent_tasks、agent_action_log、agent_stage_log、patient_teachers`；一律 `PRAGMA table_info` 探测 + `ADD COLUMN lineage_id TEXT NOT NULL DEFAULT ''`（可重跑，沿用 0002 口径） |
| ⑤ | 存量回填（显式 UPDATE，幂等） | §6.2 |
| ⑥ | 收尾计数校验 | 迁移内 `assert`：应回填行数 == 实回填行数；不符 → 抛异常、整 revision 回滚（沿用 0001 口径） |
| ⑦ | 纪律：不动任何已验收对象 | 不 ALTER `agent_stage_state`（裁决③-A）、不重建任何表、不改 `templates` 既有 3 个索引、不碰 `plan_templates` 数据（§2.3） |

### 6.2 存量回填（真机基线，可枚举）

真机基线（只读实测 2026-09-29；Epic 4 开工时 `alembic_version` 应为 `0004`，即 step 3.5 之后）：`teachers = 1`（李老师）、`patients = 10`、`patient_teachers = 10`（全 `active` → 李老师）、`templates = 5`（`lineage_id` 全 `''`）、`patient_records = 4`、`drafts = 1`、`plan_templates = 1`、`agent_tasks = 5`。

| 表 | 回填规则 | 预期行数（真机） |
| :---- | :---- | :---- |
| `lineage` | 每老师一行（⑥ 之外：步骤 ③ 种子） | 1 |
| `patient_teachers` | 按 `teacher_name` → `owner_teacher_name` 映射 | 10 |
| `templates` | 按 `teacher_id` → `owner_teacher_name` 映射 | 5 |
| `patient_records` / `drafts` / `agent_tasks` | 按 `teacher_name` 映射 | 4 / 1 / 5 |
| `plan_templates` | **不回填**（A1 裁决：不补列、不师门化 → 无列可填；缺口见 TD-005） | — |
| `agent_*` 其余表 | 按 `teacher_name` 映射（有行才回填） | 依实表 |
| 找不到映射的行 | **留 `''`** + 打印清单 | 预期 0 |
| 空值兜底 | **禁止** `COALESCE(..., 'lin-...')` | — |

回填 SQL 形状（每表一条，幂等、可重跑）：

```sql
UPDATE patient_records
   SET lineage_id = (SELECT id FROM lineage
                      WHERE owner_teacher_name = patient_records.teacher_name)
 WHERE lineage_id = ''
   AND EXISTS (SELECT 1 FROM lineage WHERE owner_teacher_name = patient_records.teacher_name);
```

> **step 4.1 实测补充（2026-09-29）**：
> ① **计数校验分两级**（CTO 放行约束 2）：级 1 = 每表「应填 == 实填」（不符即抛错）；级 2 = 当 5 张核心表的**整表行数**命中真机签名（`teachers` 1 / `patient_teachers` 10 / `templates` 5 / `patient_records` 4 / `drafts` 1）时，再断言「回填后已归属行数」= 10 / 5 / 4 / 1 与 `lineage` 行数 = 1。签名不匹配时只跑级 1 并打印提示（避免在非真机库误报中止）。
> ② **「整 revision 回滚」的实际语义** = `alembic_version` 停在 0004 + 业务数据零变更；本机 SQLAlchemy / pysqlite 默认隔离级别下 **DDL 不在事务内**（`CREATE TABLE` / `ADD COLUMN` 不受回滚保护，已实测留证），空的 `lineage` 表与 `lineage_id` 列会残留 —— 由 `0005` 自身的幂等探测在下一次 `upgrade` 时吸收（修好触发条件后重跑即收敛，已用用例固定）。若要把 DDL 也纳入回滚，需改 `alembic/env.py` 的事务接入方式 —— **CTO 2026-09-29 裁决②：不立项**，已登记 `docs/tech-debt.md` **TD-006**；触发条件 = 出现**真实 DDL 残留导致的生产事故**再立项。
> ③ **§6.1 的 ②（建索引）与 ④（补列）次序微调**：SQLite 不允许在尚不存在的列上建索引 → 实际执行「补列 → 建 `idx_patient_teachers_lineage`」，最终结果与 §6.1 一致。
> ④ **§6.4「重复执行第二遍不报错」的边界**：SQLite 无 `ADD COLUMN IF NOT EXISTS`，故离线产物第二遍会在 `ADD COLUMN` 段报 `duplicate column name`（已实测）；**跳过该段后**（种子 `INSERT ... WHERE NOT EXISTS` + 回填 `UPDATE ... WHERE lineage_id = ''`）重复执行不报错、行数不变（已实测幂等）。

### 6.3 downgrade（统一口径，裁决④）

- **只回收结构，不删业务列**：`DROP INDEX idx_patient_teachers_lineage` → `DROP TABLE lineage`（其索引随表消失，仍显式先 drop 一遍，沿用 0001 口径）。**不** `DROP COLUMN` 任何 `lineage_id` —— 12 张表的列回退后**保留**，值保留。
- **安全闸（沿用 0003 口径）**：若 `lineage` 行数 > 老师数（= 已有老师自建 / 多师门数据），或 `patient_teachers` 存在 `lineage_id` 非空且 `status='inactive'` 的退出记录 → **抛异常中止 downgrade**，提示先导出（`GET /api/lineages` 与相关列表）或改用 flag 回退。
- **口径一致性**：本口径与 `docs/tech-debt.md` TD-003 的 §0 总表行、§3「CTO 裁决」行**逐字一致**（三处同句）。
- ⚠️ 0004 是**已存在例外**（逐列 `DROP`），**不追溯修改**（TD-003 已记）。

### 6.4 离线 SQL 产物与可重跑

| 项 | 口径 |
| :---- | :---- |
| 产物 | `docs/migrations/0005_add_lineage.sql`（upgrade 段 + downgrade 段 + 幂等说明），沿用 0002 / 0003 / 0004 的老规矩 |
| 生成方式 | 由迁移内联 SQL **逐句导出**（不重写一遍），人工核对句序 |
| 判据 | 在**副本库**（`backend/zhiheng.db.bak-*` 复制出临时文件）上 `sqlite3 < 0005_add_lineage.sql` 跑通；重复执行第二遍**不报错、不改行数** |
| 不进仓库 | 备份与临时副本（`.gitignore` 已含 `backend/zhiheng.db.bak-*`） |

### 6.5 真机升级窗口（沿用 CTO 裁决③ 的备份纪律）

1. **强制先备份**：`backend/zhiheng.db` → `backend/zhiheng.db.bak-20260930`（**不进仓库**；Epic 2 step 3.5 同款纪律）。
2. `alembic upgrade head` → `alembic current` 应为 `0005_...`。
3. `PRAGMA table_info(<表>)`：§2.3「必须」的 12 张表都能看到 `lineage_id`；`lineage` 表 1 行（真机 1 位老师）。
4. §6.2 计数校验：`patient_teachers` 10 行回填、`templates` 5 行、`patient_records` 4 行、`drafts` 1 行；**孤儿行 = 0**。
5. flag 保持 off 跑一遍既有回归（`pytest backend -q`）→ 全绿；再开 flag 做 lab 验证。

---

## 7. 前端（`App.tsx` 单文件 SPA）

### 7.1 两个维度并存（裁决⑥）

| 维度 | 载体 | 语义 |
| :---- | :---- | :---- |
| **人的维度（既有，保留）** | 「我的老師（n/3）」列表 | 老师关系：加入 / 退出某位老师 = 加入 / 退出**其师门** |
| **组织维度（新增）** | 「我的師門」视图 + 切换器 | 师门关系：当前师门上下文、跨门只读汇总 |

- **同源**：两个列表的数据都来自 `GET /api/student-lineages`（= `patient_teachers` 升级版），**不新增第二套后端真相**（与裁决①的「不许两处真相」同款纪律）。
- 阶段一一师一门 → 「3 位老师上限」= 「3 个师门上限」，两个维度数值一致、不会出现「老师满了、师门没满」的矛盾态。
- **UI 文案一律繁体古字**（Epic 1 §13.4 / 决策 11），草案：`🏯 我的師門`、`切換師門`、`本門病歷`、`全部師門（彙總）`、`退出師門`、`未歸屬`；退出确认文案：「退出後老師將看不到你在本師門的資料，**資料不會被刪除**」（把 §1.4 的承诺写进 UI）。

### 7.2 老师端（阶段一 = 无切换器）

| 项 | 口径 |
| :---- | :---- |
| 当前师门 | 登录态（前端本地 `teacher` 状态）后拉 `GET /api/lineages?teacher_name=` → 取唯一一行存 `selectedLineage` |
| **不提供切换器** | 阶段一一师一门 → 老师端**没有**切门动作 = **直接消除最大的越权源**（「切错师门」在老师端不存在） |
| 读请求 | 所有 §3.2 的 read 调用自动带 `lineage_id`（集中在一处拼参，避免散落漏传） |
| 展示 | 侧栏或设置区显示「目前師門：<name>」（只读展示）；`status='archived'` → 顶部提示条 |
| flag off | **不渲染任何师门 UI**，请求**不带** `lineage_id`（§4.4 零行为变化） |

### 7.3 学生端

| 项 | 口径 |
| :---- | :---- |
| 师门视图切换 | `本門` / `全部師門（彙總）`；切换 = 换 `lineage_id` 上下文 → **先清场再重拉**（防陈旧数据串门） |
| 「我的老師（n/3）」 | **保留**；上限文案由「3 位老師」改为「最多 3 個師門」（数值语义不变，措辞对齐师门口径） |
| 退出师门 | 两步确认（二次确认 + 副作用明示）→ `DELETE /api/student-lineages` → 成功后刷新两个列表 |
| 未归属数据 | flag on 时**不显示**（§2.4 纪律 2）；学生侧若存在 `''` 行 → 提示「未歸屬資料請聯絡管理員」 |
| 汇总 | 只读卡片（各师门就诊数 / 未签草案数 / 最近活动）；**不**做单一等级 |

### 7.4 验收手段受限（沿用既有约束，必须写明）

- 前端**无测试框架**（无 vitest / jest）→ 验证 = `npx tsc --noEmit` + `npm run build` + **手动清单**。
- 手动清单（5 条，必须逐条留证）：
  1. 学生加第 4 个师门 → 出现上限拒绝文案，且库内无新行；
  2. 学生切换师门 → 列表**清场**后只显示本门数据（无上一门残留）；
  3. 学生退出师门 → 老师侧该学生不可见，**学生侧数据仍在**（可读自己的病历）；
  4. flag on 时 `''` 未归属行**不显示**；
  5. flag off → 无任何师门 UI，请求 URL 中**无** `lineage_id`（网络面板核对）。

### 7.5 学生自加 vs 老师拉入的账号语义差异（step 4.4 追加；§3.4 表格第 2 行的口径细化）

> 编号说明：本小节在 step 4.4 收口计划中拟编号 **§7.4**，但 §7.4 已被「验收手段受限」占用（且 §8 ⑪ 组按编号引用它），为避免同号两节，故顺延为 **§7.5**。

同一条接口 `POST /api/student-lineages`（`lineage_service.join_student_lineage()`，`lineage_service.py:754-800`）承载两种语义，**分岔键 = `teacher_name` 是否为空**（`:778`）：

| 维度 | **学生自加**（`teacher_name` 空） | **老师拉入**（`teacher_name` 非空） |
| :---- | :---- | :---- |
| 入口 | 学生端「📇 我的老師」加入（`App.tsx:2090 handleAddTeacher` → `joinLineageByTeacher` `:691-710`），请求体只有 `{student_name, lineage_id}` | 管理端 / 老师端直连接口，带 `{student_name, lineage_id, teacher_name}`；**前端目前无入口**（见下「现状缺口」） |
| `patients` 账号 | **不建**（本接口不碰建号，避免与邀请码 / 老师拉入形成第二套建号实现） | **建**（复用既有 `database.teacher_add_student()`，`database.py:532-547`，语句一字不改：`INSERT OR IGNORE INTO patients(guardian_name='self', relation='本人')`） |
| 积分账户 | 不动 | `INSERT OR IGNORE INTO points_accounts`（初始 100 分，同上函数第 3 步） |
| 归属行 | 唯一写点 `_upsert_membership()`（`:712-751`）：先 `UPDATE`，`rowcount == 0` 才 `INSERT` | 同左：`teacher_add_student()` 顺手插的那行（`lineage_id=''`）被紧接着的 `_upsert_membership()` **就地更新**到本师门 → 归属行始终只有一个写点 |
| 额外校验 | 无 | 多一道 403 `lineage_forbidden`（`:786-789`：该老师必须是本师门 owner） |
| 共同校验（顺序） | `lineage_gate()` → 名字 / id 形状 → 404 `lineage_not_found` → 400 `lineage_invalid`（已封存）→ 409 `student_lineage_limit`（`:704-709` 在**任何写入之前**计数，拒绝时库内零新行） | 同左 |
| 幂等 | 已在同门（`active` 且 `lineage_id` 相同）→ `changed=false` 且零写入 | 同左 |

三条必须写明的推论：

1. **「学生自加不建账号」≠「学生没有账号」**：学生账号由既有两条路径产生 —— 邀请码（`database.accept_invite()`，`database.py:1014-1024`）或老师拉入（`teacher_add_student()`）。本接口只负责归属行，故 flag on 与否都不改变「账号从哪来」的既有口径。
2. **两种语义的可见性后果完全相同**：老师端能否看见该学生，取决于 `patient_teachers(status='active', lineage_id=本门)`，**不**取决于账号由谁创建（§3.1「归属 = 访问范围，不是所有权」）。
3. **`''` 行的处置仍按 §2.4 纪律 2**：任何绕过本接口写入的归属行（含旧入口）都是「未歸屬」，flag on 下对任何师门都不可见、只给提示（学生端文案 `App.tsx:3139-3142`）。

**现状缺口（必须留痕，属待批子步）**：老师端「👥 學生管理」的新增学生按钮仍走**旧路径** `POST /api/teacher/add-student`（`App.tsx:3192` → `database.teacher_add_student()`，**不写** `lineage_id`），邀请码接受（`POST /api/invites/accept`）同理 —— 这两条路径产出的归属行 `lineage_id = ''`，flag on 下即「未歸屬」：老师端读路径按师门过滤后**看不到**该学生，学生端只显示「未歸屬資料請聯絡管理員」。后端**已备好**老师拉入分支（`lineage_service.py:762-766` 已披露「§4.3 歸屬組的 flag on 改造屬待批子步」），前端尚未接入口。自测 / 演示时请留意：用旧入口加完学生后，需再走一次师门加入（或直连接口带 `teacher_name`）才会落进本门。

---

## 8. 测试矩阵

统一纪律（沿用 Epic 1 §14 / Epic 2 §9）：**先红后绿**；每组用例都要能在 **flag off / flag on 两态**分别给出结论；flag off 的断言用「语句序列 / 响应**逐字节**一致」，不用「行为差不多」。

| 组 | 名称 | 关键用例 | 断言 |
| :-- | :---- | :---- | :---- |
| ① | `0005` upgrade | 空库；真机副本；重复执行第二遍 | `lineage` 表 + `idx_lineage_owner` 存在；§2.3「必须」的 12 张表都有 `lineage_id`；`lineage` 行数 = 老师数（真机 1）；回填计数 = §6.2 预期；第二遍无变化、不报错 |
| ② | `0005` downgrade | 常规；有「多师门行」时；有 `inactive` 退出记录时 | ① `lineage` 表与 `idx_patient_teachers_lineage` 消失；② 12 表 `lineage_id` **仍在且值不变**（裁决④）；③ 有退出/多门数据 → `pytest.raises` 中止 |
| ③ | flag off 零行为变化 | 老师端读接口全量；写接口；模板四入口；智能体三扫描 | 语句序列 / 响应 JSON 与 Epic 4 之前**逐字节**一致（快照比对）；模板传非空 `lineage_id` 仍 400 `lineage_not_supported` |
| ④ | 新接口功能 | 7 端点 happy path（flag on） | 200 + 字段形状；落库校验；`lineage_invalid` / `student_lineage_limit` 可触发 |
| ⑤ | 隔离正确性（**核心**） | 两老师 × 两师门 fixture：逐 §3.2 P0/P1 各走一遍；`teacher_name` 空；跨门 `lineage_id`；不存在的 id；`''` 行 | 返回行集合与「直接 SQL 按 lineage 过滤」**完全一致**；不存在「4xx 之外的静默全量」 |
| ⑥ | 归属生命周期 | 加入 → 退出 → 再加入；第 4 个师门；老师拉入已存在学生 | `status` 迁移正确；**数据行不删**（病历仍在）；上限 409；再加入回 `active`（§5.4-3 的更新分支） |
| ⑦ | 模板线 | 四入口 × {合法/缺/越门/不存在}；跨门两条 active 共存；智能体取模板 | `uq_templates_active_one` 生效；`get_active_template` 调用点不漏传 lineage（调用点清单断言） |
| ⑧ | 阶段边界（裁决③守护） | `PRAGMA table_info(agent_stage_state)`；全行 `lineage_id=''`；`stage=` 写点计数；`agent_stage_log` 写入带 lineage 但 stats 不受影响 | ① PK 仍为 `teacher_name`；② 沿用 Epic 2 ⑱ 组既有断言**必须全绿**（本 Epic 不改这两处代码） |
| ⑨ | 默认师门与 slug | 种子 id 可复现；中文名 / 重名 / 空名边界；缺 lineage 的写入 | 两次生成同一 id；缺 lineage 被 4xx 拦住且库内**无新行**；`grep` 断言无 `COALESCE(lineage_id` |
| ⑩ | 双主权自检 | 既有导出路径不带 lineage 不报错；模板导出字段白名单 | 不出现 `lineage_required` 类错误；导出内容**无患者标识**字段 |
| ⑪ | 前端 | `npx tsc --noEmit` + `npm run build` + §7.4 手动 5 条 | 零 TS 错误；手动 5 条逐条留证 |
| ⑫ | 全量回归 | `pytest backend -q` | 全绿（Epic 1 / 2 / 3 全量，含 `test_migrations.py`） |

> 收口必须给出的证据：③ 组的「语句序列快照」；⑤ 组的**两师门 fixture**（不许用「单老师 + 手工改库」代替）；② 组的 downgrade 中止异常堆栈。

---

## 9. 施工顺序（step 4.0 → 4.1 →（4.2 ∥ 4.3）→ 4.4）

| step | 内容 | 交付物 | 验收判据 | flag |
| :-- | :---- | :---- | :---- | :-- |
| **4.0** | 设计定稿（本文件） | `docs/epic4-lineage-design-v1.md` + 3 处文档回写 | 六裁决落点齐全；**零代码改动**（`git status` 仅 `.md`） | — |
| **4.1** | 迁移 `0005` + 离线 SQL | `backend/alembic/versions/0005_add_lineage.py`、`docs/migrations/0005_add_lineage.sql` | ① ② 组用例；真机备份 + upgrade + 计数校验（§6.5） | off |
| **4.2** | 后端隔离（读 / 写路径 + flag + 7 个新接口） | `database.py` / `main.py` / `agent.py` / 新 `backend/lineage_api.py` + `backend/test_lineage.py` | ③ ④ ⑤ ⑥ ⑨ ⑩ 组；flag off 逐字节一致 | off → on |
| **4.3** | 前端两维度并存 | `App.tsx` | ⑪ 组（`tsc` + `build` + 手动 5 条） | off → on |
| **4.4** | 收口：全量回归 + 文档回写 + lab 验证 | 回归报告 + `tech-debt.md`（如需新登）+ 本文件「施工记录」小节 | ⑫ 组全绿；§5.5 自检清单逐条留证 | on |

三条顺序纪律：

1. **4.2 ∥ 4.3 可并行**，但前端**不得**先于后端 flag on 上线（4.3 合并前 4.2 的 off 态必须已完成并回归）。
2. **4.0 的 §5.3 边界声明必须在 4.1 迁移落笔前已成文**（本文件已满足）。
3. **与治理见证入口互不误杀**：见证入口是**独立子任务**（Epic 4 之后、Epic 5 之前，技术决策 12），须另开 `mode=ro` 连接；Epic 4 **不为它预留**任何接口 / flag / 错误码，但**不得**关闭其通路（只读连接读 `lineage` + 业务表即可）。Epic 4 若改了某表结构，需在 4.4 收口时通知见证入口子任务（避免其只读视图字段错位）。

> **注（CTO 2026-09-29「step 4.1 放行」）**：4.1 的交付范围 = **迁移 `0005` + 离线 SQL + ① ② 组用例**；**真机备份 / `alembic upgrade head` / 计数校验（§6.5）推迟到放行后的单独窗口**执行，不属 4.1 交付（本步铁律：不跑 `upgrade head`、不动真机库）。另：真机库实测仍停在 `0002_add_draft_template_refs`（0003 / 0004 尚未落地），故真机窗口里的 `upgrade head` 会**一趟跑完 0003 → 0004 → 0005**，执行前请复核 0003 的 downgrade 安全闸与 §6.5 备份纪律。

---

## 10. 回退与灰度

### 10.1 三级回退（能关 flag 就不回退代码；能回退代码就不回退迁移）

| 级 | 动作 | 影响 | 前置条件 |
| :-- | :---- | :---- | :---- |
| 1 | 关 flag（`LINEAGE_ENABLED=off`） | **即时**回到零行为变化；不动数据、**不必重启**（flag 现读） | 无（任何时刻可做） |
| 2 | 回退代码（`git revert` 4.2 / 4.3 提交） | 新接口 404；数据里已有 `lineage_id` 值（**无害**：flag off 不读它） | 先关 flag |
| 3 | 回退迁移（`alembic downgrade 0004`） | `lineage` 表 + 索引消失；**12 表的 `lineage_id` 列保留**（裁决④）；有退出 / 多门数据 → **安全闸中止** | 先备份 + 先导出（§6.5 / §6.3） |

### 10.2 灰度

`迁移先上（flag off，零行为变化）` → `代码上（仍 off）` → `单老师 lab 打开` → `观察 24h`（隔离错误 / 4xx 计数 / 智能体三扫描是否越门）→ `全量 on`。

**回滚触发条件**（任一命中即关 flag）：⑤ 组用例在真机复现；出现「非 4xx 的越门数据」；智能体为别师门学生生成请示 / 提醒。

---

## 11. 不做的事（本 Epic 明确排除）

1. 登录 / 鉴权 / token（§5.1；阶段一内不可能消除的边界）。
2. 一师多门（阶段一硬约束：`lineage.owner_teacher_name` 唯一）。
3. 按师门分阶段 / 改 `agent_stage_state` PK（§5.3，裁决③-A）。
4. 段位系统（Epic 5 §D5）。
5. 引荐链 / 存活门限 / 协议底线（阶段三；R-009 / R-010 属此）。
6. 加密 / 思想指纹 / 监护模式（阶段二）。
7. 治理见证入口（**独立子任务**，Epic 4 之后、Epic 5 之前）。
8. 师门共用库存 / 财务（`herb_inventory` / `points_*` / `transactions`）。
9. 数据导出 / 删除的**实现**（阶段二；本 Epic 只保证不阻塞，§1.4）。
10. 患者标识与知识分离的实现（阶段二）。
11. 新 UI 框架 / 路由重构（沿用 `App.tsx` 单文件）。
12. `plan_templates` 的师门化（**A1 已裁决：不做** —— Epic 1 兼容镜像，本期不补列 / 不回填 / 不过滤；缺口登记 `docs/tech-debt.md` TD-005，触发条件 = 开放「一师多门」或白皮书要求旧接口过滤）。

> 纪律：任何被提及的新需求都要先回答「**这是 Epic 4 的职责吗？**」；不是 → 记进 `docs/backlog-white-paper-v2.1.md`，不在本 Epic 做。

---

## 附录 A 待 CTO 确认项（**不阻塞 step 4.1**）

| # | 事项 | 影响面 | 建议 |
| :-- | :---- | :---- | :---- |
| A1 | `plan_templates`（旧「施治模板」接口）是否也按师门过滤（§2.3） | 若是 → 4.1 迁移需多补一列 + 回填（**现在补最便宜**，之后补要再开一次迁移） | 建议：**不加**（Epic 1 §7.6 已定位兼容镜像；师门维度由单向双写的 `templates` 承载），并在 4.4 收口时复核 |
| A2 | `POST /api/lineages` 重复开山门的语义：409 还是幂等返回既有行（§4.2） | 只影响前端分支处理 | 建议：**幂等返回 200 + 既有行**（阶段一老师端无切换器，409 会造成「自己把自己锁住」的困惑） |
| A3 | 学生「切换师门视图」是否记住上次选择（`localStorage`） | 纯前端体验 | 建议：**记住**，key = `zh.lineage.<student_name>`；flag off 时不写任何 key |
| A4 | `development-plan-v1.md` §5 标题「立即 5 个 epic issue」与「治理见证入口」是否注册为 D6 / 加 §3.4 验收列 | 仅口径与编号 | 建议：标题保持不动（避免改已验收编号）；见证入口不进 D 序列，作为独立子任务行 |
| A5 | 师门中文名默认值（`<老师名>師門`）是否可编辑 | 若可编辑 → 4.2 需加 `PATCH /api/lineages/{id}`（当前**不提供**） | 建议：阶段一**不可编辑**（`name` 仅创建时定；改名走「归档 + 新建」，避免 id 与语义漂移） |

**批复结果（CTO 2026-09-29，逐条）**：

| # | 裁决 | 落地 |
| :-- | :---- | :---- |
| A1 | **不加**（`plan_templates` 不师门化） | 本文 §2.3 / §6.2 / §11-12 已改口径；缺口登记 `docs/tech-debt.md` **TD-005** |
| A2 | **幂等**（重复开山门 → 200 + 既有行，不用 409） | 属 step 4.2 服务层（`POST /api/lineages`）；本步（4.1）不动 |
| A3 | **记住**（`localStorage`；flag off 时**不写**任何 key） | 属 step 4.3（`App.tsx`）；本步（4.1）不动 |
| A4 | `development-plan-v1.md` §5 标题**保持不动**；「治理见证入口」**维持独立子任务行**（不进 D 序列） | 无需文档改动（已与现状一致） |
| A5 | 阶段一**不可编辑**（改名 = 归档 + 新建；**不**提供 `PATCH`） | 属 step 4.2；本步（4.1）不动 |

## 附录 B 施工记录（每步完成后追加一行）

| step | 日期 | 交付物 | 判据结果 | 备注 |
| :-- | :---- | :---- | :---- | :---- |
| 4.0 | 2026-09-29 | 本文件**新建**；`development-plan-v1.md`（§3.3-D4 + §5-Epic 4）、`tech-debt.md`（TD-003）回写 | **零代码改动**（`git status` 仅 `.md`：新建 1 + 修改 3） | 六裁决逐条落地；R-009 / R-010 / 技术决策 12 已在上一步落盘 |
| 4.1 | 2026-09-29 | `backend/alembic/versions/0005_add_lineage.py`（**新**）；`docs/migrations/0005_add_lineage.sql`（**新**，193 行）；`backend/test_migrations.py`（**+10 用例**）；`backend/test_agent_stage.py`（**1 处断言同步**，见备注⑦）；`docs/tech-debt.md`（**TD-005**）；本文件（§2.3 / §6.2 / §6.3 实测补充 / §9 注 / §11-12 / 附录 A 批复 / 本表） | **先红后绿**：0005 组用例先红（`9 failed / 10 deselected`，`no such table: lineage`）→ 迁移落地后 `10 passed / 10 deselected`；离线产物回放三项实测通过（见下） | **未跑真机 `upgrade`、未动真机库**（`backend/zhiheng.db` sha256 前后不变）；真机备份 / upgrade / 计数校验按 §9 注推迟到单独窗口 |

> 4.1 实测备注（证据留痕）：
> ① **先红**：迁移未落地时 `pytest backend/test_migrations.py -q -k 0005` = `9 failed / 10 deselected`（`sqlite3.OperationalError: no such table: lineage` / 断言失败）；
> ② **后绿**：迁移落地后同一命令 = `10 passed / 10 deselected`（含新增的「离线产物与迁移内联常量逐字一致」用例）；
> ③ **离线产物回放**（在「真机副本 → `alembic upgrade 0004`」上进行；本机无 `sqlite3` CLI，故以 Python `sqlite3.executescript` 等价复现 §6.4 判据）：
>    第一遍 → `version = 0005_add_lineage`、`lineage` 1 行（`lin-ua8739bc7` / `李老师師門` / `李老师` / `active`）、`idx_lineage_owner` + `idx_patient_teachers_lineage` 就位、12 张表都有 `lineage_id`、已归属行数 **10 / 5 / 4 / 1**、`plan_templates` **无** `lineage_id`；
>    第二遍（原样）→ 预期报 `duplicate column name: lineage_id`；第二遍（跳过 `ADD COLUMN` 段）→ 状态与第一遍**逐字段一致**（幂等）；
> ④ **产物生成只读**：`--sql` 生成前后，真机库与副本库的 sha256 **均未变化**（离线探测只读，不写库文件、不建 journal）；
> ⑤ **回填计数校验**：真机签名命中时断言 1/10/5/4/1，不符即抛错（「孤儿行」用例已验证：版本号停在 0004 + 业务数据零变更，修正数据后重跑收敛到 0005）；
> ⑥ **downgrade**：只 `DROP` `lineage` 表与 2 个索引，12 张表的 `lineage_id` 列与值**全部保留**（裁决④）；两道安全闸（师门数 > 老师数 / 有已退出师门记录）用例验证会中止并提示先导出。
> ⑦ **Epic 2 既有守护用例的同步（唯一一处，已披露）**：`backend/test_agent_stage.py::test_whitelists_match_migration_0003_columns` 原本断言 `agent_stage_log` 的列集合**恰好** = `AGENT_STAGE_LOG_INSERT_FIELDS | {id, teacher_name, event_type}`；`0005` 按裁决③-C 补 `lineage_id` 后该断言必然失效（首轮全量回归实测 `1 failed / 407 passed`）。已把期望集合显式加上 `lineage_id`（**唯一白名单外例外**，其余仍逐列严格相等）。`AGENT_STAGE_LOG_INSERT_FIELDS` 常量、`agent_stage_state` 的断言、以及 Epic 2 ⑱ 组的 `stage=` 写点守护**一字未改**。

## 附录 C 上游依据文件（引用不复制）

| 来源 | 引用点 |
| :---- | :---- |
| `docs/backlog-white-paper-v2.1.md` | §4.2 多师原文、§1.2 双主权原文（本文 §1.3 / §1.4）；R-009 / R-010 |
| `docs/development-plan-v1.md` | §3.3-D4、§5-Epic 4、技术决策 3（AI 三铁律）/ 5（哈希口径）/ 11（繁体 UI）/ 12（治理见证入口） |
| `docs/epic1-template-design-v1.md` | §1.1（DDL 唯一真相源 = 迁移）、§1.3（索引克制）、§1.4（零 FK/CHECK）、§7.6（兼容镜像）、§10.1（错误码与「无 DELETE」）、§13.4（繁体 UI） |
| `docs/epic2-agent-stage-design-v1.md` | §1.2（`teacher_name` 即身份）、§2.1（AI 三铁律）、§9（测试纪律）、⑱ 组（`stage=` 写点守护） |
| `docs/tech-debt.md` | TD-003（downgrade 统一口径，裁决④） |
| Epic 3（施工中） | `agent_learning_events` 哈希快照口径 —— 见证入口的「证据模式」复用该口径（独立子任务时引用，本 Epic 不动） |
