"""
Rate limiter to prevent alert spam.
Implements cooldown periods based on configurable dedup keys.
"""

import time
from typing import Dict, Optional
from collections import defaultdict
from loguru import logger


class RateLimiter:
    """
    Rate limiter with configurable cooldown periods.

    Prevents sending duplicate alerts within a specified time window.
    Tracks alerts by (rule_id, dedup_key) combination.
    """

    def __init__(self, cleanup_interval: int = 3600):
        """
        Initialize rate limiter.

        Args:
            cleanup_interval: How often to clean up old entries (seconds)
        """
        # Track last alert time: {(rule_id, dedup_value): timestamp}
        self._alert_timestamps: Dict[tuple, float] = {}

        # Cleanup interval
        self._cleanup_interval = cleanup_interval
        self._last_cleanup = time.time()

    def should_alert(
        self,
        rule_id: str,
        event: Dict,
        cooldown_seconds: int,
        dedup_key: str = "plate.normalized_text"
    ) -> bool:
        """
        Check if an alert should be sent based on rate limiting.

        Args:
            rule_id: Rule identifier
            event: Event data dict
            cooldown_seconds: Cooldown period in seconds
            dedup_key: Field path to use for deduplication (e.g., "plate.normalized_text")

        Returns:
            True if alert should be sent, False if rate-limited
        """
        # Get dedup value from event
        dedup_value = self._get_nested_value(event, dedup_key)
        if dedup_value is None:
            # If we can't get dedup key, allow the alert but warn
            logger.warning(f"Could not extract dedup key '{dedup_key}' from event, allowing alert")
            return True

        # Create cache key
        cache_key = (rule_id, str(dedup_value))

        # Check if we've alerted recently
        current_time = time.time()
        last_alert_time = self._alert_timestamps.get(cache_key)

        if last_alert_time is not None:
            time_since_last_alert = current_time - last_alert_time
            if time_since_last_alert < cooldown_seconds:
                # Still in cooldown period
                remaining = cooldown_seconds - time_since_last_alert
                logger.debug(
                    f"Rate limiting alert for rule '{rule_id}' "
                    f"(dedup: {dedup_value}, {remaining:.0f}s remaining)"
                )
                return False

        # Update timestamp and allow alert
        self._alert_timestamps[cache_key] = current_time

        # Periodic cleanup
        if current_time - self._last_cleanup > self._cleanup_interval:
            self._cleanup_old_entries(cooldown_seconds)

        return True

    def _get_nested_value(self, event: Dict, field_path: str) -> Optional[str]:
        """
        Get value from nested dict using dot notation.

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

            return str(value) if value is not None else None

        except Exception as e:
            logger.warning(f"Failed to get nested value for '{field_path}': {e}")
            return None

    def _cleanup_old_entries(self, max_cooldown: int = 3600):
        """
        Remove old entries from the cache to prevent memory leaks.

        Args:
            max_cooldown: Maximum cooldown period to keep (seconds)
        """
        current_time = time.time()
        cutoff_time = current_time - (max_cooldown * 2)  # Keep 2x max cooldown

        # Count before cleanup
        count_before = len(self._alert_timestamps)

        # Remove old entries
        self._alert_timestamps = {
            key: timestamp
            for key, timestamp in self._alert_timestamps.items()
            if timestamp > cutoff_time
        }

        # Count after cleanup
        count_after = len(self._alert_timestamps)
        removed = count_before - count_after

        if removed > 0:
            logger.info(f"Rate limiter cleanup: removed {removed} old entries, {count_after} remaining")

        self._last_cleanup = current_time

    def get_stats(self) -> Dict:
        """
        Get rate limiter statistics.

        Returns:
            Dict with stats about the rate limiter
        """
        return {
            'total_entries': len(self._alert_timestamps),
            'last_cleanup': self._last_cleanup
        }

    def clear(self):
        """Clear all rate limit entries (for testing)."""
        self._alert_timestamps.clear()
        logger.info("Rate limiter cache cleared")
