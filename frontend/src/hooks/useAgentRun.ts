import { useCallback, useEffect, useRef, useState } from "react";
import { flushSync } from "react-dom";
import { buildAgentInput, fetchThreadState, streamAgentRun } from "../lib/agentClient";
import {
  applyNodeStart,
  finalizePipeline,
  isChainEndEvent,
  isChainStartEvent,
  normalizeNodeName,
  normalizeStreamEvent,
  parseEventNodeName,
  parseEventNodeOutput,
  payloadForNode,
  recordNodeComplete,
  startPipeline,
  syncFromThreadState,
  syncPipelineFromState,
} from "../lib/streamProgress";
import {
  detailForNode,
  initialStepStates,
  stepIdForNode,
  WORKFLOW_STEPS,
} from "../lib/workflowSteps";
import type { AgentState, LogEntry, RunRequest, StepState, StepStatus } from "../types";

const POLL_MS = 1500;

function nowIso() {
  return new Date().toISOString();
}

function makeLog(level: LogEntry["level"], message: string): LogEntry {
  return {
    id: `${Date.now()}-${Math.random().toString(36).slice(2, 8)}`,
    time: new Date().toLocaleTimeString(),
    level,
    message,
  };
}

function markBundledWorkflowComplete(
  steps: StepState[],
  state: AgentState,
  completedNodes: Set<string>,
): StepState[] {
  let next = steps;
  for (const def of WORKFLOW_STEPS) {
    for (const node of def.nodes) {
      completedNodes.add(node);
    }
    next = next.map((step) =>
      step.id === def.id
        ? {
            ...step,
            status: "completed" as StepStatus,
            completedAt: nowIso(),
            detail:
              def.id === "prepare"
                ? state.task_plan_summary
                  ? String(state.task_plan_summary)
                  : "Batch workflow route"
                : "Completed via batch workflow",
          }
        : step,
    );
  }
  return next;
}

function publishSteps(setSteps: (s: StepState[]) => void, next: StepState[]) {
  flushSync(() => setSteps(next));
}

export function useAgentRun() {
  const abortRef = useRef<AbortController | null>(null);
  const pollRef = useRef<number | null>(null);
  const completedNodesRef = useRef<Set<string>>(new Set());
  const [running, setRunning] = useState(false);
  const [steps, setSteps] = useState<StepState[]>(initialStepStates());
  const [result, setResult] = useState<AgentState | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [logs, setLogs] = useState<LogEntry[]>([]);
  const [threadId, setThreadId] = useState<string | null>(null);
  const [runId, setRunId] = useState<string | null>(null);
  const [loggedIn, setLoggedIn] = useState<boolean | null>(null);

  const pushLog = useCallback((level: LogEntry["level"], message: string) => {
    flushSync(() => setLogs((prev) => [...prev, makeLog(level, message)]));
  }, []);

  const stopPolling = useCallback(() => {
    if (pollRef.current != null) {
      window.clearInterval(pollRef.current);
      pollRef.current = null;
    }
  }, []);

  const reset = useCallback(() => {
    abortRef.current?.abort();
    abortRef.current = null;
    stopPolling();
    completedNodesRef.current = new Set();
    setRunning(false);
    setSteps(initialStepStates());
    setResult(null);
    setError(null);
    setLogs([]);
    setThreadId(null);
    setRunId(null);
    setLoggedIn(null);
  }, [stopPolling]);

  const run = useCallback(
    async (request: RunRequest) => {
      const { channelName, channelUrl } = request;
      if (!channelName.trim() && !channelUrl.trim()) {
        setError("Enter a channel name or URL, or set YOUTUBE_CHANNEL_NAME in the backend .env");
        return;
      }

      abortRef.current?.abort();
      stopPolling();
      const abort = new AbortController();
      abortRef.current = abort;
      completedNodesRef.current = new Set();

      setRunning(true);
      setError(null);
      setResult(null);
      setLogs([]);
      setLoggedIn(null);
      publishSteps(setSteps, startPipeline(initialStepStates()));
      pushLog("info", "🚀 Starting agent workflow…");

      let stepSnapshot = startPipeline(initialStepStates());
      let latestState: AgentState = {};
      let latestNext: string[] = [];
      const startedNodes = new Set<string>();
      let activeThreadId: string | null = null;

      const applyLoggedIn = (state: AgentState) => {
        if (state.logged_in === true) setLoggedIn(true);
        if (state.logged_in === false) setLoggedIn(false);
      };

      const publishState = (state: AgentState, stepsToPublish: StepState[]) => {
        applyLoggedIn(state);
        latestState = state;
        stepSnapshot = stepsToPublish;
        flushSync(() => setResult(state));
        publishSteps(setSteps, stepsToPublish);
      };

      const refreshFromThread = async (threadId: string) => {
        if (abort.signal.aborted) return;
        try {
          const thread = await fetchThreadState(threadId);
          const synced = syncFromThreadState(
            stepSnapshot,
            latestState,
            completedNodesRef.current,
            {
              values: thread.values as AgentState,
              next: thread.next ?? [],
              tasks: thread.tasks ?? [],
            },
          );
          latestNext = thread.next ?? [];
          publishState(synced.state, synced.steps);
        } catch {
          // polling is best-effort while the graph is busy
        }
      };

      const handleNodeComplete = (nodeName: string, payload: Record<string, unknown>) => {
        const normalized = normalizeNodeName(nodeName);
        const merged = payloadForNode(normalized, payload, latestState);
        const detail = detailForNode(normalized, merged);
        pushLog("info", `✅ ${normalized}: ${detail}`);
        if (merged.logged_in === true && normalized === "login_youtube") {
          pushLog("success", "🔐 YouTube login confirmed");
        }
        stepSnapshot = recordNodeComplete(
          stepSnapshot,
          normalized,
          detail,
          completedNodesRef.current,
        );
        const synced = syncPipelineFromState(
          stepSnapshot,
          merged as AgentState,
          completedNodesRef.current,
          latestNext,
        );
        publishState(merged as AgentState, synced);
      };

      try {
        const input = buildAgentInput(request);
        const { threadId: createdThreadId, stream } = await streamAgentRun(input, abort.signal);
        activeThreadId = createdThreadId;
        setThreadId(createdThreadId);
        pushLog("info", `🧵 Thread ${createdThreadId.slice(0, 8)}…`);

        pollRef.current = window.setInterval(() => {
          if (activeThreadId) void refreshFromThread(activeThreadId);
        }, POLL_MS);

        for await (const chunk of stream) {
          if (abort.signal.aborted) break;

          const event = normalizeStreamEvent(String(chunk.event ?? ""));

          if (event === "metadata") {
            const meta = chunk.data as { run_id?: string } | undefined;
            if (meta?.run_id) setRunId(String(meta.run_id));
          }

          if (event === "error") {
            const errData = chunk.data as { message?: string; error?: string };
            throw new Error(errData?.message || errData?.error || "Agent stream error");
          }

          if (event === "events") {
            if (isChainStartEvent(chunk.data)) {
              const nodeName = normalizeNodeName(parseEventNodeName(chunk.data) ?? "");
              if (nodeName && !startedNodes.has(nodeName)) {
                startedNodes.add(nodeName);
                stepSnapshot = applyNodeStart(stepSnapshot, nodeName);
                publishSteps(setSteps, stepSnapshot);
                pushLog("info", `▶️ ${nodeName}`);
              }
            }
            if (isChainEndEvent(chunk.data)) {
              const nodeName = normalizeNodeName(parseEventNodeName(chunk.data) ?? "");
              const stepId = stepIdForNode(nodeName);
              if (nodeName && stepId) {
                const nodeOutput = parseEventNodeOutput(chunk.data);
                const payload =
                  Object.keys(nodeOutput).length > 0
                    ? nodeOutput
                    : (latestState as Record<string, unknown>);
                handleNodeComplete(nodeName, payload);
              }
            }
          }

          if (event === "updates" && chunk.data && typeof chunk.data === "object") {
            for (const [rawNode, nodeUpdate] of Object.entries(chunk.data)) {
              const nodeName = normalizeNodeName(rawNode);

              if (nodeName === "execute_workflow") {
                stepSnapshot = markBundledWorkflowComplete(
                  stepSnapshot,
                  { ...latestState, ...(nodeUpdate as AgentState) },
                  completedNodesRef.current,
                );
                publishSteps(setSteps, stepSnapshot);
                continue;
              }

              if (stepIdForNode(nodeName)) {
                handleNodeComplete(nodeName, nodeUpdate as Record<string, unknown>);
              }
            }
          }

          if (event === "values" && chunk.data) {
            latestState = chunk.data as AgentState;
            const synced = syncPipelineFromState(
              stepSnapshot,
              latestState,
              completedNodesRef.current,
              latestNext,
            );
            publishState(latestState, synced);
          }

          if (activeThreadId) {
            void refreshFromThread(activeThreadId);
          }
        }

        if (activeThreadId) {
          await refreshFromThread(activeThreadId);
        }

        stepSnapshot = finalizePipeline(
          stepSnapshot,
          latestState,
          completedNodesRef.current,
          latestNext,
        );
        publishSteps(setSteps, stepSnapshot);
        setResult(latestState);
        pushLog("success", "🎉 Workflow finished");
      } catch (err) {
        if (abort.signal.aborted) {
          pushLog("warn", "⏹️ Run stopped");
        } else {
          const message = err instanceof Error ? err.message : String(err);
          setError(message);
          pushLog("error", message);
          publishSteps(
            setSteps,
            stepSnapshot.map((s) =>
              s.status === "running" ? { ...s, status: "error", detail: message } : s,
            ),
          );
        }
      } finally {
        stopPolling();
        setRunning(false);
        abortRef.current = null;
      }
    },
    [pushLog, stopPolling],
  );

  const cancel = useCallback(() => {
    abortRef.current?.abort();
    stopPolling();
    setRunning(false);
    pushLog("warn", "⏹️ Stopping agent…");
  }, [pushLog, stopPolling]);

  useEffect(() => () => {
    abortRef.current?.abort();
    stopPolling();
  }, [stopPolling]);

  return { running, steps, result, error, logs, threadId, runId, loggedIn, run, cancel, reset };
}
