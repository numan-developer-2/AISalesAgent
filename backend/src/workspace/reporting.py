"""Saved-record reporting. Counts describe inquiry cohorts, not unique people."""

from collections import defaultdict
from datetime import datetime, timedelta, timezone
import re
from urllib.parse import parse_qs, urlparse, urlunparse


def capture_source(value, fallback, allowed):
    try:
        parsed = urlparse(value or fallback)
        origin = f"{parsed.scheme}://{parsed.netloc}"
        if origin not in allowed or parsed.username or parsed.password:
            parsed = urlparse(fallback)
        query = parse_qs(parsed.query)
        attribution = {}
        for key in ("utm_source", "utm_medium", "utm_campaign"):
            item = query.get(key, [""])[0]
            if re.fullmatch(r"[\w .-]{1,80}", item, flags=re.ASCII):
                attribution[key] = item
        # Never retain arbitrary query strings, login tokens or URL fragments.
        page = urlunparse((parsed.scheme, parsed.netloc, parsed.path, "", "", ""))
        return page, attribution
    except ValueError:
        return fallback, {}


def timestamp(value):
    try:
        parsed = datetime.fromisoformat(value)
        return parsed if parsed.tzinfo else parsed.replace(tzinfo=timezone.utc)
    except (TypeError, ValueError):
        return None


def summarize(conversations, leads, meetings, requests, days, now=None):
    now = now or datetime.now(timezone.utc)
    cutoff = now - timedelta(days=days)
    cohort = {
        c["id"]: c
        for c in conversations
        if (stamp := timestamp(c.get("created_at"))) and cutoff <= stamp <= now
    }
    linked = defaultdict(list)
    for lead in leads:
        if lead.get("conversation_id") in cohort:
            linked[lead["conversation_id"]].append(lead)
    booked = {
        m.get("conversation_id")
        for m in meetings
        if m.get("status") in ("booked", "simulated", "attended")
    }
    fields = ("sessions", "engaged", "contactable", "progressing", "booked", "won")
    totals = dict.fromkeys(fields, 0)
    sources = {}
    for key, conv in cohort.items():
        rows = linked[key]
        source = conv.get("attribution", {}).get("utm_source") or "Unattributed"
        medium = conv.get("attribution", {}).get("utm_medium") or "Unspecified"
        campaign = conv.get("attribution", {}).get("utm_campaign") or "Unspecified"
        group = sources.setdefault(
            (source, medium, campaign),
            {
                "source": source,
                "medium": medium,
                "campaign": campaign,
                **dict.fromkeys(fields, 0),
            },
        )
        states = {
            "sessions": True,
            "engaged": bool(rows)
            or key in booked
            or any(m.get("role") == "user" for m in conv.get("messages", [])),
            "contactable": any(l.get("email") or l.get("phone") for l in rows),
            "progressing": any(
                l.get("stage")
                in (
                    "qualified",
                    "meeting_booked",
                    "meeting_attended",
                    "proposal_requested",
                    "proposal_sent",
                    "won",
                )
                for l in rows
            ),
            "booked": key in booked,
            "won": any(l.get("stage") == "won" for l in rows),
        }
        # A won-contact conversion is a subset of contactable sessions.
        states["won"] = states["won"] and states["contactable"]
        for field, present in states.items():
            totals[field] += int(present)
            group[field] += int(present)
    open_requests = [
        r
        for r in requests
        if r.get("conversation_id") in cohort and r.get("status") != "completed"
    ]
    return {
        "days": days,
        "as_of": now.isoformat(),
        "since": cutoff.isoformat(),
        "counts": totals,
        "rates": {
            "contact_capture": (
                round(totals["contactable"] * 100 / totals["engaged"], 1)
                if totals["engaged"]
                else None
            ),
            "booking": (
                round(totals["booked"] * 100 / totals["engaged"], 1)
                if totals["engaged"]
                else None
            ),
            "won": (
                round(totals["won"] * 100 / totals["contactable"], 1)
                if totals["contactable"]
                else None
            ),
        },
        "sources": sorted(
            sources.values(),
            key=lambda row: (
                -row["engaged"],
                row["source"],
                row["medium"],
                row["campaign"],
            ),
        ),
        "open_requests": len(open_requests),
        "overdue_requests": sum(
            bool((due := timestamp(r.get("due_at"))) and due < now)
            for r in open_requests
        ),
        "sample_sessions": sum(bool(c.get("sample")) for c in cohort.values()),
    }
