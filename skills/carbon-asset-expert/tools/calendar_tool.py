"""Compliance-calendar generation and ICS export.

Dates are a planning template. Statutory deadlines are set by the annual
allocation and surrender notices; pass the confirmed dates as arguments.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, timedelta


@dataclass(frozen=True)
class Milestone:
    day: date
    code: str
    title: str
    owner: str
    note: str = ""


def build_calendar(compliance_year, report=(3, 31), verification=(6, 30), surrender=(12, 31)):
    """Build the seven milestones for a compliance year (emissions of year-1)."""
    if compliance_year < 2000:
        raise ValueError("compliance_year looks implausible")
    y = compliance_year
    events = [
        Milestone(date(y, 1, 15), "DATA", "上年度活动数据封版与月度存证归档", "生产/能源管理"),
        Milestone(date(y, *report), "REPORT", "提交上年度排放报告", "碳资产管理"),
        Milestone(date(y, *verification), "VERIFY", "完成核查并关闭不符合项", "碳资产管理/第三方"),
        Milestone(date(y, 9, 30), "GAP", "缺口复核、CCER 采购与注销", "碳资产管理/财务"),
        Milestone(date(y, 11, 30), "FUND", "履约资金与交易授权到位", "财务/管理层"),
        Milestone(date(y, *surrender), "SURRENDER", "配额清缴", "碳资产管理"),
        Milestone(date(y + 1, 1, 31), "REVIEW", "履约复盘与结转核对", "碳资产管理/审计"),
    ]
    return sorted(events, key=lambda event: event.day)


def to_ics(events, calendar_name="Carbon compliance calendar"):
    """Export milestones as an all-day ICS calendar (CRLF line endings)."""
    lines = [
        "BEGIN:VCALENDAR",
        "VERSION:2.0",
        "PRODID:-//energy-skills//carbon-asset-expert//CN",
        "CALSCALE:GREGORIAN",
        f"X-WR-CALNAME:{calendar_name}",
    ]
    for event in events:
        start = event.day.strftime("%Y%m%d")
        end = (event.day + timedelta(days=1)).strftime("%Y%m%d")
        description = f"{event.owner}｜{event.note}" if event.note else event.owner
        lines.extend(
            [
                "BEGIN:VEVENT",
                f"UID:{start}-{event.code}@energy-skills",
                f"DTSTAMP:{start}T000000Z",
                f"DTSTART;VALUE=DATE:{start}",
                f"DTEND;VALUE=DATE:{end}",
                f"SUMMARY:{event.title}",
                f"DESCRIPTION:{description}",
                "END:VEVENT",
            ]
        )
    lines.append("END:VCALENDAR")
    return "\r\n".join(lines) + "\r\n"
