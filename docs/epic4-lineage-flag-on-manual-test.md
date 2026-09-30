# Epic 4 · flag on 手工自測腳本（批 3 回歸 · 清單 ⑥⑦）

> 適用：Epic 4「多師管理（師門歸屬與隔離）」批 1（ErrorBoundary + 4+2 處讀接口降級）與
> 批 2（就緒信號 + 就緒門 + 依賴成對）合入後，**只做人工瀏覽器驗收**。
> 本文**不含**任何 `npm` / `pytest` 步驟；自動化回歸仍由 `backend/test_lineage.py` 負責。
>
> 本輪前提（留痕）：批 3 原提案的單行修改（`App.tsx` `lineageEnabled` → `lineageReady`）已**回退**，
> 現行 `frontend/src/App.tsx:2237` 為 `if (lineageEnabled && !currentRole.includes('老师'))`；
> `git status --short` 應**無輸出**（工作樹與 HEAD 逐字節一致）。
> 故本腳本同時是「§4.4 flag off 零行為變化」契約未被破壞的現場證據。

---

## 0. 前置（每次執行前都要做一遍）

### 0.1 環境與啟動命令

```powershell
# 終端 A：後端（flag on）
cd d:\projects\zhiheng-tcm\backend
$env:LINEAGE_ENABLED = 'on'
python -m uvicorn main:app --host 0.0.0.0 --port 8000 --reload
```

```powershell
# 終端 B：前端
cd d:\projects\zhiheng-tcm\frontend
npm run dev
```

瀏覽器開 <http://localhost:5173>（`frontend/vite.config.ts` 把 `/api` 代理到 `127.0.0.1:8000`）。

⚠️ **flag 是「進程級環境變量 + 每次調用現讀」（`backend/lineage_service.py:39-47`）**：
在**已經跑著**的終端裡新開一個 PowerShell 改 `$env:` **不會**影響那個 uvicorn 進程。
要切 flag，必須「停掉 uvicorn → 設 env → 重啟」（§4.4 的「不必重啟」指的是不必改代碼/不必重佈，不是不必重啟進程）。

⚠️ **模板卡另需 Epic 1 的 flag**：⑥-3 / ⑦-4 要看到「📜 模板傳承（四類）」這張卡，終端 A 還必須有
`$env:TEMPLATE_API_ENABLED = 'on'`（否則模板探測 404 → 整卡不渲染，`TemplateStudio.tsx:1352`），
`LINEAGE_ENABLED` 只決定卡內的師門口徑。兩個 flag 一起設最省事：

```powershell
$env:LINEAGE_ENABLED = 'on'
$env:TEMPLATE_API_ENABLED = 'on'
```


### 0.2 數據基線（本機 `backend/zhiheng.db` 只讀實測，執行前請對一次）

| 項 | 值 |
| :-- | :-- |
| `alembic_version` | `0005_add_lineage` |
| `lineage`（李老師的師門） | `id = lin-ua8739bc7`、`name = 李老师師門`、`owner_teacher_name = 李老师`、`status = active` |
| `teachers` | 1 位（`李老师`） |
| `patient_teachers` | 10 行，**全部** `lineage_id = lin-ua8739bc7`、`status = active`；`lineage_id = ''` 的行 = **0** |
| 業務行 | `drafts = 1`、`patient_records = 4`、`appointments = 6`、`templates = 5`（均屬李老師） |

> 若你的庫行數與上表不同（例如又加了學生/預約），**只影響「行數」類預期**，不影響本文任何「狀態碼 / 文案」類預期。

### 0.3 瀏覽器準備

1. F12 → **Network** 面板，勾 ☑ `Preserve log`，Filter 填 `api`（乾淨視角）。
2. F12 → **Console** 面板保持可見（白屏 / 未捕獲異常都在這裡留痕）。
3. 每步切換角色 / 頁籤前後，用 **Ctrl+F5 硬刷新**一次，避免 HMR 殘留狀態。

### 0.4 操作地圖（改版也不會記錯位置）

| 元件 | 位置 | 代碼 |
| :-- | :-- | :-- |
| 角色切換（除錯用） | 整頁**最底部**「🧑⚕️ 角色切换」卡：李老师 / 李老师智能体 / 学生 / 学生智能体 | `App.tsx:4662-4670` |
| 老師端 4 頁籤 | 標題下方：首頁 / 診室 / 管理 / 設定（預設 `home`） | `App.tsx:2770-2776`、`App.tsx:293` |
| 師門條（只讀） | 頁籤欄**下方**、所有頁籤共用一處 | `App.tsx:2790-2798` |
| 師門徽章（三處） | ① 診室隊列 ② 診室工作台 ③ 學生管理（卡片標題旁） | `App.tsx:4030`、`App.tsx:4264`、`App.tsx:3259` |
| 模板卡 | 「管理」頁籤，「學生管理」之後 | `App.tsx:3793-3795` → `TemplateStudio.tsx` |

### 0.5 判定通則

* 每步三段核對：**預期畫面 → 預期 Network（URL 是否帶 `lineage_id` / 狀態碼）→ 通過標準**。
* ⑥ 的硬指標只有兩條：**首屏零 4xx/5xx**（Network filter `api` 內 status ≥ 400 的條目數 = 0）與
  **四條點名讀接口的 URL 都帶 `lineage_id`**。
* ⑦ 的硬指標只有兩條：**頁面可用（不白屏、Console 無未捕獲異常）** 與
  **模板卡出現「師門未就緒」紅字 + 可點的「🔄 重新載入」**（400 是**設計預期**，不是故障）。
* 任一項不符 → 先跑附錄 A（flag off 對照）取一次基線，再把「⑥/⑦ 實測 + flag off 基線 + 截圖」一起上報。


---

## 1. 場景 ⑥：flag on + 李老師（**已開山門**）

### ⑥-0 準備

1. 確認終端 A 的啟動命令裡有 `$env:LINEAGE_ENABLED = 'on'`（§0.1），後端已起來。
2. Ctrl+F5 硬刷新頁面 → 點最底部「🧑‍⚕️ 角色切换」的 **`李老师`** 按鈕。
3. 停在**預設頁籤「首頁」**（`teacherTab === 'home'`），先只看首屏。

### ⑥-1 首屏（首頁）

**預期畫面**

* 頁面正常渲染，**無白屏**；Console **無**未捕獲異常（批 1 的 `ErrorBoundary` 不應出現
  「🏮 此處暫未能顯示」）。
* 頁籤欄下方出現**師門條**（`App.tsx:2790-2798`）：
  `🏯 目前師門：李老师師門`（`name` 空時回落 `id`）
  ＋ 灰字 `（階段一：一位老師 = 一個師門，不提供切換）`
  ＋ 右側 `本頁資料均限本師門 · lin-ua8739bc7`
* **不應**出現橙色條「⚠️ 目前師門已封存（只讀）：…」（只有 `status='archived'` 才渲染，`App.tsx:2785-2789`）。

**預期 Network**（`Preserve log` 開著，看 `api` 過濾後的完整序列）

| # | 請求 | 預期狀態 | 備註 |
| :-- | :-- | :-- | :-- |
| 1 | `GET /api/lineages?teacher_name=李老师` | **200** `{"lineages":[{…"id":"lin-ua8739bc7"…}]}` | 探測即 flag 探測器（`App.tsx:599-611`）；**沒有** 404 |
| 2 | `GET /api/teacher-patients?teacher_name=李老师&lineage_id=lin-ua8739bc7` | 200 | 10 人 |
| 3 | `GET /api/role-data?role=李老师&patient_name=张三&teacher_name=李老师&lineage_id=lin-ua8739bc7` | 200 | |
| 4 | `GET /api/drafts?teacher_name=李老师&lineage_id=lin-ua8739bc7` | 200 | |
| 5 | `GET /api/patient-records?patient_name=张三&teacher_name=李老师&lineage_id=lin-ua8739bc7` | 200 | |
| 6 | `GET /api/appointments?teacher_name=李老师&lineage_id=lin-ua8739bc7` | 200 | |
| 7 | `GET /api/appointments/calendar?teacher_name=李老师&lineage_id=lin-ua8739bc7` | 200 | |

**通過標準**

* 序列 1 一定**先於** 2~7（批 2 就緒門：`App.tsx:855-862` 的 effect 在 `lineageReady` 之前一條都不發）——
  若看到 3/4/5/6 出現在 1 之前，或看到不帶 `lineage_id` 的同名請求，**即為回歸**。
* Network 面板內 `api` 的所有響應 **status ≥ 400 的條目 = 0**（點 name 欄排序，看 Status 欄）。
* 點名四條 `drafts` / `patient-records` / `role-data` / `appointments` 的 URL **逐字含 `lineage_id=lin-ua8739bc7`**。

### ⑥-2 診室頁籤 → 兩處徽章

**操作**：點頁籤 **`诊室`**，上下滾一遍（先看「🩺 诊室队列」，再看「🩺 诊室工作台」）。

**預期畫面**

* `🩺 诊室队列` 標題右側出現徽章：`🏯 本頁限師門：李老师師門`（`App.tsx:4030`）。
* `🩺 诊室工作台` 標題右側同一徽章（`App.tsx:4264`）。
* 隊列雙列（📅 預約面診 / 💻 遠程問診）與既有卡片照常顯示，行數與 flag off 基線一致。

**預期 Network**：不因切頁籤而新增 4xx；`/api/complaints?…&lineage_id=…`、`/api/agent_tasks?…&lineage_id=…`、
`/api/agent_action_log?…&lineage_id=…` 若發出，均 200（每條都帶 `lineage_id`）。

### ⑥-3 管理頁籤 → 學生管理徽章 + 模板卡

**操作**：點頁籤 **`管理`**，滾到「👥 学生管理」，再往下看「📜 模板傳承（四類）」。

**預期畫面**

* `👥 学生管理（10人）` 標題右側同一枚徽章 `🏯 本頁限師門：李老师師門`（`App.tsx:3259`）；
  下方學生表 **10 行**、狀態徽章正常（不應出現「暂无学生，请在上方添加」）。
* 模板卡渲染：標題 `📜 模板傳承（四類）`（`TemplateStudio.tsx:1357`）
  ＋ 灰字提示 ＋ 右上 `🔄 重新載入` 按鈕。
* 卡片內出現藍底只讀條（`TemplateStudio.tsx:1389-1393`）：
  `🏯 本頁模板歸屬師門：lin-ua8739bc7（階段一：一位老師 = 一個師門，不提供切換）`。
* **不應**出現紅字「師門未就緒：…」與「模板表未就緒…」（`TemplateStudio.tsx:1379`、`1384-1385`）。
* 四類頁籤徽章（問診 / 病歷 / 施治 / 開方）顯示各類 `active` 版本號；版本列表非空（`templates` 共 5 行）。

**預期 Network**（模板卡探測 + 首次列表，`TemplateStudio.tsx:1137-1150`）

| 請求 | 預期 |
| :-- | :-- |
| `GET /api/templates?include_schema=0&type=inquiry&teacher_name=李老师&teacher_id=李老师&lineage_id=lin-ua8739bc7` | **200** |
| `GET /api/templates?teacher_name=李老师&teacher_id=李老师&lineage_id=lin-ua8739bc7` | **200** |

**通過標準**：三處徽章 + 師門條 + 模板卡歸屬條 **四處齊全**；模板卡無任何紅字；整頁 0 筆 ≥400。

### ⑥-4 其餘頁籤快掃

**操作**：點 `设置` 頁籤 → 滾到底 → 切 `学生`（學生端）→ 再切回 `李老师`。

**預期**：全程無白屏；切回老師端後師門條 / 徽章 / 模板卡**重新出現**且 `lineage_id` 一致
（換角色會重探，見 `App.tsx:590-613`）。

### ⑥-5 記錄

| 項 | 預期 | 實測 | 截圖 | 結論 |
| :-- | :-- | :-- | :-- | :-- |
| ⑥-1 首屏零 4xx/5xx | 0 條 | | | |
| ⑥-1 四條點名 URL 帶 `lineage_id` | 4/4 | | | |
| ⑥-1 師門條文案 | 見 ⑥-1 | | | |
| ⑥-2 診室兩處徽章 | 2/2 | | | |
| ⑥-3 學生管理徽章 + 10 人 | ✔ | | | |
| ⑥-3 模板卡歸屬條 | `lin-ua8739bc7` | | | |
| ⑥-4 切角色往返可恢復 | ✔ | | | |

---

## 2. 場景 ⑦：flag on + 李老師**未開山門**（臨時禁用其師門）

### ⑦-0 目標狀態是什麼（先對齊，否則一定測錯）

「未開山門」= `GET /api/lineages?teacher_name=李老师` **200 且 `{"lineages": []}`**（一個師門行都沒有），
前端據此落到：`lineageEnabled = true`（flag 確實是開的）、`teacherLineage = null`、
`currentLineageId = ''`（`App.tsx:549-555`），於是所有請求**不帶** `lineage_id`
→ 後端 `lineage_read_scope()` 依 §3.2 / §5.2 fail-loud 回 **400 `lineage_required`**（不是 404、不是全量）。

> ⚠️ **不要用「封存（archive）」模擬 ⑦**：`App.tsx:608` 是 `rows.find(active) || rows[0]` ——
> `archived` 行**仍會被當作當前的師門上下文**，師門條變成「⚠️ 目前已封存」那條，URL 依然帶
> `lineage_id`，**測不到**本文要驗的「上下文為空」路徑。
> （`list_lineages_by_teacher()` 明確含 `archived`：`lineage_service.py:475-488`。）

### ⑦-0.1 準備（路線 A · 推薦：**副本庫**，真機庫一個字節都不動）

```powershell
# A1 先停掉終端 A 的 uvicorn（Ctrl+C），回到 repo 根目錄
cd d:\projects\zhiheng-tcm

# A2 複製真機庫（連同資料，只改副本）
Copy-Item backend\zhiheng.db backend\zhiheng.no-lineage.db -Force
```

```powershell
# A3 在副本裡把「李老师師門」的 owner 改名 → 等效於「李老師未開山門」
#    （用 here-string 傳給 python，避開 Windows PowerShell 5.1 對原生程序的引號處理）
$py = @'
import sqlite3
con = sqlite3.connect(r"backend\zhiheng.no-lineage.db")
con.execute("UPDATE lineage SET owner_teacher_name = '李老师（未開山門）' WHERE owner_teacher_name = '李老师'")
con.commit()
print(con.execute("select id, name, owner_teacher_name, status from lineage").fetchall())
con.close()
'@
$py | python -
```

期望輸出：`[('lin-ua8739bc7', '李老师師門', '李老师（未開山門）', 'active')]`（行還在，只是**不再屬於李老師**）。

```powershell
# A4 後端指向副本庫（ZHIENG_DB 是相對路徑 → 相對 backend/，database.py:6）
cd d:\projects\zhiheng-tcm\backend
$env:ZHIENG_DB = 'zhiheng.no-lineage.db'
$env:LINEAGE_ENABLED = 'on'
python -m uvicorn main:app --host 0.0.0.0 --port 8000 --reload
```

> 啟動時 `main.py` 會跑 `init_db()` + `run_upgrade()`：副本已是 `0005_add_lineage`，**冪等**無變化。
> 副本可放心改壞，刪掉即復原（見 §4）。

**路線 B（備選 · 就地改真機庫，務必先備份且用完立刻還原）**

```powershell
cd d:\projects\zhiheng-tcm
Copy-Item backend\zhiheng.db "backend\zhiheng.db.bak-$(Get-Date -Format yyyyMMdd-HHmmss)" -Force   # 先備份
# 改 owner：把 A3 的 here-string 改成 r"backend\zhiheng.db" 執行
# 還原：把 owner_teacher_name 從 '李老师（未開山門）' 改回 '李老师'（或用 .bak 覆蓋）
```

### ⑦-1 首屏可用性（**最重要**的一步）

1. Ctrl+F5 硬刷新 → 底部切到 **`李老师`**。
2. Network filter = `api`。

**預期畫面**

* 頁面**正常可用、無白屏**；Console 無未捕獲異常（批 1 的降級把 400 錯誤體擋在 `setState` 之外）。
* **師門條不出現**（`App.tsx:2783` 需 `teacherLineage` 為真值 → 這裡是 `null`）。
* 首頁既有卡片（黃曆 / 智能體工作台 / 備忘錄…）照常渲染；清單類卡片進**空態**而非報錯。

**預期 Network**

| 請求 | 預期狀態 | body 關鍵字 |
| :-- | :-- | :-- |
| `GET /api/lineages?teacher_name=李老师` | **200** | `{"lineages":[]}` ← **必須是 200 + 空數組**（若 404 = flag 其實是 off，回 §0.1 重啟） |
| `GET /api/teacher-patients?teacher_name=李老师` | **400** | `"error":"lineage_required"`、`"msg":"缺少師門上下文（lineage_id）：老師端讀取必須帶 lineage_id"` |
| `GET /api/role-data?...&teacher_name=李老师` | 400 | 同上 |
| `GET /api/drafts?teacher_name=李老师` | 400 | 同上 |
| `GET /api/patient-records?...&teacher_name=李老师` | 400 | 同上 |
| `GET /api/appointments?teacher_name=李老师` | 400 | 同上 |
| `GET /api/appointments/calendar?teacher_name=李老师` | 400 | 同上 |
| `GET /api/complaints?...&teacher_name=李老师` | 400 | 卡片自吞（`App.tsx:1259-1265`）→「暂无待处理陈述…」 |
| `GET /api/agent_tasks?...`（×2）、`/api/agent_action_log?...` | 400 | `Array.isArray` 兜底 → 空列表 |

**通過標準**：URL **一律沒有** `lineage_id`（上下文為空時 `withLineage` 原樣返回，`App.tsx:559-560`）；
400 是**設計預期**（設計 §3.2 / §5.2「漏改即 4xx」）；**頁面不得白屏、不得彈錯誤框**。

### ⑦-2 診室頁籤：清單空態文案

**操作**：點 `诊室` 頁籤。

**預期畫面**

* `🩺 诊室队列` 標題右側 **無**徽章（`renderLineageChip()` 條件不成立 → `null`，`App.tsx:580-585`）。
* 隊列「📅 預約面診」與「💻 遠程問診」兩列均為灰字 **「暂无」**（`App.tsx:4042`、`App.tsx:4085`）；
  臨時加插候選「暂无没预约的学生」（`App.tsx:4153`）。
* `🩺 诊室工作台`：**無**徽章；「寫入目標：（暂无待处理病历草案，请先在"诊室队列"里选一位学生）」（`App.tsx:4273`）；
  「暂无待处理病历（在"诊室队列"里选一位学生即可开始记录）」（`App.tsx:4405`）。
* 「待處理陳述」：暂无待处理陈述，学生完成问诊前准备后会显示在这里（`App.tsx:4209`）。

### ⑦-3 管理頁籤：學生管理空態

**操作**：點 `管理` 頁籤 → 看「👥 学生管理」。

**預期畫面**

* 標題 `👥 学生管理（0人）`，右側 **無**徽章。
* 表格體灰字 **「暂无学生，请在上方添加」**（`App.tsx:3308-3309`）。
* 中藥材庫存 / 財務管理等其它卡片照常（不依賴師門）。

### ⑦-4 模板卡：**紅字 + 重新載入**（第二步重點）

**操作**：在同一「管理」頁籤往下滾到模板卡，再點一次右上 `🔄 重新載入`。

**預期畫面**

* 模板卡**仍然渲染**（不是整卡消失——flag 是 on），標題 `📜 模板傳承（四類）`，
  右上 `🔄 重新載入` **可點、不置灰**（`TemplateStudio.tsx:1358-1372`）。
* 卡內紅字（`TemplateStudio.tsx:1384-1385`）：
  `師門未就緒：缺少師門上下文（lineage_id）：老師端讀取必須帶 lineage_id　—— 請先開山門，或確認當前師門狀態後重新載入`
  （`error` 為空時才回落後備文案「模板需歸屬到一個師門（後端要求 lineage_id）」；正常情況顯示後端 `msg`。）
* **不應**出現 `🏯 本頁模板歸屬師門：…` 那條（`lineageId` 為空 → `TemplateStudio.tsx:1389` 條件不成立）。
* 點 `🔄 重新載入` 後：`probeNonce` +1 → **重跑探測**（`TemplateStudio.tsx:1368`），
  紅字**保持不變**（上下文仍為空 → 仍 400）——這是預期，不是卡死。

**預期 Network**

| 請求 | 預期 |
| :-- | :-- |
| `GET /api/templates?include_schema=0&type=inquiry&teacher_name=李老师&teacher_id=李老师`（**無** `lineage_id`） | 400 `"error":"lineage_required"` |
| 點「🔄 重新載入」後 | **再發一次**上表請求（同樣 400）→ 證明重試走的是「重跑探測」而非只重拉列表 |

### ⑦-5（可選）自愈驗證：把師門還回去

前提：走路線 A（副本庫）。

1. 另開一個 PowerShell，把副本的 `owner_teacher_name` 改回 `李老师`（here-string 同 A3，SQL 反過來寫）。
2. 瀏覽器：切到 `学生` → 再切回 `李老师`（觸發 `App.tsx:590-613` 重探）。
3. **預期**：師門條 + 三處徽章 + 模板卡歸屬條全部回來；`/api/templates…&lineage_id=lin-ua8739bc7` → 200。
4. 留痕一句：`🔄 重新載入` 只重跑 **TemplateStudio 自身**的探測；上下文為空時，恢復需要一次
   **App 級重探**（切角色 / 切老師）。此為階段一（一師一門、無切換器）的既有設計，非缺陷。

### ⑦-6（可選）學生端「未歸屬」提示怎麼看到

**實測：當前真機庫 `patient_teachers` 中 `lineage_id = ''` 的行數 = 0** → 學生端那條
`未歸屬：李老师 —— 未歸屬資料請聯絡管理員。`（`App.tsx:3226-3231`）**在現有資料下不會出現**。
要現場看到，可在**副本庫**上臨時造一條未歸屬行：

```powershell
$py = @'
import sqlite3
con = sqlite3.connect(r"backend\zhiheng.no-lineage.db")
con.execute("UPDATE patient_teachers SET lineage_id = '' WHERE patient_name = '张三' AND teacher_name = '李老师'")
con.commit()
print(con.execute("select patient_name, teacher_name, lineage_id from patient_teachers").fetchall())
con.close()
'@
$py | python -
```

硬刷新 → 切到 `学生`（或 `学生智能体`）→「我的師門」卡內應出現那條橙紅字提示；
同時「我的老师」裡該老師的歸屬行不再列在「在門內」清單（`App.tsx:3202-3219`），
若一個在門師門都沒有，還會出現空態「尚未加入任何師門：…」（`App.tsx:3222-3223`）。

> 留痕：這條路徑對應設計 §3.2 附註的**現狀缺口**（`docs/epic4-lineage-design-v1.md:482`）：
> 老師端「新增學生」與邀請碼接受仍走舊入口（不寫 `lineage_id`）→ 產出的行就是「未歸屬」，
> 需另走一次師門加入才會落進本門。

### ⑦-7 記錄

| 項 | 預期 | 實測 | 截圖 | 結論 |
| :-- | :-- | :-- | :-- | :-- |
| ⑦-1 頁面可用、無白屏 | ✔ | | | |
| ⑦-1 `/api/lineages` | 200 + `[]` | | | |
| ⑦-1 老師端讀接口 | 全部 400 `lineage_required` | | | |
| ⑦-1 URL 不帶 `lineage_id` | ✔ | | | |
| ⑦-2 診室兩處空態 | 「暂无」×N | | | |
| ⑦-3 學生管理空態 | 「暂无学生…」 | | | |
| ⑦-4 模板卡紅字 + 重載按鈕 | 見 ⑦-4 | | | |
| ⑦-5 自愈（可選） | 全部恢復 | | | |
| ⑦-6 學生端未歸屬（可選） | 橙紅字提示 | | | |

---

## 3. 常見誤操作（反例速查，避免把「設計預期」記成 Bug）

| # | 誤操作 | 後果 / 正確做法 |
| :-- | :-- | :-- |
| 1 | 用 `POST /api/lineages/{id}/archive` 模擬 ⑦ | **測不到**：`archived` 行仍被前端當上下文（`App.tsx:608`）→ 師門條變「已封存」、URL 仍帶 `lineage_id`。正確做法見 ⑦-0.1 |
| 2 | 期待 ⑦ 出現師門條 / 三處徽章 | **不會**：三者都要求 `teacherLineage` 為真值（`App.tsx:2783`、`580-585`） |
| 3 | 期待 ⑦ 首屏的老師端讀接口是 200 | **不會**：flag on + 無上下文 = 400 `lineage_required` 是設計（§3.2 / §5.2）；空態才是預期結果 |
| 4 | 期待 ⑦ 模板卡「整卡消失」 | **不會**：整卡不渲染只在 flag **off**（`probeState==='off'` → `return null`，`TemplateStudio.tsx:1352`）；⑦ 是 `no_lineage` → 卡在 + 紅字 |
| 5 | 在 flag off 下期待任何師門 UI / `lineage_id` | **不會**（§4.4 零行為變化）：見附錄 A |
| 6 | 改 `$env:LINEAGE_ENABLED` 但沒重啟 uvicorn | **不生效**：env 是進程級的，`lineage_enabled()` 每次現讀也只讀**本進程** env（§0.1） |
| 7 | 用舊入口（「+ 添加学生」/ 邀請碼）加學生後期待其進入本門 | flag on 下該行 `lineage_id = ''` = 未歸屬（設計 §3.2 附註，`docs/epic4-lineage-design-v1.md:482`）→ 老師端看不到，學生端只給提示 |
| 8 | 看到 `400 lineage_required` 就斷定「前端漏傳參數」 | **先看 `msg` 再定位，不能靠錯誤碼定位**：`lineage_read_scope()`（`backend/lineage_service.py:272-304`）**先校 `lineage_id` 後校 `teacher_name`**，兩者**共用同一個錯誤碼** `lineage_required` —— 缺 `lineage_id`（msg「缺少師門上下文（lineage_id）」）會**遮住**缺 `teacher_name`（msg「缺少老師身份（teacher_name）」，只有 `lineage_id` 合法時才可能出現）。附錄 B 的只讀探針可逐條驗證 |

> 第 **8** 行即本轮 CTO 報告的 **TD-010**（學生端 `/api/role-data` 400）的誤判來源；
> 核查結論（含真機庫副本 + flag on 的 `TestClient` 實測矩陣）見 `docs/tech-debt.md` **§8**。

---

## 4. 收尾與復位（每次都做）

```powershell
# 1) 停掉後端（Ctrl+C）→ 刪副本庫 → 清環境變量 → 起回真機庫
cd d:\projects\zhiheng-tcm
Remove-Item backend\zhiheng.no-lineage.db -Force
Remove-Item Env:ZHIENG_DB -ErrorAction SilentlyContinue

# 2) 確認倉庫零改動（本輪回退後應為空輸出）
git status --short
```

* 若走了路線 B（就地改真機庫）：確認 `lineage.owner_teacher_name` 已改回 `李老师`
  （可用附錄 B 的只讀探針核對），並刪掉臨時 `.bak-*` 或按團隊備份慣例保留。
* 若被 ⑦-6 改過 `patient_teachers`：那是在**副本庫**上做的，刪副本即復原；
  若曾誤改真機庫，把該行 `lineage_id` 改回 `lin-ua8739bc7`。
* 完成後把 ⑥-5 / ⑦-7 兩張記錄表（含截圖連結）貼進回歸報告。

---

## 附錄 A（可選）：flag off 對照基線

用途：⑥/⑦ 出現任何疑問時，先取一次 flag off 基線，用來區分「本來就這樣」與「批 2 引入的回歸」。

```powershell
# 停掉 uvicorn → 清 flag → 重啟（README.md:25-31 的原命令）
cd d:\projects\zhiheng-tcm\backend
Remove-Item Env:LINEAGE_ENABLED -ErrorAction SilentlyContinue
Remove-Item Env:ZHIENG_DB -ErrorAction SilentlyContinue
python -m uvicorn main:app --host 0.0.0.0 --port 8000 --reload
```

| 項 | flag off 預期 |
| :-- | :-- |
| `GET /api/lineages?teacher_name=李老师` | **404** `"error":"lineage_disabled"`（7 個新端點全 404，`docs/epic4-lineage-design-v1.md:284`） |
| 首屏 `role-data` / `drafts` / `patient-records` / `appointments` / `teacher-patients` | **200**，且 URL **逐字面不帶** `lineage_id`（`withLineage` 原樣返回） |
| 師門條 / 三處徽章 | **全部不渲染**（`App.tsx:2783`、`580-585`） |
| 模板卡 | 由 **Epic 1 的 `TEMPLATE_API_ENABLED`** 決定（與 `LINEAGE_ENABLED` 無關）：該 flag 開 → 卡片照常、URL 不帶 `lineage_id` 且 200；該 flag 關 → 整卡不渲染 |
| 判定 | 以上四條**同時**成立 = 「§4.4 零行為變化」在現場成立 |

---

## 附錄 B（可選）：只讀取證探針

只讀（`mode=ro`，不寫庫文件、不建 journal），用來核對 §0.2 基線與 §4 復位：

```powershell
cd d:\projects\zhiheng-tcm
$py = @'
import sqlite3
con = sqlite3.connect("file:backend/zhiheng.db?mode=ro", uri=True)
q = lambda label, sql, p=(): print(label, con.execute(sql, p).fetchall())
q("alembic_version   :", "select version_num from alembic_version")
q("lineage           :", "select id, name, owner_teacher_name, status from lineage")
q("teachers          :", "select name from teachers")
q("pt_by_lineage     :", "select teacher_name, lineage_id, status, count(1) from patient_teachers group by teacher_name, lineage_id, status")
q("pt_unassigned_cnt :", "select count(1) from patient_teachers where lineage_id = ?", ("",))
q("drafts_by_teacher :", "select teacher_name, count(1) from drafts group by teacher_name")
q("records_by_teacher:", "select teacher_name, count(1) from patient_records group by teacher_name")
q("templates_by_teach:", "select teacher_id, count(1) from templates group by teacher_id")
q("appts_by_teacher  :", "select teacher_name, count(1) from appointments group by teacher_name")
con.close()
'@
$py | python -
```

（本輪實測輸出見 §0.2；`lineage` 應為 `lin-ua8739bc7 / 李老师師門 / 李老师 / active`。）

---

## 附錄 C：本輪（批 3）留痕與代碼位置索引

**回退留痕**：批 3 原提案 `frontend/src/App.tsx:2237` `lineageEnabled → lineageReady` 已**回退**。

* 回退理由（複核結論）：批 3 指令所依據的是批 2 **之前**的代碼狀態；批 2 落地後
  「flag on + 探測未落地缺 `teacher_name`」的前提已不成立。在 flag on 路徑上
  `lineageEnabled` 與 `lineageReady` **恆等**（同批置 true）→ 該替換在 flag on 下**零收益**；
  在 flag off / 探測異常時 `lineageReady` 同樣為 true → 學生端 URL 會補 `teacher_name` →
  後端 `database.py:1151-1153` 的 `if teacher_name:` 分支（**不受** `filter_on` 保護）仍按老師過濾
  → 行集變化，破壞 §4.4「flag off 零行為變化」契約，並與 `database.py:1138-1139` docstring、
  設計 §3.2 / §4.4、`App.tsx:2234-2236` 註釋三處契約衝突；且在重探窗口會新引入「已就緒但條件為假 → 丟參」的 400。
* 驗收：`git status --short` **空輸出**；`git diff --stat` **無輸出**（= 相對 HEAD 零變化）。

**關鍵代碼位置（本文引用，便於當場覆核）**

| 主題 | 位置 |
| :-- | :-- |
| flag 判定（每次現讀、默認 off） | `backend/lineage_service.py:39-47` |
| 老師端讀點唯一入口（fail-loud） | `backend/lineage_service.py:272-303`、`backend/database.py:16-33` |
| 老師視角師門清單（含 archived） | `backend/lineage_service.py:459-488` |
| 新端點與錯誤體翻譯 | `backend/lineage_api.py:43-104`、`main.py` 註冊 |
| 模板側由「拒」改「校驗」 | `backend/template_api.py:89-109` |
| 讀接口簽名（`lineage_id` 可選參數） | `backend/main.py:193-194`、`426-427`、`697-698`、`755-756`、`852-864` |
| 師門探測 + 就緒位（生產者） | `frontend/src/App.tsx:590-613` |
| 就緒門 + 依賴成對（消費者） | `frontend/src/App.tsx:855-862` |
| `withLineage` 唯一拼參出口 | `frontend/src/App.tsx:557-560` |
| 師門條 / 封存條 | `frontend/src/App.tsx:2783-2800` |
| 三處徽章 render | `frontend/src/App.tsx:580-585`、`3259`、`4030`、`4264` |
| 模板卡探測 / 紅字 / 重載 / 歸屬條 | `frontend/src/TemplateStudio.tsx:1137-1150`、`1384-1385`、`1358-1372`、`1389-1393` |
| 學生端未歸屬提示 | `frontend/src/App.tsx:3226-3231` |
