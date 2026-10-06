import logging, smtplib, ssl
from email.message import EmailMessage
from .config import settings

def mail_configured() -> bool:
    return bool(settings.smtp_host and settings.smtp_user and settings.smtp_password)

def demo_allowed() -> bool:
    """True only on a local test setup: flag on, no HTTPS cookies (not hosted) and no mail account configured."""
    return settings.demo_show_code and not settings.cookie_secure and not mail_configured()

def send_mail(to: str, subject: str, body: str) -> tuple[bool, str | None]:
    """Send via SMTP (e.g. Gmail with an App Password). Returns (ok, reason-if-failed). Never logs the password."""
    if not mail_configured():
        return False, "E-mail is not set up: SMTP_USER or SMTP_PASSWORD is empty in the .env file"
    try:
        msg = EmailMessage()
        msg["From"], msg["To"], msg["Subject"] = settings.smtp_from or settings.smtp_user, to, subject
        msg.set_content(body)
        pw = settings.smtp_password.replace(" ", "")
        ctx = ssl.create_default_context()
        if settings.smtp_port == 465:
            with smtplib.SMTP_SSL(settings.smtp_host, 465, timeout=20, context=ctx) as s:
                s.login(settings.smtp_user, pw); s.send_message(msg)
        else:
            with smtplib.SMTP(settings.smtp_host, settings.smtp_port, timeout=20) as s:
                s.ehlo(); s.starttls(context=ctx); s.ehlo(); s.login(settings.smtp_user, pw); s.send_message(msg)
        return True, None
    except smtplib.SMTPAuthenticationError:
        return False, "The mail server rejected the login. For Gmail use a 16-character App Password (2-Step Verification must be on), not your normal password"
    except smtplib.SMTPRecipientsRefused:
        return False, "The mail server refused the recipient address"
    except (smtplib.SMTPConnectError, ConnectionError, TimeoutError, OSError):
        logging.exception("Could not reach the mail server")
        return False, "Could not reach the mail server. Check the internet connection, SMTP_HOST and SMTP_PORT (587, or 465)"
    except Exception as e:
        logging.exception("Could not send e-mail")
        return False, f"Sending failed ({type(e).__name__})"
