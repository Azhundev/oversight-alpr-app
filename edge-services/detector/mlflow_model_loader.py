"""
MLflow Model Loader for ALPR System
Provides model loading from MLflow Model Registry with local fallback

This module allows the detector service to load models from:
1. MLflow Model Registry (preferred) - with versioning and stage management
2. Local models directory (fallback) - for offline/development use
"""

import os
import shutil
import tempfile
from pathlib import Path
from typing import Optional, Tuple, Dict, Any
from loguru import logger

try:
    import mlflow
    from mlflow.tracking import MlflowClient
    MLFLOW_AVAILABLE = True
except ImportError:
    MLFLOW_AVAILABLE = False
    logger.warning("MLflow not installed. Model loading will use local files only.")


class MLflowModelLoader:
    """
    Model loader that fetches models from MLflow Model Registry
    with automatic fallback to local model files.

    Model Stages:
    - Production: Active deployment model
    - Staging: Testing/validation
    - Archived: Previous versions
    - None: Just registered, not deployed

    Example usage:
        loader = MLflowModelLoader()
        model_path, metadata = loader.get_model_path(
            "alpr-plate-detector",
            fallback_filename="yolo11n-plate.pt"
        )
    """

    # Default model directory (relative to project root)
    DEFAULT_MODELS_DIR = "models"

    # Default MLflow tracking URI
    DEFAULT_TRACKING_URI = "http://localhost:5000"

    def __init__(
        self,
        tracking_uri: Optional[str] = None,
        fallback_models_dir: Optional[str] = None,
        enable_mlflow: bool = True,
        preferred_stage: str = "Production",
        cache_dir: Optional[str] = None,
    ):
        """
        Initialize the MLflow model loader.

        Args:
            tracking_uri: MLflow tracking server URI. Defaults to http://localhost:5000
            fallback_models_dir: Local directory for fallback models. Defaults to ./models
            enable_mlflow: Whether to attempt MLflow loading. Set False for local-only mode.
            preferred_stage: Preferred model stage to load (Production, Staging, etc.)
            cache_dir: Directory to cache downloaded models. Defaults to temp directory.
        """
        self.tracking_uri = tracking_uri or os.environ.get(
            "MLFLOW_TRACKING_URI", self.DEFAULT_TRACKING_URI
        )
        self.fallback_models_dir = fallback_models_dir or os.environ.get(
            "ALPR_MODELS_DIR", self.DEFAULT_MODELS_DIR
        )
        self.enable_mlflow = enable_mlflow and MLFLOW_AVAILABLE
        self.preferred_stage = preferred_stage
        self.cache_dir = cache_dir or os.path.join(tempfile.gettempdir(), "alpr-mlflow-cache")

        # Configure S3/MinIO credentials for artifact access
        if self.enable_mlflow:
            os.environ.setdefault("AWS_ACCESS_KEY_ID", "alpr_minio")
            os.environ.setdefault("AWS_SECRET_ACCESS_KEY", "alpr_minio_secure_pass_2024")
            os.environ.setdefault("MLFLOW_S3_ENDPOINT_URL", "http://localhost:9000")

        # Initialize MLflow client if available
        self.client: Optional[MlflowClient] = None
        self._mlflow_connected = False

        if self.enable_mlflow:
            self._init_mlflow_client()

        # Ensure cache directory exists
        Path(self.cache_dir).mkdir(parents=True, exist_ok=True)

        logger.info(f"MLflowModelLoader initialized")
        logger.info(f"  MLflow enabled: {self.enable_mlflow}")
        logger.info(f"  MLflow connected: {self._mlflow_connected}")
        logger.info(f"  Tracking URI: {self.tracking_uri}")
        logger.info(f"  Fallback dir: {self.fallback_models_dir}")
        logger.info(f"  Preferred stage: {self.preferred_stage}")

    def _init_mlflow_client(self) -> None:
        """Initialize MLflow client and test connection."""
        try:
            mlflow.set_tracking_uri(self.tracking_uri)
            self.client = MlflowClient(tracking_uri=self.tracking_uri)

            # Test connection by listing registered models
            self.client.search_registered_models(max_results=1)
            self._mlflow_connected = True
            logger.success(f"Connected to MLflow at {self.tracking_uri}")

        except Exception as e:
            logger.warning(f"Failed to connect to MLflow at {self.tracking_uri}: {e}")
            logger.info("Will use local model files as fallback")
            self._mlflow_connected = False

    def get_model_path(
        self,
        model_name: str,
        fallback_filename: str,
        version: Optional[int] = None,
        stage: Optional[str] = None,
    ) -> Tuple[str, Dict[str, Any]]:
        """
        Get the path to a model, attempting MLflow first then falling back to local.

        Args:
            model_name: Registered model name in MLflow (e.g., "alpr-plate-detector")
            fallback_filename: Local filename to use if MLflow unavailable (e.g., "yolo11n-plate.pt")
            version: Specific version number to load. If None, uses latest for stage.
            stage: Model stage to load. Defaults to self.preferred_stage.

        Returns:
            Tuple of (model_path, metadata_dict)

            metadata_dict contains:
            - source: "mlflow" or "local"
            - model_name: Name of the model
            - version: Version number (MLflow only)
            - stage: Stage name (MLflow only)
            - run_id: Training run ID (MLflow only)
            - artifact_uri: MLflow artifact URI (MLflow only)
        """
        stage = stage or self.preferred_stage

        # Try MLflow first
        if self._mlflow_connected:
            try:
                path, metadata = self._load_from_mlflow(model_name, version, stage)
                if path and Path(path).exists():
                    return path, metadata
            except Exception as e:
                logger.warning(f"MLflow model load failed for {model_name}: {e}")

        # Fallback to local file
        return self._load_from_local(fallback_filename)

    def _load_from_mlflow(
        self,
        model_name: str,
        version: Optional[int] = None,
        stage: str = "Production",
    ) -> Tuple[str, Dict[str, Any]]:
        """
        Load a model from MLflow Model Registry.

        Args:
            model_name: Registered model name
            version: Specific version (optional)
            stage: Model stage to load

        Returns:
            Tuple of (local_path, metadata)
        """
        if not self.client:
            raise RuntimeError("MLflow client not initialized")

        # Get model version info
        if version is not None:
            # Load specific version
            model_version = self.client.get_model_version(model_name, str(version))
        else:
            # Get latest version for the stage
            versions = self.client.get_latest_versions(model_name, stages=[stage])
            if not versions:
                # Try without stage filter
                versions = self.client.get_latest_versions(model_name)
                if not versions:
                    raise ValueError(f"No versions found for model {model_name}")
                logger.info(f"No {stage} version found, using latest version")
            model_version = versions[0]

        logger.info(
            f"Found MLflow model: {model_name} v{model_version.version} "
            f"(stage: {model_version.current_stage})"
        )

        # Get artifact URI
        artifact_uri = model_version.source

        # Download model artifacts to cache
        cache_path = os.path.join(
            self.cache_dir,
            model_name,
            f"v{model_version.version}"
        )

        # Check if already cached
        model_files = list(Path(cache_path).glob("*.pt")) if Path(cache_path).exists() else []

        if not model_files:
            logger.info(f"Downloading model artifacts to {cache_path}")
            Path(cache_path).mkdir(parents=True, exist_ok=True)

            # Download artifacts using MLflow
            local_path = mlflow.artifacts.download_artifacts(
                artifact_uri=artifact_uri,
                dst_path=cache_path
            )

            # Find the .pt file in downloaded artifacts
            model_files = list(Path(cache_path).rglob("*.pt"))

            if not model_files:
                # Try .engine files (TensorRT)
                model_files = list(Path(cache_path).rglob("*.engine"))

        if not model_files:
            raise FileNotFoundError(f"No model files found in {cache_path}")

        # Prefer .engine over .pt if available
        engine_files = [f for f in model_files if f.suffix == ".engine"]
        pt_files = [f for f in model_files if f.suffix == ".pt"]

        if engine_files:
            model_path = str(engine_files[0])
            logger.info(f"Using TensorRT engine: {model_path}")
        elif pt_files:
            model_path = str(pt_files[0])
            logger.info(f"Using PyTorch model: {model_path}")
        else:
            model_path = str(model_files[0])

        metadata = {
            "source": "mlflow",
            "model_name": model_name,
            "version": int(model_version.version),
            "stage": model_version.current_stage,
            "run_id": model_version.run_id,
            "artifact_uri": artifact_uri,
            "description": model_version.description or "",
            "tags": dict(model_version.tags) if model_version.tags else {},
        }

        logger.success(
            f"Loaded model from MLflow: {model_name} v{model_version.version}"
        )

        return model_path, metadata

    def _load_from_local(self, filename: str) -> Tuple[str, Dict[str, Any]]:
        """
        Load a model from local filesystem.

        Args:
            filename: Model filename (e.g., "yolo11n-plate.pt")

        Returns:
            Tuple of (local_path, metadata)
        """
        # Build path from models directory
        model_path = os.path.join(self.fallback_models_dir, filename)

        if not os.path.exists(model_path):
            # Try absolute path
            if os.path.exists(filename):
                model_path = filename
            else:
                raise FileNotFoundError(
                    f"Model not found: {model_path} or {filename}"
                )

        metadata = {
            "source": "local",
            "model_name": os.path.basename(model_path),
            "path": model_path,
        }

        logger.info(f"Loaded model from local path: {model_path}")

        return model_path, metadata

    def list_models(self) -> Dict[str, Any]:
        """
        List all registered models in MLflow.

        Returns:
            Dict with model information
        """
        if not self._mlflow_connected:
            return {"error": "MLflow not connected", "models": []}

        try:
            models = self.client.search_registered_models()
            result = {
                "tracking_uri": self.tracking_uri,
                "models": []
            }

            for model in models:
                model_info = {
                    "name": model.name,
                    "description": model.description,
                    "tags": dict(model.tags) if model.tags else {},
                    "versions": []
                }

                # Get versions
                for version in self.client.search_model_versions(f"name='{model.name}'"):
                    model_info["versions"].append({
                        "version": version.version,
                        "stage": version.current_stage,
                        "status": version.status,
                        "run_id": version.run_id,
                    })

                result["models"].append(model_info)

            return result

        except Exception as e:
            return {"error": str(e), "models": []}

    def get_model_info(self, model_name: str) -> Dict[str, Any]:
        """
        Get detailed information about a specific model.

        Args:
            model_name: Name of the registered model

        Returns:
            Dict with model details
        """
        if not self._mlflow_connected:
            return {"error": "MLflow not connected"}

        try:
            model = self.client.get_registered_model(model_name)
            versions = self.client.search_model_versions(f"name='{model_name}'")

            return {
                "name": model.name,
                "description": model.description,
                "tags": dict(model.tags) if model.tags else {},
                "creation_timestamp": model.creation_timestamp,
                "last_updated_timestamp": model.last_updated_timestamp,
                "versions": [
                    {
                        "version": v.version,
                        "stage": v.current_stage,
                        "status": v.status,
                        "run_id": v.run_id,
                        "source": v.source,
                        "description": v.description,
                    }
                    for v in versions
                ]
            }

        except Exception as e:
            return {"error": str(e)}

    def clear_cache(self, model_name: Optional[str] = None) -> None:
        """
        Clear cached model files.

        Args:
            model_name: Specific model to clear, or None for all models
        """
        if model_name:
            cache_path = os.path.join(self.cache_dir, model_name)
        else:
            cache_path = self.cache_dir

        if os.path.exists(cache_path):
            shutil.rmtree(cache_path)
            logger.info(f"Cleared cache: {cache_path}")
            Path(self.cache_dir).mkdir(parents=True, exist_ok=True)


# Convenience function for quick model loading
def load_model(
    model_name: str,
    fallback_filename: str,
    tracking_uri: Optional[str] = None,
    **kwargs
) -> Tuple[str, Dict[str, Any]]:
    """
    Convenience function to load a model.

    Args:
        model_name: MLflow model name
        fallback_filename: Local fallback filename
        tracking_uri: Optional MLflow URI
        **kwargs: Additional arguments for MLflowModelLoader

    Returns:
        Tuple of (model_path, metadata)
    """
    loader = MLflowModelLoader(tracking_uri=tracking_uri, **kwargs)
    return loader.get_model_path(model_name, fallback_filename)


if __name__ == "__main__":
    # Test the model loader
    import json

    print("=" * 60)
    print("MLflow Model Loader Test")
    print("=" * 60)

    # Initialize loader
    loader = MLflowModelLoader()

    # List registered models
    print("\n--- Registered Models ---")
    models = loader.list_models()
    print(json.dumps(models, indent=2, default=str))

    # Try loading vehicle detector
    print("\n--- Loading Vehicle Detector ---")
    try:
        path, meta = loader.get_model_path(
            "alpr-vehicle-detector",
            "yolo11n.pt"
        )
        print(f"Path: {path}")
        print(f"Metadata: {json.dumps(meta, indent=2, default=str)}")
    except Exception as e:
        print(f"Error: {e}")

    # Try loading plate detector
    print("\n--- Loading Plate Detector ---")
    try:
        path, meta = loader.get_model_path(
            "alpr-plate-detector",
            "yolo11n-plate.pt"
        )
        print(f"Path: {path}")
        print(f"Metadata: {json.dumps(meta, indent=2, default=str)}")
    except Exception as e:
        print(f"Error: {e}")

    print("\n" + "=" * 60)
