#!/usr/bin/env python3
"""Send the completed accounting briefing HTML as an email attachment via Gmail API.

Usage: send_briefing_email.py <html_file_path> <YYYY-MM-DD>

Requires environment variables:
- GOOGLE_APPLICATION_CREDENTIALS: path to service account JSON file
  OR
- BRIEFING_GMAIL_REFRESH_TOKEN: OAuth2 refresh token
- BRIEFING_GMAIL_CLIENT_ID: OAuth2 client ID
- BRIEFING_GMAIL_CLIENT_SECRET: OAuth2 client secret
"""
import os
import sys
import base64
import json
from email.mime.application import MIMEApplication
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText

try:
    from google.auth.transport.requests import Request
    from google.oauth2.service_account import Credentials
    from google.oauth2.credentials import Credentials as OAuth2Credentials
    import googleapiclient.discovery
except ImportError:
    print("Error: google-auth and google-api-python-client required", file=sys.stderr)
    print("Install with: pip install google-auth google-auth-oauthlib google-api-python-client", file=sys.stderr)
    sys.exit(1)

RECIPIENTS = ["ssh7010@aju.co.kr", "010051@aju.co.kr"]


def get_gmail_service():
    """Create Gmail API service using available credentials."""
    credentials = None

    # Try service account first
    if "GOOGLE_APPLICATION_CREDENTIALS" in os.environ:
        cred_path = os.environ["GOOGLE_APPLICATION_CREDENTIALS"]
        credentials = Credentials.from_service_account_file(
            cred_path,
            scopes=["https://www.googleapis.com/auth/gmail.send"]
        )
    # Try OAuth2 refresh token
    elif all(k in os.environ for k in ["BRIEFING_GMAIL_REFRESH_TOKEN", "BRIEFING_GMAIL_CLIENT_ID", "BRIEFING_GMAIL_CLIENT_SECRET"]):
        creds_info = {
            "client_id": os.environ["BRIEFING_GMAIL_CLIENT_ID"],
            "client_secret": os.environ["BRIEFING_GMAIL_CLIENT_SECRET"],
            "refresh_token": os.environ["BRIEFING_GMAIL_REFRESH_TOKEN"],
            "type": "authorized_user"
        }
        credentials = OAuth2Credentials.from_authorized_user_info(creds_info)
        if credentials.expired:
            credentials.refresh(Request())
    else:
        raise ValueError(
            "No credentials found. Set either GOOGLE_APPLICATION_CREDENTIALS "
            "or BRIEFING_GMAIL_REFRESH_TOKEN with CLIENT_ID and CLIENT_SECRET"
        )

    return googleapiclient.discovery.build("gmail", "v1", credentials=credentials)


def create_message(sender, to, subject, body, html_path):
    """Create a MIME message with HTML attachment."""
    msg = MIMEMultipart()
    msg["From"] = sender
    msg["To"] = ", ".join(to)
    msg["Subject"] = subject

    msg.attach(MIMEText(body, "plain"))

    with open(html_path, "rb") as f:
        html_bytes = f.read()

    attachment = MIMEApplication(html_bytes, _subtype="html")
    attachment.add_header(
        "Content-Disposition", "attachment",
        filename=os.path.basename(html_path)
    )
    msg.attach(attachment)

    return base64.urlsafe_b64encode(msg.as_bytes()).decode()


def main():
    if len(sys.argv) != 3:
        print("Usage: send_briefing_email.py <html_file_path> <YYYY-MM-DD>", file=sys.stderr)
        sys.exit(1)

    html_path, report_date = sys.argv[1], sys.argv[2]

    if not os.path.exists(html_path):
        print(f"Error: File not found: {html_path}", file=sys.stderr)
        sys.exit(1)

    try:
        gmail_service = get_gmail_service()

        sender = os.environ.get("BRIEFING_GMAIL_ADDRESS", "me")

        subject = f"{report_date} 회계팀 오전 브리핑 송부 드립니다."
        body = (
            "※ 이 메일은 AI가 작성부터 첨부파일 생성, 파일 첨부, 발송까지 전 과정을 자동으로 수행했습니다.\n\n"
            "안녕하십니까\n"
            "회계팀입니다.\n\n"
            f"{report_date} 회계팀 오전 브리핑 송부 드립니다.\n\n"
            "확인 부탁드립니다.\n\n"
            "감사합니다."
        )

        message = create_message(sender, RECIPIENTS, subject, body, html_path)

        send_message = {"raw": message}
        gmail_service.users().messages().send(userId="me", body=send_message).execute()

        print("Sent briefing email to:", ", ".join(RECIPIENTS))

    except Exception as e:
        print(f"Error sending email: {e}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
