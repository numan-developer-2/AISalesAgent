import {
  useEffect,
  useState,
  useCallback,
  useRef,
  type FormEvent,
} from "react";
import {
  ArrowUpRight,
  ArrowRight,
  LayoutDashboard,
  Users,
  MessagesSquare,
  CalendarDays,
  Workflow,
  BookOpen,
  Settings,
  Search,
  Bell,
  ChevronDown,
  PanelLeftClose,
  PanelLeftOpen,
  Plus,
  Download,
  Flame,
  Check,
  Command,
  LogOut,
  Activity,
  Layers,
  Sparkles,
  Target,
  TrendingUp,
  Clock,
  ChevronRight,
  RefreshCw,
  AlertCircle,
  Globe,
  ShieldCheck,
  MessageCircle,
  Loader2,
  BarChart3,
} from "lucide-react";
import { api, ApiError, send, dateLabel, initials, label } from "./api";
import type {
  Workspace,
  Lead,
  Conversation,
  Business,
  Knowledge,
} from "./types";
import { Badge, Empty, Modal, SearchBox, SectionHeader, Submit } from "./ui";
import { Insights, SalesDesk, RelatedInquiries } from "./SalesOperations";
import { ActivityChart } from "./AnalyticsCharts";
import { SHOWCASE, appUrl } from "./showcase/mode";

const NAV = [
  { id: "overview", label: "Overview", icon: LayoutDashboard },
  { id: "leads", label: "Lead pipeline", icon: Users },
  { id: "conversations", label: "Conversations", icon: MessagesSquare },
  { id: "meetings", label: "Meetings", icon: CalendarDays },
  { id: "sales-desk", label: "Sales desk", icon: Target },
  { id: "insights", label: "Sales insights", icon: TrendingUp },
  { id: "automations", label: "Automations", icon: Workflow },
  { id: "knowledge", label: "Knowledge base", icon: BookOpen },
  { id: "settings", label: "Workspace settings", icon: Settings },
];
const STAGES = [
  "anonymous",
  "contactable",
  "qualified",
  "meeting_booked",
  "meeting_attended",
  "proposal_requested",
  "proposal_sent",
  "handover",
  "won",
  "lost",
];

export default function App() {
  const [data, setData] = useState<Workspace | null>(null),
    [loading, setLoading] = useState(true),
    [unauth, setUnauth] = useState(false),
    [error, setError] = useState(""),
    [toast, setToast] = useState(""),
    [page, setPage] = useState(location.hash.slice(1) || "overview"),
    [mobile, setMobile] = useState(false),
    [query, setQuery] = useState(""),
    [selected, setSelected] = useState<Lead | null>(null);
  const pageRegion = useRef<HTMLDivElement>(null);
  const previousPage = useRef(page);
  const refresh = useCallback(async () => {
    try {
      setData(await api<Workspace>("/admin/workspace"));
      setUnauth(false);
      setError("");
      return true;
    } catch (e) {
      if (e instanceof ApiError && e.status === 401) setUnauth(true);
      else setError((e as Error).message);
      return false;
    } finally {
      setLoading(false);
    }
  }, []);
  useEffect(() => {
    if (previousPage.current === page) return;
    previousPage.current = page;
    window.scrollTo({ top: 0, behavior: "instant" });
    const heading = pageRegion.current?.querySelector("h1");
    heading?.setAttribute("tabindex", "-1");
    heading?.focus({ preventScroll: true });
  }, [page]);
  useEffect(() => {
    refresh();
    const timer = setInterval(refresh, 30000);
    return () => clearInterval(timer);
  }, [refresh]);
  useEffect(() => {
    const fn = () => {
      setPage(location.hash.slice(1) || "overview");
      setMobile(false);
    };
    addEventListener("hashchange", fn);
    return () => removeEventListener("hashchange", fn);
  }, []);
  useEffect(() => {
    if (toast) {
      const t = setTimeout(() => setToast(""), 4500);
      return () => clearTimeout(t);
    }
  }, [toast]);
  const notify = (s: string) => {
    setToast(s);
    refresh();
  };
  const go = (p: string) => {
    location.hash = p;
  };
  if (unauth) return <Login onLogin={refresh} />;
  if (!data)
    return (
      <div className="boot">
        <div className="brand-mark">
          <Layers />
        </div>
        <h2>{loading ? "Opening your workspace…" : "Could not connect"}</h2>
        <p>{error || "Making room for your next opportunity."}</p>
        {error && (
          <button className="button primary" onClick={refresh}>
            Try again
          </button>
        )}
      </div>
    );
  const active = NAV.find((n) => n.id === page) || NAV[0];
  return (
    <div
      className="app-shell"
      style={{ "--accent": data.business.accent } as React.CSSProperties}
    >
      {mobile && (
        <button
          className="sidebar-scrim"
          aria-label="Close navigation"
          onClick={() => setMobile(false)}
        />
      )}
      <aside className={"sidebar " + (mobile ? "sidebar-open" : "")}>
        <a className="brand" href="#overview">
          <span className="brand-mark">
            <Layers size={22} />
          </span>
          <span>
            {data.business.short_name.toLowerCase()}
            <span className="brand-period">.</span>
            <small>SALES WORKSPACE</small>
          </span>
        </a>
        <div className="workspace-switch">
          <div className="workspace-avatar">
            {initials(data.business.short_name)}
          </div>
          <div>
            <strong>{data.business.short_name}</strong>
            <small>
              {data.mode === "demo" ? "Demo workspace" : "Business workspace"}
            </small>
          </div>
          <ChevronDown size={15} />
        </div>
        <p className="nav-caption">WORKSPACE</p>
        <nav aria-label="Main navigation">
          {NAV.slice(0, 4).map((n) => (
            <a
              key={n.id}
              href={"#" + n.id}
              className={page === n.id ? "active" : ""}
              aria-current={page === n.id ? "page" : undefined}
            >
              <n.icon size={18} />
              <span>{n.label}</span>
              {n.id === "conversations" &&
                data.conversations.filter(
                  (c) => c.status === "handover_requested",
                ).length > 0 && (
                  <b>
                    {
                      data.conversations.filter(
                        (c) => c.status === "handover_requested",
                      ).length
                    }
                  </b>
                )}
            </a>
          ))}
          <p className="nav-caption">MANAGE</p>
          {NAV.slice(4).map((n) => (
            <a
              key={n.id}
              href={"#" + n.id}
              className={page === n.id ? "active" : ""}
              aria-current={page === n.id ? "page" : undefined}
            >
              <n.icon size={18} />
              <span>{n.label}</span>
            </a>
          ))}
        </nav>
        <div className="sidebar-bottom">
          <div className="agent-note">
            <span className="status-light" />
            <strong>
              {data.mode === "demo"
                ? "Explore the experience"
                : "Your sales workspace"}
            </strong>
            <p>
              {data.mode === "demo"
                ? "Sample leads. Simulated actions. A real workflow to explore."
                : "Conversations, opportunities and next steps in one place."}
            </p>
            <a
              href={appUrl("demo", data.business.id)}
              target="_blank"
              rel="noreferrer"
            >
              Preview your assistant <ArrowUpRight size={15} />
            </a>
          </div>
          <button
            className="profile"
            onClick={async () => {
              await api("/auth/logout", { method: "POST" });
              setUnauth(true);
            }}
          >
            <span className="profile-avatar">{initials(data.operator)}</span>
            <span>
              <strong>
                {data.operator === "Demo operator"
                  ? "Demo operator"
                  : data.operator}
              </strong>
              <small>Workspace administrator</small>
            </span>
            <LogOut size={16} />
          </button>
        </div>
      </aside>
      <main className="main-area">
        <header className="topbar">
          <div className="breadcrumb">
            <button
              className="icon-button mobile-menu"
              aria-label="Open navigation"
              onClick={() => setMobile(true)}
            >
              <PanelLeftOpen size={20} />
            </button>
            <span className="desktop-mark">
              <PanelLeftClose size={17} />
            </span>
            <span>Workspace</span>
            <ChevronRight size={13} />
            <strong>{active.label}</strong>
          </div>
          <div className="top-actions">
            <button
              className="quick-search"
              onClick={() => {
                go("leads");
                setTimeout(
                  () =>
                    document
                      .querySelector<HTMLInputElement>(".search-input input")
                      ?.focus(),
                  100,
                );
              }}
            >
              <Search size={16} />
              <span>Find a lead…</span>
              <kbd>⌕</kbd>
            </button>
            <button
              className="icon-button notification"
              aria-label="View automation activity"
              onClick={() => go("automations")}
            >
              <Bell size={19} />
              {data.jobs.some(
                (j) => j.status === "blocked" || j.status === "failed",
              ) && <i />}
            </button>
            <span className="top-avatar">
              {initials(data.business.short_name)}
            </span>
          </div>
        </header>
        {data.mode === "demo" && (
          <div className="demo-banner">
            <Sparkles size={14} />
            <span>
              {SHOWCASE
                ? "Portfolio demo · Fictional data · Browser-only edits"
                : "Demo workspace · Sample prospects and simulated integrations"}
            </span>
            {SHOWCASE && (
              <button
                className="text-button"
                onClick={async () => {
                  const { resetDemo } = await import("./showcase/api");
                  resetDemo();
                  location.reload();
                }}
              >
                Reset demo
              </button>
            )}
            <a
              href={appUrl("widget", data.business.id)}
              target="_blank"
              rel="noreferrer"
            >
              Try the assistant <ArrowUpRight size={13} />
            </a>
          </div>
        )}
        <div className="page-content page-enter" key={page} ref={pageRegion}>
          {error && (
            <div role="alert" className="error-banner">
              <AlertCircle size={17} />
              {error}
              <button onClick={refresh}>Retry</button>
            </div>
          )}
          {page === "overview" && (
            <Overview data={data} go={go} select={setSelected} />
          )}
          {page === "leads" && (
            <LeadPage
              data={data}
              query={query}
              setQuery={setQuery}
              select={setSelected}
            />
          )}
          {page === "conversations" && (
            <Conversations data={data} notify={notify} />
          )}
          {page === "meetings" && <Meetings data={data} />}
          {page === "sales-desk" && (
            <SalesDesk data={data} notify={notify} select={setSelected} />
          )}
          {page === "insights" && (
            <Insights key={data.business.id} data={data} />
          )}
          {page === "automations" && (
            <Automations data={data} notify={notify} />
          )}
          {page === "knowledge" && (
            <KnowledgePage data={data} notify={notify} />
          )}
          {page === "settings" && <SettingsPage data={data} notify={notify} />}
          {!NAV.some((n) => n.id === page) && (
            <Empty
              title="Page not found"
              description="Choose a workspace page from the navigation."
            />
          )}
          <footer className="page-footer">
            <span>
              <span className="status-light" /> Workspace connected
            </span>
            <span>Built for better conversations.</span>
          </footer>
        </div>
      </main>
      <LeadDetail
        lead={
          selected
            ? data.leads.find((l) => l.id === selected.id) || selected
            : null
        }
        close={() => setSelected(null)}
        notify={notify}
        viewConversation={() => {
          setSelected(null);
          go("conversations");
        }}
      />
      {toast && (
        <div className="toast" role="status">
          <Check size={17} />
          {toast}
        </div>
      )}
    </div>
  );
}

function Login({ onLogin }: { onLogin: () => Promise<boolean> }) {
  const [mode, setMode] = useState(SHOWCASE ? "demo" : ""),
    [business, setBusiness] = useState(
      new URLSearchParams(location.search).get("business") || "systematic",
    ),
    [email, setEmail] = useState(""),
    [password, setPassword] = useState(""),
    [busy, setBusy] = useState(false),
    [error, setError] = useState("");
  const submitting = useRef(false);
  useEffect(() => {
    api<{ mode: string }>("/health")
      .then((d) => setMode(d.mode))
      .catch(() =>
        setError("The backend is not reachable. Start the API and retry."),
      );
  }, []);
  async function login(demo = false) {
    if (submitting.current) return;
    submitting.current = true;
    setBusy(true);
    setError("");
    try {
      await api("/auth/" + (demo ? "demo" : "login"), {
        method: "POST",
        body: send({ business, email, password }),
      });
      if (!(await onLogin()))
        throw new Error(
          "Your workspace could not be loaded. Please try again.",
        );
    } catch (e) {
      setError((e as Error).message);
    } finally {
      submitting.current = false;
      setBusy(false);
    }
  }
  return (
    <div className="login-page login-enter">
      <div className="login-story">
        <a className="brand" href={appUrl()}>
          <span className="brand-mark">
            <Layers />
          </span>
          <span>systematic.</span>
        </a>
        <div>
          <span className="eyebrow">A MORE THOUGHTFUL SALES EXPERIENCE</span>
          <h1>
            Every conversation.
            <br />A new possibility<span>.</span>
          </h1>
          <p>
            Bring your knowledge, conversations and opportunities together. Give
            your team the context to make the next move.
          </p>
          <div className="login-proof">
            <ShieldCheck size={22} />
            <span>
              Your business. Your knowledge.
              <br />
              <strong>Your workspace.</strong>
            </span>
          </div>
        </div>
        <span className="login-copyright">SYSTEMATIC · SALES INTELLIGENCE</span>
      </div>
      <div className="login-form">
        <div className="login-form-inner">
          <span className="eyebrow">WELCOME TO YOUR WORKSPACE</span>
          <h2>Let's get to work.</h2>
          <p>
            {SHOWCASE
              ? "Explore a complete sales journey with fictional data. No account or backend required."
              : "Sign in to continue your sales conversations."}
          </p>
          {error && (
            <div role="alert" className="error-banner">
              {error}
            </div>
          )}
          <form
            onSubmit={(e) => {
              e.preventDefault();
              login(mode === "demo");
            }}
          >
            <label>
              Workspace ID
              <input
                value={business}
                disabled={busy}
                onChange={(e) => setBusiness(e.target.value)}
                required
                autoComplete="organization"
              />
            </label>
            {mode !== "demo" && (
              <>
                <label>
                  Email address
                  <input
                    type="email"
                    value={email}
                    onChange={(e) => setEmail(e.target.value)}
                    required
                    autoComplete="username"
                  />
                </label>
                <label>
                  Password
                  <input
                    type="password"
                    value={password}
                    onChange={(e) => setPassword(e.target.value)}
                    required
                    autoComplete="current-password"
                  />
                </label>
              </>
            )}
            {mode === "demo" ? (
              <button
                type="button"
                className="button primary full"
                disabled={busy}
                aria-busy={busy}
                onClick={() => login(true)}
              >
                {busy ? (
                  <>
                    <Loader2 size={17} className="spin" /> Opening workspace…
                  </>
                ) : (
                  <>
                    Open demo workspace <ArrowRight size={17} />
                  </>
                )}
              </button>
            ) : (
              <Submit busy={busy}>
                Sign in <ArrowRight size={17} />
              </Submit>
            )}
          </form>
          <p className="login-footnote">
            {mode === "demo"
              ? "Explore with fictional leads and simulated bookings. No external messages are sent."
              : "Access is limited to authorized workspace administrators."}
          </p>
          <a className="text-link" href={appUrl("demo", business)}>
            Explore the customer experience <ArrowUpRight size={14} />
          </a>
        </div>
      </div>
    </div>
  );
}

function PageIntro({
  eyebrow,
  title,
  description,
  children,
}: {
  eyebrow: string;
  title: string;
  description: string;
  children?: React.ReactNode;
}) {
  return (
    <div className="page-intro">
      <div>
        <span className="eyebrow">{eyebrow}</span>
        <h1>{title}</h1>
        <p>{description}</p>
      </div>
      <div className="intro-actions">{children}</div>
    </div>
  );
}

function Overview({
  data,
  go,
  select,
}: {
  data: Workspace;
  go: (s: string) => void;
  select: (l: Lead) => void;
}) {
  const [period, setPeriod] = useState(14);
  const since = Date.now() - period * 86400000,
    leads = data.leads.filter(
      (l) => Date.parse(l.created_at) > since && !!(l.email || l.phone),
    ),
    convs = data.conversations.filter((c) => Date.parse(c.created_at) > since),
    meetings = data.meetings
      .filter(
        (m) =>
          Date.parse(m.start_at) > Date.now() &&
          ["booked", "simulated"].includes(m.status),
      )
      .sort((a, b) => a.start_at.localeCompare(b.start_at)),
    hot = leads.filter((l) => l.lead_classification === "Hot");
  const cohort = data.period_counts?.[String(period)];
  const cards = [
    {
      label: "Contactable inquiries",
      value: cohort?.contactable ?? leads.length,
      icon: Users,
      detail: "Sessions with contact details",
      color: "green",
      page: "leads",
    },
    {
      label: "High-priority leads",
      value: hot.length,
      icon: Flame,
      detail: "Based on qualification signals",
      color: "orange",
      page: "leads",
    },
    {
      label: "Conversations",
      value: cohort?.engaged ?? convs.length,
      icon: MessagesSquare,
      detail: "Every question is an opportunity",
      color: "purple",
      page: "conversations",
    },
    {
      label: "Upcoming meetings",
      value: meetings.length,
      icon: CalendarDays,
      detail: "Your next conversations",
      color: "blue",
      page: "meetings",
    },
  ];
  const recent = [...leads]
    .sort((a, b) => b.lead_score - a.lead_score)
    .slice(0, 5);
  return (
    <>
      <PageIntro
        eyebrow="YOUR SALES COMMAND CENTER"
        title="Good conversations start here."
        description="A clear view of your pipeline, and the next steps that matter."
      >
        <select
          className="period-select"
          aria-label="Reporting period"
          value={period}
          onChange={(e) => setPeriod(Number(e.target.value))}
        >
          <option value={7}>Last 7 days</option>
          <option value={14}>Last 14 days</option>
          {SHOWCASE && <option value={30}>Last 30 days</option>}
          {SHOWCASE && <option value={90}>Last 90 days</option>}
        </select>
        <a
          className="button primary"
          href={appUrl("demo", data.business.id)}
          target="_blank"
          rel="noreferrer"
        >
          <Sparkles size={16} />
          Preview assistant
          <ArrowUpRight size={15} />
        </a>
      </PageIntro>
      <div className="metric-grid">
        {cards.map((c) => (
          <a
            className="metric-card metric-link"
            href={"#" + c.page}
            key={c.label}
            aria-label={`Open ${c.label.toLowerCase()}`}
          >
            <div className="metric-top">
              <span>{c.label}</span>
              <span className={"metric-icon " + c.color}>
                <c.icon size={18} />
              </span>
            </div>
            <strong className="metric-value">
              {c.value.toString().padStart(2, "0")}
            </strong>
            <div className="metric-foot">
              <span>{c.detail}</span>
              <ArrowUpRight size={15} aria-hidden="true" />
            </div>
          </a>
        ))}
      </div>
      <div className="overview-middle">
        <section className="panel chart-panel">
          <SectionHeader
            title="Conversation activity"
            sub="A daily view of new conversations and lead records."
            action={
              <span className="analytics-panel-icon">
                <BarChart3 size={18} />
              </span>
            }
          />
          <ActivityChart rows={data.trend.slice(-period)} />
          <div className="chart-bottom">
            <span>
              <Activity size={15} />
              Measured from saved workspace activity
            </span>
            <button className="text-button" onClick={() => go("conversations")}>
              Explore conversations <ArrowRight size={14} />
            </button>
          </div>
        </section>
        <section className="panel pipeline-panel">
          <SectionHeader
            title="Your opportunity funnel"
            sub="Current outcomes for sessions started in this period."
          />
          <div className="funnel">
            {[
              {
                name: "Engaged sessions",
                value: cohort?.engaged ?? convs.length,
                color: "funnel-1",
              },
              {
                name: "Contactable inquiries",
                value: cohort?.contactable ?? leads.length,
                color: "funnel-2",
              },
              {
                name: "Qualified & progressing",
                value:
                  cohort?.progressing ??
                  leads.filter((l) =>
                    [
                      "qualified",
                      "meeting_booked",
                      "meeting_attended",
                      "proposal_requested",
                      "proposal_sent",
                      "won",
                    ].includes(l.stage),
                  ).length,
                color: "funnel-3",
              },
              {
                name: "Customers won",
                value:
                  cohort?.won ?? leads.filter((l) => l.stage === "won").length,
                color: "funnel-4",
              },
            ].map((f, i) => (
              <div className="funnel-row" key={f.name}>
                <div>
                  <span>
                    <b>0{i + 1}</b>
                    {f.name}
                  </span>
                  <strong>{f.value}</strong>
                </div>
                <div className="funnel-track">
                  <span
                    className={f.color}
                    style={{
                      width:
                        Math.min(
                          (f.value /
                            Math.max(cohort?.engaged ?? convs.length, 1)) *
                            100,
                          100,
                        ) + "%",
                    }}
                  />
                </div>
              </div>
            ))}
          </div>
          <div className="funnel-note">
            <Target size={17} />
            <span>
              Focus on fit.
              <br />
              <strong>Make every next step count.</strong>
            </span>
          </div>
        </section>
      </div>
      <div className="overview-bottom">
        <section className="panel">
          <SectionHeader
            title="Leads worth a closer look"
            sub="Your highest-priority conversations."
            action={
              <button className="text-button" onClick={() => go("leads")}>
                View all leads <ArrowUpRight size={15} />
              </button>
            }
          />
          <LeadTable leads={recent} select={select} compact />
          {!recent.length && (
            <Empty
              title="Your pipeline starts here"
              description="New inquiries from the assistant will appear in this workspace."
            />
          )}
        </section>
        <section className="panel next-panel">
          <SectionHeader
            title="Up next"
            sub="Keep the conversation moving."
            action={<CalendarDays size={18} />}
          />
          {meetings.length ? (
            meetings.slice(0, 3).map((m) => (
              <div className="meeting-mini" key={m.id}>
                <div className="date-tile">
                  <span>{dateLabel(m.start_at, { month: "short" })}</span>
                  <strong>{new Date(m.start_at).getDate()}</strong>
                </div>
                <div>
                  <strong>{m.name}</strong>
                  <p>{m.service}</p>
                  <small>
                    {new Date(m.start_at).toLocaleTimeString("en-US", {
                      hour: "numeric",
                      minute: "2-digit",
                    })}{" "}
                    · {m.status === "simulated" ? "Demo booking" : m.timezone}
                  </small>
                </div>
              </div>
            ))
          ) : (
            <Empty
              title="Room for opportunity"
              description="Confirmed consultations will appear here."
            />
          )}
          <div className="tip-card">
            <div>
              <Sparkles size={18} />
              <span>THE NEXT BEST STEP</span>
            </div>
            <p>Context makes a better first impression.</p>
            <small>
              Review the visitor’s goals and conversation before your
              consultation.
            </small>
            <button className="text-button" onClick={() => go("leads")}>
              Review your pipeline <ArrowRight size={14} />
            </button>
          </div>
        </section>
      </div>
    </>
  );
}

function LeadTable({
  leads,
  select,
  compact = false,
}: {
  leads: Lead[];
  select: (l: Lead) => void;
  compact?: boolean;
}) {
  return (
    <div className="table-scroll">
      <table>
        <thead>
          <tr>
            <th>Lead / company</th>
            <th>Interested in</th>
            <th>Priority</th>
            {!compact && <th>Stage</th>}
            <th>Score</th>
            <th>
              <span className="sr-only">Details</span>
            </th>
          </tr>
        </thead>
        <tbody>
          {leads.map((l, i) => (
            <tr key={l.id}>
              <td>
                <button className="person-cell" onClick={() => select(l)}>
                  <span className={"avatar avatar-" + (i % 5)}>
                    {initials(l.full_name || "Visitor")}
                  </span>
                  <span>
                    <strong>{l.full_name || "Anonymous visitor"}</strong>
                    <small>
                      {l.company_name || l.email || "Exploring services"}
                    </small>
                  </span>
                </button>
              </td>
              <td>
                <span className="service-tag">
                  {l.required_services[0] || "Discovery"}
                </span>
              </td>
              <td>
                <Badge value={l.lead_classification} />
              </td>
              {!compact && (
                <td>
                  <span className="stage-label">{label(l.stage)}</span>
                </td>
              )}
              <td>
                <div className="score-cell">
                  <strong>{l.lead_score}</strong>
                  <span>
                    <i style={{ width: l.lead_score + "%" }} />
                  </span>
                </div>
              </td>
              <td>
                <button
                  className="icon-button"
                  aria-label={"View " + (l.full_name || "visitor")}
                  onClick={() => select(l)}
                >
                  <ArrowUpRight size={17} />
                </button>
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

function LeadPage({
  data,
  query,
  setQuery,
  select,
}: {
  data: Workspace;
  query: string;
  setQuery: (s: string) => void;
  select: (l: Lead) => void;
}) {
  const [filter, setFilter] = useState("All"),
    [stage, setStage] = useState("all"),
    [tablePage, setTablePage] = useState(0);
  useEffect(() => setTablePage(0), [filter, stage, query]);
  const leads = data.leads.filter(
    (l) =>
      (filter === "All" || l.lead_classification === filter) &&
      (stage === "all" || l.stage === stage) &&
      [l.full_name, l.company_name, l.email, ...l.required_services]
        .join(" ")
        .toLowerCase()
        .includes(query.toLowerCase()),
  );
  return (
    <>
      <PageIntro
        eyebrow="BUILD RELATIONSHIPS THAT CONVERT"
        title="Your lead pipeline."
        description="Understand the person behind the inquiry. Make the next move count."
      >
        <a
          className="button secondary"
          href={SHOWCASE ? "#leads" : "/api/admin/leads/export"}
          onClick={
            SHOWCASE
              ? async (event) => {
                  event.preventDefault();
                  const { downloadDemoCsv } = await import("./showcase/api");
                  downloadDemoCsv(leads);
                }
              : undefined
          }
        >
          <Download size={16} />
          Export CSV
        </a>
      </PageIntro>
      <section className="panel">
        <div className="table-toolbar">
          <div className="tabs">
            {["All", "Hot", "Warm", "Cold"].map((f) => (
              <button
                className={filter === f ? "selected" : ""}
                onClick={() => setFilter(f)}
                key={f}
              >
                {f === "All" ? "All leads" : f}
                <span>
                  {
                    data.leads.filter(
                      (l) => f === "All" || l.lead_classification === f,
                    ).length
                  }
                </span>
              </button>
            ))}
          </div>
          <div className="filter-tools">
            <SearchBox
              value={query}
              onChange={setQuery}
              placeholder="Search name, company, service…"
            />
            <select
              aria-label="Filter by stage"
              value={stage}
              onChange={(e) => setStage(e.target.value)}
            >
              <option value="all">All stages</option>
              {STAGES.map((s) => (
                <option key={s} value={s}>
                  {label(s)}
                </option>
              ))}
            </select>
          </div>
        </div>
        <LeadTable
          leads={leads.slice(tablePage * 25, (tablePage + 1) * 25)}
          select={select}
        />
        {!leads.length && (
          <Empty
            title="No matching leads"
            description="Try another search or filter. New inquiries will appear here."
          />
        )}
        <div className="table-footer">
          {leads.length} of {data.leads.length} leads{" "}
          {leads.length > 25 && (
            <div className="pagination" aria-label="Lead table pages">
              <button
                className="button secondary small"
                disabled={tablePage === 0}
                onClick={() => setTablePage((p) => p - 1)}
              >
                Previous
              </button>
              <span>
                Page {tablePage + 1} of {Math.ceil(leads.length / 25)}
              </span>
              <button
                className="button secondary small"
                disabled={(tablePage + 1) * 25 >= leads.length}
                onClick={() => setTablePage((p) => p + 1)}
              >
                Next
              </button>
            </div>
          )}
          <span>Scores prioritize review; they don't guarantee a sale.</span>
        </div>
      </section>
    </>
  );
}

function LeadDetail({
  lead,
  close,
  notify,
  viewConversation,
}: {
  lead: Lead | null;
  close: () => void;
  notify: (s: string) => void;
  viewConversation: () => void;
}) {
  const [busy, setBusy] = useState(false),
    [error, setError] = useState("");
  async function save(e: FormEvent<HTMLFormElement>) {
    e.preventDefault();
    if (!lead) return;
    setBusy(true);
    setError("");
    const f = new FormData(e.currentTarget);
    try {
      await api("/admin/leads/" + lead.id, {
        method: "PATCH",
        body: send(Object.fromEntries(f)),
      });
      notify("Lead updated");
      close();
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setBusy(false);
    }
  }
  return (
    <Modal
      open={!!lead}
      onClose={close}
      title={lead?.full_name || "Visitor profile"}
      description={
        lead?.company_name ||
        "Understand the opportunity and choose a next step."
      }
      wide
    >
      {lead && (
        <div className="lead-detail">
          <RelatedInquiries lead={lead} />
          <div className="lead-contact">
            <Badge value={lead.lead_classification} />
            <span>{lead.email || "No email shared"}</span>
            {lead.sample && <span className="muted">Sample prospect</span>}
          </div>
          <div className="detail-grid">
            <div>
              <span className="field-caption">BUSINESS GOAL</span>
              <p>{lead.business_goal || "Not shared yet"}</p>
              <span className="field-caption">SERVICES</span>
              <p>
                {lead.required_services.join(", ") || "Discovery in progress"}
              </p>
              <div className="detail-pair">
                <div>
                  <span className="field-caption">BUDGET</span>
                  <p>{lead.budget_range || "Not shared"}</p>
                </div>
                <div>
                  <span className="field-caption">TIMELINE</span>
                  <p>{lead.timeline || "Not shared"}</p>
                </div>
              </div>
            </div>
            <div className="score-breakdown">
              <span className="field-caption">QUALIFICATION SCORE</span>
              <strong>
                {lead.lead_score}
                <small>/ 100</small>
              </strong>
              {lead.score_reasons.map((r) => (
                <div key={r.component}>
                  <span title={r.reason}>{label(r.component)}</span>
                  <b>{r.score}</b>
                </div>
              ))}
            </div>
          </div>
          <form onSubmit={save}>
            <div className="form-grid">
              <label>
                Pipeline stage
                <select name="stage" defaultValue={lead.stage}>
                  {STAGES.map((s) => (
                    <option key={s} value={s}>
                      {label(s)}
                    </option>
                  ))}
                </select>
              </label>
              <label>
                Assigned owner
                <input
                  name="assigned_sales_rep"
                  defaultValue={lead.assigned_sales_rep || ""}
                  placeholder="Sales representative"
                  maxLength={100}
                />
              </label>
            </div>
            <label>
              Next action
              <input
                name="next_action"
                defaultValue={lead.next_action || ""}
                maxLength={500}
              />
            </label>
            <label htmlFor="lead-consent">
              Email follow-up permission
              <select
                id="lead-consent"
                aria-describedby="lead-consent-help"
                name="consent_status"
                defaultValue={lead.consent_status || "not_requested"}
              >
                <option value="not_requested">Not requested</option>
                <option value="granted">
                  Granted — explicit permission verified
                </option>
                <option value="declined">
                  Declined — stop email follow-ups
                </option>
              </select>
            </label>
            <small id="lead-consent-help">
              Only mark permission granted after confirming the contact
              explicitly opted in. Changes are recorded.
            </small>
            <div className="form-grid">
              <label>
                Due date
                <input
                  type="datetime-local"
                  name="due_at"
                  defaultValue={lead.due_at?.slice(0, 16) || ""}
                />
              </label>
              <label>
                Lost reason (if applicable)
                <input
                  name="lost_reason"
                  defaultValue={lead.lost_reason || ""}
                  placeholder="Budget, timing, service fit…"
                  maxLength={500}
                />
              </label>
            </div>
            <label>
              Add a note
              <textarea
                name="note"
                placeholder="Context your team should know…"
                rows={2}
                maxLength={2000}
              />
            </label>
            {lead.notes?.length > 0 && (
              <div className="notes">
                {lead.notes.map((n, i) => (
                  <p key={i}>
                    {n.text}
                    <small>
                      {n.author} · {dateLabel(n.created_at)}
                    </small>
                  </p>
                ))}
              </div>
            )}
            {error && (
              <p role="alert" className="error-text">
                {error}
              </p>
            )}
            <div className="modal-actions">
              <button
                type="button"
                className="button secondary"
                onClick={viewConversation}
              >
                View conversations
              </button>
              <Submit busy={busy}>Save changes</Submit>
            </div>
          </form>
        </div>
      )}
    </Modal>
  );
}

function Conversations({
  data,
  notify,
}: {
  data: Workspace;
  notify: (s: string) => void;
}) {
  const [selected, setSelected] = useState<Conversation | null>(null),
    [query, setQuery] = useState(""),
    [reply, setReply] = useState(""),
    [error, setError] = useState(""),
    [opening, setOpening] = useState(false),
    [conversationLimit, setConversationLimit] = useState(40),
    [busy, setBusy] = useState(false);
  const requestedConversation = useRef<string | null>(null);
  const readVersion = useRef(0);
  const pendingRead = useRef<AbortController | null>(null);
  const mutating = useRef(false);
  const select = useCallback(async (id: string) => {
    if (mutating.current) return;
    const version = ++readVersion.current;
    pendingRead.current?.abort();
    const controller = new AbortController();
    pendingRead.current = controller;
    if (requestedConversation.current !== id) {
      setSelected(null);
      setReply("");
      setOpening(true);
      setError("");
    }
    requestedConversation.current = id;
    try {
      const conversation = await api<Conversation>(
        "/admin/conversations/" + id,
        {
          signal: controller.signal,
        },
      );
      if (version === readVersion.current) {
        setSelected(conversation);
        setError("");
      }
    } catch (e) {
      if (version === readVersion.current) setError((e as Error).message);
    } finally {
      if (version === readVersion.current) setOpening(false);
    }
  }, []);
  useEffect(
    () => () => {
      readVersion.current++;
      pendingRead.current?.abort();
    },
    [],
  );
  useEffect(() => {
    if (!selected) return;
    const t = setInterval(() => select(selected.id), 5000);
    return () => clearInterval(t);
  }, [selected?.id, select]);
  async function action(kind: string) {
    if (!selected || mutating.current) return;
    mutating.current = true;
    // A poll started before this mutation must not restore stale ownership
    // or erase a reply after the server accepts it.
    const version = ++readVersion.current;
    pendingRead.current?.abort();
    setBusy(true);
    setError("");
    try {
      const result = await api<Conversation>(
        "/admin/conversations/" + selected.id + "/" + kind,
        {
          method: "POST",
          body: kind === "reply" ? send({ message: reply }) : undefined,
        },
      );
      if (version !== readVersion.current) return;
      setSelected(result);
      setReply("");
      notify(
        kind === "reply"
          ? "Reply added to the visitor conversation"
          : "Conversation ownership updated",
      );
    } catch (e) {
      if (version === readVersion.current) setError((e as Error).message);
    } finally {
      mutating.current = false;
      setBusy(false);
    }
  }
  const list = data.conversations.filter((c) =>
    [
      data.leads.find((l) => l.id === c.lead_id)?.full_name,
      ...c.messages.map((m) => m.content),
    ]
      .join(" ")
      .toLowerCase()
      .includes(query.toLowerCase()),
  );
  const lead = selected
    ? data.leads.find((l) => l.id === selected.lead_id)
    : null;
  return (
    <>
      <PageIntro
        eyebrow="CONTEXT MAKES THE DIFFERENCE"
        title="Every conversation, connected."
        description="Review the journey, understand the need, and step in when it matters."
      />
      <section className="panel inbox">
        <div className="inbox-list">
          <SearchBox
            value={query}
            onChange={setQuery}
            placeholder="Search conversations…"
          />
          {list.slice(0, conversationLimit).map((c) => {
            const l = data.leads.find((l) => l.id === c.lead_id);
            return (
              <button
                key={c.id}
                disabled={busy}
                className={
                  "inbox-item " + (selected?.id === c.id ? "selected" : "")
                }
                onClick={() => select(c.id)}
              >
                <span className="avatar">
                  {initials(l?.full_name || "Visitor")}
                </span>
                <div>
                  <strong>{l?.full_name || "Website visitor"}</strong>
                  <p>{c.messages.at(-1)?.content || "Conversation started"}</p>
                  <small>
                    {label(c.status)} · {dateLabel(c.updated_at)}
                  </small>
                </div>
              </button>
            );
          })}
          {list.length > conversationLimit && (
            <button
              className="button secondary full"
              onClick={() => setConversationLimit((n) => n + 40)}
            >
              Show more conversations ({list.length - conversationLimit})
            </button>
          )}
          {!list.length && (
            <Empty
              title="No conversations yet"
              description="Visitor messages appear here."
            />
          )}
        </div>
        <div className="inbox-main">
          {selected ? (
            <>
              <div className="inbox-header">
                <div>
                  <h3>{lead?.full_name || "Website visitor"}</h3>
                  <p>
                    {lead?.company_name || "Website inquiry"} ·{" "}
                    {label(selected.status)}
                  </p>
                </div>
                <button
                  className="button secondary"
                  disabled={busy}
                  onClick={() => action("takeover")}
                >
                  {selected.status === "human"
                    ? "Return to assistant"
                    : "Take over conversation"}
                </button>
              </div>
              {lead && (
                <div className="conversation-summary">
                  <Sparkles size={15} />
                  <span>
                    {lead.required_services.join(", ") || "Service discovery"} ·{" "}
                    {lead.business_goal || "Goal not yet shared"} · Next:{" "}
                    {lead.next_action || "Review requirements"}
                  </span>
                </div>
              )}
              <div className="message-list">
                {selected.messages.map((m) => (
                  <div key={m.id} className={"message " + m.role}>
                    <span className="message-author">
                      {m.role === "user"
                        ? "Visitor"
                        : m.author || "AI assistant"}
                    </span>
                    <p>{m.content}</p>
                    <small>
                      {new Date(m.created_at).toLocaleTimeString("en-US", {
                        hour: "2-digit",
                        minute: "2-digit",
                      })}
                    </small>
                  </div>
                ))}
              </div>
              <form
                className="reply-form"
                onSubmit={(e) => {
                  e.preventDefault();
                  action("reply");
                }}
              >
                <input
                  aria-label="Reply to visitor"
                  placeholder={
                    selected.status === "human"
                      ? "Write a reply to the visitor…"
                      : "Take over this conversation to reply"
                  }
                  value={reply}
                  onChange={(e) => setReply(e.target.value)}
                  disabled={busy || selected.status !== "human"}
                  maxLength={2000}
                />
                <button
                  className="button primary"
                  disabled={
                    busy || !reply.trim() || selected.status !== "human"
                  }
                >
                  Send <ArrowRight size={16} />
                </button>
              </form>
            </>
          ) : opening ? (
            <div className="analytics-empty" role="status">
              Opening conversation…
            </div>
          ) : (
            <Empty
              title="A little context goes a long way."
              description="Select a conversation to review messages, qualification details and the next step."
            />
          )}
          {error && (
            <p role="alert" className="error-text">
              {error}
            </p>
          )}
        </div>
      </section>
    </>
  );
}

function Meetings({ data }: { data: Workspace }) {
  return (
    <>
      <PageIntro
        eyebrow="TURN INTEREST INTO A CONVERSATION"
        title="Make time for opportunity."
        description="Your consultation schedule, with the context to start well."
      >
        <a
          className="button primary"
          href={appUrl("widget", data.business.id)}
          target="_blank"
          rel="noreferrer"
        >
          Test booking flow <ArrowUpRight size={16} />
        </a>
      </PageIntro>
      <section className="panel">
        <SectionHeader
          title="Scheduled consultations"
          sub={"Business timezone: " + data.business.timezone}
        />
        {data.meetings.length ? (
          <div className="table-scroll">
            <table>
              <thead>
                <tr>
                  <th>Contact</th>
                  <th>Service</th>
                  <th>Date & time</th>
                  <th>Status</th>
                </tr>
              </thead>
              <tbody>
                {[...data.meetings]
                  .sort((a, b) => a.start_at.localeCompare(b.start_at))
                  .map((m) => (
                    <tr key={m.id}>
                      <td>
                        <strong>{m.name}</strong>
                        <small className="block muted">{m.email}</small>
                      </td>
                      <td>{m.service}</td>
                      <td>
                        {new Date(m.start_at).toLocaleString("en-US", {
                          timeZone: m.timezone,
                          dateStyle: "medium",
                          timeStyle: "short",
                        })}
                        <small className="block muted">{m.timezone}</small>
                      </td>
                      <td>
                        <Badge value={m.status} />
                      </td>
                    </tr>
                  ))}
              </tbody>
            </table>
          </div>
        ) : (
          <Empty
            title="Your calendar has room."
            description="Appointments confirmed through the assistant will appear here."
          />
        )}
      </section>
      <div className="info-card">
        <ShieldCheck size={20} />
        <p>
          Bookings require a selected slot, valid contact details and explicit
          confirmation. Demo appointments never create external calendar events.
        </p>
      </div>
    </>
  );
}

function Automations({
  data,
  notify,
}: {
  data: Workspace;
  notify: (s: string) => void;
}) {
  const [busy, setBusy] = useState(false),
    [error, setError] = useState("");
  async function run(path: string) {
    setBusy(true);
    setError("");
    try {
      await api(path, { method: "POST" });
      notify("Automation queue updated");
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setBusy(false);
    }
  }
  return (
    <>
      <PageIntro
        eyebrow="THE FOLLOW-THROUGH MATTERS"
        title="Work that keeps moving."
        description="Notifications, follow-ups and sync jobs. Tracked from request to result."
      >
        {data.mode === "demo" && (
          <button
            className="button primary"
            disabled={busy}
            onClick={() => run("/admin/jobs/demo-process")}
          >
            <Workflow size={16} />
            Process demo jobs
          </button>
        )}
      </PageIntro>
      <div className="integration-grid">
        {data.integrations
          .filter((i) => i.id !== "ai")
          .map((i) => (
            <div className="panel integration-card" key={i.id}>
              <div className="integration-icon">
                <Workflow size={21} />
              </div>
              <div>
                <h3>
                  {
                    (
                      {
                        calendar: "Google Calendar",
                        email: "Email notifications",
                        sheets: "Google Sheets",
                        crm: "CRM webhook",
                      } as Record<string, string>
                    )[i.id]
                  }
                </h3>
                <p>
                  {i.id === "calendar"
                    ? "Confirmed consultation scheduling"
                    : i.id === "email"
                      ? "Sales alerts and agreed follow-ups"
                      : i.id === "sheets"
                        ? "Lead records, synchronized"
                        : "Connect your business systems"}
                </p>
                <Badge value={i.status} />
                <small className="block muted">
                  {i.enabled ? "Enabled" : "Disabled"} ·{" "}
                  {i.configured
                    ? "Credentials present; live verification required"
                    : "Setup required for live delivery"}
                </small>
              </div>
            </div>
          ))}
      </div>
      {error && (
        <p role="alert" className="error-text">
          {error}
        </p>
      )}
      {(data.booking_reviews || []).length > 0 && (
        <section className="panel" style={{ marginBottom: 20 }}>
          <SectionHeader
            title="Bookings needing review"
            sub="Verify uncertain external outcomes before allowing a retry."
          />
          {data.booking_reviews.map((r) => (
            <div className="table-toolbar" key={r.id}>
              <span>
                {r.name} ? {label(r.status)}
              </span>
              <button
                className="button secondary"
                disabled={busy}
                onClick={() => run("/admin/bookings/" + r.id + "/reconcile")}
              >
                Verify booking outcome
              </button>
            </div>
          ))}
        </section>
      )}
      <section className="panel">
        <SectionHeader
          title="Delivery activity"
          sub="Jobs survive restarts. Failed deliveries can be reviewed and retried."
        />
        {data.jobs.length ? (
          <div className="table-scroll">
            <table>
              <thead>
                <tr>
                  <th>Operation</th>
                  <th>Status</th>
                  <th>Attempts</th>
                  <th>Scheduled</th>
                  <th>Details</th>
                  <th />
                </tr>
              </thead>
              <tbody>
                {data.jobs.map((j) => (
                  <tr key={j.id}>
                    <td>
                      <strong>{label(j.kind)}</strong>
                      <small className="block muted">{j.id.slice(0, 10)}</small>
                    </td>
                    <td>
                      <Badge value={j.status} />
                    </td>
                    <td>{j.attempts}</td>
                    <td>
                      {new Date(j.due * 1000).toLocaleString("en-US", {
                        dateStyle: "short",
                        timeStyle: "short",
                      })}
                    </td>
                    <td className="job-error">{j.error || "—"}</td>
                    <td>
                      {["failed", "blocked"].includes(j.status) && (
                        <button
                          className="button secondary small"
                          disabled={busy}
                          onClick={() => run("/admin/jobs/" + j.id + "/retry")}
                        >
                          <RefreshCw size={13} />
                          Retry
                        </button>
                      )}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        ) : (
          <Empty
            title="Ready for the next event"
            description="New leads, booking confirmations and requests create tracked automation jobs."
          />
        )}
      </section>
    </>
  );
}

function KnowledgePage({
  data,
  notify,
}: {
  data: Workspace;
  notify: (s: string) => void;
}) {
  const [query, setQuery] = useState(""),
    [type, setType] = useState("all"),
    [open, setOpen] = useState(false),
    [busy, setBusy] = useState(false),
    [error, setError] = useState(""),
    [limit, setLimit] = useState(20),
    [remove, setRemove] = useState<Knowledge | null>(null);
  const docs = data.knowledge.filter(
    (d) =>
      (type === "all" || d.type === type) &&
      [d.title, d.content]
        .join(" ")
        .toLowerCase()
        .includes(query.toLowerCase()),
  );
  async function add(e: FormEvent<HTMLFormElement>) {
    e.preventDefault();
    setBusy(true);
    setError("");
    try {
      await api("/admin/knowledge", {
        method: "POST",
        body: send(Object.fromEntries(new FormData(e.currentTarget))),
      });
      notify("Knowledge added to this business");
      setOpen(false);
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setBusy(false);
    }
  }
  async function del() {
    if (!remove) return;
    setBusy(true);
    try {
      await api("/admin/knowledge/" + remove.id, { method: "DELETE" });
      setRemove(null);
      notify("Knowledge entry removed");
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setBusy(false);
    }
  }
  return (
    <>
      <PageIntro
        eyebrow="ANSWERS START WITH GOOD KNOWLEDGE"
        title="Your business, understood."
        description="Keep services, pricing and answers grounded in information you trust."
      >
        <button
          className="button primary"
          onClick={() => {
            setError("");
            setOpen(true);
          }}
        >
          <Plus size={17} />
          Add knowledge
        </button>
      </PageIntro>
      <div className="knowledge-summary">
        <div>
          <BookOpen size={22} />
          <strong>{data.knowledge.length}</strong>
          <span>Knowledge entries</span>
        </div>
        <div>
          <Globe size={22} />
          <strong>
            {new Set(data.knowledge.map((d) => d.source_url)).size}
          </strong>
          <span>Source pages</span>
        </div>
        <div>
          <ShieldCheck size={22} />
          <strong>Business scoped</strong>
          <span>Separate knowledge for each workspace</span>
        </div>
      </div>
      <section className="panel">
        <div className="table-toolbar">
          <SearchBox
            value={query}
            onChange={(v) => {
              setQuery(v);
              setLimit(20);
            }}
            placeholder="Search your knowledge…"
          />
          <select
            aria-label="Knowledge category"
            value={type}
            onChange={(e) => setType(e.target.value)}
          >
            <option value="all">All categories</option>
            {[...new Set(data.knowledge.map((d) => d.type))].map((t) => (
              <option key={t} value={t}>
                {label(t)}
              </option>
            ))}
          </select>
        </div>
        <div className="knowledge-list">
          {docs.slice(0, limit).map((d) => (
            <article key={d.id}>
              <div className="document-icon">
                <BookOpen size={18} />
              </div>
              <div>
                <div className="knowledge-title">
                  <h3>{d.title}</h3>
                  <span className="service-tag">{label(d.type)}</span>
                </div>
                <p>{d.content}</p>
                {d.source_url && (
                  <a href={d.source_url} target="_blank" rel="noreferrer">
                    {new URL(d.source_url).hostname}
                    <ArrowUpRight size={12} />
                  </a>
                )}
              </div>
              <button
                className="text-button muted"
                onClick={() => {
                  setError("");
                  setRemove(d);
                }}
              >
                Remove
              </button>
            </article>
          ))}
        </div>
        {!docs.length && (
          <Empty
            title="No matching knowledge"
            description="Try another search or add an approved business answer."
          />
        )}
        {docs.length > limit && (
          <div className="table-footer">
            <button
              className="button secondary small"
              onClick={() => setLimit(limit + 20)}
            >
              Show more entries
            </button>
            <span>
              {limit} of {docs.length}
            </span>
          </div>
        )}
      </section>
      <Modal
        open={open}
        onClose={() => setOpen(false)}
        title="Add business knowledge"
        description="Add approved information. It becomes available to this workspace's assistant."
      >
        <form onSubmit={add}>
          <label>
            Title
            <input name="title" required minLength={2} maxLength={150} />
          </label>
          <label>
            Category
            <select name="type">
              {[
                "faq",
                "service_overview",
                "pricing",
                "company_information",
                "process",
              ].map((t) => (
                <option key={t} value={t}>
                  {label(t)}
                </option>
              ))}
            </select>
          </label>
          <label>
            Approved answer or information
            <textarea
              name="content"
              rows={6}
              required
              minLength={20}
              maxLength={12000}
            />
          </label>
          <label>
            Source URL (optional)
            <input
              name="source_url"
              type="url"
              placeholder={data.business.website}
            />
          </label>
          {error && (
            <p className="error-text" role="alert">
              {error}
            </p>
          )}
          <div className="modal-actions">
            <Submit busy={busy}>Add knowledge</Submit>
          </div>
        </form>
      </Modal>
      <Modal
        open={!!remove}
        onClose={() => setRemove(null)}
        title="Remove knowledge entry?"
        description="This removes the entry from this workspace's local retrieval. Your frozen source files are preserved."
      >
        <p>{remove?.title}</p>
        {error && <p className="error-text">{error}</p>}
        <div className="modal-actions">
          <button className="button secondary" onClick={() => setRemove(null)}>
            Keep entry
          </button>
          <button className="button danger" disabled={busy} onClick={del}>
            Remove entry
          </button>
        </div>
      </Modal>
    </>
  );
}

function SettingsPage({
  data,
  notify,
}: {
  data: Workspace;
  notify: (s: string) => void;
}) {
  const [b, setB] = useState<Business>(data.business),
    [busy, setBusy] = useState(false),
    [error, setError] = useState(""),
    [copied, setCopied] = useState(false);
  const embed = `<script src="${location.origin}/embed.js" data-business="${b.id}" defer></script>`;
  async function save(e: FormEvent) {
    e.preventDefault();
    setBusy(true);
    setError("");
    const {
      name,
      short_name,
      welcome,
      tagline,
      accent,
      services,
      timezone,
      qualification,
      notification_email,
      followup_hours,
      integrations,
    } = b;
    try {
      await api("/admin/settings", {
        method: "PATCH",
        body: send({
          name,
          short_name,
          welcome,
          tagline,
          accent,
          services,
          timezone,
          qualification,
          notification_email,
          followup_hours,
          integrations,
        }),
      });
      notify("Workspace settings saved");
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setBusy(false);
    }
  }
  return (
    <>
      <PageIntro
        eyebrow="MAKE IT YOUR OWN"
        title="One workspace. Your way."
        description="Business identity, qualification rules and integration preferences."
      />
      <form onSubmit={save}>
        <div className="settings-layout">
          <section className="panel settings-card">
            <SectionHeader
              title="Business & assistant"
              sub="The identity your visitors will recognize."
            />
            <div className="form-grid">
              <label>
                Business name
                <input
                  value={b.name}
                  onChange={(e) => setB({ ...b, name: e.target.value })}
                  required
                  maxLength={100}
                />
              </label>
              <label>
                Short name
                <input
                  value={b.short_name}
                  onChange={(e) => setB({ ...b, short_name: e.target.value })}
                  required
                  maxLength={30}
                />
              </label>
            </div>
            <label>
              Welcome message
              <textarea
                value={b.welcome}
                onChange={(e) => setB({ ...b, welcome: e.target.value })}
                rows={3}
                maxLength={800}
              />
            </label>
            <div className="form-grid">
              <label>
                Brand accent
                <input
                  type="color"
                  value={b.accent}
                  onChange={(e) => setB({ ...b, accent: e.target.value })}
                />
              </label>
              <label>
                Timezone
                <input
                  value={b.timezone}
                  onChange={(e) => setB({ ...b, timezone: e.target.value })}
                  required
                />
              </label>
            </div>
            <label>
              Service catalog (one per line)
              <textarea
                rows={5}
                value={b.services.join("\n")}
                onChange={(e) =>
                  setB({ ...b, services: e.target.value.split("\n") })
                }
              />
            </label>
          </section>
          <section className="panel settings-card">
            <SectionHeader
              title="Qualification & follow-through"
              sub="Make lead priority match your sales process."
            />
            <div className="form-grid">
              <label>
                Hot lead threshold
                <input
                  type="number"
                  min={1}
                  max={100}
                  value={b.qualification.hot_threshold}
                  onChange={(e) =>
                    setB({
                      ...b,
                      qualification: {
                        ...b.qualification,
                        hot_threshold: +e.target.value,
                      },
                    })
                  }
                />
              </label>
              <label>
                Warm lead threshold
                <input
                  type="number"
                  min={0}
                  max={99}
                  value={b.qualification.warm_threshold}
                  onChange={(e) =>
                    setB({
                      ...b,
                      qualification: {
                        ...b.qualification,
                        warm_threshold: +e.target.value,
                      },
                    })
                  }
                />
              </label>
            </div>
            <label>
              Minimum qualification budget (USD)
              <input
                type="number"
                min={0}
                value={b.qualification.minimum_budget}
                onChange={(e) =>
                  setB({
                    ...b,
                    qualification: {
                      ...b.qualification,
                      minimum_budget: +e.target.value,
                    },
                  })
                }
              />
            </label>
            <label>
              Sales notification email
              <input
                type="email"
                value={b.notification_email}
                onChange={(e) =>
                  setB({ ...b, notification_email: e.target.value })
                }
                placeholder="sales@yourcompany.com"
              />
            </label>
            <label>
              Follow-up delay (hours)
              <input
                type="number"
                min={1}
                max={720}
                value={b.followup_hours}
                onChange={(e) =>
                  setB({ ...b, followup_hours: +e.target.value })
                }
              />
            </label>
            <p className="muted small-text">
              Automatic visitor follow-up requires explicit consent. Booked and
              closed leads are excluded.
            </p>
            <div className="integration-toggles">
              {Object.keys(b.integrations).map((k) => (
                <label className="toggle-row" key={k}>
                  <span>{label(k)} integration</span>
                  <input
                    type="checkbox"
                    checked={b.integrations[k]}
                    onChange={(e) =>
                      setB({
                        ...b,
                        integrations: {
                          ...b.integrations,
                          [k]: e.target.checked,
                        },
                      })
                    }
                  />
                </label>
              ))}
            </div>
          </section>
        </div>
        {error && (
          <p className="error-text" role="alert">
            {error}
          </p>
        )}
        <div className="settings-save">
          <span>
            {SHOWCASE
              ? "Preferences are saved in this browser only. Integrations remain simulated."
              : "Credentials stay on the server. Enabling a service does not verify its connection."}
          </span>
          <Submit busy={busy}>Save workspace settings</Submit>
        </div>
      </form>
      {SHOWCASE ? (
        <section className="panel embed-panel">
          <SectionHeader
            title="Explore the customer experience"
            sub="This public showcase uses a local scripted assistant. Website embedding and live AI belong to the private full-stack deployment."
          />
          <a className="button secondary" href={appUrl("demo")}>
            Open demo website <ArrowUpRight size={15} />
          </a>
        </section>
      ) : (
        <section className="panel embed-panel">
          <SectionHeader
            title="Bring the assistant to your website"
            sub="Add this script to an approved website origin. Use an HTTPS production URL when deploying."
          />
          <pre>{embed}</pre>
          <button
            className="button secondary"
            onClick={async () => {
              try {
                await navigator.clipboard.writeText(embed);
                setCopied(true);
              } catch {
                setError(
                  "Clipboard unavailable. Select and copy the embed code manually.",
                );
              }
            }}
          >
            {copied ? <Check size={15} /> : <Command size={15} />}{" "}
            {copied ? "Copied" : "Copy embed code"}
          </button>
          <p className="muted small-text">
            Workspace ID: {b.id} · Website permissions and new-business
            onboarding are managed in the deployment configuration.
          </p>
        </section>
      )}
    </>
  );
}
