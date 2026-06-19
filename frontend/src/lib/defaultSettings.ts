import type { AgentRunSettings } from "../types";

function envBool(key: string, fallback: boolean): boolean {
  const raw = import.meta.env[key];
  if (raw == null || String(raw).trim() === "") return fallback;
  const value = String(raw).trim().toLowerCase();
  return ["1", "true", "yes", "on"].includes(value);
}

function envInt(key: string, fallback: number): number {
  const raw = import.meta.env[key];
  if (raw == null || String(raw).trim() === "") return fallback;
  const parsed = Number(raw);
  return Number.isFinite(parsed) ? parsed : fallback;
}

function envStr(key: string, fallback: string): string {
  const raw = import.meta.env[key];
  return raw != null && String(raw).trim() !== "" ? String(raw).trim() : fallback;
}

/** Pre-fill run settings from root `.env` (VITE_DEFAULT_* or mirrored backend keys). */
export function defaultRunSettings(): AgentRunSettings {
  return {
    channelName: envStr("VITE_DEFAULT_CHANNEL_NAME", ""),
    channelUrl: envStr("VITE_DEFAULT_CHANNEL_URL", ""),
    maxVideosToScan: envInt("VITE_DEFAULT_MAX_VIDEOS_TO_SCAN", 1),
    maxCommentsPerVideo: envInt("VITE_DEFAULT_MAX_COMMENTS_PER_VIDEO", 0),
    maxReplies: envInt("VITE_DEFAULT_MAX_REPLIES", 5),
    replyPersonality: envStr("VITE_DEFAULT_REPLY_PERSONALITY", "humorous"),
    enableCommentReplies: envBool("VITE_DEFAULT_ENABLE_COMMENT_REPLIES", true),
    enableNewComments: envBool("VITE_DEFAULT_ENABLE_NEW_COMMENTS", false),
    newCommentText: envStr("VITE_DEFAULT_NEW_COMMENT_TEXT", ""),
    maxNewComments: envInt("VITE_DEFAULT_MAX_NEW_COMMENTS", 1),
    keepBrowserOpen: envBool("VITE_DEFAULT_KEEP_BROWSER_OPEN", true),
    replyToPositive: envBool("VITE_DEFAULT_REPLY_TO_POSITIVE", true),
    replyToNegative: envBool("VITE_DEFAULT_REPLY_TO_NEGATIVE", false),
    replyToNeutral: envBool("VITE_DEFAULT_REPLY_TO_NEUTRAL", false),
    replyToQuestions: envBool("VITE_DEFAULT_REPLY_TO_QUESTIONS", true),
    replyToSuggestions: envBool("VITE_DEFAULT_REPLY_TO_SUGGESTIONS", true),
    replyToSpam: envBool("VITE_DEFAULT_REPLY_TO_SPAM", false),
    emailReports: envBool("VITE_DEFAULT_EMAIL_REPORTS", true),
    emailRecipient:
      envStr("VITE_DEFAULT_EMAIL_RECIPIENT", "") ||
      envStr("VITE_GMAIL_DEFAULT_RECIPIENT", ""),
  };
}

export const REPLY_PERSONALITY_OPTIONS = [
  "humorous",
  "friendly",
  "professional",
  "enthusiastic",
] as const;
