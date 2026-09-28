"""四類模板 CRUD + 狀態機接口（Epic 1 · 設計第二部分 §9–§11 落地）

對齊：docs/epic1-template-design-v1.md
  §9   四類 `schema_json` 字段級契約（校驗層：非法值一律 400，**不清洗**）
  §10  模板 CRUD 接口（公共約定 + 9 條路徑 + 錯誤碼）
  §11  狀態機（`publish` 同事務自動歸檔舊 `active` 並返回 `archived_ids` / `archive` / `activate` / `derive`）
  §12.4 legacy 兼容（舊 `GET/POST /api/plan_template` 一行不改，仍在 main.py；雙寫屬後續子任務）

約定：
  - 前綴 `/api/templates`（新命名空間，與舊 `/api/plan_template` 並存）；
  - feature flag `TEMPLATE_API_ENABLED`（**默認 off**，§5.2 第 5 條）：off → 全部 404 `templates_disabled`；
  - flag on 但 `templates` 表缺失（遷移未跑）→ 503 `template_store_unavailable`（§7）；
  - 鑑權：每個接口都必須帶 `teacher_name` 與 `teacher_id`（GET 走 query，POST/PUT 走 body），
    兩者不等 → 403 `teacher_mismatch`；只允許操作 `teacher_id` 自己的行（越權 → 403，不回行內容）；
  - 錯誤體：`{"detail": {"error": code, "msg": 繁中, "errors": [...], "warnings": [...]}}`（前端讀 `res.detail.error`）；
  - 不做的事（§10.1）：不提供 `DELETE`；不提供改 `type` / `teacher_id` / `lineage_id` /
    `parent_template_id` / `version` 的通用 `PUT`。

啟用方式（本機 / 生產，PowerShell）：
    $env:TEMPLATE_API_ENABLED = "on"    # 不設或 off = 全部 404，走舊鏈路
"""
import os
from typing import Optional

from fastapi import APIRouter, HTTPException, Request, Response
from fastapi.responses import JSONResponse

import database
from models import (
    TemplateActionInput,
    TemplateCreateInput,
    TemplateDeriveInput,
    TemplateUpdateInput,
)

router = APIRouter(prefix="/api/templates", tags=["templates"])

# 服務層錯誤碼 → HTTP 狀態碼（§10.2 的「主要錯誤」列）
_TEMPLATE_ERROR_STATUS = {
    "template_not_found": 404,
    "template_forbidden": 403,
    "template_published_immutable": 409,
    "template_active_conflict": 409,
    "template_parent_not_found": 400,
    "template_parent_scope_mismatch": 400,
    "template_parent_self_reference": 400,
    "template_parent_future_version": 400,
    "schema_too_large": 400,
}

_ENABLED_VALUES = ("on", "1", "true", "yes")


async def template_error_handler(request: Request, exc: database.TemplateError):
    """服務層 `TemplateError` → 真實 HTTP 狀態碼 + 統一 detail 包裝（§10.1 錯誤響應）。"""
    return JSONResponse(
        status_code=_TEMPLATE_ERROR_STATUS.get(exc.code, 400),
        content={"detail": {"error": exc.code, "msg": exc.msg, "errors": [], "warnings": []}},
    )


def _enabled():
    """flag 每次請求現讀（便於灰度切換 / 測試，不必重啟）。默認 off（§5.2 第 5 條）。"""
    return os.environ.get("TEMPLATE_API_ENABLED", "off").strip().lower() in _ENABLED_VALUES


def _fail(status_code, code, msg, errors=None, warnings=None):
    raise HTTPException(
        status_code=status_code,
        detail={"error": code, "msg": msg, "errors": errors or [], "warnings": warnings or []},
    )


def _guard():
    """每個接口的第一道檢查：flag → 表就緒（§7 / §10.1）。"""
    if not _enabled():
        _fail(404, "templates_disabled", "模板接口未啟用（TEMPLATE_API_ENABLED=off）")
    if not database.template_store_ready():
        _fail(503, "template_store_unavailable", "模板表未就緒，請先執行資料庫遷移")


def _check_identity(teacher_name, teacher_id):
    if not teacher_name or not teacher_id:
        _fail(400, "teacher_required", "必須帶 teacher_name 與 teacher_id")
    if teacher_name != teacher_id:
        _fail(403, "teacher_mismatch", "teacher_name 與 teacher_id 不一致")


def _check_lineage(lineage_id):
    """§10.1：Epic 1 `lineage_id` 一律 `''`，傳非空值直接拒（防前端提前誤用留白字段）。"""
    if lineage_id:
        _fail(400, "lineage_not_supported", "Epic 1 尚不支援 lineage_id（請留空）")


def _check_type(template_type):
    if template_type not in database.TEMPLATE_TYPES:
        _fail(400, "invalid_type", "未知模板類型：%s" % template_type)


def _load_owned(template_id, teacher_id):
    """取行 + 歸屬校驗：不存在 → 404；屬於別的老師 → 403（§10.1：只允許操作自己的行）。"""
    row = database.get_template(template_id)
    if row is None:
        _fail(404, "template_not_found", "找不到該模板")
    if row["teacher_id"] != teacher_id:
        _fail(403, "template_forbidden", "無權操作他人的模板")
    return row


def _validated_schema(template_type, schema_obj, *, for_publish=False):
    """校驗（格式 / 發佈級）+ 尺寸檢查，返回**原樣** schema（不清洗、不補默認值、不刪未知鍵）。"""
    if for_publish:
        ok, errors = database.validate_template_schema_for_publish(template_type, schema_obj)
    else:
        ok, errors = database.validate_template_schema(template_type, schema_obj)
    if not ok:
        _fail(400, "schema_invalid", "模板內容不合法", errors)
    database.serialize_template_schema(schema_obj)   # 超 64 KB → TemplateError → 400 schema_too_large
    return schema_obj


def _warnings_for(row):
    """§9.4：只有 `prescription` 需要「未入庫藥材」黃字提醒；其它三類恆為空陣列。"""
    if row["type"] != "prescription":
        return []
    return database.template_herb_warnings(row["teacher_id"], row.get("schema_json"))


# ---------- 請求體（POST/PUT 走 body 帶 teacher_name / teacher_id，§10.1）----------
# 已抽至 backend/models.py（純結構重構，請求體一字不改；舊入口 `database.Template*Input` 亦保留）

# ---------- 1. 列表 ----------

@router.get("")
def list_templates(
    teacher_name: str,
    teacher_id: str,
    type: Optional[str] = None,
    status: Optional[str] = None,
    include_schema: int = 1,
    lineage_id: Optional[str] = None,
):
    """`GET /api/templates`：缺省返四類全部（排序 `type asc, version desc`）；`include_schema=0` 省流量。"""
    _guard()
    _check_identity(teacher_name, teacher_id)
    _check_lineage(lineage_id)
    if type is not None:
        _check_type(type)
    if status is not None and status not in database.TEMPLATE_STATUSES:
        _fail(400, "invalid_status", "未知狀態：%s" % status)
    rows, counts = database.list_templates(teacher_id, type, status, bool(include_schema))
    return {"templates": rows, "counts": counts}


# ---------- 3. 生效模板（**必須聲明在 /{template_id} 之前**，否則會被當成 id 吃掉）----------

@router.get("/active")
def get_active_template(
    teacher_name: str,
    teacher_id: str,
    type: str,
    lineage_id: Optional[str] = None,
):
    """`GET /api/templates/active`：`type` 必填；`template=null` = 無生效模板 → 生成側走舊路徑（§3.4）。"""
    _guard()
    _check_identity(teacher_name, teacher_id)
    _check_lineage(lineage_id)
    _check_type(type)
    return {"template": database.get_active_template(teacher_id, type)}


# ---------- 2. 詳情 + 版本鏈 ----------

@router.get("/{template_id}")
def get_template(template_id: int, teacher_name: str, teacher_id: str):
    _guard()
    _check_identity(teacher_name, teacher_id)
    row = _load_owned(template_id, teacher_id)
    return {
        "template": row,
        "chain": database.list_template_chain(template_id),
        # Epic 3 細化：引用該 (template_id, version) 的草案數（`drafts.template_id` 補列在子任務 0002）
        "generated_count": 0,
    }


# ---------- 4. 新建草稿（同 scope 已有草稿 → 複用，冪等）----------

@router.post("", status_code=201)
def create_template(data: TemplateCreateInput, response: Response):
    _guard()
    _check_identity(data.teacher_name, data.teacher_id)
    _check_lineage(data.lineage_id)
    _check_type(data.type)
    schema_obj = database.default_template_schema(data.type) if data.template_schema is None else data.template_schema
    _validated_schema(data.type, schema_obj)
    name = (data.name or "").strip() or database.TEMPLATE_TYPE_LABELS[data.type]
    row, reused = database.create_or_reuse_template(data.teacher_id, data.type, name, schema_obj)
    if reused:
        response.status_code = 200   # 冪等：不產生第二份草稿（§10.2 #4）
    return {"template": row, "reused": reused, "warnings": _warnings_for(row)}


# ---------- 5. 改草稿（已發佈 / 已歸檔 → 409）----------

@router.put("/{template_id}")
def update_template(template_id: int, data: TemplateUpdateInput):
    _guard()
    _check_identity(data.teacher_name, data.teacher_id)
    row = _load_owned(template_id, data.teacher_id)
    provided = data.model_fields_set
    name = None
    if "name" in provided and data.name is not None:
        name = data.name.strip()
        if not name:
            _fail(400, "invalid_name", "模板名不可為空")
    schema_obj = None
    if "template_schema" in provided and data.template_schema is not None:
        schema_obj = _validated_schema(row["type"], data.template_schema)
    updated, _changed = database.update_template_draft(template_id, name, schema_obj)
    return {"template": updated, "warnings": _warnings_for(updated)}


# ---------- 6. 發佈（同事務自動歸檔舊 active，返回 archived_ids；不報 409）----------

@router.post("/{template_id}/publish")
def publish_template(template_id: int, data: TemplateActionInput):
    """§11.1：`draft → active`；同 scope 舊 `active` 同事務歸檔，響應帶 `archived_ids`（批復 2）。"""
    _guard()
    _check_identity(data.teacher_name, data.teacher_id)
    row = _load_owned(template_id, data.teacher_id)
    if row["status"] == "archived":
        _fail(409, "template_published_immutable", "已歸檔的版本請改用「重新啟用」，不可直接發佈")
    # 發佈級校驗（草稿允許半成品，發佈必須完整，§9.0）
    _validated_schema(row["type"], row["schema_json"], for_publish=True)
    updated, archived_ids, changed = database.set_template_active(template_id)
    return {
        "template": updated,
        "archived_ids": archived_ids,
        "changed": changed,
        "event": "template_configured",   # Epic 3 哈希鏈接口預留（§3.5）
        "warnings": _warnings_for(updated),
    }


# ---------- 7. 歸檔 ----------

@router.post("/{template_id}/archive")
def archive_template(template_id: int, data: TemplateActionInput):
    """§11.2：`active` / `draft → archived`；已 `archived` → 200 `changed=false`（冪等）。

    副作用只有 `templates` 行本身：不碰 `drafts` / `patient_records`（歷史零回溯，§4.4）。
    """
    _guard()
    _check_identity(data.teacher_name, data.teacher_id)
    _load_owned(template_id, data.teacher_id)
    updated, changed = database.archive_template(template_id)
    return {"template": updated, "changed": changed}


# ---------- 8. 重新啟用（與 publish 同規則；不校驗 schema）----------

@router.post("/{template_id}/activate")
def activate_template(template_id: int, data: TemplateActionInput):
    """§11.3：`archived → active`，同事務自動歸檔舊 `active`；**不校驗** `schema_json`。"""
    _guard()
    _check_identity(data.teacher_name, data.teacher_id)
    _load_owned(template_id, data.teacher_id)
    updated, archived_ids, changed = database.set_template_active(template_id)
    return {"template": updated, "archived_ids": archived_ids, "changed": changed}


# ---------- 9. 派生（前端「基於此版本修訂」）----------

@router.post("/{template_id}/derive", status_code=201)
def derive_template(template_id: int, data: TemplateDeriveInput, response: Response):
    """§11.4：從 `active` / `archived` 派生新草稿；同鏈已有草稿 → 200 + `reused_draft: true`。"""
    _guard()
    _check_identity(data.teacher_name, data.teacher_id)
    _check_lineage(data.lineage_id)
    # 來源不存在 → 交給服務層回 400 `template_parent_not_found`（§10.2 #9 口徑）；
    # 存在但屬他人 → 403（越權不進服務層）
    existing = database.get_template(template_id)
    if existing is not None and existing["teacher_id"] != data.teacher_id:
        _fail(403, "template_forbidden", "無權操作他人的模板")
    name = (data.name or "").strip() or None
    row, reused = database.derive_template_from(template_id, data.teacher_id, data.parent_template_id, name)
    if reused:
        response.status_code = 200   # 同鏈已有草稿 → 複用（§4.3 第 4 條）
    return {"template": row, "reused_draft": reused}
