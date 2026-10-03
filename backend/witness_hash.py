"""D 板块 M4：治理见证哈希快照的纯函数实现。

复用 Epic 3 §2.3 的哈希口径（唯一合法实现）：
- canonical_json / sha256_hex（函数）
- GENESIS_HASH（常量）

D 快照使用独立 8 键（D v1.3 §6.2 / §9.2），不复用 Epic 3 的 9 键结构。

口径声明：
- 摘要算法 = sha256（Epic 3 §2.3 `PAYLOAD_HASH_ALGO` 同源）
- 编码 = canonical_json 的 UTF-8 字节（ensure_ascii=False）

M4 只做哈希纯函数：
- 不做存储
- 不做上链
- 不做生成时机
- 不做迁移

v1.3.1 待办（本模块相关的文档注记）：
- §6.2 加注：witness_seats 不参与快照哈希
- §6.2 加注：snapshot_hash 不参与快照自身哈希
- §6.2 加注：canonical_sort_keys 语义 = 布尔（同 Epic 3）
- §6.1 或新增 §6.6：复用范围 = 复用函数 + canonical_json + sha256_hex，不复用 9 键结构
- §6.2 加注：hash schema 未来版本锚定用 hash_schema_version 字段（待启用）
"""

from backend.learning_service import (
    GENESIS_HASH,
    canonical_json,
    sha256_hex,
)


# 参与快照哈希的 8 键（顺序无关，canonical_json 负责唯一化）
D_SNAPSHOT_HASH_KEYS = (
    "snapshot_id",
    "event_type",
    "event_source",
    "lineage_id",
    "event_payload_hash",
    "canonical_sort_keys",
    "genesis_hash",
    "timestamp",
)

# 不参与快照哈希的元信息字段（文档性常量，供测试与后续模块引用）：
# - witness_seats：随席位变更/休眠变化，纳入哈希会破坏确定性
# - snapshot_hash：快照自含哈希，纳入自身哈希造成自指
D_SNAPSHOT_NON_HASH_KEYS = (
    "witness_seats",
    "snapshot_hash",
)


def _assert_no_none(value, path=""):
    """递归检查 value 内不得出现 None（Epic 3 §2.3 硬规则 2）。

    payload 内出现 None 会序列化为 null，与空值哨兵（'' / 0 / {}）字节不同，
    是链验证漂移的常见来源。D 侧拒绝而非静默清洗——若 C 侧传入 None，
    应在接口契约层解决。
    """
    if value is None:
        raise ValueError(
            "payload 含 None（违反 Epic 3 §2.3 硬规则 2），路径："
            + (path or "<root>")
        )
    if isinstance(value, dict):
        for k, v in value.items():
            _assert_no_none(v, f"{path}.{k}" if path else str(k))
    elif isinstance(value, (list, tuple)):
        for i, v in enumerate(value):
            _assert_no_none(v, f"{path}[{i}]")


def compute_event_payload_hash(event_payload):
    """计算治理事件载荷的哈希。

    输入：event_payload — 治理事件的原始载荷（dict）
    输出：sha256 小写十六进制（64 字符）
    异常：ValueError 若 payload 内出现 None

    口径：与 Epic 3 §2.3 的 payload_hash 计算完全一致。
    """
    _assert_no_none(event_payload)
    return sha256_hex(canonical_json(event_payload))


def compute_snapshot_hash(snapshot):
    """计算快照整体哈希。

    输入：snapshot — 含 D_SNAPSHOT_HASH_KEYS 所有 8 键的 dict
    输出：sha256 小写十六进制（64 字符）
    异常：ValueError 若缺任一 D_SNAPSHOT_HASH_KEYS 中的键

    非哈希字段（witness_seats / snapshot_hash）即使存在于 snapshot，
    也不参与本哈希计算（显式白名单提取，多余键忽略）。
    """
    missing = [k for k in D_SNAPSHOT_HASH_KEYS if k not in snapshot]
    if missing:
        raise ValueError(
            "snapshot 缺 D_SNAPSHOT_HASH_KEYS 中的键：" + repr(missing)
        )
    hash_input = {k: snapshot[k] for k in D_SNAPSHOT_HASH_KEYS}
    return sha256_hex(canonical_json(hash_input))


def verify_snapshot_hash(snapshot, expected_hash):
    """验证快照哈希。

    输入：
        snapshot — 含 D_SNAPSHOT_HASH_KEYS 所有 8 键的 dict
        expected_hash — 期望的 sha256 十六进制字符串
    输出：bool（True = 匹配，False = 不匹配或快照结构非法）

    本函数不抛异常 —— 校验场景下，任何异常都归为 False。
    """
    try:
        actual = compute_snapshot_hash(snapshot)
    except (ValueError, TypeError, KeyError):
        return False
    return actual == expected_hash