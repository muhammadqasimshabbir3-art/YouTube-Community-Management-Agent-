/**
 * Local / deployed connection settings (from root .env via Vite envDir).
 *
 * Local testing (recommended in .env):
 *   VITE_LANGGRAPH_API_URL=http://127.0.0.1:2024
 *   VITE_UI_URL=http://localhost:5173
 *
 * Alternative: leave VITE_LANGGRAPH_API_URL empty to use Vite proxy /api → LANGGRAPH_PORT
 */
const configuredApi = import.meta.env.VITE_LANGGRAPH_API_URL?.trim();

export const LANGGRAPH_API_URL = configuredApi || "/api";

export const ASSISTANT_ID =
  import.meta.env.VITE_LANGGRAPH_ASSISTANT_ID?.trim() || "agent";

export const UI_URL =
  import.meta.env.VITE_UI_URL?.trim() || "http://localhost:5173";

export const GRAPH_RUN_CONFIG = { recursion_limit: 100 };
