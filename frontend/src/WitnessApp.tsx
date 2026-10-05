import { useEffect, useState } from "react";

const ENDPOINTS = [
  { path: "/referrals", title: "引荐链" },
  { path: "/seals", title: "封存记录" },
  // 已移除：{ path: "/levels", title: "段位变更" }
  //   依据 D-002（段位废弃）/ D-017（Epic 5 废除），2026-10-04。
  //   后端 GET /api/v1/witness/levels 端点仍存在但已标注废弃（见 witness_router.py），
  //   保留仅为不改动 test_witness_router.py:58 的既有断言；前端不再导航至此。
  { path: "/kangbi", title: "康币账本" },
] as const;

type ApiResponse = {
  source: string;
  items: unknown[];
  count: number;
};

export default function WitnessApp() {
  const token = new URLSearchParams(window.location.search).get("token");
  const [identity, setIdentity] = useState<string | null>(null);
  const [data, setData] = useState<Record<string, ApiResponse>>({});
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (!token) return;
    fetch("/api/v1/witness/me", { headers: { "X-Witness-Token": token } })
      .then((r) => {
        if (!r.ok) throw new Error(`鉴权失败（HTTP ${r.status}）`);
        return r.json();
      })
      .then((d) => setIdentity(d.identity))
      .catch((e) => setError(e.message));
  }, [token]);

  useEffect(() => {
    if (!identity || !token) return;
    Promise.all(
      ENDPOINTS.map((e) =>
        fetch(`/api/v1/witness${e.path}`, {
          headers: { "X-Witness-Token": token },
        })
          .then((r) => r.json())
          .then((d) => [e.path, d] as const)
      )
    ).then((results) => setData(Object.fromEntries(results)));
  }, [identity, token]);

  if (!token) {
    return (
      <div style={{ padding: 24, fontFamily: "sans-serif" }}>
        <h1>治理见证入口</h1>
        <p>未认证：请通过 URL 参数携带 token 访问。</p>
        <p style={{ color: "#888", fontSize: 12 }}>
          例：/witness.html?token=witness-dev-initiator
        </p>
      </div>
    );
  }

  if (error) {
    return (
      <div style={{ padding: 24, fontFamily: "sans-serif" }}>
        <h1>治理见证入口</h1>
        <p style={{ color: "red" }}>错误：{error}</p>
      </div>
    );
  }

  if (!identity) {
    return (
      <div style={{ padding: 24, fontFamily: "sans-serif" }}>
        <p>加载中…</p>
      </div>
    );
  }

  return (
    <div style={{ padding: 24, fontFamily: "sans-serif" }}>
      <h1>治理见证入口</h1>
      <p>
        身份：<strong>{identity}</strong>
      </p>
      <p style={{ color: "#888", fontSize: 12 }}>
        本入口为只读观察通道。不展示病历、舌苔照、语音、处方明文。
      </p>

      {ENDPOINTS.map((e) => {
        const d = data[e.path];
        return (
          <section
            key={e.path}
            style={{
              marginTop: 24,
              borderTop: "1px solid #ccc",
              paddingTop: 12,
            }}
          >
            <h2>
              {e.title}
              {d && (
                <small style={{ color: "#888", marginLeft: 8 }}>
                  （来源：{d.source}，共 {d.count} 条）
                </small>
              )}
            </h2>
            {d ? (
              d.count === 0 ? (
                <p style={{ color: "#888" }}>无数据</p>
              ) : (
                <pre
                  style={{
                    background: "#f5f5f5",
                    padding: 12,
                    overflow: "auto",
                    fontSize: 12,
                  }}
                >
                  {JSON.stringify(d.items, null, 2)}
                </pre>
              )
            ) : (
              <p>加载中…</p>
            )}
          </section>
        );
      })}
    </div>
  );
}
