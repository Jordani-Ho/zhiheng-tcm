"""Epic 3 §7：學習鏈接口（三個 GET，前綴 `/api/agent/learning`）。

設計對齊：`docs/epic3-learning-design-v1.md` §6（flag）/ §7（API 契約）/ §7.3（錯誤碼）。
本文件**零寫 SQL**：三個端點全為 GET，事件寫入在 `database.py` 的 best-effort 鉤子裡。

門衛順序（§6）：flag → 存儲就緒 → 鑑權 → 業務校驗。
"""

from fastapi import APIRouter, HTTPException

import agent_stage_service

router = APIRouter(prefix="/api/agent/learning", tags=["learning"])

# 錯誤碼 → HTTP 狀態碼（照 agent_stage_api._AGENT_STAGE_ERROR_STATUS 同款形態）
_LEARNING_ERROR_STATUS = {
    "learning_disabled": 404,
    "learning_store_unavailable": 503,
    "teacher_required": 400,
    "teacher_mismatch": 403,
    "window_invalid": 400,
    "limit_invalid": 400,
    "chain_broken": 409,
}

# limit 上限（§7.2）
_LIMIT_DEFAULT = 50
_LIMIT_MAX = 500


def _fail(status_code, code, msg):
    """統一錯誤體（§7.3）：`{"detail": {"error", "msg"}}`。"""
    raise HTTPException(status_code=status_code, detail={"error": code, "msg": msg})


def _guard():
    """門衛前兩道：flag → 存儲就緒。"""
    import learning_service
    if not learning_service.learning_enabled():
        _fail(404, "learning_disabled", "學習鏈接口未啟用（LEARNING_ENABLED=off）")
    if not learning_service.learning_store_ready():
        _fail(503, "learning_store_unavailable", "學習鏈存儲未就緒，請先執行資料庫遷移")


def _check_identity(teacher_name, teacher_id):
    """鑑權：`teacher_name` + `teacher_id` 成對（與全庫鑑權口徑一致）。"""
    if not teacher_name or not teacher_id:
        _fail(400, "teacher_required", "必須帶 teacher_name 與 teacher_id")
    if teacher_name != teacher_id:
        _fail(403, "teacher_mismatch", "teacher_name 與 teacher_id 不一致")


def _check_limit(limit):
    """`limit` 校驗：整數且 1 ≤ limit ≤ 500。"""
    if not isinstance(limit, int) or isinstance(limit, bool) or limit <= 0 or limit > _LIMIT_MAX:
        _fail(400, "limit_invalid", "limit 必須是 1 到 %d 的整數" % _LIMIT_MAX)


@router.get("/events")
def get_learning_events(teacher_name: str = "", teacher_id: str = "", limit: int = _LIMIT_DEFAULT,
                        order: str = "desc"):
    """§7.2：事件流（鏈節列表）。"""
    import learning_service
    _guard()
    _check_identity(teacher_name, teacher_id)
    _check_limit(limit)
    if order not in ("asc", "desc"):
        _fail(400, "limit_invalid", "order 只能是 asc 或 desc")
    rows = learning_service.get_learning_events(teacher_name, limit)
    if order == "desc":
        rows = list(reversed(rows))
    chain = learning_service.verify_learning_chain(teacher_name)
    return {
        "events": rows,
        "total": len(rows),
        "verified": bool(chain.get("ok")),
    }


@router.get("/chain/verify")
def verify_chain(teacher_name: str = "", teacher_id: str = ""):
    """§7.2：鏈校驗（單遍算法，全量）。"""
    import learning_service
    _guard()
    _check_identity(teacher_name, teacher_id)
    result = learning_service.verify_learning_chain(teacher_name)
    if not result.get("ok"):
        # 鏈斷是**數據事實**，不是服務故障 → 409
        raise HTTPException(
            status_code=409,
            detail={
                "error": "chain_broken",
                "msg": "鏈校驗未通過：%s" % result.get("reason", ""),
                "checked": result.get("checked", 0),
                "first_bad_seq": result.get("first_bad_seq"),
            },
        )
    return result


@router.get("/metrics")
def get_learning_metrics(teacher_name: str = "", teacher_id: str = "", window_days: int = 30):
    """§7.2：統計獨立端點（讀快照，不重算）。"""
    _guard()
    _check_identity(teacher_name, teacher_id)
    # 入參只做校驗：非法 → 400；**不**污染「同一份計算」
    if not isinstance(window_days, int) or isinstance(window_days, bool) or window_days <= 0 \
            or window_days > 3650:
        _fail(400, "window_invalid", "window_days 必須是 1 到 3650 的整數")
    return agent_stage_service.learning_metrics_view(teacher_name)
