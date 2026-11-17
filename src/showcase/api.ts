import { ApiError } from "../api";
import type { Conversation, Lead, Knowledge } from "../types";
import {
  createDemo,
  makeLead,
  reportFor,
  workspaceFor,
  type DemoState,
} from "./data";

export const STORAGE_KEY = "systematic-portfolio-demo-v1";
const AUTH_KEY = STORAGE_KEY + ":open";
let memory: DemoState | undefined;
let opened = false;
let storageAvailable = true;
export const demoStorageAvailable = () => storageAvailable;

function load(): DemoState {
  try {
    const raw = localStorage.getItem(STORAGE_KEY);
    if (raw) {
      const saved = JSON.parse(raw) as DemoState;
      if (
        saved.version === 1 &&
        saved.workspace?.business?.id === "systematic" &&
        saved.sources &&
        saved.completed &&
        saved.offers &&
        Array.isArray(saved.workspace.leads) &&
        Array.isArray(saved.workspace.conversations)
      )
        return saved;
    }
  } catch {
    storageAvailable = false;
  }
  if (!memory) {
    memory = createDemo();
    save(memory);
  }
  return structuredClone(memory);
}
function save(state: DemoState) {
  memory = structuredClone(state);
  try {
    localStorage.setItem(STORAGE_KEY, JSON.stringify(state));
  } catch {
    storageAvailable = false;
  }
}
export function resetDemo() {
  save(createDemo());
  // Only this showcase's visitor token is cleared; no unrelated site storage.
  try {
    localStorage.removeItem("systematic-showcase-visitor-v1:systematic");
  } catch {
    /* in-memory fallback */
  }
}
const fail = (status: number, message: string): never => {
  throw new ApiError(status, message);
};
const clone = <T>(value: T): T => structuredClone(value);

export async function showcaseApi<T>(
  path: string,
  options: RequestInit = {},
): Promise<T> {
  options.signal?.throwIfAborted();
  const url = new URL(path, "https://showcase.invalid");
  const route = url.pathname;
  const method = options.method || "GET";
  const body = options.body ? JSON.parse(String(options.body)) : {};
  const state = load();
  const w = state.workspace;
  const stamp = new Date().toISOString();
  let result: unknown;
  const commit = (value: unknown) => {
    save(state);
    return clone(value) as T;
  };
  const visitor = () => {
    const token = new Headers(options.headers)
      .get("Authorization")
      ?.replace(/^Bearer /, "");
    return (
      w.conversations.find(
        (c) => c.id === token && c.id.startsWith("visitor-"),
      ) || fail(401, "Start a new demo conversation.")
    );
  };
  if (route === "/health") return { mode: "demo", status: "ok" } as T;
  if (route === "/auth/demo" && method === "POST") {
    if (body.business !== "systematic")
      fail(400, "Use workspace ID systematic for this showcase.");
    opened = true;
    try {
      sessionStorage.setItem(AUTH_KEY, "1");
    } catch {
      /* no authentication is implied */
    }
    return { mode: "demo" } as T;
  }
  if (route === "/auth/logout" && method === "POST") {
    opened = false;
    try {
      sessionStorage.removeItem(AUTH_KEY);
    } catch {
      /* local only */
    }
    return {} as T;
  }
  if (route.startsWith("/admin/")) {
    try {
      opened = opened || sessionStorage.getItem(AUTH_KEY) === "1";
    } catch {
      /* local only */
    }
    if (!opened) fail(401, "Open the demo workspace to explore.");
  }
  if (route === "/admin/workspace") result = workspaceFor(state);
  else if (route === "/admin/insights") {
    const days = Number(url.searchParams.get("days") || 14);
    if (![7, 14, 30, 90].includes(days))
      fail(400, "Select a supported reporting period.");
    result = reportFor(state, days);
  } else if (route === "/admin/settings" && method === "PATCH") {
    if (
      !String(body.name || "").trim() ||
      !Array.isArray(body.services) ||
      !body.services.length
    )
      fail(400, "Provide a business name and at least one service.");
    Object.assign(w.business, body, { id: "systematic" });
    return commit(w.business);
  } else if (/^\/admin\/leads\/[^/]+/.test(route)) {
    const lead =
      w.leads.find((l) => l.id === route.split("/")[3]) ||
      fail(404, "Demo lead not found.");
    if (route.endsWith("/related"))
      result = {
        matches: w.leads.filter(
          (l) => l.id !== lead.id && l.email === lead.email,
        ),
      };
    else if (method === "PATCH") {
      const { note, ...updates } = body;
      Object.assign(lead, updates, { updated_at: stamp });
      if (note)
        lead.notes.push({
          text: String(note),
          author: "Portfolio visitor",
          created_at: stamp,
        });
      return commit(lead);
    } else result = lead;
  } else if (route.startsWith("/admin/conversations/")) {
    const c =
      w.conversations.find((c) => c.id === route.split("/")[3]) ||
      fail(404, "Demo conversation not found.");
    if (method === "POST") {
      if (route.endsWith("/takeover"))
        c.status = c.status === "human" ? "active" : "human";
      else if (route.endsWith("/reply")) {
        if (c.status !== "human" || !String(body.message || "").trim())
          fail(400, "Take over the conversation and enter a reply.");
        c.messages.push({
          id: crypto.randomUUID(),
          role: "assistant",
          author: "Demo sales team",
          content: String(body.message),
          created_at: stamp,
        });
      } else fail(404, "This action is not part of the showcase.");
      c.updated_at = stamp;
      return commit(c);
    }
    result = c;
  } else if (route.startsWith("/admin/requests/") && method === "PATCH") {
    const r =
      w.requests.find((r) => r.id === route.split("/")[3]) ||
      fail(404, "Demo request not found.");
    if ((r.version || 0) !== body.expected_version)
      fail(409, "This demo request changed. Reload it before saving.");
    if (
      body.status === "completed" &&
      r.status !== "completed" &&
      !String(body.note || "").trim()
    )
      fail(400, "Add an outcome note.");
    if (body.status === "in_progress" && !String(body.owner || "").trim())
      fail(400, "Choose a request owner.");
    Object.assign(r, {
      status: body.status,
      owner: body.owner,
      due_at: body.due_at,
      version: (r.version || 0) + 1,
    });
    (r.history ||= []).push({
      status: r.status,
      owner: r.owner || "",
      note: body.note || "",
      actor: "Portfolio visitor",
      created_at: stamp,
    });
    return commit(r);
  } else if (route === "/admin/knowledge" && method === "POST") {
    if (!body.title || !body.content) fail(400, "Provide a title and content.");
    const doc: Knowledge = {
      ...body,
      id: crypto.randomUUID(),
      updated_at: stamp,
    };
    w.knowledge.unshift(doc);
    return commit(doc);
  } else if (route.startsWith("/admin/knowledge/") && method === "DELETE") {
    w.knowledge = w.knowledge.filter((d) => d.id !== route.split("/")[3]);
    return commit({});
  } else if (route.startsWith("/admin/jobs/") && method === "POST") {
    if (route.endsWith("/demo-process"))
      w.jobs.forEach((j) => {
        if (j.status === "pending") {
          j.status = "simulated";
          j.attempts++;
          j.error = undefined;
        }
      });
    else {
      const job =
        w.jobs.find((j) => j.id === route.split("/")[3]) ||
        fail(404, "Demo job not found.");
      if (!route.endsWith("/retry")) fail(404, "Unsupported demo job action.");
      job.status = "pending";
      job.error = undefined;
    }
    return commit({});
  } else if (route === "/public/config/systematic")
    result = { ...w.business, mode: "demo" };
  else if (route === "/public/session" && method === "POST") {
    if (body.business !== "systematic")
      fail(400, "This showcase uses workspace systematic.");
    const c: Conversation = {
      id: "visitor-" + crypto.randomUUID(),
      lead_id: null,
      status: "active",
      source_page: "https://example.com/interactive-demo",
      created_at: stamp,
      updated_at: stamp,
      sample: true,
      messages: [],
    };
    w.conversations.unshift(c);
    return commit({ token: c.id, conversation: c });
  } else if (route === "/public/conversation") result = visitor();
  else if (route === "/public/chat" && method === "POST") {
    const c = visitor();
    const key = `${c.id}:chat:${body.request_id}`;
    if (state.completed[key]) return clone(state.completed[key]) as T;
    const message = String(body.message || "").trim();
    if (!message || message.length > 2000)
      fail(400, "Enter a message up to 2,000 characters.");
    const action = /book|meeting|consultation/i.test(message)
      ? "book_meeting"
      : /proposal|quote/i.test(message)
        ? "request_proposal"
        : /human|team|person/i.test(message)
          ? "human_handover"
          : "none";
    c.messages.push({
      id: crypto.randomUUID(),
      role: "user",
      content: message,
      created_at: stamp,
    });
    if (c.status !== "human")
      c.messages.push({
        id: crypto.randomUUID(),
        role: "assistant",
        content:
          action === "book_meeting"
            ? "Let's rehearse a consultation booking. Choose a sample time and confirm fictional details below."
            : action === "request_proposal"
              ? "Share a fictional project brief below. A sample proposal request will appear in the sales desk."
              : action === "human_handover"
                ? "We can record a sample handover. Use the form below, then review it in the sales desk."
                : `This is a scripted product tour, not live AI. Our demo services include ${w.business.services.join(", ")}. Try “Book a meeting”, “Request a proposal” or “Talk to the team” to explore the workflow.`,
        action,
        created_at: stamp,
      });
    c.updated_at = stamp;
    result = {
      conversation: c,
      action: c.status === "human" ? "none" : action,
    };
    state.completed[key] = clone(result);
    return commit(result);
  } else if (route === "/public/availability") {
    visitor();
    const day = url.searchParams.get("day") || "";
    if (!/^\d{4}-\d{2}-\d{2}$/.test(day) || !Number.isFinite(Date.parse(day)))
      fail(400, "Select a valid day.");
    const slots = [9, 11, 14, 16]
      .map((hour) => {
        const start = new Date(
          `${day}T${String(hour).padStart(2, "0")}:00:00Z`,
        );
        return {
          id: `slot-${day}-${hour}`,
          start_at: start.toISOString(),
          end_at: new Date(+start + 1800000).toISOString(),
          timezone: "UTC",
        };
      })
      .filter(
        (s) =>
          Date.parse(s.start_at) > Date.now() &&
          !w.meetings.some((m) => m.start_at === s.start_at),
      );
    slots.forEach((s) => (state.offers[s.id] = s));
    return commit({ slots });
  } else if (
    ["/public/book", "/public/requests"].includes(route) &&
    method === "POST"
  ) {
    const c = visitor();
    const key = `${c.id}:${route}:${body.offer_id || body.request_id}`;
    if (state.completed[key]) return clone(state.completed[key]) as T;
    if (
      !body.name ||
      !/^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(String(body.email)) ||
      !body.confirmed
    )
      fail(400, "Confirm a name and valid fictional email address.");
    const offer = state.offers[body.offer_id];
    if (
      route === "/public/book" &&
      (!offer ||
        Date.parse(offer.start_at) < Date.now() ||
        w.meetings.some((m) => m.start_at === offer.start_at))
    )
      fail(409, "This sample time is unavailable. Choose another slot.");
    let lead = w.leads.find((l) => l.id === c.lead_id);
    if (!lead) {
      lead = makeLead("visitor-lead-" + crypto.randomUUID(), c, 1, stamp);
      w.leads.unshift(lead);
      c.lead_id = lead.id;
    }
    Object.assign(lead, {
      full_name: String(body.name),
      email: String(body.email),
      company_name: String(body.company || "Demo company"),
      business_goal: String(body.goal || "Explore the demo workflow"),
      required_services: [String(body.service || w.business.services[0])],
      consent_status: body.consent ? "granted" : "not_requested",
      stage:
        route === "/public/book"
          ? "meeting_booked"
          : body.kind === "proposal"
            ? "proposal_requested"
            : "handover",
      updated_at: stamp,
    });
    if (route === "/public/book")
      w.meetings.unshift({
        id: crypto.randomUUID(),
        ...offer,
        name: lead.full_name!,
        email: lead.email!,
        service: lead.required_services[0],
        status: "simulated",
        sample: true,
      });
    else
      w.requests.unshift({
        id: crypto.randomUUID(),
        lead_id: lead.id,
        conversation_id: c.id,
        kind: body.kind === "proposal" ? "proposal" : "handover",
        summary: lead.business_goal || "Demo request",
        status: "recorded",
        version: 0,
        created_at: stamp,
        history: [],
      });
    c.messages.push({
      id: crypto.randomUUID(),
      role: "assistant",
      content:
        "Your fictional details are saved in this browser. No email, calendar event or external request was sent.",
      created_at: stamp,
    });
    result = { status: "simulated" };
    state.completed[key] = result;
    return commit(result);
  } else
    fail(404, "This endpoint is not available in the standalone showcase.");
  options.signal?.throwIfAborted();
  return clone(result) as T;
}

export function downloadDemoCsv(leads: Lead[]) {
  const cell = (value: string) =>
    '"' +
    (/^[=+@\-\t\r\n]/.test(value) ? "'" : "") +
    value.replaceAll('"', '""') +
    '"';
  const csv = [
    ["Name", "Company", "Email", "Stage", "Score"],
    ...leads.map((l) => [
      l.full_name || "",
      l.company_name || "",
      l.email || "",
      l.stage,
      String(l.lead_score),
    ]),
  ]
    .map((row) => row.map(cell).join(","))
    .join("\r\n");
  const url = URL.createObjectURL(
    new Blob([csv], { type: "text/csv;charset=utf-8" }),
  );
  const a = document.createElement("a");
  a.href = url;
  a.download = "fictional-demo-leads.csv";
  a.click();
  setTimeout(() => URL.revokeObjectURL(url), 1000);
}
