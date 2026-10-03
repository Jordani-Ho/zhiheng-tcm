"""D 板块 M2：witness_router 单元测试。"""

import sqlite3

import pytest
from fastapi.testclient import TestClient

from main import app
from witness_db import get_ro_connection


client = TestClient(app)

VALID_TOKEN = "witness-dev-initiator"
INVALID_TOKEN = "bogus-token"


def _auth_headers(token=VALID_TOKEN):
    return {"X-Witness-Token": token}


def test_T1_health_no_auth():
    r = client.get("/api/v1/witness/health")
    assert r.status_code == 200
    assert r.json() == {"status": "ok"}


def test_T2_me_no_token():
    r = client.get("/api/v1/witness/me")
    assert r.status_code == 401


def test_T3_me_bad_token():
    r = client.get("/api/v1/witness/me", headers=_auth_headers(INVALID_TOKEN))
    assert r.status_code == 401


def test_T4_me_ok():
    r = client.get("/api/v1/witness/me", headers=_auth_headers())
    assert r.status_code == 200
    assert r.json()["identity"] == "initiator"


def test_T5_referrals_no_token():
    r = client.get("/api/v1/witness/referrals")
    assert r.status_code == 401


def test_T6_referrals_ok():
    r = client.get("/api/v1/witness/referrals", headers=_auth_headers())
    assert r.status_code == 200
    body = r.json()
    assert body["source"] == "mock"
    assert body["count"] == len(body["items"])
    assert body["count"] > 0


def test_T7_seals_levels_kangbi_ok():
    for path in ("/seals", "/levels", "/kangbi"):
        r = client.get(f"/api/v1/witness{path}", headers=_auth_headers())
        assert r.status_code == 200, f"{path} failed"
        assert r.json()["source"] == "mock"


def test_T8_no_post_route():
    # 路径存在（GET 已注册）但 POST 方法未注册 → FastAPI 返回 405
    # 405（Method Not Allowed）证明写方法未注册，等价于"攻击面为零"（D v1.3 §4.3.3）
    r = client.post("/api/v1/witness/referrals", headers=_auth_headers())
    assert r.status_code == 405


def test_T9_no_put_patch_delete_routes():
    # 同 T8：路径存在但方法未注册 → 405（非 404）
    for method in ("put", "patch", "delete"):
        r = getattr(client, method)(
            "/api/v1/witness/referrals", headers=_auth_headers()
        )
        assert r.status_code == 405, f"{method} unexpectedly allowed"


def test_T10_openapi_only_get():
    r = client.get("/openapi.json")
    assert r.status_code == 200
    paths = r.json()["paths"]
    witness_paths = {
        k: v for k, v in paths.items() if k.startswith("/api/v1/witness/")
    }
    assert len(witness_paths) > 0
    for path, methods in witness_paths.items():
        for method in methods:
            assert method == "get", f"{path} has non-GET method: {method}"


def test_T11_ro_connection_cannot_write():
    conn = get_ro_connection()
    try:
        with pytest.raises(sqlite3.OperationalError):
            conn.execute("CREATE TABLE _witness_probe (x INT)")
    finally:
        conn.close()


def test_T12_mock_no_patient_data():
    r = client.get("/api/v1/witness/referrals", headers=_auth_headers())
    body = r.json()
    forbidden_keys = {"patient_name", "symptoms", "tongue", "prescription"}
    for item in body["items"]:
        leaked = set(item.keys()) & forbidden_keys
        assert not leaked, f"leaked patient fields: {leaked}"
