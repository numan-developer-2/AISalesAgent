import type { Workspace, Conversation, Lead } from "../types";

export type Source = { source: string; medium: string; campaign: string };
export type DemoState = {
  version: 1;
  workspace: Workspace;
  sources: Record<string, Source>;
  completed: Record<string, unknown>;
  offers: Record<
    string,
    { start_at: string; end_at: string; timezone: string }
  >;
};
const DAY = 86400000;
const stages = [
  "contactable",
  "qualified",
  "meeting_booked",
  "proposal_requested",
  "proposal_sent",
  "won",
  "lost",
  "handover",
];
const services = [
  "Web Development",
  "SEO",
  "AI Automation",
  "Digital Marketing",
  "E-commerce",
];
const firstNames = [
  "Alex",
  "Jordan",
  "Morgan",
  "Sam",
  "Taylor",
  "Casey",
  "Riley",
  "Avery",
  "Jamie",
  "Drew",
  "Cameron",
  "Robin",
];
const lastNames = [
  "Bennett",
  "Patel",
  "Chen",
  "Rivera",
  "Khan",
  "Reed",
  "Kim",
  "Silva",
  "Clarke",
  "Ali",
  "Singh",
  "Martin",
];
const companies = [
  "Northstar",
  "Cedar",
  "Orbit",
  "Harbor",
  "Atlas",
  "Juniper",
  "Evergreen",
  "Summit",
  "Lumen",
  "Bloom",
  "Meridian",
  "Willow",
];
const sectors = [
  "Studio",
  "Retail",
  "Learning",
  "Logistics",
  "Hospitality",
  "Consulting",
  "Labs",
];
const channels: Source[] = [
  { source: "Google", medium: "organic", campaign: "Service discovery" },
  { source: "LinkedIn", medium: "social", campaign: "Operations leaders" },
  { source: "Google", medium: "cpc", campaign: "Growth services" },
  { source: "Direct", medium: "none", campaign: "Brand visitors" },
  {
    source: "Partner referral",
    medium: "referral",
    campaign: "Agency network",
  },
  { source: "Newsletter", medium: "email", campaign: "Monthly insights" },
];

export function makeLead(
  id: string,
  conversation: Conversation,
  index: number,
  now: string,
): Lead {
  const score = 24 + ((index * 17) % 73);
  const stage = stages[index % stages.length];
  return {
    id,
    conversation_id: conversation.id,
    full_name: `${firstNames[index % 12]} ${lastNames[Math.floor(index / 12) % 12]}`,
    company_name: `${companies[index % 12]} ${sectors[Math.floor(index / 12) % 7]}`,
    email: `prospect-${index}@example.com`,
    required_services: [services[index % services.length]],
    business_goal: [
      "Increase qualified website inquiries",
      "Replace manual sales follow-ups",
      "Launch a faster online store",
      "Improve service discovery",
      "Connect marketing and sales context",
    ][index % 5],
    budget_range: [
      "$1,000–$3,000",
      "$3,000–$5,000",
      "$5,000–$10,000",
      "$10,000+",
    ][index % 4],
    timeline: ["This month", "Within 6 weeks", "This quarter"][index % 3],
    stage,
    lead_score: score,
    lead_classification: score >= 70 ? "Hot" : score >= 40 ? "Warm" : "Cold",
    created_at: conversation.created_at,
    updated_at: now,
    sample: true,
    assigned_sales_rep: [
      "Demo team · Maya",
      "Demo team · Alex",
      "Demo team · Sam",
    ][index % 3],
    next_action:
      stage === "won" ? "Schedule onboarding" : "Confirm scope and next step",
    consent_status: index % 3 ? "granted" : "not_requested",
    score_reasons: [
      {
        component: "demo_qualification",
        score,
        reason:
          "Illustrative priority from fictional service fit, timing and engagement signals.",
      },
    ],
    notes: [
      {
        text: "Fictional opportunity for portfolio demonstration. No customer data.",
        author: "Demo team",
        created_at: now,
      },
    ],
  };
}

export function createDemo(now = new Date()): DemoState {
  const stamp = now.toISOString();
  const w: Workspace = {
    business: {
      id: "systematic",
      name: "Systematic Demo Studio",
      short_name: "Systematic",
      tagline: "From first inquiry to a clear next step.",
      website: "https://example.com",
      accent: "#e97845",
      timezone: "UTC",
      welcome:
        "Explore this fictional sales journey. Ask about services, request a proposal or try a demo booking.",
      services,
      qualification: {
        hot_threshold: 70,
        warm_threshold: 40,
        minimum_budget: 1000,
      },
      navigation: [],
      allowed_origins: [],
      notification_email: "demo@example.com",
      followup_hours: 24,
      integrations: {
        email: false,
        calendar: false,
        sheets: false,
        crm: false,
      },
    },
    mode: "demo",
    operator: "Portfolio visitor",
    leads: [],
    conversations: [],
    meetings: [],
    jobs: [],
    requests: [],
    knowledge: [],
    booking_reviews: [],
    integrations: ["calendar", "email", "sheets", "crm"].map((id) => ({
      id,
      enabled: false,
      configured: false,
      status: "simulated",
      required: [],
    })),
    metrics: {},
    trend: [],
  };
  const state: DemoState = {
    version: 1,
    workspace: w,
    sources: {},
    completed: {},
    offers: {},
  };
  let index = 0;
  for (let day = 89; day >= 0; day--) {
    const date = new Date(now.getTime() - day * DAY);
    const daily = 5 + Math.floor((89 - day) / 18) + ((day * 7) % 9);
    for (let j = 0; j < daily; j++) {
      index++;
      const created = new Date(date.getTime() - j * 60000).toISOString();
      const engaged = index % 6 !== 0;
      const c: Conversation = {
        id: `demo-conversation-${index}`,
        lead_id: null,
        status: index % 11 === 0 ? "human" : "active",
        source_page: "https://example.com/services",
        created_at: created,
        updated_at: created,
        sample: true,
        messages: engaged
          ? [
              {
                id: `demo-user-${index}`,
                role: "user",
                content: `We are exploring ${services[index % 5]} to improve our customer journey. Can we discuss the next steps?`,
                created_at: created,
              },
              {
                id: `demo-assistant-${index}`,
                role: "assistant",
                content:
                  "We can start with your goals, current process and timeline, then prepare a focused consultation. This is a fictional sample conversation.",
                created_at: created,
              },
            ]
          : [],
      };
      if (engaged && index % 5 !== 0) {
        const lead = makeLead(`demo-lead-${index}`, c, index, created);
        c.lead_id = lead.id;
        w.leads.push(lead);
        if (["meeting_booked", "won"].includes(lead.stage)) {
          const start = new Date(
            day < 8
              ? now.getTime() + (1 + (j % 6)) * DAY + j * 3600000
              : Date.parse(created) + DAY,
          );
          w.meetings.push({
            id: `demo-meeting-${index}`,
            name: lead.full_name!,
            email: lead.email!,
            service: lead.required_services[0],
            start_at: start.toISOString(),
            end_at: new Date(+start + 1800000).toISOString(),
            timezone: "UTC",
            status: "simulated",
            sample: true,
          });
        }
        if (
          day < 20 &&
          ["proposal_requested", "handover", "proposal_sent"].includes(
            lead.stage,
          )
        ) {
          w.requests.push({
            id: `demo-request-${index}`,
            kind: lead.stage === "handover" ? "handover" : "proposal",
            lead_id: lead.id,
            conversation_id: c.id,
            status:
              index % 3 === 0
                ? "completed"
                : index % 3 === 1
                  ? "recorded"
                  : "in_progress",
            summary: `${lead.required_services[0]} scope and next steps`,
            owner: lead.assigned_sales_rep,
            created_at: created,
            due_at: new Date(
              now.getTime() + ((index % 7) - 2) * DAY,
            ).toISOString(),
            version: 0,
            history: [],
          });
        }
      }
      w.conversations.push(c);
      state.sources[c.id] = channels[index % channels.length];
    }
  }
  w.conversations.reverse();
  w.leads.reverse();
  w.requests.reverse();
  w.meetings.sort((a, b) => b.start_at.localeCompare(a.start_at));
  w.jobs = Array.from({ length: 24 }, (_, i) => ({
    id: `demo-job-${i + 1}`,
    kind: ["lead_notification", "followup", "crm_sync", "meeting_confirmation"][
      i % 4
    ],
    status: ["simulated", "simulated", "pending", "failed"][i % 4],
    attempts: i % 4 === 3 ? 2 : 1,
    due: Math.floor(+now / 1000) - i * 3600,
    created: Math.floor(+now / 1000) - i * 3600,
    error:
      i % 4 === 3
        ? "Simulated failure — retry to rehearse recovery."
        : undefined,
  }));
  w.knowledge = services.map((service, i) => ({
    id: `demo-knowledge-${i}`,
    title: `${service}: discovery guide`,
    type: "service",
    content: `${service} discovery starts with goals, current tools, timeline and the people involved. Scope and pricing require a team review. This document is synthetic and contains no private client material.`,
    source_url: "",
    updated_at: stamp,
  }));
  return state;
}

export function reportFor(state: DemoState, days: number, now = new Date()) {
  const since = +now - days * DAY;
  const sessions = state.workspace.conversations.filter(
    (c) => Date.parse(c.created_at) >= since,
  );
  const empty = () => ({
    sessions: 0,
    engaged: 0,
    contactable: 0,
    progressing: 0,
    booked: 0,
    won: 0,
  });
  const counts = empty();
  const sources = new Map<string, ReturnType<typeof empty> & Source>();
  const leads = new Map(state.workspace.leads.map((l) => [l.id, l]));
  for (const c of sessions) {
    const l = c.lead_id ? leads.get(c.lead_id) : undefined;
    const source = state.sources[c.id] || {
      source: "Direct",
      medium: "none",
      campaign: "Interactive demo",
    };
    const key = JSON.stringify(source);
    if (!sources.has(key)) sources.set(key, { ...empty(), ...source });
    for (const target of [counts, sources.get(key)!]) {
      target.sessions++;
      if (c.messages.some((m) => m.role === "user")) target.engaged++;
      if (l?.email) target.contactable++;
      if (l && !["contactable", "anonymous", "lost"].includes(l.stage))
        target.progressing++;
      if (l && state.workspace.meetings.some((m) => m.email === l.email))
        target.booked++;
      if (l?.stage === "won") target.won++;
    }
  }
  const ids = new Set(sessions.map((c) => c.id));
  const open = state.workspace.requests.filter(
    (r) => ids.has(r.conversation_id || "") && r.status !== "completed",
  );
  const rate = (a: number, b: number) =>
    b ? Math.round((a / b) * 1000) / 10 : null;
  return {
    counts,
    rates: {
      contact_capture: rate(counts.contactable, counts.engaged),
      booking: rate(counts.booked, counts.engaged),
      won: rate(counts.won, counts.contactable),
    },
    sources: [...sources.values()],
    open_requests: open.length,
    overdue_requests: open.filter(
      (r) => r.due_at && Date.parse(r.due_at) < +now,
    ).length,
    sample_sessions: sessions.length,
    as_of: now.toISOString(),
  };
}

export function workspaceFor(state: DemoState, now = new Date()): Workspace {
  const w = structuredClone(state.workspace);
  w.period_counts = Object.fromEntries(
    [7, 14, 30, 90].map((days) => [
      String(days),
      reportFor(state, days, now).counts,
    ]),
  );
  w.trend = Array.from({ length: 90 }, (_, i) => {
    const date = new Date(+now - (89 - i) * DAY).toISOString().slice(0, 10);
    return {
      date,
      conversations: w.conversations.filter(
        (c) =>
          c.created_at.startsWith(date) &&
          c.messages.some((m) => m.role === "user"),
      ).length,
      leads: w.leads.filter((l) => l.created_at.startsWith(date)).length,
    };
  });
  const counts = reportFor(state, 90, now).counts;
  w.metrics = {
    ...counts,
    visitors: counts.sessions,
    conversations: counts.engaged,
    leads: w.leads.length,
    hot: w.leads.filter((l) => l.lead_classification === "Hot").length,
    qualified: counts.progressing,
    meetings: w.meetings.length,
  };
  return w;
}
