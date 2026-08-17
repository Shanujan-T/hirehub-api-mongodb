import logging
import os
import smtplib
from email.message import EmailMessage

logger = logging.getLogger(__name__)


def send_identity_email_otp(email: str, code: str) -> None:
    subject = "Your HireHub account verification code"
    body = (
        f"Your HireHub account verification code is: {code}\n\n"
        "It expires in 10 minutes. If you did not request this, you can ignore this email."
    )

    smtp_host = os.getenv("SMTP_HOST")
    smtp_port = int(os.getenv("SMTP_PORT", "587"))
    smtp_user = os.getenv("SMTP_USER")
    smtp_password = os.getenv("SMTP_PASSWORD")
    mail_from = os.getenv("SMTP_FROM", smtp_user or "noreply@hirehub.local")

    if smtp_host and smtp_user and smtp_password:
        try:
            logger.info("Attempting to send email via SMTP host %s:%s (from=%s)", smtp_host, smtp_port, mail_from)
            msg = EmailMessage()
            msg["Subject"] = subject
            msg["From"] = mail_from
            msg["To"] = email
            msg.set_content(body)
            with smtplib.SMTP(smtp_host, smtp_port) as server:
                server.starttls()
                server.login(smtp_user, smtp_password)
                server.send_message(msg)
            logger.info("Email OTP successfully sent to %s via SMTP", email)
            return
        except Exception as exc:
            logger.exception("SMTP email send failed: %s", exc)

    logger.error("Email OTP was not sent to %s because SMTP is not configured.", email)


def send_identity_sms_otp(phone: str, code: str) -> None:
    message = f"Your HireHub verification code is {code}"

    account_sid = os.getenv("TWILIO_ACCOUNT_SID")
    auth_token = os.getenv("TWILIO_AUTH_TOKEN")
    from_number = os.getenv("TWILIO_FROM_NUMBER")

    if account_sid and auth_token and from_number:
        try:
            from twilio.rest import Client

            logger.info("Sending Twilio SMS to %s using from_=%s (account_sid=%s)", phone, from_number, account_sid)
            client = Client(account_sid, auth_token)
            res = client.messages.create(
                body=message,
                from_=from_number,
                to=phone,
            )
            logger.info("Twilio SMS sent successfully. SID: %s, Status: %s", getattr(res, 'sid', None), getattr(res, 'status', None))
            return
        except Exception as exc:
            logger.exception("Twilio SMS failed with exception: %s", exc)

    logger.error("SMS OTP was not sent to %s because Twilio is not configured.", phone)
