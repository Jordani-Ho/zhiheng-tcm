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

## 3. 未登记项（说明）

- Epic 2 自身引入的可见风险（快照列写入、flag 双闸门、钩子两态等）**不**进本册：它们属**在设计范围内已实现并有用例守护**的内容，见 `docs/epic2-agent-stage-design-v1.md` §7.3「风险与缓解」。
- 新增债务必须以「本 Epic 明确不修」为前提，凡「本 Epic 应当且能够修」的，一律在施工步内修完，不进本册。
