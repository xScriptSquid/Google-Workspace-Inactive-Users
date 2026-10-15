from __future__ import print_function
import datetime
import html
import io
import os
import pathlib
import subprocess
import sys
import tempfile
from google.oauth2 import service_account
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError
from googleapiclient.http import MediaIoBaseUpload

# Microsoft Edge renders the HTML report to PDF (no extra libraries needed)
EDGE_PATHS = [
    r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe",
    r"C:\Program Files\Microsoft\Edge\Application\msedge.exe",
]

# ====================================
# CONFIGURATION
# ====================================
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
ROOT_DIR = os.path.dirname(SCRIPT_DIR)
if ROOT_DIR not in sys.path:
    sys.path.insert(0, ROOT_DIR)
from report_theme import REPORT_CSS
SERVICE_ACCOUNT_FILE = os.path.join(SCRIPT_DIR, "serviceaccount.json")
ADMIN_EMAIL = os.environ.get("GW_ADMIN_EMAIL", "")
REPORT_DATE = datetime.datetime.now().strftime("%m-%d-%Y")
REPORT_NAME = f"inactive_users_report_{REPORT_DATE}.pdf"
INACTIVITY_DAYS = 30
DRIVE_FOLDER_ID = os.environ.get("DRIVE_FOLDER_ID", "")

# Organization label shown in the report footer
ORG_LABEL = os.environ.get("ORG_LABEL", "Your Organization")

DRY_RUN = True  # Set to False to actually delete users

# Email prefixes to exclude from the report (case-insensitive)
# NOTE: replace these samples with your own shared/role/system accounts.
EXCLUDE_PREFIXES = [
    "parts@", "sales@", "marketing@", "reception@", "shipping@",
    "admin@", "support@", "accounting@", "media@", "archive@",
    "noreply@", "automation@", "google@",
]

# Email domains to exclude from the report (case-insensitive)
EXCLUDE_DOMAINS = [

]

# ====================================
# AUTHENTICATION
# ====================================
SCOPES = [
    "https://www.googleapis.com/auth/admin.directory.user",
    "https://www.googleapis.com/auth/admin.directory.user.readonly",
    "https://www.googleapis.com/auth/drive.file"
]

credentials = service_account.Credentials.from_service_account_file(
    SERVICE_ACCOUNT_FILE, scopes=SCOPES)

delegated_creds = credentials.with_subject(ADMIN_EMAIL)

directory = build("admin", "directory_v1", credentials=delegated_creds)
drive = build("drive", "v3", credentials=delegated_creds)

# ====================================
# FIND INACTIVE USERS
# ====================================
cutoff = datetime.datetime.now(datetime.UTC) - datetime.timedelta(days=INACTIVITY_DAYS)

# Paginate through all users
users = []
page_token = None

while True:
    results = directory.users().list(
        customer="my_customer",
        maxResults=500,
        pageToken=page_token
    ).execute()
    
    users.extend(results.get("users", []))
    page_token = results.get("nextPageToken")
    
    if not page_token:
        break

print(f"📊 Retrieved {len(users)} total users from Google Workspace")

inactive_users = []

for user in users:
    email = user.get("primaryEmail", "")
    email_lower = email.lower()
    
    # Skip excluded email prefixes (case-insensitive)
    if any(email_lower.startswith(prefix.lower()) for prefix in EXCLUDE_PREFIXES):
        continue

    # Skip excluded email domains (case-insensitive)
    if "@" in email_lower and email_lower.split("@", 1)[1] in EXCLUDE_DOMAINS:
        continue
    
    # Skip users created within the last 30 days
    creation_time = user.get("creationTime")
    if creation_time:
        try:
            created_dt = datetime.datetime.fromisoformat(creation_time.replace("Z", "+00:00"))
            if created_dt > cutoff:
                continue
        except:
            pass
    
    last_login = user.get("lastLoginTime")

    if last_login in (None, "1970-01-01T00:00:00.000Z"):
        inactive_users.append(user)
        continue

    last_login_dt = datetime.datetime.fromisoformat(last_login.replace("Z", "+00:00"))

    if last_login_dt < cutoff:
        inactive_users.append(user)

# ====================================
# PROCESS USERS & COLLECT REPORT DATA
# ====================================
if DRY_RUN:
    print(f"\n🔍 DRY RUN MODE - No users will be deleted\n")
    print(f"Found {len(inactive_users)} inactive users (no login in {INACTIVITY_DAYS}+ days):\n")

report_data = []

for user in inactive_users:
    email = user["primaryEmail"]
    name = user.get("name", {}).get("fullName", "")
    last_login = user.get("lastLoginTime", "Never")
    creation_time = user.get("creationTime", "Unknown")
    
    if DRY_RUN:
        print(f"  • {email} ({name}) - Last login: {last_login}")
        status = "WOULD DELETE"
    else:
        try:
            directory.users().delete(userKey=email).execute()
            status = "DELETED"
            print(f"Deleted: {email}")
        except HttpError as e:
            status = f"ERROR: {e}"
            print(f"Error deleting {email}: {e}")
    
    report_data.append({
        "email": email,
        "name": name,
        "creation_time": creation_time,
        "last_login": last_login,
        "status": status
    })

# ====================================
# GENERATE HTML REPORT (in memory)
# ====================================
def format_date(date_str):
    """Format ISO date string to readable format"""
    if date_str in (None, "Never", "Unknown", "1970-01-01T00:00:00.000Z"):
        return "Never"
    try:
        dt = datetime.datetime.fromisoformat(date_str.replace("Z", "+00:00"))
        return dt.strftime("%b %d, %Y at %I:%M %p")
    except:
        return date_str

def get_status_class(status):
    """Return CSS class based on status"""
    if "WOULD DELETE" in status:
        return "status-warning"
    elif "DELETED" in status:
        return "status-success"
    elif "ERROR" in status:
        return "status-error"
    return ""

report_date_display = datetime.datetime.now().strftime("%B %d, %Y at %I:%M %p")
total_users = len(users)
inactive_count = len(inactive_users)
active_count = total_users - inactive_count
deleted_count = sum(1 for r in report_data if r["status"] == "DELETED")

html_content = f'''<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Google Workspace Inactive Users Report</title>
    <style>
{REPORT_CSS}
    </style>
</head>
<body>
    <div class="container">
        <header class="masthead">
            <div class="header-top">
                <div class="title-block">
                    <p class="kicker">Google Workspace</p>
                    <h1>Inactive Users Report</h1>
                    <p class="subtitle">Generated on {report_date_display}</p>
                </div>
                <div class="mode-badge {"dry-run" if DRY_RUN else "live"}">
                    {"Dry Run Mode" if DRY_RUN else "Live Execution"}
                </div>
            </div>
        </header>
        <div class="report-body">
            <div class="stats-grid">
                <div class="stat-card">
                    <div class="stat-label">Total Users</div>
                    <div class="stat-value">{total_users}</div>
                </div>
                <div class="stat-card">
                    <div class="stat-label">Inactive ({INACTIVITY_DAYS}+ days)</div>
                    <div class="stat-value inactive">{inactive_count}</div>
                </div>
                <div class="stat-card">
                    <div class="stat-label">Active Users</div>
                    <div class="stat-value active">{active_count}</div>
                </div>
                <div class="stat-card">
                    <div class="stat-label">{"To Review" if DRY_RUN else "Deleted"}</div>
                    <div class="stat-value">{inactive_count if DRY_RUN else deleted_count}</div>
                </div>
            </div>
            <div class="table-container">
                <table>
                    <thead>
                        <tr>
                            <th>Email</th>
                            <th>Name</th>
                            <th>Created</th>
                            <th>Last Login</th>
                            <th>Status</th>
                        </tr>
                    </thead>
                    <tbody>
'''

# Add table rows
for row in report_data:
    escaped_email = html.escape(row["email"])
    escaped_name = html.escape(row["name"]) if row["name"] else "—"
    formatted_created = format_date(row["creation_time"])
    formatted_last_login = format_date(row["last_login"])
    status_class = get_status_class(row["status"])
    status_text = "Needs Review" if row["status"] == "WOULD DELETE" else row["status"].title()
    
    html_content += f'''                    <tr>
                        <td><span class="email">{escaped_email}</span></td>
                        <td><span class="name">{escaped_name}</span></td>
                        <td><span class="date">{formatted_created}</span></td>
                        <td><span class="date">{formatted_last_login}</span></td>
                        <td><span class="status {status_class}">{status_text}</span></td>
                    </tr>
'''

html_content += f'''                </tbody>
            </table>
        </div>
        <footer>
            <p>Google Workspace Inactive User Audit • {html.escape(ORG_LABEL)}</p>
        </footer>
        </div>
    </div>
</body>
</html>
'''

# ====================================
# GENERATE PDF REPORT (in memory)
# ====================================
edge_exe = next((p for p in EDGE_PATHS if os.path.exists(p)), None)
if not edge_exe:
    print("❌ Microsoft Edge not found - cannot generate the PDF report")
    exit(1)

with tempfile.TemporaryDirectory() as tmp_dir:
    html_path = pathlib.Path(tmp_dir) / "report.html"
    pdf_path = pathlib.Path(tmp_dir) / "report.pdf"
    html_path.write_text(html_content, encoding="utf-8")

    subprocess.run(
        [
            edge_exe,
            "--headless",
            "--disable-gpu",
            "--no-pdf-header-footer",
            f"--user-data-dir={os.path.join(tmp_dir, 'edge-profile')}",
            f"--print-to-pdf={pdf_path}",
            html_path.as_uri(),
        ],
        check=True,
        timeout=120,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )

    if not pdf_path.exists():
        print("❌ Edge did not produce a PDF report")
        exit(1)

    pdf_buffer = io.BytesIO(pdf_path.read_bytes())

# ====================================
# DONE - PRINT SUMMARY
# ====================================
if DRY_RUN:
    print(f"\n📑 PDF Report: {REPORT_NAME}")
    print(f"⚠️  To actually delete these users, set DRY_RUN = False")
else:
    print(f"\n✅ Done!")
    print(f"📑 PDF Report: {REPORT_NAME}")

# ====================================
# UPLOAD TO GOOGLE DRIVE
# ====================================
def upload_to_drive(file_name, file_buffer, mime_type):
    """Upload a file buffer to Google Drive folder"""
    file_metadata = {
        "name": file_name,
        "parents": [DRIVE_FOLDER_ID]
    }
    media = MediaIoBaseUpload(file_buffer, mimetype=mime_type, resumable=True)
    
    # Check if file already exists and delete it
    results = drive.files().list(
        q=f"name='{file_name}' and '{DRIVE_FOLDER_ID}' in parents and trashed=false",
        fields="files(id)"
    ).execute()
    
    for file in results.get("files", []):
        drive.files().delete(fileId=file["id"]).execute()
    
    # Upload new file
    uploaded = drive.files().create(
        body=file_metadata,
        media_body=media,
        fields="id, webViewLink"
    ).execute()
    
    return uploaded.get("webViewLink")

print(f"\n☁️  Uploading PDF report to Google Drive...")

pdf_link = None

try:
    pdf_link = upload_to_drive(REPORT_NAME, pdf_buffer, "application/pdf")
    print(f"✅ PDF uploaded: {pdf_link}")
except HttpError as e:
    print(f"❌ Drive upload failed: {e}")