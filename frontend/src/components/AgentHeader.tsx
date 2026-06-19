import {
  Activity,
  Bot,
  Mail,
  Play,
  Radio,
  Sparkles,
  Youtube,
} from "lucide-react";
import type { ServerStatus } from "../hooks/useServerHealth";

interface AgentHeaderProps {
  serverStatus: ServerStatus;
  latencyMs: number | null;
  apiUrl: string;
  running: boolean;
}

export function AgentHeader({ serverStatus, latencyMs, apiUrl, running }: AgentHeaderProps) {
  return (
    <header className="agent-header">
      <div className="brand">
        <div className="brand-icon">
          <Youtube size={22} />
        </div>
        <div>
          <h1>YouTube Community Manager Agent</h1>
          <p>LangGraph pipeline · scrape, analyze, reply, report</p>
        </div>
      </div>

      <div className="header-status">
        <div className={`status-pill ${serverStatus}`}>
          <Radio size={14} />
          <span>
            LangGraph {serverStatus === "online" ? "connected" : serverStatus === "offline" ? "offline" : "…"}
          </span>
          {latencyMs != null && <span className="muted">· {latencyMs}ms</span>}
        </div>
        {running && (
          <div className="status-pill running">
            <Activity size={14} className="spin" />
            <span>Agent running</span>
          </div>
        )}
        <div className="status-pill neutral">
          <Bot size={14} />
          <span className="mono truncate">{apiUrl}</span>
        </div>
      </div>

      <div className="header-badges">
        <span className="badge"><Sparkles size={12} /> Humorous replies</span>
        <span className="badge"><Play size={12} /> Playwright browser</span>
        <span className="badge"><Mail size={12} /> HTML + PDF reports</span>
      </div>
    </header>
  );
}
