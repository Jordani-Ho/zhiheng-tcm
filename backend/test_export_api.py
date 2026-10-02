"""B 板塊 B5-1「學生數據導出 API」端點最小驗收用例集。

對齊：`export_api.py`（`GET /api/export/patient`）——門衛 → 身份校驗 → 統一錯誤體 → bundle 形狀。
本文件只驗**接口層**，不碰任何業務服務層（與 test_crypto_api.py 同款定位）。

覆蓋用例（8 條）：
  · test_export_disabled_returns_404          —— flag off（默認）：404 `export_disabled`
  · test_export_patient_requires_identity      —— 缺 patient_name / patient_id → 400 `patient_required`
  · test_export_patient_mismatch               —— patient_name != patient_id → 403 `patient_mismatch`
  · test_export_patient_not_found              —— 患者不存在 → 404 `patient_not_found`
  · test_export_patient_success                —— 成功：bundle 鍵集合 = 契約
  · test_export_patient_empty_data             —— 全新患者：各表空列表
  · test_export_patient_includes_records       —— 預置數據後能導出（含 record_tags 的 JOIN 關聯）
  · test_export_patient_version_and_timestamp  —— version / exported_at（ISO + `Z`）形狀

運行方式（Windows，串行；見 pytest.ini）：
    cd backend
    ../venv/Scripts/python.exe -m pytest test_export_api.py -v

紀律：
  · `client` 一律用 conftest.py 的 fixture（本文件**不**自帶 client、不 import fastapi）；
  · flag 默認 off，故本文件用 autouse fixture 統一打開（與 test_crypto_api.py 同款）；
    驗「關閉態」的用例在同一 `monkeypatch` 上 `delenv` / `setenv("off")` 即可覆蓋；
  · 預置數據只走 `database.py` 已有的連接（與 test_lineage.py `_seed` 同款），
    不經服務層，避免把「導出」的驗收耦合到別的業務寫入路徑。
"""

from datetime import datetime

import pytest

import database

# 導出端點
EXPORT_PATH = "/api/export/patient"

# init_db() 種下的既有學生 / 老師（見 database.init_db 的默認數據段）
PATIENT = "张三"
TEACHER = "李老师"

# bundle 契約鍵集合。
# 註：任務描述寫「13 個鍵」，但 `export_api.export_patient` 的返回體實為 **14 個鍵**
# （version / exported_at / patient_name / patient / profile / teachers / transcriptions /
#   drafts / records / prescriptions / homework / appointments / record_tags / complaints）；
# 本用例以**代碼契約**為準，斷言「鍵集合完全相等」（多一個少一個都紅）。
EXPECTED_KEYS = {
    "version", "exported_at", "patient_name", "patient", "profile", "teachers",
    "transcriptions", "drafts", "records", "prescriptions", "homework",
    "appointments", "record_tags", "complaints",
}

# 空患者時應為 `[]` 的列表鍵（`teachers` 亦屬之：全新患者無師生關係）
EMPTY_LIST_KEYS = (
    "teachers", "transcriptions", "drafts", "records", "prescriptions",
    "homework", "appointments", "record_tags", "complaints",
)


@pytest.fixture(autouse=True)
def export_enabled(monkeypatch):
    """統一打開 flag（`EXPORT_ENABLED` 默認 off）。

    需要驗「關閉態」的用例在同一 `monkeypatch` 上 `setenv("off")` / `delenv` 即可覆蓋。
    """
    monkeypatch.setenv("EXPORT_ENABLED", "on")


def _export(client, patient_name=PATIENT, patient_id=None):
    """走真實端點（黑盒）：不帶 `patient_id` 時默認與 `patient_name` 相同（合法身份）。"""
    if patient_id is None:
        patient_id = patient_name
    return client.get(EXPORT_PATH, params={"patient_name": patient_name, "patient_id": patient_id})


# ---------------------------------------------------------------------------
# 門衛：flag off → 404
# ---------------------------------------------------------------------------
def test_export_disabled_returns_404(client, monkeypatch):
    """`EXPORT_ENABLED` 未設 / `off`：404 `export_disabled`，錯誤體形狀統一。"""
    for flag in (None, "off", "OFF", "0"):
        if flag is None:
            monkeypatch.delenv("EXPORT_ENABLED", raising=False)
        else:
            monkeypatch.setenv("EXPORT_ENABLED", flag)
        r = _export(client)
        assert r.status_code == 404, flag
        detail = r.json()["detail"]
        assert detail["error"] == "export_disabled"
        assert detail["msg"]


# ---------------------------------------------------------------------------
# 身份校驗
# ---------------------------------------------------------------------------
def test_export_patient_requires_identity(client):
    """缺 `patient_name` 或 `patient_id` → 400 `patient_required`（身份必須成對）。"""
    cases = (
        {"patient_name": "", "patient_id": ""},
        {"patient_name": PATIENT, "patient_id": ""},
        {"patient_name": "", "patient_id": PATIENT},
    )
    for params in cases:
        r = client.get(EXPORT_PATH, params=params)
        assert r.status_code == 400, params
        assert r.json()["detail"]["error"] == "patient_required"


def test_export_patient_mismatch(client):
    """`patient_name` 與 `patient_id` 不等 → 403 `patient_mismatch`。"""
    r = _export(client, PATIENT, "李四")
    assert r.status_code == 403
    assert r.json()["detail"]["error"] == "patient_mismatch"


# ---------------------------------------------------------------------------
# 患者不存在
# ---------------------------------------------------------------------------
def test_export_patient_not_found(client):
    """身份合法但患者不在庫 → 404 `patient_not_found`。"""
    r = _export(client, "不存在的患者")
    assert r.status_code == 404
    assert r.json()["detail"]["error"] == "patient_not_found"


# ---------------------------------------------------------------------------
# 成功路徑：bundle 形狀
# ---------------------------------------------------------------------------
def test_export_patient_success(client):
    """既有學生（张三）→ 200，bundle 鍵集合 = 契約，且 `patient` 來自 `patients` 表。"""
    r = _export(client)
    assert r.status_code == 200
    payload = r.json()

    assert set(payload.keys()) == EXPECTED_KEYS
    assert payload["version"] == "1"
    assert payload["patient_name"] == PATIENT
    assert payload["patient"]["name"] == PATIENT
    # 型別契約：列表鍵一律 list，`patient` / `profile` 一律 dict
    for key in EMPTY_LIST_KEYS:
        assert isinstance(payload[key], list), key
    assert isinstance(payload["patient"], dict)
    assert isinstance(payload["profile"], dict)


def test_export_patient_empty_data(client):
    """全新患者（無師生關係、無任何業務數據）：各列表鍵全為 `[]`。"""
    database.add_patient("導出空患者", "self", "本人", "", "", "", "", "")

    r = _export(client, "導出空患者")
    assert r.status_code == 200
    payload = r.json()
    for key in EMPTY_LIST_KEYS:
        assert payload[key] == [], key
    assert payload["patient"]["name"] == "導出空患者"


def test_export_patient_includes_records(client):
    """預置數據後（病歷 + 標籤 + 轉述）能被原樣導出。

    其中標籤經 `record_tags.record_id → patient_records.id` 關聯取得，
    同時守護 `get_record_tags_by_patient` 的 JOIN 寫法不回退成「按 patient_name 直查」。
    """
    conn = database.get_connection()
    cur = conn.cursor()
    cur.execute(
        "INSERT INTO patient_records (patient_name, teacher_name, ai_draft, final_plan, doctor, visit_at) "
        "VALUES (?, ?, ?, ?, ?, ?)",
        (PATIENT, TEACHER, "AI 原稿", "導出終稿", TEACHER, "2026-09-23T15:30:00"),
    )
    record_id = cur.lastrowid
    cur.execute(
        "INSERT INTO record_tags (record_id, teacher_name, tag_type, tag_value, created_at) "
        "VALUES (?, ?, ?, ?, ?)",
        (record_id, TEACHER, "證型", "氣虛", "2026-09-23"),
    )
    cur.execute(
        "INSERT INTO transcriptions (patient_name, teacher_name, content, data_type, processed) "
        "VALUES (?, ?, ?, ?, 0)",
        (PATIENT, TEACHER, "導出轉述內容", "text"),
    )
    conn.commit()
    conn.close()

    r = _export(client)
    assert r.status_code == 200
    payload = r.json()

    assert any(row["final_plan"] == "導出終稿" for row in payload["records"])
    assert any(row["tag_value"] == "氣虛" for row in payload["record_tags"])
    assert any(row["content"] == "導出轉述內容" for row in payload["transcriptions"])


# ---------------------------------------------------------------------------
# version / exported_at
# ---------------------------------------------------------------------------
def test_export_patient_version_and_timestamp(client):
    """`version` 固定 "1"；`exported_at` 是可解析的 ISO 時間戳並以 `Z`（UTC）結尾。"""
    r = _export(client)
    assert r.status_code == 200
    payload = r.json()

    assert payload["version"] == "1"

    exported_at = payload["exported_at"]
    assert isinstance(exported_at, str)
    assert exported_at.endswith("Z")
    # 去掉 Z 後可被標準庫解析（證明不是隨手拼的假串）
    datetime.fromisoformat(exported_at[:-1])
