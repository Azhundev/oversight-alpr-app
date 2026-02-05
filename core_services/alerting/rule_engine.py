"""
Rule Engine for evaluating alert rules against PlateEvent data.

Supports condition operators:
- equals: Field equals value
- contains: Field contains substring
- regex: Field matches regex pattern
- in_list: Field value in list
- greater_than: Numeric field > value
- less_than: Numeric field < value
"""

import re
import yaml
from typing import Dict, List, Any, Optional
from dataclasses import dataclass
from loguru import logger


@dataclass
class MatchedRule:
    """Represents a rule that matched an event."""
    rule_id: str
    rule_name: str
    priority: str  # high, medium, low
    notify_channels: List[str]  # email, slack, webhook, sms
    message_template: str
    rate_limit_config: Dict
    event_data: Dict  # The event that triggered this rule


class RuleEngine:
    """Evaluates events against configured alert rules."""

    def __init__(self, rules_config_path: str):
        """
        Initialize RuleEngine with rules from YAML config.

        Args:
            rules_config_path: Path to alert_rules.yaml file
        """
        self.rules_config_path = rules_config_path
        self.rules = []
        self.notification_config = {}
        self._load_rules()

    def _load_rules(self):
        """Load rules from YAML configuration file."""
        try:
            with open(self.rules_config_path, 'r') as f:
                config = yaml.safe_load(f)

            self.notification_config = config.get('notifications', {})
            self.rules = config.get('rules', [])

            enabled_count = sum(1 for r in self.rules if r.get('enabled', True))
            logger.info(f"Loaded {len(self.rules)} rules ({enabled_count} enabled) from {self.rules_config_path}")

        except FileNotFoundError:
            logger.error(f"Rules config file not found: {self.rules_config_path}")
            self.rules = []
        except yaml.YAMLError as e:
            logger.error(f"Failed to parse rules config: {e}")
            self.rules = []

    def reload_rules(self):
        """Reload rules from config file (for dynamic updates)."""
        logger.info("Reloading alert rules...")
        self._load_rules()

    def evaluate(self, event: Dict) -> List[MatchedRule]:
        """
        Evaluate event against all enabled rules.

        Args:
            event: PlateEvent data (dict from Avro deserialization)

        Returns:
            List of MatchedRule objects for rules that matched
        """
        matched_rules = []

        for rule in self.rules:
            # Skip disabled rules
            if not rule.get('enabled', True):
                continue

            # Check if all conditions match
            conditions = rule.get('conditions', [])
            if not conditions:
                logger.warning(f"Rule '{rule.get('id')}' has no conditions, skipping")
                continue

            all_conditions_match = True
            for condition in conditions:
                if not self._check_condition(condition, event):
                    all_conditions_match = False
                    break

            if all_conditions_match:
                # All conditions matched - create MatchedRule
                matched = MatchedRule(
                    rule_id=rule.get('id', 'unknown'),
                    rule_name=rule.get('name', 'Unknown Rule'),
                    priority=rule.get('priority', 'medium'),
                    notify_channels=rule.get('notify', []),
                    message_template=rule.get('message_template', ''),
                    rate_limit_config=rule.get('rate_limit', {}),
                    event_data=event
                )
                matched_rules.append(matched)
                logger.debug(f"Rule matched: {matched.rule_id} ({matched.rule_name})")

        return matched_rules

    def _check_condition(self, condition: Dict, event: Dict) -> bool:
        """
        Check if a single condition matches the event.

        Args:
            condition: Condition dict with 'field', 'operator', 'value'
            event: Event data

        Returns:
            True if condition matches, False otherwise
        """
        field_path = condition.get('field')
        operator = condition.get('operator')
        expected_value = condition.get('value')

        if not field_path or not operator:
            logger.warning(f"Invalid condition (missing field or operator): {condition}")
            return False

        # Get actual value from event using dot notation
        actual_value = self._get_nested_value(event, field_path)

        # Handle None values
        if actual_value is None:
            # Only 'equals' with None value should match
            if operator == 'equals' and expected_value is None:
                return True
            return False

        # Evaluate based on operator
        try:
            if operator == 'equals':
                return str(actual_value).lower() == str(expected_value).lower()

            elif operator == 'contains':
                return str(expected_value).lower() in str(actual_value).lower()

            elif operator == 'regex':
                pattern = re.compile(expected_value, re.IGNORECASE)
                return pattern.search(str(actual_value)) is not None

            elif operator == 'in_list':
                # expected_value should be a list
                if not isinstance(expected_value, list):
                    logger.warning(f"'in_list' operator requires list value, got: {type(expected_value)}")
                    return False
                # Case-insensitive comparison
                actual_str = str(actual_value).upper()
                return actual_str in [str(v).upper() for v in expected_value]

            elif operator == 'greater_than':
                # Convert to float for comparison
                return float(actual_value) > float(expected_value)

            elif operator == 'less_than':
                # Convert to float for comparison
                return float(actual_value) < float(expected_value)

            else:
                logger.warning(f"Unknown operator: {operator}")
                return False

        except (ValueError, TypeError) as e:
            logger.warning(f"Failed to evaluate condition {condition}: {e}")
            return False

    def _get_nested_value(self, event: Dict, field_path: str) -> Any:
        """
        Get value from nested dict using dot notation.

        Examples:
            'plate.normalized_text' -> event['plate']['normalized_text']
            'vehicle.color' -> event['vehicle']['color']
            'camera_id' -> event['camera_id']

        Args:
            event: Event data dict
            field_path: Dot-separated field path

        Returns:
            Field value or None if not found
        """
        try:
            value = event
            for key in field_path.split('.'):
                if isinstance(value, dict):
                    value = value.get(key)
                else:
                    return None

                if value is None:
                    return None

            return value

        except Exception as e:
            logger.warning(f"Failed to get nested value for '{field_path}': {e}")
            return None

    def get_notification_config(self, channel: str) -> Optional[Dict]:
        """
        Get notification configuration for a specific channel.

        Args:
            channel: Channel name (email, slack, webhook, sms)

        Returns:
            Config dict or None if channel not found/disabled
        """
        config = self.notification_config.get(channel, {})
        if not config.get('enabled', False):
            return None
        return config
