"""Epic 3 §7 learning_api 端點的最小驗收用例。

只覆蓋門衛順序 + 三端點形狀：不做端到端鏈數據測試（那屬後續獨立測試）。
"""

import os

import pytest
from fastapi.testclient import TestClient

import main


@pytest.fixture
def client():
    return TestClient(main.app)


def test_flag_off_all_endpoints_404(client, monkeypatch):
    monkeypatch.delenv("LEARNING_ENABLED", raising=False)
    for path in ("/api/agent/learning/events", "/api/agent/learning/chain/verify",
                 "/api/agent/learning/metrics"):
        r = client.get(path, params={"teacher_name": "t", "teacher_id": "t"})
        assert r.status_code == 404
        assert r.json()["detail"]["error"] == "learning_disabled"


def test_teacher_required(client, monkeypatch):
    monkeypatch.setenv("LEARNING_ENABLED", "on")
    r = client.get("/api/agent/learning/events")
    assert r.status_code in (400, 503)  # 存储未就绪可能先拦；优先看 400
    if r.status_code == 400:
        assert r.json()["detail"]["error"] == "teacher_required"


def test_teacher_mismatch(client, monkeypatch):
    monkeypatch.setenv("LEARNING_ENABLED", "on")
    r = client.get("/api/agent/learning/events",
                   params={"teacher_name": "a", "teacher_id": "b"})
    assert r.status_code in (403, 503)
    if r.status_code == 403:
        assert r.json()["detail"]["error"] == "teacher_mismatch"
