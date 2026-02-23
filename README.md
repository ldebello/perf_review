# Performance Review Tools

This repository contains tools to export and analyze your development activity for performance reviews.

## Scripts

- **`gh_export.py`** - Exports GitHub activity (commits, PRs, issues) to CSV
- **`gdocs_export.py`** - Exports Google Docs activity and file summaries to CSV/Markdown
- **`calendar_export.py`** - Exports calendar meetings (events you were present in) to CSV and a Markdown summary

## Prerequisites

### Python Environment

```bash
# Create virtual environment
uv venv .venv
source .venv/bin/activate

# Install dependencies
uv pip install --upgrade pip wheel setuptools
uv pip install google-api-python-client google-auth-httplib2 google-auth-oauthlib
```

### GitHub Setup

1. Go to [GitHub Settings > Developer settings > Personal access tokens](https://github.com/settings/tokens)
2. Generate a **Classic Personal Access Token** (not fine-grained)
3. Select `repo` scope to access all your repositories
4. For organizations with SAML, click "Enable SSO" for each organization after creating the token

### Google Setup (Docs + Calendar)

One project and one OAuth app cover both **Google Docs** and **Calendar** exports.

1. **Project**
   - Go to [Google Cloud Console](https://console.cloud.google.com/)
   - Create a new project (or use an existing one)

2. **Enable APIs**
   - Open **APIs & Services** → **Library**
   - Enable these three APIs (search by name, then **Enable**):
     - **Drive Activity API** — for Docs activity
     - **Google Drive API** — for Drive metadata
     - **Google Calendar API** — for calendar/meeting export

3. **OAuth credentials**
   - **APIs & Services** → **Credentials** → **Create credentials** → **OAuth client ID**
   - Application type: **Desktop application**
   - Download the JSON and save it as `credentials.json` in the project root

4. **First run**
   - When you first run `gdocs_export.py` or `calendar_export.py`, the browser opens for sign-in.
   - You grant read-only access; the scripts request these scopes:
     - `https://www.googleapis.com/auth/drive.activity.readonly`
     - `https://www.googleapis.com/auth/drive.metadata.readonly`
     - `https://www.googleapis.com/auth/calendar.readonly`
   - After you approve, `token.json` is created (or updated). Later runs use it and won’t ask again.

## Usage

### GitHub Activity Export

```bash
source .venv/bin/activate
python gh_export.py --token <your_github_token> --user <your_github_username> --since 2025-02-01 --until 2026-01-31
```

### Google Docs Activity Export

```bash
source .venv/bin/activate
python gdocs_export.py --since 2025-02-01 --until 2026-01-31 \
  --out google_docs_activity.csv \
  --summary_csv google_docs_files_summary.csv \
  --summary_md google_docs_files_summary.md
```

### Calendar / meeting export

```bash
source .venv/bin/activate
python calendar_export.py --since 2025-02-01 --until 2026-01-31
```

Optional: `--out meetings_activity.csv` and `--summary_md meetings_summary.md` (these are the defaults).

**Note:** If you don't specify dates, the scripts will default to approximately 6 months back from today.

## Output Files

- `github_activity.csv` - GitHub commits, PRs, and issues
- `github_activity_summary.md` - Markdown summary of GitHub activity
- `google_docs_activity.csv` - Google Docs activity log
- `google_docs_files_summary.csv` - Summary of Google Docs files
- `google_docs_files_summary.md` - Markdown summary of Google Docs activity
- `meetings_activity.csv` - Calendar events (meetings you were present in)
- `meetings_summary.md` - Markdown summary of meetings by week
