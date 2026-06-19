/// <reference types="vite/client" />

interface ImportMetaEnv {
  readonly VITE_LANGGRAPH_API_URL: string;
  readonly VITE_LANGGRAPH_ASSISTANT_ID: string;
  readonly VITE_UI_URL: string;
  readonly VITE_DEFAULT_CHANNEL_NAME: string;
  readonly VITE_DEFAULT_CHANNEL_URL: string;
}

interface ImportMeta {
  readonly env: ImportMetaEnv;
}
