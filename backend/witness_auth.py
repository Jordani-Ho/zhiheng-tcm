"""D 板块 M2：治理见证人身份鉴权。

内测版（硬编码 2 永久席位）：
- 发起人（永久-1）→ token: witness-dev-initiator
- 知衡（永久-2）→ token: witness-dev-zhieng

鉴权方式（内测）：HTTP Header `X-Witness-Token`。
阶段四切信任根时，本块整体替换为公钥签名验证（D v1.3 §8.2）。
"""

from fastapi import Header, HTTPException


# 内测硬编码（阶段四换公钥）
WITNESS_TOKENS = {
    "witness-dev-initiator": "initiator",
    "witness-dev-zhieng": "zhieng",
}


async def require_witness(x_witness_token: str = Header(None)):
    """FastAPI 依赖：校验见证人身份。

    返回身份标识（"initiator" / "zhieng"）。
    失败抛 401。
    """
    if not x_witness_token:
        raise HTTPException(status_code=401, detail="missing witness token")
    identity = WITNESS_TOKENS.get(x_witness_token)
    if identity is None:
        raise HTTPException(status_code=401, detail="invalid witness token")
    return identity
