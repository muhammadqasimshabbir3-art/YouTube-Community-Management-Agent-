export type StepStatus = "pending" | "running" | "completed" | "skipped" | "error";

export type WorkflowAction = "analyze" | "report" | "email";

export interface WorkflowStep {
  id: string;
  nodes: string[];
  label: string;
  description: string;
  optional?: boolean;
  emoji?: string;
}

export interface StepState {
  id: string;
  status: StepStatus;
  startedAt?: string;
  completedAt?: string;
  detail?: string;
}

export interface CommentRow {
  author?: string;
  text?: string;
  category?: string;
  engagement_priority?: string;
  sentiment_score?: number | string;
  likes?: number;
  timestamp?: string;
  replied?: boolean;
  reply_text?: string;
  posted?: boolean;
  post_error?: string;
}

export interface AgentState {
  youtube_channel_name?: string;
  youtube_channel_url?: string;
  latest_video?: VideoMetadata;
  video_metadata?: VideoMetadata;
  comments?: CommentRow[];
  analyzed_comments?: CommentRow[];
  positive_comments?: CommentRow[];
  negative_comments?: CommentRow[];
  neutral_comments?: CommentRow[];
  question_comments?: CommentRow[];
  suggestion_comments?: CommentRow[];
  spam_comments?: CommentRow[];
  reply_targets?: CommentRow[];
  generated_replies?: CommentRow[];
  failed_replies?: CommentRow[];
  generated_new_comments?: Array<Record<string, unknown>>;
  failed_new_comments?: Array<Record<string, unknown>>;
  reply_statistics?: Record<string, number>;
  reply_history?: Array<Record<string, unknown>>;
  pdf_path?: string;
  html_path?: string;
  llm_summary?: string;
  task_plan_summary?: string;
  agent_route?: string;
  logged_in?: boolean;
  youtube_login_detail?: string;
  email_result?: string;
  messages?: Array<{ content?: string; type?: string }>;
}

export interface VideoMetadata {
  title?: string;
  url?: string;
  video_id?: string;
  thumbnail_url?: string;
  views?: string;
  likes?: string;
  published?: string;
  comment_count?: string;
  video_about?: string;
  description?: string;
}

export interface LogEntry {
  id: string;
  time: string;
  level: "info" | "success" | "warn" | "error";
  message: string;
}

export interface RunRequest {
  channelName: string;
  channelUrl: string;
  maxVideosToScan: number;
  maxCommentsPerVideo: number;
  maxReplies: number;
  replyPersonality: string;
  enableCommentReplies: boolean;
  enableNewComments: boolean;
  newCommentText: string;
  maxNewComments: number;
  keepBrowserOpen: boolean;
  replyToPositive: boolean;
  replyToNegative: boolean;
  replyToNeutral: boolean;
  replyToQuestions: boolean;
  replyToSuggestions: boolean;
  replyToSpam: boolean;
  emailReports: boolean;
  emailRecipient: string;
}

export type AgentRunSettings = Omit<RunRequest, never>;
