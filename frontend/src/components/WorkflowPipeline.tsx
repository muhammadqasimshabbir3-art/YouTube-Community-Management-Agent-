import type { CSSProperties } from "react";
import {
  AlertCircle,
  CheckCircle2,
  CircleDashed,
  Loader2,
  MinusCircle,
} from "lucide-react";
import { progressPercent } from "../lib/streamProgress";
import { WORKFLOW_STEPS } from "../lib/workflowSteps";
import type { StepState, StepStatus } from "../types";

interface WorkflowPipelineProps {
  steps: StepState[];
  running: boolean;
  reconnected?: boolean;
  taskPlanSummary?: string;
}

function StatusIcon({ status, emoji }: { status: StepStatus; emoji: string }) {
  switch (status) {
    case "running":
      return <Loader2 size={18} className="spin step-icon running" />;
    case "completed":
      return <CheckCircle2 size={18} className="step-icon completed" />;
    case "skipped":
      return <MinusCircle size={18} className="step-icon skipped" />;
    case "error":
      return <AlertCircle size={18} className="step-icon error" />;
    default:
      return <span className="step-emoji">{emoji}</span>;
  }
}

export function WorkflowPipeline({ steps, running, reconnected, taskPlanSummary }: WorkflowPipelineProps) {
  const progress = progressPercent(steps);
  const activeStep = steps.find((s) => s.status === "running");

  return (
    <section className="panel pipeline-panel">
      <div className="pipeline-header">
        <div>
          <div className="panel-title">
            <span>⚡ Agent Pipeline</span>
            {running && <CircleDashed size={16} className="spin" />}
          </div>
          <p className="panel-desc">
            Live LangGraph stream — steps turn <strong>running</strong> when nodes start,{" "}
            <strong>completed</strong> when they finish.
          </p>
          {activeStep && running && (
            <p className="active-step-hint">
              {WORKFLOW_STEPS.find((s) => s.id === activeStep.id)?.emoji}{" "}
              Currently: <strong>{WORKFLOW_STEPS.find((s) => s.id === activeStep.id)?.label}</strong>
            </p>
          )}
        </div>
        <div className="progress-ring" style={{ "--progress": `${progress}%` } as CSSProperties}>
          <span>{progress}%</span>
        </div>
      </div>

      {reconnected && running && (
        <div className="task-plan reconnect-banner">
          🔄 Reconnected — agent kept running on the server while you refreshed
        </div>
      )}

      {taskPlanSummary && <div className="task-plan">📋 {taskPlanSummary}</div>}

      <ol className="pipeline-steps">
        {WORKFLOW_STEPS.map((def) => {
          const state = steps.find((s) => s.id === def.id);
          const status = state?.status ?? "pending";
          return (
            <li key={def.id} className={`pipeline-step ${status}`}>
              <div className="step-marker">
                <StatusIcon status={status} emoji={def.emoji ?? "•"} />
                <div className="step-line" />
              </div>
              <div className="step-body">
                <div className="step-title-row">
                  <strong>{def.label}</strong>
                  {def.optional && <span className="optional-tag">optional</span>}
                  <span className={`step-badge ${status}`}>
                    {status === "running" ? "🔄 running" : status}
                  </span>
                </div>
                <p>{def.description}</p>
                {state?.detail && <p className="step-detail">{state.detail}</p>}
              </div>
            </li>
          );
        })}
      </ol>
    </section>
  );
}
