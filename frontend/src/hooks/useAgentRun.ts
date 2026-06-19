import { useCallback, useEffect, useRef, useState } from "react";
import { flushSync } from "react-dom";
import {
  buildAgentInput,
  fetchLatestActiveRun,
  fetchRun,
  fetchThreadState,
  isRunStillActive,
  joinRunStream,
  streamAgentRun,
} from "../lib/agentClient";
import {
  clearRunSession,
  loadRunSession,
  saveRunSession,
} from "../lib/runSession";
import {
  buildPipelineFromState,
  finalizePipeline,
  isChainEndEvent,
  isChainStartEvent,
  normalizeNodeName,
  normalizeStreamEvent,
  parseEventNodeName,
  parseEventNodeOutput,
  payloadForNode,
  startPipeline,
  type ThreadSnapshot,
} from "../lib/streamProgress";
import {
  detailForNode,
  initialStepStates,
  stepIdForNode,
  WORKFLOW_STEPS,
} from "../lib/workflowSteps";
import type { AgentState, LogEntry, RunRequest, StepState, StepStatus } from "../types";

const POLL_MS = 1000;
const ACTIVE_RUN_STATUSES = new Set(["pending", "running"]);

function nowIso() {
  return new Date().toISOString();
}

function sleep(ms: number) {
  return new Promise((resolve) => window.setTimeout(resolve, ms));
}

function makeLog(level: LogEntry["level"], message: string): LogEntry {
  return {
    id: `${Date.now()}-${Math.random().toString(36).slice(2, 8)}`,
    time: new Date().toLocaleTimeString(),
    level,
    message,
  };
}

function hydrateFromSession() {
  const session = loadRunSession();
  if (!session?.threadId) {
    return {
      steps: initialStepStates(),
      result: null as AgentState | null,
      running: false,
      threadId: null as string | null,
      runId: null as string | null,
      loggedIn: null as boolean | null,
      reconnected: false,
    };
  }
  const state = session.partialState ?? null;
  return {
    steps: session.steps?.length ? session.steps : initialStepStates(),
    result: state,
    running: Boolean(session.running),
    threadId: session.threadId,
    runId: session.runId,
    loggedIn: state?.logged_in === true ? true : state?.logged_in === false ? false : null,
    reconnected: Boolean(session.reconnected),
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

async function resolveRunId(threadId: string, runId: string | null): Promise<string | null> {
  if (runId) return runId;
  return fetchLatestActiveRun(threadId);
}

export function useAgentRun() {
  const hydrated = hydrateFromSession();
  const abortRef = useRef<AbortController | null>(null);
  const pollRef = useRef<number | null>(null);
  const completedNodesRef = useRef<Set<string>>(new Set());
  const trackingRef = useRef(hydrated.running);
  const resumeLockRef = useRef(false);
  const threadIdRef = useRef<string | null>(hydrated.threadId);
  const runIdRef = useRef<string | null>(hydrated.runId);

  const [running, setRunning] = useState(hydrated.running);
  const [reconnected, setReconnected] = useState(hydrated.reconnected);
  const [steps, setSteps] = useState<StepState[]>(hydrated.steps);
  const [result, setResult] = useState<AgentState | null>(hydrated.result);
  const [error, setError] = useState<string | null>(null);
  const [logs, setLogs] = useState<LogEntry[]>([]);
  const [threadId, setThreadId] = useState<string | null>(hydrated.threadId);
  const [runId, setRunId] = useState<string | null>(hydrated.runId);
  const [loggedIn, setLoggedIn] = useState<boolean | null>(hydrated.loggedIn);

  const persistSession = useCallback(
    (patch: {
      threadId?: string | null;
      runId?: string | null;
      running?: boolean;
      steps?: StepState[];
      partialState?: AgentState | null;
      reconnected?: boolean;
    }) => {
      const tid = patch.threadId ?? threadIdRef.current;
      if (!tid) return;
      const rid = patch.runId !== undefined ? patch.runId : runIdRef.current;
      saveRunSession({
        threadId: tid,
        runId: rid,
        startedAt: nowIso(),
        running: patch.running ?? trackingRef.current,
        steps: patch.steps ?? undefined,
        partialState: patch.partialState ?? undefined,
        reconnected: patch.reconnected ?? undefined,
      });
    },
    [],
  );

  const pushLog = useCallback((level: LogEntry["level"], message: string) => {
    flushSync(() => setLogs((prev) => [...prev, makeLog(level, message)]));
  }, []);

  const stopPolling = useCallback(() => {
    if (pollRef.current != null) {
      window.clearInterval(pollRef.current);
      pollRef.current = null;
    }
  }, []);

  const applyLoggedIn = useCallback((state: AgentState) => {
    if (state.logged_in === true) setLoggedIn(true);
    if (state.logged_in === false) setLoggedIn(false);
  }, []);

  const publishFromState = useCallback(
    (state: AgentState, nextNodes: string[], thread: ThreadSnapshot = {}) => {
      const rebuilt = buildPipelineFromState(state, nextNodes, thread);
      completedNodesRef.current = rebuilt.completedNodes;
      applyLoggedIn(state);
      flushSync(() => setResult(state));
      publishSteps(setSteps, rebuilt.steps);
      persistSession({
        steps: rebuilt.steps,
        partialState: state,
        running: trackingRef.current,
      });
      return rebuilt;
    },
    [applyLoggedIn, persistSession],
  );

  const reset = useCallback(() => {
    abortRef.current?.abort();
    abortRef.current = null;
    stopPolling();
    trackingRef.current = false;
    completedNodesRef.current = new Set();
    threadIdRef.current = null;
    runIdRef.current = null;
    clearRunSession();
    setReconnected(false);
    setRunning(false);
    setSteps(initialStepStates());
    setResult(null);
    setError(null);
    setLogs([]);
    setThreadId(null);
    setRunId(null);
    setLoggedIn(null);
  }, [stopPolling]);

  const refreshThread = useCallback(
    async (activeThreadId: string, latestState: AgentState = {}) => {
      const thread = await fetchThreadState(activeThreadId);
      const merged = { ...latestState, ...(thread.values as AgentState) } as AgentState;
      const nextNodes = thread.next ?? [];
      publishFromState(merged, nextNodes, thread as ThreadSnapshot);
      return { state: merged, next: nextNodes, thread: thread as ThreadSnapshot };
    },
    [publishFromState],
  );

  const startPolling = useCallback(
    (activeThreadId: string) => {
      stopPolling();
      pollRef.current = window.setInterval(() => {
        if (!trackingRef.current) return;
        void refreshThread(activeThreadId).catch(() => {
          // thread may be gone
        });
      }, POLL_MS);
    },
    [refreshThread, stopPolling],
  );

  const finishRun = useCallback(
    async (activeThreadId: string | null, activeRunId: string | null) => {
      if (activeThreadId && (await isRunStillActive(activeThreadId, activeRunId))) {
        persistSession({ threadId: activeThreadId, runId: activeRunId, running: true });
        return false;
      }
      trackingRef.current = false;
      stopPolling();
      setRunning(false);
      abortRef.current = null;
      clearRunSession();
      pushLog("success", "🎉 Workflow finished");
      return true;
    },
    [persistSession, pushLog, stopPolling],
  );

  const waitForRunViaPolling = useCallback(
    async (activeThreadId: string, activeRunId: string | null, abort: AbortController) => {
      while (!abort.signal.aborted && trackingRef.current) {
        const { state, next, thread } = await refreshThread(activeThreadId);
        const resolvedRunId = await resolveRunId(activeThreadId, activeRunId);
        if (resolvedRunId) {
          runIdRef.current = resolvedRunId;
          setRunId(resolvedRunId);
        }
        let done = next.length === 0;
        if (resolvedRunId) {
          try {
            const runMeta = await fetchRun(activeThreadId, resolvedRunId);
            done = !ACTIVE_RUN_STATUSES.has(runMeta.status) && next.length === 0;
            if (runMeta.status === "error") {
              throw new Error("Agent run failed on the server");
            }
          } catch (err) {
            if (err instanceof Error && err.message.includes("failed")) throw err;
            done = next.length === 0;
          }
        }
        if (done) {
          const finalized = finalizePipeline(
            buildPipelineFromState(state, next, thread).steps,
            state,
            completedNodesRef.current,
            next,
            thread,
          );
          publishSteps(setSteps, finalized);
          setResult(state);
          return;
        }
        await sleep(POLL_MS);
      }
    },
    [refreshThread],
  );

  const processStream = useCallback(
    async (
      stream: AsyncIterable<{ event?: string; data?: unknown }>,
      ctx: {
        threadId: string;
        abort: AbortController;
        initialState?: AgentState;
        onRunId?: (id: string) => void;
      },
    ) => {
      let latestState: AgentState = ctx.initialState ?? {};
      let latestNext: string[] = [];
      let latestThread: ThreadSnapshot = {};
      const loggedNodes = new Set<string>();
      let streamDisconnected = false;

      const syncFromThread = async (partial?: AgentState) => {
        const refreshed = await refreshThread(ctx.threadId, partial ?? latestState);
        latestState = refreshed.state;
        latestNext = refreshed.next;
        latestThread = refreshed.thread;
        return refreshed;
      };

      const mergeAndPublish = (patch: Record<string, unknown>) => {
        latestState = { ...latestState, ...patch } as AgentState;
        publishFromState(latestState, latestNext, latestThread);
      };

      try {
        for await (const chunk of stream) {
          if (ctx.abort.signal.aborted) {
            streamDisconnected = true;
            break;
          }

          const event = normalizeStreamEvent(String(chunk.event ?? ""));

          if (event === "metadata") {
            const meta = chunk.data as { run_id?: string } | undefined;
            if (meta?.run_id) {
              const id = String(meta.run_id);
              runIdRef.current = id;
              setRunId(id);
              ctx.onRunId?.(id);
              persistSession({ threadId: ctx.threadId, runId: id, running: true });
            }
          }

          if (event === "error") {
            const errData = chunk.data as { message?: string; error?: string };
            throw new Error(errData?.message || errData?.error || "Agent stream error");
          }

          if (event === "events") {
            if (isChainStartEvent(chunk.data)) {
              const nodeName = normalizeNodeName(parseEventNodeName(chunk.data) ?? "");
              if (nodeName && !loggedNodes.has(nodeName)) {
                loggedNodes.add(nodeName);
                pushLog("info", `▶️ ${nodeName}`);
                await syncFromThread();
              }
            }
            if (isChainEndEvent(chunk.data)) {
              const nodeName = normalizeNodeName(parseEventNodeName(chunk.data) ?? "");
              if (nodeName && stepIdForNode(nodeName)) {
                const nodeOutput = parseEventNodeOutput(chunk.data);
                const payload =
                  Object.keys(nodeOutput).length > 0
                    ? nodeOutput
                    : (latestState as Record<string, unknown>);
                const merged = payloadForNode(nodeName, payload, latestState);
                const detail = detailForNode(nodeName, merged);
                pushLog("info", `✅ ${nodeName}: ${detail}`);
                if (merged.logged_in === true && nodeName === "login_youtube") {
                  pushLog("success", "🔐 YouTube login confirmed");
                }
                await syncFromThread(merged as AgentState);
              }
            }
          }

          if (event === "updates" && chunk.data && typeof chunk.data === "object") {
            for (const [rawNode, nodeUpdate] of Object.entries(chunk.data)) {
              const nodeName = normalizeNodeName(rawNode);
              if (nodeName === "execute_workflow") {
                const merged = { ...latestState, ...(nodeUpdate as AgentState) };
                const rebuilt = buildPipelineFromState(merged, latestNext, latestThread);
                completedNodesRef.current = rebuilt.completedNodes;
                const bundled = markBundledWorkflowComplete(
                  rebuilt.steps,
                  merged,
                  completedNodesRef.current,
                );
                latestState = merged;
                publishSteps(setSteps, bundled);
                flushSync(() => setResult(merged));
                persistSession({ threadId: ctx.threadId, steps: bundled, partialState: merged, running: true });
                continue;
              }
              if (stepIdForNode(nodeName)) {
                const merged = payloadForNode(nodeName, nodeUpdate as Record<string, unknown>, latestState);
                const detail = detailForNode(nodeName, merged);
                if (!loggedNodes.has(`${nodeName}:done`)) {
                  loggedNodes.add(`${nodeName}:done`);
                  pushLog("info", `✅ ${nodeName}: ${detail}`);
                }
                mergeAndPublish(merged);
              }
            }
            await syncFromThread();
          }

          if (event === "values" && chunk.data) {
            latestState = { ...(latestState as AgentState), ...(chunk.data as AgentState) };
            await syncFromThread(latestState);
          }
        }
      } catch (err) {
        if (!ctx.abort.signal.aborted) throw err;
        streamDisconnected = true;
      }

      if (!streamDisconnected) {
        await syncFromThread(latestState);
        const finalized = finalizePipeline(
          buildPipelineFromState(latestState, latestNext, latestThread).steps,
          latestState,
          completedNodesRef.current,
          latestNext,
          latestThread,
        );
        applyLoggedIn(latestState);
        flushSync(() => setResult(latestState));
        publishSteps(setSteps, finalized);
        persistSession({
          threadId: ctx.threadId,
          steps: finalized,
          partialState: latestState,
          running: trackingRef.current,
        });
      } else {
        const snapshot = buildPipelineFromState(latestState, latestNext, latestThread).steps;
        persistSession({
          threadId: ctx.threadId,
          runId: runIdRef.current,
          steps: snapshot,
          partialState: latestState,
          running: true,
        });
      }

      return { state: latestState, streamDisconnected };
    },
    [applyLoggedIn, persistSession, publishFromState, pushLog, refreshThread],
  );

  const trackRun = useCallback(
    async (
      activeThreadId: string,
      activeRunId: string | null,
      options: { resume?: boolean; initialState?: AgentState } = {},
    ) => {
      if (resumeLockRef.current) return;
      resumeLockRef.current = true;

      const abort = new AbortController();
      abortRef.current = abort;
      trackingRef.current = true;
      setRunning(true);
      setThreadId(activeThreadId);
      threadIdRef.current = activeThreadId;

      if (options.resume) {
        setReconnected(true);
        pushLog("info", "🔄 Reconnected to in-progress run after page refresh");
      }

      const resolvedRunId = await resolveRunId(activeThreadId, activeRunId);
      if (resolvedRunId) {
        runIdRef.current = resolvedRunId;
        setRunId(resolvedRunId);
      }

      persistSession({
        threadId: activeThreadId,
        runId: resolvedRunId,
        running: true,
        reconnected: options.resume,
      });

      startPolling(activeThreadId);

      try {
        const { state, next, thread } = await refreshThread(activeThreadId, options.initialState ?? {});
        publishFromState(state, next, thread);

        const stillActive = await isRunStillActive(activeThreadId, resolvedRunId);

        if (stillActive) {
          if (resolvedRunId) {
            try {
              const stream = joinRunStream(activeThreadId, resolvedRunId, abort.signal);
              const { streamDisconnected } = await processStream(stream, {
                threadId: activeThreadId,
                abort,
                initialState: state,
                onRunId: (id) => {
                  runIdRef.current = id;
                  persistSession({ threadId: activeThreadId, runId: id, running: true });
                },
              });
              if (!streamDisconnected) {
                await finishRun(activeThreadId, runIdRef.current);
                return;
              }
              pushLog("warn", "Stream disconnected — continuing via polling");
            } catch {
              pushLog("warn", "Stream rejoin unavailable — tracking via polling");
            }
          }
          await waitForRunViaPolling(activeThreadId, runIdRef.current, abort);
          await finishRun(activeThreadId, runIdRef.current);
          return;
        }

        const finalized = finalizePipeline(
          buildPipelineFromState(state, next, thread).steps,
          state,
          completedNodesRef.current,
          next,
          thread,
        );
        publishSteps(setSteps, finalized);
        setResult(state);
        await finishRun(activeThreadId, resolvedRunId);
      } catch (err) {
        if (abort.signal.aborted) {
          pushLog("warn", "⏹️ Run stopped");
        } else {
          const message = err instanceof Error ? err.message : String(err);
          setError(message);
          pushLog("error", message);
        }
        trackingRef.current = false;
        stopPolling();
        setRunning(false);
        persistSession({ threadId: activeThreadId, runId: runIdRef.current, running: false });
      } finally {
        resumeLockRef.current = false;
      }
    },
    [finishRun, persistSession, processStream, publishFromState, pushLog, refreshThread, startPolling, waitForRunViaPolling],
  );

  const run = useCallback(
    async (request: RunRequest) => {
      const { channelName, channelUrl } = request;
      if (!channelName.trim() && !channelUrl.trim()) {
        setError("Enter a channel name or URL, or set YOUTUBE_CHANNEL_NAME in the backend .env");
        return;
      }

      abortRef.current?.abort();
      stopPolling();
      completedNodesRef.current = new Set();
      clearRunSession();

      setRunning(true);
      setReconnected(false);
      setError(null);
      setResult(null);
      setLogs([]);
      setLoggedIn(null);
      publishSteps(setSteps, startPipeline(initialStepStates()));
      pushLog("info", "🚀 Starting agent workflow…");

      const abort = new AbortController();
      abortRef.current = abort;
      trackingRef.current = true;

      try {
        const input = buildAgentInput(request);
        const { threadId: createdThreadId, runId: createdRunId, stream } = await streamAgentRun(
          input,
          abort.signal,
        );
        threadIdRef.current = createdThreadId;
        runIdRef.current = createdRunId;
        setThreadId(createdThreadId);
        setRunId(createdRunId);
        pushLog("info", `🧵 Thread ${createdThreadId.slice(0, 8)}…`);

        persistSession({
          threadId: createdThreadId,
          runId: createdRunId,
          running: true,
          steps: startPipeline(initialStepStates()),
        });
        startPolling(createdThreadId);

        const { streamDisconnected } = await processStream(stream, {
          threadId: createdThreadId,
          abort,
          onRunId: (id) => {
            runIdRef.current = id;
            setRunId(id);
            persistSession({ threadId: createdThreadId, runId: id, running: true });
          },
        });

        if (streamDisconnected || (await isRunStillActive(createdThreadId, runIdRef.current))) {
          await waitForRunViaPolling(createdThreadId, runIdRef.current, abort);
        }
        await finishRun(createdThreadId, runIdRef.current);
      } catch (err) {
        if (abort.signal.aborted) {
          pushLog("warn", "⏹️ Run stopped");
          persistSession({
            threadId: threadIdRef.current,
            runId: runIdRef.current,
            running: true,
          });
        } else {
          const message = err instanceof Error ? err.message : String(err);
          setError(message);
          pushLog("error", message);
        }
        trackingRef.current = false;
        stopPolling();
        setRunning(false);
      }
    },
    [finishRun, persistSession, processStream, pushLog, startPolling, stopPolling, waitForRunViaPolling],
  );

  const cancel = useCallback(() => {
    abortRef.current?.abort();
    trackingRef.current = false;
    stopPolling();
    clearRunSession();
    setRunning(false);
    pushLog("warn", "⏹️ Stopping agent…");
  }, [pushLog, stopPolling]);

  // Reconnect after browser refresh if a run is still active on the server.
  useEffect(() => {
    const session = loadRunSession();
    if (!session?.threadId || !session.running) return;

    void trackRun(session.threadId, session.runId, {
      resume: true,
      initialState: session.partialState ?? {},
    });
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  useEffect(() => () => stopPolling(), [stopPolling]);

  return {
    running,
    reconnected,
    steps,
    result,
    error,
    logs,
    threadId,
    runId,
    loggedIn,
    run,
    cancel,
    reset,
  };
}
