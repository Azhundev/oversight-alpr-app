#!/usr/bin/env python3
"""
OpenSearch Client Wrapper
Manages connection to OpenSearch cluster with health checks and error handling.
"""

from typing import Optional, Dict, Any, List
from loguru import logger
from opensearchpy import OpenSearch, exceptions as opensearch_exceptions


class OpenSearchClient:
    """
    OpenSearch client wrapper with connection management and health monitoring.
    """

    def __init__(
        self,
        hosts: List[str],
        use_ssl: bool = False,
        verify_certs: bool = False,
        timeout: int = 30,
        max_retries: int = 3,
        retry_on_timeout: bool = True,
    ):
        """
        Initialize OpenSearch client.

        Args:
            hosts: List of OpenSearch host URLs (e.g., ['http://opensearch:9200'])
            use_ssl: Enable SSL/TLS
            verify_certs: Verify SSL certificates
            timeout: Request timeout in seconds
            max_retries: Maximum number of retries for failed requests
            retry_on_timeout: Retry on timeout errors
        """
        self.hosts = hosts
        self.use_ssl = use_ssl
        self.verify_certs = verify_certs
        self.timeout = timeout
        self.client: Optional[OpenSearch] = None

        # Initialize client
        try:
            self.client = OpenSearch(
                hosts=hosts,
                use_ssl=use_ssl,
                verify_certs=verify_certs,
                timeout=timeout,
                max_retries=max_retries,
                retry_on_timeout=retry_on_timeout,
            )

            # Test connection
            info = self.client.info()
            logger.success(
                f"✅ Connected to OpenSearch cluster\n"
                f"   Cluster: {info.get('cluster_name', 'unknown')}\n"
                f"   Version: {info.get('version', {}).get('number', 'unknown')}\n"
                f"   Hosts: {hosts}"
            )
        except Exception as e:
            logger.error(f"❌ Failed to connect to OpenSearch: {e}")
            raise

    def is_healthy(self) -> bool:
        """
        Check if OpenSearch cluster is healthy.

        Returns:
            True if cluster status is green or yellow, False otherwise
        """
        try:
            health = self.client.cluster.health()
            status = health.get('status', 'red')

            if status in ['green', 'yellow']:
                return True
            else:
                logger.warning(f"⚠️  OpenSearch cluster status: {status}")
                return False

        except Exception as e:
            logger.error(f"❌ Failed to check OpenSearch health: {e}")
            return False

    def index_exists(self, index_name: str) -> bool:
        """
        Check if an index exists.

        Args:
            index_name: Name of the index

        Returns:
            True if index exists, False otherwise
        """
        try:
            return self.client.indices.exists(index=index_name)
        except Exception as e:
            logger.error(f"❌ Error checking if index exists: {e}")
            return False

    def create_index(
        self,
        index_name: str,
        body: Optional[Dict[str, Any]] = None
    ) -> bool:
        """
        Create an index.

        Args:
            index_name: Name of the index to create
            body: Index settings and mappings (optional, will use template if available)

        Returns:
            True if successful, False otherwise
        """
        try:
            if self.index_exists(index_name):
                logger.debug(f"Index '{index_name}' already exists, skipping creation")
                return True

            self.client.indices.create(index=index_name, body=body)
            logger.success(f"✅ Created index: {index_name}")
            return True

        except opensearch_exceptions.RequestError as e:
            if 'resource_already_exists_exception' in str(e):
                logger.debug(f"Index '{index_name}' already exists")
                return True
            else:
                logger.error(f"❌ Failed to create index '{index_name}': {e}")
                return False
        except Exception as e:
            logger.error(f"❌ Failed to create index '{index_name}': {e}")
            return False

    def bulk(self, body: List[Dict[str, Any]]) -> Dict[str, Any]:
        """
        Perform bulk indexing operation.

        Args:
            body: List of bulk operations (alternating action/doc)

        Returns:
            Bulk operation response

        Raises:
            Exception if bulk operation fails
        """
        try:
            response = self.client.bulk(body=body)
            return response
        except Exception as e:
            logger.error(f"❌ Bulk indexing failed: {e}")
            raise

    def index_document(
        self,
        index_name: str,
        doc_id: str,
        document: Dict[str, Any]
    ) -> bool:
        """
        Index a single document.

        Args:
            index_name: Index name
            doc_id: Document ID
            document: Document data

        Returns:
            True if successful, False otherwise
        """
        try:
            self.client.index(
                index=index_name,
                id=doc_id,
                body=document
            )
            return True
        except Exception as e:
            logger.error(f"❌ Failed to index document {doc_id}: {e}")
            return False

    def search(
        self,
        index: str,
        body: Dict[str, Any]
    ) -> Optional[Dict[str, Any]]:
        """
        Perform a search query.

        Args:
            index: Index name or pattern
            body: Search query DSL

        Returns:
            Search results or None on error
        """
        try:
            response = self.client.search(index=index, body=body)
            return response
        except Exception as e:
            logger.error(f"❌ Search failed: {e}")
            return None

    def get_cluster_stats(self) -> Optional[Dict[str, Any]]:
        """
        Get cluster statistics.

        Returns:
            Cluster stats or None on error
        """
        try:
            return self.client.cluster.stats()
        except Exception as e:
            logger.error(f"❌ Failed to get cluster stats: {e}")
            return None

    def close(self):
        """Close the OpenSearch client connection."""
        if self.client:
            try:
                self.client.close()
                logger.info("OpenSearch client closed")
            except Exception as e:
                logger.warning(f"Error closing OpenSearch client: {e}")
