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
| TD-010 | 学生端「无师门上下文」时的 400 与拼参口径分裂（**CTO 报告核查结论**：报告点名的「学生端 `role-data` 400 + `App.tsx:2259` 分支未生效」经实证**不成立**，真因 = 学生端上下文为空 + `lineage_required` 一码两义） | Epic 4 前端拼参层 / 后端错误码契约（**非新增缺陷**：现象为设计内 fail-loud，另含 2 条待裁决残项） | `frontend/src/App.tsx:549-560`（`currentLineageId` / `withLineage`）、`:955`（`role-data` 唯一调用点）、`:2237`（报告误指的分支，实属 `fetchAppointments`）、`:3227-3231`（未歸屬提示）、`:855-862`（就绪门）；`backend/lineage_service.py:272-304`（`lineage_read_scope`） | 低（不阻塞 Epic 3/4 交付；无越权、无白屏 —— 批 1 已把 4+2 处读点降级为空态） | **不修**（只登记 + 真因澄清）：改报告所指分支 = 变更一条已证正确且已验收的分支；残项 ②③ 属产品 / 设计语义，须 CTO 裁决；错误码细分会变更 §4.1 契约。详见 §8 |
| TD-011 | `lineage_required` **一码两义**：缺 `lineage_id` 与缺 `teacher_name` 返回**逐字相同**的 400 → 诊断只能读中文 `msg`、不能读码 | Epic 4 后端错误码契约（§4.1）→ **CTO 2026-09-29 批准细分**（**不阻塞 Epic 3**） | `backend/lineage_service.py:272-304`（`:291` 先校 `lineage_id` → `:220-227`；`:293-296` 后校 `teacher_name`）、`:51-70`（8 码表 `LINEAGE_ERROR_STATUS`）；接口层 `backend/lineage_api.py` `_fail()`；契约 `docs/epic4-lineage-design-v1.md:243 / :247-256`；前端按码判定 `frontend/src/TemplateStudio.tsx:263-272` | 低（无越权、无数据面缺陷；纯诊断精度） | **本轮不修**（已批准方向、排期未到）：改码 = 变更**已验收** §4.1 契约 + `backend/test_lineage.py:914-922` 对 msg 的**逐字**断言。详见 §9 |
| TD-012 | 学生**无任何归属行**时的解释缺失：五个本門读点全 400 → 面板空态，与「真的没有数据」**形状相同**，「我的師門」卡只有一句「尚未加入任何師門」 | Epic 4 前端 UI 文案 / 交互语义（§7.3 学生端）→ **CTO 2026-09-29 批准**（**不阻塞 Epic 3**） | `frontend/src/App.tsx:3182-3253`（空态 `:3221-3224`、未歸屬提示 `:3226-3231`）、`:549-560`（上下文回落）、`:855-862`（五个本門读点）；后端 `backend/lineage_service.py:272-304` | 低（不退回全量是设计要求；无白屏 —— 批 1 已把读点降级为空态） | **本轮不修**（已批准方向、排期未到）：要动**已验收**的 §7.3 空态 + 提示两条相邻分支，且与 TD-011 的错误码口径耦合。详见 §10 |
| TD-013 | 学生端「本門 → 全部師門（彙總）→ 本門」切回**同一位老師**的本門时**不重拉** → 五个本門读点停在清场空态（**用户可见的功能缺陷、常态路径触发**） | Epic 4 前端视图切换 / 重拉时机（§7.3 学生端）→ **CTO 2026-09-29 立项**（**不阻塞 Epic 3**） | `frontend/src/App.tsx:682-691`（`handleSwitchLineageView`）、`:687-690`（仅目标师 ≠ `selectedTeacher` 才换人）、`:864-871`（门控 effect，依赖**不含** `lineageView`）、`:564-576`（清场）；契约 `docs/epic4-lineage-design-v1.md:444`（§7.3 表第 1 行，**本轮已修订**） | **中**（用户可见的功能缺陷 + 常态路径触发；无越权、无数据损失、重进即自愈 → 不升为高） | **本轮不修**（只登记 + 契约对齐）：修点在**已验收**的视图切换函数与「依赖成对」铁律所在的依赖数组上，且前端无测试框架（§7.4）→ 须单独立项 + 手工自测重录。修法**已定 = 方案 b**。详见 §11 |
| TD-015 | 降级骨架草案进入**指标①（`template_match`）样本池** → 可能结构性拉低 ①（是否单列 `skipped_*` 待 6.5-b 裁决） | Epic 2 **step 6.5-a**（§5.3 观察期生成降级接线）暴露的**二阶风险** → **step 6.5-b 裁决** | `backend/agent_stage_service.py:1328-1390`（`compute_template_match()` 样本筛选：现只有 `skipped_no_template` / `skipped_stale_template` / `skipped_empty` 三种排除）；降级正文产出点 `backend/main.py:597-626`（`_SKELETON_NOTICE` / `_skeleton_draft_with_notice()`）+ 两处接线；`docs/epic2-agent-stage-design-v1.md` §3.2（排除样本）/ §5.3 | 中低（不阻塞本步交付；影响 = 观察期老师的 ① 偏低 → 与其**升阶判据**耦合，与「自锁」同族） | **不修**（只登记、归 6.5-b 裁决）：改样本筛选 = 变更**已验收**的 4-a 指标层 + 既有用例；且「降级草案算不算有效样本」属**指标口径 / 契约**问题，须与设计 §3.2 排除样本表一并裁决。详见 §13 |

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
>
> 登记例外：**TD-010** 由 CTO 2026-09-29「flag on 首屏回归（批 1/2/3）」指令登记（提前登记，非收口步）。登记理由：CTO 报告点名的「学生身份下 `/api/role-data` 返回 400 `lineage_required` + `App.tsx:2259` 分支在学生身份下未生效」经本轮**逐条实证被证否**（位置归因错 + 时序无抢跑；真因是「学生端无师门上下文 → 后端 fail-loud」+「`lineage_required` 一码两义」），该结论**必须留痕** —— 否则下一轮会再次去改一条本来正确的分支（本轮的批 3 已出现过同类误判）。**只登记、不修缮**。
> 编号说明（TD-010）：CTO 报告编号为 **TD-010**；本册此前最高为 **TD-008**，**TD-009 未被占用**（TD-004 亦为历史空缺）。为不改动他人编号，本条目**沿用 CTO 编号 TD-010** → 总表出现 TD-008 → TD-010 的跳号，与既有 TD-004 空缺同例；若 CTO 另有 TD-009 / TD-010 归属，一切以 CTO 编号为准。
>
> **2026-09-29 CTO「TD-010 三项裁决」（本轮）**：① 错误码细分 → **批准**，编号 **TD-011**（§9；**不阻塞 Epic 3**）；② 无归属学生解释缺失 → **批准**，编号 **TD-012**（§10；**不阻塞 Epic 3**）；③ 「全部師門（彙總）」口径 → 采纳**「只读彙總、**不重拉**本門数据」**，并把 `frontend/src/App.tsx:671-672` 的注释就地改写为与实现一致（**只改注释、逻辑未动**）→ TD-010 的残项 ③ **随之关闭**。
> 编号说明（TD-011 / TD-012）：两条均由 CTO 直接编号、接续 TD-010；**TD-009 仍为空缺**（与 TD-004 同例，非漏登）。三条款项同出一次裁决，但**分条登记**：错误码契约 与 UI 语义 属不同类别，实施步 / 验证面 / 回归风险都不同。
> 登记例外（TD-011 / TD-012）：与 TD-010 **同批**（非收口回归步，由 CTO 指令提前登记）。理由：两者都是 TD-010 核查出的**真实残项**且 CTO **已裁决批准**，若不登记则「已批准但未实施」失去排期依据与完成判据；**只登记、本轮不实施**。
>
> **2026-09-29 CTO「事实 d」两项裁决（本次）**：① 「事实 d」→ **立 TD-013**（§11）。理由：切回同一位老師的本門时学生看到清场空态，是**用户可见的功能缺陷**、**常态路径**触发，**不是边界 case**；修法**采纳方案 b**（在 `handleSwitchLineageView` 内显式补一次本門重拉，**不动依赖数组**）—— 方案 a（把 `lineageView` 加进依赖）会让**进入**彙總时多 5 个无谓 400，**不采纳**。② 设计 §7.3:444 与裁决③ 不一致 → **批准修订**：设计文档是**权威契约**，代码与契约不一致时**修正契约** → §7.3 表第 1 行已就地修订为「彙總视图**只清场、不重拉**；本門视图**清场 + 重拉**」→ **TD-010 完成判据 ③ 的收尾随之完成**。
> 编号说明（TD-013）：由 CTO 直接编号、接续 TD-012；**TD-009 仍为空缺**（与 TD-004 同例，非漏登）。
> 登记例外（TD-013）：与 TD-010 / TD-011 / TD-012 **同批**（非收口回归步，由 CTO 指令登记）。理由：它是 TD-010 核查连带暴露的**真实缺陷**，且 CTO **已立项**、修法已定、判据见 §11；**本轮只登记 + 修订契约，不实施代码**。
>
> **2026-09-30 CTO「step 6.5-a 二阶风险登记」指令（本次）**：生成路径接线（设计 §5.3 观察期降级）会产出「降级骨架草案」，而它照 §5.3 **仍走 `insert_draft` 落库** → **进入指标①的样本池**（现有排除只有 `template_id=0` / stale / empty）→ **立 TD-015**（§13）。事实：降级正文用的是 `build_draft_template()` 的**固定标题**（`backend/main.py:121-139`：`【中医病历草案】/【主诉（学生原话）】/【既往病历参考】/【待老师补充】`），未必与老师 active `record` 模板的段落 `title` / `order` 逐字对齐 → `section_hit` 结构性偏低；且今天**没有任何**「降级样本」标记，样本筛选也无从识别 → 是否单列 `skipped_*`（或明确「计入并写明理由」）**归 6.5-b 裁决**，本步**只登记、不修**。这与 6.5-a 裁决 D2（掐断 `permission_denied` 自锁）属**同族**：D2 堵住了审计面，本条目是同一问题在**指标面**的残留。
>
> 编号说明（TD-015）：由 CTO 直接编号、接续 TD-013；**TD-014 未被占用**（与 TD-004 / TD-009 同例，非漏登）。本章节号取 **§13** 并落在 §12「未登记项（说明）」**之后**：登记纪律要求既有条目与既有章节号**不得改写**，故本条按「纯追加」处理（章节号 = 登记次序，不重排既有章节）。
> 登记例外（TD-015）：**非收口回归步**、由 CTO「step 6.5-a」指令在**施工步内**提前登记（与 TD-005 / TD-006 / TD-010–TD-013 同批纪律）。理由：6.5-a 的裁决 D2 已把「降级」定性为**产品语义**，那么「这些样本进不进 ①」就是紧接着必须回答的口径问题；若不留痕，6.5-b 极易在不知情的前提下把骨架样本与 LLM 样本混算。**只登记、不在 6.5-a 内修缮**。

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

## 8. TD-010 · 学生端「无师门上下文」的 400 与拼参口径分裂（CTO 报告核查结论）

> 条目性质：**核查留痕 + 残余登记**。CTO 报告点名的「缺陷」经逐条实证**不成立**（见「核查结论」「事实 a/b/c」），本条目登记的是**真因澄清**与两条**待 CTO 裁决**的残余项。

| 项 | 内容 |
| :---- | :---- |
| 编号 | TD-010（沿用 CTO 报告编号；册内下一空闲号为 TD-009 —— 见 §0「编号说明（TD-010）」） |
| 归属 | Epic 4 前端拼参层（`App.tsx`）+ 后端错误码契约 → **本 Epic 明确不修**（只登记；两条残余项待裁决） |
| 报告原文 | 现象：学生身份下 `GET /api/role-data?role=学生&patient_name=X` 返回 400 `lineage_required`；位置：`frontend/src/App.tsx` 约 2259 行 `if (lineageEnabled && !currentRole.includes('老师'))` 分支「在学生身份下未生效」；修复方向：核查该分支前置条件是否成立 + 调用时序是否在就绪门前抢跑；优先级：低（不阻塞 Epic 3/4 交付） |
| 核查结论 ①（位置归因不成立） | `/api/role-data` 的**唯一**调用点是 `App.tsx:955`，URL 模板**恒含** `&teacher_name=${selectedTeacher}`（与任何 flag 分支无关）；报告所指的 `if (lineageEnabled && !currentRole.includes('老师'))` 实为 **`App.tsx:2237`**，位于 **`fetchAppointments`**（`/api/appointments`）—— 与报告点名的接口不是同一个。且该分支在 `学生` / `学生智能体` 下**是生效的**（见「事实 b」）。 |
| 核查结论 ②（时序抢跑不成立） | 见「事实 b」：`lineageEnabled` 与 `lineageReady` 在**同一次批处理**内置位，而五条师门相关首屏读只在 `lineageReady === true` 的 effect（`App.tsx:855-862`，依赖成对）里发出 → **发请求时 `lineageEnabled` 必为 `true`**，不存在「就绪门前抢跑」。 |
| 真因 | 学生端 `currentLineageId === ''`（`App.tsx:549-555`）→ `withLineage()`（`:559-560`）原样返回 URL → 后端按设计 §3.2 / §5.2 **fail-loud** 回 400。即：**「学生端没有师门上下文」**，不是「分支未生效」，也不是「漏传 teacher_name」。 |
| 事实 a（误判来源：一码两义） | `backend/lineage_service.py:272-304` 的 `lineage_read_scope()` **先**校 `lineage_id`（`:291` `parse_lineage_id`）**后**校 `teacher_name`（`:293-296`），两者**共用同一个错误码** `lineage_required`（仅 `msg` 不同）。真机库副本 + flag on 的 `TestClient` 实测矩阵（临时探针跑完即删）：**A** 全参 → `200`；**B** 缺 `lineage_id` → `400`「缺少師門上下文（lineage_id）…」；**C** 报告的 URL 形状（连 `teacher_name` 都没有）→ `400`，且 `msg` 与 B **逐字相同**（永远先命中 lineage 那条）；**D** `teacher_name=`（空串）+ 合法 `lineage_id` → `400`「缺少老師身份（teacher_name）…」。→ **C 与 B 的响应无法区分**，报告正是把「缺 `lineage_id`」读成了「缺 `teacher_name` / 分支未生效」。 |
| 事实 b（前置条件成立、无抢跑） | ① 前置条件：`'学生'` / `'学生智能体'` 均不含子串「老师」→ `!currentRole.includes('老师')` **恒为 true**；② 时序：学生端 `setLineageEnabled(true)`（`:635`）与 `setLineageReady(true)`（`:647`）落在**同一次批处理**，老师端为 `:607` / `:609`，门控 effect 依赖 `[currentRole, selectedPatient, selectedTeacher, lineageReady]`（`:862`）→ **门内发出时 flag 必已为真**；③ flag off / 连不上 → `lineageEnabled === false`，但此时后端 `lineage_enabled()` 同为 off → `lineage_read_scope()` 返回 `(False, '')`，**不会 400**（实测 M：flag off 下学生无 `teacher_name` 的 `/api/appointments?patient_name=张三` → **200**）。→ 「分支未生效」在两个方向上都不产生 400。 |
| 事实 c（400 的两条可达路径） | ① 学生**没有任何在门归属行**（未加入 / 全部已退出）→ 探测返回 `{"student_lineages":[]}` → 五个读点全 400（设计 §3.2 / §5.2 有意如此：**不退回全量**；批 2 就绪门亦刻意采纳「上下文为空也照发」→ 正是本轮手工自测 `docs/epic4-lineage-flag-on-manual-test.md` ⑦ 的预期）；② 学生选了「**全部師門（彙總）**」视图 → `lineageView === LINEAGE_ALL_VIEW` → `:554` 返回 `''` → 同上。两条都是**语义上没有上下文**，非时序问题。 |
| 事实 d（**本轮新增** · 代码走查，**未做浏览器实测** · 状态：**已由 CTO 编号 TD-013 并立项** → 见 §11） | **切回「同一位老師」的本門也不重拉**：`handleSwitchLineageView`（`:673-682`）先清场（`:675`）、再设 `lineageView`（`:676`），只在「目标师的 `teacher_name !== selectedTeacher`」时才 `setSelectedTeacher`（`:678-681`）；而五个本門读点的 gated effect 依赖是 `[currentRole, selectedPatient, selectedTeacher, lineageReady]`（`:862`，**不含** `lineageView`）→ 本門视图常驻「先清場、**不重拉**」→ 学生点「全部師門（彙總）」再点回本門（常态路径：目标师 = `selectedTeacher`），五个列表停在清场后的空态，直到切人 / 切角色 / 重进才恢复。**注**：这不是裁决③ 的「彙總只清場」——它发生在**本門**方向。修法二选一（均需单独立项）：**a** 把 `lineageView` 加进 gated effect 依赖（代价：**进入**彙總视图时也会重拉 → 5 个不带 `lineage_id` 的 400，虽与「清场空态」同形但属无谓请求）；**b** 在 `handleSwitchLineageView` 内**显式补一次** 本門视图的重拉（不动依赖数组）。**（2026-09-29 裁决：本项已编号 **TD-013** 并**立项**，采纳**方案 b** → 详见 §11）** |
| 等级 | 低（不阻塞 Epic 3/4 交付）：无越权、无白屏 —— 批 1 已把 4+2 处读点降级为空态 |
| 风险 | ① **诊断风险（本轮已实际触发一次）**：错误码不可区分 → 后续任何「学生端 400」都会被误判为「漏传 `teacher_name`」→ 去改一条**本来正确**的分支（本轮的批 3 已出现同类误判，见 `docs/epic4-lineage-flag-on-manual-test.md` 附录 C）**→ 已由 TD-011 承接**（§9，CTO 2026-09-29 批准，不阻塞 Epic 3）；② **体验缺口 → 已由 TD-012 承接**（§10，CTO 2026-09-29 批准，不阻塞 Epic 3）：学生无归属行时，自己的病历 / 联系簿 / 预约全为空态，而 §7.3 的「未歸屬」提示**只在存在 `patient_teachers` 行（`lineage_id = ''`）时才给**（`App.tsx:3226-3231`）→ **完全没有归属行的学生看不到任何解释**（该卡空态只有一句「尚未加入任何師門」：`App.tsx:3221-3224`）；③ **口径不一致 → 已关闭**（2026-09-29 裁决③）：原注释写「『全部師門（彙總）』= 本門上下文不变」，但实现（`:554`）把 ALL 视图判为 `''`，且门控 effect 依赖数组**不含** `lineageView`（`:862`）→ 设计 §7.3「先清場**再重拉**」在该视图只有前半句；**裁决采纳「只读彙總、不重拉本門数据」，`App.tsx:671-672` 注释本轮已改写为与实现一致（只改注释、逻辑未动）** —— 由此连带暴露的**新殘項**见「事实 d」（**已编号 TD-013 / 已立项**，见 §11）。 |
| 为什么现在不修 | ① 报告点名的缺陷经核查**不存在**，改它 = 变更一条已证正确且已验收的分支（属「变更已验收交付物」）；② 残余项 ②③ 都涉及**产品 / 设计语义**（无归属学生是否该看得见自己的数据、彙總视图是否保留本門上下文），须 CTO 裁决后才能动，不能在回归步内顺手改；③ 错误码细分（如新增 `lineage_teacher_required`）会变更 §4.1 错误码契约与前端 `res.detail.error` 读法 = 变更已验收契约，且需同步 `docs/epic4-lineage-design-v1.md` §4.1 与 `backend/test_lineage.py` ⑩ 组断言。 |
| 将来怎么修（**2026-09-29 三项裁决已落地**） | **已裁决**：① 错误码细分 → **批准**，拆出 **TD-011**（§9；不阻塞 Epic 3）；② 学生无归属行的解释缺失 → **批准**，拆出 **TD-012**（§10；不阻塞 Epic 3）；③ 「全部師門（彙總）」口径 → 采纳**「只读彙總、不重拉本門数据」**，本轮**就地修正** `frontend/src/App.tsx:671-672` 注释使其与实现一致（**只改注释、逻辑未动**）→ 本项**关闭**。**已裁决**：本轮新发现的「切回同一老師本門也不重拉」（「事实 d」）→ 由 CTO **编号 TD-013 并立项**（§11，修法采**方案 b**），**不并进本条修缮**。**本条自身已无待办**（① ② 已外移为独立条目），处置维持「**只登记、不修缮**」。 |
| 完成判据 | ① 学生无归属行 → 首屏 0 个 400（或 URL 按裁决形态发出且 UI 有明确解释）；② `学生` / `学生智能体` 下 Network 面板中 `/api/role-data` **恒带** `teacher_name`（含 `''` 边界用例）；③ 「彙總」视图行为与设计 §7.3 文字**逐字一致**；④ `pytest backend -q` 全绿 + `npx tsc --noEmit` 通过。（**2026-09-29 补充**：裁决③ 采纳「只读彙總、不重拉」后，本判据 ③ 的落点转为**设计 §7.3 表第 1 行** —— 现文「切换 = 换 `lineage_id` 上下文 → **先清场再重拉**」（`docs/epic4-lineage-design-v1.md:444`）需补「彙總视图只清场、不重拉」；本轮按 CTO 指令**未改设计文档**，留作该判据的收尾。**2026-09-29 收尾完成**：`docs/epic4-lineage-design-v1.md` §7.3 表第 1 行已按裁决③ 修订为「彙總视图**只清场、不重拉**；本門视图**清场 + 重拉**」，与实现（`App.tsx:682-691` / `:864-871`）逐字对齐；同一批把「切回同一位老師时依赖不变 → 不重拉」**立项 TD-013**〔§11〕。） |
| 关联 | 设计 `docs/epic4-lineage-design-v1.md` §3.2（老师端读必带双因子）/ §5.2（漏改即越权）/ §7.3（学生端视图切换）/ §4.1（错误码契约）；本轮手工自测 `docs/epic4-lineage-flag-on-manual-test.md` §3（反例速查，本轮已补「错误码不可区分」一条）；本册 **TD-008**（无鉴权边界：本条目不涉及越权）；代码位置：`frontend/src/App.tsx:549-560 / 955 / 2231-2247 / 3227-3231 / 855-862`、`backend/lineage_service.py:272-304`；**后续条目**：TD-011（§9 错误码细分）/ TD-012（§10 无归属学生解释）；**新殘项**：本条「事实 d」（切回同一老師本門不重拉）→ **已编号 TD-013、已立项**（§11） |

---

## 9. TD-011 · `lineage_required` 一码两义（缺 `lineage_id` 与缺 `teacher_name` 不可区分）

| 项 | 内容 |
| :---- | :---- |
| 编号 | TD-011（由 CTO 2026-09-29「TD-010 三项裁决」① 编号并**批准方向**） |
| 归属 | 后端**错误码契约**（Epic 4 §4.1）→ **本轮不实施**（已批准、排期未到；**不阻塞 Epic 3**） |
| 位置 | 校验入口 `backend/lineage_service.py:272-304`（`lineage_read_scope`）：**先** `parse_lineage_id()`（`:291` → 实现 `:220-227`，抛 `LINEAGE_REQUIRED` + msg「缺少師門上下文（lineage_id）…」）**后**校 `teacher_name`（`:293-296`，**同一个码** + msg「缺少老師身份（teacher_name）…」）；码表 `:51-70`（`LINEAGE_REQUIRED` / `LINEAGE_ERROR_STATUS` 8 码）；接口层统一出口 `backend/lineage_api.py` `_fail()`；契约 `docs/epic4-lineage-design-v1.md:243`（错误体四键）/`:247-256`（§4.1 表）；前端**按码判定** `frontend/src/TemplateStudio.tsx:263-272`（`lineageProbeFailure`） |
| 现象 | flag on 下「缺 `lineage_id`」与「缺 `teacher_name`」是**两种不同根因**，却返回**形状完全相同的 400**：同 `error` 码、且 msg 也**不可区分** —— 因为 `parse_lineage_id()` 先抛，缺 `teacher_name` 的那条 msg **永远不可达**（除非 `lineage_id` 先合法）。 |
| 实测证据 | TD-010「事实 a」矩阵（真机库副本 + `TestClient`）：**B**（缺 `lineage_id`）与 **C**（连 `teacher_name` 也没有）响应**逐字相同**；只有 **D**（`teacher_name=` 空串 + 合法 `lineage_id`）才落到「缺少老師身份」。 |
| 危害 | ① **误判成本已实际发生**：CTO 报告据该 400 码推断「前端漏传 `teacher_name` / 拼参分支未生效」→ 差点改一条已证正确且已验收的分支（本轮已拦下，见 TD-010「事实 b」）；② 任何自动化（脚本 / 监控 / E2E / 日志聚合）按 `error` 分流时，两类根因**无法区分**；③ 排障只能靠匹配中文 `msg`（`msg` 是「人类可读」，**不是契约**）→ 与「机器可判定」的接口纪律相悖。 |
| 等级 | 低（无数据面缺陷、无越权、无功能受损；纯**诊断精度**问题） |
| 为什么本轮不修 | ① 改/增 `error` 码 = **变更已验收契约**：§4.1 是明确的**8 码**表（`docs/epic4-lineage-design-v1.md:247-256`），新增第 9 码要同步设计文档 + 前端按码判定（`TemplateStudio.tsx:263-272`）+ 全部 400 断言；② `backend/test_lineage.py:914-922` 对 msg 有**逐字**断言、`:987-998`（`_assert_error`）对四键与码断言 → **测试面亦属已验收**；③ CTO 裁决为「批准，**不阻塞 Epic 3**」→ 排序上让位于 Epic 3 交付；④ 当前无功能受损，代价只是排障时多读一眼 msg。 |
| 将来怎么修（已批准，二选一） | **A · 新增独立码（推荐）**：`LINEAGE_TEACHER_REQUIRED = "lineage_teacher_required"`（400）写入 `LINEAGE_ERROR_STATUS`（`backend/lineage_service.py:51-70`），`backend/lineage_service.py:293-296` 改抛该码；同步 §4.1 表 + 前端 `frontend/src/TemplateStudio.tsx:270`（决定是否并入「师门上下文问题」判定）+ `backend/test_lineage.py:918-922` 逐字断言。**B · 不改码、回带缺参项**：沿用 `lineage_required`，在**契约内已有**的 `errors` 数组回带 `[{path: 'lineage_id' \| 'teacher_name', msg: ...}]` → 前端读法**零变更**，但仍需在设计 §4.1 补一行说明。**两者都不许**放宽 400（**绝不**退化为全量，§3.2 / §5.2）。 |
| 完成判据 | ① 同一 URL 形状（缺 `lineage_id` vs 缺 `teacher_name`）返回**可区分**的 `error`（或 `errors`）→ 新增一条「两者不相等」的用例；② flag off 下两者仍 200、零行为变化（①/② 组不回归）；③ 设计 §4.1 表与实际可达码集合一致（用例可枚举全码 / 全 `errors` 形状）；④ `pytest backend -q` 全绿。 |
| 关联 | TD-010「事实 a」（误判来源，含实测矩阵）；设计 §4.1（错误码契约）/ §3.2（老师端读必带双因子）/ §5.2（漏改即越权）；`docs/epic4-lineage-flag-on-manual-test.md` §3 第 8 行（「不能靠错误码定位缺哪个参数」陷阱）；**耦合项**：TD-012（空态文案可按细分后的码 / `errors` 精确分流） |

## 10. TD-012 · 学生「无任何归属行」时解释缺失（空态不可区分）

| 项 | 内容 |
| :---- | :---- |
| 编号 | TD-012（由 CTO 2026-09-29「TD-010 三项裁决」② 编号并**批准方向**） |
| 归属 | 前端 **UI 文案 / 交互语义**（Epic 4 §7.3 学生端）→ **本轮不实施**（已批准、排期未到；**不阻塞 Epic 3**） |
| 位置 | `frontend/src/App.tsx:3182-3253`（🏯「我的師門」卡）：空态 `:3221-3224`、未歸屬提示 `:3226-3231`、彙總卡 `:3233-3250`、视图切换器 `:3189-3200`；上下文回落 `:549-560`（`currentLineageId` / `withLineage`）；五个本門读点 `:855-862`；后端 fail-loud `backend/lineage_service.py:272-304`；设计口径 `docs/epic4-lineage-design-v1.md:440-446`（§7.3） |
| 现象 | 学生**没有任何归属行**（从未加入 / 全部已退出）→ `GET /api/student-lineages` 返回 `{"student_lineages":[]}`（`App.tsx:634-637`，`activeMemberships` 为空）→ 五个本門读点的 URL 不带 `lineage_id` → flag on 下后端按 §3.2 / §5.2 **fail-loud** 回 400 → 批 1 把 400 降级为**空态**。此时该卡只给一句「尚未加入任何師門：可在上方「我的老师」裡加入一位老師（= 加入其師門）。」（`:3222-3224`）→ **学生看不出「病历 / 联系簿 / 预约 / 草案为什么是空的」**。 |
| 关键风险 | **两种空态在 UI 上形状完全相同**：①「无师门上下文 → 读点 400 → 空」；②「确实还没有数据 → 200 空数组」。学生（与支持人员）**无法区分**这两者，也无法从界面上得知「加入師門後这些数据就会出现」；且「全部已退出」与「从未加入」共用**同一句**文案（只讲「加入」，没讲「退出後本門資料不再顯示」）。 |
| 补充事实 | §7.3 的「未歸屬」提示（`:3226-3231`）**只在 `patient_teachers` 存在 `lineage_id = ''` 行时**才渲染 → **完全没有归属行的学生一条提示都没有**（该提示与「无归属行」是两种情形：前者是「有行但未歸屬」，后者是「没有行」）。 |
| 等级 | 低（无越权：**不退回全量**是设计要求；无白屏：批 1 已把 4+2 处读点降级为空态；影响面 = 可理解性 / 支持成本，非数据正确性） |
| 为什么本轮不修 | ① 属**产品文案 / 交互语义**（CTO 裁决②「批准，**不阻塞 Epic 3**」）；② 要动的是**已验收**的 §7.3 空态与提示两条相邻分支，须与 **§2.4 纪律 2「绝不兜底成某个师门」**一起改文字 → 属变更已验收交付物，需单独一步 + 手工自测 ⑦ 重录；③ 与 **TD-011** 有耦合：若两处空态都要指向「缺哪个上下文」，最好等 TD-011 的码 / `errors` 口径定案后一次改到位。 |
| 将来怎么修（已批准） | ① 空态**一分为二**：**从未加入** vs **全部已退出**（可用 `studentLineages.filter(r => !r.unassigned).length` 判定「有历史行 = 曾加入」）；② 文案点明因果：「**當前無師門上下文** → 本門資料（病歷 / 預約 / 聯繫簿 / 草案）暫不可見；加入師門後可見」；③ 可选：为「读点 400 造成的空态」加一条统一提示条（口径与 `TemplateStudio` 的师门红字一致），但**不得**兜底成任一师门；④ 与 TD-011 联动：细分码 / `errors` 后，空态可按根因精确分流（缺 `lineage_id` vs 缺 `teacher_name`）；⑤ 全部文案沿用**繁体古字**（设计 §7.1：`🏯 我的師門` / `未歸屬` 等既有口径）。 |
| 完成判据 | ①「从未加入」与「全部已退出」两种情形文案**不同**，且都说明「本門讀點為何為空」；② flag off 下 UI / 请求与 Epic 4 之前**逐字面一致**（§4.4 零行为变化）；③ 手工自测 ⑦ 的记录表能把「**无上下文空态**」与「**无数据空态**」**区分**开（改前改后各录一次）；④ `npx tsc --noEmit` 通过。 |
| 关联 | TD-010「事实 c ①」（400 的第一条可达路径）；TD-011（错误码细分，**耦合项**）；设计 §7.3（学生端）/ §7.1（我的師門卡）/ §2.4 纪律 2（绝不兜底）；`docs/epic4-lineage-flag-on-manual-test.md` §3 第 3 行（⑦ 首屏 400 + 空態＝設計預期） |

---

## 11. TD-013 · 切回「同一位老師」的本門时**不重拉**（学生看到清场空态）

> 条目性质：**新缺陷登记 + 契约对齐**。来源 = TD-010「事实 d」（代码走查发现，本轮 CTO 裁决**立项**）。本轮**只登记**，代码修缮单独立项；同批已就地修订设计 §7.3 表第 1 行，使契约与实现对齐。

| 项 | 内容 |
| :---- | :---- |
| 编号 | TD-013（由 CTO 2026-09-29「事实 d」裁决① 编号并**立项**） |
| 归属 | Epic 4 前端**视图切换 / 重拉时机**（`App.tsx` 单文件 SPA 的 effect 依赖口径，§7.3 学生端）→ **本轮不实施**（已立项、排期未到；**不阻塞 Epic 3**） |
| 位置 | `frontend/src/App.tsx:682-691`（`handleSwitchLineageView`：`:684` 清场 → `:685` 设 `lineageView` → `:687-690` **仅当**目标师的 `teacher_name !== selectedTeacher` 才 `setSelectedTeacher`）；`:564-576`（`clearLineageScopedPanels`）；`:864-871`（五个本門读点的门控 effect，依赖 `[currentRole, selectedPatient, selectedTeacher, lineageReady]`，**按「依赖成对」铁律不含 `lineageView`**）；`:549-555`（`currentLineageId`，彙總视图回落空串 `:554`）；切换器 `:3201-3208`；契约 `docs/epic4-lineage-design-v1.md:444`（§7.3 表第 1 行 —— **本轮已修订**） |
| 事实 d 描述（TD-010 原始走查记录） | **切回「同一位老師」的本門也不重拉**：`handleSwitchLineageView` 先清场（`:684`）、再设 `lineageView`（`:685`），只在「目标师的 `teacher_name !== selectedTeacher`」时才 `setSelectedTeacher`（`:687-690`）；而五个本門读点的门控 effect 依赖是 `[currentRole, selectedPatient, selectedTeacher, lineageReady]`（`:871`，**不含** `lineageView`）→ 本門视图常驻「先清場、**不重拉**」。**注**：这不是裁决③ 的「彙總只清場」—— 它发生在**本門**方向。 |
| 现象（复现路径） | 学生端 flag on：① 进入「🏯 我的師門」→ 默认**本門**视图（`:643-644`）→ 五个本門读点（病历 / 联系簿 / 预约 / 草案 / 日历）正常；② 点「**全部師門（彙總）**」（`:3207`）→ 清场 + 拉只读彙總卡片；③ 再点回**本門**（`:3203`）→ 目标师 = 当前 `selectedTeacher` → `:687-690` 不换人 → 依赖数组**无变化** → effect **不重跑** → 五个面板**停在清场后的空态**。恢复条件 = 任何使依赖变化或重挂载的动作（切人 / 切角色 / 切老师 / 重进应用）。 |
| 影响 | ① **用户可见的功能缺陷**：学生看到自己的本門病历 / 联系簿 / 预约 / 草案**全空**，而数据完好地留在后端 → 学生会以为「我的资料没了」（与 **TD-012** 的「空态不可区分」叠加，属同一类可理解性风险）；② **常态路径触发**：视图切换器是本 Epic 学生端的主交互、两个按钮相邻，一次「彙總 → 本門」即命中，**不是边界 case**；③ **边界内**：无越权（该路径下 `currentLineageId` 仍为真实 `lineage_id`，只是请求**没发出**）、无白屏、无数据损坏（不落库），重进即自愈。 |
| 等级 | **中**（用户可见的功能缺陷 + 常态路径触发；无越权 / 无数据损失 / 可自愈 → 不升为高；**不阻塞 Epic 3**） |
| 为什么本轮不修 | ① 修点落在**已验收**的视图切换函数与「**依赖成对**」铁律所在的依赖数组上（`App.tsx:862-863` 注释明写「只加门控而漏依赖 = 永久空数据」），顺手改 = 变更已验收交付物；② 前端**无测试框架**（设计 §7.4：验证只有 `npx tsc --noEmit` + `npm run build` + 手工清单）→ 必须重录手工自测第 2 条；③ 本轮 CTO 指令范围为「**登记 + 契约对齐**」，不含代码。 |
| 将来怎么修（**已裁决：方案 b**） | 在 `handleSwitchLineageView` 内**显式补一次本門重拉**（**不动依赖数组**）。前置须同时满足：(a) `view !== LINEAGE_ALL_VIEW`（本門方向）；(b) `lineageEnabled && lineageReady`（flag off / 未就绪不发，守 §4.4 零行为变化）；(c) 本次切换**没有**改变 `selectedTeacher`（否则既有门控 effect 已负责重拉，补拉会变**双拉**）→ 复用那五个 fetch（`fetchRoleData` / `fetchDrafts` / `fetchPatientRecords` / `fetchAppointments` / `fetchCalendar`，与 `:864-871` 同一组）并复位 `lineageSummary`。**明确不采纳方案 a**（把 `lineageView` 加进 gated effect 依赖数组）：那会让**进入**彙總视图时也重拉 → 5 个不带 `lineage_id` 的 400（与「清场空态」同形，但属**无谓请求**）。 |
| 完成判据 | ① 手工自测第 2 条扩写为「**先清场再重拉**（本門 → 彙總 → 本門）」：三步后五个面板**自动恢复**本門数据、Network 面板中五个请求各带**正确** `lineage_id`、无 400；② **进入**彙總视图**不新增**本門请求（5 个不带 `lineage_id` 的 400 不出现）；③ flag off 下 URL 与请求**次数**与 Epic 4 之前逐字面一致（§4.4）；④ gated effect 的依赖数组**未变**（`App.tsx:871`）；⑤ `npx tsc --noEmit` + `npm run build` 通过；⑥ 设计 §7.3 表第 1 行与本条完成后的实现**逐字一致**。 |
| 附带项（本轮核出的**注释口径偏差**，本轮不改码） | `frontend/src/App.tsx:122`（师门上下文「四条纪律」③）仍写「切换师门 = 换上下文 → **先清场再重拉**」，未覆盖「彙總视图无本門上下文 → **只清场、不重拉**」→ 与修订后的设计 §7.3 表第 1 行**不完全对齐**。本轮按 CTO 指令**只动两处文档**（不改代码、含注释）；实施本条时**一并改注释、不动逻辑**（沿用裁决③ 对 `App.tsx:671-672` 的处置口径）。 |
| 关联 | 来源条目 = 本册 **TD-010「事实 d」**（其「事实 d」行状态由本条承接：**已编号 TD-013 / 已立项**）；同族 = **TD-012**（学生会把空态读成「我的资料没了」；本条让**多余**的空态消失）；**TD-011**（错误码细分：本条完成后，「彙總 400」与「补拉缺参 400」可按码进一步区分）；设计 §7.3（学生端视图切换，**本轮已修订**）/ §7.4（验收手段受限）/ §4.4（flag off 零行为变化）/ §5.2（漏改即越权：本条不涉及）；`docs/epic4-lineage-flag-on-manual-test.md` §3（手工自测反例速查） |

---

## 12. 未登记项（说明）

- Epic 2 自身引入的可见风险（快照列写入、flag 双闸门、钩子两态等）**不**进本册：它们属**在设计范围内已实现并有用例守护**的内容，见 `docs/epic2-agent-stage-design-v1.md` §7.3「风险与缓解」。
- 新增债务必须以「本 Epic 明确不修」为前提，凡「本 Epic 应当且能够修」的，一律在施工步内修完，不进本册。

---

## 13. TD-015 · 降级骨架草案进入指标①样本池（观察期生成降级产出的样本如何计 ①）

| 项 | 内容 |
| :---- | :---- |
| 编号 | TD-015 |
| 归属 | Epic 2 **step 6.5-a**（设计 §5.3 观察期生成降级接线）暴露的**二阶风险** → **step 6.5-b 裁决** |
| 位置 | 样本筛选（现实现）：`backend/agent_stage_service.py:1328-1390` `compute_template_match()` —— 现只有三种排除：`skipped_no_template`（生成时无生效模板）、`skipped_stale_template`（`template_id` ≠ 当前 active）、`skipped_empty`；降级正文产出点：`backend/main.py:597-626`（`_SKELETON_NOTICE` + `_skeleton_draft_with_notice()`）、接线点 `:645-655`（`_generate_and_store_llm_draft()`）与 `:746-754`（`POST /api/generate-draft` 端点体）；契约：`docs/epic2-agent-stage-design-v1.md` §3.2（排除样本）/ §5.3（降级路径仍走 `insert_draft`，含快照列） |
| 事实 | 6.5-a 按 §5.3 让观察期老师走本地骨架：正文 = §5.3 提示语首行 + `build_draft_template()` 的**固定标题**骨架（`backend/main.py:121-139`：`【中医病历草案】/【主诉（学生原话）】/【既往病历参考】/【待老师补充】`）。而指标① 的**基准**是老师 active `record` 模板的段落 `title` / `order`（设计 §3.2 / Epic 1 §9.2）→ 两套标题是**两套字面量**，骨架草案的 `section_hit` 结构性偏低；首行提示语还会落在 `【中医病历草案】` 段之前（是否计入 `warnings` / violations 取决于解析口径）。这些草案仍按 §5.3 走 `insert_draft` 落库 → **进样本池**，而今天**没有任何**「降级样本」标记，样本筛选也无从识别。 |
| 现象 | 观察期老师的 ① 会因**自身降级路径**而偏低 → `template_match_below_threshold` 进 `blockers`（设计 §3.6）→ 与 6.5-a 裁决 D2 掐断的「自锁」**同族**：升阶判据被生成降级路径本身拖住。D2 已堵住 `permission_denied` 那条路，本条目是同一问题在**指标面**的残留。 |
| 等级 | 中低（**不阻塞本步交付**）：无越权、无数据面损坏；影响面 = 观察期老师的 ① 读数与升阶判定。 |
| 为什么现在不修 | ① 6.5-a 的 CTO 范围是「新符号 + 两处接线 + 常量 + 注释 + 登记」五件，指标口径**不在内**；② 改样本筛选 = 变更**已验收**的 4-a 指标层（`compute_template_match()`）与其既有用例；③ 真问题不是「加一行 `if`」，而是「设计 §3.2 的排除样本表要不要新增一类」= **契约问题**，须与 §3.2 / §5.3 一并裁决。 |
| 将来怎么修（**待 6.5-b 二选一**） | **(a) 单列排除**：给降级生成的草案单列 `skipped_degraded`，并在设计 §3.2 排除样本表登记该计数（前端照 `已略過 N 份…` 同款式样展示）。识别手段三选一：① 以 §5.3 提示语为标记（依赖文案契约，零迁移）；② `drafts` 新增「生成来源」列（要迁移，成本最高）；③ 记生成时的阶段快照（需快照列）。 **(b) 明确计入**：保留现状并在设计 §3.2 / §5.3 写明「降级骨架草案**属于**有效样本」—— 理由：① 的语义是「智能体是否按模板骨架输出」，降级样本恰好是**反例样本**（智能体零输出），排除它会把观察期的 ① 变成「无样本」而非「不达标」。**两案判据不同**：(a) 认为观察期的 ① 无意义；(b) 认为有意义（只是必然低）。 |
| 完成判据（任一方案落地时） | ① 设计 §3.2 的排除样本表 / 口径文字与本条裁决**逐字一致**；② 6.5-b 用例钉住所选语义（(a) 断 `skipped_degraded` 计数与 `samples` 的关系；(b) 断降级样本计入 `samples` 且 `value` 按实际算、**不特判为 `null`**）；③ 既有 4-a 用例全绿（若新增排除类，须同步 4-a 的断言）；④ 与 6.5-a 裁决 D2（零审计）不冲突：**不得**用「给降级路径补一行审计」的方式实现标记。 |
| 关联 | 同族 = **6.5-a 裁决 D2（自锁，已掐断审计面）**；`backend/agent_stage_service.py:858-862`（口径 B：那一格「属产品语义，不是权限」）；设计 §3.2（排除样本）/ §3.6（`blockers` 十条）/ §5.3（降级路径）/ §7.1-③；本册 **TD-010**（同款纪律：只登记 + 真因澄清，不改已验收分支）。 |
