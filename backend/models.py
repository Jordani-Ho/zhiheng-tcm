"""`/api/templates` 的 Pydantic 請求體（Epic 1 · 設計 §10.1；原 `template_api.py` L124–L158 整段搬移）

約定（原註解一字不改地跟著搬過來）：
  - `schema_json` 欄位在前端叫 `schema_json`，在模型裡故意叫 `template_schema` + `Field(alias=...)`：
    避免遮蔽 `BaseModel.schema_json`（pydantic 2.x 會對 shadow 欄位發 UserWarning）；
    `populate_by_name=True` 讓別名與欄位名兩種鍵名都能收。
  - `template_schema: Any` 故意不做結構約束：不合法由服務層校驗回 400 `schema_invalid`，
    而不是 FastAPI 自動回 422（設計 §10.1 錯誤碼契約）。
  - 本模組只放「請求體」：不含路由、不含服務層；`database.py` 亦 re-export 這四個類，
    舊入口 `database.Template*Input` 仍可用。
"""
from typing import Any, Optional

from pydantic import BaseModel, ConfigDict, Field


class TemplateCreateInput(BaseModel):
    # 欄位名故意不叫 `schema_json`：那會遮蔽 `BaseModel.schema_json`（pydantic 會發 UserWarning）。
    # 對外仍用別名 `schema_json`，請求體結構與設計 §10.1 一字不差。
    model_config = ConfigDict(populate_by_name=True)

    teacher_name: str
    teacher_id: str
    type: str
    name: str = ""
    # 故意用 Any：結構不合法由校驗層回 400 schema_invalid（而不是 FastAPI 的 422）
    template_schema: Any = Field(default=None, alias="schema_json")
    lineage_id: str = ""


class TemplateUpdateInput(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    teacher_name: str
    teacher_id: str
    # None = 「本次不改」。只允許改這兩個鍵（§10.1：不提供改 type / teacher_id / … 的通用 PUT）
    name: Optional[str] = None
    template_schema: Any = Field(default=None, alias="schema_json")


class TemplateActionInput(BaseModel):
    teacher_name: str
    teacher_id: str


class TemplateDeriveInput(TemplateActionInput):
    name: Optional[str] = None
    parent_template_id: Optional[int] = None
    lineage_id: str = ""


# ---------- Epic 4 §4.2：師門 / 歸屬 請求體（`lineage_api.py` 專用） ----------
# 本段三個類的欄位**一律給默認值**（`str = ""` / `Optional[str] = None`），刻意**不用**必填欄位：
#   §4.4 要求「flag off → 7 個端點一律 404 `lineage_disabled`」，而 FastAPI 的 body 校驗發生在
#   **函數體之前** —— 欄位必填的話，「缺欄位 + flag off」會先被框架回 422，蓋掉 flag 門；
#   故把 body 校驗刻意留給服務層（統一錯誤體 400 / 404，§4.1 錯誤碼契約）。
#   （完全不帶 body 的請求仍由 FastAPI 回 422，這點與 Epic 1 `template_api.py` 相同。）


class _LineageBody(BaseModel):
    """共用基底：只帶「缺鍵也不 422」的默認值口徑，**不做**任何鑑權 / 形狀校驗（校驗一律在服務層）。"""

    model_config = ConfigDict(populate_by_name=True)


class LineageOwnerInput(_LineageBody):
    """老師操作**自己**師門的請求體（`POST /api/lineages`、`POST /api/lineages/{id}/archive` 共用）。

    `teacher_name` + `teacher_id` 是「名稱 / ID 一致」的雙欄位鑑權（`require_teacher_identity()`）：
      · `POST /api/lineages` → 缺名 / 不一致 → 400 `lineage_invalid`（開山門不接受空老師名）；
      · `POST .../archive`  → 名稱不符 owner（或老師根本不在該門）→ 403 `lineage_forbidden`。
    """

    teacher_name: str = ""
    teacher_id: str = ""


class LineageCreateInput(LineageOwnerInput):
    """`POST /api/lineages`（開山門，A2 裁決：已開過 → 200 冪等）。

    `name` 的三種情形（`create_lineage()` 內分岔）：
      · 缺鍵（`None`）→ 用 `default_lineage_name()`（「老師名 + 的師門」）；
      · 顯式空字串（`""`）→ 400 `lineage_invalid`（「缺鍵」與「明確要一個空名」是兩種意思）；
      · 其他 → 去空白後使用。
    """

    name: Optional[str] = None


class StudentLineageInput(_LineageBody):
    """`POST /api/student-lineages`：學生自加（`teacher_name` 空）/ 老師拉入（`teacher_name` 非空）。

    `teacher_name` 是**分岔鍵**、不是必填鑑權：空 → 學生自加（只寫歸屬行）；
    非空 → 老師拉入（先校驗該老師確為師門 owner，再走既有 `database.teacher_add_student()`
    做帳號 / 積分初始化）。超上限（3 個在門師門）→ 409 `student_lineage_limit`。
    """

    student_name: str = ""
    lineage_id: str = ""
    teacher_name: str = ""
