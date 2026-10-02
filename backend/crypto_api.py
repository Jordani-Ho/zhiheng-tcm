"""B 板塊 B1b-1「加解密 API」：**無會話**，每次請求攜帶助記詞（前綴 `/api/crypto`）。

對齊：docs/phase2-data-sovereignty-design.md
  §3.1.3 密鑰層次 / §5.1 算法選型 / §5.2 密鑰派生鏈 / §5.3 加密 blob 結構

落地分工（B1a → B1b-1）：
  · 密碼學全在 `crypto_service.py`（B1a 純函數層：助記詞 / 派生 / 加解密）；
  · 本文件只做四件事 —— 門衛 → 入參校驗 → 調用服務層 → 統一錯誤體；
    零密碼學、零 SQL、零持久化（助記詞**不落地、不緩存、不打日誌**，即用即棄）。

設計要點：
  · **無會話（stateless）**：不像全庫其他接口帶 `teacher_name` / `teacher_id`，
    本組端點以「請求體裡的助記詞」作為唯一憑證；服務端不留任何服務端狀態；
  · feature flag `CRYPTO_ENABLED`（**默認 off**）：off → 四個端點一律 404 `crypto_disabled`，
    既有鏈路一字不改；flag **每次請求現讀**（便於灰度切換 / 測試，不必重啟）；
  · 錯誤體：`{"detail": {"error": code, "msg": 繁中}}`（與 learning_api §7.3 同款）；
  · 本文件用 `HTTPException` 直出、**無**自定義異常類
    → main.py 不需要 `add_exception_handler`。

啟用方式（本機 / 生產，PowerShell）：
    $env:CRYPTO_ENABLED = "on"    # 不設或 off = 全部 404
"""
from __future__ import annotations

import os
from typing import Any

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

import crypto_service

router = APIRouter(prefix="/api/crypto", tags=["crypto"])

# 錯誤碼 → HTTP 狀態碼（照 learning_api._LEARNING_ERROR_STATUS 同款形態）
_CRYPTO_ERROR_STATUS = {
    "crypto_disabled": 404,
    "invalid_mnemonic": 400,
    "invalid_strength": 400,
    "invalid_purpose": 400,
    "invalid_blob": 400,
    "decrypt_failed": 400,
}

# flag 的「開啟」取值（與 template_api._ENABLED_VALUES 同款口徑）
_ENABLED_VALUES = ("on", "1", "true", "yes")

# 支持的助記詞強度（bit）：128 → 12 詞、256 → 24 詞（§3.1.3 / §5.1）
_SUPPORTED_STRENGTHS = (128, 256)


# ---------------------------------------------------------------------------
# 請求體（**本文件自帶**：`models.py` 是既有文件，本步驟不動它；
# 口徑與 main.py 內聯 `BaseModel` 同款 —— 缺字段一律走「校驗失敗」而非 422）
# ---------------------------------------------------------------------------
class GenerateMnemonicInput(BaseModel):
    """`POST /generate-mnemonic`：強度可省，默認 128 位（→ 12 詞）。"""

    strength: int = 128


class ValidateMnemonicInput(BaseModel):
    """`POST /validate-mnemonic`：非法助記詞**不報錯**，只回 `valid: false`。"""

    mnemonic: str = ""


class EncryptInput(BaseModel):
    """`POST /encrypt`：助記詞 + 用途標籤 + 明文。"""

    mnemonic: str = ""
    purpose: str = ""
    plaintext: str = ""


class DecryptInput(BaseModel):
    """`POST /decrypt`：助記詞 + 用途標籤 + blob。

    `blob` 聲明為 `Any`（而非 `dict`）是刻意的：形狀校驗放進端點，讓非法形狀落到
    400 `invalid_blob` 的統一錯誤體，而不是 FastAPI 的 422 校驗體。
    """

    mnemonic: str = ""
    purpose: str = ""
    blob: Any = None


# ---------------------------------------------------------------------------
# 門衛 / 錯誤體 / 校驗助手（照 learning_api 同款：每個端點的第一道門都是 `_guard()`）
# ---------------------------------------------------------------------------
def _enabled() -> bool:
    """flag 現讀（默認 off）：`on` / `1` / `true` / `yes` 視為開啟。"""
    return os.environ.get("CRYPTO_ENABLED", "off").strip().lower() in _ENABLED_VALUES


def _fail(status_code, code, msg):
    """統一錯誤體（照 learning_api._fail）：`{"detail": {"error", "msg"}}`。"""
    raise HTTPException(status_code=status_code, detail={"error": code, "msg": msg})


def _fail_code(code, msg):
    """按 `_CRYPTO_ERROR_STATUS` 取真實 HTTP 狀態碼（表外的碼兜底 400）。"""
    _fail(_CRYPTO_ERROR_STATUS.get(code, 400), code, msg)


def _guard():
    """每個接口的第一道門：flag off → 404 `crypto_disabled`（無任何其他副作用）。"""
    if not _enabled():
        _fail_code("crypto_disabled", "crypto api disabled")


def _check_strength(strength):
    """強度校驗：僅允許 128 / 256（位）。"""
    if strength not in _SUPPORTED_STRENGTHS:
        _fail_code("invalid_strength", "strength 必須是 128 或 256（bit）")


def _check_mnemonic(mnemonic):
    """助記詞校驗：非合法 BIP-39 助記詞 → 400 `invalid_mnemonic`。"""
    if not crypto_service.validate_mnemonic(mnemonic):
        _fail_code("invalid_mnemonic", "助記詞校驗失敗：不是合法的 BIP-39 助記詞")


def _check_purpose(purpose):
    """用途標籤校驗：必須是非空字符串（與 `crypto_service.derive_data_key` 口徑一致）。"""
    if not isinstance(purpose, str) or purpose == "":
        _fail_code("invalid_purpose", "purpose 必須是非空字符串（如 field:name）")


def _derive_data_key(mnemonic, purpose):
    """助記詞 → 主密鑰 → 按 purpose 派生子數據密鑰（§5.2 完整派生鏈）。"""
    master_key = crypto_service.mnemonic_to_master_key(mnemonic)
    return crypto_service.derive_data_key(master_key, purpose)


# ---------------------------------------------------------------------------
# 1. 生成助記詞
# ---------------------------------------------------------------------------
@router.post("/generate-mnemonic")
def generate_mnemonic(data: GenerateMnemonicInput):
    """§5.1：生成 BIP-39 助記詞（128 位 → 12 詞 / 256 位 → 24 詞）。"""
    _guard()
    _check_strength(data.strength)
    mnemonic = crypto_service.generate_mnemonic(data.strength)
    return {"mnemonic": mnemonic, "word_count": len(mnemonic.split())}


# ---------------------------------------------------------------------------
# 2. 校驗助記詞
# ---------------------------------------------------------------------------
@router.post("/validate-mnemonic")
def validate_mnemonic(data: ValidateMnemonicInput):
    """只回合法性布爾：非法是**預期入參**而非故障，故 200 + `valid: false`。"""
    _guard()
    return {"valid": bool(crypto_service.validate_mnemonic(data.mnemonic))}


# ---------------------------------------------------------------------------
# 3. 加密
# ---------------------------------------------------------------------------
@router.post("/encrypt")
def encrypt_payload(data: EncryptInput):
    """§5.3：`data_key = HKDF(master_key, purpose)` → AES-256-GCM → 加密 blob。

    校驗在前（助記詞 / purpose），故 `crypto_service.encrypt` 不會走到 `CryptoError`
    —— 它能拋的兩類情形（密鑰長度錯、明文非字符串）在這裡都已被排除。
    """
    _guard()
    _check_mnemonic(data.mnemonic)
    _check_purpose(data.purpose)
    data_key = _derive_data_key(data.mnemonic, data.purpose)
    return {"blob": crypto_service.encrypt(data_key, data.plaintext)}


# ---------------------------------------------------------------------------
# 4. 解密
# ---------------------------------------------------------------------------
@router.post("/decrypt")
def decrypt_payload(data: DecryptInput):
    """§5.3：同一派生鏈復現 `data_key` → 解 blob；篡改 / 密鑰不符 → 400 `decrypt_failed`。"""
    _guard()
    _check_mnemonic(data.mnemonic)
    _check_purpose(data.purpose)
    if not isinstance(data.blob, dict):
        _fail_code("invalid_blob", "blob 必須是 {version, nonce, ciphertext, tag} 對象")
    data_key = _derive_data_key(data.mnemonic, data.purpose)
    try:
        plaintext = crypto_service.decrypt(data_key, data.blob)
    except crypto_service.CryptoError as exc:
        # 認證標籤不匹配 / 版本不支援 / 字段非法 → 統一 400（不把底層異常類型漏給前端）
        _fail_code("decrypt_failed", "解密失敗：{}".format(exc))
    return {"plaintext": plaintext}
