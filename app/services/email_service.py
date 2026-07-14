import logging
import smtplib
from datetime import datetime, timezone
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from sqlalchemy.orm import Session
import requests

from app.core.encryption import decrypt_value
from app.models.email_configuration import EmailConfiguration

logger = logging.getLogger(__name__)


class EmailService:
    @staticmethod
    def _parse_emails(emails: str | list[str] | None) -> list[str]:
        if not emails:
            return []
        if isinstance(emails, str):
            emails_list = [emails]
        else:
            emails_list = list(emails)
        
        parsed = []
        for item in emails_list:
            # Split by comma or semicolon and strip whitespace
            for part in item.replace(";", ",").split(","):
                part_cleaned = part.strip()
                if part_cleaned and part_cleaned not in parsed:
                    parsed.append(part_cleaned)
        return parsed

    @staticmethod
    def send_email_with_active_config(
        db: Session,
        to_email: str | list[str],
        subject: str,
        html_content: str,
        text_content: str = None,
        cc_email: str | list[str] = None,
    ) -> bool:
        """
        Retrieves the active email configuration and sends an email.
        """
        from sqlalchemy import select
        active_config = db.scalar(
            select(EmailConfiguration).where(EmailConfiguration.is_active == True)
        )

        if not active_config:
            logger.warning("No active email configuration found. Email cannot be sent.")
            return False

        try:
            return EmailService._send_email_via_config(
                active_config, to_email, subject, html_content, text_content, cc_email
            )
        except Exception as e:
            logger.error(f"Failed to send email via active config '{active_config.name}': {e}")
            return False

    @staticmethod
    def _send_email_via_config(
        config: EmailConfiguration,
        to_email: str | list[str],
        subject: str,
        html_content: str,
        text_content: str = None,
        cc_email: str | list[str] = None,
    ) -> bool:
        """
        Low-level email sending using the provided EmailConfiguration.
        Raises exception if sending fails.
        """
        if config.provider == "microsoft_graph":
            return EmailService._send_via_graph(
                config, to_email, subject, html_content, text_content, cc_email
            )
        elif config.provider == "smtp":
            return EmailService._send_via_smtp(
                config, to_email, subject, html_content, text_content, cc_email
            )
        else:
            raise ValueError(f"Unsupported email provider: {config.provider}")

    @staticmethod
    def _send_via_graph(
        config: EmailConfiguration,
        to_email: str | list[str],
        subject: str,
        html_content: str,
        text_content: str = None,
        cc_email: str | list[str] = None,
    ) -> bool:
        """
        Sends email using Microsoft Graph API (OAuth2 Client Credentials Flow).
        """
        if not config.tenant_id or not config.client_id or not config.client_secret:
            raise ValueError("Microsoft Graph API credentials (Tenant ID, Client ID, Client Secret) are incomplete.")

        # Parse multiple emails
        actual_to = EmailService._parse_emails(to_email)
        actual_cc = EmailService._parse_emails(cc_email)

        if not actual_to:
            raise ValueError("No recipient email address specified.")

        # 1. Decrypt Client Secret
        decrypted_secret = decrypt_value(config.client_secret)

        # 2. Get Access Token from Microsoft Identity Platform
        token_url = f"https://login.microsoftonline.com/{config.tenant_id}/oauth2/v2.0/token"
        token_data = {
            "grant_type": "client_credentials",
            "client_id": config.client_id,
            "client_secret": decrypted_secret,
            "scope": "https://graph.microsoft.com/.default",
        }

        logger.info(f"Requesting M365 access token from: {token_url}")
        token_res = requests.post(token_url, data=token_data, timeout=10)
        
        if token_res.status_code != 200:
            error_details = token_res.json() if token_res.headers.get("content-type", "").startswith("application/json") else token_res.text
            raise ValueError(f"Microsoft authentication failed (HTTP {token_res.status_code}): {error_details}")

        access_token = token_res.json().get("access_token")
        if not access_token:
            raise ValueError("Access token not found in Microsoft authentication response.")

        # 3. Call Microsoft Graph sendMail endpoint
        # The sender email is used as the User ID in Graph API (users/email/sendMail)
        send_mail_url = f"https://graph.microsoft.com/v1.0/users/{config.sender_email}/sendMail"
        
        headers = {
            "Authorization": f"Bearer {access_token}",
            "Content-Type": "application/json",
        }

        # Build payload
        payload = {
            "message": {
                "subject": subject,
                "body": {
                    "contentType": "HTML",
                    "content": html_content,
                },
                "toRecipients": [
                    {
                        "emailAddress": {
                            "address": email,
                        }
                    }
                    for email in actual_to
                ],
            },
            "saveToSentItems": "true",
        }

        if actual_cc:
            payload["message"]["ccRecipients"] = [
                {
                    "emailAddress": {
                        "address": email,
                    }
                }
                for email in actual_cc
            ]

        logger.info(f"Sending Microsoft Graph email to: {actual_to} via {config.sender_email} (CC: {actual_cc})")
        res = requests.post(send_mail_url, json=payload, headers=headers, timeout=15)
        
        # M365 Graph sendMail returns 202 Accepted on success
        if res.status_code not in (200, 202):
            error_info = res.json() if res.headers.get("content-type", "").startswith("application/json") else res.text
            raise ValueError(f"Microsoft Graph API sendMail failed (HTTP {res.status_code}): {error_info}")

        logger.info("Microsoft Graph email sent successfully!")
        return True

    @staticmethod
    def _send_via_smtp(
        config: EmailConfiguration,
        to_email: str | list[str],
        subject: str,
        html_content: str,
        text_content: str = None,
        cc_email: str | list[str] = None,
    ) -> bool:
        """
        Sends email using standard SMTP.
        """
        if not config.smtp_host or not config.smtp_port:
            raise ValueError("SMTP host or port is not configured.")

        # Parse multiple emails
        actual_to = EmailService._parse_emails(to_email)
        actual_cc = EmailService._parse_emails(cc_email)

        if not actual_to:
            raise ValueError("No recipient email address specified.")

        # 1. Build MIME Message
        msg = MIMEMultipart("alternative")
        msg["Subject"] = subject
        msg["From"] = config.sender_email
        msg["To"] = ", ".join(actual_to)
        if actual_cc:
            msg["Cc"] = ", ".join(actual_cc)

        if text_content:
            msg.attach(MIMEText(text_content, "plain", "utf-8"))
        msg.attach(MIMEText(html_content, "html", "utf-8"))

        # 2. Decrypt Password
        decrypted_password = decrypt_value(config.smtp_password)

        # 3. Connect and send
        logger.info(f"Connecting to SMTP server {config.smtp_host}:{config.smtp_port}")
        
        server = None
        try:
            if config.smtp_port == 465:
                # SSL port
                server = smtplib.SMTP_SSL(config.smtp_host, config.smtp_port, timeout=15)
            else:
                # Typically STARTTLS port (e.g. 587 or 25)
                server = smtplib.SMTP(config.smtp_host, config.smtp_port, timeout=15)
                if config.smtp_use_tls:
                    server.starttls()
            
            if config.smtp_username and decrypted_password:
                logger.info(f"Authenticating SMTP user: {config.smtp_username}")
                server.login(config.smtp_username, decrypted_password)
                
            logger.info(f"Sending SMTP email to: {actual_to} (CC: {actual_cc})")
            server.send_message(msg)
            logger.info("SMTP email sent successfully!")
            return True
        finally:
            if server:
                try:
                    server.quit()
                except Exception:
                    pass

    @staticmethod
    def test_connection(
        db: Session,
        config: EmailConfiguration,
        test_recipient: str,
    ) -> tuple[bool, str | None]:
        """
        Sends a test email using the provided configuration.
        Updates configuration fields (connection_status, error_message, last_tested_at).
        If the configuration has an ID and is in the database, it commits the changes.
        """
        now = datetime.now(timezone.utc)
        config.last_tested_at = now

        subject = "Microsoft 365 Email Connection Test"
        html_content = f"""
        <html>
            <body style="font-family: Arial, sans-serif; color: #333333; line-height: 1.6;">
                <div style="max-width: 600px; margin: 0 auto; padding: 20px; border: 1px solid #e0e0e0; border-radius: 8px; background-color: #ffffff;">
                    <h2 style="color: #206bc4; margin-top: 0;">Connection Test Successful!</h2>
                    <p>Hello,</p>
                    <p>This is a test email sent from the <strong>Cognitive ERP Settings</strong> page.</p>
                    <p>Your connection configuration for <strong>{config.name}</strong> ({config.provider}) is fully verified and working properly.</p>
                    <hr style="border: 0; border-top: 1px solid #eeeeee; margin: 20px 0;" />
                    <p style="font-size: 0.85em; color: #777777; margin-bottom: 0;">
                        Timestamp: {now.strftime("%Y-%m-%d %H:%M:%S UTC")}<br />
                        Mailbox: {config.sender_email}<br />
                        Integration Method: {config.provider.replace('_', ' ').title()}
                    </p>
                </div>
            </body>
        </html>
        """
        
        try:
            EmailService._send_email_via_config(config, test_recipient, subject, html_content)
            config.connection_status = "connected"
            config.error_message = None
            
            # If the object is bound to session and persisted, commit changes
            if config.id and db.object_session(config):
                db.commit()
            return True, None
        except Exception as e:
            error_str = str(e)
            logger.error(f"Email connection test failed: {error_str}")
            config.connection_status = "failed"
            config.error_message = error_str[:1000]  # Cap length for safety
            
            if config.id and db.object_session(config):
                db.commit()
            return False, error_str
