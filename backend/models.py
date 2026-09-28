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
