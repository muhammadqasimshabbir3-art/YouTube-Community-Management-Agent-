import type { AgentRunSettings } from "../types";
import { defaultRunSettings } from "./defaultSettings";

const STORAGE_KEY = "yt-agent-run-settings";

export function loadRunSettings(): AgentRunSettings {
  const defaults = defaultRunSettings();
  try {
    const raw = localStorage.getItem(STORAGE_KEY) ?? sessionStorage.getItem(STORAGE_KEY);
    if (!raw) return defaults;
    const parsed = JSON.parse(raw) as Partial<AgentRunSettings>;
    return { ...defaults, ...parsed };
  } catch {
    return defaults;
  }
}

export function saveRunSettings(settings: AgentRunSettings): void {
  const raw = JSON.stringify(settings);
  try {
    localStorage.setItem(STORAGE_KEY, raw);
    sessionStorage.setItem(STORAGE_KEY, raw);
  } catch {
    // ignore quota / private mode
  }
}
