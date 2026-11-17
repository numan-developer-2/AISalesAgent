import { useEffect, useState, type FormEvent } from "react";
import {
  ArrowRight,
  RefreshCw,
  Target,
  BarChart3,
  GitBranch,
} from "lucide-react";
import { api, send, label, dateLabel } from "./api";
import { Badge, Empty, Modal, SectionHeader, Submit } from "./ui";
import type { Lead, SalesRequest, Workspace } from "./types";
import { OutcomeChart, SourceChart } from "./AnalyticsCharts";

type Counts = {
  sessions: number;
  engaged: number;
  contactable: number;
  progressing: number;
  booked: number;
  won: number;
};
type Report = {
  counts: Counts;
  rates: {
    contact_capture: number | null;
    booking: number | null;
    won: number | null;
  };
  sources: (Counts & { source: string; medium: string; campaign: string })[];
  open_requests: number;
  overdue_requests: number;
  sample_sessions: number;
  as_of: string;
};

export function Insights({ data }: { data: Workspace }) {
  const [days, setDays] = useState(14),
    [snapshot, setSnapshot] = useState<{ days: number; report: Report } | null>(
      null,
    ),
    [updating, setUpdating] = useState(false),
    [error, setError] = useState(""),
    [reload, setReload] = useState(0);
  useEffect(() => {
    let active = true;
    const controller = new AbortController();
    setUpdating(true);
    setError("");
    const timeout = window.setTimeout(() => {
      active = false;
      controller.abort();
      setError("The report took too long to load. Please try again.");
      setUpdating(false);
    }, 20000);
    api<Report>("/admin/insights?days=" + days, { signal: controller.signal })
      .then((r) => active && setSnapshot({ days, report: r }))
      .catch((e) => active && setError(e.message))
      .finally(() => {
        window.clearTimeout(timeout);
        if (active) setUpdating(false);
      });
    return () => {
      active = false;
      window.clearTimeout(timeout);
      controller.abort();
    };
  }, [days, reload, data]);
  // Keep the chart tree mounted while a new cohort loads. The displayed
  // period belongs to this snapshot, never to the pending filter selection.
  const report = snapshot?.report;
  const percent = (value: number | null) =>
    value === null ? "—" : value + "%";
  return (
    <>
      <div className="page-intro">
        <div>
          <span className="eyebrow">MEASURE THE NEXT STEP</span>
          <h1>Sales insights</h1>
          <p>See which inquiries become contacts, meetings and customers.</p>
        </div>
        <div className="intro-actions">
          <select
            aria-label="Insights reporting period"
            className="period-select"
            value={days}
            onChange={(e) => {
              setError("");
              setUpdating(true);
              setDays(Number(e.target.value));
            }}
          >
            {[7, 14, 30, 90].map((d) => (
              <option key={d} value={d}>
                Last {d} days
              </option>
            ))}
          </select>
          <button
            className="button secondary insights-refresh"
            disabled={updating}
            aria-busy={updating}
            onClick={() => {
              setError("");
              setUpdating(true);
              setReload((v) => v + 1);
            }}
          >
            <RefreshCw size={15} className={updating ? "spin" : ""} />{" "}
            {updating ? "Updating insights" : "Refresh insights"}
          </button>
        </div>
      </div>
      {error && (
        <p className="error-banner" role="alert">
          Could not load last {days} days. {error}
        </p>
      )}
      {!report && !error && (
        <div
          className="insights-loading"
          role="status"
          aria-label="Loading sales insights"
        >
          <span className="sr-only">Loading sales insights…</span>
          <div className="metric-grid">
            {[0, 1, 2, 3].map((i) => (
              <div className="metric-card skeleton-card" key={i}>
                <i />
                <i />
                <i />
              </div>
            ))}
          </div>
          <div className="insight-visual-grid">
            <div className="panel skeleton-chart" />
            <div className="panel skeleton-chart" />
          </div>
        </div>
      )}
      {report && snapshot && (
        <div
          role="region"
          aria-label="Sales insights report"
          aria-busy={updating}
        >
          <div className="report-context">
            <span>
              <span className="status-light" />{" "}
              {data.mode === "demo" ? "Demo analytics" : "Workspace analytics"}{" "}
              <span className="context-divider">/</span>
              <span aria-label="Displayed report period">
                Last {snapshot.days} days
              </span>
            </span>
            <span role="status">
              {updating
                ? snapshot.days !== days
                  ? `Loading last ${days} days · Showing last ${snapshot.days} days`
                  : "Refreshing saved activity…"
                : error
                  ? "Showing the last successful report"
                  : `Updated ${new Date(report.as_of).toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" })}`}
            </span>
          </div>
          <div className="metric-grid">
            {[
              [
                "Contact capture",
                percent(report.rates.contact_capture),
                `${report.counts.contactable} of ${report.counts.engaged} engaged sessions`,
              ],
              [
                "Booking conversion",
                percent(report.rates.booking),
                `${report.counts.booked} of ${report.counts.engaged} engaged sessions`,
              ],
              [
                "Won conversion",
                percent(report.rates.won),
                `${report.counts.won} of ${report.counts.contactable} contactable sessions`,
              ],
              [
                "Requests awaiting completion",
                report.open_requests,
                `${report.overdue_requests} overdue in this cohort`,
              ],
            ].map(([title, value, detail]) => (
              <section className="metric-card" key={title}>
                <div className="metric-top">
                  <span>{title}</span>
                  <Target size={17} />
                </div>
                <strong className="metric-value">{value}</strong>
                <p className="muted">{detail}</p>
              </section>
            ))}
          </div>
          <div className="insight-visual-grid">
            <section className="panel insight-visual-panel">
              <SectionHeader
                title="From interest to outcome"
                sub="See how this period's sessions are progressing."
                action={
                  <span className="analytics-panel-icon">
                    <GitBranch size={18} />
                  </span>
                }
              />
              <OutcomeChart counts={report.counts} />
            </section>
            <section className="panel insight-visual-panel">
              <SectionHeader
                title="Source contribution"
                sub="Compare the sources behind your inquiries."
                action={
                  <span className="analytics-panel-icon">
                    <BarChart3 size={18} />
                  </span>
                }
              />
              <SourceChart sources={report.sources} />
            </section>
          </div>
          <section className="panel operations-panel">
            <SectionHeader
              title="Where inquiries come from"
              sub="First recorded campaign source for sessions started in this period."
            />
            <div className="operations-table">
              <table>
                <thead>
                  <tr>
                    {[
                      "Source / medium",
                      "Campaign",
                      "Sessions",
                      "Engaged",
                      "Contactable",
                      "Booked",
                      "Won",
                    ].map((t) => (
                      <th key={t} scope="col">
                        {t}
                      </th>
                    ))}
                  </tr>
                </thead>
                <tbody>
                  {report.sources.map((s) => (
                    <tr key={JSON.stringify([s.source, s.medium, s.campaign])}>
                      <td>
                        <strong>{s.source}</strong>
                        <br />
                        <small>{s.medium}</small>
                      </td>
                      <td>{s.campaign}</td>
                      <td>{s.sessions}</td>
                      <td>{s.engaged}</td>
                      <td>{s.contactable}</td>
                      <td>{s.booked}</td>
                      <td>{s.won}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
            {!report.sources.length && (
              <Empty
                title="No sessions in this period"
                description="New website inquiries will appear as visitors use the assistant."
              />
            )}
            <p className="operations-help">
              Counts represent sessions, not unique people. Outcomes use the
              current saved state of that session's leads. Campaign tags are
              visitor supplied; untagged and older sessions appear as
              Unattributed. This report does not measure revenue or advertising
              ROI.
            </p>
            <p className="operations-help">
              As of {dateLabel(report.as_of)}.{" "}
              {report.sample_sessions > 0 &&
                `${report.sample_sessions} fictional sample sessions are included.`}{" "}
              {data.mode === "demo" && "Demo bookings are simulated."}
            </p>
          </section>
        </div>
      )}
    </>
  );
}

export function SalesDesk({
  data,
  notify,
  select,
}: {
  data: Workspace;
  notify: (s: string) => void;
  select: (l: Lead) => void;
}) {
  const [filter, setFilter] = useState("open"),
    [selected, setSelected] = useState<SalesRequest | null>(null);
  const rows = data.requests
    .filter(
      (r) =>
        filter === "all" ||
        (filter === "open"
          ? r.status !== "completed"
          : r.status === "completed"),
    )
    .sort(
      (a, b) =>
        (a.due_at || "9999").localeCompare(b.due_at || "9999") ||
        (a.created_at || "").localeCompare(b.created_at || ""),
    );
  return (
    <>
      <div className="page-intro">
        <div>
          <span className="eyebrow">TURN INTEREST INTO ACTION</span>
          <h1>Sales desk</h1>
          <p>
            Assign proposals and handovers, set a due date, and record the
            outcome.
          </p>
        </div>
        <select
          className="period-select"
          aria-label="Request filter"
          value={filter}
          onChange={(e) => setFilter(e.target.value)}
        >
          <option value="open">Open requests</option>
          <option value="completed">Completed requests</option>
          <option value="all">All requests</option>
        </select>
      </div>
      <section className="panel operations-panel">
        <SectionHeader
          title="Team requests"
          sub="Completing a task records its outcome; sending a proposal or replying to a visitor is a separate action."
        />
        <div className="operations-table">
          <table>
            <thead>
              <tr>
                {["Contact", "Request", "Owner", "Due", "Status", "Action"].map(
                  (t) => (
                    <th scope="col" key={t}>
                      {t}
                    </th>
                  ),
                )}
              </tr>
            </thead>
            <tbody>
              {rows.map((r) => {
                const lead = data.leads.find((l) => l.id === r.lead_id),
                  overdue =
                    r.status !== "completed" &&
                    !!r.due_at &&
                    Date.parse(r.due_at) < Date.now();
                return (
                  <tr key={r.id}>
                    <td>
                      {lead ? (
                        <button
                          className="text-button"
                          onClick={() => select(lead)}
                        >
                          {lead.full_name || lead.email || "Visitor"}
                        </button>
                      ) : (
                        "Visitor"
                      )}
                    </td>
                    <td>
                      {label(r.kind)}
                      <small className="request-summary">
                        {r.summary || "No additional details"}
                      </small>
                    </td>
                    <td>{r.owner || "Unassigned"}</td>
                    <td>
                      {r.due_at
                        ? dateLabel(r.due_at, {
                            month: "short",
                            day: "numeric",
                            hour: "numeric",
                            minute: "2-digit",
                          })
                        : "Not set"}
                      {overdue && (
                        <strong className="request-overdue">Overdue</strong>
                      )}
                    </td>
                    <td>
                      <Badge value={r.status} />
                    </td>
                    <td>
                      <button
                        className="button secondary"
                        onClick={() => setSelected(r)}
                        aria-label={`Manage ${r.kind} for ${lead?.full_name || "visitor"}`}
                      >
                        Manage <ArrowRight size={14} />
                      </button>
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
        {!rows.length && (
          <Empty
            title="No requests in this view"
            description="Proposal and handover requests from visitors will appear here."
          />
        )}
      </section>
      {selected && (
        <RequestEditor
          request={selected}
          close={() => setSelected(null)}
          notify={notify}
        />
      )}
    </>
  );
}

function RequestEditor({
  request,
  close,
  notify,
}: {
  request: SalesRequest;
  close: () => void;
  notify: (s: string) => void;
}) {
  const [busy, setBusy] = useState(false),
    [error, setError] = useState(""),
    [status, setStatus] = useState(request.status);
  const localDate = (value?: string | null) => {
    if (!value) return "";
    const d = new Date(value);
    return new Date(d.getTime() - d.getTimezoneOffset() * 60000)
      .toISOString()
      .slice(0, 16);
  };
  async function save(e: FormEvent<HTMLFormElement>) {
    e.preventDefault();
    setBusy(true);
    setError("");
    const form = new FormData(e.currentTarget),
      due = String(form.get("due_at") || "");
    try {
      await api("/admin/requests/" + request.id, {
        method: "PATCH",
        body: send({
          expected_version: request.version || 0,
          status,
          owner: form.get("owner"),
          due_at: due ? new Date(due).toISOString() : null,
          note: form.get("note"),
        }),
      });
      notify("Sales request updated");
      close();
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setBusy(false);
    }
  }
  return (
    <Modal
      open
      onClose={close}
      title="Manage sales request"
      description={request.summary || "Choose an owner and the next step."}
    >
      <form onSubmit={save} className="operations-form">
        <label>
          Status
          <select value={status} onChange={(e) => setStatus(e.target.value)}>
            <option value="recorded">Recorded</option>
            <option value="in_progress">In progress</option>
            <option value="completed">Completed</option>
          </select>
        </label>
        <label>
          Request owner
          <input
            name="owner"
            defaultValue={request.owner || ""}
            maxLength={100}
            required={status === "in_progress"}
          />
        </label>
        <label>
          Due date (your local time)
          <input
            name="due_at"
            type="datetime-local"
            defaultValue={localDate(request.due_at)}
          />
        </label>
        <label>
          Outcome or progress note
          <textarea
            name="note"
            rows={3}
            maxLength={2000}
            required={status === "completed" && request.status !== "completed"}
          />
        </label>
        {error && (
          <div className="error-banner" role="alert">
            {error}
            <button
              type="button"
              onClick={() => {
                notify("Refreshing requests");
                close();
              }}
            >
              Reload requests
            </button>
          </div>
        )}
        <Submit busy={busy}>Save request</Submit>
      </form>
      {!!request.history?.length && (
        <div className="request-history">
          <h3>Request history</h3>
          {[...request.history].reverse().map((h, i) => (
            <div key={i}>
              <strong>
                {label(h.status)} · {h.owner || "Unassigned"}
              </strong>
              <p>{h.note}</p>
              <small>
                {h.actor} · {dateLabel(h.created_at)}
              </small>
            </div>
          ))}
        </div>
      )}
    </Modal>
  );
}

export function RelatedInquiries({ lead }: { lead: Lead }) {
  const [matches, setMatches] = useState<Partial<Lead>[]>([]),
    [error, setError] = useState(""),
    [loading, setLoading] = useState(true),
    [reload, setReload] = useState(0);
  useEffect(() => {
    let active = true;
    setMatches([]);
    setError("");
    setLoading(true);
    if (!lead.email) {
      setLoading(false);
      return;
    }
    api<{ matches: Partial<Lead>[] }>(`/admin/leads/${lead.id}/related`)
      .then((r) => active && setMatches(r.matches))
      .catch((e) => active && setError(e.message))
      .finally(() => active && setLoading(false));
    return () => {
      active = false;
    };
  }, [lead.id, lead.email, reload]);
  return (
    <section className="related-inquiries">
      <h3>Related inquiries</h3>
      <p className="muted">
        Same email address within this business. Confirm identity before
        treating these as the same contact.
      </p>
      {loading && <p>Checking earlier inquiries…</p>}
      {error && (
        <p role="alert">
          {error}{" "}
          <button
            className="text-button"
            onClick={() => setReload((n) => n + 1)}
          >
            Retry related inquiries
          </button>
        </p>
      )}
      {!loading && !error && !matches.length && (
        <p className="muted">No other inquiries with this email.</p>
      )}
      {matches.map((m) => (
        <details key={m.id}>
          <summary>
            {m.full_name || "Visitor"} · {label(m.stage || "anonymous")} ·{" "}
            {m.created_at ? dateLabel(m.created_at) : ""}
          </summary>
          <p>{m.business_goal || "No goal recorded"}</p>
          <small>{m.required_services?.join(", ")}</small>
        </details>
      ))}
    </section>
  );
}
