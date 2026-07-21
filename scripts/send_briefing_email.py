#!/usr/bin/env python3
"""Send the completed accounting briefing HTML as an email attachment via Gmail SMTP.

Usage: send_briefing_email.py <html_file_path> <YYYY-MM-DD>

Requires two environment variables:
- BRIEFING_GMAIL_ADDRESS: the Gmail address to send from
- BRIEFING_GMAIL_APP_PASSWORD: a Gmail App Password for that address
"""
import os
import smtplib
import sys
from email.mime.application import MIMEApplication
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText

RECIPIENTS = ["ssh7010@aju.co.kr", "010051@aju.co.kr"]


def main():
    if len(sys.argv) != 3:
        print("Usage: send_briefing_email.py <html_file_path> <YYYY-MM-DD>", file=sys.stderr)
        sys.exit(1)

    html_path, report_date = sys.argv[1], sys.argv[2]

    gmail_address = os.environ["BRIEFING_GMAIL_ADDRESS"]
    app_password = os.environ["BRIEFING_GMAIL_APP_PASSWORD"]

    with open(html_path, "rb") as f:
        html_bytes = f.read()

    msg = MIMEMultipart()
    msg["From"] = gmail_address
    msg["To"] = ", ".join(RECIPIENTS)
    msg["Subject"] = f"{report_date} 회계팀 오전 브리핑 송부 드립니다."

    body = (
        "※ 이 메일은 AI가 작성부터 첨부파일 생성, 파일 첨부, 발송까지 전 과정을 자동으로 수행했습니다.\n\n"
        "안녕하십니까\n"
        "회계팀입니다.\n\n"
        f"{report_date} 회계팀 오전 브리핑 송부 드립니다.\n\n"
        "확인 부탁드립니다.\n\n"
        "감사합니다."
    )
    msg.attach(MIMEText(body, "plain"))

    attachment = MIMEApplication(html_bytes, _subtype="html")
    attachment.add_header(
        "Content-Disposition", "attachment", filename=f"{report_date}_accounting_briefing.html"
    )
    msg.attach(attachment)

    with smtplib.SMTP("smtp.gmail.com", 587) as server:
        server.starttls()
        server.login(gmail_address, app_password)
        server.sendmail(gmail_address, RECIPIENTS, msg.as_string())

    print("Sent briefing email to:", ", ".join(RECIPIENTS))


if __name__ == "__main__":
    main()
