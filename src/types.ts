export type Message = {
  grounding_status?: string;
  id: string;
  role: "user" | "assistant";
  content: string;
  created_at: string;
  action?: string;
  author?: string;
  sources?: { title: string; url: string }[];
};
export type Conversation = {
  id: string;
  lead_id: string | null;
  status: string;
  created_at: string;
  updated_at: string;
  source_page: string;
  messages: Message[];
  sample?: boolean;
};
export type Lead = {
  id: string;
  full_name?: string;
  company_name?: string;
  email?: string;
  phone?: string;
  required_services: string[];
  business_goal?: string;
  budget_range?: string;
  timeline?: string;
  lead_score: number;
  lead_classification: string;
  stage: string;
  created_at: string;
  updated_at: string;
  conversation_id: string;
  assigned_sales_rep?: string;
  next_action?: string;
  due_at?: string;
  lost_reason?: string;
  consent_status?: "not_requested" | "granted" | "declined";
  consent_updated_at?: string;
  sample?: boolean;
  score_reasons: { component: string; score: number; reason: string }[];
  notes: { text: string; created_at: string; author: string }[];
};
export type Meeting = {
  id: string;
  name: string;
  email: string;
  service: string;
  start_at: string;
  end_at: string;
  timezone: string;
  status: string;
  sample?: boolean;
};
export type Job = {
  id: string;
  kind: string;
  status: string;
  attempts: number;
  due: number;
  created: number;
  error?: string;
};
export type Knowledge = {
  id: string;
  title: string;
  content: string;
  type: string;
  source_url: string;
  updated_at: string;
};
export type Business = {
  id: string;
  name: string;
  short_name: string;
  tagline: string;
  website: string;
  accent: string;
  timezone: string;
  welcome: string;
  meeting_duration?: number;
  services: string[];
  qualification: {
    hot_threshold: number;
    warm_threshold: number;
    minimum_budget: number;
  };
  navigation: { label: string; url: string }[];
  allowed_origins: string[];
  notification_email: string;
  followup_hours: number;
  integrations: Record<string, boolean>;
};
export type Integration = {
  id: string;
  enabled: boolean;
  configured: boolean;
  status: string;
  required: string[];
};
export type Workspace = {
  business: Business;
  mode: "demo" | "live";
  operator: string;
  leads: Lead[];
  conversations: Conversation[];
  meetings: Meeting[];
  jobs: Job[];
  knowledge: Knowledge[];
  requests: SalesRequest[];
  booking_reviews: {
    id: string;
    name: string;
    status: string;
    created: number;
  }[];
  integrations: Integration[];
  metrics: Record<string, number>;
  period_counts?: Record<
    string,
    {
      sessions: number;
      engaged: number;
      contactable: number;
      progressing: number;
      booked: number;
      won: number;
    }
  >;
  trend: { date: string; leads: number; conversations: number }[];
};

export type SalesRequest = {
  id: string;
  kind: string;
  lead_id: string;
  status: string;
  summary: string;
  conversation_id?: string;
  created_at?: string;
  owner?: string;
  due_at?: string | null;
  version?: number;
  history?: {
    status: string;
    owner: string;
    note: string;
    actor: string;
    created_at: string;
  }[];
};
