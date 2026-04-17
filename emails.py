import smtplib
import time
from email.message import EmailMessage

SMTP_SERVER = "smtp.gmail.com"
SMTP_PORT = 587

EMAIL_ADDRESS = "emailtests4970@gmail.com"
EMAIL_PASSWORD = "jnqy tlyh agqe sueq"

userList = "emails"

def send_email(to_email, subject, body):
    msg = EmailMessage()
    msg["From"] = EMAIL_ADDRESS
    msg["To"] = to_email
    msg["Subject"] = subject
    msg.set_content(body)

    with smtplib.SMTP(SMTP_SERVER, SMTP_PORT) as server:
        server.starttls()
        server.login(EMAIL_ADDRESS, EMAIL_PASSWORD)
        server.send_message(msg)

def sendEmails(userList):
    emails = [e.strip() for e in userList.split(",") if e.strip()]

    for email in emails:
        try:
            send_email(
                email,
                "Test Email",
                "Test message."
            )
            print(f"Sent to {email}")
            time.sleep(2)
        except Exception as e:
            print(f"Failed for {email}: {e}")

if __name__ == "__main__":
    sendEmails(userList)
