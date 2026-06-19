import path from "node:path";
import { fileURLToPath } from "node:url";
import { defineConfig, loadEnv } from "vite";
import react from "@vitejs/plugin-react";

const rootDir = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "..");

/** Mirror backend .env keys into VITE_DEFAULT_* when the Vite key is unset. */
const BACKEND_TO_VITE_DEFAULT: [string, string][] = [
  ["YOUTUBE_CHANNEL_NAME", "VITE_DEFAULT_CHANNEL_NAME"],
  ["YOUTUBE_CHANNEL_URL", "VITE_DEFAULT_CHANNEL_URL"],
  ["MAX_VIDEOS_TO_SCAN", "VITE_DEFAULT_MAX_VIDEOS_TO_SCAN"],
  ["MAX_COMMENTS_PER_VIDEO", "VITE_DEFAULT_MAX_COMMENTS_PER_VIDEO"],
  ["MAX_REPLIES_PER_VIDEO", "VITE_DEFAULT_MAX_REPLIES"],
  ["REPLY_PERSONALITY", "VITE_DEFAULT_REPLY_PERSONALITY"],
  ["ENABLE_COMMENT_REPLIES", "VITE_DEFAULT_ENABLE_COMMENT_REPLIES"],
  ["ENABLE_NEW_COMMENTS", "VITE_DEFAULT_ENABLE_NEW_COMMENTS"],
  ["NEW_COMMENT_TEXT", "VITE_DEFAULT_NEW_COMMENT_TEXT"],
  ["MAX_NEW_COMMENTS", "VITE_DEFAULT_MAX_NEW_COMMENTS"],
  ["KEEP_BROWSER_OPEN", "VITE_DEFAULT_KEEP_BROWSER_OPEN"],
  ["REPLY_TO_POSITIVE", "VITE_DEFAULT_REPLY_TO_POSITIVE"],
  ["REPLY_TO_NEGATIVE", "VITE_DEFAULT_REPLY_TO_NEGATIVE"],
  ["REPLY_TO_NEUTRAL", "VITE_DEFAULT_REPLY_TO_NEUTRAL"],
  ["REPLY_TO_QUESTIONS", "VITE_DEFAULT_REPLY_TO_QUESTIONS"],
  ["REPLY_TO_SUGGESTIONS", "VITE_DEFAULT_REPLY_TO_SUGGESTIONS"],
  ["REPLY_TO_SPAM", "VITE_DEFAULT_REPLY_TO_SPAM"],
  ["EMAIL_REPORTS", "VITE_DEFAULT_EMAIL_REPORTS"],
  ["GMAIL_DEFAULT_RECIPIENT", "VITE_DEFAULT_EMAIL_RECIPIENT"],
];

function mirrorBackendEnvDefaults(env: Record<string, string>) {
  for (const [backendKey, viteKey] of BACKEND_TO_VITE_DEFAULT) {
    const backendValue = env[backendKey]?.trim();
    const viteValue = env[viteKey]?.trim();
    if (!viteValue && backendValue) {
      env[viteKey] = backendValue;
      process.env[viteKey] = backendValue;
    }
  }
}

export default defineConfig(({ mode }) => {
  const env = loadEnv(mode, rootDir, "");
  mirrorBackendEnvDefaults(env);
  const langgraphPort = env.LANGGRAPH_PORT || "2024";
  const frontendPort = Number(env.FRONTEND_PORT || "5173");

  return {
    envDir: rootDir,
    plugins: [react()],
    server: {
      port: frontendPort,
      strictPort: true,
      proxy: {
        "/api": {
          target: `http://127.0.0.1:${langgraphPort}`,
          changeOrigin: true,
          rewrite: (path) => path.replace(/^\/api/, ""),
        },
      },
    },
    preview: {
      port: frontendPort,
    },
  };
});
