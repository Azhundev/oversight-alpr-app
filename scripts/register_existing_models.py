#!/usr/bin/env python3
"""
Register Existing YOLO Models to MLflow Model Registry

This script registers the existing YOLO models (vehicle and plate detectors)
to the MLflow Model Registry, enabling version tracking and deployment management.

Models registered:
- alpr-vehicle-detector: yolo11n.pt (COCO pre-trained for vehicles)
- alpr-plate-detector: yolo11n-plate.pt (Custom trained for license plates)

Usage:
    python scripts/register_existing_models.py

Environment Variables:
    MLFLOW_TRACKING_URI: MLflow server URL (default: http://localhost:5000)
"""

import os
import sys
import json
import hashlib
from pathlib import Path
from datetime import datetime

import mlflow
from mlflow.tracking import MlflowClient
from loguru import logger

# Configuration
MLFLOW_TRACKING_URI = os.environ.get("MLFLOW_TRACKING_URI", "http://localhost:5000")
MODELS_DIR = Path(__file__).parent.parent / "models"

# Model definitions
MODELS_TO_REGISTER = [
    {
        "name": "alpr-vehicle-detector",
        "description": "YOLOv11 vehicle detector trained on COCO dataset. Detects cars, trucks, buses, and motorcycles.",
        "files": {
            "pt": "yolo11n.pt",
            "engine": "yolo11n.engine",
            "onnx": "yolo11n.onnx",
        },
        "tags": {
            "model_type": "yolov11",
            "task": "object_detection",
            "classes": "car,truck,bus,motorcycle",
            "framework": "ultralytics",
            "precision": "fp16",
        },
    },
    {
        "name": "alpr-plate-detector",
        "description": "YOLOv11 license plate detector. Custom trained for detecting license plates on vehicles.",
        "files": {
            "pt": "yolo11n-plate.pt",
            "engine": "yolo11n-plate.engine",
            "onnx": "yolo11n-plate.onnx",
        },
        "tags": {
            "model_type": "yolov11",
            "task": "object_detection",
            "classes": "license_plate",
            "framework": "ultralytics",
            "precision": "fp16",
            "custom_trained": "true",
        },
    },
]


def get_file_hash(filepath: Path) -> str:
    """Calculate MD5 hash of a file."""
    if not filepath.exists():
        return ""
    with open(filepath, "rb") as f:
        return hashlib.md5(f.read()).hexdigest()


def get_version_info(model_dir: Path, base_name: str) -> dict:
    """Read version info from .version file if it exists."""
    version_file = model_dir / f"{base_name}.version"
    if version_file.exists():
        try:
            with open(version_file, "r") as f:
                return json.load(f)
        except Exception as e:
            logger.warning(f"Failed to read version file {version_file}: {e}")
    return {}


def register_model(
    client: MlflowClient,
    model_config: dict,
    models_dir: Path,
) -> bool:
    """
    Register a model to MLflow Model Registry.

    Args:
        client: MLflow client instance
        model_config: Model configuration dict
        models_dir: Directory containing model files

    Returns:
        True if successful, False otherwise
    """
    model_name = model_config["name"]
    description = model_config["description"]
    files = model_config["files"]
    tags = model_config["tags"]

    logger.info(f"Registering model: {model_name}")

    # Check which files exist
    available_files = {}
    for file_type, filename in files.items():
        filepath = models_dir / filename
        if filepath.exists():
            available_files[file_type] = filepath
            logger.info(f"  Found {file_type}: {filepath}")

    if not available_files:
        logger.error(f"  No model files found for {model_name}")
        return False

    # Get the primary model file (.pt preferred)
    if "pt" in available_files:
        primary_file = available_files["pt"]
    elif "engine" in available_files:
        primary_file = available_files["engine"]
    else:
        primary_file = list(available_files.values())[0]

    # Get version info if available
    base_name = primary_file.stem
    version_info = get_version_info(models_dir, base_name)

    # Create or get registered model
    try:
        registered_model = client.get_registered_model(model_name)
        logger.info(f"  Model '{model_name}' already registered")
    except mlflow.exceptions.MlflowException:
        logger.info(f"  Creating new registered model: {model_name}")
        registered_model = client.create_registered_model(
            name=model_name,
            description=description,
            tags=tags,
        )

    # Create experiment for this model
    experiment_name = f"ALPR/{model_name}"
    experiment = mlflow.get_experiment_by_name(experiment_name)
    if experiment is None:
        experiment_id = mlflow.create_experiment(
            experiment_name,
            tags={"model_name": model_name, "purpose": "model_registration"}
        )
    else:
        experiment_id = experiment.experiment_id

    # Start a run to log the model
    with mlflow.start_run(experiment_id=experiment_id, run_name=f"register-{datetime.now().strftime('%Y%m%d-%H%M%S')}"):
        # Log parameters
        mlflow.log_param("model_name", model_name)
        mlflow.log_param("primary_file", str(primary_file.name))
        mlflow.log_param("file_size_mb", round(primary_file.stat().st_size / (1024 * 1024), 2))
        mlflow.log_param("file_hash", get_file_hash(primary_file))

        # Log version info if available
        if version_info:
            for key, value in version_info.items():
                mlflow.log_param(f"version_{key}", str(value))

        # Log all available model files as artifacts
        artifact_dir = "model_files"
        for file_type, filepath in available_files.items():
            logger.info(f"  Uploading artifact: {filepath.name}")
            mlflow.log_artifact(str(filepath), artifact_dir)

        # Log version file if exists
        version_file = models_dir / f"{base_name}.version"
        if version_file.exists():
            mlflow.log_artifact(str(version_file), artifact_dir)

        # Get artifact URI
        run_id = mlflow.active_run().info.run_id
        artifact_uri = f"runs:/{run_id}/{artifact_dir}"

        # Register model version
        try:
            model_version = client.create_model_version(
                name=model_name,
                source=artifact_uri,
                run_id=run_id,
                description=f"Registered from existing model files on {datetime.now().isoformat()}",
                tags={
                    "registered_from": "local_files",
                    "primary_file": primary_file.name,
                    "file_hash": get_file_hash(primary_file),
                }
            )

            logger.success(f"  Created model version: {model_version.version}")

            # Transition to Production stage
            client.transition_model_version_stage(
                name=model_name,
                version=model_version.version,
                stage="Production",
                archive_existing_versions=True,
            )
            logger.success(f"  Model version {model_version.version} promoted to Production")

        except Exception as e:
            logger.error(f"  Failed to create model version: {e}")
            return False

    return True


def main():
    """Main registration function."""
    logger.info("=" * 60)
    logger.info("MLflow Model Registration Script")
    logger.info("=" * 60)

    # Check models directory
    if not MODELS_DIR.exists():
        logger.error(f"Models directory not found: {MODELS_DIR}")
        sys.exit(1)

    logger.info(f"Models directory: {MODELS_DIR}")
    logger.info(f"MLflow tracking URI: {MLFLOW_TRACKING_URI}")

    # Initialize MLflow
    mlflow.set_tracking_uri(MLFLOW_TRACKING_URI)
    client = MlflowClient(tracking_uri=MLFLOW_TRACKING_URI)

    # Test connection
    try:
        client.search_experiments()
        logger.success(f"Connected to MLflow at {MLFLOW_TRACKING_URI}")
    except Exception as e:
        logger.error(f"Failed to connect to MLflow: {e}")
        logger.error("Make sure MLflow server is running: docker compose up -d mlflow")
        sys.exit(1)

    # Register each model
    success_count = 0
    for model_config in MODELS_TO_REGISTER:
        logger.info("-" * 40)
        if register_model(client, model_config, MODELS_DIR):
            success_count += 1

    # Summary
    logger.info("=" * 60)
    logger.info(f"Registration complete: {success_count}/{len(MODELS_TO_REGISTER)} models registered")

    if success_count == len(MODELS_TO_REGISTER):
        logger.success("All models registered successfully!")
    else:
        logger.warning("Some models failed to register. Check the logs above.")

    # Print registered models
    logger.info("\n--- Registered Models ---")
    for model in client.search_registered_models():
        latest_versions = client.get_latest_versions(model.name)
        for version in latest_versions:
            logger.info(
                f"  {model.name} v{version.version} [{version.current_stage}]"
            )

    logger.info("\nAccess MLflow UI at: http://localhost:5000")


if __name__ == "__main__":
    main()
