"""SLA Monitor: live view of every open ticket's SLA clock.

For each ticket that is still waiting on its first response or its resolution
this works out the current SLA target, how much time is left before it, and
which monitor state the ticket is in:

- Overdue: the target has already passed.
- At Risk: more of the SLA window has been used than the escalation warning
  threshold set in HD Settings (an escalation warning is raised).
- On Track: inside the window and below the threshold.
- Paused: the ticket is in a "Paused" status, so the SLA clock is stopped.

Durations are computed on the server, in the system time zone the SLA
targets are stored in, so the browser's clock and time zone don't matter.
"""

import frappe
from frappe import _
from frappe.utils import cint, flt, get_datetime, now_datetime

from helpdesk.utils import agent_only

HD_TICKET = "HD Ticket"

STATE_OVERDUE = "Overdue"
STATE_AT_RISK = "At Risk"
STATE_ON_TRACK = "On Track"
STATE_PAUSED = "Paused"
STATES = (STATE_OVERDUE, STATE_AT_RISK, STATE_ON_TRACK, STATE_PAUSED)

# Most urgent first; used to sort the monitor list.
STATE_ORDER = {state: index for index, state in enumerate(STATES)}

STAGE_RESPONSE = "First Response"
STAGE_RESOLUTION = "Resolution"

# Ticket status categories that still have a running (or paused) SLA clock.
ACTIVE_STATUS_CATEGORIES = ["Open", "Paused"]

MONITOR_FIELDS = [
    "name",
    "subject",
    "status",
    "status_category",
    "priority",
    "agent_group",
    "_assign",
    "sla",
    "agreement_status",
    "response_by",
    "resolution_by",
    "first_responded_on",
    "resolution_date",
    "service_level_agreement_creation",
    "on_hold_since",
    "creation",
]


@frappe.whitelist()
@agent_only
def get_sla_monitor(
    team: str | None = None,
    priority: str | None = None,
    state: str | None = None,
    assigned_to_me: bool = False,
    search: str | None = None,
) -> dict:
    """Open tickets with an SLA, each with its remaining time and monitor state,
    plus a count per state. Respects HD Ticket permissions."""
    settings = get_monitor_settings()
    filters = build_ticket_filters(team, priority, assigned_to_me)
    or_filters = build_search_filters(search)

    rows = frappe.get_list(
        HD_TICKET,
        fields=MONITOR_FIELDS,
        filters=filters,
        or_filters=or_filters,
        order_by="modified desc",
        limit_page_length=0,
    )

    now = now_datetime()
    tickets = [
        ticket
        for ticket in (
            evaluate_ticket(row, now, settings["warning_threshold"]) for row in rows
        )
        if ticket
    ]

    summary = {s: 0 for s in STATES}
    for ticket in tickets:
        summary[ticket["state"]] += 1
    summary["total"] = len(tickets)
    summary["needs_escalation"] = summary[STATE_OVERDUE] + summary[STATE_AT_RISK]

    if state:
        if state not in STATES:
            frappe.throw(_("Unknown SLA state: {0}").format(state))
        tickets = [t for t in tickets if t["state"] == state]

    tickets.sort(key=lambda t: (STATE_ORDER[t["state"]], t["remaining_seconds"]))

    return {
        "settings": settings,
        "summary": summary,
        "tickets": tickets,
        "server_time": str(now),
    }


def get_monitor_settings() -> dict:
    """Thresholds come from HD Settings so they can be tuned without code changes."""
    threshold = flt(_get_setting("sla_warning_threshold"))
    # Outside 1-100 the warning would never fire or would always fire,
    # so fall back to the field's default in the doctype.
    if threshold <= 0 or threshold > 100:
        threshold = flt(_get_field_default("sla_warning_threshold"))
    return {
        "warning_threshold": threshold,
        "refresh_interval": max(cint(_get_setting("sla_monitor_refresh_interval")), 0),
    }


def _get_setting(fieldname: str):
    """Saved HD Settings value, or the doctype default when it was never saved.

    A Single doesn't store defaults of fields added after it was first saved,
    and get_single_value would read such a field as 0 rather than unset.
    """
    Singles = frappe.qb.DocType("Singles")
    saved = (
        frappe.qb.from_(Singles)
        .select(Singles.value)
        .where(Singles.doctype == "HD Settings")
        .where(Singles.field == fieldname)
        .run()
    )
    if saved and saved[0][0] not in (None, ""):
        return saved[0][0]
    return _get_field_default(fieldname)


def _get_field_default(fieldname: str):
    field = frappe.get_meta("HD Settings").get_field(fieldname)
    return field.default if field else None


def build_ticket_filters(
    team: str | None, priority: str | None, assigned_to_me: bool
) -> list:
    filters = [
        ["status_category", "in", ACTIVE_STATUS_CATEGORIES],
        ["sla", "is", "set"],
    ]
    if team:
        filters.append(["agent_group", "=", team])
    if priority:
        filters.append(["priority", "=", priority])
    if frappe.parse_json(assigned_to_me):
        filters.append(["_assign", "like", f"%{frappe.session.user}%"])
    return filters


def build_search_filters(search: str | None) -> list | None:
    search = (search or "").strip()
    if not search:
        return None
    like = f"%{search}%"
    return [
        ["name", "like", like],
        ["subject", "like", like],
        ["raised_by", "like", like],
    ]


def evaluate_ticket(row: dict, now, warning_threshold: float) -> dict | None:
    """Monitor entry for one ticket, or None when no SLA target is pending."""
    stage, due = get_current_target(row)
    if not due:
        return None

    start = get_datetime(row.service_level_agreement_creation or row.creation)
    is_paused = row.status_category == "Paused" or bool(row.on_hold_since)
    # A paused clock is frozen at the moment it was paused.
    reference = get_datetime(row.on_hold_since) if row.on_hold_since else now

    window_seconds = max((due - start).total_seconds(), 0)
    elapsed_seconds = max((reference - start).total_seconds(), 0)
    remaining_seconds = (due - reference).total_seconds()

    used_percent = (
        round(elapsed_seconds / window_seconds * 100, 1) if window_seconds else 100.0
    )

    state = get_state(remaining_seconds, used_percent, is_paused, warning_threshold)

    return {
        "name": row.name,
        "subject": row.subject,
        "status": row.status,
        "priority": row.priority,
        "agent_group": row.agent_group,
        "assigned_to": frappe.parse_json(row._assign) if row._assign else [],
        "sla": row.sla,
        "agreement_status": row.agreement_status,
        "stage": stage,
        "due": str(due),
        "remaining_seconds": int(remaining_seconds),
        "used_percent": min(used_percent, 100.0),
        "state": state,
        "escalation_warning": get_escalation_message(
            state, stage, remaining_seconds, used_percent
        ),
    }


def get_current_target(row: dict):
    """The SLA target the ticket is racing against right now."""
    if not row.first_responded_on and row.response_by:
        return STAGE_RESPONSE, get_datetime(row.response_by)
    if not row.resolution_date and row.resolution_by:
        return STAGE_RESOLUTION, get_datetime(row.resolution_by)
    return None, None


def get_state(
    remaining_seconds: float,
    used_percent: float,
    is_paused: bool,
    warning_threshold: float,
) -> str:
    if remaining_seconds < 0:
        # A breach stays a breach even when the ticket is paused afterwards.
        return STATE_OVERDUE
    if is_paused:
        return STATE_PAUSED
    if used_percent >= warning_threshold:
        return STATE_AT_RISK
    return STATE_ON_TRACK


def get_escalation_message(
    state: str, stage: str, remaining_seconds: float, used_percent: float
) -> str | None:
    stage_label = _(stage)
    if state == STATE_OVERDUE:
        return _("{0} SLA breached {1} ago. Escalate now.").format(
            stage_label, format_duration(-remaining_seconds)
        )
    if state == STATE_AT_RISK:
        return _("{0}% of the {1} window used, {2} left. Consider escalating.").format(
            round(used_percent), stage_label.lower(), format_duration(remaining_seconds)
        )
    return None


def format_duration(seconds: float) -> str:
    """Compact duration such as "2d 3h", "4h 10m" or "12m"."""
    seconds = int(abs(seconds))
    days, seconds = divmod(seconds, 86400)
    hours, seconds = divmod(seconds, 3600)
    minutes = seconds // 60
    if days:
        return f"{days}d {hours}h"
    if hours:
        return f"{hours}h {minutes}m"
    return f"{minutes}m"
