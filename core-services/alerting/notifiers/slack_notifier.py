"""
Slack notifier using incoming webhooks.
Sends formatted messages to Slack channels.
"""

import requests
import json
from typing import Dict
from loguru import logger

from .base import BaseNotifier


class SlackNotifier(BaseNotifier):
    """Send notifications to Slack via incoming webhooks."""

    def __init__(self, config: Dict):
        """
        Initialize Slack notifier.

        Required config:
            - webhook_url: Slack incoming webhook URL
        Optional config:
            - channel: Override default channel (e.g., #alerts)
            - username: Bot username (default: ALPR Alert Bot)
            - icon_emoji: Bot icon emoji (default: :rotating_light:)
        """
        super().__init__(config)
        self.webhook_url = config.get('webhook_url')
        self.channel = config.get('channel')
        self.username = config.get('username', 'ALPR Alert Bot')
        self.icon_emoji = config.get('icon_emoji', ':rotating_light:')

    def send(self, alert_data: Dict) -> bool:
        """
        Send Slack notification.

        Args:
            alert_data: Alert information dict

        Returns:
            True if message sent successfully, False otherwise
        """
        if not self.validate_config():
            logger.error("Slack notifier config invalid, skipping")
            return False

        try:
            payload = self._create_payload(alert_data)

            response = requests.post(
                self.webhook_url,
                json=payload,
                timeout=10
            )

            if response.status_code == 200:
                logger.info(f"Slack notification sent successfully for rule: {alert_data.get('rule_id')}")
                return True
            else:
                logger.error(f"Slack API error: {response.status_code} - {response.text}")
                return False

        except requests.RequestException as e:
            logger.error(f"Failed to send Slack notification: {e}")
            return False
        except Exception as e:
            logger.error(f"Unexpected error sending Slack notification: {e}")
            return False

    def _create_payload(self, alert_data: Dict) -> Dict:
        """
        Create Slack webhook payload with Block Kit formatting.

        Uses Slack's Block Kit for rich formatting:
        https://api.slack.com/block-kit
        """
        priority = alert_data.get('priority', 'medium')
        rule_name = alert_data.get('rule_name', 'ALPR Alert')
        message = alert_data.get('message', '')
        event = alert_data.get('event', {})

        # Priority emoji and color
        priority_config = {
            'high': {'emoji': '🚨', 'color': '#dc3545'},
            'medium': {'emoji': '⚠️', 'color': '#ffc107'},
            'low': {'emoji': 'ℹ️', 'color': '#28a745'}
        }
        config = priority_config.get(priority.lower(), {'emoji': '📢', 'color': '#6c757d'})

        # Base payload
        payload = {
            'username': self.username,
            'icon_emoji': self.icon_emoji
        }

        # Override channel if specified
        if self.channel:
            payload['channel'] = self.channel

        # Build blocks for rich formatting
        blocks = [
            {
                "type": "header",
                "text": {
                    "type": "plain_text",
                    "text": f"{config['emoji']} {rule_name}",
                    "emoji": True
                }
            },
            {
                "type": "section",
                "fields": [
                    {
                        "type": "mrkdwn",
                        "text": f"*Priority:*\n{priority.upper()}"
                    },
                    {
                        "type": "mrkdwn",
                        "text": f"*Rule:*\n{alert_data.get('rule_id', 'unknown')}"
                    }
                ]
            },
            {
                "type": "section",
                "text": {
                    "type": "mrkdwn",
                    "text": f"```\n{message}\n```"
                }
            }
        ]

        # Add plate image button if available
        images = event.get('images', {})
        plate_url = images.get('plate_url', '')
        if plate_url and plate_url.startswith('http'):
            blocks.append({
                "type": "actions",
                "elements": [
                    {
                        "type": "button",
                        "text": {
                            "type": "plain_text",
                            "text": "View Plate Image",
                            "emoji": True
                        },
                        "url": plate_url,
                        "style": "primary"
                    }
                ]
            })

        # Add divider
        blocks.append({"type": "divider"})

        # Add context footer
        plate = event.get('plate', {})
        camera_id = event.get('camera_id', 'unknown')
        captured_at = event.get('captured_at', 'unknown')

        blocks.append({
            "type": "context",
            "elements": [
                {
                    "type": "mrkdwn",
                    "text": f"Camera: `{camera_id}` | Time: `{captured_at}` | Confidence: `{plate.get('confidence', 0):.2%}`"
                }
            ]
        })

        payload['blocks'] = blocks

        # Add color attachment for sidebar indicator
        payload['attachments'] = [{
            'color': config['color']
        }]

        return payload

    def validate_config(self) -> bool:
        """Validate Slack configuration."""
        if not self.enabled:
            return False

        if not self.webhook_url:
            logger.error("Slack notifier missing webhook_url")
            return False

        if not self.webhook_url.startswith('https://hooks.slack.com/'):
            logger.error("Slack webhook_url appears invalid")
            return False

        return True
