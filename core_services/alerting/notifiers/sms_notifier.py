"""
SMS notifier using Twilio API.
Sends text message alerts for critical events.
"""

from typing import Dict
from loguru import logger

from .base import BaseNotifier

# Optional Twilio import (may not be installed in all environments)
try:
    from twilio.rest import Client as TwilioClient
    from twilio.base.exceptions import TwilioRestException
    TWILIO_AVAILABLE = True
except ImportError:
    TWILIO_AVAILABLE = False
    logger.warning("Twilio library not installed. SMS notifications will be disabled.")


class SMSNotifier(BaseNotifier):
    """Send SMS notifications via Twilio."""

    def __init__(self, config: Dict):
        """
        Initialize SMS notifier.

        Required config:
            - twilio_account_sid: Twilio account SID
            - twilio_auth_token: Twilio auth token
            - from_number: Twilio phone number (E.164 format: +15551234567)
            - to_numbers: List of recipient phone numbers (E.164 format)
        """
        super().__init__(config)
        self.account_sid = config.get('twilio_account_sid')
        self.auth_token = config.get('twilio_auth_token')
        self.from_number = config.get('from_number')
        self.to_numbers = config.get('to_numbers', [])

        # Initialize Twilio client if available
        self.client = None
        if TWILIO_AVAILABLE and self.account_sid and self.auth_token:
            try:
                self.client = TwilioClient(self.account_sid, self.auth_token)
            except Exception as e:
                logger.error(f"Failed to initialize Twilio client: {e}")

    def send(self, alert_data: Dict) -> bool:
        """
        Send SMS notification.

        Args:
            alert_data: Alert information dict

        Returns:
            True if SMS sent successfully to all recipients, False otherwise
        """
        if not TWILIO_AVAILABLE:
            logger.error("Twilio library not available, cannot send SMS")
            return False

        if not self.validate_config():
            logger.error("SMS notifier config invalid, skipping")
            return False

        try:
            message_body = self._create_message(alert_data)

            # Send to all recipients
            success_count = 0
            for to_number in self.to_numbers:
                try:
                    message = self.client.messages.create(
                        body=message_body,
                        from_=self.from_number,
                        to=to_number
                    )
                    logger.info(f"SMS sent successfully to {to_number} (SID: {message.sid})")
                    success_count += 1

                except TwilioRestException as e:
                    logger.error(f"Twilio API error sending to {to_number}: {e}")
                except Exception as e:
                    logger.error(f"Failed to send SMS to {to_number}: {e}")

            # Return True if at least one message sent successfully
            if success_count > 0:
                logger.info(f"SMS notifications sent to {success_count}/{len(self.to_numbers)} recipients for rule: {alert_data.get('rule_id')}")
                return True
            else:
                logger.error("Failed to send SMS to any recipients")
                return False

        except Exception as e:
            logger.error(f"Unexpected error sending SMS notification: {e}")
            return False

    def _create_message(self, alert_data: Dict) -> str:
        """
        Create concise SMS message.

        SMS messages are limited to 160 chars for single segment,
        so we keep it brief and focused.
        """
        event = alert_data.get('event', {})
        plate = event.get('plate', {})
        rule_name = alert_data.get('rule_name', 'ALPR Alert')
        priority = alert_data.get('priority', 'medium').upper()

        plate_text = plate.get('normalized_text', 'UNKNOWN')
        camera_id = event.get('camera_id', 'unknown')
        confidence = plate.get('confidence', 0)

        # Format: [PRIORITY] Rule: Plate (Camera) Conf: XX%
        message = f"[{priority}] {rule_name}\n"
        message += f"Plate: {plate_text}\n"
        message += f"Camera: {camera_id}\n"
        message += f"Confidence: {confidence:.0%}"

        # Truncate if too long (keep under 160 chars for single segment)
        if len(message) > 160:
            message = message[:157] + "..."

        return message

    def validate_config(self) -> bool:
        """Validate SMS configuration."""
        if not self.enabled:
            return False

        if not TWILIO_AVAILABLE:
            logger.error("Twilio library not installed")
            return False

        if not self.client:
            logger.error("Twilio client not initialized")
            return False

        if not self.account_sid or not self.auth_token:
            logger.error("SMS notifier missing Twilio credentials")
            return False

        if not self.from_number:
            logger.error("SMS notifier missing from_number")
            return False

        if not self.to_numbers:
            logger.error("SMS notifier has no recipients configured")
            return False

        # Validate phone number format (basic check)
        if not self.from_number.startswith('+'):
            logger.error("from_number must be in E.164 format (e.g., +15551234567)")
            return False

        for number in self.to_numbers:
            if not number.startswith('+'):
                logger.error(f"Recipient number {number} must be in E.164 format")
                return False

        return True
