import type { AgentState, StepState, StepStatus } from "../types";
import { detailForNode, stepIdForNode, WORKFLOW_STEPS } from "./workflowSteps";

export interface ThreadSnapshot {
  values?: AgentState;
  next?: string[];
  tasks?: Array<{ name: string; result?: unknown; error?: string | null }>;
}

export function normalizeStreamEvent(raw: string): string {
  return raw.split("|")[0]?.trim() ?? raw;
}

export function normalizeNodeName(raw: string): string {
  const base = raw.split("|")[0]?.trim() ?? raw;
  return base.replace(/^graph:/, "");
}

function stepIndex(stepId: string): number {
  return WORKFLOW_STEPS.findIndex((s) => s.id === stepId);
}

export function markStepRunning(steps: StepState[], stepId: string, detail?: string): StepState[] {
  return steps.map((step) => {
    if (step.id === stepId) {
      return {
        ...step,
        status: "running" as StepStatus,
        detail: detail ?? step.detail,
        startedAt: step.startedAt ?? new Date().toISOString(),
      };
    }
    return step;
  });
}

export function markStepCompleted(
  steps: StepState[],
  stepId: string,
  detail?: string,
): StepState[] {
  const idx = stepIndex(stepId);
  return steps.map((step, i) => {
    if (step.id === stepId) {
      return {
        ...step,
        status: "completed" as StepStatus,
        detail: detail ?? step.detail,
        completedAt: new Date().toISOString(),
      };
    }
    if (idx >= 0 && i === idx + 1 && step.status === "pending") {
      return {
        ...step,
        status: "running" as StepStatus,
        startedAt: new Date().toISOString(),
        detail: "Starting…",
      };
    }
    return step;
  });
}

export function markStepSkipped(steps: StepState[], stepId: string, detail: string): StepState[] {
  return steps.map((step) =>
    step.id === stepId
      ? {
          ...step,
          status: "skipped" as StepStatus,
          detail,
          completedAt: step.completedAt ?? new Date().toISOString(),
        }
      : step,
  );
}

export function startPipeline(steps: StepState[]): StepState[] {
  if (!WORKFLOW_STEPS.length) return steps;
  return markStepRunning(steps, WORKFLOW_STEPS[0].id, "Agent booting…");
}

export function progressPercent(steps: StepState[]): number {
  const total = WORKFLOW_STEPS.length;
  if (!total) return 0;
  const completed = steps.filter((s) => s.status === "completed" || s.status === "skipped").length;
  const running = steps.some((s) => s.status === "running") ? 0.5 : 0;
  return Math.min(100, Math.round(((completed + running) / total) * 100));
}

export function applyNodeStart(steps: StepState[], nodeName: string): StepState[] {
  const stepId = stepIdForNode(normalizeNodeName(nodeName));
  if (!stepId) return steps;
  return markStepRunning(steps, stepId, "In progress…");
}

/** Track per-graph-node completion; only mark UI step done when all its nodes finished. */
export function recordNodeComplete(
  steps: StepState[],
  nodeName: string,
  detail: string,
  completedNodes: Set<string>,
): StepState[] {
  const normalized = normalizeNodeName(nodeName);
  if (!normalized) return steps;
  completedNodes.add(normalized);

  const stepId = stepIdForNode(normalized);
  if (!stepId) return steps;

  const def = WORKFLOW_STEPS.find((s) => s.id === stepId);
  if (!def) return markStepCompleted(steps, stepId, detail);

  const doneCount = def.nodes.filter((n) => completedNodes.has(n)).length;
  if (def.nodes.every((n) => completedNodes.has(n))) {
    return markStepCompleted(steps, stepId, detail);
  }
  return markStepRunning(steps, stepId, `${doneCount}/${def.nodes.length} — ${detail}`);
}

export function parseEventNodeName(data: unknown): string | null {
  if (!data || typeof data !== "object") return null;
  const evt = data as Record<string, unknown>;
  const metadata = evt.metadata as Record<string, unknown> | undefined;
  const fromMeta = metadata?.langgraph_node;
  if (typeof fromMeta === "string" && fromMeta) return fromMeta;
  if (typeof evt.name === "string" && evt.name) return evt.name;
  return null;
}

/** Node return payload from LangGraph `events` stream (`on_chain_end`). */
export function parseEventNodeOutput(data: unknown): Record<string, unknown> {
  if (!data || typeof data !== "object") return {};
  const evt = data as Record<string, unknown>;
  const payload = evt.data;
  if (!payload || typeof payload !== "object") return {};
  const record = payload as Record<string, unknown>;
  const output = record.output;
  if (output && typeof output === "object" && !Array.isArray(output)) {
    return output as Record<string, unknown>;
  }
  return record;
}

export function isChainStartEvent(data: unknown): boolean {
  if (!data || typeof data !== "object") return false;
  const evt = data as Record<string, unknown>;
  return evt.event === "on_chain_start" || evt.event === "on_tool_start";
}

export function isChainEndEvent(data: unknown): boolean {
  if (!data || typeof data !== "object") return false;
  const evt = data as Record<string, unknown>;
  return evt.event === "on_chain_end" || evt.event === "on_tool_end";
}

function stats(state: AgentState) {
  return state.reply_statistics ?? {};
}

function isPostingDisabled(s: Record<string, number>): boolean {
  const flag = (s as Record<string, unknown>).posting_enabled;
  return flag === false || flag === 0 || flag === "false";
}

/** Whether a graph node has finished based on accumulated LangGraph state. */
export function isNodeComplete(nodeName: string, state: AgentState): boolean {
  const s = stats(state);
  switch (nodeName) {
    case "prepare_agent":
      return Boolean(
        state.agent_route ||
          state.task_plan_summary ||
          state.youtube_channel_name ||
          state.youtube_channel_url ||
          (state.messages && state.messages.length > 0),
      );
    case "decide_agent":
      return Boolean(state.task_plan_summary || state.agent_route);
    case "login_youtube":
      return state.logged_in === true || state.logged_in === false;
    case "fetch_channel_data":
      return Boolean(state.latest_video || state.video_metadata || state.comments);
    case "analyze_comments":
      return Array.isArray(state.analyzed_comments);
    case "select_reply_targets":
      return s.reply_targets_selected != null || Array.isArray(state.reply_targets);
    case "generate_replies":
      return s.replies_generated != null || Array.isArray(state.generated_replies);
    case "post_replies":
      return s.replies_posted != null;
    case "generate_new_comment":
      return Array.isArray(state.generated_new_comments) || s.new_comments_generated != null;
    case "post_new_comment":
      return s.new_comments_posted != null;
    case "generate_html_report":
      return Boolean(state.html_path);
    case "generate_pdf_report":
      return Boolean(state.pdf_path);
    case "email_report":
      return Boolean(state.email_result);
    case "execute_workflow":
      return Boolean(state.html_path || state.comments || state.task_plan_summary);
    default:
      return false;
  }
}

/** Human-readable detail for a completed node derived from full graph state. */
export function stateDetailForNode(nodeName: string, state: AgentState): string {
  const s = stats(state);
  switch (nodeName) {
    case "prepare_agent":
      return "Channel config loaded";
    case "decide_agent":
      return state.task_plan_summary ? String(state.task_plan_summary) : "Route selected";
    case "login_youtube":
      if (state.logged_in === true) {
        return state.youtube_login_detail ?? "✅ YouTube signed in — session active";
      }
      return "❌ YouTube login check failed";
    case "fetch_channel_data": {
      const count = state.comments?.length ?? 0;
      const video = state.latest_video ?? state.video_metadata;
      const title = video?.title ? ` from "${video.title}"` : "";
      return `📥 ${count} comments scraped${title}`;
    }
    case "analyze_comments": {
      const count = state.analyzed_comments?.length ?? 0;
      const positive = state.positive_comments?.length ?? 0;
      return `🔍 ${count} analyzed (${positive} positive)`;
    }
    case "select_reply_targets": {
      const n = state.reply_targets?.length ?? s.reply_targets_selected ?? 0;
      return n > 0 ? `🎯 ${n} reply target(s) selected` : "🎯 No eligible positive targets";
    }
    case "generate_replies": {
      const n = s.replies_generated ?? state.generated_replies?.length ?? 0;
      const personality = s.reply_personality ?? "humorous";
      return `✍️ ${n} ${personality} reply draft(s) ready`;
    }
    case "post_replies": {
      const posted = s.replies_posted ?? 0;
      const failed = s.replies_failed ?? 0;
      if (posted === 0 && failed === 0 && isPostingDisabled(s)) {
        return "💬 Posting disabled — replies saved in report";
      }
      return `💬 ${posted} posted, ${failed} failed`;
    }
    case "generate_new_comment": {
      const n = state.generated_new_comments?.length ?? s.new_comments_generated ?? 0;
      return n > 0 ? `📝 ${n} new comment draft(s)` : "📝 New comment step finished";
    }
    case "post_new_comment": {
      const posted = s.new_comments_posted ?? 0;
      const failed = s.new_comments_failed ?? 0;
      if (posted === 0 && failed === 0) {
        return "📝 New comment posting skipped or disabled";
      }
      return `📝 ${posted} posted, ${failed} failed`;
    }
    case "generate_html_report":
      return state.html_path ? `📊 ${state.html_path}` : "📊 HTML dashboard ready";
    case "generate_pdf_report":
      return state.pdf_path ? `📄 ${state.pdf_path}` : "📄 PDF report ready";
    case "email_report":
      return state.email_result
        ? `📧 ${String(state.email_result).slice(0, 120)}`
        : "📧 Email step finished";
    case "execute_workflow":
      return "Full workflow executed in batch mode";
    default:
      return detailForNode(nodeName, state as unknown as Record<string, unknown>);
  }
}

function stepIsDone(stepId: string, completedNodes: Set<string>): boolean {
  const def = WORKFLOW_STEPS.find((s) => s.id === stepId);
  if (!def) return false;
  return def.nodes.every((n) => completedNodes.has(n));
}

function workflowProgressedPastReplies(state: AgentState): boolean {
  return Boolean(state.html_path || state.pdf_path || state.email_result);
}

/** Mark optional steps the graph routed around (never executed). */
export function inferSkippedFromRouting(
  steps: StepState[],
  state: AgentState,
  completedNodes: Set<string>,
): StepState[] {
  const s = stats(state);
  const genDone = s.replies_generated != null || Array.isArray(state.generated_replies);
  const pastReplies = workflowProgressedPastReplies(state);

  let next = steps;

  const maybeSkip = (stepId: string, detail: string) => {
    const step = next.find((item) => item.id === stepId);
    if (!step || (step.status !== "pending" && step.status !== "running")) return;
    if (stepIsDone(stepId, completedNodes)) return;
    next = markStepSkipped(next, stepId, detail);
    const def = WORKFLOW_STEPS.find((item) => item.id === stepId);
    def?.nodes.forEach((node) => completedNodes.add(node));
  };

  if (genDone && s.replies_posted == null) {
    if (isPostingDisabled(s)) {
      maybeSkip("post_replies", "Posting disabled in settings");
    } else if ((state.generated_replies?.length ?? 0) === 0) {
      maybeSkip("post_replies", "No replies generated to post");
    } else if (pastReplies) {
      maybeSkip("post_replies", "Skipped by workflow routing");
    }
  }

  if (pastReplies && s.new_comments_posted == null && !completedNodes.has("generate_new_comment")) {
    maybeSkip("new_comment", "New comments disabled");
  }

  if (pastReplies && !state.pdf_path && state.html_path) {
    maybeSkip("pdf_report", "PDF not generated for this run");
  }

  if (pastReplies && !state.email_result && (state.pdf_path || state.html_path)) {
    maybeSkip("email", "Email not sent for this run");
  }

  return next;
}

function activeStepHint(stepId: string): string {
  switch (stepId) {
    case "login":
      return "🔐 Verifying YouTube session…";
    case "fetch":
      return "📥 Scraping comments from latest video…";
    case "analyze":
      return "🔍 Classifying comment sentiment…";
    case "select":
      return "🎯 Selecting top positive reply targets…";
    case "generate_replies":
      return "✍️ Generating AI replies…";
    case "post_replies":
      return "💬 Posting replies on YouTube…";
    case "new_comment":
      return "📝 Working on new video comment…";
    case "html_report":
      return "📊 Building HTML dashboard…";
    case "pdf_report":
      return "📄 Generating PDF report…";
    case "email":
      return "📧 Sending email report…";
    default:
      return "In progress…";
  }
}

function markActiveStep(steps: StepState[], completedNodes: Set<string>): StepState[] {
  for (const def of WORKFLOW_STEPS) {
    const step = steps.find((s) => s.id === def.id);
    if (!step) continue;
    if (step.status === "completed" || step.status === "skipped") continue;
    if (stepIsDone(def.id, completedNodes)) continue;
    return markStepRunning(steps, def.id, activeStepHint(def.id));
  }
  return steps;
}

function markRunningFromNextNodes(steps: StepState[], nextNodes: string[]): StepState[] {
  if (!nextNodes.length) return steps;
  for (const raw of nextNodes) {
    const stepId = stepIdForNode(normalizeNodeName(raw));
    if (stepId) {
      return markStepRunning(steps, stepId, activeStepHint(stepId));
    }
  }
  return steps;
}

/** Sync every pipeline step from accumulated graph state (values stream fallback). */
export function syncPipelineFromState(
  steps: StepState[],
  state: AgentState,
  completedNodes: Set<string>,
  nextNodes?: string[],
): StepState[] {
  let next = steps;

  for (const def of WORKFLOW_STEPS) {
    for (const node of def.nodes) {
      if (!isNodeComplete(node, state)) continue;
      next = recordNodeComplete(next, node, stateDetailForNode(node, state), completedNodes);
    }
  }

  next = inferSkippedFromRouting(next, state, completedNodes);
  if (nextNodes && nextNodes.length > 0) {
    next = markRunningFromNextNodes(next, nextNodes);
  } else {
    next = markActiveStep(next, completedNodes);
  }
  return next;
}

/** Apply state sync + routing skips at end of run (no forced completion). */
export function finalizePipeline(
  steps: StepState[],
  state: AgentState,
  completedNodes: Set<string>,
  nextNodes?: string[],
): StepState[] {
  return inferSkippedFromRouting(
    syncPipelineFromState(steps, state, completedNodes, nextNodes),
    state,
    completedNodes,
  );
}

export function applyNodeComplete(
  steps: StepState[],
  nodeName: string,
  detail: string,
  completedNodes: Set<string>,
): StepState[] {
  return recordNodeComplete(steps, nodeName, detail, completedNodes);
}

/** Merge LangGraph thread snapshot (poll or stream) into pipeline steps. */
export function syncFromThreadState(
  steps: StepState[],
  state: AgentState,
  completedNodes: Set<string>,
  thread: ThreadSnapshot,
): { steps: StepState[]; state: AgentState } {
  let merged = { ...state, ...(thread.values ?? {}) } as AgentState;
  let next = steps;

  for (const task of thread.tasks ?? []) {
    const node = normalizeNodeName(task.name);
    if (!node || (task.result == null && !task.error)) continue;
    const payload =
      task.result && typeof task.result === "object" && !Array.isArray(task.result)
        ? (task.result as Record<string, unknown>)
        : {};
    merged = { ...merged, ...payload } as AgentState;
    next = recordNodeComplete(
      next,
      node,
      detailForNode(node, { ...merged, ...payload }),
      completedNodes,
    );
  }

  next = syncPipelineFromState(next, merged, completedNodes, thread.next ?? []);
  return { steps: next, state: merged };
}

/** Merge node update payload with accumulated state for richer step details. */
export function payloadForNode(
  _nodeName: string,
  nodeUpdate: Record<string, unknown>,
  state: AgentState,
): Record<string, unknown> {
  return { ...state, ...nodeUpdate };
}
