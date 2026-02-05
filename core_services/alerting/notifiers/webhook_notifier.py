"""
Generic webhook notifier for custom integrations.
Sends HTTP POST/PUT requests with configurable headers and authentication.
"""

import requests
import json
from typing import Dict
from loguru import logger

from .base import BaseNotifier


class WebhookNotifier(BaseNotifier):
    """Send notifications to custom webhooks."""

    def __init__(self, config: Dict):
        """
        Initialize webhook notifier.

        Required config:
            - url: Webhook URL
        Optional config:
            - method: HTTP method (POST or PUT, default: POST)
            - headers: Dict of HTTP headers
            - timeout: Request timeout in seconds (default: 10)
        """
        super().__init__(config)
        self.url = config.get('url')
        self.method = config.get('method', 'POST').upper()
        self.headers = config.get('headers', {})
        self.timeout = config.get('timeout', 10)

        # Ensure Content-Type is set
        if 'Content-Type' not in self.headers:
            self.headers['Content-Type'] = 'application/json'

    def send(self, alert_data: Dict) -> bool:
        """
        Send webhook notification.

        Args:
            alert_data: Alert information dict

        Returns:
            True if webhook called successfully, False otherwise
        """
        if not self.validate_config():
            logger.error("Webhook notifier config invalid, skipping")
            return False

        try:
            payload = self._create_payload(alert_data)

            # Send request
            if self.method == 'POST':
                response = requests.post(
                    self.url,
                    json=payload,
                    headers=self.headers,
                    timeout=self.timeout
                )
            elif self.method == 'PUT':
                response = requests.put(
                    self.url,
                    json=payload,
                    headers=self.headers,
                    timeout=self.timeout
                )
            else:
                logger.error(f"Unsupported HTTP method: {self.method}")
                return False

            # Check response
            if 200 <= response.status_code < 300:
                logger.info(f"Webhook notification sent successfully for rule: {alert_data.get('rule_id')}")
                return True
            else:
                logger.error(f"Webhook returned error: {response.status_code} - {response.text}")
                return False

        except requests.RequestException as e:
            logger.error(f"Failed to send webhook notification: {e}")
            return False
        except Exception as e:
            logger.error(f"Unexpected error sending webhook notification: {e}")
            return False

    def _create_payload(self, alert_data: Dict) -> Dict:
        """
        Create webhook payload.

        Sends comprehensive event data in a structured format.
        """
        event = alert_data.get('event', {})

        payload = {
            'alert': {
                'rule_id': alert_data.get('rule_id'),
                'rule_name': alert_data.get('rule_name'),
                'priority': alert_data.get('priority'),
                'message': alert_data.get('message'),
                'timestamp': event.get('captured_at')
            },
            'event': {
                'event_id': event.get('event_id'),
                'camera_id': event.get('camera_id'),
                'track_id': event.get('track_id'),
                'captured_at': event.get('captured_at'),
                'plate': event.get('plate', {}),
                'vehicle': event.get('vehicle', {}),
                'images': event.get('images', {}),
                'latency_ms': event.get('latency_ms', 0),
                'node': event.get('node', {})
            }
        }

        return payload

    def validate_config(self) -> bool:
        """Validate webhook configuration."""
        if not self.enabled:
            return False

        if not self.url:
            logger.error("Webhook notifier missing url")
            return False

        if not self.url.startswith(('http://', 'https://')):
            logger.error("Webhook URL must start with http:// or https://")
            return False

        if self.method not in ['POST', 'PUT']:
            logger.error(f"Unsupported HTTP method: {self.method} (use POST or PUT)")
            return False

        return True
