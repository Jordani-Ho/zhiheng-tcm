# Epic 3 闭环报告 v1：学习闭环

作者：知衡（发起人）
版本：1.0
日期：2026-10-01
范围：Epic 3 全流程（3.1 – 3.5）

---

## 一、Epic 3 目标

建立「学习闭环」：把智能体的每一次学习事件写成一条**可校驗的哈希鏈**，
使师承的演化过程可追溯、不可篡改。

四条核心不变量（设计文档 §0.3 三条 + 本 Epic 补充一条）：

1. **三条铁律不动**：AI 永不诊断 / 永不开方 / 永不签字。
2. **flag off = 与今天 1:1**：`LEARNING_ENABLED` 默认 off，off 时既有链路逐字节不变。
3. **数据主权归患者**：明文姓名不入链，`patient_name_hash = sha256(name)[:16]`。
4. **同一判断只有一份实现**：`/api/agent/learning/metrics` 与 `/api/agent/stage` 的 ③
   必须来自同一份计算（快照），禁止在新文件里复制指标算法。

---

## 二、施工子步与交付物

| 子步 | 交付物 | 状态 | commit |
| :--- | :--- | :--- | :--- |
| **3.1** | 设计定稿 + 迁移 `0006_add_agent_learning_events` + 离线产物 + 0006 守护用例 | ✅ 闭环 | 见 HEAD `3adc75d` 之前的 commit 链 |
| **3.2** | 哈希链纯函数（`canonical_json` / `sha256_hex` / `compute_link_hash` / `compute_patient_name_hash`）+ `learning_service.py` 骨架（`learning_enabled()` / `learning_store_ready()`）+ 常量与迁移双向对齐用例 | ✅ 闭环 | 同上 |
| **3.3-a~f** | 事件接线（改 1 / 改 2 / 改 3 / 改 4）+ `learning_event_emitted` / `agent_updated` 写入 + 白名单冻结 + 转发点唯一守护 | ✅ 闭环 | 同上（HEAD 之前 `bdf5be5`） |
| **3.4** | ③ 指标转正（`inquiry_preference_consistency` 从 `null` → `structural_coverage` 对象） | ✅ 闭环 | `ea69d48` |
| **3.5** | `learning_api.py` 三端点 + 前端 ③ 数值卡 + 类型修正 | ✅ 闭环 | `3adc75d` |

---

## 三、验收结果

### 3.1 测试演进

| 阶段 | passed | failed | 说明 |
| :--- | :--- | :--- | :--- |
| 3.3-f 收口（HEAD `bdf5be5`） | 511 | 0 | 本 Epic 起点 |
| 3.4-a/b 完成后 | 600 | 0 | ③ 转正 + 三处断言更新 |
| 3.5-a 完成后 | 603 | 0 | 后端三端点 + 3 个新测试 |
| **Epic 3 终结** | **603** | **0** | — |

### 3.2 前端构建

- `tsc -b && vite build`：✅ 通过
- 产物：`dist/index.html` 0.51 kB / `dist/assets/*.js` 432.24 kB（gzip 121.63 kB）

### 3.3 守护测试

- 硬约束守护全部绿：
  - `test_learning_service_references_stay_on_the_wiring_whitelist`（`learning_service` 引用白名单）
  - `test_database_to_service_import_stays_inside_function_bodies`（延迟 import）
  - `test_require_capability_body_has_no_capability_branches`（能力判定零硬编码）
  - 迁移 0006 双向口径对齐
  - `agent_stage_service.py` 唯一向上写路径守护

---

## 四、关键裁决记录

### 4.1 ③ 指标的语义（CTO 2026-10-01 裁决）

**③ 语义 = 「問診模板結構覆蓋率」，非「同源一致性」。**

- `basis` 字段恒为 `"structural_coverage"`（机器可读的语义标识）
- 数据源 = `complaints` + `templates(type='inquiry')`（不引入新表）
- 归一化复用 `_normalize_metric_text`
- 覆盖判定 = 「inquiry 模板的每个 label，是否在其名下 complaint 里被提及」（跨样本累计）

### 4.2 ③ 的无数据返回口径（CTO 2026-10-01 裁决）

| 情况 | ③ 返回值 | metrics_reason ③ |
| :--- | :--- | :--- |
| 无 active `inquiry` 模板 | `null` | `deferred_to_epic3`（保持） |
| 有 active 模板，complaints 样本数 = 0 | `0.0` | `no_complaints_samples` |
| 有 active 模板 + 有样本 | `0..1` | 空 dict（正常） |

核心口径：**「有 active inquiry 模板即不 null」**，而非「永不 null」。
无參照系時 `null` 語義誠實。

### 4.3 ③ 是否进入 `can_recommend`（CTO 2026-10-01 裁决）

**③ 不进入 `can_recommend`。** 本步不做 blocker 化，留 Epic 4/5 单独裁决。

### 4.4 前端展示（与 ①② 同构）

- ③ 数值卡与 ①② 同组件、同样式
- 副标题恒为「（結構覆蓋率）」
- 值域映射：
  - `null` → 显示「—」（无 active 模板）
  - `0.0` → 显示 `0%`（有模板无样本）
  - `0~1` → 显示百分比 + 样本数

### 4.5 `learning_api.py` 三端点（设计文档 §7.2）

| 端点 | 方法 | 用途 |
| :--- | :--- | :--- |
| `/api/agent/learning/events` | GET | 事件流（链节列表，按 seq 排序） |
| `/api/agent/learning/chain/verify` | GET | 链校验（单遍算法，全量） |
| `/api/agent/learning/metrics` | GET | 统计独立端点（读快照，不重算） |

- 前缀：`/api/agent/learning`
- 8 个错误码：`learning_disabled`(404) / `learning_store_unavailable`(503) /
  `teacher_required`(400) / `teacher_mismatch`(403) / `window_invalid`(400) /
  `limit_invalid`(400) / `chain_broken`(409) / `chain_write_failed`(503)
- 门卫顺序：flag → 存储就绪 → 鉴权 → 业务校验
- **零写 SQL**：事件写入在 `database.py` 的 best-effort 钩子，不在本文件

---

## 五、遗留与挂账

| 编号 | 描述 | 状态 |
| :--- | :--- | :--- |
| TD-017 | 差异记录：「证型变化 + 方剂变化」两类挂 backlog（A8 先做「字段级 diff + 措辞变化」两类） | 挂账 |
| TD-018 | `lineage_service` 自己写 SQL（Epic 4 偏离，本 Epic 不跟随） | 已登记 |
| TD-019 | 注释去行号化（3.3-f 收口已兑现） | 已闭环 |
| §11-3 | 强校驗（从投影列 + detail 重建 canonical payload 逐字节比对） | 未获放行，待裁決 |
| §11-5 | 按师门检索学习事件（`lineage_id` 仅审计标注，不做师门过滤） | 单独立项 |

---

## 六、下一步

Epic 3 闭环后，项目进入 **板块 B：阶段二数据主权落地**：

- 加密 / 思想指纹 / 监护模式 / 导出 / 封存
- 预计 5-7 步

---

## 七、签署

- 作者：知衡（发起人）
- CTO：Claude（会话内 CTO 身份）
- 执行：Cline（IDE 内 AI 助手）
- 日期：2026-10-01
- HEAD：`3adc75d`
