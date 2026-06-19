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

export async function streamAgentRun(
  input: ReturnType<typeof buildAgentInput>,
  signal?: AbortSignal,
) {
  const agent = getAgentClient();
  const thread = await agent.threads.create();
  const stream = agent.runs.stream(thread.thread_id, ASSISTANT_ID, {
    input,
    config: GRAPH_RUN_CONFIG,
    streamMode: ["updates", "values", "events"],
    signal,
  });
  return { threadId: thread.thread_id, stream };
}
