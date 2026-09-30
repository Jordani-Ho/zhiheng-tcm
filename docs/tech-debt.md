# 知衡社区 · 技术债登记册

版本：v1.0
日期：2026-09-28
范围：**只登记、不修缮**。每条债务都必须写明「为什么现在不修」与「将来怎么修」，避免在施工步内顺手重构。
登记纪律：只在**收口回归步**（如 Epic 2 step 2.6）追加条目；条目一经登记，改动它需要单独提交 + 单独立项。

---

## 0. 登记总表

| 编号 | 名称 | 归属 | 位置 | 等级 | 本 Epic 处置 |
| :---- | :---- | :---- | :---- | :---- | :---- |
| TD-001 | `_drafts_supports_template_refs()` 未收敛到 `_table_has_columns()` | Epic 1（已验收） | `backend/database.py:645-651` | 低 | **不动**（Epic 2 不碰 Epic 1 已验收代码） |
| TD-002 | `resolve_agent_task()` 中 approved + 非对象 JSON 的既有 `AttributeError` | 存量（Epic 2 之前） | `backend/database.py:1697-1703` | 中低 | **不修**（「既有语义一字不改」原则） |
| TD-003 | 迁移回退口径：**全库已统一为「downgrade 不删业务列，只回收结构（表、索引）」**；0004 为**已存在例外**（不追溯修改） | Epic 2 迁移层（0004 按 CTO 裁决 A1 落地）→ **Epic 4 迁移层（0005 起执行新口径）** | `backend/alembic/versions/0004_add_patient_record_template_refs.py`（**例外**）；`backend/alembic/versions/0005_*.py`（**新口径**） | 低（方向已裁决、口径已定） | **不动 0004**；Epic 4 的 `0005` 按新口径实施（downgrade 只回收新增表与索引，`lineage_id` 等业务列回退时**保留**） |
| TD-005 | `plan_templates` 未按师门过滤（Epic 1 兼容镜像，未师门化） | Epic 1 兼容镜像 → **Epic 4 明确不师门化**（CTO 2026-09-29 裁决 A1） | `backend/database.py:372-381`（建表 + 旧「施治模板」入口）；`backend/alembic/versions/0005_add_lineage.py`（**不补列 / 不回填 / 不过滤**，见 §4） | 低（阶段一「一师一门」下不产生越权） | **不动**（不加 `lineage_id`）：它是 Epic 1 兼容镜像、已被 `templates` 取代；触发条件 = 开放「一师多门」或白皮书要求旧接口按师门过滤，届时单独立项 |
| TD-006 | `alembic/env.py` 未做 DDL 事务化 → **DDL 不在事务内**（结构残留由幂等探测吸收） | 迁移层（**Epic 1 起既有**，非 Epic 4 引入） | `backend/alembic/env.py:51-72`（在线模式 `transaction_per_migration=False` + 「SQLite 3.49 支持 DDL 事务」注释）；`backend/alembic/versions/0005_add_lineage.py`（依赖幂等探测吸收残留） | 低（无数据面缺陷） | **不动**（CTO 2026-09-29 裁决②：**不立项**）；触发条件 = 出现**真实 DDL 残留导致的生产事故** |
| TD-007 | `plan_templates` 未按师门过滤（Epic 1 兼容镜像）—— **step 4.4 收口复核留痕**（同源：TD-005） | Epic 1 兼容镜像 → Epic 4 **step 4.4 收口复核：维持「不加」** | `backend/database.py:2342-2371`（旧读 / 写通道）；`frontend/src/App.tsx:773`（前端唯一读取点） | 低（同上：阶段一「一师一门」下不产生越权） | **不动**：4.4 复核未出现 TD-005 的触发条件；**处置一律以 TD-005 为准**（本条只留「收口已复核」的痕迹，不重复处置） |
| TD-008 | 后端**无鉴权** → lineage 隔离只能防「同客户端切错师门」与「服务端漏过滤」，**防不住直连伪造 `teacher_name`** | 全库既有架构（Epic 1 之前既存，**非 Epic 4 引入**） | 全部路由（`backend/main.py` / `template_api.py` / `lineage_api.py`）；隔离判定入口 `backend/lineage_service.py:272`（`lineage_read_scope`）、`backend/template_api.py:98-109`（`_check_lineage`） | 中高（安全面）：从「隔离强度」看属根本缺口，从「本 Epic 范围」看属既有边界 | **不修**（登记留痕）：无鉴权 = 全库架构级改造，远超 Epic 4 范围；设计 §5.1 已明文声明该边界 |

> 登记例外：TD-003 由 CTO 2026-09-28 裁决③ 指令于 **Epic 2 step 3.1** 提前登记（一般纪律是「只在收口回归步登记」）。
> 本条**只登记、不在 step 3.1 内修缮** —— 请 CTO 在 step 3.6 收口时复核是否需要调整等级 / 处置。
> **2026-09-29 CTO 裁决④（Epic 4 step 4.0 放行时给出）**：口径已定 —— 全库**统一**为「downgrade **不删业务列**，只回收结构（表、索引）」；**0004 为已存在例外，不追溯修改**（不改其 `downgrade()`、不改其离线 SQL、不改其往返断言）；**Epic 4 的迁移 `0005` 采用新口径**。本条**等级维持「低」**，处置已从「待裁决」转为「已裁决，实施随 0005 落地」，详见 §3 表格内的「CTO 裁决」行与「将来怎么修」行。
>
> 登记例外：TD-005 由 CTO 2026-09-29「step 4.1 放行」指令于 **Epic 4 step 4.1** 登记（同为提前登记）。登记理由：`plan_templates` 的师门化在 step 4.0 附录 A-A1 被提出、当次裁决为「**不加**」，故该缺口必须留痕，否则后续「为什么旧施治模板接口不过滤师门」将无据可查。**只登记、不在 4.1 内修缮**。
>
> 登记例外：TD-006 由 CTO 2026-09-29「真机升级窗口放行」指令登记（同为提前登记，不进收口步）。登记理由：`docs/epic4-lineage-design-v1.md` §9 注② 在 step 4.1 实测发现「DDL 不在事务内、结构残留不随回滚消失」，该事实必须留痕（否则后续「为什么退回后还留着空表 / 空列」无据可查）。**只登记、不在 4.1 / 升级窗口内修缮**；裁决为**不立项**，触发条件见本条「等级 / 风险」行。
>
> 登记例外：TD-007 / TD-008 由 CTO 2026-09-29「**step 4.4 收口**」指令登记（**收口回归步，正合登记纪律**，非例外）。TD-007 与 **TD-005 同源**（设计 §2.3 / 附录 A-A1「在 4.4 收口时复核」）：本步已复核并维持「**不加**」，故本条**不重复处置**、处置以 TD-005 为准。TD-008 是本 Epic 唯一新增的「安全性边界」条目 —— 登记理由是「师门隔离」四个字极易被读成安全边界，必须与设计 §5.1 一起读。
> 编号说明：step 4.4 计划中原拟「TD-007 = `plan_templates`、TD-008 = 无鉴权」；因 **TD-005 已占用 `plan_templates` 主题**，为守「同一主题只有一条处置」的纪律，TD-007 仅作上述**复核留痕**（内容与 TD-005 同源、不另立处置），无鉴权条仍按计划编号为 **TD-008**。

---

## 1. TD-001 · 表列探测存在两份实现

| 项 | 内容 |
| :---- | :---- |
| 编号 | TD-001 |
| 归属 | **Epic 1 已验收代码**（迁移 0002 / `docs/epic1-template-design-v1.md` §12.1 / §12.2） |
| 位置 | 未收敛实现：`backend/database.py:645-651` `_drafts_supports_template_refs(conn)`；唯一实现：`backend/database.py:654-666` `_table_has_columns(conn, table, columns)`；调用点：`backend/database.py:781` |
| 事实 | 两者逻辑同构：`PRAGMA table_info('<table>')` 取 `row["name"]` 集合 → 判断目标列是否为其子集 → `except sqlite3.Error` 返回 `False`。`_table_has_columns()` 的 docstring 自 Epic 2 step 2.3 起声明为「表列探测的**唯一实现**」（CTO step 2.3 追加要求 1：同一个判断只许有一份实现），但当时**未**回改 Epic 1 的这份旧实现，于是全库并存两份。Epic 2 的两个新列探测（`_drafts_supports_ai_original()` / `_patient_records_supports_ai_original()`，`database.py:678-685`）已全部走唯一实现。 |
| 等级 | 低 —— 现状无行为缺陷：两份实现语句形状与返回语义逐字节等价，且各自的调用路径都有守护用例（Epic 2 侧：`backend/test_agent_stage.py:1010` 的 `test_single_flag_gate_and_probe_helpers_are_shared` 断言两个快照列探测共用同一个 `_table_has_columns`）。 |
| 风险 | 中远期：两份实现各自演进时会分叉（例如某天给探测加白名单表名校验、或改用 `sqlite_master` 解析），届时「同一个判断」出现两种口径。 |
| 为什么现在不修 | Epic 2 施工边界（`docs/epic2-agent-stage-design-v1.md` §5.4 / §8）明确不动 Epic 1 已验收代码；step 2 主链的纪律是「既有符号与语句形状逐字节不变」，此处相属**纯重构**，混入 step 2.6 会污染回归证据。 |
| 将来怎么修 | 独立一次纯重构提交：`_drafts_supports_template_refs(conn)` 函数体替换为 `return _table_has_columns(conn, "drafts", _DRAFT_TEMPLATE_REF_COLUMNS)`，常量与函数名保留（调用点 `database.py:781` 与 Epic 1 测试零改动）。 |
| 完成判据 | ① `pytest backend -q` 全绿（Epic 1 `test_templates.py` / `test_migrations.py` 与 Epic 2 全量）；② 改动前后对 `insert_draft` 的语句序列逐字节比对一致（⑨ 组用例口径）；③ 最好时机 = 下一次允许改动 Epic 1 代码的排期窗口。 |

---

## 2. TD-002 · approved + 非对象 JSON 触发既有 `AttributeError`

| 项 | 内容 |
| :---- | :---- |
| 编号 | TD-002 |
| 归属 | **存量语义**（Epic 2 之前既有分支，非 Epic 2 引入） |
| 位置 | `backend/database.py:1697-1703`：`action = json.loads(task["action_data"]) if task["action_data"] else {}` → 紧随其后的 `action.get("action") in ("send_care_notice", "send_notice")` |
| 事实 | 当 `agent_tasks.action_data` 是**合法 JSON 但不是对象**（如 `'[1, 2, 3]'` / `'"text"'` / `'123'`）且 `decision='approved'` 时，`action` 不是 `dict` → `.get(...)` 抛 `AttributeError`。该行为在 Epic 2 施工步骤 2.4 之前即存在，属既有脏数据路径。 |
| 等级 | 中低 —— 触发面窄：只有「老师 ✅ 确认 + 该请示的 `action_data` 为合法非对象 JSON」两者同时成立才爆；`action_data` 的既有写入方（学生类 `send_care_notice` / 扣分请示）都写对象 JSON，故现实触发条件是脏数据 / 外部写入。表现是异常冒泡（接口层 500），而非静默错账。 |
| 为什么现在不修 | CTO 裁决⑤②⑥ 与 step 2.4 的硬纪律是「**既有语义一字不改**」：改 3 只许**追加**转发段。故 Epic 2 只做了两件事 —— ① 新增的转发段（`database.py:1733-1738`）自行加 `isinstance(resolved_action, dict)` 兜底，避免**本步引入** rejected 路径回归；② 把既有行为写进用例注释留档（`backend/test_agent_stage.py:1263-1270`）而不回改既有分支。修它会改变 approved 路径的对外行为（500 → 正常返回），属于行为变更，不在 Epic 2 授权范围内。 |
| 将来怎么修 | 单独提交 + 单独用例，且必须先经 CTO 批准「行为变更」：把 approved 分支的解析改为与转发段同款防御（解析后 `isinstance(..., dict)` 否则 `{}`），并新增用例「approved + `action_data='[1, 2, 3]'` → 正常落定、不抛异常、`send_*_notice` 分支不触发」。 |
| 完成判据 | ① 新用例红 → 绿；② `pytest backend -q` 全绿；③ 在提交说明中显式标注「既有行为变更：由异常变为正常返回」，避免被误读为静默修 bug。 |
| 关联 | Epic 2 step 2.4 的 ⑫ 组用例（`test_agent_stage.py:1161-1381`）只守两件事：flag off 逐字节一致 + 转发段不引入回归；**不**覆盖 approved 路径的既有 AttributeError（守「一字不改」）—— 这也是本条债务今天只能靠注释而非用例表达的原因。 |

---

## 3. TD-003 · 迁移回退口径不一致（0004 删两列，0002 / 0003 保留列）

| 项 | 内容 |
| :---- | :---- |
| 编号 | TD-003 |
| 归属 | **Epic 2 迁移层**（迁移 0004；按 CTO 2026-09-28 裁决 A1 落地，step 3.0 已验收） |
| 位置 | `backend/alembic/versions/0004_add_patient_record_template_refs.py` 的 `downgrade()`：逐列 `DROP COLUMN patient_records.template_id` / `template_version`，失败抛 `RuntimeError`。对照：`0002_add_draft_template_refs.py`（回退**保留** `drafts.template_id` / `template_version`）、`0003_add_agent_stage.py`（回退**保留**两个快照列，只删 3 张新表，另带「有审计事件即中止」安全闸）。 |
| 事实 | 三份迁移对「回退要不要删列」并存两种口径：0002 / 0003 走「只回收结构、不删数据列」（Epic 1 §12.1 纪律），0004 走「逐列 DROP」。0004 的删列本身是**幂等**的（先 `PRAGMA table_info` 探测，缺列即跳过）且失败即抛，不存在静默半删。 |
| 等级 | 低 —— 各迁移与其自身设计一致：0004 的两列是**引用快照**（`DEFAULT 0` = 未记录），删掉不损失病历正文，只损失 ① 指标「这份病历是照哪版模板写的」的归因；`upgrade head` 路径与 flag off 语义完全不受影响。 |
| 风险 | 中远期：运维若按 Epic 1 口径的直觉（「downgrade 不丢列」）回退，会在 0004 上丢两列归因数据；若反向统一成「都不删列」，则与 0004 的已验收产物（含 `docs/migrations/0004_add_patient_record_template_refs.sql` 的说明与 `test_migrations.py` 的往返断言）不一致。 |
| 为什么现在不修 | 「0004 删列」是 CTO 裁决 A1 的明确要求（step 3.0 已验收）。把已验收迁移改成「不删列」属**变更已验收交付物**，必须单独提交 + 单独批准，不能在 step 3.x 内顺手改。 |
| **CTO 裁决（2026-09-29，Epic 4 step 4.0 放行时给出）** | **④ 全库统一为「downgrade 不删业务列，只回收结构（表、索引）」；0004 为已存在例外，不追溯修改；Epic 4 的 `0005` downgrade 采用新口径。** 等价于「取方向①的口径 + 豁免 0004」：不改 0004 的 `downgrade()`、不改 `docs/migrations/0004_*.sql`、不改 `test_migrations.py` 的 0004 往返断言（避免变更已验收交付物）。 |
| 将来怎么修 | **口径已定，不再二选一。** 剩余动作只在「未来某次允许变更已验收产物的窗口」才考虑：若届时要把 0004 也统一为「不删列」，需**单独提交 + 单独批准**，并同步改 `docs/migrations/0004_add_patient_record_template_refs.sql` 的说明与 `test_migrations.py` 的 0004 往返断言（改为「回退后两列仍在、老行仍为 0」）。默认**不做**。 |
| 完成判据 | **口径侧（2026-09-29 已达成）**：§0 总表行 + 本条 + `docs/epic4-lineage-design-v1.md` §6.3 三处写成**同一句话**。**实施侧（Epic 4 step 4.1 起适用）**：① `0005` 的 `downgrade()` 只 `DROP` 新增表与索引，**不** `DROP` 任何业务列（`lineage_id` 等回退后**保留**）；② `pytest backend/test_migrations.py -q` 全绿（含 0005 往返断言「回退后新增列仍在、老行值不变」）；③ 全量 `pytest backend -q` 绿；④ 提交说明显式标注「回退口径：只回收结构、不删业务列」，避免被误读为静默修 bug。 |
| 关联 | **真机升级窗口（CTO 裁决③）**：step 3.1–3.4 全部完成后、step 3.5（`sign_draft` 写 0004 两列 + 真机 `alembic upgrade head`）之前，**强制**先文件级备份 `backend/zhiheng.db` → `backend/zhiheng.db.bak-20260928`，备份**不进仓库**。✅ 已闭环：`.gitignore` 已加忽略规则 `backend/zhiheng.db.bak-*`（CTO 2026-09-28 批准，紧跟 `backend/zhiheng.db` 之后）。现状核对：`backend/zhiheng.db.bak-20260928`（184320 B，与库同尺寸）在 `git status` 中**已消失**、`git check-ignore` 退出码 0；`backend/backups/`（磁盘已存在）本就已被忽略，可作后续集中备份目录；仓库内**无任何**被跟踪的 `*db` 文件（`git ls-files` 为空）。备份文件**留在原位不动**（它是当前唯一副本，移动无收益）。 |

---

## 4. TD-005 · `plan_templates` 未按师门过滤（Epic 1 兼容镜像，未师门化）

| 项 | 内容 |
| :---- | :---- |
| 编号 | TD-005 |
| 归属 | **Epic 1 兼容镜像**（旧「施治模板」`plan_templates`）→ Epic 4 **明确不师门化**（CTO 2026-09-29 裁决 A1） |
| 位置 | `backend/database.py:372-381`（`plan_templates` 建表 + 注释）；`backend/template_service.py` 的 `sync_legacy_plan_template()`（旧 → `templates` 的**单向双写**）；`backend/alembic/versions/0005_add_lineage.py`（`ADD_COLUMNS` / `BACKFILL_SOURCES` 里**都没有** `plan_templates` —— 不补列、不回填、不过滤） |
| 事实 | ① 旧「施治模板」接口（`plan_templates`，一位老师一行 `teacher_name UNIQUE`）自 Epic 1 起被定位为**兼容镜像**（`docs/epic1-template-design-v1.md` §7.6：Epic 2 起只读、只由旧接口维护）；② flag on 时其内容**单向双写**进 `templates`（带 `lineage_id`），新链路的师门维度由 `templates` 承载；③ Epic 4 step 4.1 的 12 张「必须补 `lineage_id`」清单（设计 §2.3）**不含** `plan_templates`，故旧接口的返回行**仍是老师维度、不带师门过滤**。 |
| 等级 | 低 —— 阶段一硬约束「一师一门」（`lineage.owner_teacher_name` 唯一）下，一位老师只有一个师门，`plan_templates` 的行天然属于该老师唯一师门，**不产生越权**；数值面也无影响（旧接口只服务其所属老师本人）。 |
| 风险 | 中远期：① 若阶段二开放「一师多门」，同一位老师的旧施治模板将无法区分「哪一门」；② 若白皮书要求「旧接口也按师门过滤」，届时需再开一次迁移补列 + 回填（**比现在补列贵**：此刻补列最便宜，A1 已权衡并放弃）。 |
| 为什么现在不修 | CTO 2026-09-29 裁决 A1：**不加**。理由：`plan_templates` 是 Epic 1 兼容镜像、已被 `templates` 取代；补 `lineage_id` 会连带触发旧「施治模板」接口（读 / 写两处）的改动，属**变更已验收交付物** + 范围蔓延。已按「只登记、不修缮」入册。 |
| 将来怎么修 | **单独立项**（不并入任何现有 Epic）：① 迁移补 `plan_templates.lineage_id TEXT NOT NULL DEFAULT ''` + 按 `teacher_name` 回填；② 旧接口读路径加师门过滤、写路径带 `lineage_id`；③ `sync_legacy_plan_template()` 双写时带上当时师门；④ 同步更新 `docs/epic1-template-design-v1.md` §7.6（兼容镜像的定位变更）与本册本条。 |
| 完成判据 | ① 「一师多门」fixture 下旧接口只返回本门行（跨门行 4xx 或不可见，不得返回全量）；② `pytest backend -q` 全绿；③ Epic 1 的兼容镜像语义仍成立（旧 → `templates` 单向双写不变）；④ 设计文档 §2.3 / §11 与本册本条同步更新。 |
| 关联 | 设计文档 `docs/epic4-lineage-design-v1.md` §2.3（明确不加清单）/ §11-12（不做的事）/ 附录 A-A1（裁决来源）；`docs/epic1-template-design-v1.md` §7.6（兼容镜像定位）；`backend/test_migrations.py::test_0005_source_keeps_epic4_redlines`（用例固定「0005 不碰 `plan_templates`」）。 |

---

## 5. TD-006 · `alembic/env.py` 未做 DDL 事务化（DDL 不在事务内）

| 项 | 内容 |
| :---- | :---- |
| 编号 | TD-006 |
| 归属 | **迁移层既有基础设施**（`backend/alembic/env.py`，自 Epic 1 迁移 0001 起；**非 Epic 4 引入**） |
| 位置 | `backend/alembic/env.py:51-72` `run_migrations_online()`：`context.configure(..., transaction_per_migration=False)` 与注释「同一个连接、同一个事务内跑完所有迁移（SQLite 3.49 支持 DDL 事务）」；受影响调用方：`backend/migrations_runner.py`（`main.py` / `conftest.py` / CLI 同一条路径）；依赖方：`backend/alembic/versions/0005_add_lineage.py`（靠自身幂等探测吸收残留） |
| 事实 | 本机（Python 3.12 + SQLAlchemy 2.0 + pysqlite / `sqlite3` 默认 `isolation_level=""` legacy 事务模式）下，**DDL 不受事务保护**：`CREATE TABLE` / `ALTER TABLE ... ADD COLUMN` 会被 SQLite 隐式提交并绕过 `context.begin_transaction()`。**实测证据**（Epic 4 step 4.1 的「孤儿行」用例）：让 `0005` 在回填阶段抛错后 —— ① `alembic_version` 停在 `0004`（版本号回滚成立）、② 业务数据零变更（DML 回滚成立）、③ 但**空的 `lineage` 表与 12 张表的 `lineage_id` 列全部残留**。故「整 revision 回滚」的**实际语义 = 版本号 + 数据回滚，结构不回滚**；修正数据后重跑 `upgrade` 由幂等探测吸收（`sqlite_master` / `PRAGMA table_info` 探测后跳过），实测收敛到 `0005`。 |
| 等级 | 低 —— 现状无数据面缺陷：① 残留物恰是「目标状态的一部分」（新列 + 新空表），`0005` 的重跑路径把它当「已完成」跳过；② 迁移失败时旧代码向后兼容（flag off 不读 `lineage_id`；`plan_templates` 等旧接口零影响）；③ 全库 0001–0005 五条迁移均为「只增 + 幂等」（`IF [NOT] EXISTS`、探测后补列），故残留不会引发二次执行错误（唯一「第二遍原样执行离线 SQL」会报 `duplicate column name`，属预期并已在设计 §6.4 说明）。 |
| 风险 | 中远期：① 残留会让「半途失败的 revision」在库结构上看起来是「部分完成」，一旦未来出现**破坏性 DDL** 迁移（`DROP COLUMN` / 重建表改类型 / 先 `DROP` 后 `ADD`），重跑行为会分歧（二次 DROP 报错，或真的丢列）；② 在线与离线（人工逐句执行）的行为不能保证同构，运维心智负担；③ 生产事故时「回滚到上一个 revision」的预期与库结构实际状态不符，需要人工核对。 |
| 为什么现在不修 | **CTO 2026-09-29 裁决②：不立项**。触发条件 = 若将来出现**真实 DDL 残留导致的生产事故**，再立项。技术理由：修它必须改 `env.py` 的事务接入方式（显式 `BEGIN` / 调整 `isolation_level` / 关 autocommit），属**全库共用基础设施**改动，会连带影响 0001–0005 五条已验收迁移的执行路径、离线 SQL 生成与测试基座（`test_migrations.py` 全部往返用例），属「动已验收交付物」；而当前「只增 + 幂等」的迁移纪律已把危害面吸收到可接受范围（见「等级」行），收益与风险不成比例。 |
| 将来怎么修 | **单独立项**（不并入任何现有 Epic）：① 在 `run_migrations_online()` 内显式开事务并对 DDL 生效（如 `connection.exec_driver_sql("BEGIN")` + 迁移结束显式 `COMMIT`，或改用 `sqlite3` 非 legacy 事务模式 / `isolation_level=None` + 手动事务）；② 新增**跨 revision 守护用例**：临时 revision 中途抛错 → 断言 `lineage` 表**不存在**、`alembic_version` 回起点；③ 复核 0001–0005 五条迁移在该路径下的往返结果与离线产物逐字一致性；④ 同步更新 `docs/epic4-lineage-design-v1.md` §9 注② 与本册本条。 |
| 完成判据 | ① 造「中途抛错」的临时 revision，断言**结构 + 版本号双双回到起点**（无残留空表 / 空列）；② `pytest backend -q` 全绿（含 0001–0005 全部往返断言与 0005 幂等收敛用例）；③ 真机升级窗口「分步 upgrade + 每步 `alembic current`」流程不变、`docs/migrations/0005_*.sql` 零变化。 |
| 关联 | 发现于 **Epic 4 step 4.1**（设计 `docs/epic4-lineage-design-v1.md` §9 注② 与 附录 B 4.1 备注② 留痕）；证据用例 `backend/test_migrations.py::test_0005_orphan_row_aborts_and_converges`；裁决来源 = CTO 2026-09-29「step 4.1 验收 + 三项裁决」②。 |

---

## 6. TD-007 · `plan_templates` 未按师门过滤（Epic 1 兼容镜像）—— step 4.4 收口复核留痕

> **与 TD-005 同源**：主题、位置、事实、风险、将来怎么修、完成判据**全部沿用 TD-005**（见本册 §4）。本条**只记录 step 4.4 收口的复核动作与结论**，不另立处置；两者冲突时**一律以 TD-005 为准**。

| 项 | 内容 |
| :---- | :---- |
| 编号 | TD-007（复核留痕条目；处置 = TD-005） |
| 归属 | Epic 1 兼容镜像（`docs/epic1-template-design-v1.md` §7.6）→ Epic 4 **step 4.4 收口复核** |
| 位置 | 旧读通道 `backend/database.py:2342-2349` `get_plan_template()`；旧写通道 `backend/database.py:2352-2371` `save_plan_template()`（含 `:2364` 的「有则 UPDATE」探测）；前端唯一读取点 `frontend/src/App.tsx:773`（`GET /api/plan_template?teacher_name=`，所在 `useEffect` 为 `:770-776`） |
| 复核依据 | 设计 `docs/epic4-lineage-design-v1.md` 附录 A-A1：「建议**不加**……**并在 4.4 收口时复核**」（CTO 2026-09-29 裁决 A1 = **不加**） |
| 复核结论 | **维持「不加」**（`plan_templates` 不师门化、不加 `lineage_id`、旧接口不过滤）。四条理由：① TD-005 的两个触发条件（开放「一师多门」/ 白皮书要求旧接口按师门过滤）在本步**均未出现**；② 阶段一一师一门下，本表每行的 `teacher_name` 天然唯一对应其唯一师门，**不产生越权**；③ 本表内容 flag on 下已由旧写通道**单向双写**进带 lineage 的 `templates`（Epic 1 §7.6 定位不变），师门维度有承载方；④ 本步任务一已把前端对该接口的 `lineage_id` 拼参**撤掉** → 该 URL 在 flag on / off 两态**逐字面相同**，符合 §4.4「URL 逐字面纯净」。 |
| 等级 | 低（同 TD-005） |
| 风险 | 同 TD-005 §4「风险」行（一师多门无法区分 / 白皮书若要求则需再开一次迁移，届时补列更贵） |
| 为什么现在不修 | 同 TD-005；且 4.4 复核未触发任何触发条件 |
| 将来怎么修 | 同 TD-005「单独立项」四步；本条目随 TD-005 一并关闭，**不单独立项** |
| 完成判据 | 同 TD-005 §4「完成判据」行 |
| 关联 | 本册 **TD-005**（同源、处置方）；设计 §2.3（「不加」清单）/ §11-12（不做的事）/ 附录 A-A1（裁决来源）；`docs/epic1-template-design-v1.md` §7.6（兼容镜像定位） |

---

## 7. TD-008 · 后端无鉴权（lineage 隔离的强度边界）

| 项 | 内容 |
| :---- | :---- |
| 编号 | TD-008 |
| 归属 | **全库既有架构**（自 Epic 1 之前即如此，**非 Epic 4 引入**）→ Epic 4 **明确不修**（只登记） |
| 位置 | 全部路由：`backend/main.py`（业务路由）、`backend/template_api.py`、`backend/lineage_api.py` —— **没有** token / session / 身份签名，`teacher_name` / `patient_name` / `student_name` 全部由请求方**自报**；Epic 4 的两个隔离判定入口 `backend/lineage_service.py:272` `lineage_read_scope()` 与 `backend/template_api.py:98-109` `_check_lineage()` 都只校「**请求参数之间的一致性**」（师门存在性 + 请求老师是否属于该师门），**不校「你是谁」** |
| 事实 | 「师门隔离」在本项目的实际强度由三层构成，只有中间一层是后端强制：① 前端拼参（`App.tsx:553` `withLineage` / `TemplateStudio.tsx:226` `identityQuery`）= **体验层**，可绕过（设计 §5.1 已声明）；② 后端过滤（`lineage_read_scope()` fail-loud + SQL 带 `lineage_id`）= **能防「服务端漏过滤」**；③ 身份凭据 = **不存在** → 任何人直连后端、把 `teacher_name` 填成别人，即可读到别人的行。**加 `lineage_id` 过滤不改变这一点**：伪造者同样能自报一个合法 `lineage_id`（阶段一一师一门时它甚至就是对方的默认师门 id）。 |
| 等级 | 中高（安全面）：从「隔离强度」看属**根本缺口**；从「本 Epic 范围」看属**既有边界**（不因 Epic 4 而变差） |
| 风险 | ① 「師門隔離」四个字极易被读成安全边界 → 误判（**故本册与设计 §5.1 必须一起读**）；② 未来若开放公网 / 多租户，「直连伪造身份」会从理论风险变成实际攻击面；③ 当前隔离能防的只有两类：**同客户端切错师门**（前端上下文串门）与**服务端漏过滤**（漏改即 4xx / 行集不符），**防不住第三类**（直连伪造）。 |
| 为什么现在不修 | 无鉴权 = **全库架构级改造**（登录态、会话 / 令牌、中间件、所有路由签名与所有既有调用方），会变更 Epic 1 / 2 / 3 的**已验收接口契约**，远超 Epic 4「归属语义 + 隔离过滤」的范围；Epic 4 的义务止于「把边界写明 + 不制造新的越权路径」，设计 §5.1 已明文声明。 |
| 将来怎么修 | **单独立项**（不并入任何现有 Epic；候选定位：Epic 6 鉴权 / 多租户）：① 引入登录 + 会话（或短期令牌），服务端**从会话取身份**，路由不再信任请求体 / 查询串里的 `teacher_name` / `patient_name`；② `lineage_read_scope()` 的 fail-loud 语义与 SQL 形状**保持不变**，只把「身份来源」换成会话（保护 Epic 4 的全部过滤成果）；③ 新增「伪造身份」负向用例（直连改 `teacher_name` → 必须 401/403，不得返回他人行）；④ 同步更新设计 §5.1 与本册本条。 |
| 完成判据 | ① 直连伪造 `teacher_name` / `patient_name` 不再能读到他人数据（负向用例先红后绿）；② flag off 的「逐字节一致」纪律仍成立（鉴权不改变业务响应体与语句序列）；③ `pytest backend -q` 全绿；④ 设计 §5.1 与本册本条同步改为「已修」。 |
| 关联 | 设计 `docs/epic4-lineage-design-v1.md` **§5.1**（已知边界：后端没有鉴权，必须写明）/ §5.2（漏改即越权的查询）/ §7.2（老师端无切换器 = 消除最大越权源）；本册 TD-005 / TD-007（兼容镜像不过滤，与之叠加时须按本条的边界口径理解） |

---

## 8. 未登记项（说明）

- Epic 2 自身引入的可见风险（快照列写入、flag 双闸门、钩子两态等）**不**进本册：它们属**在设计范围内已实现并有用例守护**的内容，见 `docs/epic2-agent-stage-design-v1.md` §7.3「风险与缓解」。
- 新增债务必须以「本 Epic 明确不修」为前提，凡「本 Epic 应当且能够修」的，一律在施工步内修完，不进本册。
