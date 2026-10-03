"""D 板块 M4：witness_hash 单元测试。"""

import pytest

from backend.learning_service import GENESIS_HASH, canonical_json
from backend.witness_hash import (
    D_SNAPSHOT_HASH_KEYS,
    compute_event_payload_hash,
    compute_snapshot_hash,
    verify_snapshot_hash,
)


def _full_snapshot():
    """构造一个完整的合法快照（8 个哈希键 + witness_seats 元信息）。"""
    return {
        "snapshot_id": "snap-001",
        "event_type": "REFERRAL_CREATED",
        "event_source": "C 板块",
        "lineage_id": "lineage-abc",
        "event_payload_hash": "a" * 64,
        "canonical_sort_keys": True,
        "genesis_hash": GENESIS_HASH,
        "timestamp": "2026-10-02T10:00:00Z",
        "witness_seats": ["permanent-1", "permanent-2", "elected-1"],
    }


# T1: 正常路径 —— 完整快照 → 稳定 hash
def test_T1_normal_stable():
    snap = _full_snapshot()
    h1 = compute_snapshot_hash(snap)
    h2 = compute_snapshot_hash(snap)
    assert h1 == h2
    assert isinstance(h1, str)
    assert len(h1) == 64
    assert h1 == h1.lower()


# T2: 缺单键 → ValueError，报出缺失键名
def test_T2_missing_key_raises():
    snap = _full_snapshot()
    del snap["snapshot_id"]
    with pytest.raises(ValueError) as exc_info:
        compute_snapshot_hash(snap)
    assert "snapshot_id" in str(exc_info.value)


# T2b: 缺多键 → ValueError 报出全部缺失键
def test_T2b_missing_multiple_keys():
    snap = _full_snapshot()
    del snap["snapshot_id"]
    del snap["timestamp"]
    with pytest.raises(ValueError) as exc_info:
        compute_snapshot_hash(snap)
    msg = str(exc_info.value)
    assert "snapshot_id" in msg
    assert "timestamp" in msg


# T3: 含中文 → hash 稳定；不同中文产生不同 hash
def test_T3_chinese_stable():
    snap1 = _full_snapshot()
    snap1["event_type"] = "纠纷调停"
    snap1["event_source"] = "社区治理"

    snap2 = _full_snapshot()
    snap2["event_type"] = "严重违规"
    snap2["event_source"] = "社区治理"

    h1 = compute_snapshot_hash(snap1)
    assert h1 == compute_snapshot_hash(snap1)          # 幂等
    assert h1 != compute_snapshot_hash(snap2)          # 不同中文不同 hash


# T3b: ensure_ascii=False 语义核实 —— 中文不转义为 \uXXXX
def test_T3b_chinese_not_escaped():
    encoded = canonical_json({"k": "纠纷调停"})
    assert "纠纷调停" in encoded
    assert "\\u" not in encoded


# T4: 数值类型敏感 —— int 1 vs float 1.0 产生不同 hash
def test_T4_numeric_type_sensitive():
    h_int = compute_event_payload_hash({"x": 1})
    h_float = compute_event_payload_hash({"x": 1.0})
    assert h_int != h_float


# T4b: payload 含 None → ValueError
def test_T4b_none_in_payload_raises():
    with pytest.raises(ValueError):
        compute_event_payload_hash({"x": None})


# T4c: payload 嵌套含 None → ValueError
def test_T4c_nested_none_raises():
    with pytest.raises(ValueError):
        compute_event_payload_hash({"outer": {"inner": [1, None, 3]}})


# T5: 篡改一字节 → hash 变化
def test_T5_tamper_detection():
    snap = _full_snapshot()
    h_before = compute_snapshot_hash(snap)
    snap["event_type"] = "REFERRAL_CREATED_X"
    h_after = compute_snapshot_hash(snap)
    assert h_before != h_after


# T6: dict 键顺序不影响 hash
def test_T6_key_order_independent():
    snap1 = _full_snapshot()
    snap2 = dict(reversed(list(snap1.items())))
    assert compute_snapshot_hash(snap1) == compute_snapshot_hash(snap2)


# T7: 幂等 —— 同输入重复调用 → 相同输出
def test_T7_idempotent():
    snap = _full_snapshot()
    results = [compute_snapshot_hash(snap) for _ in range(10)]
    assert len(set(results)) == 1


# T8: witness_seats 不参与哈希
def test_T8_witness_seats_not_hashed():
    snap1 = _full_snapshot()
    snap2 = _full_snapshot()
    snap2["witness_seats"] = ["completely", "different", "seats"]
    assert compute_snapshot_hash(snap1) == compute_snapshot_hash(snap2)


# T9: snapshot_hash 字段不参与自身哈希
def test_T9_snapshot_hash_not_self_hashed():
    snap1 = _full_snapshot()
    snap2 = _full_snapshot()
    snap2["snapshot_hash"] = "any-hash-value"
    assert compute_snapshot_hash(snap1) == compute_snapshot_hash(snap2)


# T10: verify 正常路径
def test_T10_verify_true():
    snap = _full_snapshot()
    h = compute_snapshot_hash(snap)
    assert verify_snapshot_hash(snap, h) is True


# T11: verify 篡改检测
def test_T11_verify_false_on_tamper():
    snap = _full_snapshot()
    h = compute_snapshot_hash(snap)
    snap["event_type"] = "TAMPERED"
    assert verify_snapshot_hash(snap, h) is False


# T12: verify 对非法快照返回 False（不抛异常）
def test_T12_verify_false_on_malformed():
    snap = _full_snapshot()
    del snap["snapshot_id"]
    assert verify_snapshot_hash(snap, "anyhash") is False


# T13: compute_event_payload_hash 基础路径
def test_T13_event_payload_hash_basic():
    payload = {"action": "referral", "from": "teacher-A", "to": "teacher-B"}
    h = compute_event_payload_hash(payload)
    assert isinstance(h, str)
    assert len(h) == 64
    assert h == compute_event_payload_hash(payload)


# T14: D_SNAPSHOT_HASH_KEYS 常量正确性
def test_T14_hash_keys_shape():
    assert isinstance(D_SNAPSHOT_HASH_KEYS, tuple)
    assert len(D_SNAPSHOT_HASH_KEYS) == 8
    assert "event_payload_hash" in D_SNAPSHOT_HASH_KEYS
    assert "witness_seats" not in D_SNAPSHOT_HASH_KEYS
    assert "snapshot_hash" not in D_SNAPSHOT_HASH_KEYS


# T15: canonical_sort_keys = True（布尔，非 list）
def test_T15_canonical_sort_keys_is_bool():
    snap = _full_snapshot()
    assert snap["canonical_sort_keys"] is True
    # 验证真值可被 canonical_json 序列化
    h = compute_snapshot_hash(snap)
    assert isinstance(h, str)