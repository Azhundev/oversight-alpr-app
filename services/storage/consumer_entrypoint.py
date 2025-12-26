#!/usr/bin/env python3
"""
Kafka Consumer Entrypoint
Starts either JSON or Avro consumer based on configuration
"""

import os
import sys
from loguru import logger


def main():
    """Main entrypoint - decide which consumer to use"""

    # Check if we should use Avro or JSON
    use_avro = os.getenv('USE_AVRO', 'false').lower() == 'true'

    logger.info("=" * 70)
    logger.info("🚀 ALPR Kafka Consumer")
    logger.info("=" * 70)
    logger.info(f"Serialization Format: {'Avro' if use_avro else 'JSON'}")
    logger.info("=" * 70)

    if use_avro:
        logger.info("📦 Using Avro deserialization with Schema Registry")
        try:
            from avro_kafka_consumer import main as avro_main
            avro_main()
        except ImportError as e:
            logger.error(f"Failed to import Avro consumer: {e}")
            logger.error("Make sure confluent-kafka[avro] is installed")
            logger.info("Falling back to JSON consumer...")
            from kafka_consumer import main as json_main
            json_main()
    else:
        logger.info("📄 Using JSON deserialization (legacy mode)")
        from kafka_consumer import main as json_main
        json_main()


if __name__ == "__main__":
    main()
