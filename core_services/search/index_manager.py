#!/usr/bin/env python3
"""
Index Manager for OpenSearch
Handles monthly index creation and lifecycle management.
"""

from datetime import datetime
from typing import Optional
from loguru import logger
from opensearch_client import OpenSearchClient


class IndexManager:
    """
    Manages time-based index creation and lifecycle for ALPR events.

    Creates monthly indices following the pattern: alpr-events-YYYY.MM
    """

    def __init__(
        self,
        opensearch_client: OpenSearchClient,
        index_prefix: str = "alpr-events",
    ):
        """
        Initialize Index Manager.

        Args:
            opensearch_client: OpenSearch client instance
            index_prefix: Prefix for index names (default: "alpr-events")
        """
        self.client = opensearch_client
        self.index_prefix = index_prefix
        self.current_index: Optional[str] = None

    def get_current_index_name(self) -> str:
        """
        Get the index name for the current month.

        Returns:
            Index name in format: {prefix}-YYYY.MM
        """
        now = datetime.utcnow()
        return f"{self.index_prefix}-{now.strftime('%Y.%m')}"

    def ensure_current_index_exists(self) -> str:
        """
        Ensure the current month's index exists. Create if necessary.

        Returns:
            Current index name

        Note:
            Index will automatically use the template if it matches the pattern.
            No need to explicitly provide settings/mappings.
        """
        index_name = self.get_current_index_name()

        # Check if we need to create a new index
        if self.current_index != index_name:
            if not self.client.index_exists(index_name):
                logger.info(f"Creating new monthly index: {index_name}")

                # Create index (will apply template automatically if pattern matches)
                success = self.client.create_index(index_name)

                if success:
                    self.current_index = index_name
                    logger.success(f"✅ Monthly index ready: {index_name}")
                else:
                    logger.error(f"❌ Failed to create index: {index_name}")
                    # Fall back to previous index if available
                    if self.current_index:
                        logger.warning(f"⚠️  Falling back to: {self.current_index}")
                        return self.current_index
                    raise Exception(f"Failed to create index: {index_name}")
            else:
                logger.debug(f"Index already exists: {index_name}")
                self.current_index = index_name

        return self.current_index

    def get_index_for_event(self, event: dict) -> str:
        """
        Get the appropriate index name for an event.

        Currently returns the current month's index.
        Could be extended to use event timestamp for historical data.

        Args:
            event: Event data (dict)

        Returns:
            Index name
        """
        # For real-time indexing, always use current month's index
        return self.ensure_current_index_exists()

    def get_index_for_timestamp(self, timestamp: datetime) -> str:
        """
        Get the index name for a specific timestamp.

        Useful for backfilling historical data.

        Args:
            timestamp: Event timestamp

        Returns:
            Index name in format: {prefix}-YYYY.MM
        """
        return f"{self.index_prefix}-{timestamp.strftime('%Y.%m')}"
