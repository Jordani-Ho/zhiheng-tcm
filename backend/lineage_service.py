"""師門（lineage）隔離的**服務層**：feature flag + 錯誤碼契約 + 老師端讀點的雙因子校驗
+ §4.2 七個新接口的業務實現（本模組是唯一寫點，接口層 `lineage_api.py` 只做 HTTP 轉譯）。

對齊：docs/epic4-lineage-design-v1.md
  §4.1  錯誤碼契約（8 個碼；讀路徑子步落地 6 個，本子步補上 `lineage_disabled` /
        `student_lineage_limit`，至此 8 個碼全數可達）
  §4.4  feature flag `LINEAGE_ENABLED`（照抄 `template_service.py:897-909` /
        `agent_stage_service.py:137-163`：雙常量 + **每次調用現讀**，默認 off）
  §5.1  「服務層**存在性 + 歸屬**雙校驗，而不是『只要參數帶了就放行』」
  §5.2  「漏改」的表現必須是 **4xx**，而不是「返回全量」
  §5.3  階段是老師的能力畫像（裁決③）：本模組**不參與** `agent_stage_*` 的過濾
  §5.4  禁止把默認師門 id 寫成代碼常量 → `default_lineage_id()` 由 `slugify(teacher_name)` **計算**

三條寫死在這裡、後續子步不得改的口徑：
  ① **flag off（默認）= 零行為變化**：`lineage_read_scope()` 直接返回 `(False, "")`，**不發任何 SQL**、
     不讀庫、不打日誌，調用方的 SQL / 參數 / 響應**逐字節不變**（§4.4）。
  ② **flag on = 老師端讀點必須帶 `lineage_id`**：缺 / 空 → 400 `lineage_required`（**不許**退化為全量）。
     老師端讀取只認「上下文師門」這一個維度 —— 學生端（`student_name`）不走本函數。
  ③ **`import database` 一律放在函數體內**（與 `agent_stage_service._store_connection()` 同口徑）：
     `database.py` 側對本模組的 import 同樣在函數體內 → 兩個方向都延遲，
     循環依賴在任一條路徑上都不成立；本模組**不在 import 時**碰任何庫。

啟用方式（本機 / 生產，PowerShell）：
    $env:LINEAGE_ENABLED = "on"    # 不設或 off = 隔離不生效，既有鏈路逐字節不變
"""
import hashlib
import importlib.util
import os
import re
import sqlite3
from datetime import datetime

# ---------------------------------------------------------------------------
# 總閘 flag（§4.4）：與 Epic 1 / Epic 2 兩套 flag **逐字同款**，默認 off
# ---------------------------------------------------------------------------
LINEAGE_ENABLED_VALUES = ("on", "1", "true", "yes")


def lineage_enabled():
    """總閘 `LINEAGE_ENABLED`：**每次調用現讀**（便於灰度切換 / 測試，不必重啟 uvicorn）。**默認 off。**

    flag off = 與今天 1:1（§4.4）：`/api/lineages*` / `/api/student-lineages*` 全部 404
    `lineage_disabled`；`lineage_read_scope()` 不生效；既有 SQL 與響應逐字節不變。

    **本函數只讀環境變量**：不讀庫、不打日誌、不拋異常、不緩存（讀到的永遠是當前 env）。
    """
    return os.environ.get("LINEAGE_ENABLED", "off").strip().lower() in LINEAGE_ENABLED_VALUES


# ---------------------------------------------------------------------------
# 錯誤碼契約（§4.1）：8 個碼 + 各自的 HTTP 狀態碼
# ---------------------------------------------------------------------------
LINEAGE_REQUIRED = "lineage_required"                    # 400
LINEAGE_FORBIDDEN = "lineage_forbidden"                  # 403
LINEAGE_NOT_FOUND = "lineage_not_found"                  # 404
LINEAGE_DISABLED = "lineage_disabled"                    # 404
LINEAGE_INVALID = "lineage_invalid"                      # 400
STUDENT_LINEAGE_LIMIT = "student_lineage_limit"          # 409
LINEAGE_NOT_SUPPORTED = "lineage_not_supported"          # 400（**僅 flag off 保留**）
LINEAGE_STORE_UNAVAILABLE = "lineage_store_unavailable"  # 503

LINEAGE_ERROR_STATUS = {
    LINEAGE_REQUIRED: 400,
    LINEAGE_FORBIDDEN: 403,
    LINEAGE_NOT_FOUND: 404,
    LINEAGE_DISABLED: 404,
    LINEAGE_INVALID: 400,
    STUDENT_LINEAGE_LIMIT: 409,
    LINEAGE_NOT_SUPPORTED: 400,
    LINEAGE_STORE_UNAVAILABLE: 503,
}


class LineageError(Exception):
    """師門服務層錯誤：帶機器碼，由接口層翻譯成 HTTP 狀態碼（§4.1）。

    形狀與 `TemplateError`（`template_service.py`）/ `AgentStageError`（`agent_stage_service.py`）
    **同構**：`errors` / `warnings` 剛好湊齊統一錯誤體
    `{detail: {error, msg, errors, warnings}}`（§4.1「錯誤體形狀」）的四個鍵，
    接口層不必再補鍵、也不必判斷某鍵是否存在。

    四條邊界：
      · **只做淺拷貝、不校驗元素形狀**：元素形狀由拋錯方決定，本類不做二次清洗。
      · `None` → `[]`（不是 `None`）：接口層直出 detail 時不允許出現 `null`。
      · **不繼承 `TemplateError`**：那是 Epic 1 已驗收代碼，本 Epic 不複用、不改它。
      · **不與 flag 綁定**：flag off 時本異常不會被拋出（`lineage_read_scope()` 直接返回
        `(False, "")`），flag off 的單例語義由 `lineage_read_scope()` 保證，不由本類保證。
    """

    def __init__(self, code, msg, errors=None, warnings=None):
        super().__init__(msg)
        self.code = code
        self.msg = msg
        self.errors = list(errors or [])
        self.warnings = list(warnings or [])

    def detail(self):
        """統一錯誤體（§4.1）：`{"error": code, "msg": ..., "errors": [], "warnings": []}`。"""
        return {"error": self.code, "msg": self.msg, "errors": list(self.errors),
                "warnings": list(self.warnings)}


def lineage_error_status(code):
    """錯誤碼 → HTTP 狀態碼（未知碼按 400，與 `template_api._TEMPLATE_ERROR_STATUS` 同口徑）。"""
    return LINEAGE_ERROR_STATUS.get(code, 400)


# ---------------------------------------------------------------------------
# 師門 id 口徑（§0.1 / §2.1）：**唯一真相源 = 遷移 0005**
# ---------------------------------------------------------------------------
LINEAGE_ID_PREFIX = "lin-"
_LINEAGE_ID_RE = re.compile(r"^lin-[a-z0-9]+(?:-[a-z0-9]+)*$")
_MIGRATION_0005_PATH = os.path.join(
    os.path.dirname(os.path.abspath(__file__)), "alembic", "versions", "0005_add_lineage.py"
)
_migration_0005_cache = []


def _migration_0005():
    """按路徑載入遷移 0005（alembic 也是按路徑載入的，`test_migrations.py` 同口徑）。

    只為取 `slugify` / `lineage_id_for` —— **不在 0005 裡再寫一份**（§5.4 第 6 條：
    默認師門 id 由 `slugify(teacher_name)` **計算**得出，不落常量）。

    三條口徑：
      · 找不到文件 → `None`；載入失敗（例如 **運行時未裝 `sqlalchemy`**，而 0005 的模組頭
        `import sqlalchemy as sa` 因此在 import 期就炸）→ 也 `None`；
      · `None` 時 `slugify()` 回落**同款算法**（下面那份），因此「庫裡有行、這裡算得出同一個 id」
        在裝了 / 沒裝 alembic 依賴的兩台機器上一致；
      · 結果緩存（一個進程只探一次），**不緩存教師名 → id 的映射**（那只是純函數計算）。
    """
    if _migration_0005_cache:
        return _migration_0005_cache[0]
    module = None
    if os.path.exists(_MIGRATION_0005_PATH):
        try:
            spec = importlib.util.spec_from_file_location(
                "migration_0005_add_lineage", _MIGRATION_0005_PATH
            )
            module = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(module)
        except Exception:  # noqa: BLE001 —— 遷移文件不可載入（缺 sqlalchemy 等）不是錯誤態
            module = None
    _migration_0005_cache.append(module)
    return module


def slugify(name):
    """老師名 → 小寫 ASCII 安全串（§0.1）。**唯一實現**在 0005（本函數只做轉發）。

    0005 不可用時回落同款算法（小寫 → 非 `[a-z0-9]` 轉 `-` → 折疊 `-` → 去首尾 `-` →
    空則 `u<sha1(名)[:8]>`），保證「庫裡有行、這裡算得出同一個 id」。
    """
    module = _migration_0005()
    if module is not None:
        return module.slugify(name)
    raw = "" if name is None else str(name)
    slug = "".join(
        ch if ("a" <= ch <= "z" or "0" <= ch <= "9") else "-" for ch in raw.strip().lower()
    )
    while "--" in slug:
        slug = slug.replace("--", "-")
    slug = slug.strip("-")
    if not slug:
        slug = "u" + hashlib.sha1(raw.encode("utf-8")).hexdigest()[:8]
    return slug


def default_lineage_id(teacher_name):
    """§0.1 / §3.1 推導規則：`teacher_name` →（該老師唯一師門）→ `lineage_id` = `'lin-' + slugify(名)`。

    **只做推導，不查庫、不建行**：階段一的「一師一門」讓這個 id 可復現；
    是否真的存在、老師是否真屬於它，一律以 `load_lineage()` / `teacher_in_lineage()` 的
    庫內校驗為準（§5.2「不是只要參數帶了就放行」）。
    """
    return LINEAGE_ID_PREFIX + slugify(teacher_name)


# ---------------------------------------------------------------------------
# 存儲探針（照抄 `template_service.template_store_ready()` → 503 同款先例）
# ---------------------------------------------------------------------------
def _store_connection():
    """取庫連接：`import database` 恆在**函數體內**（見模組 docstring 口徑 ③）。

    本函數**只取連接**，不做任何校驗 / 建表 / 寫庫。
    """
    import database
    return database.get_connection()


def lineage_store_ready():
    """`lineage` 表是否就位：遷移未跑（或表被改名 / 庫不可讀）→ `False`。

    三條口徑（寫死在這裡，後續子步不得改）：
      1. **不讀 flag**：flag 與「存儲就緒」是**兩件事**，不許合併成一個布林 ——
         flag off → 讀點根本不進來（`lineage_read_scope()` 已返回）；flag on 但表缺失 →
         503 `lineage_store_unavailable`（`agent_stage_store_ready()` 同款理由）。
      2. **只看 `lineage` 這一張表**：12 張業務表的 `lineage_id` 列缺失不屬「存儲沒就緒」
         （列缺失時過濾條件自然命中 0 行，指標可降級、存儲沒壞）。
      3. **絕不建庫 / 建表 / 寫入，異常一律吞成 `False`**（只捕 `sqlite3.Error`，不 print、不拋）：
         接口層因此可以無條件調用它。
    """
    try:
        conn = _store_connection()
        try:
            row = conn.execute(
                "SELECT name FROM sqlite_master WHERE type = 'table' AND name = 'lineage'"
            ).fetchone()
        finally:
            conn.close()
        return row is not None
    except sqlite3.Error:
        return False


# ---------------------------------------------------------------------------
# 讀路徑的雙因子校驗（§3.1 老師可見性 / §5.1 存在性 + 歸屬）
# ---------------------------------------------------------------------------
def parse_lineage_id(lineage_id):
    """校驗 `lineage_id` 的**形狀**：空 → 400 `lineage_required`；格式非法 → 400 `lineage_invalid`。

    返回去空白後的 `lineage_id`。**不查庫**（存在性由 `load_lineage()` 負責）。
    """
    if lineage_id is None or not str(lineage_id).strip():
        raise LineageError(
            LINEAGE_REQUIRED, "缺少師門上下文（lineage_id）：老師端讀取必須帶 lineage_id"
        )
    value = str(lineage_id).strip()
    if not _LINEAGE_ID_RE.match(value):
        raise LineageError(
            LINEAGE_INVALID,
            "lineage_id 格式不合法：應為 'lin-' + slug（小寫字母 / 數字 / 連字符）",
        )
    return value


def load_lineage(lineage_id):
    """讀 `lineage` 一行（`sqlite3.Row`）；不存在 → `None`；表缺失 / 讀庫失敗 → 503。

    表缺失是部署態（遷移未跑），必須 503 `lineage_store_unavailable` 而不是 404
    —— 否則運維會把「請跑遷移」誤讀成「這個師門不存在」（§4.1 / `agent_stage_store_ready()` 同款）。
    `sqlite3.Error` 只在**探針已過、真讀失敗**（庫被鎖 / 表被改名）時才可能出現。
    """
    if not lineage_store_ready():
        raise LineageError(
            LINEAGE_STORE_UNAVAILABLE, "師門表未就緒，請先執行資料庫遷移（0005_add_lineage）"
        )
    conn = _store_connection()
    try:
        return conn.execute("SELECT * FROM lineage WHERE id = ?", (lineage_id,)).fetchone()
    except sqlite3.Error:
        raise LineageError(
            LINEAGE_STORE_UNAVAILABLE, "師門表讀取失敗，請確認資料庫遷移（0005_add_lineage）已就緒"
        )
    finally:
        conn.close()


def teacher_in_lineage(lineage_row, teacher_name):
    """歸屬判定（§3.1 老師可見性）：「請求老師必須屬於該師門」。

    階段一（一師一門）= `owner_teacher_name` 命中即通過；別的老師 / 空老師名 / 無行一律不放行。
    **不看 `status`**：師門被封存（`archived`）後歷史行仍可讀（§5.5-3「退出不丟數據」同款精神）。
    """
    if lineage_row is None:
        return False
    owner = lineage_row["owner_teacher_name"]
    teacher = (teacher_name or "").strip()
    return bool(teacher) and owner == teacher


def lineage_read_scope(teacher_name, lineage_id=None):
    """**老師端讀點的唯一入口**（§3.2 全清單都經此函數）。

    返回 `(filter_on, lineage_id)`：
      · flag off → `(False, "")` —— **零 SQL、零校驗、零行為變化**（§4.4 口徑 ①）；
      · flag on → `(True, <合法 lineage_id>)`，老師端 SQL 應加 `lineage_id = ?` 過濾。

    五條 fail-loud 路徑（flag on，§4.1 / §5.2「漏改的表現必須是 4xx」）：
      · `lineage_id` 空 → 400 `lineage_required`（**不許**退化為全量）；
      · `lineage_id` 格式非法 → 400 `lineage_invalid`；
      · `lineage` 表缺失 → 503 `lineage_store_unavailable`；
      · 師門不存在 → 404 `lineage_not_found`；
      · 老師不屬於該師門 → 403 `lineage_forbidden`。

    `teacher_name` 為空同樣 400 `lineage_required` —— §3.2 明確把「`teacher_name` 可空 = 高危」
    列為漏改即越權的頭兩條（空 = 該患者**所有老師**的記錄 / **全庫**草案）。
    """
    if not lineage_enabled():
        return False, ""
    lineage = parse_lineage_id(lineage_id)
    teacher = (teacher_name or "").strip()
    if not teacher:
        raise LineageError(
            LINEAGE_REQUIRED, "缺少老師身份（teacher_name）：老師端讀取必須帶非空 teacher_name"
        )
    row = load_lineage(lineage)
    if row is None:
        raise LineageError(LINEAGE_NOT_FOUND, "師門不存在：%s（請核對 lineage_id）" % lineage)
    if not teacher_in_lineage(row, teacher):
        raise LineageError(
            LINEAGE_FORBIDDEN, "無權以「%s」的身份讀取師門 %s" % (teacher, lineage)
        )
    return True, lineage


# ---------------------------------------------------------------------------
# §4.2 七個新接口的**服務層**（接口層 `lineage_api.py` 只做 HTTP 轉譯）
#
#   ① GET    /api/lineages?teacher_name=          → list_lineages_by_teacher()
#   ② GET    /api/lineages?student_name=          → list_lineages_by_student()
#   ③ POST   /api/lineages                        → create_lineage()       【A2：冪等，不 409】
#   ④ POST   /api/lineages/{id}/archive           → archive_lineage()
#   ⑤ GET    /api/lineages/summary?student_name=  → lineage_summary()
#   ⑥ GET    /api/student-lineages?student_name=  → list_student_lineages()
#   ⑦ POST   /api/student-lineages                → join_student_lineage()
#   ⑧ DELETE /api/student-lineages                → leave_student_lineage()
#
# （§4.2 表格共 7 行；第 1 行 `GET /api/lineages` 有兩種身分（老師 / 學生），
#   故本層拆成 ① ② 兩個函數 —— 兩者查的是同一張 `lineage`，不是第二套真相）
#
# 五條寫死在本段的紀律（後續子步不得改）：
#   ① **每條對外函數的第一句都是 `lineage_gate()`**：flag off → 404 `lineage_disabled`（§4.4），
#      之後才談參數 / 業務校驗。順序不可顛倒 —— 倒過來 flag off 時會漏出 400 而不是 404；
#   ② **寫點唯一**：`lineage` 表與歸屬行（`patient_teachers` 升級版 = `student_lineage` 的實現，
#      §2.2）的寫入全部在本段，且一經寫入必落 `lineage_id`（§2.4 紀律 1）；
#   ③ **退出 = `status='inactive'`**：不刪行、不刪業務資料（§1.4 雙主權：歸屬 ≠ 所有權）；
#   ④ **既有函數一字不改**：`add_patient_teacher()` / `teacher_add_student()` 的語句不動
#      （§4.3「歸屬組」的 flag on 改造屬**待批**子步）；本段只在必要時**調用**
#      `teacher_add_student()` 做帳號 / 積分初始化，歸屬行仍由本段單一寫入
#      （理由見 `join_student_lineage()` 的 docstring）；
#   ⑤ **不碰 HTTP**：本段一律拋 `LineageError`，狀態碼由接口層按 `LINEAGE_ERROR_STATUS`
#      翻譯（§4.1 的唯一映射表），本段不 import fastapi。
# ---------------------------------------------------------------------------
LINEAGE_STATUS_ACTIVE = "active"
LINEAGE_STATUS_ARCHIVED = "archived"
LINEAGE_STATUSES = (LINEAGE_STATUS_ACTIVE, LINEAGE_STATUS_ARCHIVED)   # §2.1 白名單（DB 零 CHECK）
STUDENT_LINEAGE_MAX = 3          # §2.2 上限：沿用既有「最多 3 位老師」的**數值**語義
MEMBERSHIP_ACTIVE = "active"     # 歸屬行 `status` 的兩個取值（`patient_teachers` 既有語義）
MEMBERSHIP_INACTIVE = "inactive"


def default_lineage_name(teacher_name):
    """§6.1-③ 默認中文名 = `<老師名>師門`。**唯一實現**在 0005（`lineage_name_for()`）。

    本函數只做轉發（與 `slugify()` 同口徑：0005 載入不了時回落同款算法），
    避免「同一個命名規則」在服務層與遷移裡各寫一份。
    """
    module = _migration_0005()
    if module is not None:
        return module.lineage_name_for(teacher_name)
    return "%s師門" % ("" if teacher_name is None else str(teacher_name))


def lineage_gate():
    """**每條新接口的第一道門**（§4.2 / §4.4）：flag → 存儲就緒；任一不滿足直接拋。

      · flag off（默認）→ 404 `lineage_disabled`（`/api/lineages*` / `/api/student-lineages*` 全部）；
      · flag on 但 `lineage` 表缺失（遷移未跑）→ 503 `lineage_store_unavailable`
        （照抄 `template_store_unavailable` 的部署態語義）。

    接口層 `lineage_api._guard()` 調的就是本函數（**同一個實現口徑**，不另寫一份判斷）；
    對外函數自己再調一次是為了讓「直接 import 本模組」的調用方也走同一道門。
    """
    if not lineage_enabled():
        raise LineageError(
            LINEAGE_DISABLED, "師門接口未啟用：請設置環境變量 LINEAGE_ENABLED=on（設計 §4.4）"
        )
    if not lineage_store_ready():
        raise LineageError(
            LINEAGE_STORE_UNAVAILABLE, "師門表未就緒，請先執行資料庫遷移（0005_add_lineage）"
        )


def require_teacher_identity(teacher_name, teacher_id):
    """老師側**寫**接口的雙因子校驗（§4.2：開山門 / 封存都要 `teacher_name` + `teacher_id`）。

    `teacher_id` 在全庫的既有語義 = 「與 `teacher_name` 相同的那個校驗值」（前端一直這麼傳；
    後端無登錄體系，此邊界 §5.1 已明示）。故本函數只做**形狀 + 一致性**校驗：
      · `teacher_name` 空 → 400 `lineage_required`；
      · `teacher_id` 空 → 400 `lineage_invalid`（缺校驗值 ≠ 缺身份）；
      · 兩者不一致 → 403 `lineage_forbidden`（雙因子失敗，不提示哪一半錯）。
    返回去空白後的 `teacher_name`。
    """
    teacher = (teacher_name or "").strip()
    if not teacher:
        raise LineageError(LINEAGE_REQUIRED, "缺少老師身份（teacher_name）")
    identity = (teacher_id or "").strip()
    if not identity:
        raise LineageError(
            LINEAGE_INVALID, "缺少老師身份校驗值（teacher_id）：開山門 / 封存必須帶 teacher_id"
        )
    if identity != teacher:
        raise LineageError(LINEAGE_FORBIDDEN, "teacher_name 與 teacher_id 不一致")
    return teacher


def _require_student_name(student_name):
    """學生側接口的身份校驗（§4.2）：空 → 400 `lineage_required`。"""
    student = (student_name or "").strip()
    if not student:
        raise LineageError(LINEAGE_REQUIRED, "缺少學生身份（student_name）")
    return student


def _fetch_all(sql, params=()):
    """只讀查詢 → `list[sqlite3.Row]`；讀庫失敗 → 503 `lineage_store_unavailable`。

    只捕 `sqlite3.Error`：走到這裡時 `lineage_store_ready()` 已過，還能失敗就是庫被鎖 /
    表被改名等部署態問題，不偽裝成 4xx（與 `load_lineage()` 同口徑）。
    """
    conn = _store_connection()
    try:
        return conn.execute(sql, params).fetchall()
    except sqlite3.Error:
        raise LineageError(
            LINEAGE_STORE_UNAVAILABLE, "師門表讀取失敗，請確認資料庫遷移（0005_add_lineage）已就緒"
        )
    finally:
        conn.close()


def _lineage_dict(row):
    """`lineage` 行 → 對外字典（欄位名前綴一字不改，前端只認這一種形狀）。"""
    if row is None:
        return None
    return {
        "id": row["id"],
        "name": row["name"],
        "owner_teacher_name": row["owner_teacher_name"],
        "description": row["description"] or "",
        "status": row["status"],
        "created_at": row["created_at"] or "",
        "updated_at": row["updated_at"] or "",
    }


def _membership_dict(row):
    """歸屬行 → 對外字典：**只有歸屬欄位**，不含患者病歷內容（雙主權：師門只看得到歸屬）。"""
    if row is None:
        return None
    return {
        "student_name": row["patient_name"],
        "teacher_name": row["teacher_name"],
        "lineage_id": row["lineage_id"] or "",
        "status": row["status"],
        "joined_at": row["created_at"] or "",
    }


def _now_iso():
    """時間列口徑（§2.1）：與 `templates.created_at/updated_at` 同款 —— `datetime.now().isoformat()`。"""
    return datetime.now().isoformat()


# ---------------------------------------------------------------------------
# 老師側（§7.2 階段一：一師一門 → 老師端**沒有切換器**，讀的就是自己開創的那一門）
# ---------------------------------------------------------------------------
_LINEAGE_TEACHER_SQL = (
    # §2.5 索引 `idx_lineage_owner (owner_teacher_name, status)` 正好命中本查詢的前兩列
    "SELECT * FROM lineage WHERE owner_teacher_name = ? ORDER BY status, created_at, id"
)
_LINEAGE_STUDENT_SQL = (
    # 學生側：歸屬行 → 師門（INNER JOIN：`lineage_id = ''` 的未歸屬行不參與，§2.4 紀律 2）
    "SELECT l.id AS lineage_id, l.name AS name, l.owner_teacher_name AS owner_teacher_name, "
    "l.description AS description, l.status AS status, l.created_at AS created_at, "
    "l.updated_at AS updated_at, pt.teacher_name AS teacher_name, "
    "pt.status AS membership_status, pt.created_at AS joined_at "
    "FROM patient_teachers pt INNER JOIN lineage l ON l.id = pt.lineage_id "
    "WHERE pt.patient_name = ? AND pt.status = ? "
    "ORDER BY l.status, l.created_at, l.id"
)


def list_lineages_by_teacher(teacher_name):
    """`GET /api/lineages?teacher_name=`（§4.2 / §7.2）：老師**開創**的師門清單。

    三條口徑：
      · 階段一 = 一師一門 → 正常只有 0 或 1 行；查詢仍按清單形狀返回（`ORDER BY status,
        created_at, id`，`active` 在 `archived` 之前），將來放開一師多門時接口形狀不變；
      · **含 `status='archived'`**：§7.2 要求前端顯示「已封存」提示條 —— 封存 ≠ 不可見；
      · 排序完全確定（`created_at` 相同的歷史行再按 `id` 兜底），不依賴 SQLite 隱式順序。
    """
    lineage_gate()
    teacher = (teacher_name or "").strip()
    if not teacher:
        raise LineageError(LINEAGE_REQUIRED, "缺少老師身份（teacher_name）")
    return [_lineage_dict(row) for row in _fetch_all(_LINEAGE_TEACHER_SQL, (teacher,))]


def list_lineages_by_student(student_name):
    """`GET /api/lineages?student_name=`（§4.2 / §3.4）：學生**當前有效**的師門（`pt.status='active'`）。

    與 `list_student_lineages()` 的分工（兩者同源於 `patient_teachers`，**不是**第二套真相）：
      · 本函數 = 「可切換的師門上下文」（§7.3 切換器的數據源，只含 active 歸屬）；
      · `list_student_lineages()` = 「我的師門（歸屬清單 + 退出歷史 + 未歸屬提示）」。

    每行同時給 `status`（師門自身的 active / archived）與 `membership_status`（歸屬行的
    active / inactive）：前端據前者畫「已封存」徽章、據後者判斷是否在門內，不必二次查詢。
    """
    lineage_gate()
    student = _require_student_name(student_name)
    rows = _fetch_all(_LINEAGE_STUDENT_SQL, (student, MEMBERSHIP_ACTIVE))
    out = []
    for row in rows:
        item = dict(row)
        for key in ("status", "description", "created_at", "updated_at", "joined_at",
                    "membership_status", "teacher_name"):
            item[key] = item[key] or ""
        out.append(item)
    return out


def _find_lineage_by_owner(teacher_name):
    """一師一門（§2.1）的**唯一查法**：按 `owner_teacher_name` 取一行（`sqlite3.Row` 或 `None`）。"""
    rows = _fetch_all(_LINEAGE_TEACHER_SQL, (teacher_name,))
    return rows[0] if rows else None


def create_lineage(teacher_name, teacher_id, name=None):
    """`POST /api/lineages`（§4.2 / 附錄 A2 裁決）：開山門。**重複 → 200 + 既有行（冪等，不 409）**。

    七條口徑：
      · 雙因子：`teacher_name` + `teacher_id` 一致（`require_teacher_identity()`）；
      · 一師一門（§2.1）：先按 `owner_teacher_name` 查既有行 → 命中即冪等返回、**不新建第二行**
        （「一師一門」因此在服務層成立；DB 層不加 UNIQUE，全庫零約束紀律不破）；
      · `id` = `default_lineage_id(teacher_name)`（§5.4 第 6 條：**計算**得出，不落常量）；
      · `name`：`None`（請求體沒帶這個鍵）→ 默認 `<老師名>師門`（§6.1-③ / A5：階段一不可編輯）；
        **顯式空串 / 全空白 → 400 `lineage_invalid`**（§4.1 表格：「`name` 空」）。
        這是本接口唯一需要分辨「缺鍵」與「空值」的欄位，故兩種入參行為不同；
      · 已封存（`archived`）的師門**不**因重複開山門而回到 `active`（封存是留痕，不是可反覆
        開關的旗標），但會在 `warnings` 裡明示；
      · 新建行固定 `description = ''`、`created_at = updated_at = 本次時間`（§2.1：ISO 字串）；
      · 併發同 id 寫入（唯一競態窗口）→ 捕 `IntegrityError` 後讀回既有行，仍按冪等返回
        （`created=false`）。
    """
    lineage_gate()
    teacher = require_teacher_identity(teacher_name, teacher_id)
    if name is None:
        lineage_name = default_lineage_name(teacher)
    else:
        lineage_name = str(name).strip()
        if not lineage_name:
            raise LineageError(
                LINEAGE_INVALID,
                "師門名稱（name）不可為空：不帶 name 時默認「%s」" % default_lineage_name(teacher),
            )
    existing = _find_lineage_by_owner(teacher)
    if existing is not None:
        warnings = []
        if existing["status"] == LINEAGE_STATUS_ARCHIVED:
            warnings.append("該師門已封存（status=archived）：開山門為冪等操作，不改動既有行的狀態或名稱")
        expected_id = default_lineage_id(teacher)
        if existing["id"] != expected_id:
            warnings.append(
                "既有師門 id 與 `lin-<slug>` 口徑不一致（歷史行）：以既有行為準、不新建（口徑 = %s）"
                % expected_id
            )
        return {"lineage": _lineage_dict(existing), "created": False, "warnings": warnings}

    expected_id = default_lineage_id(teacher)
    now = _now_iso()
    created = False
    row = None
    conn = _store_connection()
    try:
        try:
            conn.execute(
                "INSERT INTO lineage (id, name, owner_teacher_name, description, status, "
                "created_at, updated_at) VALUES (?, ?, ?, '', ?, ?, ?)",
                (expected_id, lineage_name, teacher, LINEAGE_STATUS_ACTIVE, now, now),
            )
            conn.commit()
            created = True
        except sqlite3.IntegrityError:
            # 併發：同 id（PK）已被寫入 → 退化成「冪等返回既有行」，不把競態暴露成 500
            conn.rollback()
        except sqlite3.Error:
            conn.rollback()
            raise LineageError(
                LINEAGE_STORE_UNAVAILABLE, "師門寫入失敗，請確認資料庫遷移（0005_add_lineage）已就緒"
            )
        row = conn.execute("SELECT * FROM lineage WHERE id = ?", (expected_id,)).fetchone()
    finally:
        conn.close()
    if row is None:
        raise LineageError(
            LINEAGE_STORE_UNAVAILABLE,
            "師門寫入後讀回失敗：%s（請確認資料庫可寫且遷移已就緒）" % expected_id,
        )
    return {"lineage": _lineage_dict(row), "created": created, "warnings": []}


def archive_lineage(lineage_id, teacher_name, teacher_id):
    """`POST /api/lineages/{id}/archive`（§4.2）：封存（**不提供 DELETE**，沿用 Epic 1 §10.1）。

    五條口徑：
      · 雙因子 + 存在性 + 歸屬，一律走既有校驗：缺參數 → 400 / 不存在 → 404 / 別門 → 403；
      · **只改 `status` 與 `updated_at`**：不動 `patient_teachers`（學生歸屬與其業務資料一律保留，
        §5.5-3「退出不丟數據」同款精神）、不刪任何行、不動其他表的 `lineage_id`；
      · 重複封存 → 200 且 `changed=false`（連 `updated_at` 都不改，前端據此做「已封存」判斷）；
      · 封存後該師門**不再接受新加入**（`join_student_lineage()` 直接拒），歷史行照樣可讀
        （`teacher_in_lineage()` 不看 `status`，故老師仍讀得到本門歷史）；
      · 名稱不可編輯（A5）→ 改名 = 封存 + 新建，故本接口沒有第二個可寫欄位
        （也就**不提供** `PATCH /api/lineages/{id}`）。
    """
    lineage_gate()
    teacher = require_teacher_identity(teacher_name, teacher_id)
    lineage = parse_lineage_id(lineage_id)
    row = load_lineage(lineage)
    if row is None:
        raise LineageError(LINEAGE_NOT_FOUND, "師門不存在：%s（請核對 lineage_id）" % lineage)
    if not teacher_in_lineage(row, teacher):
        raise LineageError(LINEAGE_FORBIDDEN, "無權以「%s」的身份封存師門 %s" % (teacher, lineage))
    if row["status"] == LINEAGE_STATUS_ARCHIVED:
        return {
            "lineage": _lineage_dict(row), "archived": True, "changed": False,
            "warnings": ["該師門已是封存態：重複封存不改變任何欄位（含 updated_at）"],
        }
    conn = _store_connection()
    try:
        conn.execute(
            "UPDATE lineage SET status = ?, updated_at = ? WHERE id = ?",
            (LINEAGE_STATUS_ARCHIVED, _now_iso(), lineage),
        )
        conn.commit()
        updated = conn.execute("SELECT * FROM lineage WHERE id = ?", (lineage,)).fetchone()
    except sqlite3.Error:
        conn.rollback()
        raise LineageError(
            LINEAGE_STORE_UNAVAILABLE, "師門寫入失敗，請確認資料庫遷移（0005_add_lineage）已就緒"
        )
    finally:
        conn.close()
    if updated is None:
        raise LineageError(LINEAGE_STORE_UNAVAILABLE, "師門寫入後讀回失敗：%s" % lineage)
    return {
        "lineage": _lineage_dict(updated), "archived": True, "changed": True,
        "warnings": ["封存只回收「可加入」：學生歸屬與其病歷一律保留（§5.5-3），歷史讀取不受影響"],
    }


# ---------------------------------------------------------------------------
# 學生側（§3.4 / §7.3）：歸屬生命週期 = 加入 → 退出（`inactive`）→ 再加入
#   · 唯一寫點 `_upsert_membership()`；「退出」= 改 `status`，**永不刪行**（雙主權 §1.4）
#   · 上限 `STUDENT_LINEAGE_MAX`（3）：與既有「最多 3 位老師」數值一致（§2.2）
# ---------------------------------------------------------------------------
_STUDENT_MEMBERSHIP_SQL = (
    # 「我的師門」：歸屬清單 + 退出歷史（**LEFT JOIN**：`lineage_id = ''` 的未歸屬行也要出現，
    # 以 `unassigned=true` 標明 —— §7.3「未歸屬資料請聯絡管理員」的數據來源）
    "SELECT pt.patient_name AS student_name, pt.teacher_name AS teacher_name, "
    "pt.status AS status, pt.created_at AS joined_at, pt.lineage_id AS lineage_id, "
    "l.name AS name, l.status AS lineage_status, l.owner_teacher_name AS owner_teacher_name "
    "FROM patient_teachers pt LEFT JOIN lineage l ON l.id = pt.lineage_id "
    "WHERE pt.patient_name = ? "
    "ORDER BY CASE WHEN pt.status = ? THEN 0 ELSE 1 END, pt.created_at, pt.lineage_id"
)


def _membership_view(row):
    """歸屬清單一行 → 對外字典（`list_student_lineages()` / `lineage_summary()` 共用）。

    兩個狀態欄位**不可混用**：`status` = 歸屬行（active = 在門內 / inactive = 已退出），
    `lineage_status` = 師門自身（active / archived）。`unassigned` = 該行沒有師門
    （`lineage_id = ''`，§2.4 未歸屬）：此時 `name` / `lineage_status` 一律空串，
    前端據 `unassigned` 顯示「未歸屬」提示，**不得**自行兜底成某個師門。
    """
    item = {
        "student_name": row["student_name"],
        "teacher_name": row["teacher_name"] or "",
        "lineage_id": row["lineage_id"] or "",
        "name": row["name"] or "",
        "status": row["status"] or "",
        "lineage_status": row["lineage_status"] or "",
        "owner_teacher_name": row["owner_teacher_name"] or "",
        "joined_at": row["joined_at"] or "",
    }
    item["unassigned"] = not item["lineage_id"]
    return item


def list_student_lineages(student_name):
    """`GET /api/student-lineages?student_name=`（§3.4 表格第 1 行）：我的師門（**含退出歷史**）。

    四條口徑：
      · 返回 `active` + `inactive` 兩種歸屬行，並帶 `lineage.name` 與老師名（§3.4 明文）；
      · `LEFT JOIN lineage`：`lineage_id = ''` 的未歸屬行**照樣返回**並標 `unassigned=true`
        （§7.3：提示「未歸屬資料請聯絡管理員」，不是靜默丟掉）；
      · 排序：在門內（active）在前、退出歷史在後；同段內按 `joined_at`、`lineage_id` 穩定排序；
      · 本接口是 §7.1「兩個維度並存」的**唯一數據源**（「我的老師（n/3）」與「我的師門」同源），
        故一次給足兩邊要用的欄位（老師名 + 師門名 + 兩種狀態），前端不必再拼第二個接口。
    """
    lineage_gate()
    student = _require_student_name(student_name)
    rows = _fetch_all(_STUDENT_MEMBERSHIP_SQL, (student, MEMBERSHIP_ACTIVE))
    return [_membership_view(row) for row in rows]


def _active_membership_count(student_name):
    """該學生**當前在門內**的師門數（§2.2 上限判定的唯一查法：只數 `status='active'`）。

    只讀、獨立於寫入（`join_student_lineage()` 在**任何寫入之前**調用，故拒絕時庫內零新行）。
    """
    row = _fetch_all(
        "SELECT COUNT(*) AS active_count FROM patient_teachers "
        "WHERE patient_name = ? AND status = ?",
        (student_name, MEMBERSHIP_ACTIVE),
    )[0]
    return row["active_count"]


def _upsert_membership(student_name, teacher_name, lineage_id):
    """歸屬行的**唯一寫點**（`patient_teachers` 升級版 = `student_lineage` 的實現，§2.2）。

    三條口徑：
      · 先 `UPDATE`（命中既有行 = 就地改成 `status='active'` + 本師門 `lineage_id`）：
        一招覆蓋三種既有行 —— 退出留痕（`inactive`）、未歸屬行（`lineage_id = ''`）、
        跨門行（別的 `lineage_id`）。**一律不新增行、不刪歷史**（PK `(patient_name, teacher_name)`
        不變，§2.2「唯一性」明文不加 `UNIQUE(patient_name, lineage_id)`）；
      · 只有 `rowcount == 0` 才 `INSERT`（`created_at` = 本次真實時間；既有
        `add_patient_teacher()` 的固定日期屬演示寫法，本接口不沿用）；
      · 同一個連接 / 同一個事務：中間失敗（庫鎖等）→ 回滾 + 503，不留半截資料。
    返回 `(歸屬行 sqlite3.Row 或 None, 是否新建)`。
    """
    conn = _store_connection()
    try:
        cursor = conn.execute(
            "UPDATE patient_teachers SET lineage_id = ?, status = ? "
            "WHERE patient_name = ? AND teacher_name = ?",
            (lineage_id, MEMBERSHIP_ACTIVE, student_name, teacher_name),
        )
        created = cursor.rowcount == 0
        if created:
            conn.execute(
                "INSERT INTO patient_teachers (patient_name, teacher_name, status, created_at, "
                "lineage_id) VALUES (?, ?, ?, ?, ?)",
                (student_name, teacher_name, MEMBERSHIP_ACTIVE, _now_iso(), lineage_id),
            )
        conn.commit()
        row = conn.execute(
            "SELECT * FROM patient_teachers WHERE patient_name = ? AND teacher_name = ?",
            (student_name, teacher_name),
        ).fetchone()
    except sqlite3.Error:
        conn.rollback()
        raise LineageError(
            LINEAGE_STORE_UNAVAILABLE, "歸屬寫入失敗，請確認資料庫遷移（0005_add_lineage）已就緒"
        )
    finally:
        conn.close()
    return row, created


def join_student_lineage(student_name, lineage_id, teacher_name=None):
    """`POST /api/student-lineages`（§3.4 表格第 2 行）：加入師門。**學生自加 / 老師拉入同一接口**。

    `teacher_name` 是**分岔鍵**：
      · 空 → **學生自加**：只寫歸屬行。業務語義沿用既有 `database.add_patient_teacher()`
        （3 個上限、已存在則不重複插行），但**不復用它的返回值**：它把「超限」與「已在名單」
        混成同一個 `error` 字串，本接口要的是兩種不同回應（409 vs 冪等 200），
        且它的固定 `created_at`（演示寫法）與 `lineage_id` 缺失都不合本接口要求；
      · 非空 → **老師拉入**（§3.4）：先校驗該老師確為本師門 owner，再調**既有**的
        `database.teacher_add_student()` 做帳號 / 積分初始化 —— 「新學生帳號怎麼建」因此
        仍只有**一份實現**（該函數語句一字不改；§4.3 歸屬組的 flag on 改造屬待批子步）。
        它順手插的那行歸屬（`lineage_id = ''`）會被緊接著的 `_upsert_membership()` **就地更新**
        到本師門，故歸屬行始終只有本服務一個寫點。

    五道校驗（順序 = 便宜在前、貴在後；一律 fail-loud，§5.2「漏改的表現必須是 4xx」）：
      `lineage_gate()` → 學生名 / `lineage_id` 形狀 → 師門存在（404）→ 師門未封存（400）
      → 老師歸屬（403，僅老師拉入時）。
    上限：在門數 ≥ `STUDENT_LINEAGE_MAX` → 409 `student_lineage_limit`，**判定在寫入之前**
      → 拒絕時庫內零新行（§8 ⑥ 組判據）。
    冪等：已在該師門（歸屬行 active 且 `lineage_id` 相同）→ `changed=false` 且**零寫入**。
    """
    lineage_gate()
    student = _require_student_name(student_name)
    lineage = parse_lineage_id(lineage_id)
    teacher = (teacher_name or "").strip()
    row = load_lineage(lineage)
    if row is None:
        raise LineageError(LINEAGE_NOT_FOUND, "師門不存在：%s（請核對 lineage_id）" % lineage)
    if row["status"] != LINEAGE_STATUS_ACTIVE:
        raise LineageError(
            LINEAGE_INVALID, "師門已封存（status=archived），不接受新加入：%s" % lineage
        )
    if teacher and not teacher_in_lineage(row, teacher):
        raise LineageError(
            LINEAGE_FORBIDDEN, "無權以「%s」的身份拉學生加入師門 %s" % (teacher, lineage)
        )
    # 階段一一師一門：歸屬行的 teacher_name = 師門 owner（不取請求裡的 teacher_name，
    # 避免「老師名與師門 owner 不一致」時寫出一行 owner 之外的歸屬）
    owner = row["owner_teacher_name"]
    existing = _fetch_all(
        "SELECT patient_name, teacher_name, status, created_at, lineage_id "
        "FROM patient_teachers WHERE patient_name = ? AND teacher_name = ?",
        (student, owner),
    )
    if existing and existing[0]["status"] == MEMBERSHIP_ACTIVE \
            and (existing[0]["lineage_id"] or "") == lineage:
        return {
            "student_lineage": _membership_dict(existing[0]), "joined": True,
            "reactivated": False, "changed": False,
            "warnings": ["該學生已在本師門內：重複加入不改變任何欄位"],
        }
    active_count = _active_membership_count(student)
    if active_count >= STUDENT_LINEAGE_MAX:
        raise LineageError(
            STUDENT_LINEAGE_LIMIT,
            "最多只能同時加入 %d 個師門（現有 %d 個）：請先退出一個師門再加入"
            % (STUDENT_LINEAGE_MAX, active_count),
        )
    reactivated = bool(existing) and existing[0]["status"] != MEMBERSHIP_ACTIVE
    if teacher:
        import database   # 函數體內 import（模組 docstring 口徑 ③）
        database.teacher_add_student(teacher, student)
    membership, created = _upsert_membership(student, owner, lineage)
    if membership is None:
        raise LineageError(
            LINEAGE_STORE_UNAVAILABLE, "歸屬寫入後讀回失敗：%s × %s" % (student, owner)
        )
    warnings = []
    if reactivated:
        warnings.append("該學生曾退出本師門：本次為「再加入」，既有病歷與歸屬歷史一律保留")
    elif created:
        warnings.append("首次加入本師門：歸屬行新建（created_at = 本次時間）")
    return {
        "student_lineage": _membership_dict(membership), "joined": True,
        "reactivated": reactivated, "changed": True, "warnings": warnings,
    }


def leave_student_lineage(student_name, lineage_id):
    """`DELETE /api/student-lineages`（§3.4 表格第 3 行）：退出師門（**退出 ≠ 刪除**）。

    五條口徑：
      · 退出 = 歸屬行 `status='inactive'`：**不刪行、不刪業務資料**（§1.4 雙主權：
        「退出師門 ≠ 刪除病歷」；學生仍讀得到自己的資料，只是該老師不再看得到**本師門**的行）；
      · 找不到歸屬行（含「從未加入」與「只有未歸屬行 `lineage_id = ''`」兩種情形）
        → 403 `lineage_forbidden`（§4.1：「學生不在該師門」）；
      · 已是退出態 → 200 且 `changed=false`（重複退出不改變任何欄位）；
      · 定位鍵 = `(patient_name, lineage_id)`：階段一一師一門，一個 `lineage_id` 只對應一位老師；
      · 本接口**不**改 `patients` / 病歷 / 草案的任何 `lineage_id`（雙主權：不得讓歸屬成為
        資料存續的前置條件 —— 導出 / 刪除義務見 §11-12，屬階段二）。
    """
    lineage_gate()
    student = _require_student_name(student_name)
    lineage = parse_lineage_id(lineage_id)
    conn = _store_connection()
    try:
        row = conn.execute(
            "SELECT * FROM patient_teachers WHERE patient_name = ? AND lineage_id = ?",
            (student, lineage),
        ).fetchone()
        if row is None:
            raise LineageError(
                LINEAGE_FORBIDDEN, "該學生不在師門 %s 內（無可退出的歸屬）" % lineage
            )
        if row["status"] != MEMBERSHIP_ACTIVE:
            return {
                "student_lineage": _membership_dict(row), "left": True, "changed": False,
                "warnings": ["已是退出態：重複退出不改變任何欄位，資料亦不刪除"],
            }
        conn.execute(
            "UPDATE patient_teachers SET status = ? WHERE patient_name = ? AND lineage_id = ?",
            (MEMBERSHIP_INACTIVE, student, lineage),
        )
        conn.commit()
        updated = conn.execute(
            "SELECT * FROM patient_teachers WHERE patient_name = ? AND lineage_id = ?",
            (student, lineage),
        ).fetchone()
    except sqlite3.Error:
        conn.rollback()
        raise LineageError(
            LINEAGE_STORE_UNAVAILABLE, "歸屬寫入失敗，請確認資料庫遷移（0005_add_lineage）已就緒"
        )
    finally:
        conn.close()
    if updated is None:
        raise LineageError(
            LINEAGE_STORE_UNAVAILABLE, "退出後讀回失敗：%s × %s" % (student, lineage)
        )
    return {
        "student_lineage": _membership_dict(updated), "left": True, "changed": True,
        "warnings": ["退出後老師不再看得到你在本師門的資料；**資料不會被刪除**（§1.4 雙主權）"],
    }


def lineage_summary(student_name):
    """`GET /api/lineages/summary?student_name=`（§3.4 表格第 4 行）：跨師門**只讀聚合**。

    四條口徑：
      · 每個「當前有效的師門」（`list_lineages_by_student()`）一項，各含：
        就診數（`patient_records`）、未簽草案數（`drafts.signed = 0`）、最近活動（`MAX(visit_at)`）；
      · `patient_records` / `drafts` 都有 `lineage_id` 列（§2.3 十二張表之一）→ 統計口徑與老師端
        讀點**同一份**「歸屬 = 可見範圍」語義，不是另一套算法；
      · **不做**單一合成等級 / 段位（§11-4：段位屬 Epic 5 §D5），只回可核對的數字；
      · `lineage_id = ''` 的未歸屬行不進任何一項（§2.4 紀律 2：不猜歸屬、不把孤兒行算進彙總）。
    """
    lineage_gate()
    student = _require_student_name(student_name)
    memberships = list_lineages_by_student(student)
    conn = _store_connection()
    try:
        summary = []
        for membership in memberships:
            lineage = membership["lineage_id"]
            visits = conn.execute(
                "SELECT COUNT(*) AS visits, MAX(visit_at) AS last_visit_at FROM patient_records "
                "WHERE patient_name = ? AND lineage_id = ?",
                (student, lineage),
            ).fetchone()
            drafts = conn.execute(
                "SELECT COUNT(*) AS unsigned_drafts FROM drafts "
                "WHERE patient_name = ? AND lineage_id = ? AND signed = 0",
                (student, lineage),
            ).fetchone()
            summary.append({
                "lineage_id": lineage,
                "name": membership["name"],
                "teacher_name": membership["teacher_name"],
                "status": membership["status"],
                "visits": visits["visits"],
                "unsigned_drafts": drafts["unsigned_drafts"],
                "last_visit_at": visits["last_visit_at"] or "",
            })
    except sqlite3.Error:
        raise LineageError(
            LINEAGE_STORE_UNAVAILABLE, "師門統計讀取失敗，請確認資料庫遷移（0005_add_lineage）已就緒"
        )
    finally:
        conn.close()
    return {"student_name": student, "summary": summary}
