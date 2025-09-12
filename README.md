# Performance Review Tools

This repository contains tools to export and analyze your development activity for performance reviews.

## Scripts

- **`gh_export.py`** - Exports GitHub activity (commits, PRs, issues) to CSV
- **`gdocs_export.py`** - Exports Google Docs activity and file summaries to CSV/Markdown

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

### Google Docs Setup

1. Go to [Google Cloud Console](https://console.cloud.google.com/)
2. Create a new project (or use existing)
3. Enable these APIs:
   - Drive Activity API
   - Google Drive API
4. Create OAuth 2.0 credentials:
   - Type: Desktop application
   - Download `credentials.json` and place it in the project root
5. On first run, the browser will open for authorization and create `token.json`

## Usage

### GitHub Activity Export

```bash
source .venv/bin/activate
python gh_export.py --token <your_github_token> --user <your_github_username> --since 2025-03-01 --until 2025-09-12
```

### Google Docs Activity Export

```bash
source .venv/bin/activate
python gdocs_export.py --since 2025-03-01 --until 2025-09-12 \
  --out google_docs_activity.csv \
  --summary_csv google_docs_files_summary.csv \
  --summary_md google_docs_files_summary.md
```

**Note:** If you don't specify dates, the scripts will default to approximately 6 months back from today.

## Output Files

- `github_activity.csv` - GitHub commits, PRs, and issues
- `github_activity_summary.md` - Markdown summary of GitHub activity
- `google_docs_activity.csv` - Google Docs activity log
- `google_docs_files_summary.csv` - Summary of Google Docs files
- `google_docs_files_summary.md` - Markdown summary of Google Docs activity
