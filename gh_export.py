#!/usr/bin/env python3
import argparse, csv, datetime as dt, time, sys, re
import requests
from urllib.parse import urlparse

API = "https://api.github.com"

def daterange_defaults():
    today = dt.datetime.utcnow().date()
    since = (today - dt.timedelta(days=182))  # ~6 months
    return since.isoformat(), today.isoformat()

def req(session, method, url, **kwargs):
    r = session.request(method, url, **kwargs)
    if r.status_code == 403 and r.headers.get("X-RateLimit-Remaining") == "0":
        reset = int(r.headers.get("X-RateLimit-Reset", "0"))
        sleep_s = max(reset - int(time.time()) + 2, 10)
        time.sleep(sleep_s)
        r = session.request(method, url, **kwargs)
    r.raise_for_status()
    return r

def paginate(session, url, params=None, headers=None):
    params = params or {}
    headers = headers or {}
    while True:
        r = req(session, "GET", url, params=params, headers=headers)
        data = r.json()
        yield data
        # Pagination via Link
        link = r.headers.get("Link")
        if not link:
            break
        next_url = None
        for part in link.split(","):
            if 'rel="next"' in part:
                m = re.search(r'<([^>]+)>', part)
                if m: next_url = m.group(1)
        if not next_url:
            break
        url = next_url
        params = None  # ya vienen en el next_url

def iso(dtstr):
    # normalize timestamps to 'YYYY-MM-DDTHH:MM:SSZ'
    if not dtstr: return ""
    try:
        return dt.datetime.fromisoformat(dtstr.replace("Z","+00:00")).strftime("%Y-%m-%dT%H:%M:%SZ")
    except Exception:
        return dtstr

def search_issues(session, q, per_page=100):
    url = f"{API}/search/issues"
    for page in paginate(session, url, params={"q": q, "per_page": per_page}):
        for item in page.get("items", []):
            yield item

def get_pr_details(session, repo_full, number):
    url = f"{API}/repos/{repo_full}/pulls/{number}"
    r = req(session, "GET", url)
    return r.json()

def list_user_repos(session, user):
    # Own repos and where user is member (public and private if token allows)
    repos = []
    for page in paginate(session, f"{API}/users/{user}/repos", params={"per_page":100,"type":"all","sort":"updated"}):
        repos.extend(page)
    return [r["full_name"] for r in repos]

def list_commits_for_repo(session, repo_full, author, since_iso, until_iso):
    url = f"{API}/repos/{repo_full}/commits"
    params = {"author": author, "since": since_iso+"T00:00:00Z", "until": until_iso+"T23:59:59Z", "per_page": 100}
    try:
        for page in paginate(session, url, params=params):
            for c in page:
                yield c
    except requests.HTTPError as e:
        # Repos without permissions or archived: ignore silently
        return

def main():
    parser = argparse.ArgumentParser(description="Export GitHub activity (last 6 months) to CSV/MD.")
    parser.add_argument("--token", required=True, help="GitHub Personal Access Token")
    parser.add_argument("--user", required=True, help="GitHub username (login)")
    parser.add_argument("--since", help="YYYY-MM-DD (default: today-6months)")
    parser.add_argument("--until", help="YYYY-MM-DD (default: today)")
    parser.add_argument("--out", default="github_activity.csv", help="Output CSV file")
    args = parser.parse_args()

    since, until = (args.since, args.until)
    if not since or not until:
        since, until = daterange_defaults()

    session = requests.Session()
    session.headers.update({
        "Accept": "application/vnd.github+json",
        "Authorization": f"token {args.token}",
        "User-Agent": "gh-6mo-export"
    })

    rows = []
    summary = {"PR":0, "Commit":0, "Issue":0, "Review":0}
    def add_row(category, repo, identifier, title, url, created_at, extra=None):
        nonlocal rows, summary
        summary[category] = summary.get(category,0)+1
        base = {
            "category": category,
            "repo": repo,
            "id": identifier,
            "title_or_message": title or "",
            "url": url or "",
            "created_at": iso(created_at),
        }
        if extra:
            base.update(extra)
        rows.append(base)

    print(f"⏳ Range: {since} .. {until}", file=sys.stderr)

    # 1) Pull Requests created by the user
    print("→ Searching created PRs…", file=sys.stderr)
    pr_q = f'is:pr author:{args.user} created:{since}..{until}'
    for item in search_issues(session, pr_q):
        repo_full = "/".join(urlparse(item["repository_url"]).path.strip("/").split("/")[-2:])
        number = item["number"]
        pr_html = item["html_url"]
        pr_title = item["title"]
        created_at = item["created_at"]
        # details (additions, deletions, files, merged)
        try:
            prd = get_pr_details(session, repo_full, number)
            extra = {
                "state": prd.get("state",""),
                "merged": str(bool(prd.get("merged_at"))),
                "merged_at": iso(prd.get("merged_at")),
                "additions": prd.get("additions",0),
                "deletions": prd.get("deletions",0),
                "changed_files": prd.get("changed_files",0),
            }
        except requests.HTTPError:
            extra = {}
        add_row("PR", repo_full, f"PR#{number}", pr_title, pr_html, created_at, extra)

    # 2) Issues created by the user
    print("→ Searching created Issues…", file=sys.stderr)
    issue_q = f'is:issue author:{args.user} created:{since}..{until}'
    for item in search_issues(session, issue_q):
        repo_full = "/".join(urlparse(item["repository_url"]).path.strip("/").split("/")[-2:])
        number = item["number"]
        add_row("Issue", repo_full, f"Issue#{number}", item["title"], item["html_url"], item["created_at"],
                {"state": item.get("state",""),
                 "labels": ",".join([l["name"] for l in item.get("labels",[])])})

    # 3) PRs reviewed by the user (code reviews)
    print("→ Searching reviewed PRs…", file=sys.stderr)
    review_q = f'type:pr reviewed-by:{args.user} updated:{since}..{until}'
    for item in search_issues(session, review_q):
        repo_full = "/".join(urlparse(item["repository_url"]).path.strip("/").split("/")[-2:])
        number = item["number"]
        add_row("Review", repo_full, f"PR#{number}", item["title"], item["html_url"], item["created_at"],
                {"state": item.get("state","")})

    # 4) User commits (iterating over user repos)
    print("→ Listing repos and extracting commits…", file=sys.stderr)
    repos = list_user_repos(session, args.user)
    since_iso = since
    until_iso = until
    for repo_full in repos:
        for c in list_commits_for_repo(session, repo_full, args.user, since_iso, until_iso):
            sha = c.get("sha","")
            msg = (c.get("commit",{}) or {}).get("message","").split("\n")[0][:300]
            html_url = c.get("html_url","") or f"https://github.com/{repo_full}/commit/{sha}"
            created_at = (c.get("commit",{}) or {}).get("author",{}).get("date","")
            add_row("Commit", repo_full, sha[:12], msg, html_url, created_at)

    # Write unified CSV
    fieldnames = ["category","repo","id","title_or_message","url","created_at",
                  "state","merged","merged_at","additions","deletions","changed_files","labels"]
    with open(args.out, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=fieldnames)
        w.writeheader()
        for r in rows:
            for k in fieldnames:
                if k not in r: r[k] = ""
            w.writerow(r)

    # Summary Markdown
    by_repo = {}
    for r in rows:
        by_repo.setdefault(r["repo"], {"PR":0,"Commit":0,"Issue":0,"Review":0})
        by_repo[r["repo"]][r["category"]] = by_repo[r["repo"]].get(r["category"],0)+1

    with open("github_activity_summary.md","w",encoding="utf-8") as md:
        md.write(f"# GitHub Activity Summary ({since}..{until})\n\n")
        md.write(f"- PRs: {summary.get('PR',0)}\n")
        md.write(f"- Commits: {summary.get('Commit',0)}\n")
        md.write(f"- Issues: {summary.get('Issue',0)}\n")
        md.write(f"- Reviews: {summary.get('Review',0)}\n\n")
        md.write("## By repo\n\n")
        for repo, counts in sorted(by_repo.items(), key=lambda x: sum(x[1].values()), reverse=True):
            total = sum(counts.values())
            md.write(f"- **{repo}**: {total} (PR: {counts.get('PR',0)}, Commits: {counts.get('Commit',0)}, Issues: {counts.get('Issue',0)}, Reviews: {counts.get('Review',0)})\n")

    print(f"✅ Done. CSV: {args.out} | Summary: github_activity_summary.md", file=sys.stderr)

if __name__ == "__main__":
    main()
