import threading
import unittest
from unittest.mock import Mock

from main import (
    GHOSTLive,
    OUTLOOK_INBOX_SUMMARY_TOOL_DECLARATIONS,
    OUTLOOK_SUMMARY_ROUTING_INSTRUCTIONS,
)
from ui.outlook_report import (
    OutlookReportDashboardMixin,
    _validate_inbox_report,
)

_VALID_REPORT = {
    "overview": "Three messages need attention.",
    "scan_complete": True,
    "coverage_note": "All Inbox pages reviewed.",
    "metrics": {
        "received_count": 12,
        "unread_count": 3,
        "action_needed_count": 2,
        "meeting_invite_count": 1,
    },
    "priority_emails": [],
    "action_items": [],
    "upcoming_meetings": [],
    "email_volume_by_hour": [],
    "category_counts": [],
    "top_senders": [],
}


class OutlookInboxSummaryTests(unittest.TestCase):
    def test_inbox_and_executive_requests_share_one_report_workflow(self):
        self.assertIn("email summary report", OUTLOOK_SUMMARY_ROUTING_INSTRUCTIONS)
        self.assertIn("executive report", OUTLOOK_SUMMARY_ROUTING_INSTRUCTIONS)
        self.assertIn("same complete Inbox summary workflow", OUTLOOK_SUMMARY_ROUTING_INSTRUCTIONS)
        self.assertEqual(
            [tool["name"] for tool in OUTLOOK_INBOX_SUMMARY_TOOL_DECLARATIONS],
            ["show_outlook_inbox_summary"],
        )

        live = object.__new__(GHOSTLive)
        live.ui = Mock()
        handlers = live._build_tool_handlers()
        self.assertNotIn("outlook_executive_report", handlers)
        self.assertIn("show_outlook_inbox_summary", handlers)

    def test_summary_tool_opens_the_ui_popup(self):
        live = object.__new__(GHOSTLive)
        live.ui = Mock()

        handler, timeout = live._build_tool_handlers()[
            "show_outlook_inbox_summary"
        ]

        result = handler({"report": _VALID_REPORT})

        self.assertEqual(result, {"status": "shown"})
        self.assertEqual(timeout, 15)
        live.ui.show_outlook_inbox_summary.assert_called_once_with(_VALID_REPORT)

    def test_popup_request_is_dispatched_to_tk_main_thread(self):
        ui = object.__new__(OutlookReportDashboardMixin)
        ui._main_thread = threading.current_thread()
        ui._safe_ui = Mock()
        ui._render_outlook_inbox_summary = Mock()

        ui.show_outlook_inbox_summary(_VALID_REPORT)

        ui._render_outlook_inbox_summary.assert_called_once_with(_VALID_REPORT)

    def test_unstructured_summary_is_rejected(self):
        ui = object.__new__(OutlookReportDashboardMixin)

        with self.assertRaisesRegex(ValueError, "must be a report object"):
            ui.show_outlook_inbox_summary("  ")

    def test_partial_report_requires_a_coverage_note(self):
        report = dict(_VALID_REPORT)
        report["scan_complete"] = False
        report["coverage_note"] = ""

        with self.assertRaisesRegex(ValueError, "explain their coverage gaps"):
            _validate_inbox_report(report)

    def test_negative_metric_counts_are_rejected(self):
        report = dict(_VALID_REPORT)
        report["metrics"] = dict(_VALID_REPORT["metrics"])
        report["metrics"]["unread_count"] = -1

        with self.assertRaisesRegex(ValueError, "invalid unread_count"):
            _validate_inbox_report(report)


if __name__ == "__main__":
    unittest.main()
