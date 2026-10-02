"""B 板块 B1a「密钥体系与加解密」纯函数层：零 HTTP、零 DB、零全局状态。

对齐：docs/phase2-data-sovereignty-design.md
  §3.1.3 密钥层次 / §3.1.4 字段私钥包与 tombstone
  §5.1   算法选型 / §5.2 密钥派生链（完整版）/ §5.3 加密 blob 结构

完整派生链（本模块逐段落地）：

    助记词（BIP-39，12 / 24 词）
      └─ Argon2id（熵拉伸，抗暴力破解）─→ 种子（64 字节）
           └─ BIP-32（路径 m/44'/0'/0'/0/0）─→ 主密钥（32 字节）
                ├─ HKDF-SHA256（按 purpose 派生）─→ 子数据密钥（32 字节）
                │      └─ AES-256-GCM ─→ 加密 blob
                └─ field_id 一律以 sha256(field_id) 十六进制入包（tombstone 防泄漏）

设计要点（写死在此，供后续步骤引用）：
  · **BIP-39 只负责「助记词 ↔ 熵」的编码**，不直接派生密钥；
  · **Argon2id** 对助记词做熵拉伸，输出 64 字节种子；
    - 参数固定为 time_cost=3 / memory_cost=65536(=64 MiB) / parallelism=1；
    - salt 取 `sha256(passphrase)`（恒定 32 字节）—— 纯函数无持久化，故用确定性 salt：
      既满足 Argon2 对 salt ≥ 8 字节的硬要求，又让 passphrase 参与派生（换 passphrase 必换密钥）；
  · **BIP-32** 派生分层确定性密钥树；取 `m/44'/0'/0'/0/0` 叶子私钥的 32 字节作为主密钥
    （独立命名空间，避免与既有加密货币钱包用途混淆）；
  · **HKDF-SHA256** 由主密钥按 `purpose`（如 `field:name` / `field:family` /
    `field:tongue` / `field:voice`）派生互不相同的 32 字节子密钥；
  · **AES-256-GCM** 为认证加密：防篡改；blob 结构见 §5.3（version / nonce / ciphertext / tag）。

模块纪律（与 Epic 3 `learning_service.py` 同款分层）：
  · **不 import `database`** —— 本模块不碰 DB、不发任何 SQL；
  · 除 `generate_mnemonic`（含 CSPRNG）外**全部为纯函数**：相同入参必得相同结果；
  · **零模块级可变状态**：顶层只有常量与函数定义；导入期零副作用（不读档 / 不读库 / 不读 env）；
  · 类型注解齐全；公开函数一律带中文 docstring；
  · 任何失败一律以自定义异常 `CryptoError` 冒泡 —— 调用方无需 import 第三方库的异常类型。
"""
import hashlib
import os

from argon2.low_level import Type as Argon2Type
from argon2.low_level import hash_secret_raw
from bip_utils import (
    Bip39MnemonicGenerator,
    Bip39MnemonicValidator,
    Bip39WordsNum,
    Bip44,
    Bip44Changes,
    Bip44Coins,
)
from cryptography.exceptions import InvalidTag
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from cryptography.hazmat.primitives.kdf.hkdf import HKDF

# ---------------------------------------------------------------------------
# 口径常量（§3.1.3 / §5.1 / §5.3）：一经落地即被 blob / 派生链引用，变更须连带迁移方案
# ---------------------------------------------------------------------------
BLOB_VERSION = "1"            # 加密 blob 契约版本（§5.3：字面量 "1"）
NONCE_LEN = 12                # AES-GCM 标准 nonce 长度（96 bit）
TAG_LEN = 16                  # AES-GCM 认证标签长度（128 bit）
SEED_LEN = 64                 # Argon2id 输出种子长度（§5.2：64 字节）
MASTER_KEY_LEN = 32           # 主密钥长度（§3.1.3：AES-256 = 32 字节）
DATA_KEY_LEN = 32             # 子数据密钥长度（HKDF 输出，AES-256 = 32 字节）

# 助记词强度（bit）→ 词数：128 位 = 12 词、256 位 = 24 词（§3.1.3 / §5.1）
_STRENGTH_TO_WORDS = {
    128: Bip39WordsNum.WORDS_NUM_12,
    256: Bip39WordsNum.WORDS_NUM_24,
}

# BIP-32 派生路径：独立用途命名空间（避免与既有加密货币钱包冲突）
BIP32_PATH = "m/44'/0'/0'/0/0"

# Argon2id 参数（§5.1：内存硬、抗 GPU / ASIC）
ARGON2_TIME_COST = 3          # 迭代次数
ARGON2_MEMORY_COST = 65536    # 内存成本（KiB）= 64 MiB
ARGON2_PARALLELISM = 1        # 并行度（纯函数，保持确定性）


class CryptoError(Exception):
    """B 板块加密链路统一异常。

    加解密 / 密钥派生 / 助记词校验的**所有**失败分支一律以此类型抛出，
    使调用方（服务层 / 接口层）无需感知 `argon2` / `cryptography` / `bip_utils`
    的底层异常类型，也让「篡改检测失败」在接口层可稳定映射为同一个错误体。
    """


def generate_mnemonic(strength: int = 128) -> str:
    """生成 BIP-39 助记词（CSPRNG 熵源）。

    参数：
        strength: 熵强度（bit）。仅支持 `128`（→ 12 词）与 `256`（→ 24 词，§3.1.3）。

    返回：
        以空格分隔的助记词字符串。

    异常：
        ValueError: 传入不支持的强度值。

    说明：
        本函数是模块内**唯一非纯函数**（依赖系统级随机数 os.urandom），
        其余函数在相同入参下结果恒定。
    """
    words_num = _STRENGTH_TO_WORDS.get(strength)
    if words_num is None:
        raise ValueError(
            "不支持的助记词强度：{!r}（仅允许 {}）".format(
                strength, sorted(_STRENGTH_TO_WORDS)
            )
        )
    return str(Bip39MnemonicGenerator().FromWordsNumber(words_num))


def validate_mnemonic(mnemonic: str) -> bool:
    """校验 BIP-39 助记词是否合法（词表 + 词数 + 校验和）。

    参数：
        mnemonic: 待校验的助记词字符串。

    返回：
        `True` 表示合法；`False` 表示词表外 / 词数不符 / 校验和错误 / 入参非字符串。

    说明：
        非法输入一律返回 `False`（不抛异常），便于调用方在恢复流程中直接做分支判定。
    """
    if not isinstance(mnemonic, str):
        return False
    try:
        return bool(Bip39MnemonicValidator().IsValid(mnemonic))
    except Exception:
        # 校验器对极端异常入参（编码 / 解析）抛错时，统一按「不合法」处理
        return False


def mnemonic_to_master_key(mnemonic: str, passphrase: str = "") -> bytes:
    """由 BIP-39 助记词派生主密钥（32 字节）。

    派生链（§5.2）：助记词 → Argon2id → 种子（64 字节）→ BIP-32(m/44'/0'/0'/0/0) → 主密钥。

    参数：
        mnemonic: 合法的 BIP-39 助记词。
        passphrase: 可选口令（BIP-39 的 25th word 语义），空串表示不设口令。

    返回：
        32 字节主密钥。

    异常：
        CryptoError: 助记词非法时抛出。

    说明：
        Argon2id 参数 = time_cost 3 / memory_cost 65536 / parallelism 1；
        salt = `sha256(passphrase.encode("utf-8"))`（恒定 32 字节，确定性、可复现），
        因此同一助记词 + 同一 passphrase 必得同一主密钥，换 passphrase 必换主密钥。
    """
    if not validate_mnemonic(mnemonic):
        raise CryptoError("助记词校验失败：不是合法的 BIP-39 助记词")

    passphrase_bytes = passphrase.encode("utf-8") if isinstance(passphrase, str) else b""
    salt = hashlib.sha256(passphrase_bytes).digest()   # 恒定 32 字节，满足 Argon2 salt ≥ 8 字节要求

    seed = hash_secret_raw(
        secret=mnemonic.encode("utf-8"),
        salt=salt,
        time_cost=ARGON2_TIME_COST,
        memory_cost=ARGON2_MEMORY_COST,
        parallelism=ARGON2_PARALLELISM,
        hash_len=SEED_LEN,
        type=Argon2Type.ID,
    )

    # Bip44 链 Purpose(44')/Coin(0')/Account(0)/Change(0)/AddressIndex(0) 即 BIP32_PATH = "m/44'/0'/0'/0/0"
    bip44_mst = Bip44.FromSeed(seed, Bip44Coins.BITCOIN)
    leaf_key = (
        bip44_mst.Purpose()
        .Coin()
        .Account(0)
        .Change(Bip44Changes.CHAIN_EXT)
        .AddressIndex(0)
        .PrivateKey()
        .Raw()
        .ToBytes()
    )
    return bytes(leaf_key)


def derive_data_key(master_key: bytes, purpose: str) -> bytes:
    """由主密钥经 HKDF-SHA256 派生 32 字节子数据密钥。

    参数：
        master_key: 32 字节主密钥（`mnemonic_to_master_key` 的输出）。
        purpose: 用途标签（如 `field:name` / `field:family` / `field:tongue` / `field:voice`）；
                 不同 purpose 派生互不相同的子密钥（域隔离）。

    返回：
        32 字节子数据密钥。

    异常：
        CryptoError: `master_key` 长度非 32 字节，或 `purpose` 非非空字符串。

    说明：
        HKDF-SHA256 的 salt 固定为空（等价全零），仅以 `info=purpose` 做域隔离；
        同 (master_key, purpose) 必得同一子密钥，保证确定性可复现。
    """
    if not isinstance(master_key, (bytes, bytearray)) or len(master_key) != MASTER_KEY_LEN:
        raise CryptoError("master_key 必须是 {} 字节".format(MASTER_KEY_LEN))
    if not isinstance(purpose, str) or purpose == "":
        raise CryptoError("purpose 必须是非空字符串")

    hkdf = HKDF(
        algorithm=hashes.SHA256(),
        length=DATA_KEY_LEN,
        salt=None,
        info=purpose.encode("utf-8"),
    )
    return hkdf.derive(bytes(master_key))


def encrypt(data_key: bytes, plaintext: str) -> dict:
    """以 AES-256-GCM 加密明文，返回 §5.3 结构的 blob。

    参数：
        data_key: 32 字节子数据密钥（`derive_data_key` 的输出）。
        plaintext: 待加密明文（UTF-8 字符串）。

    返回：
        dict，键集合恒为 `{"version", "nonce", "ciphertext", "tag"}`（值均为十六进制字符串）：
            · version:   契约版本，恒为 `"1"`；
            · nonce:     随机 12 字节 nonce（CSPRNG，每次加密都重新生成）；
            · ciphertext: 密文（不含 tag）；
            · tag:        GCM 认证标签（16 字节）。

    异常：
        CryptoError: `data_key` 长度非 32 字节，或 `plaintext` 非字符串。
    """
    _require_data_key(data_key)
    if not isinstance(plaintext, str):
        raise CryptoError("plaintext 必须是字符串")

    nonce = os.urandom(NONCE_LEN)
    sealed = AESGCM(bytes(data_key)).encrypt(nonce, plaintext.encode("utf-8"), None)
    ciphertext, tag = sealed[:-TAG_LEN], sealed[-TAG_LEN:]
    return {
        "version": BLOB_VERSION,
        "nonce": nonce.hex(),
        "ciphertext": ciphertext.hex(),
        "tag": tag.hex(),
    }


def decrypt(data_key: bytes, blob: dict) -> str:
    """解密 AES-256-GCM blob，返回明文字符串。

    参数：
        data_key: 32 字节子数据密钥（须与加密时一致）。
        blob: `encrypt` 产出的 §5.3 结构（version / nonce / ciphertext / tag，均为十六进制）。

    返回：
        解密后的 UTF-8 明文字符串。

    异常：
        CryptoError: 以下任一情形一律抛出——
            · `data_key` 长度非 32 字节；
            · `blob` 非 dict，或缺少字段 / 字段非合法十六进制；
            · blob 版本不受支持；
            · **认证标签校验失败**（密文 / tag 被篡改，或密钥不匹配）。
    """
    _require_data_key(data_key)
    if not isinstance(blob, dict):
        raise CryptoError("blob 必须是 dict")

    if blob.get("version") != BLOB_VERSION:
        raise CryptoError("不支持的 blob 版本：{!r}".format(blob.get("version")))

    try:
        nonce = bytes.fromhex(blob["nonce"])
        ciphertext = bytes.fromhex(blob["ciphertext"])
        tag = bytes.fromhex(blob["tag"])
    except (KeyError, TypeError, ValueError) as exc:
        raise CryptoError("blob 字段缺失或非合法十六进制：{}".format(exc)) from exc

    try:
        plaintext = AESGCM(bytes(data_key)).decrypt(nonce, ciphertext + tag, None)
    except InvalidTag as exc:
        raise CryptoError("解密失败：认证标签不匹配（密文被篡改或密钥错误）") from exc

    try:
        return plaintext.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise CryptoError("解密失败：明文非合法 UTF-8") from exc


def hash_field_id(field_id: str) -> str:
    """计算 field_id 的 SHA-256 十六进制摘要（§3.1.4：tombstone 的 field_id_hash）。

    参数：
        field_id: 字段标识（如 `name` / `family` / `tongue` / `voice`）。

    返回：
        64 个字符的 SHA-256 十六进制摘要。

    异常：
        CryptoError: `field_id` 非字符串。

    说明：
        字段私钥包只存哈希、不存明文 field_id —— 攻击者即使拿到包，也看不出删的是姓名还是舌象；
        持有主密钥者用已知 field_id 计算哈希后即可定位条目（防 tombstone 泄漏）。
    """
    if not isinstance(field_id, str):
        raise CryptoError("field_id 必须是字符串")
    return hashlib.sha256(field_id.encode("utf-8")).hexdigest()


def _require_data_key(data_key: bytes) -> None:
    """校验子数据密钥长度（内部助手）：非 32 字节一律抛 `CryptoError`。"""
    if not isinstance(data_key, (bytes, bytearray)) or len(data_key) != DATA_KEY_LEN:
        raise CryptoError("data_key 必须是 {} 字节".format(DATA_KEY_LEN))
