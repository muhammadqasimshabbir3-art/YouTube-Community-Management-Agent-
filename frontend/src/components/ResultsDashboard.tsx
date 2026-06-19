import { useMemo, useState } from "react";
import { Download, ExternalLink, FileText, MessageSquare } from "lucide-react";
import type { AgentState, CommentRow } from "../types";

function pct(part: number, total: number) {
  return total ? Math.round((part / total) * 1000) / 10 : 0;
}

function commentRows(comments: CommentRow[], includeReply = false) {
  return comments.map((c) => ({
    Author: c.author ?? "",
    Category: c.category ?? "",
    Priority: c.engagement_priority ?? "",
    Likes: c.likes ?? 0,
    Comment: c.text ?? "",
    ...(includeReply
      ? {
          "AI Reply": c.reply_text ?? "",
          Posted: c.posted ? "Yes" : "No",
          Error: c.post_error ?? "",
        }
      : {}),
  }));
}

interface ResultsDashboardProps {
  result: AgentState | null;
  error: string | null;
}

export function ResultsDashboard({ result, error }: ResultsDashboardProps) {
  const [tab, setTab] = useState("overview");

  const analyzed = result?.analyzed_comments ?? result?.comments ?? [];
  const total = analyzed.length;
  const stats = result?.reply_statistics ?? {};
  const video = result?.video_metadata ?? result?.latest_video;

  const tabs = useMemo(
    () => [
      { id: "overview", label: "Overview" },
      { id: "positive", label: `Positive (${result?.positive_comments?.length ?? 0})` },
      { id: "replies", label: `AI Replies (${result?.generated_replies?.length ?? 0})` },
      { id: "failed", label: `Failed (${result?.failed_replies?.length ?? 0})` },
      { id: "all", label: `All (${total})` },
    ],
    [result, total],
  );

  if (error) {
    return (
      <section className="panel results-panel error-panel">
        <h3>Workflow Error</h3>
        <p>{error}</p>
      </section>
    );
  }

  if (!result || total === 0 && !video) {
    return (
      <section className="panel results-panel empty-panel">
        <MessageSquare size={28} />
        <h3>Results will appear here</h3>
        <p>Start an agent run to see video metadata, comment analysis, replies, and report links.</p>
      </section>
    );
  }

  return (
    <section className="panel results-panel">
      <div className="results-header">
        <div>
          <h3>Community Dashboard</h3>
          <p>
            {result.youtube_channel_name && <strong>{result.youtube_channel_name}</strong>}
            {video?.title && <> · {video.title}</>}
          </p>
        </div>
        <div className="report-links">
          {result.html_path && (
            <span className="btn small path-chip" title={result.html_path}>
              <FileText size={14} /> HTML saved
            </span>
          )}
          {result.pdf_path && (
            <span className="btn small path-chip" title={result.pdf_path}>
              <Download size={14} /> PDF saved
            </span>
          )}
          {video?.url && (
            <a className="btn small" href={video.url} target="_blank" rel="noreferrer">
              <ExternalLink size={14} /> Video
            </a>
          )}
        </div>
      </div>

      <div className="metrics-grid">
        <Metric label="Comments" value={String(total)} />
        <Metric label="Positive" value={`${pct(result.positive_comments?.length ?? 0, total)}%`} />
        <Metric label="Replies posted" value={String(stats.replies_posted ?? 0)} />
        <Metric label="Replies failed" value={String(stats.replies_failed ?? result.failed_replies?.length ?? 0)} />
        <Metric label="New comments" value={String(stats.new_comments_posted ?? 0)} />
        <Metric label="Targets" value={String(result.reply_targets?.length ?? 0)} />
      </div>

      {result.llm_summary && (
        <div className="summary-box">
          <strong>Executive summary</strong>
          <p>{result.llm_summary}</p>
        </div>
      )}

      <div className="tab-bar">
        {tabs.map((t) => (
          <button
            key={t.id}
            type="button"
            className={`tab ${tab === t.id ? "active" : ""}`}
            onClick={() => setTab(t.id)}
          >
            {t.label}
          </button>
        ))}
      </div>

      <div className="tab-content">
        {tab === "overview" && (
          <div className="overview-grid">
            {video?.thumbnail_url && (
              <img src={video.thumbnail_url} alt={video.title ?? "Video"} className="video-thumb" />
            )}
            <div>
              <dl className="meta-list">
                <dt>Views</dt><dd>{video?.views ?? "—"}</dd>
                <dt>Likes</dt><dd>{video?.likes ?? "—"}</dd>
                <dt>Published</dt><dd>{video?.published ?? "—"}</dd>
                <dt>Comment count</dt><dd>{video?.comment_count ?? "—"}</dd>
              </dl>
              {video?.video_about && <p className="about">{video.video_about}</p>}
            </div>
          </div>
        )}
        {tab === "positive" && <DataTable rows={commentRows(result.positive_comments ?? [])} />}
        {tab === "replies" && <DataTable rows={commentRows(result.generated_replies ?? [], true)} />}
        {tab === "failed" && <DataTable rows={commentRows(result.failed_replies ?? [], true)} />}
        {tab === "all" && <DataTable rows={commentRows(analyzed)} />}
      </div>

      {result.email_result && (
        <div className="email-result">
          <strong>Email:</strong> {result.email_result}
        </div>
      )}

      {(result.html_path || result.pdf_path) && (
        <div className="path-list">
          {result.html_path && (
            <p>
              <strong>HTML:</strong> <code className="mono">{result.html_path}</code>
            </p>
          )}
          {result.pdf_path && (
            <p>
              <strong>PDF:</strong> <code className="mono">{result.pdf_path}</code>
            </p>
          )}
          <p className="muted">Reports are written on the LangGraph server host (see <code>reports/</code> locally).</p>
        </div>
      )}
    </section>
  );
}

function Metric({ label, value }: { label: string; value: string }) {
  return (
    <div className="metric-card">
      <span>{label}</span>
      <strong>{value}</strong>
    </div>
  );
}

function DataTable({ rows }: { rows: Record<string, unknown>[] }) {
  if (!rows.length) return <p className="muted">No data in this tab.</p>;
  const columns = Object.keys(rows[0]);
  return (
    <div className="table-wrap">
      <table>
        <thead>
          <tr>{columns.map((c) => <th key={c}>{c}</th>)}</tr>
        </thead>
        <tbody>
          {rows.map((row, i) => (
            <tr key={i}>
              {columns.map((c) => (
                <td key={c}>{String(row[c] ?? "")}</td>
              ))}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
