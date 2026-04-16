import smtplib
import csv
import time
from email.message import EmailMessage

# gmail smtp settings
SMTP_SERVER = "smtp.gmail.com"
SMTP_PORT = 587

# testing email + app password
EMAIL_ADDRESS = "emailtests4970@gmail.com"
EMAIL_PASSWORD = "jnqy tlyh agqe sueq"

def send_email(to_email, subject, body):
    # building the email
    msg = EmailMessage()
    msg["From"] = EMAIL_ADDRESS
    msg["To"] = to_email
    msg["Subject"] = subject
    msg.set_content(body)

    # connecting to gmail + sending
    with smtplib.SMTP(SMTP_SERVER, SMTP_PORT) as server:
        server.starttls()
        server.login(EMAIL_ADDRESS, EMAIL_PASSWORD)
        server.send_message(msg)

def send_from_csv(csv_file):
    # opening csv and looping through emails
    with open(csv_file, newline='') as file:
        reader = csv.DictReader(file)
        for row in reader:
            email = row["email"]
            try:
                send_email(
                    email,
                    "Test Email",
                    "Test message."
                )
                print(f"Sent to {email}")
                time.sleep(2)  # adds a delay to hopefully prevent a spam flag
            except Exception as e:
                print(f"Failed for {email}: {e}")

if __name__ == "__main__":
    send_from_csv("emails.csv")