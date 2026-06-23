/**
 * Local / deployed connection settings.
 *
 * Local dev (root .env via Vite envDir):
 *   VITE_LANGGRAPH_API_URL=http://127.0.0.1:2024
 *
 * Vercel production — set in Project → Environment Variables:
 *   VITE_LANGGRAPH_API_URL=https://<your-railway-app>.up.railway.app
 *   (aliases: VITE_API_URL, NEXT_PUBLIC_API_URL)
 *
 * Leave empty locally to use Vite proxy /api → LANGGRAPH_PORT
 */
function readApiUrl(): string {
  const candidates = [
    import.meta.env.VITE_LANGGRAPH_API_URL,
    import.meta.env.VITE_API_URL,
    import.meta.env.NEXT_PUBLIC_API_URL,
  ];
  for (const value of candidates) {
    const trimmed = value?.trim();
    if (trimmed) return trimmed;
  }
  return "";
}

export const LANGGRAPH_API_URL = readApiUrl() || "/api";

export const ASSISTANT_ID =
  import.meta.env.VITE_LANGGRAPH_ASSISTANT_ID?.trim() || "agent";

export const UI_URL =
  import.meta.env.VITE_UI_URL?.trim() || "http://localhost:5173";

export const GRAPH_RUN_CONFIG = { recursion_limit: 100 };
