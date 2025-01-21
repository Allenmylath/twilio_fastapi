import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from dotenv import load_dotenv
import os

# Load environment variables
load_dotenv()

def send_email(recipient_email, subject, message_text):
    """
    Send an email using SMTP with credentials from environment variables.
    
    Args:
        recipient_email (str): Email address of the recipient
        subject (str): Subject line of the email
        message_text (str): Body text of the email
    
    Returns:
        bool: True if email was sent successfully, False otherwise
    """
    # Get credentials from environment variables
    smtp_server = os.getenv("SMTP_SERVER", "smtp.gmail.com")
    smtp_port = int(os.getenv("SMTP_PORT", "587"))
    sender_email = os.getenv("SENDER_EMAIL")
    sender_password = os.getenv("SENDER_PASSWORD")

    # Verify required environment variables are set
    if not all([sender_email, sender_password]):
        raise ValueError("Missing required environment variables. Please check your .env file.")

    try:
        # Create the email message
        message = MIMEMultipart()
        message["From"] = sender_email
        message["To"] = recipient_email
        message["Subject"] = subject

        # Add body to email
        message.attach(MIMEText(message_text, "plain"))

        # Create SMTP session
        with smtplib.SMTP(smtp_server, smtp_port) as server:
            server.starttls()  # Enable TLS
            server.login(sender_email, sender_password)
            
            # Send email
            server.send_message(message)
            
        return True

    except Exception as e:
        print(f"Error sending email: {str(e)}")
        return False

# Example usage:
if __name__ == "__main__":
    # Test the function
    recipient = "recipient@example.com"
    subject = "Test Email"
    message = "This is a test email sent from Python."
    
    success = send_email(
        recipient_email=recipient,
        subject=subject,
        message_text=message
    )
    
    if success:
        print("Email sent successfully!")
    else:
        print("Failed to send email.")
