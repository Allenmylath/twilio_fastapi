import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart

# SMTP Configuration
smtp_server = "smtp.gmail.com"
smtp_port = 587
sender_email = "allengeorgemylath@gmail.com"
sender_password = "dhnx dzgi cdzs yeea"

# List of recipient emails
recipient_emails = [
    "johananddijo@gmail.com",
    "Mark.Pattison@careadhd.co.uk",
]


def email_init(recipient, subject, body):
    try:
        # Create message
        message = MIMEMultipart()
        message["From"] = sender_email
        message["To"] = recipient
        message["Subject"] = subject

        # Add body to email
        message.attach(MIMEText(body, "plain"))

        # Create SMTP session
        with smtplib.SMTP(smtp_server, smtp_port) as server:
            server.starttls()  # Enable TLS
            server.login(sender_email, sender_password)

            # Send email
            server.send_message(message)
            print(f"Successfully sent email to {recipient}")

    except Exception as e:
        print(f"Failed to send email to {recipient}. Error: {str(e)}")


def send_email(subject, body):
    print("Starting bulk email sending...")

    for recipient in recipient_emails:
        email_init(recipient, subject, body)

    print("Bulk email sending completed!")


'''
# Example usage
if __name__ == "__main__":
    email_subject = "Test Email"
    email_body = """
    Hello,
    
    This is a test email sent using Python.
    
    Best regards,
    Your Name
    """
    
    send_bulk_emails(email_subject, email_body)
'''
