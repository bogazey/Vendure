import { RequireAuth, RequireCapability, usePlatformUser, useProductEntitlements } from "@platform-core/react-client";

const BACKEND_URL = "http://localhost:9303";

export default function App() {
  return (
    <div style={{ minHeight: "100vh", display: "flex", alignItems: "center", justifyContent: "center" }}>
      <div style={{ width: 480, background: "rgba(17,24,39,.75)", border: "1px solid rgba(255,255,255,.08)", borderRadius: 18, padding: 32 }}>
        <h1 style={{ margin: "0 0 4px", fontSize: 22, color: "#22c55e" }}>Sample Future Product 2</h1>
        <p style={{ color: "#94a3b8", fontSize: 13, margin: "0 0 20px" }}>
          Onboarded through Grand Admin. Uses @platform-core/react-client - no copied auth code.
        </p>

        <RequireAuth
          loading={<p data-testid="state">Checking your session…</p>}
          fallback={
            <div>
              <p data-testid="state">This product delegates sign-in to the ecosystem's central identity.</p>
              <a
                href={`${BACKEND_URL}/auth/login`}
                style={{ display: "inline-block", marginTop: 10, padding: "10px 16px", borderRadius: 10, background: "#22c55e", color: "#0b0f1a", fontWeight: 600, textDecoration: "none" }}
              >
                Sign in with Central Identity
              </a>
            </div>
          }
        >
          <Dashboard />
        </RequireAuth>
      </div>
    </div>
  );
}

function Dashboard() {
  const { user, logout } = usePlatformUser();
  const { status, entitlement, error } = useProductEntitlements();

  return (
    <div>
      <p data-testid="state">Signed in via the central identity - no separate account exists here.</p>
      <dl style={{ fontSize: 13, color: "#cbd3e8" }}>
        <dt style={{ color: "#64748b", marginTop: 8 }}>Email</dt>
        <dd data-testid="email" style={{ margin: 0, fontFamily: "monospace" }}>{user?.email}</dd>
        <dt style={{ color: "#64748b", marginTop: 8 }}>Global user ID (sub)</dt>
        <dd data-testid="sub" style={{ margin: 0, fontFamily: "monospace", wordBreak: "break-all" }}>{user?.sub}</dd>
        <dt style={{ color: "#64748b", marginTop: 8 }}>Entitlement in sample-future-2</dt>
        <dd data-testid="entitlement">
          {status === "loading" && "Loading…"}
          {status === "ready" && (entitlement?.plan_slug ? `${entitlement.plan_slug} · ${entitlement.source}` : "No active plan")}
          {status === "error" && `Error: ${error?.message}`}
        </dd>
      </dl>

      <RequireCapability
        capability="beta_feature"
        loading={<p data-testid="capability-state">Checking capability…</p>}
        denied={<p data-testid="capability-state">No access to the beta feature on your current plan.</p>}
      >
        <p data-testid="capability-state" style={{ color: "#22d3ee" }}>Beta feature unlocked!</p>
      </RequireCapability>

      <button
        type="button"
        onClick={() => void logout()}
        style={{ marginTop: 16, padding: "10px 16px", borderRadius: 10, border: "none", background: "#334155", color: "#e2e8f0", cursor: "pointer" }}
      >
        Sign out of Sample Future Product 2
      </button>
    </div>
  );
}
