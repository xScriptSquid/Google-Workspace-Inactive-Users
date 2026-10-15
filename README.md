# gw-inactive-users

A Google Workspace inactive-user audit. It uses the Admin SDK Directory API to
find users with no recent login, renders a clean PDF report, and optionally
uploads it to a Google Drive folder.

Defaults to a dry run, so out of the box it reports and changes nothing.

## What it does

- Pages through every user in the Workspace via the Admin SDK Directory API
- Flags users with no login in a configurable window (default 30 days), treating
  the Google "never logged in" sentinel (`1970-01-01`) as inactive
- Skips shared, role, and system accounts via prefix and domain exclusion lists
- Skips accounts created inside the window (too new to judge)
- Builds an HTML report and renders it to PDF with headless Edge
- Optionally uploads the PDF to a Google Drive folder

With `DRY_RUN = True` (the default) it only reports. Set it to `False` to have it
delete the flagged accounts through the Directory API. Leave it on `True` unless
you know exactly what you want removed.

## Requirements

- A Google Cloud **service account** with **domain-wide delegation** enabled
- A Workspace super-admin to delegate to (set via `GW_ADMIN_EMAIL`)
- These OAuth scopes authorized for the service account in the Admin console:
  - `https://www.googleapis.com/auth/admin.directory.user.readonly`
  - `https://www.googleapis.com/auth/admin.directory.user` (only needed if you run
    with `DRY_RUN = False`)
  - `https://www.googleapis.com/auth/drive.file`
- Python 3.11+ with `google-api-python-client` and `google-auth`
- Microsoft Edge installed (used to render the PDF)

## Setup

The service account key and org-specific values are kept out of the code.

```bash
pip install google-api-python-client google-auth

export GW_ADMIN_EMAIL="admin@yourdomain.com"
export ORG_LABEL="Your Organization"

# Optional, only if uploading the report to Drive:
export DRIVE_FOLDER_ID="your-drive-folder-id"
```

Place your service account key at `serviceaccount.json` next to the script (that
file is gitignored and never committed).

Then edit the exclusion lists near the top of the script
(`EXCLUDE_PREFIXES`, `EXCLUDE_DOMAINS`) to match the shared and system accounts in
your Workspace. The ones included are placeholder samples.

## Usage

```bash
python GW_Inactive.py
```

It prints the flagged users, writes a dated PDF, and (if configured) uploads it
to Drive.

## Safety

- Read-only by default. Deleting a Workspace user removes their account and data,
  so review the report before ever running with `DRY_RUN = False`.
- "Last login" reflects what the Directory API reports and may not capture every
  access path, so treat results as candidates to review, not a kill list.
- No credentials or org data are committed. The service account key stays in a
  gitignored `serviceaccount.json`, and org-specific values come from environment
  variables.

## License

MIT