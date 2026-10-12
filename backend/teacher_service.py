"""老师入社区（内测场景 1）—— D-051。

【为什么需要这个模块】
`teachers` 表虽然有，但 `INSERT INTO teachers` **只出现在 `database.init_db()` 的种子数据里**
（`database.py:409`）—— 全库**没有任何「创建老师」的函数或端点**。
老师是写死的种子，不是「入社区」进来的。内测场景 1「老师入社区」因此是从零开始。

而 `POST /api/lineages`（`lineage_service.create_lineage`）**只创建师门，不创建 `teachers` 行**。
本模块把这两件事合成一个动作：**建老师行 + 建该老师的默认师门**。

【设计约束（不破坏既有链路）】
· **零修改既有文件**：本模块是纯新增，不改 `database.py` / `lineage_service.py` / `main.py` 之外
  的任何函数体。接线只需在 `main.py` 加两行（import + include_router）。
· **复用而非重写**：师门的创建 / 幂等 / 命名 / 双因子校验**全部调 `lineage_service.create_lineage()`**，
  本模块不复制那份逻辑（项目纪律：同一个判断只许有一份实现，见 TD-001）。
· **幂等**：重复提交同一老师 → 200 + `created=false`，不报错、不建第二行（照 `create_lineage` 先例）。
· **师门旗标**：`lineage_service.create_lineage()` 首个动作是 `lineage_gate()`，故建师门要求
  `LINEAGE_ENABLED=on`。内测期该旗标在核心闭环内，会打开；若未开，本模块**仍建老师行**，
  并把师门步骤的结果如实放进 `warnings`（**不吞、不伪装成功**）。
"""
import sqlite3
from datetime import datetime
from typing import Optional

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

import lineage_service

router = APIRouter(prefix="/api/teachers", tags=["teachers"])


# ---------------------------------------------------------------------------
# 错误码（照 lineage_service / referral_api 的既有形状：code + 人话 msg）
# ---------------------------------------------------------------------------
ERROR_STATUS = {
    "teacher_name_required": 400,
    "teacher_name_taken_by_other": 409,
    "teacher_store_unavailable": 503,
}


class TeacherOnboardInput(BaseModel):
    """老师入社区入参。

    · `name`：老师姓名 —— 全库的业务主键（`teachers.name` PRIMARY KEY）。
    · `teacher_id`：身份因子，须与 `name` **一致**（沿 `lineage_service.require_teacher_identity`
      的既有口径：阶段一没有账号体系，双因子一致性是唯一的身份校验）。
    · `description`：对外简介，可空。
    """

    name: str
    teacher_id: Optional[str] = None
    description: Optional[str] = ""


def _fail(code, msg):
    raise HTTPException(
        status_code=ERROR_STATUS.get(code, 400),
        detail={"error": code, "msg": msg},
    )


def _connection():
    import database  # 函数体内 import（照 lineage_service._store_connection 口径）
    return database.get_connection()


def _now_iso():
    return datetime.now().isoformat(timespec="seconds")


def _table_ready(conn):
    row = conn.execute(
        "SELECT name FROM sqlite_master WHERE type = 'table' AND name = 'teachers'"
    ).fetchone()
    return row is not None


def onboard_teacher(name, teacher_id=None, description=""):
    """老师入社区：建 `teachers` 行 + 建该老师的默认师门。幂等。

    返回：
        {
          "teacher": {"name":..., "description":..., "status":"active", "created_at":...},
          "teacher_created": True/False,
          "lineage": {...} | None,
          "lineage_created": True/False,
          "warnings": [...],
        }
    """
    teacher = (name or "").strip()
    if not teacher:
        _fail("teacher_name_required", "老师姓名（name）不能为空")

    # 双因子一致性：阶段一无账号体系，身份校验 = name 与 teacher_id 一致
    # （沿 lineage_service.require_teacher_identity 的既有口径，不另立一套）
    if teacher_id is not None and str(teacher_id).strip() not in ("", teacher):
        _fail(
            "teacher_name_taken_by_other",
            "身份因子不一致：name=%r 而 teacher_id=%r（阶段一要求两者一致）"
            % (teacher, str(teacher_id).strip()),
        )

    warnings = []
    try:
        conn = _connection()
    except sqlite3.Error:
        _fail("teacher_store_unavailable", "数据库不可用，请确认后端已初始化")

    try:
        if not _table_ready(conn):
            _fail(
                "teacher_store_unavailable",
                "teachers 表不存在：请先跑迁移 / 后端初始化",
            )

        existing = conn.execute(
            "SELECT name, description, status, created_at FROM teachers WHERE name = ?",
            (teacher,),
        ).fetchone()

        if existing is not None:
            teacher_row = dict(existing)
            teacher_created = False
        else:
            now = _now_iso()
            conn.execute(
                "INSERT INTO teachers (name, description, status, last_active_at, created_at) "
                "VALUES (?, ?, 'active', ?, ?)",
                (teacher, description or "", now, now),
            )
            conn.commit()
            teacher_row = {
                "name": teacher,
                "description": description or "",
                "status": "active",
                "created_at": now,
            }
            teacher_created = True
    except sqlite3.Error:
        conn.rollback()
        _fail("teacher_store_unavailable", "老师行写入失败，请稍后重试")
    finally:
        conn.close()

    # ---- 步骤 2：建该老师的默认师门（复用既有实现，不复制逻辑） ----
    lineage = None
    lineage_created = False
    try:
        result = lineage_service.create_lineage(teacher, teacher, None)
        lineage = result.get("lineage")
        lineage_created = bool(result.get("created"))
        warnings.extend(result.get("warnings") or [])
    except lineage_service.LineageError as exc:
        # 师门旗标 off / 存储未就绪 —— 老师行已建成，如实上报，不伪装成功
        warnings.append(
            "老师行已创建，但**师门未创建**（%s：%s）。原因通常是 LINEAGE_ENABLED 未开启"
            "或迁移 0005 未跑；开启后重跑本接口即可补齐（幂等）。"
            % (getattr(exc, "code", "lineage_error"), str(exc))
        )
    except Exception as exc:  # noqa: BLE001 —— 师门失败不得回滚老师行，如实上报
        warnings.append("师门创建失败（%s: %s）；老师行已创建，可重跑本接口补齐。" % (type(exc).__name__, exc))

    return {
        "teacher": teacher_row,
        "teacher_created": teacher_created,
        "lineage": lineage,
        "lineage_created": lineage_created,
        "warnings": warnings,
    }


@router.post("/onboard")
def api_onboard_teacher(data: TeacherOnboardInput):
    """老师入社区（内测场景 1）。幂等：重复提交 → 200 + `teacher_created=false`。"""
    return onboard_teacher(data.name, data.teacher_id, data.description)
