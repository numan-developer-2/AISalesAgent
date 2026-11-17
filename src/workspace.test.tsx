import { beforeEach, describe, it, expect, vi } from "vitest";
import {
  act,
  fireEvent,
  render,
  screen,
  waitFor,
  within,
} from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import App from "./App";
import { Widget } from "./Widget";
import { Insights } from "./SalesOperations";
import type { Workspace, Conversation } from "./types";

let workspace: Workspace;
let conversation: Conversation;
let signedIn: boolean;
let fetchMock: ReturnType<
  typeof vi.fn<(url: string, options?: RequestInit) => Promise<Response>>
>;

beforeEach(() => {
  vi.spyOn(window, "scrollTo").mockImplementation(() => {});
  signedIn = true;
  conversation = {
    id: "conversation-1",
    lead_id: "lead-1",
    status: "active",
    source_page: "https://example.com",
    created_at: new Date().toISOString(),
    updated_at: new Date().toISOString(),
    messages: [
      {
        id: "m1",
        role: "user",
        content: "I need help with SEO.",
        created_at: new Date().toISOString(),
      },
    ],
  };
  workspace = {
    business: {
      id: "systematic",
      name: "Systematic IT Solutions",
      short_name: "Systematic",
      tagline: "Good conversations.",
      website: "https://example.com",
      accent: "#e97845",
      timezone: "Asia/Karachi",
      welcome: "How can we help your business?",
      services: ["SEO", "Web Development"],
      qualification: {
        hot_threshold: 70,
        warm_threshold: 40,
        minimum_budget: 500,
      },
      navigation: [],
      allowed_origins: ["https://example.com"],
      notification_email: "",
      followup_hours: 24,
      integrations: {
        email: false,
        calendar: false,
        sheets: false,
        crm: false,
      },
    },
    mode: "demo",
    operator: "Demo operator",
    leads: [
      {
        id: "lead-1",
        full_name: "Olivia Bennett",
        company_name: "Northstar Studio",
        email: "olivia@example.com",
        required_services: ["SEO"],
        lead_score: 80,
        lead_classification: "Hot",
        stage: "qualified",
        created_at: new Date().toISOString(),
        updated_at: new Date().toISOString(),
        conversation_id: "conversation-1",
        score_reasons: [],
        notes: [],
      },
    ],
    conversations: [conversation],
    meetings: [],
    jobs: [],
    knowledge: [],
    requests: [],
    booking_reviews: [],
    integrations: [],
    metrics: {
      visitors: 1,
      conversations: 1,
      leads: 1,
      hot: 1,
      qualified: 1,
      won: 0,
      meetings: 0,
    },
    trend: [{ date: "2026-09-26", leads: 1, conversations: 1 }],
  };
  fetchMock = vi.fn(async (url: string, options: RequestInit = {}) => {
    const body = options.body ? JSON.parse(String(options.body)) : {};
    let value: unknown = {};
    let status = 200;
    if (url === "/api/health") value = { mode: "demo" };
    else if (url === "/api/auth/demo") {
      signedIn = true;
      value = { mode: "demo" };
    } else if (url === "/api/admin/workspace") {
      value = signedIn ? workspace : { detail: "Sign in" };
      status = signedIn ? 200 : 401;
    } else if (
      url.startsWith("/api/admin/leads/") &&
      options.method === "PATCH"
    ) {
      Object.assign(workspace.leads[0], body);
      value = workspace.leads[0];
    } else if (url.endsWith("/related")) {
      value = {
        matches: workspace.leads.filter(
          (l) => l.id !== "lead-1" && l.email === workspace.leads[0].email,
        ),
        basis: "same_email_unverified",
      };
    } else if (
      url.startsWith("/api/admin/requests/") &&
      options.method === "PATCH"
    ) {
      const request = workspace.requests.find((r) => url.endsWith(r.id))!;
      Object.assign(request, body, { version: body.expected_version + 1 });
      value = request;
    } else if (url.startsWith("/api/admin/insights?")) {
      const counts = {
        sessions: 4,
        engaged: 2,
        contactable: 1,
        progressing: 1,
        booked: 1,
        won: 0,
      };
      value = {
        counts,
        rates: { contact_capture: 50, booking: 50, won: 0 },
        sources: [
          { ...counts, source: "google", medium: "cpc", campaign: "autumn" },
        ],
        open_requests: 1,
        overdue_requests: 0,
        sample_sessions: 0,
        as_of: new Date().toISOString(),
      };
    } else if (url === "/api/admin/conversations/conversation-1")
      value = conversation;
    else if (url.endsWith("/takeover")) {
      conversation = { ...conversation, status: "human" };
      value = conversation;
    } else if (url.endsWith("/reply")) {
      conversation = {
        ...conversation,
        messages: [
          ...conversation.messages,
          {
            id: "reply",
            role: "assistant",
            author: "Sales team",
            content: body.message,
            created_at: new Date().toISOString(),
          },
        ],
      };
      value = conversation;
    } else if (url === "/api/admin/knowledge") {
      const doc = {
        ...body,
        id: "new-doc",
        updated_at: new Date().toISOString(),
      };
      workspace.knowledge = [doc];
      value = doc;
    } else if (url.startsWith("/api/public/config/"))
      value = { ...workspace.business, mode: "demo" };
    else if (url === "/api/public/session")
      value = {
        token: "visitor-token",
        conversation: { ...conversation, messages: [] },
      };
    else if (url === "/api/public/conversation") value = conversation;
    else if (url === "/api/public/chat") {
      conversation = {
        ...conversation,
        messages: [
          {
            id: "visitor",
            role: "user",
            content: body.message,
            created_at: new Date().toISOString(),
          },
          {
            id: "assistant",
            role: "assistant",
            content: "Choose a consultation time below.",
            action: "book_meeting",
            created_at: new Date().toISOString(),
          },
        ],
      };
      value = { conversation, action: "book_meeting", mode: "demo" };
    } else if (url.startsWith("/api/public/availability"))
      value = {
        slots: [
          {
            id: "offered-slot",
            start_at: "2026-10-01T10:00:00+05:00",
            end_at: "2026-10-01T10:30:00+05:00",
            timezone: "Asia/Karachi",
          },
        ],
      };
    else if (url === "/api/public/book")
      value = { id: "booking", status: "simulated" };
    else {
      status = 404;
      value = { detail: "Unexpected test endpoint: " + url };
    }
    return new Response(JSON.stringify(value), {
      status,
      headers: { "Content-Type": "application/json" },
    });
  });
  vi.stubGlobal("fetch", fetchMock);
});

describe("Sales workspace interactions", () => {
  it("opens every workspace page through navigation without losing the page heading", async () => {
    render(<App />);
    const user = userEvent.setup();
    await screen.findByRole("heading", {
      name: "Good conversations start here.",
    });
    const pages = [
      ["Lead pipeline", "Your lead pipeline."],
      ["Conversations", "Every conversation, connected."],
      ["Meetings", "Make time for opportunity."],
      ["Sales desk", "Sales desk"],
      ["Sales insights", "Sales insights"],
      ["Automations", "Work that keeps moving."],
      ["Knowledge base", "Your business, understood."],
      ["Workspace settings", "One workspace. Your way."],
      ["Overview", "Good conversations start here."],
    ];
    for (const [name, heading] of pages) {
      await user.click(
        within(
          screen.getByRole("navigation", { name: "Main navigation" }),
        ).getByRole("link", { name }),
      );
      const title = await screen.findByRole("heading", {
        name: heading,
        level: 1,
      });
      await waitFor(() => expect(title).toHaveFocus());
      expect(screen.queryByText("Page not found")).not.toBeInTheDocument();
    }
  });

  it("assigns and completes sales requests with an outcome note", async () => {
    location.hash = "sales-desk";
    workspace.requests = [
      {
        id: "request-1",
        kind: "proposal",
        lead_id: "lead-1",
        status: "recorded",
        summary: "SEO proposal",
        version: 0,
      },
    ];
    render(<App />);
    const user = userEvent.setup();
    await user.click(
      await screen.findByRole("button", {
        name: "Manage proposal for Olivia Bennett",
      }),
    );
    await user.selectOptions(screen.getByLabelText("Status"), "in_progress");
    await user.type(screen.getByLabelText("Request owner"), "Ayesha");
    await user.click(screen.getByRole("button", { name: "Save request" }));
    await waitFor(() =>
      expect(workspace.requests[0].status).toBe("in_progress"),
    );
    expect(workspace.requests[0].owner).toBe("Ayesha");
    await user.click(
      await screen.findByRole("button", {
        name: "Manage proposal for Olivia Bennett",
      }),
    );
    await user.selectOptions(screen.getByLabelText("Status"), "completed");
    expect(screen.getByLabelText("Outcome or progress note")).toBeRequired();
    await user.type(
      screen.getByLabelText("Outcome or progress note"),
      "Proposal delivered separately.",
    );
    await user.click(screen.getByRole("button", { name: "Save request" }));
    await waitFor(() => expect(workspace.requests[0].status).toBe("completed"));
    await user.selectOptions(
      screen.getByLabelText("Request filter"),
      "completed",
    );
    expect(
      await screen.findByRole("button", {
        name: "Manage proposal for Olivia Bennett",
      }),
    ).toBeInTheDocument();
    const calls = fetchMock.mock.calls.filter(
      ([url, options]) =>
        url === "/api/admin/requests/request-1" && options?.method === "PATCH",
    );
    expect(JSON.parse(String(calls[1][1]?.body))).toMatchObject({
      expected_version: 1,
      status: "completed",
      note: "Proposal delivered separately.",
    });
  });

  it("shows source reporting and requests the selected cohort period", async () => {
    location.hash = "insights";
    render(<App />);
    const user = userEvent.setup();
    const sourceTable = await screen.findByRole("table");
    expect(within(sourceTable).getByText("google")).toBeInTheDocument();
    expect(
      within(screen.getByText("Contact capture").closest("section")!).getByText(
        "50%",
      ),
    ).toBeInTheDocument();
    expect(
      within(
        screen.getByText("Booking conversion").closest("section")!,
      ).getByText("50%"),
    ).toBeInTheDocument();
    expect(
      screen.getByText(/Counts represent sessions, not unique people/),
    ).toBeInTheDocument();
    await user.selectOptions(
      screen.getByLabelText("Insights reporting period"),
      "30",
    );
    await waitFor(() =>
      expect(
        fetchMock.mock.calls.some(
          ([url]) => url === "/api/admin/insights?days=30",
        ),
      ).toBe(true),
    );
    expect(await screen.findByText("autumn")).toBeInTheDocument();
  });

  it("lets an operator review earlier inquiries without silently merging them", async () => {
    location.hash = "leads";
    workspace.leads.push({
      ...workspace.leads[0],
      id: "lead-earlier",
      full_name: "Earlier inquiry",
      business_goal: "Previous website redesign",
      stage: "lost",
    });
    render(<App />);
    const user = userEvent.setup();
    await user.click(
      await screen.findByRole("button", { name: "View Olivia Bennett" }),
    );
    const details = await screen.findByText(/Earlier inquiry · Lost/);
    await user.click(details);
    expect(screen.getByText("Previous website redesign")).toBeInTheDocument();
    expect(
      screen.getByText(
        /Confirm identity before treating these as the same contact/,
      ),
    ).toBeInTheDocument();
  });

  it("opens the demo through the sign-in screen", async () => {
    signedIn = false;
    render(<App />);
    const user = userEvent.setup();
    await user.click(
      await screen.findByRole("button", { name: /Open demo workspace/ }),
    );
    expect(
      await screen.findByRole("heading", {
        name: "Good conversations start here.",
      }),
    ).toBeInTheDocument();
    expect(
      screen.getByText(/Sample prospects and simulated integrations/),
    ).toBeInTheDocument();
  });
  it("keeps the login button busy until the workspace arrives and prevents repeated submissions", async () => {
    signedIn = false;
    let release!: () => void;
    const original = fetchMock.getMockImplementation()!;
    fetchMock.mockImplementation(async (url, options) => {
      if (url === "/api/admin/workspace" && signedIn)
        return new Promise<Response>((resolve) => {
          release = () => resolve(new Response(JSON.stringify(workspace)));
        });
      return original(url, options);
    });
    render(<App />);
    const user = userEvent.setup();
    await user.dblClick(
      await screen.findByRole("button", { name: /Open demo workspace/ }),
    );
    expect(
      screen.getByRole("button", { name: /Opening workspace/ }),
    ).toBeDisabled();
    expect(
      screen.queryByRole("heading", { name: "Good conversations start here." }),
    ).not.toBeInTheDocument();
    expect(
      fetchMock.mock.calls.filter(([url]) => url === "/api/auth/demo"),
    ).toHaveLength(1);
    await act(async () => release());
    expect(
      await screen.findByRole("heading", {
        name: "Good conversations start here.",
      }),
    ).toBeInTheDocument();
  });

  it("offers a retry when authentication succeeds but loading the workspace fails", async () => {
    signedIn = false;
    let fail = true;
    const original = fetchMock.getMockImplementation()!;
    fetchMock.mockImplementation(async (url, options) => {
      if (url === "/api/admin/workspace" && signedIn && fail)
        return new Response(
          JSON.stringify({ detail: "Temporary workspace failure" }),
          { status: 503 },
        );
      return original(url, options);
    });
    render(<App />);
    const user = userEvent.setup();
    await user.click(
      await screen.findByRole("button", { name: /Open demo workspace/ }),
    );
    expect(await screen.findByRole("alert")).toHaveTextContent(
      "Your workspace could not be loaded",
    );
    expect(
      screen.getByRole("button", { name: /Open demo workspace/ }),
    ).toBeEnabled();
    fail = false;
    await user.click(
      screen.getByRole("button", { name: /Open demo workspace/ }),
    );
    expect(
      await screen.findByRole("heading", {
        name: "Good conversations start here.",
      }),
    ).toBeInTheDocument();
  });

  it("keeps the report mounted and accurately labelled while a new period loads", async () => {
    location.hash = "insights";
    render(<App />);
    const user = userEvent.setup();
    await screen.findByText("autumn");
    await user.selectOptions(
      screen.getByLabelText("Source chart metric"),
      "booked",
    );
    const chart = screen.getByRole("list", {
      name: "Session outcome breakdown",
    });
    const metric = screen.getByLabelText("Source chart metric");
    const original = fetchMock.getMockImplementation()!;
    let release!: () => void;
    fetchMock.mockImplementation(async (url, options) => {
      if (url.startsWith("/api/admin/insights?"))
        return new Promise<Response>((resolve) => {
          release = () => {
            void original(url, options).then(resolve);
          };
        });
      return original(url, options);
    });
    await user.click(screen.getByRole("button", { name: "Refresh insights" }));
    expect(screen.getByText("autumn")).toBeInTheDocument();
    expect(
      screen.getByRole("list", { name: "Session outcome breakdown" }),
    ).toBeInTheDocument();
    expect(
      screen.getByRole("button", { name: "Updating insights" }),
    ).toBeDisabled();
    await act(async () => release());
    await screen.findByRole("button", { name: "Refresh insights" });
    await user.selectOptions(
      screen.getByLabelText("Insights reporting period"),
      "90",
    );
    expect(screen.getByText("autumn")).toBeInTheDocument();
    expect(
      screen.queryByRole("status", { name: "Loading sales insights" }),
    ).not.toBeInTheDocument();
    expect(screen.getByLabelText("Displayed report period")).toHaveTextContent(
      "Last 14 days",
    );
    expect(
      screen.getByText("Loading last 90 days · Showing last 14 days"),
    ).toBeInTheDocument();
    expect(
      screen.getByRole("list", { name: "Session outcome breakdown" }),
    ).toBe(chart);
    expect(screen.getByLabelText("Source chart metric")).toBe(metric);
    expect(metric).toHaveValue("booked");
    await act(async () => release());
    await waitFor(() =>
      expect(
        screen.getByLabelText("Displayed report period"),
      ).toHaveTextContent("Last 90 days"),
    );
    expect(screen.getByLabelText("Source chart metric")).toBe(metric);
    expect(metric).toHaveValue("booked");
  });

  it("ignores late responses and errors when reporting periods change rapidly", async () => {
    render(<Insights data={workspace} />);
    const user = userEvent.setup();
    await screen.findByText("autumn");
    const original = fetchMock.getMockImplementation()!;
    const pending: {
      signal?: AbortSignal | null;
      finish: (fail?: boolean) => Promise<void>;
    }[] = [];
    fetchMock.mockImplementation(
      (url, options) =>
        new Promise<Response>((resolve) => {
          pending.push({
            signal: options?.signal,
            finish: async (fail = false) => {
              const body = await (await original(url, options)).json();
              body.sources[0].campaign =
                url.split("days=")[1] + "-day campaign";
              resolve(
                new Response(
                  JSON.stringify(
                    fail ? { detail: "Old request failed" } : body,
                  ),
                  { status: fail ? 500 : 200 },
                ),
              );
            },
          });
        }),
    );
    for (const days of ["90", "7", "14"]) {
      await user.selectOptions(
        screen.getByLabelText("Insights reporting period"),
        days,
      );
    }
    expect(pending).toHaveLength(3);
    expect(pending[0].signal?.aborted).toBe(true);
    expect(pending[1].signal?.aborted).toBe(true);
    expect(pending[2].signal?.aborted).toBe(false);
    await act(async () => pending[2].finish());
    await screen.findByText("14-day campaign");
    await act(async () => pending[0].finish());
    await act(async () => pending[1].finish(true));
    expect(screen.getByText("14-day campaign")).toBeInTheDocument();
    expect(screen.queryByText("90-day campaign")).not.toBeInTheDocument();
    expect(screen.queryByRole("alert")).not.toBeInTheDocument();
    expect(screen.getByLabelText("Displayed report period")).toHaveTextContent(
      "Last 14 days",
    );
    expect(
      screen.getByRole("button", { name: "Refresh insights" }),
    ).toBeEnabled();
  });

  it("keeps the last successful period on failure and retries the selected period", async () => {
    render(<Insights data={workspace} />);
    const user = userEvent.setup();
    await screen.findByText("autumn");
    const original = fetchMock.getMockImplementation()!;
    fetchMock.mockResolvedValue(
      new Response(JSON.stringify({ detail: "Report unavailable" }), {
        status: 503,
      }),
    );
    await user.selectOptions(
      screen.getByLabelText("Insights reporting period"),
      "90",
    );
    expect(await screen.findByRole("alert")).toHaveTextContent(
      "Could not load last 90 days",
    );
    expect(screen.getByText("autumn")).toBeInTheDocument();
    expect(screen.getByLabelText("Displayed report period")).toHaveTextContent(
      "Last 14 days",
    );
    expect(
      screen.getByText("Showing the last successful report"),
    ).toBeInTheDocument();
    fetchMock.mockImplementation(original);
    await user.click(screen.getByRole("button", { name: "Refresh insights" }));
    await waitFor(() =>
      expect(
        screen.getByLabelText("Displayed report period"),
      ).toHaveTextContent("Last 90 days"),
    );
    expect(screen.queryByRole("alert")).not.toBeInTheDocument();
  });

  it("preserves source selection and chart nodes during background workspace updates", async () => {
    const view = render(<Insights data={workspace} />);
    const user = userEvent.setup();
    await screen.findByText("autumn");
    await user.selectOptions(
      screen.getByLabelText("Source chart metric"),
      "contactable",
    );
    const chart = screen.getByRole("list", {
      name: "Session outcome breakdown",
    });
    const original = fetchMock.getMockImplementation()!;
    let finish!: () => Promise<void>;
    let signal: AbortSignal | null | undefined;
    fetchMock.mockImplementation(
      (url, options) =>
        new Promise<Response>((resolve) => {
          signal = options?.signal;
          finish = async () => resolve(await original(url, options));
        }),
    );
    view.rerender(<Insights data={{ ...workspace }} />);
    expect(
      screen.getByRole("list", { name: "Session outcome breakdown" }),
    ).toBe(chart);
    expect(screen.getByLabelText("Source chart metric")).toHaveValue(
      "contactable",
    );
    expect(
      screen.queryByRole("status", { name: "Loading sales insights" }),
    ).not.toBeInTheDocument();
    await act(async () => finish());
    expect(
      screen.getByRole("list", { name: "Session outcome breakdown" }),
    ).toBe(chart);
    view.unmount();
    expect(signal?.aborted).toBe(true);
  });

  it("recovers from a stalled report without leaving the refresh button stuck", async () => {
    render(<Insights data={workspace} />);
    await screen.findByText("autumn");
    const original = fetchMock.getMockImplementation()!;
    let signal: AbortSignal | null | undefined;
    fetchMock.mockImplementation((_url, options) => {
      signal = options?.signal;
      return new Promise<Response>(() => {});
    });
    vi.useFakeTimers();
    try {
      fireEvent.change(screen.getByLabelText("Insights reporting period"), {
        target: { value: "90" },
      });
      act(() => vi.advanceTimersByTime(20000));
      expect(signal?.aborted).toBe(true);
      expect(screen.getByRole("alert")).toHaveTextContent("took too long");
      expect(screen.getByText("autumn")).toBeInTheDocument();
      expect(
        screen.getByRole("button", { name: "Refresh insights" }),
      ).toBeEnabled();
    } finally {
      vi.useRealTimers();
    }
    fetchMock.mockImplementation(original);
    await userEvent
      .setup()
      .click(screen.getByRole("button", { name: "Refresh insights" }));
    await waitFor(() =>
      expect(
        screen.getByLabelText("Displayed report period"),
      ).toHaveTextContent("Last 90 days"),
    );
  });

  it("opens a feature from a KPI card and focuses the new page after navigation", async () => {
    render(<App />);
    const user = userEvent.setup();
    await user.click(
      await screen.findByRole("link", { name: "Open conversations" }),
    );
    await waitFor(() =>
      expect(
        within(
          screen.getByRole("navigation", { name: "Main navigation" }),
        ).getByRole("link", { name: "Conversations" }),
      ).toHaveAttribute("aria-current", "page"),
    );
    expect(document.activeElement?.tagName).toBe("H1");
    expect(window.scrollTo).toHaveBeenCalledWith({
      top: 0,
      behavior: "instant",
    });
    await user.click(
      within(
        screen.getByRole("navigation", { name: "Main navigation" }),
      ).getByRole("link", { name: "Sales insights" }),
    );
    expect(
      await screen.findByRole("heading", { name: "Source contribution" }),
    ).toBeInTheDocument();
  });
  it("filters leads and saves a pipeline change through the API", async () => {
    location.hash = "leads";
    render(<App />);
    const user = userEvent.setup();
    await user.type(
      await screen.findByPlaceholderText("Search name, company, service…"),
      "Olivia",
    );
    await user.click(
      screen.getByRole("button", { name: "View Olivia Bennett" }),
    );
    const dialog = screen.getByRole("dialog");
    await user.selectOptions(
      within(dialog).getByLabelText("Pipeline stage"),
      "proposal_sent",
    );
    await user.selectOptions(
      within(dialog).getByLabelText("Email follow-up permission"),
      "declined",
    );
    await user.type(
      within(dialog).getByLabelText("Add a note"),
      "Discussed scope with the client.",
    );
    await user.click(
      within(dialog).getByRole("button", { name: "Save changes" }),
    );
    await waitFor(() => expect(workspace.leads[0].stage).toBe("proposal_sent"));
    expect(workspace.leads[0].consent_status).toBe("declined");
    expect(await screen.findByRole("status")).toHaveTextContent("Lead updated");
  });
  it("keeps the most recently selected conversation when earlier reads finish late", async () => {
    location.hash = "conversations";
    const second = {
      ...conversation,
      id: "conversation-2",
      lead_id: "lead-2",
      messages: [],
    };
    workspace.conversations.push(second);
    workspace.leads.push({
      ...workspace.leads[0],
      id: "lead-2",
      full_name: "Second visitor",
      conversation_id: second.id,
    });
    const original = fetchMock.getMockImplementation()!;
    const pending: (() => void)[] = [];
    fetchMock.mockImplementation((url, options) => {
      if (url.startsWith("/api/admin/conversations/"))
        return new Promise<Response>((resolve) => {
          pending.push(() =>
            resolve(
              new Response(
                JSON.stringify(
                  url.endsWith("conversation-2") ? second : conversation,
                ),
              ),
            ),
          );
        });
      return original(url, options);
    });
    render(<App />);
    const user = userEvent.setup();
    await user.click(
      await screen.findByRole("button", { name: /Olivia Bennett/ }),
    );
    expect(screen.getByText("Opening conversation…")).toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: /Second visitor/ }));
    await act(async () => pending[1]());
    expect(
      screen.getByRole("heading", { name: "Second visitor" }),
    ).toBeInTheDocument();
    await act(async () => pending[0]());
    expect(
      screen.getByRole("heading", { name: "Second visitor" }),
    ).toBeInTheDocument();
    expect(
      screen.queryByRole("heading", { name: "Olivia Bennett" }),
    ).not.toBeInTheDocument();
  });

  it("does not restore stale ownership after a takeover completes", async () => {
    location.hash = "conversations";
    render(<App />);
    const user = userEvent.setup();
    await user.click(
      await screen.findByRole("button", { name: /Olivia Bennett/ }),
    );
    await screen.findByRole("button", { name: "Take over conversation" });
    const original = fetchMock.getMockImplementation()!;
    const stale = JSON.stringify(conversation);
    let finish!: () => void;
    fetchMock.mockImplementation((url, options) => {
      if (url === "/api/admin/conversations/conversation-1")
        return new Promise<Response>((resolve) => {
          finish = () => resolve(new Response(stale));
        });
      return original(url, options);
    });
    await user.click(screen.getByRole("button", { name: /Olivia Bennett/ }));
    await user.click(
      screen.getByRole("button", { name: "Take over conversation" }),
    );
    await screen.findByRole("button", { name: "Return to assistant" });
    await act(async () => finish());
    expect(
      screen.getByRole("button", { name: "Return to assistant" }),
    ).toBeInTheDocument();
    expect(
      screen.getByRole("textbox", { name: "Reply to visitor" }),
    ).toBeEnabled();
  });

  it("clears a reply draft when switching visitors", async () => {
    location.hash = "conversations";
    conversation.status = "human";
    const second = {
      ...conversation,
      id: "conversation-2",
      lead_id: "lead-2",
      messages: [],
    };
    workspace.conversations.push(second);
    workspace.leads.push({
      ...workspace.leads[0],
      id: "lead-2",
      full_name: "Second visitor",
      conversation_id: second.id,
    });
    const original = fetchMock.getMockImplementation()!;
    fetchMock.mockImplementation((url, options) =>
      url === "/api/admin/conversations/conversation-2"
        ? Promise.resolve(new Response(JSON.stringify(second)))
        : original(url, options),
    );
    render(<App />);
    const user = userEvent.setup();
    await user.click(
      await screen.findByRole("button", { name: /Olivia Bennett/ }),
    );
    await user.type(
      await screen.findByRole("textbox", { name: "Reply to visitor" }),
      "Draft for Olivia only",
    );
    await user.click(screen.getByRole("button", { name: /Second visitor/ }));
    await screen.findByRole("heading", { name: "Second visitor" });
    expect(
      screen.getByRole("textbox", { name: "Reply to visitor" }),
    ).toHaveValue("");
  });

  it("supports human takeover and a real reply mutation", async () => {
    location.hash = "conversations";
    render(<App />);
    const user = userEvent.setup();
    await user.click(
      await screen.findByRole("button", { name: /Olivia Bennett/ }),
    );
    await user.click(
      await screen.findByRole("button", { name: "Take over conversation" }),
    );
    await user.type(
      screen.getByRole("textbox", { name: "Reply to visitor" }),
      "Hello, I can help with your SEO goals.",
    );
    await user.click(screen.getByRole("button", { name: /Send/ }));
    expect(
      await screen.findByText("Hello, I can help with your SEO goals."),
    ).toBeInTheDocument();
  });
  it("adds approved knowledge and refreshes the list", async () => {
    location.hash = "knowledge";
    render(<App />);
    const user = userEvent.setup();
    await user.click(
      await screen.findByRole("button", { name: "Add knowledge" }),
    );
    const dialog = screen.getByRole("dialog");
    await user.type(
      within(dialog).getByLabelText("Title"),
      "Consultation process",
    );
    await user.type(
      within(dialog).getByLabelText("Approved answer or information"),
      "We discuss your business goals during the consultation.",
    );
    await user.click(
      within(dialog).getByRole("button", { name: "Add knowledge" }),
    );
    expect(
      await screen.findByRole("heading", { name: "Consultation process" }),
    ).toBeInTheDocument();
  });
  it("shows a recoverable server error instead of claiming a successful change", async () => {
    location.hash = "leads";
    render(<App />);
    const user = userEvent.setup();
    await user.click(
      await screen.findByRole("button", { name: "View Olivia Bennett" }),
    );
    fetchMock.mockImplementationOnce(
      async () =>
        new Response(
          JSON.stringify({ detail: "Database temporarily unavailable" }),
          { status: 503 },
        ),
    );
    await user.click(
      within(screen.getByRole("dialog")).getByRole("button", {
        name: "Save changes",
      }),
    );
    expect(await screen.findByRole("alert")).toHaveTextContent(
      "Database temporarily unavailable",
    );
    expect(screen.getByRole("dialog")).toBeInTheDocument();
  });
});

describe("Visitor journey", () => {
  it("retries quick replies with the same ID and gives edited messages a new ID", async () => {
    history.replaceState({}, "", "/widget?business=retry-test");
    const original = fetchMock.getMockImplementation()!;
    fetchMock.mockImplementation(
      async (url: string, options: RequestInit = {}) =>
        url === "/api/public/chat"
          ? new Response(
              JSON.stringify({ detail: "Temporarily unavailable" }),
              { status: 503 },
            )
          : original(url, options),
    );
    render(<Widget />);
    const user = userEvent.setup();
    await user.click(
      await screen.findByRole("button", { name: "Explore pricing" }),
    );
    await screen.findByRole("alert");
    await user.click(screen.getByRole("button", { name: "Retry" }));
    await screen.findByRole("alert");
    await user.type(
      screen.getByLabelText("Your message"),
      "I need SEO instead",
    );
    await user.click(screen.getByRole("button", { name: "Send message" }));
    await screen.findByRole("alert");
    const requests = fetchMock.mock.calls
      .filter(([url]) => url === "/api/public/chat")
      .map(([, options]) => JSON.parse(String(options?.body)));
    expect(requests).toHaveLength(3);
    expect(requests[0]).toEqual(requests[1]);
    expect(requests[0].message).toBe("Explore pricing");
    expect(requests[2].message).toBe("I need SEO instead");
    expect(requests[2].request_id).not.toBe(requests[0].request_id);
  });

  it("binds form retries to the submitted details and consent", async () => {
    history.replaceState({}, "", "/widget?business=form-retry-test");
    const original = fetchMock.getMockImplementation()!;
    fetchMock.mockImplementation(
      async (url: string, options: RequestInit = {}) =>
        url === "/api/public/requests"
          ? new Response(
              JSON.stringify({ detail: "Temporarily unavailable" }),
              { status: 503 },
            )
          : original(url, options),
    );
    render(<Widget />);
    const user = userEvent.setup();
    await screen.findByRole("button", { name: "Explore pricing" });
    await user.click(screen.getByRole("button", { name: "Talk to a person" }));
    await user.type(screen.getByLabelText("Your name"), "Alex Guest");
    await user.type(screen.getByLabelText("Email address"), "alex@example.com");
    await user.click(screen.getByLabelText(/I confirm/));
    await user.click(screen.getByRole("button", { name: "Submit request" }));
    await screen.findByRole("alert");
    await user.click(screen.getByRole("button", { name: "Submit request" }));
    await screen.findByRole("alert");
    await user.click(screen.getByLabelText(/You may email me/));
    await user.type(
      screen.getByLabelText("What would you like help with?"),
      "Revised project goal",
    );
    await user.click(screen.getByRole("button", { name: "Submit request" }));
    await screen.findByRole("alert");
    const requests = fetchMock.mock.calls
      .filter(([url]) => url === "/api/public/requests")
      .map(([, options]) => JSON.parse(String(options?.body)));
    expect(requests).toHaveLength(3);
    expect(requests[0]).toEqual(requests[1]);
    expect(requests[2]).toMatchObject({
      consent: true,
      goal: "Revised project goal",
    });
    expect(requests[2].request_id).not.toBe(requests[0].request_id);
  });

  it("connects a conversation to a selected-slot confirmation without faking a live booking", async () => {
    history.replaceState({}, "", "/widget?business=systematic");
    render(<Widget />);
    const user = userEvent.setup();
    await user.click(
      await screen.findByRole("button", { name: "Book a consultation" }),
    );
    const slot = await screen.findByRole("button", { name: "10:00 AM" });
    await user.click(slot);
    await user.type(screen.getByLabelText("Your name"), "Alex Guest");
    await user.type(screen.getByLabelText("Email address"), "alex@example.com");
    await user.click(screen.getByLabelText(/I confirm this appointment/));
    await user.click(
      screen.getByRole("button", { name: /Confirm demo appointment/ }),
    );
    expect(
      await screen.findByRole("heading", { name: "Demo appointment saved" }),
    ).toBeInTheDocument();
    const call = fetchMock.mock.calls.find(
      ([url]) => url === "/api/public/book",
    );
    expect(JSON.parse(String(call?.[1]?.body))).toMatchObject({
      offer_id: "offered-slot",
      confirmed: true,
      email: "alex@example.com",
      consent: false,
    });
    expect(
      screen.getByText(/No external email or calendar event was sent/),
    ).toBeInTheDocument();
  });
});
