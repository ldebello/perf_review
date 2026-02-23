#!/usr/bin/env python3
import argparse, csv, datetime as dt, time
from typing import List, Dict, Any

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
    since = (today - dt.timedelta(days=182)).isoformat()  # ~6 months
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

def iso(dtstr):
    # normalize to YYYY-MM-DDTHH:MM:SSZ
    if not dtstr:
        return ""
    try:
        return dt.datetime.fromisoformat(dtstr.replace("Z","+00:00")).strftime("%Y-%m-%dT%H:%M:%SZ")
    except Exception:
        return dtstr

def is_me_actor(actor: Dict[str,Any]) -> bool:
    # Drive Activity v2 marks knownUser.isCurrentUser
    user = actor.get("user", {})
    ku = user.get("knownUser", {})
    return bool(ku.get("isCurrentUser", False))

def get_driveitem_info(target: Dict[str,Any]):
    di = target.get("driveItem", {}) or target.get("file", {}) or {}
    title = (di.get("title") or di.get("name") or "")
    name = di.get("name", "")  # items/XYZ...
    mime = di.get("mimeType", "")
    return title, name, mime

def action_label(primary: Dict[str,Any]) -> str:
    for k in ["create", "edit", "comment", "rename", "move", "restore", "delete", "permissionChange"]:
        if k in primary:
            return k.upper()
    return "OTHER"

def activity_time(activity: Dict[str,Any]) -> str:
    # Use timestamp (if timeRange exists, take endTime)
    if "timestamp" in activity:
        return activity["timestamp"]
    tr = activity.get("timeRange", {})
    return tr.get("endTime") or tr.get("startTime") or ""

def build_doc_url(item_name: str) -> str:
    # item_name: "items/XXXXXXXXXXXXXXXXX" -> fileId
    if not item_name:
        return ""
    file_id = item_name.split("/")[-1]
    return f"https://docs.google.com/document/d/{file_id}/edit"

def parse_ts(ts: str):
    if not ts:
        return None
    try:
        return dt.datetime.fromisoformat(ts.replace("Z", "+00:00"))
    except Exception:
        return None

def main():
    ap = argparse.ArgumentParser(description="Export Google Docs activities (create/edit/comment) and build summary by file.")
    ap.add_argument("--since", help="YYYY-MM-DD (default: today-6m)")
    ap.add_argument("--until", help="YYYY-MM-DD (default: today)")
    ap.add_argument("--out", default="google_docs_activity.csv", help="Detailed output CSV")
    ap.add_argument("--summary_csv", default="google_docs_files_summary.csv", help="CSV summary by file")
    ap.add_argument("--summary_md", default="google_docs_files_summary.md", help="Markdown summary by file")
    args = ap.parse_args()

    since, until = (args.since, args.until)
    if not since or not until:
        since, until = default_range()

    creds = get_creds()
    da = build("driveactivity", "v2", credentials=creds)  # Drive Activity
    # drv = build("drive", "v3", credentials=creds)       # optional if you want extra metadata

    # Temporal filter; then filter in code by actor=me, actions and MIME
    filter_str = f'time >= "{since}T00:00:00Z" AND time <= "{until}T23:59:59Z"'
    page_token = None

    rows: List[Dict[str,Any]] = []
    mime_docs = "application/vnd.google-apps.document"
    page_size = 100

    while True:
        body = {"filter": filter_str, "pageSize": page_size}
        if page_token:
            body["pageToken"] = page_token
        resp = da.activity().query(body=body).execute()
        acts = resp.get("activities", [])
        for a in acts:
            # Filter: actor = me and action CREATE/EDIT/COMMENT
            actors = a.get("actors", [])
            if not any(is_me_actor(ac) for ac in actors):
                continue
            primary = a.get("primaryActionDetail", {})
            act = action_label(primary)
            if act not in ("CREATE","EDIT","COMMENT"):
                continue

            # Main target (there can be several)
            targets = a.get("targets", [])
            if not targets:
                continue
            title, item_name, mime = "", "", ""
            for t in targets:
                title, item_name, mime = get_driveitem_info(t)
                if item_name:
                    break
            if not item_name or mime != mime_docs:
                continue  # only Google Docs

            when = iso(activity_time(a))
            row = {
                "date": when[:10],
                "timestamp": when,
                "action": act,                 # CREATE / EDIT / COMMENT
                "title": title,
                "file_id": item_name.split("/")[-1],
                "url": build_doc_url(item_name),
                "mimeType": mime,
            }
            rows.append(row)

        page_token = resp.get("nextPageToken")
        if not page_token:
            break
        time.sleep(0.2)

    # Deduplicate by (timestamp, action, file_id) in case API groups them
    seen = set()
    dedup = []
    for r in rows:
        key = (r["timestamp"], r["action"], r["file_id"])
        if key in seen:
            continue
        seen.add(key)
        dedup.append(r)
    rows = dedup

    # === Detailed CSV ===
    fieldnames = ["date","timestamp","action","title","url","file_id","mimeType"]
    with open(args.out, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=fieldnames)
        w.writeheader()
        w.writerows(rows)

    # === SUMMARY BY FILE (NO REPEATS) ===
    files: Dict[str, Dict[str, Any]] = {}
    for r in rows:
        fid = r["file_id"]
        if not fid:
            continue
        d = files.setdefault(fid, {
            "file_id": fid,
            "title": "",
            "url": "",
            "first_activity_dt": None,  # store datetime for sorting
            "last_activity_dt": None,
            "creates": 0,
            "edits": 0,
            "comments": 0,
            "total_actions": 0,
            "active_days": set(),
        })
        if r.get("title"):
            d["title"] = r["title"]
        if r.get("url"):
            d["url"] = r["url"]

        ts_dt = parse_ts(r.get("timestamp",""))
        if ts_dt:
            if d["first_activity_dt"] is None or ts_dt < d["first_activity_dt"]:
                d["first_activity_dt"] = ts_dt
            if d["last_activity_dt"] is None or ts_dt > d["last_activity_dt"]:
                d["last_activity_dt"] = ts_dt
            d["active_days"].add(ts_dt.date().isoformat())

        act = r.get("action")
        if act == "CREATE":
            d["creates"] += 1
        elif act == "EDIT":
            d["edits"] += 1
        elif act == "COMMENT":
            d["comments"] += 1
        d["total_actions"] += 1

    files_list = []
    for fid, d in files.items():
        first_str = d["first_activity_dt"].strftime("%Y-%m-%d %H:%M:%S %Z") if d["first_activity_dt"] else ""
        last_str  = d["last_activity_dt"].strftime("%Y-%m-%d %H:%M:%S %Z") if d["last_activity_dt"] else ""
        files_list.append({
            "file_id": d["file_id"],
            "title": d["title"],
            "url": d["url"],
            "first_activity": first_str,
            "last_activity": last_str,
            "creates": d["creates"],
            "edits": d["edits"],
            "comments": d["comments"],
            "total_actions": d["total_actions"],
            "active_days": len(d["active_days"]),
            "_last_sort": d["last_activity_dt"].isoformat() if d["last_activity_dt"] else "",
        })

    # Sort by last activity desc
    files_list.sort(key=lambda x: x["_last_sort"], reverse=True)

    # CSV summary by file
    fieldnames_sum = ["file_id","title","url","first_activity","last_activity","creates","edits","comments","total_actions","active_days"]
    with open(args.summary_csv, "w", newline="", encoding="utf-8") as fsum:
        w = csv.DictWriter(fsum, fieldnames=fieldnames_sum)
        w.writeheader()
        for row in files_list:
            w.writerow({k: row[k] for k in fieldnames_sum})

    # Markdown summary by file
    with open(args.summary_md, "w", encoding="utf-8") as md:
        md.write(f"# Google Docs – Summary by file ({since}..{until})\n\n")
        md.write(f"- Total files touched: **{len(files_list)}**\n")
        md.write(f"- Total actions: **{sum(x['total_actions'] for x in files_list)}**\n\n")
        md.write("## Files (ordered by last activity)\n\n")
        for x in files_list:
            title = x['title'] or '(no title)'
            md.write(f"- **{title}**  \n")
            md.write(f"  URL: {x['url']}\n")
            md.write(f"  — Last activity: {x['last_activity']} | Actions: {x['total_actions']} (Create: {x['creates']}, Edit: {x['edits']}, Comment: {x['comments']}) | Active days: {x['active_days']}\n\n")

    # Console totals
    by_action = {}
    for r in rows:
        by_action[r["action"]] = by_action.get(r["action"], 0) + 1
    print(f"✅ Detailed export: {args.out}  |  Records: {len(rows)}  |  {by_action}")
    print(f"📄 Summary by file: {args.summary_csv}  |  {args.summary_md}")
    print(f"ℹ️ Range: {since} .. {until}")

if __name__ == "__main__":
    main()
