"""D 板块 M2：治理见证只读路由。

前缀：/api/v1/witness/
方法：仅 GET。不注册任何写路由（D v1.3 §4.3.3）。

数据源（内测）：
- WITNESS_USE_MOCK=1（默认）→ 返回 mock 数据
- WITNESS_USE_MOCK=0       → 返回 501（等 C 板块实现）

Mock 数据字段对齐未来 C 板块 schema，不含患者信息（D v1.3 §4.6）。
"""

import os

from fastapi import APIRouter, Depends, HTTPException

from witness_auth import require_witness


router = APIRouter(prefix="/api/v1/witness", tags=["witness"])

USE_MOCK = os.environ.get("WITNESS_USE_MOCK", "1") == "1"


def _mock_referrals():
    return [
        {
            "id": 1,
            "referrer": "teacher-A",
            "referee": "teacher-B",
            "lineage_id": "lineage-alpha",
            "created_at": "2026-09-01T10:00:00Z",
            "reason": "跟我学过三年",
        },
        {
            "id": 2,
            "referrer": "teacher-B",
            "referee": "teacher-C",
            "lineage_id": "lineage-beta",
            "created_at": "2026-09-15T14:30:00Z",
            "reason": "同门推荐",
        },
    ]


def _mock_seals():
    return [
        {
            "id": 1,
            "lineage_id": "lineage-alpha",
            "reason": "生命周期封存",
            "created_at": "2026-09-20T08:00:00Z",
        },
    ]


def _mock_levels():
    return [
        {
            "id": 1,
            "student_id": "s-001",
            "from_level": "一段",
            "to_level": "二段",
            "created_at": "2026-09-25T12:00:00Z",
        },
    ]


def _mock_kangbi():
    return [
        {
            "id": 1,
            "from": "student-x",
            "to": "teacher-A",
            "amount": 10,
            "created_at": "2026-09-28T16:00:00Z",
        },
    ]


def _wrap(items):
    return {"source": "mock", "items": items, "count": len(items)}


@router.get("/health")
async def health():
    return {"status": "ok"}


@router.get("/me")
async def me(identity: str = Depends(require_witness)):
    return {"identity": identity}


@router.get("/referrals")
async def referrals(identity: str = Depends(require_witness)):
    if USE_MOCK:
        return _wrap(_mock_referrals())
    raise HTTPException(status_code=501, detail="C 板块 referrals 未实现")


@router.get("/seals")
async def seals(identity: str = Depends(require_witness)):
    if USE_MOCK:
        return _wrap(_mock_seals())
    raise HTTPException(status_code=501, detail="C 板块 seals 未实现")


@router.get("/levels")
async def levels(identity: str = Depends(require_witness)):
    if USE_MOCK:
        return _wrap(_mock_levels())
    raise HTTPException(status_code=501, detail="C 板块 levels 未实现")


@router.get("/kangbi")
async def kangbi(identity: str = Depends(require_witness)):
    if USE_MOCK:
        return _wrap(_mock_kangbi())
    raise HTTPException(status_code=501, detail="C 板块 kangbi 未实现")
