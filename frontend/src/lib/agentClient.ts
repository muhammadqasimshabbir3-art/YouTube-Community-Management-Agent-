/**
 * Connection layer: UI → LangGraph Server API
 */
import { Client } from "@langchain/langgraph-sdk";
import { ASSISTANT_ID, GRAPH_RUN_CONFIG, LANGGRAPH_API_URL } from "../config";
import type { RunRequest } from "../types";

let client: Client | null = null;

export function getAgentClient(): Client {
  if (!client) {
    client = new Client({ apiUrl: LANGGRAPH_API_URL });
  }
  return client;
}

export async function checkAgentHealth(): Promise<{ ok: boolean; latencyMs: number }> {
  const start = performance.now();
  try {
    const res = await fetch(`${LANGGRAPH_API_URL}/ok`, { method: "GET" });
    return { ok: res.ok, latencyMs: Math.round(performance.now() - start) };
  } catch {
    return { ok: false, latencyMs: 0 };
  }
}

export function buildAgentInput(request: RunRequest) {
  const name = request.channelName.trim();
  const url = request.channelUrl.trim();
  let prompt = "Analyze YouTube channel latest video comments";
  if (name) prompt += ` for ${name}`;
  if (url) prompt += ` (${url})`;
  if (request.emailReports) {
    prompt += " and generate PDF report and email it";
  } else {
    prompt += " and generate HTML dashboard report";
  }

  return {
    messages: [],
    user_input: prompt,
    youtube_channel_url: url,
    youtube_channel_name: name,
    workflow_action: request.emailReports ? "email" : "analyze",
    max_videos_to_scan: request.maxVideosToScan,
    max_comments_per_video: request.maxCommentsPerVideo,
    max_replies_per_video: request.maxReplies,
    reply_personality: request.replyPersonality,
    enable_comment_replies: request.enableCommentReplies,
    enable_new_comments: request.enableNewComments,
    new_comment_text: request.newCommentText,
    max_new_comments: request.maxNewComments,
    keep_browser_open: request.keepBrowserOpen,
    reply_to_positive: request.replyToPositive,
    reply_to_negative: request.replyToNegative,
    reply_to_neutral: request.replyToNeutral,
    reply_to_questions: request.replyToQuestions,
    reply_to_suggestions: request.replyToSuggestions,
    reply_to_spam: request.replyToSpam,
    email_reports: request.emailReports,
    email_recipient: request.emailRecipient.trim(),
  };
}

export async function fetchThreadState(threadId: string) {
  const agent = getAgentClient();
  return agent.threads.getState(threadId);
}

export async function fetchRun(threadId: string, runId: string) {
  const agent = getAgentClient();
  return agent.runs.get(threadId, runId);
}

const ACTIVE_RUN_STATUSES = new Set(["pending", "running"]);

/** Find the newest still-active run on a thread (used after refresh when runId was not saved). */
export async function fetchLatestActiveRun(threadId: string): Promise<string | null> {
  const agent = getAgentClient();
  try {
    const runs = await agent.runs.list(threadId, { limit: 10 });
    const active = runs.find((run) => ACTIVE_RUN_STATUSES.has(run.status));
    return active?.run_id ?? null;
  } catch {
    return null;
  }
}

export async function isRunStillActive(threadId: string, runId: string | null): Promise<boolean> {
  try {
    const thread = await fetchThreadState(threadId);
    if ((thread.next?.length ?? 0) > 0) return true;
    if (!runId) {
      const latest = await fetchLatestActiveRun(threadId);
      if (!latest) return false;
      runId = latest;
    }
    const run = await fetchRun(threadId, runId);
    return ACTIVE_RUN_STATUSES.has(run.status);
  } catch {
    return false;
  }
}

export function joinRunStream(
  threadId: string,
  runId: string,
  signal?: AbortSignal,
) {
  const agent = getAgentClient();
  return agent.runs.joinStream(threadId, runId, {
    streamMode: ["updates", "values", "events"],
    cancelOnDisconnect: false,
    signal,
  });
}

export async function streamAgentRun(
  input: ReturnType<typeof buildAgentInput>,
  signal?: AbortSignal,
) {
  const agent = getAgentClient();
  const thread = await agent.threads.create();
  // Create the run first so we have run_id immediately (survives browser refresh).
  const run = await agent.runs.create(thread.thread_id, ASSISTANT_ID, {
    input,
    config: GRAPH_RUN_CONFIG,
    streamMode: ["updates", "values", "events"],
    onDisconnect: "continue",
  });
  const stream = agent.runs.joinStream(thread.thread_id, run.run_id, {
    streamMode: ["updates", "values", "events"],
    cancelOnDisconnect: false,
    signal,
  });
  return { threadId: thread.thread_id, runId: run.run_id, stream };
}
