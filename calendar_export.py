#!/usr/bin/env python3
"""Export calendar meetings (events you were present in) for performance review context."""
import argparse
import csv
import datetime as dt
from collections import defaultdict
from typing import Any, Dict, List

from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from google.auth.transport.requests import Request
from googleapiclient.discovery import build

SCOPES = [
    "https://www.googleapis.com/auth/calendar.readonly",
    "https://www.googleapis.com/auth/drive.activity.readonly",
    "https://www.googleapis.com/auth/drive.metadata.readonly",
]


def default_range():
    today = dt.date.today()
    since = (today - dt.timedelta(days=182)).isoformat()
    until = today.isoformat()
    return since, until


def get_creds():
    creds = None
    try:
        creds = Credentials.from_authorized_user_file("token.json", SCOPES)
    except Exception:
        pass
    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            creds.refresh(Request())
        else:
            flow = InstalledAppFlow.from_client_secrets_file("credentials.json", SCOPES)
            creds = flow.run_local_server(port=0)
        with open("token.json", "w") as f:
            f.write(creds.to_json())
    return creds


def parse_event_time(event: Dict[str, Any], key: str) -> str:
    """Get start or end time as ISO string from event (date or dateTime)."""
    raw = (event.get(key) or {})
    if "dateTime" in raw:
        return (raw.get("dateTime") or "").replace("Z", "Z")
    if "date" in raw:
        return (raw.get("date") or "") + "T00:00:00Z"
    return ""


def main():
    ap = argparse.ArgumentParser(
        description="Export calendar meetings (events on your primary calendar) to CSV and optional summary."
    )
    ap.add_argument("--since", help="YYYY-MM-DD (default: today-6m)")
    ap.add_argument("--until", help="YYYY-MM-DD (default: today)")
    ap.add_argument("--out", default="meetings_activity.csv", help="Output CSV")
    ap.add_argument("--summary_md", default="meetings_summary.md", help="Markdown summary")
    args = ap.parse_args()

    since, until = (args.since, args.until)
    if not since or not until:
        since, until = default_range()

    creds = get_creds()
    cal = build("calendar", "v3", credentials=creds)

    time_min = f"{since}T00:00:00Z"
    time_max = f"{until}T23:59:59Z"

    rows: List[Dict[str, Any]] = []
    page_token = None
    while True:
        resp = (
            cal.events()
            .list(
                calendarId="primary",
                timeMin=time_min,
                timeMax=time_max,
                singleEvents=True,
                orderBy="startTime",
                pageToken=page_token or None,
            )
            .execute()
        )
        for event in resp.get("items", []):
            start_str = parse_event_time(event, "start")
            end_str = parse_event_time(event, "end")
            date_str = start_str[:10] if start_str else ""
            title = (event.get("summary") or "").strip() or "(No title)"
            link = event.get("htmlLink") or ""
            organizer = (event.get("organizer") or {}).get("email") or ""
            attendees = event.get("attendees") or []
            attendees_count = len(attendees)
            # Conference link (Meet, etc.)
            conf = event.get("conferenceData") or {}
            entry = (conf.get("entryPoints") or [])
            meet_link = ""
            for ep in entry:
                if (ep.get("entryPointType") or "").upper() == "VIDEO":
                    meet_link = ep.get("uri") or ""
                    break
            if not meet_link and entry:
                meet_link = entry[0].get("uri") or ""

            rows.append({
                "date": date_str,
                "start": start_str,
                "end": end_str,
                "title": title,
                "link": link,
                "meet_link": meet_link,
                "organizer": organizer,
                "attendees_count": attendees_count,
            })
        page_token = resp.get("nextPageToken")
        if not page_token:
            break

    fieldnames = ["date", "start", "end", "title", "link", "meet_link", "organizer", "attendees_count"]
    with open(args.out, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=fieldnames)
        w.writeheader()
        w.writerows(rows)

    # Summary by week
    by_week: Dict[str, int] = defaultdict(int)
    for r in rows:
        if r["date"]:
            try:
                d = dt.datetime.strptime(r["date"], "%Y-%m-%d")
                week = d.strftime("%Y-W%W")
                by_week[week] += 1
            except ValueError:
                pass

    with open(args.summary_md, "w", encoding="utf-8") as md:
        md.write(f"# Calendar meetings summary ({since} .. {until})\n\n")
        md.write(f"- Total events: **{len(rows)}**\n\n")
        md.write("## By week\n\n")
        for week in sorted(by_week.keys(), reverse=True):
            md.write(f"- **{week}**: {by_week[week]} meetings\n")

    print(f"✅ Meetings export: {args.out}  |  Summary: {args.summary_md}  |  Events: {len(rows)}")
    print(f"ℹ️ Range: {since} .. {until}")


if __name__ == "__main__":
    main()
