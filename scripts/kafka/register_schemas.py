#!/usr/bin/env python3
"""
Register Avro schemas with Confluent Schema Registry

This script registers all ALPR event schemas with the Schema Registry.
Run this after starting the Schema Registry service.

Usage:
    python scripts/register_schemas.py
"""

import json
import sys
import requests
from pathlib import Path
from loguru import logger

# Configuration
SCHEMA_REGISTRY_URL = "http://localhost:8081"
SCHEMAS_DIR = Path(__file__).parent.parent / "schemas"

# Schema to subject mapping
# Format: {schema_filename: subject_name}
# Subject naming convention: {topic_name}-value (for value schemas)
# Use {topic_name}-key for key schemas
SCHEMA_MAPPINGS = {
    "plate_event.avsc": "alpr.plates.detected-value"
}


def check_schema_registry():
    """Check if Schema Registry is accessible"""
    try:
        response = requests.get(f"{SCHEMA_REGISTRY_URL}/subjects", timeout=5)
        response.raise_for_status()
        logger.success(f"✅ Schema Registry accessible at {SCHEMA_REGISTRY_URL}")
        return True
    except requests.exceptions.RequestException as e:
        logger.error(f"❌ Cannot connect to Schema Registry: {e}")
        logger.info("Make sure Schema Registry is running: docker compose up -d schema-registry")
        return False


def register_schema(schema_file: Path, subject: str) -> bool:
    """
    Register a schema with the Schema Registry

    Args:
        schema_file: Path to the Avro schema file (.avsc)
        subject: Schema Registry subject name

    Returns:
        True if successful, False otherwise
    """
    try:
        # Read schema file
        with open(schema_file, 'r') as f:
            schema_json = json.load(f)

        # Convert schema to string (Schema Registry expects JSON string)
        schema_str = json.dumps(schema_json)

        # Prepare request payload (Schema Registry v1 format)
        # schema: JSON string representation of Avro schema
        # schemaType: Must be "AVRO", "JSON", or "PROTOBUF"
        payload = {
            "schema": schema_str,
            "schemaType": "AVRO"
        }

        # Register schema
        url = f"{SCHEMA_REGISTRY_URL}/subjects/{subject}/versions"
        response = requests.post(
            url,
            json=payload,
            headers={"Content-Type": "application/vnd.schemaregistry.v1+json"}
        )

        if response.status_code == 200:
            # Successfully registered new schema version
            schema_id = response.json()['id']
            logger.success(f"✅ Registered schema: {subject} (ID: {schema_id})")
            return True
        elif response.status_code == 409:
            # Schema already exists (identical schema previously registered - idempotent operation)
            logger.info(f"ℹ️  Schema already registered: {subject}")
            return True
        else:
            logger.error(f"❌ Failed to register {subject}: {response.status_code}")
            logger.error(f"   Response: {response.text}")
            return False

    except FileNotFoundError:
        logger.error(f"❌ Schema file not found: {schema_file}")
        return False
    except json.JSONDecodeError as e:
        logger.error(f"❌ Invalid JSON in {schema_file}: {e}")
        return False
    except Exception as e:
        logger.error(f"❌ Error registering {subject}: {e}")
        return False


def list_registered_schemas():
    """List all registered schemas"""
    try:
        response = requests.get(f"{SCHEMA_REGISTRY_URL}/subjects")
        response.raise_for_status()

        subjects = response.json()
        if subjects:
            logger.info(f"\n📋 Registered schemas ({len(subjects)} total):")
            for subject in subjects:
                # Fetch latest version metadata (includes version number and global schema ID)
                version_response = requests.get(
                    f"{SCHEMA_REGISTRY_URL}/subjects/{subject}/versions/latest"
                )
                if version_response.status_code == 200:
                    version_data = version_response.json()
                    logger.info(f"   • {subject}")
                    logger.info(f"     Version: {version_data.get('version', 'unknown')}")
                    logger.info(f"     ID: {version_data.get('id', 'unknown')}")
        else:
            logger.info("📋 No schemas registered yet")

    except Exception as e:
        logger.error(f"❌ Error listing schemas: {e}")


def get_compatibility_mode(subject: str = None):
    """Get compatibility mode for a subject or global"""
    try:
        if subject:
            url = f"{SCHEMA_REGISTRY_URL}/config/{subject}"
        else:
            url = f"{SCHEMA_REGISTRY_URL}/config"

        response = requests.get(url)
        response.raise_for_status()

        config = response.json()
        mode = config.get('compatibilityLevel', 'UNKNOWN')

        if subject:
            logger.info(f"🔧 Compatibility mode for {subject}: {mode}")
        else:
            logger.info(f"🔧 Global compatibility mode: {mode}")

        return mode

    except Exception as e:
        logger.error(f"❌ Error getting compatibility mode: {e}")
        return None


def main():
    """Main registration process"""
    logger.info("=" * 70)
    logger.info("🚀 ALPR Schema Registry Setup")
    logger.info("=" * 70)

    # Step 1: Check Schema Registry connectivity
    if not check_schema_registry():
        sys.exit(1)

    # Step 2: Get global compatibility mode
    get_compatibility_mode()

    # Step 3: Register schemas
    logger.info(f"\n📝 Registering schemas from: {SCHEMAS_DIR}")
    success_count = 0
    total_count = len(SCHEMA_MAPPINGS)

    for schema_file_name, subject in SCHEMA_MAPPINGS.items():
        schema_file = SCHEMAS_DIR / schema_file_name
        logger.info(f"\n🔧 Processing: {schema_file_name} → {subject}")

        if register_schema(schema_file, subject):
            success_count += 1

    # Step 4: Summary
    logger.info("\n" + "=" * 70)
    logger.info(f"📊 Summary: {success_count}/{total_count} schemas registered")
    logger.info("=" * 70)

    # Step 5: List all registered schemas
    list_registered_schemas()

    # Step 6: Final instructions
    logger.info("\n✨ Next Steps:")
    logger.info("   1. Update Kafka producers to use Avro serialization")
    logger.info("   2. Update Kafka consumers to use Avro deserialization")
    logger.info("   3. Restart services: docker compose restart kafka-consumer query-api")
    logger.info("\n🌐 Schema Registry UI: http://localhost:8080 (Kafka UI)")
    logger.info("🔍 Schema Registry API: http://localhost:8081")

    if success_count == total_count:
        logger.success("\n✅ All schemas registered successfully!")
        sys.exit(0)
    else:
        logger.error(f"\n❌ Failed to register {total_count - success_count} schema(s)")
        sys.exit(1)


if __name__ == "__main__":
    main()
