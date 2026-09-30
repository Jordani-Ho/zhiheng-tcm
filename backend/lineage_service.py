"""師門（lineage）隔離的**服務層**：feature flag + 錯誤碼契約 + 老師端讀點的雙因子校驗。

對齊：docs/epic4-lineage-design-v1.md
  §4.1  錯誤碼契約（8 個碼；本步落地「讀路徑」相關的 6 個碼，其餘 2 個隨 4.2 後續 / 4.3 接線）
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
