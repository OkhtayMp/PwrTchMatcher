from __future__ import annotations

APP_NAME = "PWR / TCH Matcher"
GITHUB_URL = "https://github.com/OkhtayMp/pwr-tch-matcher"
CREATE_COLUMN = "__CREATE_POWER_TT__"

INTERNAL = {
    "pwr_row": "__matcher_pwr_row",
    "pwr_site": "__matcher_pwr_site",
    "pwr_from": "__matcher_pwr_from",
    "pwr_to": "__matcher_pwr_to",
    "tch_row": "__matcher_tch_row",
    "tch_site": "__matcher_tch_site",
    "tch_fault": "__matcher_tch_fault",
    "tch_ticket": "__matcher_tch_ticket",
    "match_ticket": "__matcher_match_ticket",
}

DATE_FORMATS = (
    "%m/%d/%Y %H:%M:%S",
    "%-m/%-d/%Y %-H:%M:%S",
    "%m/%d/%Y %H:%M",
    "%-m/%-d/%Y %-H:%M",
    "%Y-%m-%d %H:%M:%S",
    "%Y-%m-%d %H:%M",
    "%Y/%m/%d %H:%M:%S",
    "%Y/%m/%d %H:%M",
    "%Y-%m-%d",
)

PWR_ROLES = (
    ("site", "Site", ("Site Name", "Site", "Zone", "site_name", "site")),
    ("start", "Started", ("First Occurred On", "First Occurred", "First Occur Time", "Start Time")),
    ("end", "Cleared", ("Cleared On", "Cleared", "Clear Time", "End Time", "Ended On")),
)

TCH_ROLES = (
    ("site", "Zone / Site", ("Zone", "Site Name", "Site", "site_name", "site")),
    (
        "fault_time",
        "Fault time",
        ("Fault First Occur Time", "First Occurred On", "Fault Time", "First Occur Time"),
    ),
    ("ticket", "Ticket ID", ("Ticket ID", "Ticket", "ticket_id")),
)
