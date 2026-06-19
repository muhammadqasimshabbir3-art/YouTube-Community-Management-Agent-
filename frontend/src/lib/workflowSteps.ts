import type { StepState, WorkflowStep } from "../types";

export const WORKFLOW_STEPS: WorkflowStep[] = [
  {
    id: "prepare",
    nodes: ["prepare_agent", "decide_agent"],
    label: "🧠 Agent Planning",
    description: "Load channel config and build the task plan",
    emoji: "🧠",
  },
  {
    id: "login",
    nodes: ["login_youtube"],
    label: "🔐 YouTube Login",
    description: "Sign in with saved session or browser credentials",
    emoji: "🔐",
  },
  {
    id: "fetch",
    nodes: ["fetch_channel_data"],
    label: "📥 Scrape Comments",
    description: "Open target channel latest video and collect all comments",
    emoji: "📥",
  },
  {
    id: "analyze",
    nodes: ["analyze_comments"],
    label: "🔍 Analyze Sentiment",
    description: "Classify every comment by sentiment and engagement priority",
    emoji: "🔍",
  },
  {
    id: "select",
    nodes: ["select_reply_targets"],
    label: "🎯 Select Reply Targets",
    description: "Pick top positive comments for humorous replies",
    emoji: "🎯",
  },
  {
    id: "generate_replies",
    nodes: ["generate_replies"],
    label: "✍️ Generate Replies",
    description: "Write AI community-manager replies",
    emoji: "✍️",
  },
  {
    id: "post_replies",
    nodes: ["post_replies"],
    label: "💬 Post Replies",
    description: "Publish replies on YouTube (when enabled)",
    optional: true,
    emoji: "💬",
  },
  {
    id: "new_comment",
    nodes: ["generate_new_comment", "post_new_comment"],
    label: "📝 New Video Comment",
    description: "Generate and post a top-level community comment",
    optional: true,
    emoji: "📝",
  },
  {
    id: "html_report",
    nodes: ["generate_html_report"],
    label: "📊 HTML Dashboard",
    description: "Build interactive dashboard report and close browser",
    emoji: "📊",
  },
  {
    id: "pdf_report",
    nodes: ["generate_pdf_report"],
    label: "📄 PDF Report",
    description: "Export PDF community summary",
    optional: true,
    emoji: "📄",
  },
  {
    id: "email",
    nodes: ["email_report"],
    label: "📧 Email Delivery",
    description: "Send HTML + PDF via Gmail SMTP",
    optional: true,
    emoji: "📧",
  },
];

const NODE_TO_STEP = new Map<string, string>();
for (const step of WORKFLOW_STEPS) {
  for (const node of step.nodes) {
    NODE_TO_STEP.set(node, step.id);
  }
}
NODE_TO_STEP.set("execute_workflow", "prepare");

export function stepIdForNode(nodeName: string): string | undefined {
  return NODE_TO_STEP.get(nodeName);
}

export function initialStepStates(): StepState[] {
  return WORKFLOW_STEPS.map((step) => ({
    id: step.id,
    status: "pending" as const,
  }));
}

export function detailForNode(nodeName: string, payload: Record<string, unknown>): string {
  switch (nodeName) {
    case "prepare_agent":
      return "Preparing agent input…";
    case "fetch_channel_data": {
      const scraped = payload.comments_scraped_count ?? (payload.comments as unknown[])?.length;
      const title = (payload.latest_video as Record<string, string> | undefined)?.title;
      if (scraped != null && title) return `${scraped} comments from "${title}"`;
      if (scraped != null) return `${scraped} comments scraped`;
      return "Channel data fetched";
    }
    case "analyze_comments": {
      const count = (payload.analyzed_comments as unknown[])?.length;
      return count != null ? `${count} comments analyzed` : "Analysis complete";
    }
    case "select_reply_targets": {
      const count = (payload.reply_targets as unknown[])?.length;
      return count != null ? `${count} reply target(s) selected` : "Targets selected";
    }
    case "generate_replies": {
      const stats = payload.reply_statistics as Record<string, number> | undefined;
      const n = stats?.replies_generated ?? (payload.generated_replies as unknown[])?.length;
      return n != null ? `${n} reply draft(s) ready` : "Replies generated";
    }
    case "post_replies": {
      const stats = payload.reply_statistics as Record<string, number> | undefined;
      const posted = stats?.replies_posted ?? 0;
      const failed = stats?.replies_failed ?? 0;
      return `${posted} posted, ${failed} failed`;
    }
    case "post_new_comment": {
      const stats = payload.reply_statistics as Record<string, number> | undefined;
      const posted = stats?.new_comments_posted ?? 0;
      return `${posted} new comment(s) posted`;
    }
    case "generate_new_comment": {
      const n = (payload.generated_new_comments as unknown[])?.length;
      return n != null ? `${n} new comment draft(s)` : "New comment step finished";
    }
    case "generate_html_report":
      return payload.html_path ? `Saved ${String(payload.html_path)}` : "HTML report ready";
    case "generate_pdf_report":
      return payload.pdf_path ? `Saved ${String(payload.pdf_path)}` : "PDF report ready";
    case "email_report":
      return payload.email_result ? String(payload.email_result) : "Email step finished";
    case "login_youtube":
      if (payload.youtube_login_detail) return `✅ ${String(payload.youtube_login_detail)}`;
      if (payload.logged_in === true) return "✅ YouTube signed in — session active";
      if (payload.logged_in === false) return "❌ YouTube login check failed";
      return "Checking YouTube session…";
    case "decide_agent":
      return payload.task_plan_summary ? String(payload.task_plan_summary) : "Route selected";
    case "execute_workflow":
      return "Full workflow executed in batch mode";
    default:
      return "Done";
  }
}
