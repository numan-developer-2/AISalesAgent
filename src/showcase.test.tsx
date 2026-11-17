import { beforeEach, describe, expect, it, vi } from "vitest";
import { render, screen, within, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";

vi.hoisted(() => vi.stubEnv("MODE", "showcase"));
import App from "./App";
import { api } from "./api";
import { appUrl } from "./showcase/mode";
import { createDemo, reportFor, workspaceFor } from "./showcase/data";
import { resetDemo, STORAGE_KEY } from "./showcase/api";
import type { Workspace, Conversation, SalesRequest } from "./types";

beforeEach(async () => {
  localStorage.clear();
  sessionStorage.clear();
  vi.spyOn(window, "scrollTo").mockImplementation(() => {});
  resetDemo();
  await api("/auth/logout", { method: "POST" });
  vi.stubGlobal(
    "fetch",
    vi.fn(() => {
      throw new Error("Showcase must never call a backend");
    }),
  );
});
const post = (value: unknown) => ({
  method: "POST",
  body: JSON.stringify(value),
});
const open = () => api("/auth/demo", post({ business: "systematic" }));

describe("Standalone portfolio showcase", () => {
  it("creates linked fictional records and distinct, consistent cohorts", () => {
    const now = new Date("2026-11-17T18:00:00Z");
    const state = createDemo(now);
    const w = workspaceFor(state, now);
    expect(w.conversations.length).toBeGreaterThan(800);
    expect(w.leads.length).toBeGreaterThan(500);
    expect(w.trend).toHaveLength(90);
    for (const lead of w.leads) {
      expect(lead.email).toMatch(/@example\.com$/);
      expect(
        w.conversations.some(
          (c) => c.id === lead.conversation_id && c.lead_id === lead.id,
        ),
      ).toBe(true);
    }
    const reports = [7, 14, 30, 90].map((days) => reportFor(state, days, now));
    for (let i = 1; i < reports.length; i++)
      expect(reports[i].counts.sessions).toBeGreaterThan(
        reports[i - 1].counts.sessions,
      );
    for (const report of reports) {
      expect(report.sources.reduce((sum, s) => sum + s.sessions, 0)).toBe(
        report.counts.sessions,
      );
      expect(report.counts.booked).toBeLessThanOrEqual(
        report.counts.contactable,
      );
      expect(report.counts.contactable).toBeLessThanOrEqual(
        report.counts.engaged,
      );
    }
  });

  it("opens every feature with real demo data and no network requests", async () => {
    render(<App />);
    const user = userEvent.setup();
    await user.click(
      await screen.findByRole("button", { name: /Open demo workspace/ }),
    );
    await screen.findByRole("heading", {
      name: "Good conversations start here.",
    });
    for (const name of [
      "Lead pipeline",
      "Sales insights",
      "Conversations",
      "Meetings",
      "Sales desk",
      "Automations",
      "Knowledge base",
      "Workspace settings",
      "Overview",
    ]) {
      await user.click(
        within(
          screen.getByRole("navigation", { name: "Main navigation" }),
        ).getByRole("link", { name }),
      );
      await waitFor(() => expect(document.activeElement?.tagName).toBe("H1"));
      expect(screen.queryByRole("alert")).not.toBeInTheDocument();
    }
    expect(fetch).not.toHaveBeenCalled();
  }, 15000);

  it("paginates large lead lists and preserves report controls across periods", async () => {
    await open();
    location.hash = "leads";
    render(<App />);
    const user = userEvent.setup();
    await screen.findByText(/Page 1 of/);
    expect(within(screen.getByRole("table")).getAllByRole("row")).toHaveLength(
      26,
    );
    await user.click(screen.getByRole("button", { name: "Next" }));
    expect(screen.getByText(/Page 2 of/)).toBeInTheDocument();
    await user.type(
      screen.getByPlaceholderText("Search name, company, service…"),
      "Northstar",
    );
    expect(screen.queryByText(/Page 2 of/)).not.toBeInTheDocument();
    await user.click(
      within(
        screen.getByRole("navigation", { name: "Main navigation" }),
      ).getByRole("link", { name: "Sales insights" }),
    );
    await user.selectOptions(
      await screen.findByLabelText("Source chart metric"),
      "booked",
    );
    await user.selectOptions(
      screen.getByLabelText("Insights reporting period"),
      "90",
    );
    await waitFor(() =>
      expect(
        screen.getByLabelText("Displayed report period"),
      ).toHaveTextContent("Last 90 days"),
    );
    expect(screen.getByLabelText("Source chart metric")).toHaveValue("booked");
    expect(fetch).not.toHaveBeenCalled();
  });

  it("persists lead edits, request history, knowledge and simulated queue actions", async () => {
    await open();
    const w = await api<Workspace>("/admin/workspace");
    await api(`/admin/leads/${w.leads[0].id}`, {
      method: "PATCH",
      body: JSON.stringify({ stage: "won", note: "Portfolio rehearsal" }),
    });
    const request = w.requests.find((r) => r.status !== "completed")!;
    await api(`/admin/requests/${request.id}`, {
      method: "PATCH",
      body: JSON.stringify({
        expected_version: 0,
        status: "completed",
        owner: "Demo team",
        note: "Scope reviewed locally",
      }),
    });
    await api(
      "/admin/knowledge",
      post({
        title: "Demo guide",
        content: "Fictional content",
        type: "faq",
        source_url: "",
      }),
    );
    const failed = w.jobs.find((j) => j.status === "failed")!;
    await api(`/admin/jobs/${failed.id}/retry`, post({}));
    await api("/admin/jobs/demo-process", post({}));
    const updated = await api<Workspace>("/admin/workspace");
    expect(updated.leads[0].stage).toBe("won");
    expect(updated.leads[0].notes.at(-1)?.text).toBe("Portfolio rehearsal");
    expect(
      updated.requests.find((r) => r.id === request.id)?.history,
    ).toHaveLength(1);
    expect(updated.jobs.find((j) => j.id === failed.id)?.status).toBe(
      "simulated",
    );
    expect(updated.knowledge[0].title).toBe("Demo guide");
    expect(
      JSON.parse(localStorage.getItem(STORAGE_KEY)!).workspace.leads[0].stage,
    ).toBe("won");
    resetDemo();
    expect(
      (await api<Workspace>("/admin/workspace")).knowledge.some(
        (d) => d.title === "Demo guide",
      ),
    ).toBe(false);
  });

  it("connects a scripted visitor journey to requests, takeover and a simulated meeting", async () => {
    const session = await api<{ token: string; conversation: Conversation }>(
      "/public/session",
      post({ business: "systematic" }),
    );
    const headers = { Authorization: `Bearer ${session.token}` };
    const chat = await api<{ action: string }>("/public/chat", {
      ...post({ message: "Request a proposal", request_id: "message-1" }),
      headers,
    });
    expect(chat.action).toBe("request_proposal");
    const contact = {
      name: "Taylor Demo",
      email: "taylor-demo@example.com",
      service: "SEO",
      goal: "Test the product journey",
      consent: true,
      confirmed: true,
    };
    const request = {
      ...post({ ...contact, kind: "proposal", request_id: "request-1" }),
      headers,
    };
    await api("/public/requests", request);
    await api("/public/requests", request);
    await open();
    const w = await api<Workspace>("/admin/workspace");
    expect(
      w.requests.filter((r) => r.conversation_id === session.token),
    ).toHaveLength(1);
    await api(`/admin/conversations/${session.token}/takeover`, post({}));
    await api(
      `/admin/conversations/${session.token}/reply`,
      post({ message: "Sample reply from the team" }),
    );
    expect(
      (
        await api<Conversation>("/public/conversation", { headers })
      ).messages.at(-1)?.content,
    ).toBe("Sample reply from the team");
    const day = new Date(Date.now() + 10 * 86400000).toISOString().slice(0, 10);
    const { slots } = await api<{ slots: { id: string }[] }>(
      `/public/availability?day=${day}`,
      { headers },
    );
    const booking = { ...post({ ...contact, offer_id: slots[0].id }), headers };
    await api("/public/book", booking);
    await api("/public/book", booking);
    expect(
      (await api<Workspace>("/admin/workspace")).meetings.filter(
        (m) => m.email === contact.email,
      ),
    ).toHaveLength(1);
    expect(fetch).not.toHaveBeenCalled();
  });

  it("rejects unsupported actions, conflicts and aborted reads", async () => {
    await expect(api("/admin/workspace")).rejects.toMatchObject({
      status: 401,
    });
    await open();
    await expect(api("/admin/unknown")).rejects.toMatchObject({ status: 404 });
    await expect(api("/admin/insights?days=999")).rejects.toMatchObject({
      status: 400,
    });
    const controller = new AbortController();
    controller.abort();
    await expect(
      api("/admin/insights?days=14", { signal: controller.signal }),
    ).rejects.toMatchObject({ name: "AbortError" });
    const w = await api<Workspace>("/admin/workspace");
    await expect(
      api<SalesRequest>(`/admin/requests/${w.requests[0].id}`, {
        method: "PATCH",
        body: JSON.stringify({ expected_version: 99 }),
      }),
    ).rejects.toMatchObject({ status: 409 });
  });

  it("uses static-host friendly links without root /demo or /widget paths", () => {
    expect(appUrl("demo")).toContain("?view=demo&business=systematic");
    expect(appUrl("widget")).toContain("?view=widget&business=systematic");
  });
});
