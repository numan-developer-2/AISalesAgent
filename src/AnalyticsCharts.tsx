import { useEffect, useId, useRef, useState } from "react";
import { BarChart3, MousePointer2 } from "lucide-react";
import type { Workspace } from "./types";

const number = new Intl.NumberFormat("en-US");
const dayLabel = (date: string, long = false) =>
  new Date(date + "T12:00:00Z").toLocaleDateString("en-US", {
    month: long ? "long" : "short",
    day: "numeric",
    ...(long ? { year: "numeric" as const } : {}),
    timeZone: "UTC",
  });

export function ActivityChart({ rows }: { rows: Workspace["trend"] }) {
  const id = useId().replace(/:/g, "");
  const container = useRef<HTMLDivElement>(null);
  const [width, setWidth] = useState(680);
  const [active, setActive] = useState<number | null>(null);
  const [visible, setVisible] = useState({ conversations: true, leads: true });
  useEffect(() => {
    if (!container.current || typeof ResizeObserver === "undefined") return;
    const observer = new ResizeObserver(([entry]) => {
      if (entry.contentRect.width > 0)
        setWidth(Math.max(240, Math.round(entry.contentRect.width)));
    });
    observer.observe(container.current);
    return () => observer.disconnect();
  }, []);
  useEffect(() => setActive(null), [rows.length, rows[0]?.date]);
  const total = rows.reduce(
    (sum, row) => ({
      conversations: sum.conversations + row.conversations,
      leads: sum.leads + row.leads,
    }),
    { conversations: 0, leads: 0 },
  );
  const peak = rows.reduce<(typeof rows)[number] | null>(
    (best, row) =>
      !best || row.conversations > best.conversations ? row : best,
    null,
  );
  const maximum = Math.max(
    1,
    ...rows.flatMap((r) => [
      visible.conversations ? r.conversations : 0,
      visible.leads ? r.leads : 0,
    ]),
  );
  // Integer, evenly spaced ticks share the exact same scale as both series.
  const magnitude = 10 ** Math.floor(Math.log10(Math.max(1, maximum / 4)));
  const tick = Math.max(
    1,
    [1, 2, 5, 10].map((n) => n * magnitude).find((n) => n >= maximum / 4) ||
      magnitude * 10,
  );
  const ceiling = Math.ceil(maximum / tick) * tick;
  const left = 38,
    right = width - 16,
    top = 14,
    bottom = 220;
  const step = (right - left) / Math.max(rows.length, 1);
  const x = (i: number) => left + step * (i + 0.5);
  const y = (value: number) => bottom - (value / ceiling) * (bottom - top);
  const points = rows.map((r, i) => `${x(i)},${y(r.conversations)}`).join(" ");
  const selected = active === null ? null : rows[active];
  const hasActivity = total.conversations + total.leads > 0;
  const labelEvery = Math.max(
    1,
    Math.ceil(rows.length / (width < 450 ? 3 : 6)),
  );
  return (
    <div className="analytics-activity">
      <div className="activity-summary">
        <div>
          <span>Conversations started</span>
          <strong>{number.format(total.conversations)}</strong>
          <small>Across {rows.length} days</small>
        </div>
        <div>
          <span>Lead records created</span>
          <strong>{number.format(total.leads)}</strong>
          <small>From saved inquiries</small>
        </div>
        <div>
          <span>Peak conversation day</span>
          <strong className="activity-peak">
            {peak && peak.conversations > 0
              ? dayLabel(peak.date)
              : "No activity"}
          </strong>
          <small>
            {peak && peak.conversations > 0
              ? `${number.format(peak.conversations)} conversations`
              : "Waiting for inquiries"}
          </small>
        </div>
      </div>
      <div className="chart-toolbar">
        <span className="chart-unit">Daily records · UTC</span>
        <div className="series-controls" aria-label="Visible activity series">
          {(["conversations", "leads"] as const).map((key) => (
            <button
              key={key}
              type="button"
              aria-pressed={visible[key]}
              disabled={
                visible[key] &&
                Object.values(visible).filter(Boolean).length === 1
              }
              onClick={() => setVisible((v) => ({ ...v, [key]: !v[key] }))}
            >
              <i className={"series-swatch " + key} />
              {key === "conversations" ? "Conversations" : "Leads"}
            </button>
          ))}
        </div>
      </div>
      <div className="activity-plot" ref={container}>
        {rows.length > 0 ? (
          <svg
            viewBox={`0 0 ${width} 254`}
            width="100%"
            height="254"
            role="group"
            aria-label="Daily conversation and lead activity"
          >
            <defs>
              <linearGradient id={id + "-area"} x1="0" y1="0" x2="0" y2="1">
                <stop offset="0" stopColor="#287c72" stopOpacity=".2" />
                <stop offset="1" stopColor="#287c72" stopOpacity=".015" />
              </linearGradient>
            </defs>
            {Array.from({ length: ceiling / tick + 1 }, (_, i) => i * tick).map(
              (value) => (
                <g key={value} aria-hidden="true">
                  <line
                    x1={left}
                    x2={right}
                    y1={y(value)}
                    y2={y(value)}
                    className="analytics-gridline"
                  />
                  <text
                    x={left - 10}
                    y={y(value) + 4}
                    textAnchor="end"
                    className="analytics-axis"
                  >
                    {number.format(value)}
                  </text>
                </g>
              ),
            )}
            {visible.conversations && hasActivity && (
              <polygon
                points={`${x(0)},${bottom} ${points} ${x(rows.length - 1)},${bottom}`}
                fill={`url(#${id}-area)`}
              />
            )}
            {visible.leads &&
              rows.map((r, i) => (
                <rect
                  key={r.date}
                  x={x(i) - Math.min(step * 0.42, 16) / 2}
                  y={y(r.leads)}
                  width={Math.min(step * 0.42, 16)}
                  height={bottom - y(r.leads)}
                  rx="3"
                  className="activity-bar"
                  aria-hidden="true"
                />
              ))}
            {visible.conversations && (
              <polyline
                points={points}
                fill="none"
                className="activity-line"
                aria-hidden="true"
              />
            )}
            {visible.conversations &&
              rows.map((r, i) => (
                <circle
                  key={r.date}
                  cx={x(i)}
                  cy={y(r.conversations)}
                  r={active === i ? 5 : 3}
                  className="activity-dot"
                  aria-hidden="true"
                />
              ))}
            {active !== null && rows[active] && (
              <line
                x1={x(active)}
                x2={x(active)}
                y1={top}
                y2={bottom}
                className="activity-crosshair"
                aria-hidden="true"
              />
            )}
            {rows.map((r, i) => (
              <g key={r.date}>
                {(i % labelEvery === 0 ||
                  (i === rows.length - 1 &&
                    i % labelEvery >= labelEvery / 2)) && (
                  <text
                    x={x(i)}
                    y="244"
                    textAnchor="middle"
                    className="analytics-axis"
                    aria-hidden="true"
                  >
                    {dayLabel(r.date)}
                  </text>
                )}
                <rect
                  data-chart-point
                  x={left + step * i}
                  y={top}
                  width={step}
                  height={bottom - top}
                  className="chart-hit-target"
                  tabIndex={0}
                  role="button"
                  aria-label={`${dayLabel(r.date, true)}: ${r.conversations} conversations, ${r.leads} leads`}
                  onPointerEnter={() => setActive(i)}
                  onPointerLeave={() => setActive(null)}
                  onFocus={() => setActive(i)}
                  onBlur={() => setActive(null)}
                  onClick={() => setActive(i)}
                  onKeyDown={(event) => {
                    if (event.key === "Enter" || event.key === " ") {
                      event.preventDefault();
                      setActive(i);
                    }
                    const next =
                      event.key === "ArrowRight"
                        ? Math.min(rows.length - 1, i + 1)
                        : event.key === "ArrowLeft"
                          ? Math.max(0, i - 1)
                          : event.key === "Home"
                            ? 0
                            : event.key === "End"
                              ? rows.length - 1
                              : null;
                    if (next !== null) {
                      event.preventDefault();
                      event.currentTarget.ownerSVGElement
                        ?.querySelectorAll<SVGRectElement>("[data-chart-point]")
                        [next]?.focus();
                    }
                  }}
                />
              </g>
            ))}
          </svg>
        ) : (
          <div className="analytics-empty">
            <BarChart3 size={28} />
            <p>No activity recorded in this period.</p>
          </div>
        )}
        {selected && active !== null && (
          <div
            className="chart-tooltip"
            role="tooltip"
            style={{ left: Math.min(Math.max(x(active), 94), width - 94) }}
          >
            <strong>{dayLabel(selected.date, true)}</strong>
            <span>
              <i className="series-swatch conversations" />
              Conversations <b>{number.format(selected.conversations)}</b>
            </span>
            <span>
              <i className="series-swatch leads" />
              Leads <b>{number.format(selected.leads)}</b>
            </span>
          </div>
        )}
        {!hasActivity && rows.length > 0 && (
          <div className="chart-empty-note">No activity yet in this period</div>
        )}
      </div>
      <p className="chart-instruction">
        <MousePointer2 size={12} />
        Hover, tap or focus a day to inspect values. Arrow keys move between
        days.
      </p>
    </div>
  );
}

export type InsightCounts = {
  sessions: number;
  engaged: number;
  contactable: number;
  progressing: number;
  booked: number;
  won: number;
};
export type SourceRow = InsightCounts & {
  source: string;
  medium: string;
  campaign: string;
};

export function OutcomeChart({ counts }: { counts: InsightCounts }) {
  const stages = [
    { key: "sessions", title: "All sessions", color: "#94aaa8" },
    { key: "engaged", title: "Engaged", color: "#54958e" },
    { key: "contactable", title: "Contactable", color: "#297e73" },
    { key: "booked", title: "Booked", color: "#d48a4c" },
    { key: "won", title: "Won", color: "#7971b1" },
  ] as const;
  return (
    <div className="outcome-chart">
      <div className="visual-chart-key">
        <span>Current session outcomes</span>
        <span>Share of all sessions</span>
      </div>
      <ol aria-label="Session outcome breakdown">
        {stages.map((stage) => {
          const value = counts[stage.key];
          const share =
            counts.sessions > 0 ? (value / counts.sessions) * 100 : 0;
          return (
            <li key={stage.key}>
              <div className="outcome-label">
                <span>{stage.title}</span>
                <strong>
                  {number.format(value)}{" "}
                  <small>
                    {counts.sessions > 0 ? `${Math.round(share)}%` : "—"}
                  </small>
                </strong>
              </div>
              <div className="visual-bar-track">
                <span
                  style={{
                    width: `${Math.min(100, share)}%`,
                    background: stage.color,
                  }}
                />
              </div>
            </li>
          );
        })}
      </ol>
      <p className="visual-chart-note">
        Outcomes can overlap. These are current records, not sequential drop-off
        rates.
      </p>
    </div>
  );
}

export function SourceChart({ sources }: { sources: SourceRow[] }) {
  const [metric, setMetric] = useState<"sessions" | "contactable" | "booked">(
    "sessions",
  );
  const groups = new Map<string, number>();
  for (const row of sources)
    groups.set(row.source, (groups.get(row.source) || 0) + row[metric]);
  const sorted = [...groups].sort(
    (a, b) => b[1] - a[1] || a[0].localeCompare(b[0]),
  );
  const rows = sorted
    .slice(0, 5)
    .map(([name, value]) => ({ name, value, key: name }));
  if (sorted.length > 5)
    rows.push({
      name: "Other sources",
      value: sorted.slice(5).reduce((sum, [, v]) => sum + v, 0),
      key: "__remaining-sources__",
    });
  const total = sorted.reduce((sum, [, value]) => sum + value, 0);
  const max = Math.max(1, ...rows.map((r) => r.value));
  return (
    <div className="source-chart">
      <div className="source-chart-toolbar">
        <span className="chart-unit">
          {number.format(total)}{" "}
          {metric === "contactable"
            ? "contactable sessions"
            : metric === "booked"
              ? "booked sessions"
              : "sessions"}
        </span>
        <select
          aria-label="Source chart metric"
          value={metric}
          onChange={(e) => setMetric(e.target.value as typeof metric)}
        >
          <option value="sessions">Sessions</option>
          <option value="contactable">Contactable</option>
          <option value="booked">Booked</option>
        </select>
      </div>
      {total > 0 ? (
        <ol aria-label="Source contribution breakdown">
          {rows.map((row, i) => (
            <li key={row.key}>
              <div className="source-row-label">
                <span className="source-rank">
                  {String(i + 1).padStart(2, "0")}
                </span>
                <span className="source-name" title={row.name}>
                  {row.name}
                </span>
                <strong>{number.format(row.value)}</strong>
                <small>{Math.round((row.value / total) * 100)}%</small>
              </div>
              <div className="visual-bar-track">
                <span
                  style={{
                    width: `${(row.value / max) * 100}%`,
                    background: i === 0 ? "#297e73" : "#a2c3bc",
                  }}
                />
              </div>
            </li>
          ))}
        </ol>
      ) : (
        <div className="analytics-empty">
          <BarChart3 size={28} />
          <p>No {metric} recorded for these sources.</p>
          <small>Try another metric or reporting period.</small>
        </div>
      )}
      <p className="visual-chart-note">
        Grouped by source across campaigns. Percentages show the share of the
        selected metric.
      </p>
    </div>
  );
}
