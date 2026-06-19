import type { LogEntry } from "../types";

interface ActivityLogProps {
  logs: LogEntry[];
}

export function ActivityLog({ logs }: ActivityLogProps) {
  return (
    <section className="panel activity-log">
      <div className="panel-title">
        <span>Activity Log</span>
      </div>
      <div className="log-stream">
        {logs.length === 0 ? (
          <p className="muted">Run the agent to see live node updates…</p>
        ) : (
          logs.map((entry) => (
            <div key={entry.id} className={`log-line ${entry.level}`}>
              <span className="log-time">{entry.time}</span>
              <span className="log-msg">{entry.message}</span>
            </div>
          ))
        )}
      </div>
    </section>
  );
}
