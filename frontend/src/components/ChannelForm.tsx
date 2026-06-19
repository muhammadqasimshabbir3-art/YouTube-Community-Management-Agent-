import type { AgentRunSettings } from "../types";
import { REPLY_PERSONALITY_OPTIONS } from "../lib/defaultSettings";

interface AgentConfigFormProps {
  settings: AgentRunSettings;
  onChange: <K extends keyof AgentRunSettings>(key: K, value: AgentRunSettings[K]) => void;
  disabled?: boolean;
}

function ToggleRow({
  label,
  hint,
  checked,
  onChange,
  disabled,
}: {
  label: string;
  hint?: string;
  checked: boolean;
  onChange: (value: boolean) => void;
  disabled?: boolean;
}) {
  return (
    <label className="toggle-row">
      <input
        type="checkbox"
        checked={checked}
        onChange={(e) => onChange(e.target.checked)}
        disabled={disabled}
      />
      <span>
        <strong>{label}</strong>
        {hint && <small>{hint}</small>}
      </span>
    </label>
  );
}

export function AgentConfigForm({ settings, onChange, disabled }: AgentConfigFormProps) {
  return (
    <section className="panel channel-form">
      <div className="panel-title">
        <span>🎬 Target Channel & Settings</span>
      </div>
      <p className="panel-desc">
        Per-run options override backend <code>.env</code> for this agent run only. Channel
        credentials still come from <code>YOUTUBE_EMAIL</code> / <code>YOUTUBE_PASSWORD</code>.
      </p>

      <h3 className="form-section-title">Channel</h3>
      <div className="form-grid">
        <label>
          <span>Channel name</span>
          <input
            type="text"
            value={settings.channelName}
            onChange={(e) => onChange("channelName", e.target.value)}
            placeholder="e.g. @OldeWorldMelodies"
            disabled={disabled}
          />
        </label>
        <label>
          <span>Channel URL (optional)</span>
          <input
            type="url"
            value={settings.channelUrl}
            onChange={(e) => onChange("channelUrl", e.target.value)}
            placeholder="https://www.youtube.com/@channel"
            disabled={disabled}
          />
        </label>
      </div>

      <h3 className="form-section-title">Scraping</h3>
      <div className="form-grid">
        <label>
          <span>Max videos to scan</span>
          <input
            type="number"
            min={1}
            max={10}
            value={settings.maxVideosToScan}
            onChange={(e) => onChange("maxVideosToScan", Math.max(1, Number(e.target.value) || 1))}
            disabled={disabled}
          />
        </label>
        <label>
          <span>Max comments per video</span>
          <input
            type="number"
            min={0}
            max={5000}
            value={settings.maxCommentsPerVideo}
            onChange={(e) =>
              onChange("maxCommentsPerVideo", Math.max(0, Number(e.target.value) || 0))
            }
            disabled={disabled}
          />
          <small className="field-hint">0 = all visible comments on the video</small>
        </label>
      </div>

      <h3 className="form-section-title">Replies</h3>
      <div className="form-grid">
        <label>
          <span>Max replies per video</span>
          <input
            type="number"
            min={1}
            max={50}
            value={settings.maxReplies}
            onChange={(e) => onChange("maxReplies", Math.max(1, Number(e.target.value) || 1))}
            disabled={disabled}
          />
        </label>
        <label>
          <span>Reply personality</span>
          <select
            value={settings.replyPersonality}
            onChange={(e) => onChange("replyPersonality", e.target.value)}
            disabled={disabled}
          >
            {REPLY_PERSONALITY_OPTIONS.map((option) => (
              <option key={option} value={option}>
                {option}
              </option>
            ))}
          </select>
        </label>
      </div>

      <div className="toggle-grid">
        <ToggleRow
          label="Enable comment replies"
          hint="Post AI replies on YouTube (ENABLE_COMMENT_REPLIES)"
          checked={settings.enableCommentReplies}
          onChange={(v) => onChange("enableCommentReplies", v)}
          disabled={disabled}
        />
        <ToggleRow
          label="Keep browser open"
          hint="Keep Chrome open through scrape and posting (KEEP_BROWSER_OPEN)"
          checked={settings.keepBrowserOpen}
          onChange={(v) => onChange("keepBrowserOpen", v)}
          disabled={disabled}
        />
      </div>

      <h3 className="form-section-title">Reply to categories</h3>
      <div className="toggle-grid compact">
        <ToggleRow
          label="Positive"
          checked={settings.replyToPositive}
          onChange={(v) => onChange("replyToPositive", v)}
          disabled={disabled}
        />
        <ToggleRow
          label="Negative"
          checked={settings.replyToNegative}
          onChange={(v) => onChange("replyToNegative", v)}
          disabled={disabled}
        />
        <ToggleRow
          label="Neutral"
          checked={settings.replyToNeutral}
          onChange={(v) => onChange("replyToNeutral", v)}
          disabled={disabled}
        />
        <ToggleRow
          label="Questions"
          checked={settings.replyToQuestions}
          onChange={(v) => onChange("replyToQuestions", v)}
          disabled={disabled}
        />
        <ToggleRow
          label="Suggestions"
          checked={settings.replyToSuggestions}
          onChange={(v) => onChange("replyToSuggestions", v)}
          disabled={disabled}
        />
        <ToggleRow
          label="Spam"
          checked={settings.replyToSpam}
          onChange={(v) => onChange("replyToSpam", v)}
          disabled={disabled}
        />
      </div>

      <h3 className="form-section-title">New video comment</h3>
      <div className="toggle-grid">
        <ToggleRow
          label="Enable new comments"
          hint="Generate and post a top-level comment (ENABLE_NEW_COMMENTS)"
          checked={settings.enableNewComments}
          onChange={(v) => onChange("enableNewComments", v)}
          disabled={disabled}
        />
      </div>
      <div className="form-grid">
        <label>
          <span>Custom new comment text (optional)</span>
          <input
            type="text"
            value={settings.newCommentText}
            onChange={(e) => onChange("newCommentText", e.target.value)}
            placeholder="Leave empty to let AI draft one"
            disabled={disabled}
          />
        </label>
        <label>
          <span>Max new comments</span>
          <input
            type="number"
            min={1}
            max={5}
            value={settings.maxNewComments}
            onChange={(e) => onChange("maxNewComments", Math.max(1, Number(e.target.value) || 1))}
            disabled={disabled || !settings.enableNewComments}
          />
        </label>
      </div>

      <h3 className="form-section-title">Email</h3>
      <div className="toggle-grid">
        <ToggleRow
          label="Email reports"
          hint="Send HTML + PDF via Gmail SMTP (EMAIL_REPORTS)"
          checked={settings.emailReports}
          onChange={(v) => onChange("emailReports", v)}
          disabled={disabled}
        />
      </div>
      <div className="form-grid">
        <label>
          <span>Email recipient</span>
          <input
            type="email"
            value={settings.emailRecipient}
            onChange={(e) => onChange("emailRecipient", e.target.value)}
            placeholder="you@example.com"
            disabled={disabled || !settings.emailReports}
          />
        </label>
      </div>
    </section>
  );
}

interface RunControlsProps {
  running: boolean;
  serverOnline: boolean;
  onStart: () => void;
  onStop: () => void;
}

export function RunControls({ running, serverOnline, onStart, onStop }: RunControlsProps) {
  return (
    <section className="panel run-controls">
      <div className="panel-title">
        <span>🤖 Run Agent</span>
      </div>
      <div className="button-row">
        {!running ? (
          <button
            type="button"
            className="btn primary start-btn"
            disabled={!serverOnline}
            onClick={onStart}
          >
            ▶️ Start Agent
          </button>
        ) : (
          <button type="button" className="btn danger stop-btn" onClick={onStop}>
            ⏹️ Stop Agent
          </button>
        )}
      </div>
      {!serverOnline && (
        <p className="hint warn">
          Start the LangGraph server first: <code>./start.sh both</code>
        </p>
      )}
      {running && (
        <p className="hint running-hint">🔄 Agent is working — watch the pipeline below for live progress…</p>
      )}
    </section>
  );
}
