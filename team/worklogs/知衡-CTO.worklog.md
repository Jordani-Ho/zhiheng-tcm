# 知衡（CTO） · worklog

## 2026-10-04 建立

- 本会话角色：CTO / 项目主管（技术全权，与发起人为合伙人关系）
- 权威文档：`docs/whitepaper-v1.1.md`（哲学）+ `docs/whitepaper-v2.1.md`（技术运营）
- 决策台账：`team/decisions/decision-log.md`（本会话建立）

---

## 2026-10-04 第一轮：板块摸查 + 决策台账建立

### 完成

1. **读全部权威文档**：白皮书 v1.1（167 行）、v2.1（2076 行）、`team/README.md`、3 份 worklog、三份组织参考文件（`H:\...\定稿\` 下的团队角色与分工 / 产品哲学 / 团队重构）。

2. **六路并行摸查全部板块代码**（只读，未跑 pytest）：
   - A 板块（Epic 3 学习闭环）：已闭环，但**前端零消费**三个端点
   - B 板块（数据主权）：B1a/B1b-1/B4/B5-1 有；**B2/B3 零代码**；架构偏离未登记
   - C 板块（社区规则）：**仅 M1 引荐链**；M2/M3/X1/X2 零；`chain_hash` 从不写入
   - D 板块（治理见证）：M2+M4 有，工程质量最好（RO 连接 + openapi 守护）；**M1/M3/M5 零**；**看的是假数据**
   - E 板块（去中心化）：**全零**；设计文档「已建表」清单 5 张表**根本不存在**
   - 阶段一四模块（Epic 1/2/4/5）：Epic 1/2/4 已实现（318 测试）；**Epic 5 废弃未同步到主计划**

3. **关键数据本人复核**（不采信摸查员转述）：
   - 数据库 32 张表；`evidence_package` / `student_level` / `state_judgment` / `community_external_tx` / `kangbi_ledger` / `student_rank_record` **均不存在**
   - `chain_ready` / `chain_hash` **仅** `seal_events` 与 `referral_chain` 真有；**无任何写 TRUE 的代码**（库内 `chain_ready=1` 计数 0）
   - `evidence_hash` 在 backend **零命中**
   - HTTP 端点 **122 条**（router 44 + `main.py` 内联 78）
   - 迁移 `0001`–`0008`；离线 SQL 产物缺 `0002`、`0008`

4. **测试实跑一次**：642 passed + 65 errors = 707。65 个错误根因 = 沙箱禁止 pytest 使用系统临时目录（`fixture setup` 阶段 `PermissionError`），**非代码问题**。改到工作区 basetemp 后 pytest 在收尾清理阶段被挡、未打印汇总行。→ **「707 全绿」未取得干净验证。**

5. **建 `team/decisions/decision-log.md`**（发起人批准 D-011）：
   - 回填 **D-001 ~ D-024**（含 C 板块 5 项产品判断 + T-1/T-2/T-10 裁决 + 本轮 10 项技术决策 + 2 项自纠）
   - 登记**未决事项 D-025 ~ D-030**（四条底线要件、信誉等级模型、撤回背书入宪、D 侧解封通知、主计划残留清理、白皮书 11 条内部矛盾）

6. **更新 `team/README.md`**：§五 角色清单对齐 D-021/D-012；§六 基线从 `ddb9fd3` 更新到 `bb5d0c7`，补规模数据与板块状态表。

7. **建本角色卡与 worklog**：`team/roles/知衡-CTO.md`。

### 发起人本轮的两个拍板

- **D-010**：第一次落地范围 = **一位老师带一位学生走通一次完整闭环**（A 选项）
- **D-011**：先建决策日志再开工

### 本轮自纠（已记入决策日志）

- **D-023**：此前给的「C 的 M3 依赖 T-2b」**判断不成立**——T-2b 是 M2 的依赖。教训：排序意图不得表述为硬依赖。
- **D-024**：一度报「板块端点未注册」——**误报**。新版 FastAPI 把 `include_router` 存为 `_IncludedRouter` 容器，不再展平进 `app.routes`。教训：查证工具的行为假设也要验证。

### 待办

- [ ] **D-029**：清理 `docs/development-plan-v1.md` 中 21 处已废概念（段位 / 存活门限）+ Epic 5 整节
- [ ] 清理段位代码残留（`witness_router._mock_levels` + `/levels` 端点、`WitnessApp` 的「段位变更」入口）
- [ ] 修正 E 设计文档「已建表」清单（D-013）+ `evidence_hash` 口径（D-014）
- [ ] 修正 B 设计文档把 `state_judgment` 当作已闭环交付的表述（D-008 连带）
- [ ] 在 v0.5 文件头加「已冻结」标记（D-005 连带）
- [ ] 建议发起人：为 MAP-xxx 与项目编号建一张对照表（D-021 连带）

### 待发起人决策

- **D-025** 信誉「等级」模型是否要定义（不定，C 的 M1 降级逻辑半残）
- **D-026** 四条协议底线的**判定要件**（**C 的 M2 成稿唯一缺口**）
- **D-027** 「撤回背书」是否写入白皮书（现 v2.1 零命中，代码已有两列）
- **D-030** 白皮书 v2.1 自身 11 条内部矛盾是否出 **v2.2 修订清单**
- **D-020 适用时点确认**：后端鉴权是「第一次落地前」还是「真人内测前」必须
- **六个板块负责人派任**（A / Epic 1 / Epic 2 / Epic 4 / B / D / E）

### 下次启动时读

- `team/decisions/decision-log.md`（**决策总表 + 未决事项**）
- `team/README.md` §六（当前基线）
- 本 worklog

### 环境异常（需发起人知悉）

三个目录**不可读、连删除都失败**，`git status` 每次报权限警告（退出码仍 0）：

- `backend/.pytest_cache`（历史遗留）
- `.pytest_tmp/`、`.pytest_tmp2/`（本轮跑测试时我新建的，已无法清理）

---

## 2026-10-04 第二轮：执行 D-029 及连带修正

发起人指示：「按你自己的默认节奏来行动吧」→ 执行决策日志中的默认动作（D-029 及连带项）。

### 完成：文档层（6 个文件）

| 文件 | 修正内容 | 依据 |
| :-- | :-- | :-- |
| `docs/development-plan-v1.md` | **主计划残留清理**：加「阅读前置」失效声明；§1.2 段位行作废；§1.3 加「现状」列（11 项实测）；§2 四阶段进度更新为实测（阶段一 40%→**90%**）；§3.1 目标去段位；§3.3 五个交付物→**四个**；D5 整节作废并留历史；§3.4 验收总表更新；**Epic 5 整节废除 + 原文留档**；独立子任务落地时机改写；技术决策 12 补实测现状；§6 阶段三去废概念；§8 优先级表标实测；§11 下一步重写 | D-002 / D-003 / D-010 / D-013 / D-015 / D-017 / D-022 |
| `docs/phase4-decentralization-design.md` | **E 板块「已建表」失真修正**：加阅读前置警告（含四路径核实结论）；§1.1 重建表清单（7 真 / 5 不存在）；`evidence_hash` 与身份公钥改判；§9.1 锚定清单逐行加待建/废弃标记 + 段位行作废；§9.2 交易层两表标待建；§9.2 对齐表 **4 行从「✅ 对齐」改判**（撤回背书/信誉等级/evidence_package/state_judgment）；基线 `80fca86`/`603` 更正为 `bb5d0c7`/`707` | D-013 / D-014 / D-017 / D-018 |
| `docs/phase2-data-sovereignty-design.md` | **B 板块「已闭环」失真修正**：加阅读前置警告（`state_judgment` 表不存在）；§0.4 依赖表 C 行改判；`TD-B-001` 前置条件 `[x]`→`[ ]`；登记「B1b-1 实现为服务端 API vs 设计称客户端本地存储」的架构偏离 | D-008 / D-013 |
| `docs/phase3-governance-design.md`（v0.5） | **加「🧊 已冻结」头部**：冻结依据 D-005、作废章节对照表（§4 存活门限 / §6 段位 / `/api/level/*`）、指向 v1 替代文件、§11.3 已改写说明 | D-005 / D-003 / D-002 / D-008 / D-007 |
| `team/decisions/decision-log.md` | 新增 **D-031**（段位代码残留：先改文档不动代码）、**D-032**（测试基线恢复列第一优先）、未决 **D-033**；总表与变更日志同步 | — |
| `team/README.md` | （第一轮已更新）§五 角色清单、§六 基线 | D-012 / D-021 |

### 完成：代码层（2 个文件，**最小改动**）

| 文件 | 改动 | 性质 |
| :-- | :-- | :-- |
| `backend/witness_router.py` | `_mock_levels()` 与 `GET /levels` 加**废弃 docstring**（依据 + 实测 + 为何暂不删） | **纯注释**，零行为变更 |
| `frontend/src/WitnessApp.tsx` | 导航项移除 `/levels`（「段位变更」），就地留注释说明 | 移一项，`ENDPOINTS` 两处 `.map` 无需改 |

**验证**：`npx tsc -b` 前端类型检查 **退出码 0**；`witness_router.py` AST 语法检查通过。

### 本轮的判断：为什么没删 `/levels` 端点

摸查发现 `/levels` **不是孤立残留**——它挂在 `backend/test_witness_router.py:58` 的 `test_T7_seals_levels_kangbi_ok`（循环断言三个端点）。**删端点 = 改测试基线**，而测试基线当前不可靠（65 setup errors 未解决）→ **在无可信黄金基线时动被测代码，风险大于收益**。故按 D-017 原意「改文档防误导」，把删除列为 **D-033**，待 **D-032**（测试基线恢复）解除后单独立项。

### 待办（更新）

- [x] ~~D-029 清理 `dev-plan` 已废概念 + Epic 5 整节~~
- [x] ~~修正 E 设计「已建表」清单（D-013）+ `evidence_hash` 口径（D-014）~~
- [x] ~~修正 B 设计把 `state_judgment` 当已闭环的表述（D-008 连带）~~
- [x] ~~在 v0.5 文件头加「已冻结」标记（D-005 连带）~~
- [x] ~~段位代码残留标注（D-031）~~
- [ ] **D-033**：删除 `/levels` 端点 + `_mock_levels()` + 同步改 `test_witness_router.py:58` —— **阻塞于 D-032**
- [ ] 修正 `docs/governance-witness-interface-contract.md` 的 `/readonly/levels` 等段位引用
- [ ] 修正 `docs/phase3-construction-outline.md`（整份旧五子项口径，须整体重写）
- [ ] 修正 `docs/epic1-template-design-v1.md:54` 的 `student_rank_record` 引用
- [ ] 登记 B1b-1 架构偏离进 `docs/tech-debt.md`（目前只在 B 设计文档头部标注）
- [ ] 修正 `TD-B-010` 与代码不符处（flag off 时老师端 tab 实为恒 5 个）
- [ ] 补 `docs/migrations/0002_*.sql` 与 `0008_*.sql` 离线产物
- [ ] 建议发起人：为 MAP-xxx 与项目编号建对照表（D-021 连带）

### 待发起人决策（未变 + 新增）

- **D-032** 🔴 ~~**测试基线恢复**（需授权：修 3 个不可读目录，或临时切完全权限）—— 阻塞一切验收与 D-033~~ → ✅ **本轮已解决，见第三轮**
- **D-026** 🔴 四条协议底线的判定要件（C 的 M2 成稿唯一缺口）
- **D-025** 信誉「等级」模型是否定义
- **D-020** 后端鉴权适用时点（第一次落地前 / 真人内测前）
- **D-027** 「撤回背书」是否入宪
- **D-030** 白皮书 v2.1 十一条内部矛盾是否出 v2.2 修订清单
- **板块负责人派任**：A / Epic 1 / Epic 2 / Epic 4 / B / D / E

---

## 2026-10-04 第三轮：取得第一份干净测试基线（D-032 关闭）

发起人指示：「我授权给你，技术上你什么都能做，包括动代码」→ 解除 D-032 的授权阻塞。

### 完成

1. **权限根因诊断（推翻了此前的判断）**
   - 用 DSH 的 Windows 沙箱权限诊断脚本检查 `.pytest_tmp` 及其全部父目录。
   - 结论 **`VERDICT=NOT_THIS_CLASS`**：三个目录**所有者是当前用户**、`WRITE_DAC` / `WRITE_OWNER` **均可用**、**无外来包条目**。
   - → **不是 Windows ACL 问题，是 DSH 沙箱本身的拦截。** 我此前「Windows 文件权限问题」的说法**不准确**，已在 D-032 更正。

2. **✅ 取得项目第一份干净测试基线**
   ```
   707 passed, 8 warnings in 809.68s (0:13:29)     退出码 0
   ```
   - 在沙箱外（`danger-full-access`）运行全量 `backend`。
   - 输出留档 `team/pytest-baseline.txt`（已 gitignore）。
   - 全程**无 `PermissionError`**。
   - 该基线**已覆盖本轮全部代码改动**（`witness_router.py` / `WitnessApp.tsx` 均在跑测试之前完成）→ 等效于一次完整回归。

3. **解开了 65 个错误的完整根因**
   - 沙箱**同时**拦截了两处 pytest 临时目录：系统 temp（`C:\...\dsh-*\pytest-of-DELL`）**与**工作区根 `pytest-of-DELL`。
   - 沙箱内运行时工作区根会留下 `pytest-of-DELL`，且**沙箱内不可读、不可删**。
   - → 立为**运营纪律**（写入角色卡第 6 条）：**pytest 必须在沙箱外运行。**

4. **环境彻底收拾干净**
   - 删除 `.pytest_tmp` / `.pytest_tmp2` / `pytest-of-DELL`（沙箱外）。
   - `git status` **权限警告从 3 条降为 0 条**。
   - `.gitignore` 补丁：`.pytest_cache/` / `backend/.pytest_cache/` / `.pytest_tmp*/` / `team/pytest-baseline.txt` / `team/acl-reports/` / `.obsidian/`。
   - **❌ 撤回一条误报（当场自纠）**：本轮一度认为「`backend/zhiheng.db` 受 git 跟踪、`.gitignore` 失效」→ **实测证否**：`git ls-files backend/zhiheng.db` 返回空；`git check-ignore -v` 退出码 0（规则生效）。
   - **全库安全核查（本轮顺带完成）**：`git ls-files` 的 **130 个被跟踪文件**中，**零个**数据库（`.db`/`.sqlite`）、**零个**密钥（`.key`/`.pem`）、**零个** `.env`、零个 `.bak-*`。
     → **生产库、测试库、`.env`（含 `DEEPSEEK_API_KEY`）、备份文件均未进版本库。** 远端为私有仓库 `github.com/Jordani-Ho/zhiheng-tcm`。

5. **文档同步**
   - `team/decisions/decision-log.md`：**D-032 关闭**（✅ 已解决），补完整解决过程与运营纪律。
   - `team/README.md` §六：测试基线段改为 **707 passed / 0 failed / 0 errors** + 沙箱运行纪律。
   - `team/roles/知衡-CTO.md`：纪律新增第 6/7/8 条（沙箱外跑测试、无基线不动被测代码、删除前确认绝对路径）。

### 待办（更新，含新增）

- [ ] **D-033**：删除废弃 `/levels` 端点 + `_mock_levels()` + 同步改 `test_witness_router.py:58` —— **D-032 已解除阻塞，现可执行**
- [ ] 修正 `docs/governance-witness-interface-contract.md` 的 `/readonly/levels` 等段位引用
- [ ] 修正 `docs/phase3-construction-outline.md`（整份旧五子项口径，须整体重写）
- [ ] 修正 `docs/epic1-template-design-v1.md:54` 的 `student_rank_record` 引用
- [ ] 登记 B1b-1 架构偏离进 `docs/tech-debt.md`（目前只在 B 设计文档头部标注）
- [ ] 修正 `TD-B-010` 与代码不符处（flag off 时老师端 tab 实为恒 5 个）
- [ ] 补 `docs/migrations/0002_*.sql` 与 `0008_*.sql` 离线产物
- [ ] 建议发起人：为 MAP-xxx 与项目编号建对照表（D-021 连带）

### 待发起人决策（更新）

- **D-026** 🔴 四条协议底线的判定要件（**C 的 M2 成稿唯一缺口**）
- **D-025** 信誉「等级」模型是否定义
- **D-020** 后端鉴权适用时点（第一次落地前 / 真人内测前）
- **D-027** 「撤回背书」是否入宪
- **D-030** 白皮书 v2.1 十一条内部矛盾是否出 v2.2 修订清单
- **板块负责人派任**：A / Epic 1 / Epic 2 / Epic 4 / B / D / E

### 下次启动时读

- `team/decisions/decision-log.md`（**决策总表 + 未决事项**）
- `team/README.md` §六（当前基线 + 沙箱纪律）
- 本 worklog
