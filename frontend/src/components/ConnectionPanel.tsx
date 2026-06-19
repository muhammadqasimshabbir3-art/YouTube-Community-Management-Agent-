import { Loader2, RefreshCw, Server, Wifi, WifiOff } from "lucide-react";
import type { ServerStatus } from "../hooks/useServerHealth";

interface ConnectionPanelProps {
  status: ServerStatus;
  latencyMs: number | null;
  apiUrl: string;
  assistantId: string;
  threadId: string | null;
  runId: string | null;
  loggedIn: boolean | null;
  onRefresh: () => void;
}

export function ConnectionPanel({
  status,
  latencyMs,
  apiUrl,
  assistantId,
  threadId,
  runId,
  loggedIn,
  onRefresh,
}: ConnectionPanelProps) {
  return (
    <aside className="panel connection-panel">
      <div className="panel-title">
        <Server size={16} />
        <span>Backend</span>
        <button type="button" className="icon-btn" onClick={onRefresh} title="Refresh connection">
          <RefreshCw size={14} />
        </button>
      </div>

      <div className="connection-grid">
        <div className="connection-row">
          <span>API</span>
          <code className="mono">{apiUrl}</code>
        </div>
        <div className="connection-row">
          <span>Graph</span>
          <code className="mono">{assistantId}</code>
        </div>
        <div className="connection-row">
          <span>Health</span>
          <span className={`health ${status}`}>
            {status === "checking" && <Loader2 size={14} className="spin" />}
            {status === "online" && <Wifi size={14} />}
            {status === "offline" && <WifiOff size={14} />}
            {status}
            {latencyMs != null ? ` (${latencyMs}ms)` : ""}
          </span>
        </div>
        <div className="connection-row">
          <span>YouTube</span>
          <span className={`health ${loggedIn === true ? "online" : loggedIn === false ? "offline" : ""}`}>
            {loggedIn === true && "🔐 signed in"}
            {loggedIn === false && "🔐 not signed in"}
            {loggedIn == null && "—"}
          </span>
        </div>
        {threadId && (
          <div className="connection-row">
            <span>Thread</span>
            <code className="mono">{threadId.slice(0, 12)}…</code>
          </div>
        )}
        {runId && (
          <div className="connection-row">
            <span>Run</span>
            <code className="mono">{runId.slice(0, 12)}…</code>
          </div>
        )}
      </div>

      <div className="deploy-note">
        <strong>Deployment</strong>
        <p>
          Backend runs on LangGraph Server. Point this UI at it with{" "}
          <code>VITE_LANGGRAPH_API_URL</code> when hosting the frontend separately.
        </p>
      </div>
    </aside>
  );
}
