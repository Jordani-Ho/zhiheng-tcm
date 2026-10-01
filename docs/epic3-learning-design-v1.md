# Epic 3 设计：学习闭环 v1

> 状态：**step 3.0 只读调研已验收（CTO 2026-09-30 批复 A1–A8）**、**step 3.1 已交付**（设计定稿 + 迁移 `0006` + 离线产物 + 0006 守护用例）。本文件是 Epic 3 的**设计唯一真相源**；step 3.1 交付范围内**零业务实现** —— 哈希链纯函数属 step 3.2、事件接线属 step 3.3、③ 指标转正属 step 3.4、接口与前端属 step 3.5（§10）。
> 对齐：白皮书 2.0 第五章 5.3（原文 §1.5）、`docs/development-plan-v1.md` §3.3-D3 / §5-Epic 3 / §4-技术决策 5（本地哈希链预留）/ 决策 12（治理见证入口）。
> **DDL 唯一真相源 = 迁移 `0006_add_agent_learning_events`**（沿用 Epic 1 §1.1 纪律：`database.py::init_db()` **不**重复写一份 DDL）。
> 语言纪律：叙述用简体；**所有 UI 文案一律繁体古字**（沿用 Epic 1 §13.4 / 决策 11）。
> 铁律：AI 永不诊断、永不开方、永不签字（决策 3 / Epic 2 §2.1）在本 Epic 内**一字不动**；阶段一**不微调模型权重**，只做规则统计与模板偏好（§0.3-3）。
> 施工顺序：3.1（本步）→ 3.2 → 3.3 → 3.4 → 3.5（§10）。

---

## 0. 术语与范围

### 0.1 术语表

| 术语 | 定义 | 实现载体 |
| :---- | :---- | :---- |
| 学习事件 | 学习闭环四环节上发生的一次可留痕动作（配置 → 生成 → 修改 → 学习 → 更新，共 5 类） | 新表 `agent_learning_events`（§2.1） |
| 链节（link） | 某位老师链上的**一行**事件；「链节指纹」= 该行的 `prev_hash` 值 | `agent_learning_events` 行（§2.4） |
| 链节指纹 | 本行业务字段 + 上一条链节指纹的 sha256（A3）；列名沿用 `prev_hash` | `prev_hash` 列（§2.4） |
| 载荷哈希 | `sha256(canonical_json(payload))`；覆盖**载荷字节** | `payload_hash` 列（§2.3） |
| 创世哈希 | 空链的「上一条链节指纹」= 64 个 ASCII `0`；**常量** | `GENESIS_HASH`（§2.4） |
| 单链 / 按老师单链 | 每位老师**各自**一条从 `seq=1` 起的链；不同老师的链互不串联 | `UNIQUE(teacher_name, seq)`（§2.5） |
| 定位键 | 用于把事件定位到具体业务对象的键；**明文姓名不入链** | `patient_name_hash` / `draft_id` / `template_id` / `lineage_id`（§2.2 / §5.2） |
| 投影列 | 表列中**与 payload 顶层键同名**的那些 —— 权威源恒为 `payload_json`，列为可检索投影 | §2.2 两分法 |
| 链元列 | 表列中**不属于** payload 的那些（`id` / `payload_json` / `payload_hash` / `prev_hash`） | §2.2 两分法 |
| 结构覆盖率 | ③ 指标的真实语义：已发布 `inquiry` 模板的**结构**被问诊实际覆盖的比例（A1） | §5.1 |
| 见证入口 | 9 席治理见证人的只读总览入口（决策 12，Epic 4 之后）；其「证据模式」复用本文件口径 | §4 |

### 0.2 范围

**做**（对齐 `development-plan-v1.md` §3.3-D3 与 §5-Epic 3）

1. 新建 `agent_learning_events` 事件表（§2.1）+ 按老师单链的 `seq`（§2.5）。
2. 事件流接线：`template_configured` → `draft_generated` → `draft_modified` → `learning_event_emitted` → `agent_updated`（§3.1；落地属 3.3）。
3. 本地哈希链：`payload_hash` + `prev_hash`（链节指纹），可自证未篡改（§2.3 / §2.4；落地属 3.2）。
4. 差异记录：**字段级 diff + 措辞变化**两类（A8；落地属 3.3）。
5. 学习结果更新**统计指标**（含 ③ 转正），**不**改模型权重（§5；落地属 3.4）。
6. 一致率统计接口（**独立端点**，A7）+ 事件流 / 链校验只读接口（§7；落地属 3.5）。
7. 前端：③ 卡片加副标题「（結構覆蓋率）」（A1；落地属 3.5）。

**不做**（防范围蔓延）

- **证型变化 / 方剂变化**两类差异（A8：挂 backlog → TD-017，§11-1）。
- 模型微调 / 权重更新 / 训练（阶段一不做，只做规则统计与模板偏好）。
- 把 `agent_stage_log` 纳入同链（A6：**不纳入**，§3.3）。
- 跨老师 / 跨师门的「全局链」（本 Epic 恒「按老师单链」，A2）。
- 上链（公链 / 联盟链）、加密、思想指纹、导出迁移（阶段二）。
- `inquiry` 模板「只存不用」的接线改造（`test_inquiry_template_not_wired_in_epic1` 钉住；3.4 只做 ③ 的结构覆盖率统计，**不**改问诊生成路径）。
- 段位系统（Epic 5）；治理见证入口（独立子任务，Epic 4 之后）。

### 0.3 三条不可动不变量（本 Epic 红线）

1. **AI 三铁律**：永不诊断、永不开方、永不签字（决策 3）。事件流只记录「发生了什么」，**不产出**任何临床结论。
2. **事件表只增不改不删**：无 `UPDATE` / 无 `DELETE` / 无 HTTP 写入端点（§7）；`payload_hash` 与 `prev_hash` 一经写入即不可重算（§4 口径冻结）。
3. **不微调模型权重**：学习结果只更新统计指标（①②③ 与事件计数），**不得**回写模型参数（§3.3-D3 原文）。

---

## 1. 依据：A1–A8 裁决与 step 3.1 范围

### 1.1 八项裁决逐条落点

| # | 裁决（CTO 2026-09-30，逐字要点） | 落点 |
| :-- | :---- | :---- |
| A1 | ③ **转正**：语义定位「**問診模板結構覆蓋率**」；**键名保留** `inquiry_preference_consistency`（不改）；三处落地 = 设计文档明确 + 后端加 `basis: "structural_coverage"` + 前端加副标题「（結構覆蓋率）」 | 本文件 §5；3.4 / 3.5 施工 |
| A2 | `seq`：**按老师单链**；`UNIQUE(teacher_name, seq)` | §2.5；迁移 `0006` 的 `INDEX_DDL[0]`（**唯一索引**，非表内约束 —— 见 §2.6） |
| A3 | `prev_hash`：**链节指纹**；`prev_hash = sha256(canonical_json({seq, event_type, payload_hash, prev_hash}))` | §2.4；`GENESIS_HASH` 已冻结在迁移 `0006` |
| A4 | flag：新 flag `LEARNING_ENABLED`；照三套惯例（`on`/`1`/`true`/`yes`、现读、默认 off） | §6；`FLAG_NAME` / `FLAG_VALUES` / `FLAG_DEFAULT` 已冻结在迁移 `0006` |
| A5 | payload 定位键：`patient_name_hash = sha256(patient_name)[:16]` + `draft_id` / `template_id` **明文** + `lineage_id`（**仅审计标注**）。理由：**数据主权归患者，明文姓名不入链** | §2.2（列）+ §2.3（payload 键）+ §5.2；`PATIENT_NAME_HASH_LEN = 16` 已冻结 |
| A6 | `agent_stage_log` **不**纳入同链 | §3.3；迁移 `0006` **零 `ALTER TABLE`**（守护用例 `test_0006_source_keeps_epic3_redlines`） |
| A7 | API：**新文件** `learning_api.py`；统计接口**独立端点** | §7；3.5 施工 |
| A8 | 差异记录：**先做**「字段级 diff + 措辞变化」两类；「证型变化 + 方剂变化」**挂 backlog（TD-017）** | §3.2 / §11-1 |

**两条施工约束**（CTO 同批）：① **3.2 必须先于 3.3**（哈希链纯函数先于事件接线）；② **3.3 与 3.4 串行**（同改 `agent_stage_service.py`）。→ §10 施工表已按此排序。

### 1.2 本步（3.1）范围与 CTO 的「12 项要求」对照

本步**只做**：设计定稿（本文件）+ 迁移 `0006` + 离线产物 + 0006 守护用例。
**不写**：服务层 / 库层 / 接口 / 前端；**不改** Epic 2 已验收代码。

| # | CTO 的 12 项要求 | 本文件章节 |
| :-- | :---- | :---- |
| 1 | 表字段全集（含 A5 的定位键口径） | §2.1（DDL）+ **§2.2（字段全集 + 两分法）** |
| 2 | 事件类型枚举（5 类） | §3.1 |
| 3 | canonical 口径逐字（`sort_keys` / `separators` / `ensure_ascii` / 参与哈希的键集合） | §2.3 |
| 4 | genesis 常量（`GENESIS_HASH`） | §2.4 |
| 5 | `seq` 语义（按老师单调） | §2.5 |
| 6 | 与 `agent_stage_log` 的边界复述（引用 epic2 §1.3） | §3.3 |
| 7 | 与 `epic4:620` 的复用承诺 + 口径冻结声明 | §4 |
| 8 | ③ 口径与已知局限（结构覆盖率，非一致性） | §5 |
| 9 | flag 裁决（`LEARNING_ENABLED`） | §6 |
| 10 | API 契约 | §7 |
| 11 | 回退方案 | §8 |
| 12 | §5.6 交叉风险备忘（零产品语义降级 + 不借道 `permission_denied`） | §9 |

### 1.3 调研阶段的两项高风险发现（本设计已对应处置）

| 发现 | 风险 | 处置 |
| :---- | :---- | :---- |
| `epic4:620` 承诺见证入口复用 Epic 3 的哈希口径，但其施工在 Epic 4 **之后** | **高**：Epic 3 若先自定口径并落数据，见证入口只能「将错就错」 | §4 的**口径冻结声明**（变更须 CTO 单独裁决 + 数据迁移方案） |
| `inquiry` 模板**只存不用**，且 `TEN_QUESTIONS`（简体）与 `_DEFAULT_INQUIRY_FIELDS`（繁體）**label 简繁不匹配** → ③ 实为「事后结构覆盖率」而非「同源一致性」 | **高**：③ 极易被读成「智能体遵循了老师偏好」 | A1 转正时**明确定位为结构覆盖率**：加 `basis: "structural_coverage"` + 前端副标题 + §5.3 逐条写明局限 |

---

## 2. 数据底座：`agent_learning_events`

### 2.1 表 DDL（唯一真相源 = 迁移 `0006_add_agent_learning_events`）

```sql
CREATE TABLE IF NOT EXISTS agent_learning_events (
    id                INTEGER PRIMARY KEY AUTOINCREMENT,
    teacher_name      TEXT NOT NULL,
    seq               INTEGER NOT NULL,
    event_type        TEXT NOT NULL,
    lineage_id        TEXT NOT NULL DEFAULT '',
    patient_name_hash TEXT NOT NULL DEFAULT '',
    draft_id          INTEGER DEFAULT 0,
    template_id       INTEGER DEFAULT 0,
    payload_json      TEXT NOT NULL DEFAULT '{}',
    payload_hash      TEXT NOT NULL DEFAULT '',
    prev_hash         TEXT NOT NULL DEFAULT '',
    created_at        TEXT NOT NULL DEFAULT ''
);
```

- 全部 TEXT / INTEGER，**零外键、零 CHECK**（与存量 24+ 张表同构，Epic 1 §1.4 纪律）。
- **本文件不重复维护 DDL**：上面这段是**引用**；唯一真相源 = 迁移 `0006` 的 `TABLE_DDL` 常量，两者由 `test_0006_offline_sql_artifact_matches_migration` 逐字对齐。
- `database.py::init_db()` **不**建本表（新表一律走迁移 —— 0003 / 0005 同款纪律）。

### 2.2 表字段全集（含 A5 定位键口径）

**两分法（本设计的关键不变式）**：

| 组 | 列 | 与 payload 的关系 |
| :---- | :---- | :---- |
| **投影列** | `teacher_name` / `seq` / `event_type` / `lineage_id` / `patient_name_hash` / `draft_id` / `template_id` / `created_at` | 每一个都有一个**同名 payload 顶层键**（§2.3）。**权威源恒为 `payload_json`，列为可检索 / 可审计的投影**（「单一真相源 + 只读投影」是本库既有惯用法，cf. `agent_stage_service.generation_degraded` 对闸门的只读投影） |
| **链元列** | `id` / `payload_json` / `payload_hash` / `prev_hash` | **不属于** payload；由 step 3.2 的哈希链纯函数产出 / 参与哈希计算 |

逐列口径：

| 列 | 类型 / 约束 | 口径 |
| :---- | :---- | :---- |
| `id` | INTEGER PRIMARY KEY AUTOINCREMENT | SQLite 物理行号（全局递增）。**不参与任何链计算**（与 `seq` 解耦，§2.5） |
| `teacher_name` | TEXT NOT NULL | 链主体（= `teachers.name`；`teacher_name` 即身份，与全库鉴权口径一致）。**空值不允许** —— `UNIQUE(teacher_name, seq)` 对 NULL 不去重，故显式 NOT NULL。（相对 0003 的 `agent_stage_log.teacher_name TEXT` 是「可空 → 不可空」的**收紧**；理由：无主体的链节无意义） |
| `seq` | INTEGER NOT NULL | 该老师链上的**单调序号**，从 `1` 起、步长 1（§2.5） |
| `event_type` | TEXT NOT NULL | 5 类之一（§3.1）。非法值由服务层白名单拦截（**不加 DB 级 CHECK** —— 存量全库无 CHECK） |
| `lineage_id` | TEXT NOT NULL DEFAULT `''` | **【A5】** 定位键之一，**仅作审计标注**（`''` = 未归属，沿用 Epic 4 §2.4 哨兵语义）。**不参与**读写过滤 —— 本表**不**做师门过滤（对齐 Epic 4 裁决③-C 对 `agent_stage_log.lineage_id` 的定性） |
| `patient_name_hash` | TEXT NOT NULL DEFAULT `''` | **【A5】** `sha256(patient_name)[:16]`（**前 16 个十六进制字符**）。**明文姓名不入链、不入表** —— 理由：数据主权归患者（A5 原文）。空串 = 该事件不涉及具体患者 |
| `draft_id` | INTEGER DEFAULT 0 | **【A5】** 定位键**明文**。`0` = 不适用（与全库「0 = 未记录」惯例一致，cf. `drafts.template_id`） |
| `template_id` | INTEGER DEFAULT 0 | **【A5】** 定位键**明文**。`0` = 不适用 |
| `payload_json` | TEXT NOT NULL DEFAULT `'{}'` | `canonical_json(payload)` 的**落库字节**（§2.3）。**哈希覆盖对象** |
| `payload_hash` | TEXT NOT NULL DEFAULT `''` | `sha256(payload_json 字节)` 的小写十六进制（64 字符） |
| `prev_hash` | TEXT NOT NULL DEFAULT `''` | **链节指纹**（A3，§2.4）。首节 = 以 `GENESIS_HASH` 为输入的指纹 |
| `created_at` | TEXT NOT NULL DEFAULT `''` | ISO 字符串（全库惯例：`database.py` / 迁移 0001 同源） |

**「列 == payload 值」不变式**：8 个投影列的落库值**必须**与 `payload_json` 里同名键的值一致，且由**同事务、同一代码路径**写入（step 3.3 的强制要求，由 3.3 用例钉住）。违背即产生「两处真相」。

> **A5 口径留痕（待 3.3 前确认）**：A5 把四个定位键定为「**payload 定位键**」。本设计把它们**同时**落在列与 payload 上（列 = 投影）。若 CTO 要求**只存列、不入 payload**，须在 3.3 前裁定 —— 此时表为空、改动零成本（§11-4）。

### 2.3 canonical 口径（逐字冻结）

**唯一合法实现**（step 3.2 的 `learning_service.canonical_json()` 必须逐参对齐）：

```python
import hashlib
import json


def canonical_json(payload):
    """payload → 唯一字节形式（键排序、无多余空白、中文原样保留）。"""
    return json.dumps(
        payload,
        sort_keys=True,          # 键序唯一化（dict 插入顺序不影响字节）
        separators=(",", ":"),   # 无多余空白（默认 ", " / ": " 会引入空格）
        ensure_ascii=False,      # 中文原样保留（缺省会输出 \uXXXX → 与 UI 文案口径不符）
    )


def sha256_hex(text):
    """文本 → sha256 小写十六进制（64 字符）。"""
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


payload_hash = sha256_hex(canonical_json(payload))
```

**参与哈希的键集合 = payload 的顶层 9 键**（顺序无关，`sort_keys` 负责唯一化）：

| 键 | 类型 | 来源 |
| :---- | :---- | :---- |
| `seq` | int | 列 `seq` |
| `event_type` | str | 列 `event_type` |
| `teacher_name` | str | 列 `teacher_name` |
| `created_at` | str | 列 `created_at`（ISO） |
| `lineage_id` | str | 列 `lineage_id`（**A5**，仅审计标注） |
| `patient_name_hash` | str | 列 `patient_name_hash`（**A5**） |
| `draft_id` | int | 列 `draft_id`（**A5**） |
| `template_id` | int | 列 `template_id`（**A5**） |
| `detail` | object | **事件特化载荷**（只在 payload 里，**不单列** —— 5 类事件形状异构，单列会变宽表） |

**三条硬规则**：

1. **9 键恒存在**：缺业务值时用**空值哨兵**（`''` / `0` / `{}`），**不得省略键** —— `sort_keys` 只排序、不补键；键集漂移 = 整条链验不过。
2. **payload 内不得出现 `None`**：`json.dumps(None)` = `null`，与 `''` / `0` 是不同字节；任何一侧漂移都会让链验不过。全库的「空值哨兵」惯例（`''` / `0`）在此**强制适用**。
3. **数值类型归一**：`seq` / `draft_id` / `template_id` 一律 `int`（禁 `float` / 字符串数字）。`detail` 内数值同理。

**`detail` 的演进自由（重要）**：本设计**冻结顶层 9 键**，但 `detail` 的**内部键集合**允许随事件类型演进（3.3 定稿）—— 因为链承诺的是「**`payload_json` 的字节未被改**」，**不是**「schema 不变」。新增 / 调整 `detail` 键只影响**其后的新事件**，**既有链节仍逐字节可验**。

**UTF-8**：`sha256` 的输入恒为 `canonical_json(...).encode("utf-8")`（`ensure_ascii=False` 后必须**显式**指定 UTF-8，禁用平台默认编码）。

### 2.4 A3 链节指纹 + `GENESIS_HASH`

```python
GENESIS_HASH = "0" * 64        # 常量：空链的「上一条链节指纹」（64 个 ASCII '0'）


def link_fingerprint(seq, event_type, payload_hash, prev_link):
    """A3 链节指纹 = 本行业务字段 + 上一条链节指纹。"""
    return sha256_hex(canonical_json({
        "seq": seq,
        "event_type": event_type,
        "payload_hash": payload_hash,
        "prev_hash": prev_link,
    }))
```

**落库规则**：

- 第 1 条（`seq = 1`）：`row.prev_hash = link_fingerprint(1, et, ph, GENESIS_HASH)`
- 第 n 条：`row.prev_hash = link_fingerprint(n, et, ph, row_{n-1}.prev_hash)`

**列名命名留痕**：`prev_hash` 的**值语义 = 本行的链节指纹**（既接收「上一节」的输入，也承载本节的累积结果），并非「上一行的哈希」的字面含义。命名沿用 `development-plan-v1.md` 技术决策 5 与 §3.3-D3 的既有表述（`prev_hash + payload_hash`）→ **命名冻结不改**（A3 逐字给的就是这个公式）。

**校验算法（单遍、`seq` 升序、零额外状态）**：

```python
def verify_chain(rows):        # rows: 按 seq 升序、同一老师
    expected_seq = 1
    expected_prev = GENESIS_HASH
    for row in rows:
        if row.seq != expected_seq:                                # 跳号 / 乱序
            return False, row.seq, "seq_gap"
        if sha256_hex(row.payload_json) != row.payload_hash:        # 第 1 层：载荷字节未被改
            return False, row.seq, "payload_tampered"
        if row.prev_hash != link_fingerprint(
            row.seq, row.event_type, row.payload_hash, expected_prev
        ):                                                          # 第 2 层：链断
            return False, row.seq, "link_broken"
        expected_seq += 1
        expected_prev = row.prev_hash
    return True, None, "ok"
```

**覆盖力（设计承诺）**：单行篡改 `payload_json` / `seq` / `event_type` → 该行指纹必变；删除中间行 → 其后首个仍存在的行指纹必变（`expected_prev` 链断）；换序 → `seq` 与 `expected_prev` 双错。

**未覆盖（明示残余，本步不解决）**：8 个**投影列**若被**单独**修改（而不动 `payload_json`），上面第 1 / 2 层校验**都不会发现** —— 因为 `payload_hash` 覆盖的是 `payload_json` 的字节。→ §11-3 登记为 **3.2 的裁决项**：可选强校验 = 从投影列 + `detail` 重建 canonical payload，与 `payload_json` **逐字节比对**（即钉住 §2.2 的「列 == payload 值」不变式）。

### 2.5 A2 `seq` 语义：按老师单链

1. **单链**：每位老师**各自**一条链，`seq` 从 **1** 起、步长 **1**，**不跳号、不复用、不回退**。不同老师的链**互不串联** —— 老师 A 的 `seq = 1` 恒以 `GENESIS_HASH` 起算，与老师 B 的链无关。
2. **分配口径**（3.3 实现）：同一事务内 `SELECT COALESCE(MAX(seq), 0) + 1 FROM agent_learning_events WHERE teacher_name = ?` → 立即 `INSERT`。
3. **并发兜底**：`UNIQUE(teacher_name, seq)`（§2.6）→ 冲突即事务失败（**重试或显式报错**），**绝不静默丢事件**。
4. **与 `id` 解耦**：`id` 是全局递增的物理行号，`seq` 是**按老师各自从 1 起**的逻辑序号；`id` 不参与链计算（§2.2）。
5. **flag off**：不写事件、不分配 `seq`（§6）→ 打开再关闭后 `seq` **不补空洞**（链的连续性只承诺「已落库的行之间」）。

### 2.6 索引（迁移 `0006` 的 `INDEX_DDL`）

| 索引 | 定义 | 用途 / 依据 |
| :---- | :---- | :---- |
| `uq_agent_learning_events_teacher_seq` | `UNIQUE (teacher_name, seq)` | **【A2】** 按老师单链的**硬约束**（§2.5-3）。这里用**显式命名的唯一索引**而非表内 `UNIQUE` 约束 —— 与 0001 的 `uq_templates_active_one` 同款（表内约束会生成不可命名的 `sqlite_autoindex_*`，`downgrade` 无法单独回收；命名索引可被 `sqlite_master` 探测与单独 `DROP`） |
| `idx_agent_learning_events_teacher_time` | `(teacher_name, created_at DESC)` | 读路径：某老师**最近事件倒序** + 时间窗（见证入口「证据模式」的快照筛选）。照 0003 的 `idx_agent_stage_log_teacher_time` 同款。（`(teacher_name, seq)` 已能服务 seq 序读，故**不**再建重复索引 —— 索引克制，Epic 1 §1.3） |

**只建 2 个索引**：本表唯一高频读路径是「某老师的事件流」，两个索引已全覆盖；`event_type` / `draft_id` 维度**暂不建**（单机单老师量级，不预支）。触发条件 = 出现按 `event_type` 的全表扫描热点。

---

## 3. 事件类型枚举（5 类）+ 与 `agent_stage_log` 的边界

### 3.1 五类事件（`EVENT_TYPES`，已冻结在迁移 `0006`）

| # | `event_type` | 触发时点（既有业务路径） | 环节 | 落地步 |
| :-- | :---- | :---- | :---- | :---- |
| 1 | `template_configured` | 老师**发布 / 归档 / 启用**某类模板（`template_api.py` 的 publish `:244` / archive `:266` / activate `:281`） | 配置 | 3.3 |
| 2 | `draft_generated` | 智能体**生成**病历草案并落库（`database.insert_draft()`，`database.py:811-847`；AI 原始输出快照见 `_draft_ai_snapshot:760-776`） | 生成 | 3.3 |
| 3 | `draft_modified` | 老师**修改**草案内容（`database.update_draft_content()`，`database.py:888-892`）—— **四环节中唯一零既有落点，须新增「改 4」**（§10） | 修改 | 3.3 |
| 4 | `learning_event_emitted` | 一次学习结算**被产出**（读过样本、算过差异、产出可更新的统计结论）—— 即「本次学习发生了什么」的**汇总节** | 学习 | 3.3 |
| 5 | `agent_updated` | 学习结果**落实到统计指标 / 阶段视图**（`agent_stage_service._evaluate()`，`:2061`；不写模型权重）—— 即「智能体因此变成了什么」的**收口节** | 更新 | 3.3 / 3.4 |

**顺序语义**：`template_configured` → `draft_generated` → `draft_modified` → `learning_event_emitted` → `agent_updated` 是**同一次学习闭环**上的**逻辑先后**（`development-plan-v1.md` §3.3-D3 原文），**不是**表级约束（**不加** CHECK、不加触发器；实际写入由各业务路径各自触发，可能缺环 —— 缺环是允许的：老师可能只配了模板而从未生成过草案）。

**枚举冻结**：5 个字符串 = 契约，**不得**新增 / 改名 / 缩写；`EVENT_TYPES` 是唯一白名单（服务层校验，测试逐字对齐）。

### 3.2 payload 顶层 9 键与事件特化 `detail`（骨架；`detail` 键集归 3.3 定稿）

payload 的**非 `detail`** 八个键是固定投影（§2.2 / §2.3）；`detail` 按事件类型填：

| `event_type` | `detail` 骨架（**3.3 定稿**，此处为设计意图） |
| :---- | :---- |
| `template_configured` | `{"template_id": int, "template_type": str, "version": int, "from_status": str, "to_status": str}`（复用 Epic 1 §3.5 的模板事件形状） |
| `draft_generated` | `{"template_version": int, "content_hash": str, "degraded": bool}`（`degraded` = 该草案是否产自观察期降级骨架，对齐 Epic 2 §5.6 / TD-015 的样本识别口径） |
| `draft_modified` | `{"field_diff": [{"field": str, "before_hash": str, "after_hash": str}], "wording_changed": bool}` —— **A8 的第一类（字段级 diff）+ 第二类（措辞变化）**。**明文的「修改前后文本」不入链**（只放 `*_hash`：正文属患者数据，沿用 A5 的「明文不入链」取向） |
| `learning_event_emitted` | `{"source_event_types": [str], "difference_kinds": [str], "sample_count": int}` |
| `agent_updated` | `{"from_stage": str, "to_stage": str, "capability": str, "metrics_hash": str}`（`metrics_hash` = 本次评估结果快照的哈希，快照本体留在 `agent_stage_state.last_metrics_json`，**不**复制进链） |

**A8 的边界（逐字）**：本 Epic **先做**「字段级 diff + 措辞变化」两类；「**证型变化** + **方剂变化**」**不做**、挂 backlog（**TD-017**，§11-1）。

### 3.3 A6 边界复述：与 `agent_stage_log` 分属两张表、两条流

**引用 `docs/epic2-agent-stage-design-v1.md` §1.3 注（逐字）**：

> **与 Epic 3 的边界（防重叠）**：本表是**治理审计**（阶段 / 权限 / 配置）；Epic 3 的 `agent_learning_events` 是**学习事件流**（生成 / 修改 / 哈希链）。Epic 2 **不建哈希链**，只保证本表「只增」。Epic 3 如需把本表纳入链，属其范围，不影响本表结构。

**A6 裁决 = 不纳入**。四条理由：

1. **生命周期不同**：`agent_stage_log` 允许「导出留档后清空」（0003 的 downgrade 安全闸正是给这条留出口）；链节一旦清空即**断链**（`seq` 空洞 + `expected_prev` 链断）→ 两个「可清空」的语义不可共存。
2. **事件性质不同**：治理审计回答「谁在什么时候被拒 / 被升级 / 被配置」；学习证据回答「老师的修改如何改变统计」。混读会让证据面被治理噪音稀释。
3. **时机不同**：`agent_stage_log` 建于迁移 `0003`（2026-09-28），早于本链的 `seq` / `GENESIS_HASH` 口径；纳入须为**历史行**回填 `seq` 与链节指纹 —— **事后造链**，其见证价值为负（无法证明历史行未被改过）。
4. **§5.6 同族**：`agent_stage_log` 的 `evaluation` 等事件由**正常业务流程高频**产生；纳入链会让链节膨胀，并与「链节 = 可向见证人出示的证据」这一定位冲突。

**结论**：迁移 `0006` **零 `ALTER TABLE`**（不碰 `agent_stage_log` 一个字节），由用例 `test_0006_source_keeps_epic3_redlines` 做源码级守护。

---

## 4. 与 `epic4-lineage-design-v1.md:620` 的复用承诺 + 口径冻结声明

**上游承诺（`docs/epic4-lineage-design-v1.md:620`，逐字）**：

> `| Epic 3（施工中） | agent_learning_events 哈希快照口径 —— 见证入口的「证据模式」复用该口径（独立子任务时引用，本 Epic 不动） |`

**① 复用承诺（本 Epic 的对外义务）**：治理见证入口（`development-plan-v1.md` 技术决策 12；落地时机 = Epic 4 之后、Epic 5 之前，独立子任务）的「**证据模式**」（生成带哈希快照的证据）**复用本文件 §2.3 / §2.4 的口径**，**不另立第二套** hash / canonical / 链节指纹实现。

**② 口径冻结声明（CTO 2026-09-30，逐字）**：

> **「一经落地即为见证入口复用基准，变更须 CTO 单独裁决 + 数据迁移方案」**

展开：

| 项 | 内容 |
| :---- | :---- |
| **「一经落地」的时点** | = 迁移 `0006` 已执行 **且** 首个事件已写入（step 3.3 落地）之后。**在此之前（即今天）**本文件口径仍是**设计条文**，改动只走设计评审，无数据迁移成本 |
| **受冻结的项** | canonical 参数（`sort_keys` / `separators` / `ensure_ascii`）、`GENESIS_HASH` 取值、链节指纹公式（A3）、`seq` 语义（A2）、哈希算法（`sha256`）、payload **顶层 9 键**集合 |
| **变更流程** | 必须 (**a**) **CTO 单独裁决** + (**b**) 附**数据迁移方案**（存量链节如何重算 / 如何标注断代，例如新增 `chain_version` 列并设过渡期双写） |
| **明令禁止** | **静默重算**既有 `payload_hash` / `prev_hash`（那等于篡改证据本身）。链的「不可改」是它的唯一价值 |
| **不在冻结内** | `detail` 的内部键集合（§2.3）、`EVENT_TYPES` 的**落地时点**（哪一步接哪条）、API 形态（§7）—— 这些可演进 |

**③ 与 0005 的对齐（口径唯一来源的既有范式）**：Epic 4 的做法是 `lineage_service.py` 用 `importlib` 从迁移 `0005` 取 `slugify` / `lineage_id_for`（口径唯一来源 = 迁移）。Epic 3 的**同款纪律**（写入 3.2 的验收清单）：

- `learning_service.GENESIS_HASH == 迁移 0006 的 GENESIS_HASH`（逐字）
- `learning_service.PAYLOAD_TOP_LEVEL_KEYS == 迁移 0006 的同名常量`（顺序无关、集合相等）
- `learning_service.EVENT_TYPES == 迁移 0006 的 EVENT_TYPES`（**逐字含顺序**）
- `learning_service.PATIENT_NAME_HASH_LEN == 16` 且 `canonical_json` 的三个参数逐字等于迁移 0006 的 `CANONICAL_*`
- 反过来：迁移 `0006` 的常量是**冻结见证**，**不**被服务层改写（3.2 的用例从**两边**断言，防单侧漂移）

---

## 5. 指标 ③ 口径（A1 转正）与已知局限

### 5.1 语义定位与口径

- **语义定位（A1 逐字）**：③ = 「**問診模板結構覆蓋率**」（UI 文案：繁体古字）。
- **口径**：③ = 该老师**已发布（`status='active'`）的 `inquiry` 模板**的**结构字段集合**，被**智能体问诊实际产出**的结构所覆盖的比例：

  ```
  ③ = |模板结构键 ∩ 实际问诊结构键| / |模板结构键|
  ```

  分母 = `schema_json` 里的字段集合（与 `template_service._DEFAULT_INQUIRY_FIELDS`（`:95-106`）同源的字段键口径）；分子 = 其中**在已落库问诊结构中出现过**的键数。**无样本 / 无 active `inquiry` 模板 → `null` 占位**（沿用 Epic 2 的 `_METRICS_DEFERRED`（`:1587`）/ `_blank_metrics_snapshot`（`:1615`）语义，**不变**）。
- **是不是「就绪」的判据不变**：③ **有样本**时返回 `float`（0..1）；**无样本**时返回 `null` —— 转正的是「**有样本时的口径**」，不是「无样本时的占位」。
- **计算位置不变**：仍在 `agent_stage_service._evaluate()`（`:2061`）里算，仍是 `metrics` 三键之一；**不新表、不新缓存、不复制一份计算**。

### 5.2 键名与返回体（A1）

| 项 | 裁决 | 说明 |
| :---- | :---- | :---- |
| **键名** | **保留** `inquiry_preference_consistency`（**不改名**） | 理由：改名 = 变更 Epic 2 **已验收**契约（后端 `_blank_metrics_snapshot` / `agent_stage_api` / 前端 `AgentStagePanel.tsx:162` `:482` `:1176-1180` 的键读点全都要动，且会波及既有断言） |
| **后端标记** | **新增** `basis: "structural_coverage"`（结论：3.4 施工） | 与 ③ 同级、同返回体内。语义修正**由标记承担**，不由改名承担 |
| **前端副标题** | ③ 卡片加副标题「**（結構覆蓋率）**」（结论：3.5 施工） | 位置：`frontend/src/AgentStagePanel.tsx` 的 ③ 卡标题行（UI 文案一律繁体古字，Epic 1 §13.4） |

**返回体形状（③ 部分，3.4 定稿）**：

```json
{
  "inquiry_preference_consistency": 0.75,
  "inquiry_preference_consistency_basis": "structural_coverage"
}
```

> `basis` 的**承载形式**（并列键 `*_basis` vs 嵌进 ③ 值对象）属 **3.4 的实现细节**；本设计只冻结**取值** `"structural_coverage"` 与「必须机器可读」这两点。若 3.4 选择并列键，键名须形如 `inquiry_preference_consistency_basis`（与主键成对，前端好读）。

### 5.3 已知局限（**高风险，必须与 §7 / §9 一起读**）

1. **③ 不是「同源一致性」**：`inquiry` 模板目前**只存不用** —— 智能体问诊**不读**该模板（由 `backend/test_templates.py:747` 的 `test_inquiry_template_not_wired_in_epic1` 钉住）；且 `agent.TEN_QUESTIONS`（`:318`，简体标签）与 `template_service._DEFAULT_INQUIRY_FIELDS`（`:95-106`，繁體标签）**简繁不匹配** → 今日实现里两边**没有共同口径**。
   → 因此 ③ 只能算「**事后结构覆盖率**」（拿模板结构去对**已产出**的问诊文本做覆盖统计），**不能**被读成「智能体遵循了老师的问诊偏好」。这正是 A1 把 ③ 定位为「結構覆蓋率」而非「一致性」的原因。
2. **键名是历史命名**：`inquiry_preference_consistency` 的字面读法与真实语义**不一致** —— 该不一致**已知、已登记**，修正靠 `basis` + 副标题，**不靠改名**（A1）。
3. **依赖文本结构识别**：覆盖统计需要从问诊文本里识别结构键 → 识别口径（关键词 / 段落标题 / 十问标签）属 **3.4 的实现细节**，且**必须**在 3.4 用例里写明「识别失败的样本如何计」（预期：计入分母、不计入分子，且返回体带样本数，便于老师自判可信度）。
4. **口径升级的触发条件**：若将来把 `inquiry` 模板**真正接线**（智能体按模板提问），③ 应**重新裁决**（届时可升级为真正的「一致性」并更换 `basis` 取值）→ 登记在 §11-7。

### 5.4 三处落地（A1 逐条点名）

| # | 面 | 内容 | 落地步 |
| :-- | :---- | :---- | :---- |
| 1 | **设计文档** | 本节（语义定位 + 口径 + 局限） | **本步已交付** |
| 2 | **后端** | ③ 的返回体加 `basis: "structural_coverage"` | 3.4 |
| 3 | **前端** | ③ 卡片副标题「（結構覆蓋率）」 | 3.5 |

### 5.5 不变更项（防顺手改坏）

- `agent_stage_service._METRICS_DEFERRED`（`:1587`）/ `_blank_metrics_snapshot`（`:1615`）的 **①② 语义一字不动**。
- ①② 指标的样本池与阈值口径**不动**（`database.get_draft_samples` `:2147`、`_draft_ai_snapshot` `:760-776`）。
- `/api/agent/stage` 的 `metrics` **三键名字与形状**不动（Epic 2 已验收契约）→ 3.4 只**追加** `basis`。
- **唯一允许的既有断言改写（已披露）**：`test_inquiry_metric_is_null_placeholder` —— ③ 从「占位 `null`」转正为「结构覆盖率」后该用例必然失效，**3.4 施工时必须改写**，且为**唯一**一处既有断言变更（其余既有用例全绿不改）。

---

## 6. feature flag（A4）

| 项 | 裁决 |
| :---- | :---- |
| **flag 名** | `LEARNING_ENABLED` |
| **真值集合** | `("on", "1", "true", "yes")` —— 比较前 `strip().lower()`（大小写不敏感） |
| **默认值** | `off`（未设置 = off） |
| **读取方式** | **每次调用现读**环境变量（`os.environ.get(...)`）：不读库、不打日志、不抛异常、**不缓存**（便于灰度切换 / 测试，不必重启 uvicorn） |
| **实现落点** | `backend/learning_service.py::learning_enabled()`（3.2 建文件），**逐字照抄** `template_service.template_api_enabled()` / `agent_stage_service.agent_stage_enabled()`（`:137-163`）/ `lineage_service.lineage_enabled()` 三套惯例 |
| **常量冻结** | 迁移 `0006` 的 `FLAG_NAME` / `FLAG_VALUES` / `FLAG_DEFAULT`（3.2 用例与之一致） |

**flag off 语义（与今天 1:1）**：

1. **不写** `agent_learning_events` 一行、**不分配** `seq`、**不算** ③、**不改**任何既有响应字段。
2. `/api/agent/learning*` 全部 **404 `learning_disabled`**（前端据此**整块不渲染**）。
3. 既有链路（草案生成 / 修改 / 签字 / 模板 / 阶段 / 师门）**逐字节不变**。

**flag 与「存储就绪」是两件事**（Epic 2 §7.1-⑫ / Epic 4 同款纪律，**不得合并成一个布尔**）：

| 状态 | 门卫结论 | 前端表现 |
| :---- | :---- | :---- |
| flag off | 404 `learning_disabled` | 功能没开 → **整块不渲染** |
| flag on + 表缺失（迁移没跑） | 503 `learning_store_unavailable` | 迁移没跑 → **红字提示请运维** |

**门卫顺序**（3.5 落地）：flag → 存储就绪 → 鉴权（`teacher_required` / `teacher_mismatch`）→ 业务校验。倒过来的话 flag off 时会漏出 400 / 403，违反「flag off → 全部 404」。

---

## 7. API 契约（A7）

### 7.1 文件与挂载

| 项 | 裁决 |
| :---- | :---- |
| **文件** | **新建** `backend/learning_api.py`（**不**挂到 `agent_stage_api.py` / `template_api.py` / `lineage_api.py` 里） |
| **挂载** | `main.py` 增一行 `app.include_router(learning_api.router)` + 一个异常处理器（照 `template_api` / `agent_stage_api` / `lineage_api` 同款） |
| **前缀** | `/api/agent/learning` |
| **统计接口** | **独立端点**（A7）：**不**塞进 `/api/agent/stage` 的返回体 |
| **写端点** | **无**（本 Epic 无 POST / PUT / PATCH / DELETE；事件由既有业务路径自动产生，§3.1） |

### 7.2 端点表

| 端点 | 方法 | 用途 | 关键查询参数 | 2xx 返回体（要点） |
| :---- | :---- | :---- | :---- | :---- |
| `/api/agent/learning/events` | GET | 事件流（链节列表，按 `seq` 排序） | `teacher_name` / `teacher_id` / `limit`（默认 50、上限 500）/ `order`（默认 `desc`，可选 `asc`） | `{"events": [{id, seq, event_type, patient_name_hash, draft_id, template_id, payload_hash, prev_hash, created_at, payload}], "total": int, "verified": bool}` |
| `/api/agent/learning/chain/verify` | GET | 链校验（§2.4 的单遍算法） | `teacher_name` / `teacher_id` / `limit`（默认全量） | `{"ok": bool, "checked": int, "first_bad_seq": int\|null, "reason": str}`（`reason` ∈ `ok` / `seq_gap` / `payload_tampered` / `link_broken`） |
| `/api/agent/learning/metrics` | GET | **统计独立端点**（A7）：①②③ + 窗口与样本明细 | `teacher_name` / `teacher_id` / `window_days`（默认 30） | `{"metrics": {template_match, modification_consistency, inquiry_preference_consistency}, "inquiry_preference_consistency_basis": "structural_coverage", "samples": {…}, "window_days": int, "evaluated_at": str}` |

### 7.3 错误码契约（8 码，照 `LINEAGE_ERROR_STATUS` / `AGENT_STAGE_ERROR_STATUS` 同款形态）

| 码 | HTTP | 触发 |
| :---- | :---- | :---- |
| `learning_disabled` | 404 | flag off（门卫第一道，§6） |
| `learning_store_unavailable` | 503 | flag on 但 `agent_learning_events` 未就绪（迁移没跑） |
| `teacher_required` | 400 | 缺 `teacher_name` / `teacher_id` |
| `teacher_mismatch` | 403 | 两位老师不一致（与全库鉴权口径一致） |
| `window_invalid` | 400 | `window_days` 非法（≤0 / 非整数 / 超上限） |
| `limit_invalid` | 400 | `limit` 非法（≤0 / 超上限 500） |
| `chain_broken` | 409 | `chain/verify` 检出断链（**不是** 500：链断是**数据事实**，不是服务故障） |
| `chain_write_failed` | 503 | 事件写入失败（**仅日志 + 该码**；**不**回退业务输出，§9-①） |

错误体形状：`{"detail": {"error": <code>, "msg": <中文提示>}}`（与 `template_api._fail` / `lineage_api._fail` / `agent_stage_api._fail` **逐键相同**，前端不必分两套解析）。

### 7.4 关系声明（防「两处真相」）

1. `/api/agent/stage` 的 `metrics` **三键不动**（Epic 2 已验收契约）；`/api/agent/learning/metrics` 是**同一份计算**的**带明细视图**（多出窗口 / 样本数 / `basis`）。
2. **「同一个判断只许有一份实现」**：两个端点必须共用 `agent_stage_service._evaluate()`（`:2061`）的**同一份计算** —— 3.5 的用例必须断言「两处取到的 ③ 值逐字相等（同一时刻、同一 flag 状态）」，**禁止**在新文件里复制一份指标算法。
3. **只读纪律**：三个端点全为 **GET**；`learning_api.py` 内**零**写 SQL、**零** `UPDATE` / `DELETE`（事件写入**不**在本文件，在 `database.py` 的 best-effort 钩子里，§10）。
4. **对齐 Epic 4 的隔离口径**：本 Epic 的接口**不**要求 `lineage_id`（本表**不做**师门过滤，`lineage_id` 仅审计标注 —— 与 `agent_stage_log` 同款定性，Epic 4 裁决③-C）。若将来要按师门检索事件，须单独立项（§11-5）。

---

## 8. 回退方案

### 8.1 三步（顺序不可换）

| 步 | 动作 | 效果 | 说明 |
| :-- | :---- | :---- | :---- |
| **① 首选：flag off** | `LEARNING_ENABLED=off`（或不设置） | 新接口 404、事件停写、③ 不再算、既有链路一字不改 | **不删表、不回退版本号**。与 `AGENT_STAGE_ENABLED` / `LINEAGE_ENABLED` / `TEMPLATE_API_ENABLED` 同款「flag 回退优先」纪律 |
| **② 可选：结构回收** | `alembic downgrade 0005_add_lineage` | 只 `DROP` `agent_learning_events` 表与 2 个索引 | **零 `DROP COLUMN`、零既有表改动**（TD-003 新口径）。**带安全闸**（§8.2） |
| **③ 数据面** | 无需动作 | —— | 本 revision **未触碰任何既有表 / 列 / 行**（迁移 `0006` 零 `ALTER TABLE`）→ 病历 / 草案 / 模板 / 师门数据无需回滚 |

### 8.2 downgrade 安全闸（与 0003 / 0005 同款）

| 条件 | 行为 |
| :---- | :---- |
| `agent_learning_events` **不存在** | 打印「已是目标状态」→ 直接输出 `DROP INDEX` ×2 + `DROP TABLE`（**可重跑**） |
| 表存在且 **0 行** | 直接回收结构 |
| 表存在且 **有事件行** | **抛 `RuntimeError` 中止**：「downgrade 已中止：agent_learning_events 中有 N 行学习事件（**哈希链节，不可重建**）→ 请先导出留档…若只是要停用功能，优先用 flag 回退（`LEARNING_ENABLED=off`），**不必**删表」 |

**安全闸的理由（已写进迁移注释）**：链节是**不可重建**的见证基准 —— `seq` / `prev_hash` / `payload_hash` 一旦随表删除，哈希链的「自证未篡改」能力即**永久丧失**（无法从业务数据反推）。
**离线模式**：安全闸与结构校验**无法离线判定** → 离线产物只打印人工确认提示（段 2/2 已注释）。

### 8.3 灰度顺序（3.5 收口时执行）

① **迁移先上**（flag off → 零行为变化）→ ② **代码上**（flag off → 仍零行为变化）→ ③ 单老师 lab 打开 `LEARNING_ENABLED=on` → ④ 观察：事件流写入 + `chain/verify` 恒 `ok` + ③ 有样本时的数值合理 → ⑤ 全量。

### 8.4 已知运维注意

- **TD-006（既有，不修）**：`alembic/env.py` 未做 DDL 事务化 → 抛出安全闸异常时 `alembic_version` **不前进**，但 `CREATE TABLE` / `CREATE INDEX` 可能残留。本 revision **幂等**（`IF NOT EXISTS` + 名字探测）→ 「修好触发条件后**重跑即收敛**」。
- **导出命令**（运维手册）：`SELECT * FROM agent_learning_events ORDER BY teacher_name, seq;`（或直接备份整个库文件）。
- **不可回退的内容**：已写入的链节**不会**因 downgrade 而「回到未写状态」；flag off 也不删历史链节（链只增）。

---

## 9. §5.6 交叉风险备忘（Epic 3 追加条）

> `docs/epic2-agent-stage-design-v1.md` §5.6 是**固定小节**，纪律原文：**「任何 Epic 新增『产品语义降级』时，必须先读本节；新增『产品语义降级』时，须在本节追加一条。」** 本节按同一纪律登记（**新增内容写在 Epic 3 设计文档内**，不改 Epic 2 已验收文档）。

**先复述 §5.6-④「未来提醒（新增「降级」类语义时必须逐条自问）」的五条**（Epic 3 逐条对照）：

| §5.6-④ 的五条自问 | Epic 3 的答案 |
| :---- | :---- |
| ④-1 区分「权限拒绝」与「功能降级」 | Epic 3 **两者都不新增**：事件写入是**旁路观测**，不是闸门、不是降级（见「声明一」） |
| ④-2 「产品语义的降级」不得经权限闸门的审计面 | Epic 3 的 5 类事件**一律不写** `permission_denied`（见「声明二」） |
| ④-3 凡「高频自动路径 × 计入判据的审计」，先算一次耦合后的行为 | `draft_modified` 可能高频，但**不参与**升阶判定（见 E3 备忘条 ②）；③ 转正后**不依赖事件条数**（见 E3 备忘条 ①） |
| ④-4 同族检查清单：新事件名是否参与升阶判定 | Epic 3 的 5 类事件**都不**参与（它们是**证据流**，不是**判据流**）；③ 转正**新增**的是一个参与判定的**指标**（不是事件）→ 见 E3 备忘条 ① |
| ④-5 口径一致性（只对 `generate_draft` 做降级的证明） | **不适用**（Epic 3 不做任何能力降级） |

**声明一：Epic 3 零产品语义降级。**

本 Epic **不新增任何**「能力降级」路径。区分两类「不产出」：

| | 权限拒绝 / 功能降级（§5.6 的对象） | Epic 3 的 flag off |
| :---- | :---- | :---- |
| 语义 | 「你不被允许」/「此刻这条路径不产出」 | 「整个功能没开」 |
| 留痕 | 前者必留痕（`permission_denied`）、后者**不得**借道权限面 | **不留痕**（不写任何事件） |
| 频次 | 可按次触发 | **全局一次性**（配置层） |

→ §5.6 的自锁机制（`产品语义的降级` × `越权留痕` × `观察期每收一次陈述即触发一次`）在 Epic 3 **无适用面**。

**并且（本 Epic 的铁律）**：**事件写入失败不得回退业务输出** —— 3.3 的接线一律 **best-effort**（失败只打日志，可选在返回体标 `chain_write_failed`），与 `database.sign_draft()` 末尾的 `on_draft_signed(teacher_name)` 同口径（Epic 2 §4.2 改 2b：钩子内部出错**不得**回滚老师已落定的决策）。**禁止**为了「保证事件写入」而回滚草案 / 修改 / 签字。

**声明二：事件写绝不借道 `permission_denied`。**

1. 5 类事件**没有一类**写入 `agent_stage_log`（§3.3 的 A6 边界 + 迁移 `0006` 零 `ALTER TABLE`）。
2. 更**不写** `permission_denied` —— 按 §5.6-④-4 的同族检查清单，`permission_denied` **参与**升阶判定（`permission_denied_in_window` → 阻断升阶），任何「借道它做记录」的行为都会**污染判据面**。
3. **3.3 与 3.4 的用例必须含源码级 + 行为级双守护**：事件接线处**零** `_stage_audit` 调用、**零** `permission_denied` 写入（照 Epic 2 ㉓ 组 `test_generation_degraded_never_writes_audit` 的双守护范式）。

**E3 备忘条 ①（Epic 3 新增自问，登记给 3.4；对应 §5.6-④-4）**：「③ 转正 = 把一个**由正常业务流程产生**的指标接入 `can_recommend`」—— 必须显式回答：

- **③ 未达标是否阻断升阶？** → **3.4 的裁决项**，本步只登记。
- **不得**通过「借道权限面」实现阻断（例如把「③ 未达标」伪装成一次能力拒绝）—— 那是 §5.6 的**原始缺陷形态**。
- 实现方式只能是**指标面**：进 `_evaluate()`（`:2061`）的判据集合（与 ①② 同款），或**不接入**（仅展示）。

**E3 备忘条 ②（高频面复查；对应 §5.6-④-3）**：`draft_modified` 由老师**每次编辑草案**产生（可能高频）→ 但 `agent_learning_events` **不参与**任何升阶判定；3.4 若把 ③ 接入判定，须复查「③ 的计算是否会被高频事件放大」。**本设计规定**：③ 只依赖「已发布 `inquiry` 模板结构」+「已落库问诊结构」，**不依赖事件条数** → 该不变式由 3.4 用例钉住。

---

## 10. 施工拆解与顺序

| step | 范围 | 前置 | 状态 |
| :-- | :---- | :---- | :---- |
| **3.1** | **设计定稿（本文件）+ 迁移 `0006` + 离线产物 + 0006 守护用例** | — | **本步已交付** |
| 3.2 | 哈希链**纯函数**（`canonical_json` / `sha256_hex` / `link_fingerprint` / `patient_name_hash` / `seq` 分配的纯部分）+ `learning_service.py` 骨架（`learning_enabled()` / `learning_store_ready()`）+ **常量与迁移 `0006` 双向对齐用例**（§4-③） | 3.1 | 待放行 |
| 3.3 | **事件接线**：改 1 / 改 2 / 改 3 复用既有钩子 + **新增「改 4」**（`draft_modified`）+ `learning_event_emitted` / `agent_updated` 的写入 | **3.2 必须先于 3.3**（CTO 约束 1） | 待放行 |
| 3.4 | **③ 转正**：`basis: "structural_coverage"` + 「③ 是否参与升阶判定」的显式裁决（§9-③）+ 改写 `test_inquiry_metric_is_null_placeholder`（唯一既有断言变更） | **与 3.3 串行**（**同改 `agent_stage_service.py`**，CTO 约束 2） | 待放行 |
| 3.5 | `learning_api.py`（§7）+ 前端副标题（A1）+ 全量回归 | 3.4 | 待放行 |

### 10.1 3.3 的钩子纪律（**红线**）

1. **复用唯一钩子入口**：`database._call_agent_stage_hook()`（`database.py:779-808`）是**全库唯一**的「库层 → 服务层」钩子转发点（`test_agent_stage.py:1602` 断言其调用点 `count == 1`）。**改 1 / 改 2 / 改 3 一律复用**这个入口，**禁止**新增第二个转发点。
2. **唯一需要新增的库层落点 = 改 4**：`database.update_draft_content()`（`database.py:888-892`）是**三行纯 UPDATE**，被 Epic 2 §5.1 红线③ 保护 → 只允许在其**末尾追加** best-effort 钩子调用，**不得**改动既有 UPDATE 语句文本、不得改其返回语义。
3. **`draft_modified` 是四环节中唯一零既有落点的环节** → 这是本 Epic 唯一「新增业务路径接线」的地方，其余三处是「复用既有钩子 + 追加一条事件」。
4. **best-effort**：钩子内部异常**必须**自行吞掉并只打日志（§9-声明一），**绝不**回滚老师的修改 / 生成 / 签字。

---

## 11. 挂账与未决

| # | 事项 | 处置 |
| :-- | :---- | :---- |
| 1 | **TD-017（待 CTO 登记）**：A8 的第二类差异 —— **证型变化** / **方剂变化** —— **本 Epic 不做** | **挂 backlog**。理由：证型 / 方剂属**临床语义**，识别需要术语表 + 白话映射，且铁律「AI 永不诊断」要求方剂识别**不得**产出诊断语义；与 Epic 5 段位 / 术语表建设耦合。触发条件 = Epic 5 术语表落地，或老师显式要求「证型变化可查」 |
| 2 | **3.3 裁决项**：payload 的 `detail` 键集合 | 顶层 9 键**已冻结**（§2.3）；`detail` 内部键随事件类型演进（不破坏既有链 —— 链只承诺「`payload_json` 字节未被改」，不承诺「schema 不变」）。键集骨架见 §3.2 |
| 3 | **3.2 裁决项**：是否启用「从投影列 + `detail` 重建 canonical payload」**强校验** | 用于抓「列被单改、`payload_json` 未改」这类篡改（§2.4「未覆盖」段）。不启用则残余风险**已知并已登记** |
| 4 | **A5 口径留痕**：四个定位键**同时**存在「列」与「payload 顶层键」 | 本设计的定性：**列 = payload 键的可检索投影，权威源恒为 payload**（§2.2）。若 CTO 要求改为「只存列、不入 payload」，须在 **3.3 前**裁定 —— 此时表为空、改动零成本 |
| 5 | 是否按师门检索事件（`agent_learning_events` 目前**零师门过滤**，`lineage_id` 仅审计标注） | **不做**（与 `agent_stage_log` 同款定性，Epic 4 裁决③-C）。触发条件 = 见证入口要求「按师门出证据」→ 届时单独立项（含索引评估） |
| 6 | **Epic 2 唯一允许的既有断言改写（已披露）** | `test_inquiry_metric_is_null_placeholder` —— 3.4 施工时**必须**改写，且为**唯一**一处既有断言变更（§5.5） |
| 7 | ③ 口径升级（若 `inquiry` 模板将来真正接线） | **重新裁决**：可升级为真正的「一致性」并更换 `basis` 取值（§5.3-4） |

---

## 附录 A：step 3.1 交付物清单

| 交付物 | 路径 | 要点 |
| :---- | :---- | :---- |
| **设计定稿** | `docs/epic3-learning-design-v1.md`（本文件） | §1.2 对照 CTO 的 12 项要求；§10 / §11 是后续四步的施工与裁决清单 |
| **迁移 0006** | `backend/alembic/versions/0006_add_agent_learning_events.py` | `down_revision = "0005_add_lineage"`；1 张表 + 2 个索引（含 A2 的唯一索引）；**零 `ALTER TABLE`**；可重跑（`IF NOT EXISTS` + 名字 + 列集合收尾校验）；downgrade 只回收结构 + **安全闸**；口径常量（`GENESIS_HASH` / `CANONICAL_*` / `PAYLOAD_TOP_LEVEL_KEYS` / `EVENT_TYPES` / `PATIENT_NAME_HASH_LEN` / `FLAG_*`）冻结在内 |
| **离线产物** | `docs/migrations/0006_add_agent_learning_events.sql` | 与迁移内联常量**逐字一致**；**无参数 / 无时间戳 / 不读库** → 可逐字节复现（0005 的种子 / 回填产物做不到这点） |
| **0006 守护用例** | `backend/test_migrations.py`（追加 0006 组） | 照 0005 十条范式：源码红线 / 口径契约 / 建表建索引 + UNIQUE 生效 / 幂等重跑 / 往返 / downgrade 安全闸 + 只回收结构 / `init_db()` 全链 / **不动 Epic 2 + Epic 4 既有结构** / 离线产物一致性 / 口径 ↔ 设计文档字面量 |
| **本步不做** | 服务层 / 库层 / 接口 / 前端 | 归 3.2 / 3.3 / 3.4 / 3.5（§10） |

**回退步骤（本步交付物自身的回退）**：见 §8 —— ① `LEARNING_ENABLED=off`（flag 回退，首选）→ ② `alembic downgrade 0005_add_lineage`（只回收 1 张表 + 2 个索引；有事件行时安全闸中止）→ ③ 数据面无需动作。

## 附录 B：上游依据文件（引用不复制）

| 来源 | 引用点 |
| :---- | :---- |
| `docs/backlog-white-paper-v2.1.md` | 第五章 5.3 学习闭环原文 |
| `docs/development-plan-v1.md` | §3.3-D3（5 类事件流 + `prev_hash + payload_hash` + 差异 4 类 + 阶段一不微调）、§5-Epic 3（子任务与回退）、§3.4（验收总表）、§4-技术决策 3（AI 三铁律）/ 5（本地哈希链预留）/ 9（pytest + 权限矩阵单测）/ 11（繁体 UI）/ 12（治理见证入口） |
| `docs/epic2-agent-stage-design-v1.md` | §1.3 注（与 Epic 3 的边界，§3.3 逐字引用）、§3.2（①② 指标与样本池）、§5.1 红线③（`update_draft_content` 保护）、§5.6（交叉风险备忘，§9 逐条对照）、§7.1-⑫（flag 与「存储就绪」不得合并）、§7.3（回退顺序） |
| `docs/epic4-lineage-design-v1.md` | `:620`（见证入口复用承诺，§4 逐字引用）、§2.4（`''` = 未归属哨兵）、§5.3（阶段恒老师维度）、裁决③-C（`lineage_id` 仅审计标注）、裁决④（downgrade 只回收结构） |
| `docs/epic1-template-design-v1.md` | §1.1（DDL 唯一真相源 = 迁移）、§1.3（索引克制）、§1.4（零 FK / 零 CHECK）、§3.5（模板事件形状）、§13.4（繁体 UI） |
| `docs/tech-debt.md` | TD-003（downgrade 新口径，0006 沿用）、TD-006（DDL 不事务化，回退后重跑即收敛）、TD-015（降级样本与指标面，`draft_generated.detail.degraded` 对齐）、TD-016（离线产物无守护 → 本条即 0006 的守护） |
| 后端实现（**只读引用**，不在本步改动） | `agent_stage_service.py`（`_METRICS_DEFERRED:1587` / `_blank_metrics_snapshot:1615` / `_evaluate:2061` / ①② 指标 `:1342` `:1443` / flag `:137-163`）、`database.py`（`update_draft_content:888-892` / `insert_draft:811-847` / `sign_draft:894+` / `_call_agent_stage_hook:779-808` / `_draft_ai_snapshot:760-776` / `get_draft_samples:2147`）、`template_api.py`（publish `:244` / archive `:266` / activate `:281`）、`template_service.py`（`_DEFAULT_INQUIRY_FIELDS:95-106`）、`agent.py`（`TEN_QUESTIONS:318`） |
| 测试（**只读引用**） | `test_templates.py:747`（`test_inquiry_template_not_wired_in_epic1`）、`test_agent_stage.py:1602`（`_call_agent_stage_hook` 调用点 `count == 1`）、`frontend/src/AgentStagePanel.tsx:162` `:482` `:1176-1180`（③ 键读点） |
