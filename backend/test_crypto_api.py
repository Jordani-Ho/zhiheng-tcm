"""B 板塊 B1b-1「加解密 API」端點最小驗收用例集。

對齊：docs/phase2-data-sovereignty-design.md §5.2（密鑰派生鏈）/ §5.3（加密 blob 結構）。
純函數層的驗收在 `test_crypto_service.py`（B1a）；本文件只驗**接口層**：
門衛 → 入參校驗 → 統一錯誤體 → 四端點形狀。

覆蓋用例：
  · test_crypto_disabled_returns_404             —— flag off（默認）：四個端點一律 404 `crypto_disabled`
  · test_generate_mnemonic_12_words              —— 128 位（含省略 strength 的默認分支）→ 12 詞
  · test_generate_mnemonic_24_words              —— 256 位 → 24 詞
  · test_generate_mnemonic_invalid_strength      —— 非法強度 → 400 `invalid_strength`
  · test_validate_mnemonic_valid / _invalid      —— 校驗正反兩面（非法**不報錯**，只回 `valid: false`）
  · test_encrypt_decrypt_roundtrip               —— 加解密往返（含中文 UTF-8）+ blob 四鍵契約
  · test_encrypt_empty_plaintext                 —— 空明文可加密、可解回空串
  · test_decrypt_wrong_mnemonic                  —— 換助記詞 → 400 `decrypt_failed`
  · test_decrypt_tampered_blob                   —— 篡改密文 → 400 `decrypt_failed`
  · test_decrypt_invalid_blob                    —— blob 非對象 / 缺字段 → 400 `invalid_blob`
  · test_encrypt_invalid_mnemonic                —— 非法助記詞 → 400 `invalid_mnemonic`
  · test_encrypt_invalid_purpose                 —— 空 purpose → 400 `invalid_purpose`
  · test_purpose_isolation                       —— 不同 purpose 派生不同子密鑰，密文互不相認

運行方式（Windows，串行；見 pytest.ini）：
    cd backend
    ../venv/Scripts/python.exe -m pytest test_crypto_api.py -v

紀律：
  · `client` 一律用 conftest.py 的 fixture（本文件**不**自帶 client、不 import `crypto_service`）；
  · flag 默認 off，故本文件用 autouse fixture 統一打開（與 conftest.py 對 TEMPLATE_API_ENABLED /
    AGENT_STAGE_ENABLED 的做法同款）；驗「關閉態」的用例自行 `monkeypatch.delenv`；
  · 期望值只走**接口契約**（狀態碼 / 錯誤碼 / 詞數 / 往返一致），不由實現自證。
"""

import pytest

# BIP-39 官方向量：128 位熵的標準 12 詞助記詞（文檔中立的固定輸入，可直接當測試夾具）
VALID_12_WORDS = ("abandon abandon abandon abandon abandon abandon "
                  "abandon abandon abandon abandon abandon about")

# 用途標籤（§5.2 的 `field:name` 系列）
PURPOSE = "field:name"

# 四個端點 + 各自最小合法請求體：關閉態用例先保證請求體合法，才驗得準是**門衛**在攔
ENDPOINTS = (
    ("/api/crypto/generate-mnemonic", {"strength": 128}),
    ("/api/crypto/validate-mnemonic", {"mnemonic": VALID_12_WORDS}),
    ("/api/crypto/encrypt", {"mnemonic": VALID_12_WORDS, "purpose": PURPOSE, "plaintext": "x"}),
    ("/api/crypto/decrypt", {"mnemonic": VALID_12_WORDS, "purpose": PURPOSE, "blob": {}}),
)


@pytest.fixture(autouse=True)
def crypto_enabled(monkeypatch):
    """統一打開 flag（`CRYPTO_ENABLED` 默認 off）。

    需要驗「關閉態」的用例在同一 `monkeypatch` 上 `delenv` 即可覆蓋（同一個 function 作用域實例）。
    """
    monkeypatch.setenv("CRYPTO_ENABLED", "on")


def _encrypt(client, mnemonic, purpose, plaintext):
    """走真實端點拿 blob（黑盒：不 import `crypto_service`，不碰密碼學內部）。"""
    r = client.post("/api/crypto/encrypt",
                    json={"mnemonic": mnemonic, "purpose": purpose, "plaintext": plaintext})
    assert r.status_code == 200
    return r.json()["blob"]


# ---------------------------------------------------------------------------
# 門衛：flag off → 四個端點全部 404
# ---------------------------------------------------------------------------
def test_crypto_disabled_returns_404(client, monkeypatch):
    """`CRYPTO_ENABLED` 未設 / `off`：四個端點一律 404 `crypto_disabled`，錯誤體形狀統一。"""
    for flag in (None, "off"):
        if flag is None:
            monkeypatch.delenv("CRYPTO_ENABLED", raising=False)
        else:
            monkeypatch.setenv("CRYPTO_ENABLED", flag)
        for path, payload in ENDPOINTS:
            r = client.post(path, json=payload)
            assert r.status_code == 404, path
            assert r.json()["detail"]["error"] == "crypto_disabled"
            assert r.json()["detail"]["msg"] == "crypto api disabled"


# ---------------------------------------------------------------------------
# 生成助記詞
# ---------------------------------------------------------------------------
def test_generate_mnemonic_12_words(client):
    """128 位（含省略 `strength` 的默認分支）→ 12 詞；且生成的助記詞能被校驗端點接受。"""
    for payload in ({"strength": 128}, {}):
        r = client.post("/api/crypto/generate-mnemonic", json=payload)
        assert r.status_code == 200
        body = r.json()
        assert body["word_count"] == 12
        assert len(body["mnemonic"].split()) == 12
        v = client.post("/api/crypto/validate-mnemonic", json={"mnemonic": body["mnemonic"]})
        assert v.status_code == 200
        assert v.json()["valid"] is True


def test_generate_mnemonic_24_words(client):
    """256 位 → 24 詞；且生成的助記詞能被校驗端點接受。"""
    r = client.post("/api/crypto/generate-mnemonic", json={"strength": 256})
    assert r.status_code == 200
    body = r.json()
    assert body["word_count"] == 24
    assert len(body["mnemonic"].split()) == 24
    v = client.post("/api/crypto/validate-mnemonic", json={"mnemonic": body["mnemonic"]})
    assert v.json()["valid"] is True


def test_generate_mnemonic_invalid_strength(client):
    """非 128 / 256 → 400 `invalid_strength`（只認兩個強度）。"""
    for strength in (192, 0, 64, 512):
        r = client.post("/api/crypto/generate-mnemonic", json={"strength": strength})
        assert r.status_code == 400, strength
        assert r.json()["detail"]["error"] == "invalid_strength"


# ---------------------------------------------------------------------------
# 校驗助記詞
# ---------------------------------------------------------------------------
def test_validate_mnemonic_valid(client):
    """標準 12 詞 BIP-39 助記詞 → 200 `{"valid": true}`。"""
    r = client.post("/api/crypto/validate-mnemonic", json={"mnemonic": VALID_12_WORDS})
    assert r.status_code == 200
    assert r.json() == {"valid": True}


def test_validate_mnemonic_invalid(client):
    """非法入參（詞表外 / 詞數不足 / 校驗和錯 / 空串）→ 200 `{"valid": false}`，**不報錯**。"""
    bad_inputs = (
        "not a mnemonic",
        "abandon " * 11,                      # 詞數不足
        "abandon " * 11 + "notaword",         # 詞表外的詞
        "abandon " * 11 + "abandon",          # 12 詞但校驗和錯
        "",
    )
    for bad in bad_inputs:
        r = client.post("/api/crypto/validate-mnemonic", json={"mnemonic": bad})
        assert r.status_code == 200
        assert r.json() == {"valid": False}


# ---------------------------------------------------------------------------
# 加解密往返 / 空明文
# ---------------------------------------------------------------------------
def test_encrypt_decrypt_roundtrip(client):
    """同助記詞 + 同 purpose：明文 → blob → 明文（含中文，驗 UTF-8 全鏈路）。"""
    plaintext = "姓名：张三；舌象：舌淡红苔薄白（往返測試）"
    blob = _encrypt(client, VALID_12_WORDS, PURPOSE, plaintext)
    # blob 契約（§5.3）：鍵集合恆為四鍵，version 恆為 "1"，其餘為合法十六進制
    assert set(blob) == {"version", "nonce", "ciphertext", "tag"}
    assert blob["version"] == "1"
    for key in ("nonce", "ciphertext", "tag"):
        assert isinstance(blob[key], str)
        assert blob[key] != ""
        bytes.fromhex(blob[key])              # 非十六進制會直接拋 ValueError
    dec = client.post("/api/crypto/decrypt",
                      json={"mnemonic": VALID_12_WORDS, "purpose": PURPOSE, "blob": blob})
    assert dec.status_code == 200
    assert dec.json() == {"plaintext": plaintext}


def test_encrypt_empty_plaintext(client):
    """空明文（`plaintext=""` / 省略該鍵）可加密，並能原樣解回空串。"""
    for payload in ({"mnemonic": VALID_12_WORDS, "purpose": PURPOSE, "plaintext": ""},
                    {"mnemonic": VALID_12_WORDS, "purpose": PURPOSE}):
        enc = client.post("/api/crypto/encrypt", json=payload)
        assert enc.status_code == 200
        blob = enc.json()["blob"]
        assert set(blob) == {"version", "nonce", "ciphertext", "tag"}
        dec = client.post("/api/crypto/decrypt",
                          json={"mnemonic": VALID_12_WORDS, "purpose": PURPOSE, "blob": blob})
        assert dec.status_code == 200
        assert dec.json() == {"plaintext": ""}


# ---------------------------------------------------------------------------
# 解密失敗分支
# ---------------------------------------------------------------------------
def test_decrypt_wrong_mnemonic(client):
    """換一個（合法的）助記詞 → 派生出的密鑰不同 → 400 `decrypt_failed`。"""
    blob = _encrypt(client, VALID_12_WORDS, PURPOSE, "秘密")
    other = client.post("/api/crypto/generate-mnemonic", json={"strength": 128}).json()["mnemonic"]
    assert other != VALID_12_WORDS
    r = client.post("/api/crypto/decrypt",
                    json={"mnemonic": other, "purpose": PURPOSE, "blob": blob})
    assert r.status_code == 400
    assert r.json()["detail"]["error"] == "decrypt_failed"


def test_decrypt_tampered_blob(client):
    """篡改密文首字符（改動一位十六進制）→ GCM 認證標籤不匹配 → 400 `decrypt_failed`。"""
    blob = _encrypt(client, VALID_12_WORDS, PURPOSE, "秘密")
    tampered = dict(blob)
    head = tampered["ciphertext"][0]
    tampered["ciphertext"] = ("0" if head != "0" else "1") + tampered["ciphertext"][1:]
    assert tampered["ciphertext"] != blob["ciphertext"]
    r = client.post("/api/crypto/decrypt",
                    json={"mnemonic": VALID_12_WORDS, "purpose": PURPOSE, "blob": tampered})
    assert r.status_code == 400
    assert r.json()["detail"]["error"] == "decrypt_failed"


def test_decrypt_invalid_blob(client):
    """blob 非對象（字符串 / 列表 / 數字）或缺該鍵 → 400 `invalid_blob`（統一錯誤體，非 422）。"""
    bad_bodies = (
        {"mnemonic": VALID_12_WORDS, "purpose": PURPOSE, "blob": "not-a-blob"},
        {"mnemonic": VALID_12_WORDS, "purpose": PURPOSE, "blob": []},
        {"mnemonic": VALID_12_WORDS, "purpose": PURPOSE, "blob": 1},
        {"mnemonic": VALID_12_WORDS, "purpose": PURPOSE},                    # 缺 blob 鍵
    )
    for body in bad_bodies:
        r = client.post("/api/crypto/decrypt", json=body)
        assert r.status_code == 400, body
        assert r.json()["detail"]["error"] == "invalid_blob"


# ---------------------------------------------------------------------------
# 加密失敗分支
# ---------------------------------------------------------------------------
def test_encrypt_invalid_mnemonic(client):
    """非法助記詞（詞表外 / 詞數不足 / 空串 / 缺鍵）→ 400 `invalid_mnemonic`（不進密碼學）。"""
    bad_bodies = (
        {"mnemonic": "not a mnemonic", "purpose": PURPOSE, "plaintext": "x"},
        {"mnemonic": "abandon " * 11, "purpose": PURPOSE, "plaintext": "x"},
        {"mnemonic": "", "purpose": PURPOSE, "plaintext": "x"},
        {"purpose": PURPOSE, "plaintext": "x"},                              # 缺 mnemonic 鍵
    )
    for body in bad_bodies:
        r = client.post("/api/crypto/encrypt", json=body)
        assert r.status_code == 400, body
        assert r.json()["detail"]["error"] == "invalid_mnemonic"


def test_encrypt_invalid_purpose(client):
    """purpose 為空串 / 缺鍵 → 400 `invalid_purpose`（域標籤不可省）。"""
    bad_bodies = (
        {"mnemonic": VALID_12_WORDS, "purpose": "", "plaintext": "x"},
        {"mnemonic": VALID_12_WORDS, "plaintext": "x"},                      # 缺 purpose 鍵
    )
    for body in bad_bodies:
        r = client.post("/api/crypto/encrypt", json=body)
        assert r.status_code == 400, body
        assert r.json()["detail"]["error"] == "invalid_purpose"


# ---------------------------------------------------------------------------
# 域隔離：purpose 不同 → 子密鑰不同 → 密文互不相認
# ---------------------------------------------------------------------------
def test_purpose_isolation(client):
    """同助記詞 + 同明文、不同 purpose：密文不同；且交叉解密必 400 `decrypt_failed`。"""
    plaintext = "同一個病人的同一個字段值"
    blob_name = _encrypt(client, VALID_12_WORDS, "field:name", plaintext)
    blob_tongue = _encrypt(client, VALID_12_WORDS, "field:tongue", plaintext)
    assert blob_name["ciphertext"] != blob_tongue["ciphertext"]

    # 拿 tongue 的 purpose 去解 name 的 blob（密鑰不符）→ 認證失敗
    crossed = client.post("/api/crypto/decrypt",
                          json={"mnemonic": VALID_12_WORDS, "purpose": "field:tongue",
                                "blob": blob_name})
    assert crossed.status_code == 400
    assert crossed.json()["detail"]["error"] == "decrypt_failed"

    # 各自的正確 purpose 都能解回原文（確認上面的失敗不是「一律失敗」）
    for purpose, blob in (("field:name", blob_name), ("field:tongue", blob_tongue)):
        ok = client.post("/api/crypto/decrypt",
                         json={"mnemonic": VALID_12_WORDS, "purpose": purpose, "blob": blob})
        assert ok.status_code == 200
        assert ok.json() == {"plaintext": plaintext}
