import { useEffect, useRef, useState, type FormEvent } from "react";
import {
  ArrowRight,
  ArrowUpRight,
  Check,
  ChevronLeft,
  Clock,
  Layers,
  Loader2,
  MessageCircle,
  Plus,
  Send,
  ShieldCheck,
  Sparkles,
  X,
} from "lucide-react";
import type { Business, Conversation } from "./types";
import { api, ApiError, send } from "./api";
import { Empty } from "./ui";
import { sourcePage } from "./attribution";
import { SHOWCASE, appUrl } from "./showcase/mode";

type Config = Business & { mode: "demo" | "live" };
type Offer = { id: string; start_at: string; end_at: string; timezone: string };
const pending = new Map<
  string,
  Promise<{ token: string; conversation: Conversation }>
>();
const businessId = () =>
  new URLSearchParams(location.search).get("business") || "systematic";
const storageKey = (b: string) =>
  (SHOWCASE ? "systematic-showcase-visitor-v1:" : "systematic-visitor-v1:") + b;

async function visitorSession(b: string) {
  if (pending.has(b)) return pending.get(b)!;
  const promise = (async () => {
    let token = "";
    try {
      token = localStorage.getItem(storageKey(b)) || "";
    } catch {
      /* Private browsing can disable storage. */
    }
    if (token) {
      try {
        return {
          token,
          conversation: await api<Conversation>("/public/conversation", {
            headers: { Authorization: "Bearer " + token },
          }),
        };
      } catch (e) {
        if (!(e instanceof ApiError && e.status === 401)) throw e;
      }
    }
    const value = await api<{ token: string; conversation: Conversation }>(
      "/public/session",
      {
        method: "POST",
        body: send({
          business: b,
          source_page: sourcePage(),
        }),
      },
    );
    try {
      localStorage.setItem(storageKey(b), value.token);
    } catch {
      /* The current tab still works. */
    }
    return value;
  })();
  pending.set(b, promise);
  try {
    return await promise;
  } catch (e) {
    pending.delete(b);
    throw e;
  }
}

export function Widget({ embedded = false }: { embedded?: boolean }) {
  const [config, setConfig] = useState<Config | null>(null),
    [conv, setConv] = useState<Conversation | null>(null),
    [token, setToken] = useState(""),
    [message, setMessage] = useState(""),
    [busy, setBusy] = useState(false),
    [error, setError] = useState(""),
    [action, setAction] = useState(""),
    [restart, setRestart] = useState(0),
    [requestId, setRequestId] = useState("");
  const pendingMessage = useRef("");
  const bottom = useRef<HTMLDivElement>(null),
    input = useRef<HTMLInputElement>(null);
  const b = businessId();
  useEffect(() => {
    let active = true;
    Promise.all([api<Config>("/public/config/" + b), visitorSession(b)])
      .then(([c, s]) => {
        if (active) {
          setConfig(c);
          setConv(s.conversation);
          setToken(s.token);
          setError("");
        }
      })
      .catch((e) => active && setError(e.message));
    return () => {
      active = false;
    };
  }, [b, restart]);
  useEffect(() => {
    bottom.current?.scrollIntoView({ behavior: "smooth", block: "nearest" });
  }, [conv?.messages.length, busy]);
  useEffect(() => {
    if (!token) return;
    const t = setInterval(() => {
      if (!busy)
        api<Conversation>("/public/conversation", {
          headers: { Authorization: "Bearer " + token },
        })
          .then(setConv)
          .catch(() => {});
    }, 5000);
    return () => clearInterval(t);
  }, [token, busy]);
  async function submit(text = message) {
    if (!text.trim() || busy || !token) return;
    setBusy(true);
    setError("");
    const id =
      requestId && pendingMessage.current === text
        ? requestId
        : crypto.randomUUID();
    pendingMessage.current = text;
    setRequestId(id);
    try {
      const r = await api<{ conversation: Conversation; action: string }>(
        "/public/chat",
        {
          method: "POST",
          headers: { Authorization: "Bearer " + token },
          body: send({ message: text, request_id: id }),
        },
      );
      setConv(r.conversation);
      setMessage("");
      setRequestId("");
      if (r.action !== "none") setAction(r.action);
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setBusy(false);
      input.current?.focus();
    }
  }
  function newChat() {
    pendingMessage.current = "";
    pending.delete(b);
    try {
      localStorage.removeItem(storageKey(b));
    } catch {}
    setAction("");
    setConv(null);
    setToken("");
    setMessage("");
    setRequestId("");
    setRestart((x) => x + 1);
  }
  function navigate(url: string) {
    if (!config?.navigation.some((n) => n.url === url)) return;
    if (window.parent !== window) {
      window.parent.postMessage(
        { type: "systematic:navigate", business: b, url },
        "*",
      );
    } else window.open(url, "_blank", "noopener,noreferrer");
  }
  const latestAction = [...(conv?.messages || [])]
    .reverse()
    .find((m) => m.action && m.action !== "none")?.action;
  return (
    <div
      className={"widget-page " + (embedded ? "widget-embedded" : "")}
      style={{ "--accent": config?.accent || "#e97845" } as React.CSSProperties}
    >
      <section className="chat-widget" aria-label="Sales assistant">
        <header className="widget-header">
          <span className="assistant-avatar">
            <Layers size={23} />
          </span>
          <div>
            <strong>{config?.short_name || "Sales"} assistant</strong>
            <span>
              <i className="status-light" />
              {conv?.status === "human"
                ? "Sales team has joined"
                : SHOWCASE
                  ? "Scripted sales demo"
                  : "AI sales assistant"}
            </span>
          </div>
          <button
            className="widget-icon"
            onClick={newChat}
            disabled={busy}
            aria-label="Start new conversation"
          >
            <Plus size={19} />
          </button>
          {embedded && (
            <button
              className="widget-icon"
              aria-label="Close assistant"
              onClick={() => window.dispatchEvent(new Event("close-assistant"))}
            >
              <X size={19} />
            </button>
          )}
        </header>
        {config?.mode === "demo" && (
          <div className="widget-mode">
            <Sparkles size={12} />
            {SHOWCASE
              ? "Scripted demo · Fictional details only · No external actions"
              : "Demo experience · No external actions"}
          </div>
        )}
        {action && config ? (
          <ActionForm
            config={config}
            token={token}
            kind={action}
            back={() => setAction("")}
            done={async () => {
              setAction("");
              setConv(
                await api<Conversation>("/public/conversation", {
                  headers: { Authorization: "Bearer " + token },
                }),
              );
            }}
          />
        ) : (
          <>
            <div className="widget-messages" aria-live="polite">
              {!conv && !error && (
                <div className="chat-loading">
                  <Loader2 className="spin" />
                  Starting your conversation…
                </div>
              )}
              {config && conv?.messages.length === 0 && (
                <div className="widget-welcome">
                  <div className="welcome-emblem">
                    <Sparkles size={25} />
                  </div>
                  <span className="eyebrow">LET'S FIND YOUR NEXT STEP</span>
                  <h2>
                    Big ideas start
                    <br />
                    with a conversation.
                  </h2>
                  <p>{config.welcome}</p>
                  <div className="quick-replies">
                    {[
                      "What services do you offer?",
                      "Explore pricing",
                      "Book a consultation",
                    ].map((s) => (
                      <button key={s} disabled={busy} onClick={() => submit(s)}>
                        {s}
                        <ArrowUpRight size={14} />
                      </button>
                    ))}
                  </div>
                </div>
              )}
              {conv?.messages.map((m) => (
                <div key={m.id} className={"widget-message " + m.role}>
                  <small>
                    {m.role === "user"
                      ? "You"
                      : m.author || config?.short_name + " AI"}
                  </small>
                  <p>{m.content}</p>
                  {m.grounding_status === "insufficient_context" && (
                    <small>Needs confirmation from the sales team</small>
                  )}
                  {m.grounding_status === "source_excerpt" && (
                    <small>Excerpt from business reference material</small>
                  )}
                  {m.sources && m.sources.length > 0 && (
                    <details>
                      <summary>Sources · {m.sources.length}</summary>
                      {m.sources
                        .filter((s) => /^https?:\/\//.test(s.url || ""))
                        .map((s, i) => (
                          <a
                            key={i}
                            href={s.url}
                            target="_blank"
                            rel="noreferrer"
                          >
                            {s.title || "Business website"}
                            <ArrowUpRight size={11} />
                          </a>
                        ))}
                    </details>
                  )}
                </div>
              ))}
              {busy && (
                <div className="thinking">
                  <i />
                  <i />
                  <i />
                  <span>Thinking through your question</span>
                </div>
              )}
              {latestAction && !busy && (
                <button
                  className="action-cta"
                  onClick={() => setAction(latestAction)}
                >
                  {latestAction === "book_meeting"
                    ? "Choose a consultation time"
                    : latestAction === "request_proposal"
                      ? "Request a proposal"
                      : "Request a human conversation"}
                  <ArrowRight size={15} />
                </button>
              )}
              <div ref={bottom} />
            </div>
            {config?.navigation.length ? (
              <div className="widget-navigation">
                {config.navigation.slice(0, 2).map((n) => (
                  <button key={n.url} onClick={() => navigate(n.url)}>
                    {n.label}
                    <ArrowUpRight size={12} />
                  </button>
                ))}
              </div>
            ) : null}
            <form
              className="widget-composer"
              onSubmit={(e) => {
                e.preventDefault();
                submit();
              }}
            >
              <input
                ref={input}
                aria-label="Your message"
                value={message}
                onChange={(e) => {
                  setMessage(e.target.value);
                }}
                maxLength={2000}
                placeholder={
                  conv?.status === "human"
                    ? "Message the sales team…"
                    : "Ask us anything about your next project…"
                }
                disabled={!token}
              />
              <button
                aria-label="Send message"
                disabled={busy || !message.trim() || !token}
              >
                {busy ? (
                  <Loader2 className="spin" size={17} />
                ) : (
                  <Send size={17} />
                )}
              </button>
            </form>
            <div className="widget-footer">
              <ShieldCheck size={11} />
              Only share information you want the sales team to receive.
              <button
                onClick={() => setAction("human_handover")}
                disabled={!token}
              >
                Talk to a person
              </button>
            </div>
          </>
        )}
        {error && (
          <div className="widget-error" role="alert">
            {error}
            <button
              onClick={() =>
                token
                  ? submit(message.trim() ? message : pendingMessage.current)
                  : setRestart((x) => x + 1)
              }
            >
              Retry
            </button>
          </div>
        )}
      </section>
      {!embedded && (
        <p className="widget-brand">
          Powered by <strong>systematic.</strong>
        </p>
      )}
    </div>
  );
}

function ActionForm({
  config,
  token,
  kind,
  back,
  done,
}: {
  config: Config;
  token: string;
  kind: string;
  back: () => void;
  done: () => void;
}) {
  const tomorrow = new Date();
  tomorrow.setDate(tomorrow.getDate() + 1);
  const localDate = (d: Date) =>
    `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, "0")}-${String(d.getDate()).padStart(2, "0")}`;
  const [day, setDay] = useState(localDate(tomorrow)),
    [slots, setSlots] = useState<Offer[]>([]),
    [slot, setSlot] = useState(""),
    [busy, setBusy] = useState(false),
    [loading, setLoading] = useState(false),
    [error, setError] = useState(""),
    [success, setSuccess] = useState("");
  const booking = kind === "book_meeting";
  const submission = useRef({ fingerprint: "", id: "" });
  useEffect(() => {
    if (!booking) return;
    let active = true;
    setLoading(true);
    setSlot("");
    setSlots([]);
    setError("");
    api<{ slots: Offer[] }>("/public/availability?day=" + day, {
      headers: { Authorization: "Bearer " + token },
    })
      .then((d) => active && setSlots(d.slots))
      .catch((e) => active && setError(e.message))
      .finally(() => active && setLoading(false));
    return () => {
      active = false;
    };
  }, [day, booking, token]);
  async function submit(e: FormEvent<HTMLFormElement>) {
    e.preventDefault();
    setBusy(true);
    setError("");
    const form = new FormData(e.currentTarget);
    const contact = {
      name: form.get("name"),
      email: form.get("email"),
      company: form.get("company"),
      service: form.get("service"),
      goal: form.get("goal"),
      consent: form.get("consent") === "on",
      confirmed: true,
    };
    const payload = booking
      ? { ...contact, offer_id: slot }
      : {
          ...contact,
          kind: kind === "request_proposal" ? "proposal" : "handover",
        };
    const fingerprint = JSON.stringify(payload);
    if (submission.current.fingerprint !== fingerprint)
      submission.current = { fingerprint, id: crypto.randomUUID() };
    try {
      await api(booking ? "/public/book" : "/public/requests", {
        method: "POST",
        headers: { Authorization: "Bearer " + token },
        body: send(
          booking ? payload : { ...payload, request_id: submission.current.id },
        ),
      });
      setSuccess(
        booking
          ? config.mode === "demo"
            ? "Demo appointment saved"
            : "Your consultation is booked"
          : "Your request is recorded",
      );
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setBusy(false);
    }
  }
  if (success)
    return (
      <div className="action-success">
        <span>
          <Check size={30} />
        </span>
        <h2>{success}</h2>
        <p>
          {config.mode === "demo"
            ? "This was a simulated experience. No external email or calendar event was sent."
            : "Your details are saved. The team can review your request in the sales workspace."}
        </p>
        <button className="button primary" onClick={done}>
          Back to conversation <ArrowRight size={16} />
        </button>
      </div>
    );
  return (
    <div className="action-form">
      <button className="text-button" onClick={back}>
        <ChevronLeft size={15} />
        Back to conversation
      </button>
      <h2>
        {booking
          ? "Make time for your next step."
          : kind === "request_proposal"
            ? "Tell us about your project."
            : "Let’s connect you with the team."}
      </h2>
      <p>
        {booking
          ? "Choose a time and confirm your details."
          : "Share your details and we’ll record your request."}
      </p>
      <form onSubmit={submit}>
        {booking && (
          <>
            <label>
              Preferred date
              <input
                type="date"
                min={localDate(new Date())}
                value={day}
                onChange={(e) => setDay(e.target.value)}
                required
              />
            </label>
            <span className="slot-caption">
              <Clock size={13} />
              {config.timezone} · {config.meeting_duration || 30}-minute
              consultation
            </span>
            <div className="slot-grid">
              {loading ? (
                <p>Checking availability…</p>
              ) : slots.length ? (
                slots.map((s) => (
                  <button
                    type="button"
                    key={s.id}
                    className={slot === s.id ? "selected" : ""}
                    onClick={() => setSlot(s.id)}
                  >
                    {new Date(s.start_at).toLocaleTimeString("en-US", {
                      timeZone: s.timezone,
                      hour: "numeric",
                      minute: "2-digit",
                    })}
                  </button>
                ))
              ) : (
                <p>No available times. Please choose another day.</p>
              )}
            </div>
          </>
        )}
        <div className="form-grid">
          <label>
            Your name
            <input
              name="name"
              autoComplete="name"
              required
              minLength={2}
              maxLength={100}
            />
          </label>
          <label>
            Company
            <input name="company" autoComplete="organization" maxLength={120} />
          </label>
        </div>
        <label>
          Email address
          <input
            name="email"
            type="email"
            autoComplete="email"
            required
            maxLength={150}
          />
        </label>
        <label>
          Interested service
          <select name="service" required>
            {config.services.map((s) => (
              <option key={s}>{s}</option>
            ))}
          </select>
        </label>
        <label>
          What would you like help with?
          <textarea name="goal" rows={2} maxLength={1000} />
        </label>
        <label className="checkbox-label">
          <input type="checkbox" name="consent" />
          You may email me a follow-up about this inquiry.
        </label>
        <label className="checkbox-label">
          <input type="checkbox" required />I confirm{" "}
          {booking
            ? "this appointment time and my contact details"
            : "that I want to send this request to the team"}
          .
        </label>
        {error && (
          <p className="error-text" role="alert">
            {error}
          </p>
        )}
        <button
          className="button primary full"
          disabled={busy || (booking && !slot)}
        >
          {busy ? <Loader2 className="spin" size={16} /> : null}
          {booking
            ? config.mode === "demo"
              ? "Confirm demo appointment"
              : "Confirm appointment"
            : "Submit request"}
          <ArrowRight size={16} />
        </button>
      </form>
    </div>
  );
}

export function DemoSite() {
  const [open, setOpen] = useState(true),
    [config, setConfig] = useState<Config | null>(null);
  useEffect(() => {
    api<Config>("/public/config/" + businessId())
      .then(setConfig)
      .catch(() => {});
    const close = () => setOpen(false);
    addEventListener("close-assistant", close);
    return () => removeEventListener("close-assistant", close);
  }, []);
  return (
    <div className="demo-site">
      <header>
        <a className="demo-logo" href={appUrl("demo")}>
          <Layers />
          {config?.short_name || "Systematic"}
          <span>IT SOLUTIONS</span>
        </a>
        <nav>
          <a href="#services">Expertise</a>
          <a href="#approach">Our approach</a>
          <a href={appUrl()}>
            Sales workspace <ArrowUpRight size={14} />
          </a>
        </nav>
        <button className="button primary" onClick={() => setOpen(true)}>
          Let's talk <ArrowUpRight size={15} />
        </button>
      </header>
      <main>
        <div className="demo-hero">
          <span className="eyebrow">YOUR NEXT CHAPTER STARTS HERE</span>
          <h1>
            Build something
            <br />
            that moves your
            <br />
            <em>business forward.</em>
          </h1>
          <p>
            Thoughtful digital experiences. Clear growth strategies.
            <br />A team that starts by understanding your business.
          </p>
          <button className="button primary" onClick={() => setOpen(true)}>
            Find your next step <ArrowRight size={17} />
          </button>
          <span className="demo-site-note">
            Interactive website preview ·{" "}
            {config?.mode === "demo"
              ? "Simulated sales experience"
              : "Connected sales assistant"}
          </span>
        </div>
        <section id="services" className="demo-services">
          <span className="eyebrow">CONNECTED EXPERTISE</span>
          <h2>
            A good idea deserves
            <br />
            the right execution.
          </h2>
          <div>
            {(
              config?.services.slice(0, 4) || [
                "SEO",
                "Web Development",
                "Digital Marketing",
                "Branding",
              ]
            ).map((s, i) => (
              <button key={s} onClick={() => setOpen(true)}>
                <span>0{i + 1}</span>
                <strong>{s}</strong>
                <ArrowUpRight />
              </button>
            ))}
          </div>
        </section>
        <section id="approach" className="demo-approach">
          <span className="eyebrow">FIRST, WE LISTEN.</span>
          <h2>Your goals set the direction.</h2>
          <p>
            Tell our assistant what you're working on. Explore relevant
            services, ask questions, and arrange a conversation with the team.
          </p>
        </section>
      </main>
      {open ? (
        <div className="demo-widget">
          <Widget embedded />
        </div>
      ) : (
        <button className="chat-launcher" onClick={() => setOpen(true)}>
          <MessageCircle size={22} />
          How can we help?
        </button>
      )}
    </div>
  );
}
