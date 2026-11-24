from datetime import timedelta

import frappe
from frappe.tests.utils import FrappeTestCase as IntegrationTestCase
from frappe.utils import get_datetime

from helpdesk.api.doc import handle_search_filter
from helpdesk.api.sla_monitor import (
    STAGE_RESOLUTION,
    STAGE_RESPONSE,
    STATE_AT_RISK,
    STATE_ON_TRACK,
    STATE_OVERDUE,
    STATE_PAUSED,
    evaluate_ticket,
    format_duration,
    get_monitor_settings,
    get_sla_monitor,
)
from helpdesk.test_utils import make_ticket

NOW = get_datetime("2026-11-24 12:00:00")
THRESHOLD = 75


def ticket_row(**values):
    """A get_list row: 10 hours into a 0:00 to 20:00 response window."""
    row = {
        "name": "1",
        "subject": "Printer on fire",
        "status": "Open",
        "status_category": "Open",
        "priority": "High",
        "agent_group": None,
        "_assign": None,
        "sla": "Default",
        "agreement_status": "First Response Due",
        "response_by": "2026-11-24 20:00:00",
        "resolution_by": "2026-11-26 00:00:00",
        "first_responded_on": None,
        "resolution_date": None,
        "service_level_agreement_creation": "2026-11-24 00:00:00",
        "on_hold_since": None,
        "creation": "2026-11-24 00:00:00",
    }
    row.update(values)
    return frappe._dict(row)


class TestEvaluateTicket(IntegrationTestCase):
    """Remaining time and state of one ticket against its current SLA target."""

    def test_on_track_inside_the_window(self) -> None:
        result = evaluate_ticket(ticket_row(), NOW, THRESHOLD)
        self.assertEqual(result["stage"], STAGE_RESPONSE)
        self.assertEqual(result["state"], STATE_ON_TRACK)
        self.assertEqual(result["remaining_seconds"], 8 * 3600)
        self.assertEqual(result["used_percent"], 60.0)
        self.assertIsNone(result["escalation_warning"])

    def test_at_risk_once_threshold_is_crossed(self) -> None:
        result = evaluate_ticket(
            ticket_row(), NOW + timedelta(hours=4), THRESHOLD
        )  # 16 of 20 hours used = 80%
        self.assertEqual(result["state"], STATE_AT_RISK)
        self.assertIn("80%", result["escalation_warning"])

    def test_overdue_after_the_target(self) -> None:
        result = evaluate_ticket(ticket_row(), NOW + timedelta(hours=10), THRESHOLD)
        self.assertEqual(result["state"], STATE_OVERDUE)
        self.assertEqual(result["remaining_seconds"], -2 * 3600)
        self.assertEqual(result["used_percent"], 100.0)
        self.assertIn("2h 0m", result["escalation_warning"])

    def test_resolution_is_tracked_after_first_response(self) -> None:
        row = ticket_row(first_responded_on="2026-11-24 01:00:00")
        result = evaluate_ticket(row, NOW, THRESHOLD)
        self.assertEqual(result["stage"], STAGE_RESOLUTION)
        self.assertEqual(result["due"], "2026-11-26 00:00:00")

    def test_paused_clock_is_frozen(self) -> None:
        row = ticket_row(status_category="Paused", on_hold_since="2026-11-24 05:00:00")
        result = evaluate_ticket(row, NOW + timedelta(days=3), THRESHOLD)
        self.assertEqual(result["state"], STATE_PAUSED)
        self.assertEqual(result["remaining_seconds"], 15 * 3600)

    def test_breach_before_pause_stays_overdue(self) -> None:
        row = ticket_row(status_category="Paused", on_hold_since="2026-11-24 21:00:00")
        result = evaluate_ticket(row, NOW, THRESHOLD)
        self.assertEqual(result["state"], STATE_OVERDUE)

    def test_no_pending_target_is_skipped(self) -> None:
        row = ticket_row(
            first_responded_on="2026-11-24 01:00:00",
            resolution_date="2026-11-24 02:00:00",
        )
        self.assertIsNone(evaluate_ticket(row, NOW, THRESHOLD))

    def test_format_duration(self) -> None:
        self.assertEqual(format_duration(90061), "1d 1h")
        self.assertEqual(format_duration(3720), "1h 2m")
        self.assertEqual(format_duration(-300), "5m")


class TestMonitorSettings(IntegrationTestCase):
    def test_threshold_comes_from_hd_settings(self) -> None:
        frappe.db.set_single_value("HD Settings", "sla_warning_threshold", 60)
        self.assertEqual(get_monitor_settings()["warning_threshold"], 60)

    def test_out_of_range_threshold_uses_the_default(self) -> None:
        frappe.db.set_single_value("HD Settings", "sla_warning_threshold", 0)
        default = frappe.get_meta("HD Settings").get_field("sla_warning_threshold")
        self.assertEqual(
            get_monitor_settings()["warning_threshold"], float(default.default)
        )

    def test_monitor_returns_summary_and_settings(self) -> None:
        data = get_sla_monitor()
        self.assertEqual(
            data["summary"]["total"],
            sum(
                data["summary"][s] for s in ("Overdue", "At Risk", "On Track", "Paused")
            ),
        )
        self.assertIn("warning_threshold", data["settings"])

    def test_unknown_state_is_rejected(self) -> None:
        with self.assertRaises(frappe.ValidationError):
            get_sla_monitor(state="Exploded")


class TestSearchFilter(IntegrationTestCase):
    """`__search` matches ticket ID, subject or raised-by in one box."""

    @classmethod
    def setUpClass(cls) -> None:
        super().setUpClass()
        cls.ticket = make_ticket(
            subject="Zebra keyboard stuck", raised_by="zebra.search@example.com"
        )

    def test_matches_subject(self) -> None:
        filters = [["__search", "like", "zebra keyboard"]]
        handle_search_filter(filters, "HD Ticket")
        self.assertEqual(filters[0][0], "name")
        self.assertIn(self.ticket.name, filters[0][2])

    def test_matches_raised_by(self) -> None:
        filters = {"__search": ["like", "zebra.search@"]}
        handle_search_filter(filters, "HD Ticket")
        self.assertIn(self.ticket.name, filters["name"][1])

    def test_blank_search_is_dropped(self) -> None:
        filters = [["__search", "like", "  "], ["status", "=", "Open"]]
        handle_search_filter(filters, "HD Ticket")
        self.assertEqual(filters, [["status", "=", "Open"]])
