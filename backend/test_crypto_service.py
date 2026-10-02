"""B 板块 B1a「密钥体系与加解密」最小验收用例集。

对齐：docs/phase2-data-sovereignty-design.md
  §3.1.3 密钥层次 / §3.1.4 字段私钥包与 tombstone
  §5.1   算法选型 / §5.2 密钥派生链 / §5.3 加密 blob 结构

覆盖用例（与 CTO 指令逐条对应）：
  · test_generate_mnemonic_12_words              —— 128 位 → 12 词
  · test_generate_mnemonic_24_words              —— 256 位 → 24 词
  · test_validate_mnemonic_valid / _invalid      —— 助记词校验正反两面
  · test_mnemonic_to_master_key_deterministic    —— 同一助记词两次派生结果相同
  · test_mnemonic_to_master_key_different_passphrase —— passphrase 不同结果不同
  · test_derive_data_key_different_purpose       —— 不同 purpose 结果不同
  · test_encrypt_decrypt_roundtrip               —— 加解密往返
  · test_decrypt_tampered_ciphertext             —— 篡改密文抛 CryptoError
  · test_decrypt_wrong_key                       —— 错误密钥抛 CryptoError
  · test_hash_field_id_deterministic             —— field_id 哈希确定性
另附少量同族边界用例（默认强度 / 非法强度 / 篡改 tag / 未知版本 / 空明文 / 非法密钥长度）。

运行方式（Windows，串行；见 pytest.ini）：
    cd backend
    ..\\venv\\Scripts\\python.exe -m pytest test_crypto_service.py -v

纪律：
  · 本文件**不 import `database`**，也不需要 `db` / `client` fixture —— `crypto_service` 是纯函数层；
  · 凡可独立复算的期望值一律走**独立路径**（`hashlib` / 常量字面量），不由被测实现自证。
"""
import hashlib
import re

import pytest

import crypto_service
from crypto_service import (
    CryptoError,
    decrypt,
    derive_data_key,
    encrypt,
    generate_mnemonic,
    hash_field_id,
    mnemonic_to_master_key,
    validate_mnemonic,
)

# BIP-39 官方向量：128 位熵的标准 12 词助记词（校验和合法），文档中立的固定输入。
VALID_12_WORDS = ("abandon abandon abandon abandon abandon abandon "
                  "abandon abandon abandon abandon abandon about")


# ---------------------------------------------------------------------------
# 助记词生成 / 校验
# ---------------------------------------------------------------------------

def test_generate_mnemonic_12_words():
    """128 位强度 → 12 词，且生成的助记词自校验通过。"""
    mnemonic = generate_mnemonic(128)
    assert isinstance(mnemonic, str)
    assert len(mnemonic.split()) == 12
    assert validate_mnemonic(mnemonic) is True


def test_generate_mnemonic_24_words():
    """256 位强度 → 24 词，且生成的助记词自校验通过。"""
    mnemonic = generate_mnemonic(256)
    assert len(mnemonic.split()) == 24
    assert validate_mnemonic(mnemonic) is True


def test_generate_mnemonic_default_and_unsupported_strength():
    """默认 128 位 → 12 词；不支持的强度 → ValueError。"""
    assert len(generate_mnemonic().split()) == 12
    with pytest.raises(ValueError):
        generate_mnemonic(192)


def test_validate_mnemonic_valid():
    """标准 12 词助记词 → 合法。"""
    assert validate_mnemonic(VALID_12_WORDS) is True


def test_validate_mnemonic_invalid():
    """词表外 / 词数不符 / 校验和错误 / 非字符串 → 一律 False。"""
    # 词表外的词（第 12 词）
    assert validate_mnemonic("abandon " * 11 + "notaword") is False
    # 词数不足（仅 11 词）
    assert validate_mnemonic("abandon " * 11) is False
    # 词数虽为 12 但校验和错误（全 abandon 不是合法组合）
    assert validate_mnemonic("abandon " * 11 + "abandon") is False
    # 非字符串入参
    assert validate_mnemonic(None) is False


# ---------------------------------------------------------------------------
# 主密钥派生
# ---------------------------------------------------------------------------

def test_mnemonic_to_master_key_deterministic():
    """同一助记词两次派生 → 结果逐字节相同，且恒为 32 字节。"""
    k1 = mnemonic_to_master_key(VALID_12_WORDS)
    k2 = mnemonic_to_master_key(VALID_12_WORDS)
    assert isinstance(k1, bytes)
    assert len(k1) == 32
    assert k1 == k2


def test_mnemonic_to_master_key_different_passphrase():
    """passphrase 不同 → 主密钥不同（口令参与派生）。"""
    k_empty = mnemonic_to_master_key(VALID_12_WORDS, "")
    k_pass = mnemonic_to_master_key(VALID_12_WORDS, "correct horse battery staple")
    assert k_empty != k_pass


def test_mnemonic_to_master_key_rejects_invalid_mnemonic():
    """非法助记词 → CryptoError（不静默产出密钥）。"""
    with pytest.raises(CryptoError):
        mnemonic_to_master_key("not a valid mnemonic phrase at all")


# ---------------------------------------------------------------------------
# 子数据密钥派生（HKDF-SHA256）
# ---------------------------------------------------------------------------

def test_derive_data_key_different_purpose():
    """四个 field purpose 派生出的子密钥两两不同，且均为 32 字节。"""
    master = mnemonic_to_master_key(VALID_12_WORDS)
    keys = {
        purpose: derive_data_key(master, purpose)
        for purpose in ("field:name", "field:family", "field:tongue", "field:voice")
    }
    assert all(len(k) == 32 for k in keys.values())
    assert len(set(keys.values())) == 4


def test_derive_data_key_deterministic():
    """同 (master_key, purpose) → 子密钥可复现。"""
    master = mnemonic_to_master_key(VALID_12_WORDS)
    assert derive_data_key(master, "field:name") == derive_data_key(master, "field:name")


def test_derive_data_key_rejects_bad_inputs():
    """主密钥长度不符 / purpose 非非空字符串 → CryptoError。"""
    master = mnemonic_to_master_key(VALID_12_WORDS)
    with pytest.raises(CryptoError):
        derive_data_key(b"short", "field:name")
    with pytest.raises(CryptoError):
        derive_data_key(master, "")


# ---------------------------------------------------------------------------
# AES-256-GCM 加解密
# ---------------------------------------------------------------------------

def test_encrypt_decrypt_roundtrip():
    """加解密往返：blob 键集合固定、version 为 "1"、明文原样还原。"""
    master = mnemonic_to_master_key(VALID_12_WORDS)
    data_key = derive_data_key(master, "field:name")
    plaintext = "张三 · 舌象：舌淡红、苔薄白"

    blob = encrypt(data_key, plaintext)
    assert set(blob.keys()) == {"version", "nonce", "ciphertext", "tag"}
    assert blob["version"] == "1"
    assert decrypt(data_key, blob) == plaintext


def test_encrypt_fresh_nonce_and_empty_plaintext():
    """每次加密 nonce 均不同；空明文也能正常往返。"""
    master = mnemonic_to_master_key(VALID_12_WORDS)
    data_key = derive_data_key(master, "field:name")

    first = encrypt(data_key, "same plaintext")
    second = encrypt(data_key, "same plaintext")
    assert first["nonce"] != second["nonce"]
    assert first["ciphertext"] != second["ciphertext"]

    assert decrypt(data_key, encrypt(data_key, "")) == ""


def test_decrypt_tampered_ciphertext():
    """篡改密文 → 认证标签校验失败 → CryptoError。"""
    master = mnemonic_to_master_key(VALID_12_WORDS)
    data_key = derive_data_key(master, "field:name")
    blob = encrypt(data_key, "张三")

    raw = bytearray(bytes.fromhex(blob["ciphertext"]))
    raw[0] ^= 0x01
    blob["ciphertext"] = raw.hex()

    with pytest.raises(CryptoError):
        decrypt(data_key, blob)


def test_decrypt_tampered_tag():
    """篡改认证标签 → CryptoError。"""
    master = mnemonic_to_master_key(VALID_12_WORDS)
    data_key = derive_data_key(master, "field:name")
    blob = encrypt(data_key, "张三")

    raw = bytearray(bytes.fromhex(blob["tag"]))
    raw[0] ^= 0x01
    blob["tag"] = raw.hex()

    with pytest.raises(CryptoError):
        decrypt(data_key, blob)


def test_decrypt_wrong_key():
    """错误密钥（另一 purpose 的子密钥）→ CryptoError。"""
    master = mnemonic_to_master_key(VALID_12_WORDS)
    good_key = derive_data_key(master, "field:name")
    wrong_key = derive_data_key(master, "field:family")
    blob = encrypt(good_key, "张三")

    with pytest.raises(CryptoError):
        decrypt(wrong_key, blob)


def test_decrypt_rejects_unknown_version():
    """不支持的 blob 版本 → CryptoError。"""
    master = mnemonic_to_master_key(VALID_12_WORDS)
    data_key = derive_data_key(master, "field:name")
    blob = encrypt(data_key, "张三")
    blob["version"] = "2"

    with pytest.raises(CryptoError):
        decrypt(data_key, blob)


# ---------------------------------------------------------------------------
# field_id 哈希
# ---------------------------------------------------------------------------

def test_hash_field_id_deterministic():
    """field_id 哈希确定性 + 长度 + 与独立 sha256 复算一致 + 不同 field_id 不同哈希。"""
    h1 = hash_field_id("field:name")
    h2 = hash_field_id("field:name")
    assert h1 == h2
    assert len(h1) == 64
    assert h1 == hashlib.sha256(b"field:name").hexdigest()
    assert h1 != hash_field_id("field:family")


# ---------------------------------------------------------------------------
# 分层纪律（源码级守护，照 test_learning.py 的同类手法）
# ---------------------------------------------------------------------------

def test_module_source_never_imports_database():
    """纯函数层纪律：`crypto_service` 顶层**不得** import `database`（本模块不碰 DB）。"""
    with open(crypto_service.__file__, encoding="utf-8") as fh:
        source = fh.read()
    assert re.search(r"^\s*(import\s+database|from\s+database\s+import)\b",
                     source, re.MULTILINE) is None

