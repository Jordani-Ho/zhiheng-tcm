# 阶段二「数据主权落地」设计文档 v1.3 Patch

> ⚠️ **本文档是 v1.3 patch，非完整设计文档。**
> 阅读时以本文档 + v1.2 主文档（`docs/phase2-data-sovereignty-design.md`）合并为准。
> **合并后本文档删除。**
>
> **B5 实现启动前必须先合并**——这是 B5 的前置条件，不是可选项。

**文件**：`docs/phase2-data-sovereignty-design-v1.3-patch.md`
**版本**：v1.3（patch）
**日期**：2026-10-02
**作者**：B 板块 CTO
**审阅**：发起人（知衡）
**依据**：B5 只读调研（HEAD bb95e6e）+ 发起人裁定
**约束**：本文档只碰 `docs/`，zero code change

---

## 0. 本 Patch 涵盖内容

| 编号 | 内容 |
| :---- | :---- |
| 1 | 替换主文档 §3.5 全文 |
| 2 | 附录 C 新增 C.3 |
| 3 | 主文档版本号 v1.2 → v1.3（合并时） |
| 4 | 编号映射说明：commit bb95e6e 原标「B4-1 导出」，实质为 B5-1（见 §5） |

---

## 1. §3.5 全文替换

> 以下全文替换主文档 §3.5「子项 5：数据封存」的所有小节（§3.5.1 至 §3.5.10）。

### 3.5 子项 5：数据封存

#### 3.5.1 是什么

阶段二只做「封存事件记录 + 查询 + 手动触发」。封存（客户端下线）的完整语义保留给阶段四。

**阶段二做**：

- `seal_events` 事件表（新）
- 查询 API（列出某主体的封存 / 重新接纳历史）
- 手动触发封存 / 重新接纳（老师或本人发起）

**阶段二不做**：

- 不自动判定「所有老师都除名」——除名事件未定义，是 C 板块的活
- 不读 `agent_stage_log`——里面没有除名事件
- 不做全站拦截——封存 ≠ 拒绝服务
- 不实际上链——链上事件接口预留，阶段四落地

#### 3.5.2 为什么不读 agent_stage_log

原设计（v1.1 §3.5.5）假设 `agent_stage_log` 有除名记录。调研证实：

- `agent_stage_log` 现有 10 类事件（`stage_upgraded` / `stage_demoted` / `upgrade_recommended` / `upgrade_declined` / `permission_denied` / `evaluation` / `config_changed` / `suggestion_generated` / `predraft_generated` / `permission_relaxed`），**无一是除名**
- `event_type` 列无 CHECK、无白名单
- `patient_teachers.status='inactive'` 同时表示「退师」和「除名」，DB 层无法区分

**结论**：除名事件的定义是 C 板块治理机制的产物。B 板块不定义，不假设。

#### 3.5.3 为什么不拦截

白皮书 §4.6 说「数据封存 = 客户端下线」。这是**客户端优先架构**的概念。阶段二还在服务端 SQLite 架构，没有「客户端」可下线。

服务端拦截封存用户 = 封号，不是白皮书说的封存。白皮书说封存是「数据保留在客户端，只有当事人自己能访问」——保护数据，不拒绝服务。

改 78+31 端点做封存拦截，是为一个阶段二不该做的事付出的代价。

#### 3.5.4 seal_events 表结构

```sql
CREATE TABLE IF NOT EXISTS seal_events (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    subject_type TEXT NOT NULL,        -- 'patient' | 'teacher'
    subject_name TEXT NOT NULL,        -- 患者名 / 老师名
    action TEXT NOT NULL,              -- 'seal' | 'readmit'
    reason TEXT,                       -- 原因（文本）
    operator TEXT,                     -- 操作者（老师名 / 本人）
    created_at TEXT NOT NULL,          -- ISO 时间戳
    chain_ready BOOLEAN DEFAULT FALSE, -- 阶段四预留：是否已上链
    chain_hash TEXT                    -- 阶段四预留：链上交易哈希
)
```

#### 3.5.5 除名依赖

「除名」的定义归 C 板块。C 板块 v0.5 已落盘（commit `827dc13`，953 行），但**未定义除名事件**。C 板块现有事件（引荐链、存活门限、协议底线封存）中无「除名」。

B 板块**不定义除名事件**。`seal_events.action` 的取值只含 `seal` / `readmit`，不含 `remove`。

若 C 板块未来定义除名事件，B 板块在 v1.4 中重新对齐。

#### 3.5.6 API 契约

| 端点 | 方法 | 参数 | 返回 |
| :---- | :---- | :---- | :---- |
| `/api/seal/events` | GET | `subject_type`, `subject_name` | `{"events": [...]}` |
| `/api/seal/trigger` | POST | `{"subject_type", "subject_name", "action", "reason", "operator"}` | `{"event_id": int}` |

**flag**：`SEAL_ENABLED`，默认 off。

**错误码**：

- `seal_disabled` → 404
- `subject_required` → 400
- `subject_mismatch` → 403
- `action_invalid` → 400
- `subject_not_found` → 404

#### 3.5.7 阶段四预留

- 自动判定（依赖 C 板块除名事件定义）
- 全站拦截（依赖客户端优先架构）
- 链上事件（依赖 E 板块区块链集成）
- `seal_events.chain_ready` / `chain_hash` 填充（阶段四写入）

#### 3.5.8 与白皮书的对应

§4.6、§5.5.3、§6.4.2。阶段二只落地「事件记录」部分，其余为阶段四预留。

---

## 2. 附录 C 新增 C.3

> 以下追加到主文档附录 C 末尾（C.1 / C.2 之后）。

### C.3 向 C 板块提出的需求：「除名」事件定义

**需求**：

B 板块 §3.5.5 明确：「除名」的定义归 C 板块。

**现状**：C 板块 v0.5 已落盘（commit `827dc13`），但未定义除名事件。C 板块现有事件（引荐链、存活门限、协议底线封存）中无「除名」。`agent_stage_log` 亦无除名事件。`patient_teachers.status='inactive'` 无法区分退师与除名。

**待 C 板块回复**：

- 除名在治理机制中的正式事件名？
- 写入哪张表？（扩 `agent_stage_log` / 新表？）
- 与「退师」如何区分？

**登记状态**：待 C 板块 v0.5 补丁或 v0.6 定义除名事件后对齐。

---

## 3. 主文档合并清单（合并时执行）

合并本 patch 到主文档时，需执行以下操作：

| 步骤 | 操作 |
| :---- | :---- |
| 1 | 用本 patch §1 的全文替换主文档 §3.5 的所有小节 |
| 2 | 将本 patch §2 的 C.3 追加到主文档附录 C 末尾 |
| 3 | 主文档头部版本号：`v1.2` → `v1.3` |
| 4 | 删除本 patch 文档 |

**合并前置**：无。合并本身不依赖任何代码改动。

**合并后**：主文档成为 v1.3，patch 文档删除。B5 实现可以启动。

---

## 4. 变更记录

| 版本 | 日期 | 变更 |
| :---- | :---- | :---- |
| v1.3 patch | 2026-10-02 | §3.5 全文替换；附录 C.3 新增；seal_events 表结构含 chain_ready / chain_hash |

---

## 5. 编号更正说明

CTO 在实施指令中对 B4/B5 编号口误，导致 commit bb95e6e 使用「B4-1」标签。

按设计文档 §7.2 的正确编号：

- B4 = 数据封存（本 patch 修订对象）
- B5 = 导出/迁移（commit bb95e6e 的实质内容）

后续 commit 统一用设计文档编号，不再使用口误编号。

---

**本 patch 待合并。合并后删除。**
