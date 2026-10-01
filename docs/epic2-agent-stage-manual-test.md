# Epic 2 · 智能體五階段 手工自測清單（flag off/on · 六段）

> 適用：Epic 2「老師智能體五階段」steps 6a–6d + 6.5-a/b + step 7 合入後，**只做人工瀏覽器驗收**。
> 本文**不含**任何 `npm install` / `pytest` 步驟；自動化回歸見 `backend/test_agent_stage.py`（㉓ 組）與 `backend/test_migrations.py`。
> 對齊：`docs/epic2-agent-stage-design-v1.md` §4.5-⑤（卡片）/ §4.6（7 端點）/ §5.1 紅線① / §5.3（觀察期降級）/ §5.6 口徑 B。

---

## 一、前置

```powershell
# 終端 A（後端，flag on）
cd d:\projects\zhiheng-tcm\backend
$env:AGENT_STAGE_ENABLED = 'on'
..\venv\Scripts\python.exe -m uvicorn main:app --host 0.0.0.0 --port 8000 --reload

# 終端 B（前端）
cd d:\projects\zhiheng-tcm\frontend
npm run dev
```

* 開 <http://localhost:5173> → 整頁最底部「🧑‍⚕️ 角色切换」選 **李老师**（老師端）。
* flag 是「進程級環境變量 + 每次請求現讀」，但**切 flag 必須重啟 uvicorn 進程**（在已跑著的終端改 `$env:` 無效）。
* 基線：`alembic_version` ≥ `0003_add_agent_stage`（現行庫 = `0005_add_lineage`）；`李老师` 在 `teachers`；`agent_stage_state` 有李老师行 —— **無行也不必補**：後端按 `default_stage='learning'` 兜底，徽章同樣是「學習期」。
* 判定通則：每段三段核對（**預期畫面 → 預期 Network → 通過標準**）；Network 勾 ☑ `Preserve log`、Filter 填 `agent/stage`；URL 裡 `teacher_name` 是**編碼**的（`李老师` = `%E6%9D%8E%E8%80%81%E5%B8%88`）。
* 段 A–F **按序一次跑完**最省事（B→C→D→E→F 的階段是遞進的）。

---

## 二、段 A · flag off（後端**不帶** flag 重啟）

```powershell
Remove-Item Env:AGENT_STAGE_ENABLED -ErrorAction SilentlyContinue   # 之後重啟 uvicorn
```

1. 🏠 首頁**無**「🧭 智能體階段」卡（`AgentStagePanel.tsx:1077`：`probeState !== 'on'` → `return null`）；原位置（智能體工作台卡下方 / 今日備忘錄卡上方）不留空框。
2. **7 端點全 404 `agent_stage_disabled`**：`GET /api/agent/stage`、`POST /evaluate`、`GET /config`、`PUT /config`、`POST /demote`、`POST /suggest`、`POST /predraft`（錯誤體四鍵齊全，`detail.error` 逐字為該碼）。
3. 既有 UI **逐字面一致**：除掛載探測那一條 `GET /api/agent/stage`（404，flag off 的既定行為，卡不渲染）外，Network 無新增請求、頁面無新增元素；首頁 / 診室 / 管理 / 設定四頁籤照常可用。
4. `POST /api/agent/scan` 響應**無** `stage` 鍵 → 恰為 `{ok, created, new_tasks}`。

---

## 三、段 B · flag on（李老师，默认 learning）

1. 卡出現，徽章 = **「學習期」**（繁文字面量由後端 `stage_label` 直出）+「自 … 起」（有 `stage_since` 時）+「下一階段：見習期」。
2. 「**🔄 立即評估**」**常顯且可點**（不只在快照過期時）→ 點擊：`POST /api/agent/stage/evaluate` **200** → 緊跟 `GET /api/agent/stage` **200** → 卡內出現「✅ 已重新評估（…）」。
3. Network：`GET /api/agent/stage?teacher_name=…&teacher_id=…` **200**（此響應是能力區的唯一來源）。
4. 三顆能力按鈕**全灰**，各自灰字（逐字、簡繁照抄）：🧪 證型候選 →「尚未開放（需「見習期」）」；📜 方劑建議 →「尚未開放（需「助手期」）」；🧾 預處方預填 →「尚未開放（需「授權期」）」。
5. 卡底鐵律文案逐字：「智能體永不診斷、永不開方、永不簽字；一切建議僅供參考，採用即為你的決定。」

---

## 四、段 C · flag on + 手工升 apprentice

```powershell
cd d:\projects\zhiheng-tcm; $py = @'
import sqlite3
c = sqlite3.connect("backend/zhiheng.db")
c.execute("UPDATE agent_stage_state SET stage='apprentice', stage_source='teacher_confirm',"
          " pending_stage='', pending_task_id=0, stage_since=datetime('now','localtime')"
          " WHERE teacher_name='李老师'")
c.commit()
'@
$py | ..\venv\Scripts\python.exe -
```

1. **Ctrl+F5 硬刷新**（無輪詢）→ 徽章變 **「見習期」**、來源注記 **「老師確認升級」**。
2. **🧪 證型候選亮起**（📜 / 🧾 仍灰：各需「助手期」/「授權期」）。
3. 先在診室選中一張**未簽**草案（能力區前置條件；否則三顆都附「需先選中未簽草案」）→ 點 🧪 → `POST /api/agent/stage/suggest` **200** → 卡內**只讀**展示「證型候選 N 條」（**永不**回填編輯框）。

> SQL 直改 = **取證捷徑**：不落 `agent_stage_log`、不產生行動日誌；真實升階請走「⏳ 待你確認」的 ✅。自測結束按 §八 復位。

---

## 五、段 D · 降級（⬇ 降級 → 二次確認）

1. 點「**⬇ 降級**」→ 卡內展開二次確認區（不彈窗、不阻塞其它卡）：「確定要降級嗎？降級立即生效（不必等任何人確認），且智能體不會自動幫你升回。」
2. 「降級到」下拉只列**低於**當前階段者（見習期 → 觀察期 / 學習期）；「降級說明」預設「由老師主動降級」；選「**觀察期**」→ 點「**確認降級**」。
3. `POST /api/agent/stage/demote` **200** → 緊跟 `GET /api/agent/stage` **200**；徽章 → **「觀察期」**、來源 → **「老師主動降級」**、回執「✅ 已降級至「觀察期」（已寫入階段審計與行動日誌）」。
4. 「📜 行動日誌」出現「老師主動降級：「見習期」→「觀察期」（單向操作，智能體不會自動升回）」。
5. 反方向：對觀察期再點 ⬇ → 按鈕置灰 +「已在最低階段（觀察期），無可降級」。

---

## 六、段 E · scan 響應帶 `stage`

```powershell
curl.exe -s -X POST http://127.0.0.1:8000/api/agent/scan -H "Content-Type: application/json" -d "{\"teacher_name\":\"李老师\"}"
```

1. 響應 = `{ok, created, new_tasks, stage}`；`stage` 與 `POST /api/agent/stage/evaluate` **同一份**（18 鍵快照 + `changed`），**不裁剪、不補鍵**。
2. `LINEAGE_ENABLED=on` 時必須另帶 `?lineage_id=…`（否則 400 `lineage_required`，見 Epic 4 §4.3）。
3. 旁路性：評估故障只在終端 A 印 `[warn] 階段評估失敗…`，`ok` / `created` / `new_tasks` 照舊（與段 A 逐字相同，僅多一個 `stage` 鍵）。

---

## 七、段 F · 觀察期骨架（智能體零參與）

1. 前置：李老师當前階段 = **觀察期**（段 D 結束即為此態）。
2. 診室觸發一次生成：該學生提交「學生陳述」（`POST /api/transcribe`）或老師現場錄入保存（`POST /api/generate-draft?transcript_id=…`）。
3. 打開生成的草案，**首行**必須逐字為：「**【觀察期】智能體尚未參與，以下為本地骨架，請老師自行填寫。**」（唯一拼裝點 `backend/main.py:616-626`：`_SKELETON_NOTICE` + `_skeleton_draft_with_notice()`）。
4. 對照：把階段改回 `learning`（§四 SQL 的 `stage='apprentice'` 換成 `'learning'`、`stage_source='default'`）→ 再觸發一次生成 → 草案**不含**該提示行（§5.1 紅線④）。
5. 判據只看草案首行：觀察期走骨架**不寫審計**（`generation_degraded()` 是只讀判定，§5.6 口徑 B）→ **不要**拿 `agent_stage_log` 當「有沒有降級」的判據。

---

## 八、復位（自測結束必做）

1. 階段復位：`UPDATE agent_stage_state SET stage='learning', stage_source='default', stage_since='', pending_stage='', pending_task_id=0 WHERE teacher_name='李老师';`
2. 自測產生的草案 / 陳述按 `id` 逐條刪（**勿**整表清空）。
3. `git status --short` 應**無輸出**（本清單**不改任何代碼 / 遷移 / 測試**）。
