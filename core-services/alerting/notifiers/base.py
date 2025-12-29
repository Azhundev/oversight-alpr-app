"""
Base notifier abstract class for all notification channels.
"""

from abc import ABC, abstractmethod
from typing import Dict, Optional
from loguru import logger


class BaseNotifier(ABC):
    """Abstract base class for notification channels."""

    def __init__(self, config: Dict):
        """
        Initialize notifier with configuration.

        Args:
            config: Channel-specific configuration dict
        """
        self.config = config
        self.enabled = config.get('enabled', False)

    @abstractmethod
    def send(self, alert_data: Dict) -> bool:
        """
        Send notification.

        Args:
            alert_data: Dict containing:
                - rule_id: Rule identifier
                - rule_name: Human-readable rule name
                - priority: Alert priority (high, medium, low)
                - message: Formatted alert message
                - event: Full PlateEvent data

        Returns:
            True if notification sent successfully, False otherwise
        """
        pass

    def format_message(self, template: str, event: Dict) -> str:
        """
        Format message template with event data.

        Supports nested field access with dot notation and safe formatting.
        Example: {plate.normalized_text} -> event['plate']['normalized_text']

        Args:
            template: Message template with {field.path} placeholders
            event: Event data dict

        Returns:
            Formatted message string
        """
        try:
            # Create a safe dict for formatting
            format_dict = self._flatten_event_for_formatting(event)
            return template.format(**format_dict)
        except (KeyError, ValueError) as e:
            logger.warning(f"Failed to format message template: {e}")
            # Return template with available fields filled
            try:
                return template.format_map(SafeDict(format_dict))
            except Exception:
                return template

    def _flatten_event_for_formatting(self, event: Dict, prefix: str = '') -> Dict:
        """
        Flatten nested event dict for string formatting.

        Converts {'plate': {'text': 'ABC123'}} to {'plate.text': 'ABC123'}

        Args:
            event: Event data dict
            prefix: Current key prefix (for recursion)

        Returns:
            Flattened dict with dot-notation keys
        """
        flat = {}

        for key, value in event.items():
            full_key = f"{prefix}.{key}" if prefix else key

            if isinstance(value, dict):
                # Recursively flatten nested dicts
                flat.update(self._flatten_event_for_formatting(value, full_key))
            elif value is not None:
                # Add non-None values
                flat[full_key] = value
            else:
                # Add None as empty string
                flat[full_key] = ''

        return flat

    def is_enabled(self) -> bool:
        """Check if notifier is enabled."""
        return self.enabled

    def validate_config(self) -> bool:
        """
        Validate notifier configuration.

        Returns:
            True if config is valid, False otherwise
        """
        # Base validation - subclasses can override
        return self.enabled


class SafeDict(dict):
    """Dict subclass that returns empty string for missing keys."""

    def __missing__(self, key):
        return f'{{{key}}}'  # Return placeholder for missing keys
