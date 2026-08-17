import os
import logging
import requests

logger = logging.getLogger(__name__)


def send_transactional_email(to_emails, subject: str, html_content: str) -> None:
    """Send one Brevo transactional email to one or more recipients."""
    api_key = os.getenv("BREVO_API_KEY", "").strip()
    sender = os.getenv("BREVO_FROM_EMAIL", "").strip()
    if not api_key or not sender:
        raise ValueError("Brevo email is not configured in the environment.")
    if isinstance(to_emails, str):
        to_emails = [to_emails]
    payload = {
        "sender": {"email": sender, "name": os.getenv("BREVO_FROM_NAME", "HireHub").strip() or "HireHub"},
        "to": [{"email": email} for email in to_emails],
        "subject": subject,
        "htmlContent": html_content,
    }
    response = requests.post(
        "https://api.brevo.com/v3/smtp/email",
        headers={"accept": "application/json", "api-key": api_key, "content-type": "application/json"},
        json=payload,
        timeout=15,
    )
    try:
        response.raise_for_status()
    except requests.HTTPError as exc:
        raise RuntimeError(f"Brevo email send failed: {response.text}") from exc


def send_otp_email(to_email: str, code: str) -> None:
    api_key = os.getenv("BREVO_API_KEY", "").strip()
    if not api_key:
        raise ValueError("BREVO_API_KEY is not configured in the environment.")

    sender = os.getenv("BREVO_FROM_EMAIL", "").strip()
    if not sender:
        raise ValueError("BREVO_FROM_EMAIL is not configured in the environment.")

    sender_name = os.getenv("BREVO_FROM_NAME", "HireHub").strip() or "HireHub"

    subject = "Your HireHub account verification code"
    html_content = (
        f"Your HireHub account verification code is: <strong>{code}</strong><br><br>"
        "It expires in 10 minutes. If you did not request this, you can ignore this email."
    )

    payload = {
        "sender": {"email": sender, "name": sender_name},
        "to": [{"email": to_email}],
        "subject": subject,
        "htmlContent": html_content,
    }

    logger.info("Attempting to send Brevo email to %s (from=%s)", to_email, sender)
    response = requests.post(
        "https://api.brevo.com/v3/smtp/email",
        headers={"accept": "application/json", "api-key": api_key, "content-type": "application/json"},
        json=payload,
        timeout=15,
    )
    try:
        response.raise_for_status()
    except requests.HTTPError as exc:
        raise RuntimeError(f"Brevo email send failed: {response.text}") from exc

    message_id = response.json().get("messageId")
    logger.info("Brevo email sent successfully. ID: %s", message_id)
