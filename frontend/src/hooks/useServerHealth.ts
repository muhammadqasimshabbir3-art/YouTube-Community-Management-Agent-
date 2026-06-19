import { useCallback, useEffect, useState } from "react";
import { checkAgentHealth } from "../lib/agentClient";
import { LANGGRAPH_API_URL } from "../config";

export type ServerStatus = "checking" | "online" | "offline";

export function useServerHealth(pollMs = 8000) {
  const [status, setStatus] = useState<ServerStatus>("checking");
  const [latencyMs, setLatencyMs] = useState<number | null>(null);

  const check = useCallback(async () => {
    const { ok, latencyMs: ms } = await checkAgentHealth();
    if (ok) {
      setLatencyMs(ms);
      setStatus("online");
    } else {
      setLatencyMs(null);
      setStatus("offline");
    }
  }, []);

  useEffect(() => {
    void check();
    const id = window.setInterval(() => void check(), pollMs);
    return () => window.clearInterval(id);
  }, [check, pollMs]);

  return { status, latencyMs, check, apiUrl: LANGGRAPH_API_URL };
}
