"""B 板塊 B4-b「數據封存 API」端點最小驗收用例集。

對齊：`seal_api.py`（`GET /api/seal/events` + `POST /api/seal/trigger`）——
門衛 → 入參校驗 → 統一錯誤體 → 寫入 / 讀取形狀。
本文件只驗**接口層**，不碰任何業務服務層（與 test_export_api.py / test_crypto_api.py 同款定位）。

覆蓋用例（12 條）：
  · test_seal_disabled_returns_404        —— flag off（默認）：兩個端點一律 404 `seal_disabled`
  · test_get_events_requires_subject      —— 缺 subject_type / subject_name → 400 `subject_required`
  · test_get_events_invalid_subject_type  —— subject_type 非 patient/teacher → 400 `action_invalid`
  · test_get_events_empty                 —— 無事件 → `events: []` / `total: 0`（不是 404）
  · test_trigger_requires_subject         —— 缺 subject_type / subject_name → 400 `subject_required`
  · test_trigger_invalid_subject_type     —— subject_type 非 patient/teacher → 400 `action_invalid`
  · test_trigger_invalid_action           —— action 非 seal/readmit → 400 `action_invalid`
  · test_trigger_seal_success             —— 寫入 seal → 返回正整數 event_id，可讀回
  · test_trigger_readmit_success          —— 寫入 readmit → 返回正整數 event_id，可讀回
  · test_trigger_then_get_events          —— 先 trigger 再查 → 兩條都在（seal → readmit）
  · test_events_filter_by_subject         —— 不同 subject_type / subject_name 互不串味
  · test_events_ordered_id_desc           —— 同一主體多條記錄按 id 倒序

運行方式（Windows，串行；見 pytest.ini）：
    cd backend
    ../venv/Scripts/python.exe -m pytest test_seal_api.py -v

紀律：
  · `client` 一律用 conftest.py 的 fixture（本文件**不**自帶 client、不直連 `database`）；
  · flag 默認 off，故本文件用 autouse fixture 統一打開（與 test_export_api.py 同款）；
    驗「關閉態」的用例在同一 `monkeypatch` 上 `delenv` / `setenv("off")` 即可覆蓋；
  · 讀寫全部經**真實端點**（黑盒），期望值只走接口契約（狀態碼 / 錯誤碼 / 字段形狀）。
"""

import pytest

# 封存端點（§3.5.6）
EVENTS_PATH = "/api/seal/events"
TRIGGER_PATH = "/api/seal/trigger"

# 測試主體（真實端點不查存在性，故可用任意具名主體）
PATIENT = "封存測試患者"
TEACHER = "封存測試老師"


@pytest.fixture(autouse=True)
def seal_enabled(monkeypatch):
    """統一打開 flag（`SEAL_ENABLED` 默認 off）。

    需要驗「關閉態」的用例在同一 `monkeypatch` 上 `delenv` / `setenv("off")` 即可覆蓋。
    """
    monkeypatch.setenv("SEAL_ENABLED", "on")


def _trigger(client, subject_type="patient", subject_name=PATIENT, action="seal",
             reason="", operator=""):
    """走真實端點（黑盒）觸發一條封存事件。"""
    return client.post(TRIGGER_PATH, json={
        "subject_type": subject_type,
        "subject_name": subject_name,
        "action": action,
        "reason": reason,
        "operator": operator,
    })


def _events(client, subject_type="patient", subject_name=PATIENT):
    """走真實端點（黑盒）查某主體的封存事件。"""
    return client.get(EVENTS_PATH, params={
        "subject_type": subject_type,
        "subject_name": subject_name,
    })


# ---------------------------------------------------------------------------
# 門衛：flag off → 兩個端點全部 404
# ---------------------------------------------------------------------------
def test_seal_disabled_returns_404(client, monkeypatch):
    """`SEAL_ENABLED` 未設 / `off`：兩個端點一律 404 `seal_disabled`，錯誤體形狀統一。"""
    for flag in (None, "off", "OFF", "0"):
        if flag is None:
            monkeypatch.delenv("SEAL_ENABLED", raising=False)
        else:
            monkeypatch.setenv("SEAL_ENABLED", flag)

        r = _events(client)
        assert r.status_code == 404, flag
        assert r.json()["detail"]["error"] == "seal_disabled"
        assert r.json()["detail"]["msg"] == "seal api disabled"

        r = _trigger(client, action="seal")
        assert r.status_code == 404, flag
        assert r.json()["detail"]["error"] == "seal_disabled"


# ---------------------------------------------------------------------------
# 查詢端點校驗
# ---------------------------------------------------------------------------
def test_get_events_requires_subject(client):
    """缺 `subject_type` / `subject_name`（任一）→ 400 `subject_required`。"""
    cases = (
        {"subject_type": "", "subject_name": ""},
        {"subject_type": "patient", "subject_name": ""},
        {"subject_type": "", "subject_name": PATIENT},
    )
    for params in cases:
        r = client.get(EVENTS_PATH, params=params)
        assert r.status_code == 400, params
        assert r.json()["detail"]["error"] == "subject_required"


def test_get_events_invalid_subject_type(client):
    """`subject_type` 非 patient / teacher → 400（本步沿用 `action_invalid` 碼，供階段四細分）。"""
    for subject_type in ("agent", "student", "PATIENT", " Patient"):
        r = client.get(EVENTS_PATH,
                       params={"subject_type": subject_type, "subject_name": PATIENT})
        assert r.status_code == 400, subject_type
        assert r.json()["detail"]["error"] == "action_invalid"


def test_get_events_empty(client):
    """全新主體、零事件 → 200 且 `events: []` / `total: 0`（空集不是錯誤，不與 404 混淆）。"""
    r = _events(client, subject_name="從未封存過的主體")
    assert r.status_code == 200
    body = r.json()
    assert body["events"] == []
    assert body["total"] == 0


# ---------------------------------------------------------------------------
# 觸發端點校驗
# ---------------------------------------------------------------------------
def test_trigger_requires_subject(client):
    """缺 `subject_type` / `subject_name`（任一）→ 400 `subject_required`。"""
    cases = (
        {"subject_type": "", "subject_name": "", "action": "seal"},
        {"subject_type": "patient", "subject_name": "", "action": "seal"},
        {"subject_type": "", "subject_name": PATIENT, "action": "seal"},
    )
    for payload in cases:
        r = client.post(TRIGGER_PATH, json=payload)
        assert r.status_code == 400, payload
        assert r.json()["detail"]["error"] == "subject_required"


def test_trigger_invalid_subject_type(client):
    """`subject_type` 非 patient / teacher → 400 `action_invalid`（校驗在 action 之前）。"""
    for subject_type in ("agent", "student", "PATIENT"):
        r = _trigger(client, subject_type=subject_type, action="seal")
        assert r.status_code == 400, subject_type
        assert r.json()["detail"]["error"] == "action_invalid"


def test_trigger_invalid_action(client):
    """`action` 非 seal / readmit（含 §3.5.5 明令不收的 `remove`）→ 400 `action_invalid`。"""
    for action in ("", "remove", "SEAL", "archive"):
        r = _trigger(client, action=action)
        assert r.status_code == 400, action
        assert r.json()["detail"]["error"] == "action_invalid"


# ---------------------------------------------------------------------------
# 成功路徑：寫入 + 讀回（只增，永不 update / delete）
# ---------------------------------------------------------------------------
def test_trigger_seal_success(client):
    """`action=seal` → 200 且返回正整數 `event_id`，字段經查詢端點原樣讀回。"""
    r = _trigger(client, action="seal", reason="生命週期封存", operator="李老师")
    assert r.status_code == 200
    event_id = r.json()["event_id"]
    assert isinstance(event_id, int) and event_id > 0

    body = _events(client).json()
    assert body["total"] == 1
    event = body["events"][0]
    assert event["id"] == event_id
    assert event["subject_type"] == "patient"
    assert event["subject_name"] == PATIENT
    assert event["action"] == "seal"
    assert event["reason"] == "生命週期封存"
    assert event["operator"] == "李老师"
    assert event["created_at"]  # 自動補的 TEXT 時間戳非空
    # 階段二不填鏈上兩列（§3.5.7：填充歸階段四）
    assert not event["chain_ready"]
    assert event["chain_hash"] is None


def test_trigger_readmit_success(client):
    """`action=readmit` → 200 且返回正整數 `event_id`（重新接納同樣只增一條）。"""
    r = _trigger(client, action="readmit", reason="願意重新接納", operator="王老师")
    assert r.status_code == 200
    event_id = r.json()["event_id"]
    assert isinstance(event_id, int) and event_id > 0

    body = _events(client).json()
    assert body["total"] == 1
    assert body["events"][0]["id"] == event_id
    assert body["events"][0]["action"] == "readmit"


def test_trigger_then_get_events(client):
    """先 trigger 再查詢：完整生命週期可回溯（seal → readmit 兩條都在，較新在前）。"""
    first = _trigger(client, action="seal", reason="第一次封存").json()["event_id"]
    second = _trigger(client, action="readmit", reason="重新接納").json()["event_id"]
    assert second > first

    body = _events(client).json()
    assert body["total"] == 2
    assert [e["id"] for e in body["events"]] == [second, first]
    assert {e["action"] for e in body["events"]} == {"seal", "readmit"}


def test_events_filter_by_subject(client):
    """不同主體（類型或名字）互不串味：只回本主體的事件。"""
    _trigger(client, subject_type="patient", subject_name="甲患者", action="seal")
    _trigger(client, subject_type="patient", subject_name="乙患者", action="seal")
    _trigger(client, subject_type="teacher", subject_name="甲患者", action="seal")

    body = _events(client, subject_type="patient", subject_name="甲患者").json()
    assert body["total"] == 1
    assert body["events"][0]["subject_type"] == "patient"
    assert body["events"][0]["subject_name"] == "甲患者"

    body = _events(client, subject_type="teacher", subject_name="甲患者").json()
    assert body["total"] == 1
    assert body["events"][0]["subject_type"] == "teacher"

    body = _events(client, subject_type="patient", subject_name="丙患者").json()
    assert body == {"events": [], "total": 0}


def test_events_ordered_id_desc(client):
    """同一主體多條記錄 → `id` 倒序（最近事件在前，供前端直接渲染歷史）。"""
    ids = [
        _trigger(client, action="seal", reason="第 %d 次封存" % i).json()["event_id"]
        for i in range(1, 4)
    ]
    body = _events(client).json()
    assert body["total"] == 3
    assert [e["id"] for e in body["events"]] == list(reversed(ids))
    assert [e["id"] for e in body["events"]] == sorted(ids, reverse=True)
