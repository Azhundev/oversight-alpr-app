#!/usr/bin/env python3
"""
Bulk Indexer for OpenSearch
Implements adaptive batching with size and time-based triggers.
"""

import time
import threading
from typing import List, Dict, Any, Callable, Optional
from datetime import datetime
from loguru import logger
from opensearch_client import OpenSearchClient
from index_manager import IndexManager


class BulkIndexer:
    """
    Adaptive bulk indexer for OpenSearch.

    Flushes batches based on:
    - Size trigger: Flush when batch reaches batch_size documents
    - Time trigger: Flush every flush_interval seconds
    """

    def __init__(
        self,
        opensearch_client: OpenSearchClient,
        index_manager: IndexManager,
        batch_size: int = 50,
        flush_interval: int = 5,
        max_retries: int = 3,
        metrics_callback: Optional[Callable] = None,
    ):
        """
        Initialize Bulk Indexer.

        Args:
            opensearch_client: OpenSearch client instance
            index_manager: Index manager instance
            batch_size: Number of documents to batch before flushing
            flush_interval: Time in seconds between automatic flushes
            max_retries: Maximum retries for failed documents
            metrics_callback: Optional callback function for metrics (batch_size, duration, errors)
        """
        self.client = opensearch_client
        self.index_manager = index_manager
        self.batch_size = batch_size
        self.flush_interval = flush_interval
        self.max_retries = max_retries
        self.metrics_callback = metrics_callback

        # Batch buffer
        self.buffer: List[Dict[str, Any]] = []
        self.buffer_lock = threading.Lock()

        # Timing
        self.last_flush_time = time.time()

        # Statistics
        self.stats = {
            'documents_added': 0,
            'documents_indexed': 0,
            'documents_failed': 0,
            'batches_flushed': 0,
            'bulk_errors': 0,
        }

        # Start background flush timer
        self._start_flush_timer()

    def add(self, event: Dict[str, Any]) -> bool:
        """
        Add a document to the batch buffer.

        Automatically flushes if batch size is reached.

        Args:
            event: Event data to index

        Returns:
            True if added successfully
        """
        try:
            with self.buffer_lock:
                # Get appropriate index for this event
                index_name = self.index_manager.get_index_for_event(event)

                # Add indexed_at timestamp
                event['indexed_at'] = datetime.utcnow().isoformat() + 'Z'

                # Prepare bulk action
                self.buffer.append({
                    'index_name': index_name,
                    'doc_id': event.get('event_id'),
                    'document': event
                })

                self.stats['documents_added'] += 1

                # Check if we need to flush (size trigger)
                if len(self.buffer) >= self.batch_size:
                    logger.debug(f"Size trigger: Flushing batch ({len(self.buffer)} documents)")
                    self._flush()

            return True

        except Exception as e:
            logger.error(f"❌ Error adding document to batch: {e}")
            return False

    def _flush(self):
        """
        Flush the current batch to OpenSearch.

        Must be called with buffer_lock held.
        """
        if not self.buffer:
            return

        batch = self.buffer.copy()
        self.buffer.clear()
        self.last_flush_time = time.time()

        # Release lock while performing I/O
        threading.Thread(target=self._flush_batch, args=(batch,), daemon=True).start()

    def _flush_batch(self, batch: List[Dict[str, Any]]):
        """
        Flush a batch of documents to OpenSearch.

        Args:
            batch: List of documents to index
        """
        if not batch:
            return

        start_time = time.time()
        batch_size = len(batch)

        try:
            # Build bulk request body (NDJSON format)
            bulk_body = []
            for item in batch:
                # Action metadata
                bulk_body.append({
                    'index': {
                        '_index': item['index_name'],
                        '_id': item['doc_id']
                    }
                })
                # Document source
                bulk_body.append(item['document'])

            # Execute bulk request
            response = self.client.bulk(body=bulk_body)

            # Process response
            errors = response.get('errors', False)
            items = response.get('items', [])

            indexed_count = 0
            failed_count = 0

            if errors:
                # Handle partial failures
                for item in items:
                    action = item.get('index', {})
                    if action.get('error'):
                        failed_count += 1
                        error_msg = action['error'].get('reason', 'unknown')
                        logger.error(f"❌ Failed to index document {action.get('_id')}: {error_msg}")
                    else:
                        indexed_count += 1
            else:
                # All succeeded
                indexed_count = batch_size

            # Update stats
            self.stats['documents_indexed'] += indexed_count
            self.stats['documents_failed'] += failed_count
            self.stats['batches_flushed'] += 1

            if failed_count > 0:
                self.stats['bulk_errors'] += 1

            # Calculate duration
            duration = time.time() - start_time

            # Log results
            if failed_count == 0:
                logger.success(
                    f"✅ Bulk indexed {indexed_count} documents in {duration:.2f}s "
                    f"(~{indexed_count/duration:.1f} docs/sec)"
                )
            else:
                logger.warning(
                    f"⚠️  Bulk indexed {indexed_count}/{batch_size} documents "
                    f"({failed_count} failed) in {duration:.2f}s"
                )

            # Call metrics callback if provided
            if self.metrics_callback:
                self.metrics_callback(
                    batch_size=indexed_count,
                    duration=duration,
                    errors=failed_count
                )

        except Exception as e:
            logger.error(f"❌ Bulk indexing failed: {e}")
            self.stats['documents_failed'] += batch_size
            self.stats['bulk_errors'] += 1

    def _start_flush_timer(self):
        """Start background timer for periodic flushing."""
        def timer_flush():
            while True:
                time.sleep(self.flush_interval)

                with self.buffer_lock:
                    if self.buffer:
                        elapsed = time.time() - self.last_flush_time
                        if elapsed >= self.flush_interval:
                            logger.debug(
                                f"Time trigger: Flushing batch "
                                f"({len(self.buffer)} documents, {elapsed:.1f}s elapsed)"
                            )
                            self._flush()

        # Start daemon thread
        flush_thread = threading.Thread(target=timer_flush, daemon=True)
        flush_thread.start()
        logger.debug(f"Background flush timer started (interval: {self.flush_interval}s)")

    def flush_now(self):
        """
        Force an immediate flush of pending documents.

        Useful for graceful shutdown.
        """
        with self.buffer_lock:
            if self.buffer:
                logger.info(f"Force flushing {len(self.buffer)} pending documents...")
                self._flush()

        # Wait a moment for background thread to complete
        time.sleep(0.5)

    def pending_count(self) -> int:
        """
        Get the number of documents pending in the buffer.

        Returns:
            Number of documents in buffer
        """
        with self.buffer_lock:
            return len(self.buffer)

    def get_stats(self) -> Dict[str, int]:
        """
        Get indexer statistics.

        Returns:
            Statistics dictionary
        """
        return self.stats.copy()
