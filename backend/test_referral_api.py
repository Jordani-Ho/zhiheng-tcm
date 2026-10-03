"""C 板塊「引薦鏈」API 的守護測試。

對齊：docs/phase3-governance-design.md §9.1
紀律：全部用例都在 tmp_path 下自建獨立 SQLite 文件，绝不碰 backend/zhiheng.db。
"""
import importlib
import os
import sys

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

BACKEND_DIR = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, BACKEND_DIR)

import migrations_runner


def _setup_client(tmp_path, monkeypatch, enabled=True):
    """构造一个最小 FastAPI app，挂 referral_router + 隔离 DB。"""
    db = tmp_path / "test_referral.db"
    assert migrations_runner.run_upgrade("head", db_file=str(db)) is True

    import database
    monkeypatch.setattr(database, "DB_PATH", str(db))

    import referral_service
    import referral_api
    importlib.reload(referral_service)
    importlib.reload(referral_api)

    if enabled:
        monkeypatch.setenv("REFERRAL_ENABLED", "on")
    else:
        monkeypatch.delenv("REFERRAL_ENABLED", raising=False)

    app = FastAPI()
    app.include_router(referral_api.router)
    return TestClient(app)


# ---------------------------------------------------------------------------
# flag 门
# ---------------------------------------------------------------------------
def test_referral_disabled_returns_404(tmp_path, monkeypatch):
    """flag off → 所有端点 404 referral_disabled。"""
    client = _setup_client(tmp_path, monkeypatch, enabled=False)
    resp = client.post("/api/referral/teacher", json={
        "referrer_id": "T-001", "referee_id": "T-002", "referral_reason": "x"})
    assert resp.status_code == 404
    assert resp.json()["detail"]["error"] == "referral_disabled"


def test_referral_disabled_get_chain_404(tmp_path, monkeypatch):
    client = _setup_client(tmp_path, monkeypatch, enabled=False)
    resp = client.get("/api/referral/chain/T-001")
    assert resp.status_code == 404


# ---------------------------------------------------------------------------
# 老师引荐老师
# ---------------------------------------------------------------------------
def test_teacher_referral_success(tmp_path, monkeypatch):
    client = _setup_client(tmp_path, monkeypatch, enabled=True)
    resp = client.post("/api/referral/teacher", json={
        "referrer_id": "T-001",
        "referee_id": "T-002",
        "referral_reason": "此人跟我学过三年",
    })
    assert resp.status_code == 200
    assert resp.json()["referral_id"].startswith("ref-")


def test_teacher_referral_self_fails(tmp_path, monkeypatch):
    client = _setup_client(tmp_path, monkeypatch, enabled=True)
    resp = client.post("/api/referral/teacher", json={
        "referrer_id": "T-001", "referee_id": "T-001", "referral_reason": "x"})
    assert resp.status_code == 400
    assert resp.json()["detail"]["error"] == "self_referral"


def test_teacher_referral_missing_reason_fails(tmp_path, monkeypatch):
    client = _setup_client(tmp_path, monkeypatch, enabled=True)
    resp = client.post("/api/referral/teacher", json={
        "referrer_id": "T-001", "referee_id": "T-002", "referral_reason": ""})
    assert resp.status_code == 400
    assert resp.json()["detail"]["error"] == "reason_required"


# ---------------------------------------------------------------------------
# 学生引荐亲友
# ---------------------------------------------------------------------------
def test_student_referral_success(tmp_path, monkeypatch):
    client = _setup_client(tmp_path, monkeypatch, enabled=True)
    resp = client.post("/api/referral/student", json={
        "referrer_id": "S-001", "referee_id": "S-002", "referee_type": "STUDENT"})
    assert resp.status_code == 200
    assert resp.json()["referral_id"].startswith("ref-")


def test_student_referral_dependent_ok(tmp_path, monkeypatch):
    client = _setup_client(tmp_path, monkeypatch, enabled=True)
    resp = client.post("/api/referral/student", json={
        "referrer_id": "S-001", "referee_id": "C-001", "referee_type": "DEPENDENT"})
    assert resp.status_code == 200


def test_student_referral_invalid_type_fails(tmp_path, monkeypatch):
    client = _setup_client(tmp_path, monkeypatch, enabled=True)
    resp = client.post("/api/referral/student", json={
        "referrer_id": "S-001", "referee_id": "X-001", "referee_type": "TEACHER"})
    assert resp.status_code == 400
    assert resp.json()["detail"]["error"] == "referee_type_invalid"


def test_student_referral_quota_exceeded(tmp_path, monkeypatch):
    """一年内第 4 次引荐 → 额度超限。"""
    client = _setup_client(tmp_path, monkeypatch, enabled=True)
    for i in range(3):
        resp = client.post("/api/referral/student", json={
            "referrer_id": "S-001", "referee_id": "S-%03d" % (i + 2),
            "referee_type": "STUDENT"})
        assert resp.status_code == 200
    resp = client.post("/api/referral/student", json={
        "referrer_id": "S-001", "referee_id": "S-099", "referee_type": "STUDENT"})
    assert resp.status_code == 400
    assert resp.json()["detail"]["error"] == "quota_exceeded"


# ---------------------------------------------------------------------------
# 查询
# ---------------------------------------------------------------------------
def test_get_referral_success(tmp_path, monkeypatch):
    client = _setup_client(tmp_path, monkeypatch, enabled=True)
    created = client.post("/api/referral/teacher", json={
        "referrer_id": "T-001", "referee_id": "T-002",
        "referral_reason": "x"}).json()["referral_id"]
    resp = client.get("/api/referral/" + created)
    assert resp.status_code == 200
    assert resp.json()["referral_id"] == created


def test_get_referral_not_found(tmp_path, monkeypatch):
    client = _setup_client(tmp_path, monkeypatch, enabled=True)
    resp = client.get("/api/referral/ref-nonexistent")
    assert resp.status_code == 404
    assert resp.json()["detail"]["error"] == "referral_not_found"


def test_get_chain_both_directions(tmp_path, monkeypatch):
    client = _setup_client(tmp_path, monkeypatch, enabled=True)
    client.post("/api/referral/teacher", json={
        "referrer_id": "T-001", "referee_id": "T-002", "referral_reason": "x"})
    client.post("/api/referral/teacher", json={
        "referrer_id": "T-002", "referee_id": "T-003", "referral_reason": "y"})
    resp = client.get("/api/referral/chain/T-002")
    assert resp.status_code == 200
    data = resp.json()
    assert len(data["as_referrer"]) == 1
    assert len(data["as_referee"]) == 1


# ---------------------------------------------------------------------------
# 撤回
# ---------------------------------------------------------------------------
def test_revoke_success(tmp_path, monkeypatch):
    client = _setup_client(tmp_path, monkeypatch, enabled=True)
    created = client.post("/api/referral/teacher", json={
        "referrer_id": "T-001", "referee_id": "T-002",
        "referral_reason": "x"}).json()["referral_id"]
    resp = client.post("/api/referral/" + created + "/revoke",
                       json={"revoke_reason": "换师门了"})
    assert resp.status_code == 200
    assert resp.json()["revoked"] is True


def test_revoke_twice_fails(tmp_path, monkeypatch):
    client = _setup_client(tmp_path, monkeypatch, enabled=True)
    created = client.post("/api/referral/teacher", json={
        "referrer_id": "T-001", "referee_id": "T-002",
        "referral_reason": "x"}).json()["referral_id"]
    client.post("/api/referral/" + created + "/revoke", json={})
    resp = client.post("/api/referral/" + created + "/revoke", json={})
    assert resp.status_code == 400
    assert resp.json()["detail"]["error"] == "already_revoked"