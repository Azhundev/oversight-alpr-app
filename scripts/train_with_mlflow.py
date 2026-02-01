#!/usr/bin/env python3
"""
YOLO Training Script with MLflow Experiment Tracking

This script trains YOLOv11 models with full MLflow integration for:
- Experiment tracking (hyperparameters, metrics)
- Artifact logging (model files, plots, configs)
- Model versioning in the registry

Usage:
    # Train plate detector
    python scripts/train_with_mlflow.py \
        --data plates.yaml \
        --model yolo11n.pt \
        --epochs 100 \
        --name plate-detector

    # Train vehicle detector (fine-tune)
    python scripts/train_with_mlflow.py \
        --data vehicles.yaml \
        --model yolo11n.pt \
        --epochs 50 \
        --name vehicle-detector

Environment Variables:
    MLFLOW_TRACKING_URI: MLflow server URL (default: http://localhost:5000)
"""

import os
import sys
import argparse
import json
import shutil
from pathlib import Path
from datetime import datetime
from typing import Optional, Dict, Any

import mlflow
from mlflow.tracking import MlflowClient
from loguru import logger

try:
    from ultralytics import YOLO
    from ultralytics.utils.callbacks.mlflow import callbacks as mlflow_callbacks
    ULTRALYTICS_AVAILABLE = True
except ImportError:
    ULTRALYTICS_AVAILABLE = False
    logger.error("Ultralytics not installed. Please install: pip install ultralytics")


# Configuration
MLFLOW_TRACKING_URI = os.environ.get("MLFLOW_TRACKING_URI", "http://localhost:5000")
DEFAULT_EXPERIMENT = "ALPR/model-training"


class MLflowYOLOTrainer:
    """
    YOLO trainer with MLflow integration for ALPR models.

    Logs:
    - Hyperparameters: epochs, batch_size, imgsz, learning_rate, etc.
    - Metrics: mAP50, mAP50-95, precision, recall, losses (per epoch)
    - Artifacts: best.pt, last.pt, results.csv, confusion_matrix.png, etc.
    """

    def __init__(
        self,
        tracking_uri: str = MLFLOW_TRACKING_URI,
        experiment_name: str = DEFAULT_EXPERIMENT,
    ):
        """
        Initialize the MLflow YOLO trainer.

        Args:
            tracking_uri: MLflow server URI
            experiment_name: MLflow experiment name
        """
        self.tracking_uri = tracking_uri
        self.experiment_name = experiment_name

        # Initialize MLflow
        mlflow.set_tracking_uri(tracking_uri)
        self.client = MlflowClient(tracking_uri=tracking_uri)

        # Create or get experiment
        experiment = mlflow.get_experiment_by_name(experiment_name)
        if experiment is None:
            self.experiment_id = mlflow.create_experiment(
                experiment_name,
                tags={"project": "ALPR", "framework": "ultralytics"}
            )
            logger.info(f"Created experiment: {experiment_name}")
        else:
            self.experiment_id = experiment.experiment_id
            logger.info(f"Using existing experiment: {experiment_name}")

    def train(
        self,
        data: str,
        model: str = "yolo11n.pt",
        epochs: int = 100,
        imgsz: int = 640,
        batch: int = 16,
        device: str = "0",
        workers: int = 8,
        name: str = "alpr-model",
        patience: int = 50,
        save_period: int = 10,
        lr0: float = 0.01,
        lrf: float = 0.01,
        optimizer: str = "AdamW",
        augment: bool = True,
        project: str = "runs/train",
        **kwargs,
    ) -> Optional[Path]:
        """
        Train a YOLO model with MLflow tracking.

        Args:
            data: Path to data YAML file (e.g., plates.yaml)
            model: Base model path or name
            epochs: Number of training epochs
            imgsz: Input image size
            batch: Batch size
            device: CUDA device (0, 1, etc.) or 'cpu'
            workers: Number of data loader workers
            name: Model/run name
            patience: Early stopping patience
            save_period: Save checkpoint every N epochs
            lr0: Initial learning rate
            lrf: Final learning rate factor
            optimizer: Optimizer name (AdamW, SGD, etc.)
            augment: Enable augmentations
            project: Output project directory
            **kwargs: Additional YOLO training arguments

        Returns:
            Path to best.pt model file, or None if training failed
        """
        if not ULTRALYTICS_AVAILABLE:
            logger.error("Ultralytics not available. Cannot train.")
            return None

        run_name = f"{name}-{datetime.now().strftime('%Y%m%d-%H%M%S')}"

        logger.info("=" * 60)
        logger.info(f"Starting training: {run_name}")
        logger.info("=" * 60)

        with mlflow.start_run(
            experiment_id=self.experiment_id,
            run_name=run_name,
            tags={
                "model_name": name,
                "base_model": model,
                "data_config": data,
            }
        ):
            # Log hyperparameters
            params = {
                "model_name": name,
                "base_model": model,
                "data_config": data,
                "epochs": epochs,
                "imgsz": imgsz,
                "batch_size": batch,
                "device": device,
                "workers": workers,
                "patience": patience,
                "lr0": lr0,
                "lrf": lrf,
                "optimizer": optimizer,
                "augment": augment,
            }
            params.update(kwargs)
            mlflow.log_params(params)

            logger.info("Logged hyperparameters to MLflow")

            # Initialize YOLO model
            yolo_model = YOLO(model)

            # Configure training output directory
            output_dir = Path(project) / run_name

            try:
                # Train the model
                results = yolo_model.train(
                    data=data,
                    epochs=epochs,
                    imgsz=imgsz,
                    batch=batch,
                    device=device,
                    workers=workers,
                    name=run_name,
                    patience=patience,
                    save_period=save_period,
                    lr0=lr0,
                    lrf=lrf,
                    optimizer=optimizer,
                    augment=augment,
                    project=project,
                    exist_ok=True,
                    verbose=True,
                    **kwargs,
                )

                # Log final metrics
                if hasattr(results, 'results_dict'):
                    metrics = results.results_dict
                    for key, value in metrics.items():
                        if isinstance(value, (int, float)):
                            mlflow.log_metric(key, value)

                # Find training output directory
                train_dir = Path(project) / run_name
                if not train_dir.exists():
                    train_dir = Path(yolo_model.trainer.save_dir)

                logger.info(f"Training output directory: {train_dir}")

                # Log artifacts
                self._log_artifacts(train_dir)

                # Get best model path
                best_model_path = train_dir / "weights" / "best.pt"
                if best_model_path.exists():
                    logger.success(f"Training complete! Best model: {best_model_path}")
                    return best_model_path
                else:
                    logger.warning("best.pt not found in training output")
                    return None

            except Exception as e:
                logger.error(f"Training failed: {e}")
                mlflow.log_param("error", str(e))
                raise

    def _log_artifacts(self, train_dir: Path) -> None:
        """
        Log training artifacts to MLflow.

        Args:
            train_dir: Training output directory
        """
        artifacts_to_log = [
            # Model weights
            ("weights/best.pt", "model"),
            ("weights/last.pt", "model"),
            # Training results
            ("results.csv", "metrics"),
            ("results.png", "plots"),
            # Validation plots
            ("confusion_matrix.png", "plots"),
            ("confusion_matrix_normalized.png", "plots"),
            ("F1_curve.png", "plots"),
            ("P_curve.png", "plots"),
            ("R_curve.png", "plots"),
            ("PR_curve.png", "plots"),
            # Training plots
            ("labels.jpg", "plots"),
            ("labels_correlogram.jpg", "plots"),
            ("train_batch0.jpg", "training_samples"),
            ("train_batch1.jpg", "training_samples"),
            ("val_batch0_pred.jpg", "validation_samples"),
            ("val_batch1_pred.jpg", "validation_samples"),
            # Config
            ("args.yaml", "config"),
        ]

        for artifact_path, artifact_dir in artifacts_to_log:
            full_path = train_dir / artifact_path
            if full_path.exists():
                try:
                    mlflow.log_artifact(str(full_path), artifact_dir)
                    logger.debug(f"Logged artifact: {artifact_path}")
                except Exception as e:
                    logger.warning(f"Failed to log artifact {artifact_path}: {e}")

    def register_trained_model(
        self,
        model_path: Path,
        model_name: str,
        description: str = "",
        stage: str = "Staging",
        tags: Optional[Dict[str, str]] = None,
    ) -> Optional[str]:
        """
        Register a trained model to the MLflow Model Registry.

        Args:
            model_path: Path to the trained model file
            model_name: Name for the registered model
            description: Model description
            stage: Initial stage (None, Staging, Production, Archived)
            tags: Additional tags for the model version

        Returns:
            Model version string if successful, None otherwise
        """
        if not model_path.exists():
            logger.error(f"Model file not found: {model_path}")
            return None

        logger.info(f"Registering model: {model_name}")

        # Get current run info
        run_id = mlflow.active_run().info.run_id if mlflow.active_run() else None

        if run_id is None:
            # Start a new run for registration
            with mlflow.start_run(
                experiment_id=self.experiment_id,
                run_name=f"register-{model_name}-{datetime.now().strftime('%Y%m%d-%H%M%S')}"
            ):
                run_id = mlflow.active_run().info.run_id
                mlflow.log_artifact(str(model_path), "model")
                artifact_uri = f"runs:/{run_id}/model"
        else:
            artifact_uri = f"runs:/{run_id}/model"

        # Create or update registered model
        try:
            self.client.get_registered_model(model_name)
        except mlflow.exceptions.MlflowException:
            self.client.create_registered_model(
                name=model_name,
                description=description,
                tags=tags or {}
            )

        # Create model version
        version = self.client.create_model_version(
            name=model_name,
            source=artifact_uri,
            run_id=run_id,
            description=description,
            tags=tags or {},
        )

        logger.success(f"Created model version: {version.version}")

        # Transition to specified stage
        if stage:
            self.client.transition_model_version_stage(
                name=model_name,
                version=version.version,
                stage=stage,
                archive_existing_versions=(stage == "Production"),
            )
            logger.success(f"Transitioned to {stage}")

        return version.version


def main():
    """Main training function with CLI arguments."""
    parser = argparse.ArgumentParser(
        description="Train YOLO models with MLflow tracking"
    )

    # Required arguments
    parser.add_argument(
        "--data", "-d",
        type=str,
        required=True,
        help="Path to data YAML file"
    )

    # Optional arguments
    parser.add_argument(
        "--model", "-m",
        type=str,
        default="yolo11n.pt",
        help="Base model path or name (default: yolo11n.pt)"
    )
    parser.add_argument(
        "--epochs", "-e",
        type=int,
        default=100,
        help="Number of training epochs (default: 100)"
    )
    parser.add_argument(
        "--imgsz",
        type=int,
        default=640,
        help="Input image size (default: 640)"
    )
    parser.add_argument(
        "--batch", "-b",
        type=int,
        default=16,
        help="Batch size (default: 16)"
    )
    parser.add_argument(
        "--device",
        type=str,
        default="0",
        help="CUDA device (default: 0)"
    )
    parser.add_argument(
        "--name", "-n",
        type=str,
        default="alpr-model",
        help="Model name (default: alpr-model)"
    )
    parser.add_argument(
        "--patience",
        type=int,
        default=50,
        help="Early stopping patience (default: 50)"
    )
    parser.add_argument(
        "--lr0",
        type=float,
        default=0.01,
        help="Initial learning rate (default: 0.01)"
    )
    parser.add_argument(
        "--optimizer",
        type=str,
        default="AdamW",
        choices=["SGD", "Adam", "AdamW", "RMSProp"],
        help="Optimizer (default: AdamW)"
    )
    parser.add_argument(
        "--register",
        action="store_true",
        help="Register model to MLflow registry after training"
    )
    parser.add_argument(
        "--stage",
        type=str,
        default="Staging",
        choices=["None", "Staging", "Production", "Archived"],
        help="Model stage after registration (default: Staging)"
    )
    parser.add_argument(
        "--mlflow-uri",
        type=str,
        default=MLFLOW_TRACKING_URI,
        help=f"MLflow tracking URI (default: {MLFLOW_TRACKING_URI})"
    )
    parser.add_argument(
        "--experiment",
        type=str,
        default=DEFAULT_EXPERIMENT,
        help=f"MLflow experiment name (default: {DEFAULT_EXPERIMENT})"
    )

    args = parser.parse_args()

    # Initialize trainer
    trainer = MLflowYOLOTrainer(
        tracking_uri=args.mlflow_uri,
        experiment_name=args.experiment,
    )

    # Train the model
    best_model = trainer.train(
        data=args.data,
        model=args.model,
        epochs=args.epochs,
        imgsz=args.imgsz,
        batch=args.batch,
        device=args.device,
        name=args.name,
        patience=args.patience,
        lr0=args.lr0,
        optimizer=args.optimizer,
    )

    if best_model and args.register:
        # Register to model registry
        registered_name = f"alpr-{args.name}"
        trainer.register_trained_model(
            model_path=best_model,
            model_name=registered_name,
            description=f"Trained on {args.data} for {args.epochs} epochs",
            stage=args.stage if args.stage != "None" else None,
        )

    logger.info("=" * 60)
    logger.info("Training script complete")
    logger.info(f"View results at: {args.mlflow_uri}")
    logger.info("=" * 60)


if __name__ == "__main__":
    main()
