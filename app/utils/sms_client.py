import os
import logging
from twilio.rest import Client

logger = logging.getLogger(__name__)


def is_twilio_configured() -> bool:
    return bool(
        os.getenv("TWILIO_ACCOUNT_SID")
        and os.getenv("TWILIO_AUTH_TOKEN")
        and os.getenv("TWILIO_VERIFY_SERVICE_SID")
    )


def _get_twilio_client_and_service():
    account_sid = os.getenv("TWILIO_ACCOUNT_SID")
    auth_token = os.getenv("TWILIO_AUTH_TOKEN")
    service_sid = os.getenv("TWILIO_VERIFY_SERVICE_SID")
    if not (account_sid and auth_token and service_sid):
        raise ValueError("Twilio credentials/service SID not fully configured in environment.")
    client = Client(account_sid, auth_token)
    return client, service_sid


def send_verification_code(phone_number: str) -> None:
    client, service_sid = _get_twilio_client_and_service()
    logger.info("Calling Twilio Verify to send code to %s", phone_number)
    client.verify.v2.services(service_sid).verifications.create(to=phone_number, channel="sms")


def check_verification_code(phone_number: str, code: str) -> bool:
    client, service_sid = _get_twilio_client_and_service()
    logger.info("Calling Twilio Verify to check code for %s", phone_number)
    verification_check = client.verify.v2.services(service_sid).verification_checks.create(to=phone_number, code=code)
    return verification_check.status == "approved"
