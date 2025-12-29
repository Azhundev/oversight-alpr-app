"""
Email notifier using SMTP.
Supports Gmail, Office365, and other SMTP servers with TLS.
"""

import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from typing import Dict
from loguru import logger

from .base import BaseNotifier


class EmailNotifier(BaseNotifier):
    """Send email notifications via SMTP."""

    def __init__(self, config: Dict):
        """
        Initialize email notifier.

        Required config:
            - smtp_host: SMTP server hostname
            - smtp_port: SMTP server port
            - username: SMTP username
            - password: SMTP password
            - from_address: Sender email address
            - recipients: List of recipient email addresses
        Optional config:
            - use_tls: Use TLS encryption (default: True)
        """
        super().__init__(config)
        self.smtp_host = config.get('smtp_host')
        self.smtp_port = config.get('smtp_port', 587)
        self.use_tls = config.get('use_tls', True)
        self.username = config.get('username')
        self.password = config.get('password')
        self.from_address = config.get('from_address')
        self.recipients = config.get('recipients', [])

    def send(self, alert_data: Dict) -> bool:
        """
        Send email notification.

        Args:
            alert_data: Alert information dict

        Returns:
            True if email sent successfully, False otherwise
        """
        if not self.validate_config():
            logger.error("Email notifier config invalid, skipping")
            return False

        try:
            # Create message
            msg = MIMEMultipart('alternative')
            msg['From'] = self.from_address
            msg['To'] = ', '.join(self.recipients)
            msg['Subject'] = self._create_subject(alert_data)

            # Create plain text and HTML versions
            text_body = alert_data.get('message', '')
            html_body = self._create_html_body(alert_data)

            msg.attach(MIMEText(text_body, 'plain'))
            msg.attach(MIMEText(html_body, 'html'))

            # Send via SMTP
            if self.use_tls:
                with smtplib.SMTP(self.smtp_host, self.smtp_port, timeout=10) as server:
                    server.starttls()
                    server.login(self.username, self.password)
                    server.send_message(msg)
            else:
                with smtplib.SMTP_SSL(self.smtp_host, self.smtp_port, timeout=10) as server:
                    server.login(self.username, self.password)
                    server.send_message(msg)

            logger.info(f"Email sent successfully to {len(self.recipients)} recipients for rule: {alert_data.get('rule_id')}")
            return True

        except smtplib.SMTPAuthenticationError as e:
            logger.error(f"SMTP authentication failed: {e}")
            return False
        except smtplib.SMTPException as e:
            logger.error(f"SMTP error sending email: {e}")
            return False
        except Exception as e:
            logger.error(f"Unexpected error sending email: {e}")
            return False

    def _create_subject(self, alert_data: Dict) -> str:
        """Create email subject line."""
        priority = alert_data.get('priority', 'medium').upper()
        rule_name = alert_data.get('rule_name', 'ALPR Alert')

        # Extract plate text if available
        event = alert_data.get('event', {})
        plate = event.get('plate', {})
        plate_text = plate.get('normalized_text', '')

        if plate_text:
            return f"[{priority}] {rule_name}: {plate_text}"
        else:
            return f"[{priority}] {rule_name}"

    def _create_html_body(self, alert_data: Dict) -> str:
        """Create HTML email body with formatting."""
        priority = alert_data.get('priority', 'medium')
        rule_name = alert_data.get('rule_name', 'ALPR Alert')
        message = alert_data.get('message', '')
        event = alert_data.get('event', {})

        # Priority color coding
        priority_colors = {
            'high': '#dc3545',    # Red
            'medium': '#ffc107',  # Yellow
            'low': '#28a745'      # Green
        }
        color = priority_colors.get(priority.lower(), '#6c757d')

        # Build HTML
        html = f"""
        <!DOCTYPE html>
        <html>
        <head>
            <style>
                body {{
                    font-family: Arial, sans-serif;
                    line-height: 1.6;
                    color: #333;
                }}
                .header {{
                    background-color: {color};
                    color: white;
                    padding: 15px;
                    border-radius: 5px 5px 0 0;
                }}
                .content {{
                    padding: 20px;
                    border: 1px solid #ddd;
                    border-radius: 0 0 5px 5px;
                }}
                .message {{
                    white-space: pre-wrap;
                    background-color: #f8f9fa;
                    padding: 15px;
                    border-left: 4px solid {color};
                    margin: 15px 0;
                }}
                .footer {{
                    margin-top: 20px;
                    padding-top: 10px;
                    border-top: 1px solid #ddd;
                    font-size: 12px;
                    color: #6c757d;
                }}
                a {{
                    color: #007bff;
                    text-decoration: none;
                }}
            </style>
        </head>
        <body>
            <div class="header">
                <h2>{rule_name}</h2>
                <p>Priority: {priority.upper()}</p>
            </div>
            <div class="content">
                <div class="message">{message}</div>
        """

        # Add image link if available
        images = event.get('images', {})
        plate_url = images.get('plate_url', '')
        if plate_url and plate_url.startswith('http'):
            html += f'<p><a href="{plate_url}">View Plate Image</a></p>'

        html += f"""
                <div class="footer">
                    <p>Alert generated by ALPR System</p>
                    <p>Rule ID: {alert_data.get('rule_id', 'unknown')}</p>
                </div>
            </div>
        </body>
        </html>
        """

        return html

    def validate_config(self) -> bool:
        """Validate email configuration."""
        if not self.enabled:
            return False

        required = ['smtp_host', 'smtp_port', 'username', 'password', 'from_address']
        for field in required:
            if not getattr(self, field, None):
                logger.error(f"Email notifier missing required config: {field}")
                return False

        if not self.recipients:
            logger.error("Email notifier has no recipients configured")
            return False

        return True
