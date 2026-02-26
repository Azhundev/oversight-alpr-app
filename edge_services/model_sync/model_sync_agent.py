"""
Model Sync Agent for ALPR Edge Devices

Polls MLflow Model Registry for new `champion` alias versions, downloads them,
validates integrity, swaps into the models directory, and triggers a pilot.py restart.

Offline-resilient: if MLflow is unreachable the agent logs a warning and continues
serving the existing local models unchanged.

Usage:
    python3 edge_services/model_sync/model_sync_agent.py
    python3 edge_services/model_sync/model_sync_agent.py --config config/model_sync.yaml
    python3 edge_services/model_sync/model_sync_agent.py --once   # single sync then exit
"""

import argparse
import hashlib
import json
import logging
import os
import shutil
import signal
import socket
import subprocess
import sys
import tempfile
import time
from datetime import datetime, timezone
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path
from threading import Event, Thread
from typing import Any, Dict, Optional

import yaml

try:
    import mlflow
    from mlflow.tracking import MlflowClient
    MLFLOW_AVAILABLE = True
except ImportError:
    MLFLOW_AVAILABLE = False

# Use loguru if available (consistent with rest of project), otherwise stdlib logging
try:
    from loguru import logger
except ImportError:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s | %(levelname)-8s | %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )
    logger = logging.getLogger("model_sync")


# ---------------------------------------------------------------------------
# HTTP status handler (GET /status on port 8005)
# ---------------------------------------------------------------------------

class _StatusHandler(BaseHTTPRequestHandler):
    agent: "ModelSyncAgent" = None  # set by start_status_server()

    def do_GET(self):
        if self.path == "/status":
            payload = self.agent.get_status()
            body = json.dumps(payload, indent=2).encode()
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", len(body))
            self.end_headers()
            self.wfile.write(body)
        else:
            self.send_response(404)
            self.end_headers()

    def log_message(self, format, *args):
        # Suppress default access log spam; use loguru/logger instead
        pass


# ---------------------------------------------------------------------------
# ModelSyncAgent
# ---------------------------------------------------------------------------

class ModelSyncAgent:
    """
    Background agent that keeps edge-device models in sync with MLflow.

    Poll cycle:
      1. For each configured model, call MLflow to resolve the `champion` alias.
      2. Compare returned version to manifest.json.
      3. If newer: download → staging → validate → swap → update manifest → trigger restart.
      4. If MLflow unreachable: log warning, skip, keep existing models.
    """

    def __init__(self, config_path: str = "config/model_sync.yaml"):
        self.config_path = config_path
        self.config = self._load_config(config_path)
        self._stop_event = Event()
        self._mlflow_connected = False
        self.client: Optional[MlflowClient] = None
        self.manifest: Dict[str, Any] = {}
        self._last_sync: Optional[str] = None
        self._status_server: Optional[HTTPServer] = None

        # Resolve key paths
        cfg = self.config["model_sync"]
        self.models_dir = Path(cfg.get("models_dir", "models"))
        self.manifest_path = Path(cfg.get("manifest_path", "models/manifest.json"))
        self.staging_dir = self.models_dir / "staging"

        # Set MinIO/S3 credentials for MLflow artifact access (same as mlflow_model_loader.py)
        os.environ.setdefault("AWS_ACCESS_KEY_ID", "alpr_minio")
        os.environ.setdefault("AWS_SECRET_ACCESS_KEY", "alpr_minio_secure_pass_2024")
        os.environ.setdefault("MLFLOW_S3_ENDPOINT_URL", "http://localhost:9000")

        self.models_dir.mkdir(parents=True, exist_ok=True)
        self.staging_dir.mkdir(parents=True, exist_ok=True)
        self.manifest = self._load_manifest()
        self._init_mlflow_client()

    # ------------------------------------------------------------------
    # Config / manifest helpers
    # ------------------------------------------------------------------

    def _load_config(self, path: str) -> Dict[str, Any]:
        config_path = Path(path)
        if not config_path.exists():
            raise FileNotFoundError(f"Config not found: {path}")
        with open(config_path) as f:
            return yaml.safe_load(f)

    def _load_manifest(self) -> Dict[str, Any]:
        if self.manifest_path.exists():
            try:
                with open(self.manifest_path) as f:
                    return json.load(f)
            except Exception as e:
                logger.warning(f"Could not read manifest ({e}), starting fresh")
        return {
            "device_id": self._device_id(),
            "last_sync": None,
            "models": {},
        }

    def _save_manifest(self) -> None:
        self.manifest["last_sync"] = datetime.now(timezone.utc).isoformat()
        self.manifest_path.parent.mkdir(parents=True, exist_ok=True)
        tmp = self.manifest_path.with_suffix(".tmp")
        with open(tmp, "w") as f:
            json.dump(self.manifest, f, indent=2)
        tmp.replace(self.manifest_path)

    def _device_id(self) -> str:
        cfg = self.config["model_sync"]
        reporting = cfg.get("reporting", {})
        did = reporting.get("device_id") if reporting else None
        return did or socket.gethostname()

    # ------------------------------------------------------------------
    # MLflow client
    # ------------------------------------------------------------------

    def _init_mlflow_client(self) -> None:
        if not MLFLOW_AVAILABLE:
            logger.warning("MLflow not installed — sync disabled, using local models")
            return
        uri = self.config["model_sync"]["mlflow_uri"]
        try:
            mlflow.set_tracking_uri(uri)
            self.client = MlflowClient(tracking_uri=uri)
            self.client.search_registered_models(max_results=1)
            self._mlflow_connected = True
            logger.info(f"Connected to MLflow at {uri}")
        except Exception as e:
            logger.warning(f"MLflow unreachable at {uri}: {e}")
            self._mlflow_connected = False

    def _reconnect_if_needed(self) -> bool:
        """Try to reconnect to MLflow if not currently connected."""
        if self._mlflow_connected:
            return True
        self._init_mlflow_client()
        return self._mlflow_connected

    # ------------------------------------------------------------------
    # Main loop
    # ------------------------------------------------------------------

    def run(self) -> None:
        cfg = self.config["model_sync"]
        poll_interval = cfg.get("poll_interval_seconds", 3600)
        status_port = cfg.get("status_port", 8005)

        logger.info("Model Sync Agent starting")
        logger.info(f"  Poll interval : {poll_interval}s")
        logger.info(f"  Alias tracked : {cfg.get('alias', 'champion')}")
        logger.info(f"  Models dir    : {self.models_dir}")
        logger.info(f"  Manifest      : {self.manifest_path}")
        logger.info(f"  Status port   : {status_port}")

        self._start_status_server(status_port)

        # Initial sync immediately on startup
        self.sync_all_models()

        while not self._stop_event.is_set():
            self._stop_event.wait(poll_interval)
            if not self._stop_event.is_set():
                self.sync_all_models()

    def run_once(self) -> None:
        """Perform a single sync cycle (for testing / one-shot use)."""
        self.sync_all_models()

    def stop(self) -> None:
        logger.info("Stopping Model Sync Agent")
        self._stop_event.set()
        if self._status_server:
            self._status_server.shutdown()

    # ------------------------------------------------------------------
    # Sync logic
    # ------------------------------------------------------------------

    def sync_all_models(self) -> None:
        cfg = self.config["model_sync"]
        models_cfg = cfg.get("models", [])

        if not self._reconnect_if_needed():
            logger.warning("MLflow unreachable — skipping sync cycle, keeping existing models")
            return

        updated = False
        for model_cfg in models_cfg:
            try:
                changed = self.sync_model(model_cfg)
                if changed:
                    updated = True
            except Exception as e:
                logger.error(f"Sync failed for {model_cfg.get('mlflow_name', '?')}: {e}")

        if updated:
            self._trigger_restart()

        self._last_sync = datetime.now(timezone.utc).isoformat()
        self._save_manifest()
        self._report_status()

    def sync_model(self, model_cfg: Dict[str, Any]) -> bool:
        """
        Check one model against the registry and update if a newer champion exists.

        Returns True if the model was updated.
        """
        mlflow_name = model_cfg["mlflow_name"]
        local_filename = model_cfg["local_filename"]
        alias = self.config["model_sync"].get("alias", "champion")

        logger.info(f"Checking {mlflow_name} (alias={alias})")

        registry_version = self._get_registry_version(mlflow_name, alias)
        if registry_version is None:
            logger.warning(f"No {alias} version found for {mlflow_name} — skipping")
            return False

        reg_ver_num = int(registry_version.version)
        manifest_entry = self.manifest.get("models", {}).get(local_filename, {})
        local_ver_num = manifest_entry.get("version")

        if local_ver_num is not None and local_ver_num >= reg_ver_num:
            logger.info(f"{mlflow_name}: local v{local_ver_num} is current (registry v{reg_ver_num})")
            return False

        logger.info(
            f"{mlflow_name}: new version available "
            f"(local={local_ver_num or 'none'} → registry={reg_ver_num})"
        )

        # Download to staging
        staging_path = self._download_model(mlflow_name, registry_version)
        if staging_path is None:
            return False

        # Validate
        if not self._validate_model(staging_path):
            logger.error(f"Validation failed for {staging_path} — keeping existing model")
            staging_path.unlink(missing_ok=True)
            return False

        # Atomic swap into models directory
        dest = self.models_dir / local_filename
        backup = dest.with_suffix(dest.suffix + ".bak") if dest.exists() else None
        try:
            if backup:
                shutil.copy2(dest, backup)
            shutil.move(str(staging_path), str(dest))
            if backup and backup.exists():
                backup.unlink()
            logger.info(f"Model updated: {dest}")
        except Exception as e:
            logger.error(f"Failed to swap model into place: {e}")
            if backup and backup.exists():
                shutil.move(str(backup), str(dest))
            staging_path.unlink(missing_ok=True)
            return False

        # Write flag file
        on_update = self.config["model_sync"].get("on_update", {})
        flag_file = on_update.get("flag_file")
        if flag_file:
            Path(flag_file).touch()

        # Update manifest
        self.manifest.setdefault("models", {})[local_filename] = {
            "mlflow_name": mlflow_name,
            "version": reg_ver_num,
            "alias": alias,
            "downloaded_at": datetime.now(timezone.utc).isoformat(),
            "run_id": registry_version.run_id,
        }

        logger.info(f"Manifest updated for {local_filename} → v{reg_ver_num}")
        return True

    # ------------------------------------------------------------------
    # MLflow helpers
    # ------------------------------------------------------------------

    def _get_registry_version(self, model_name: str, alias: str):
        """Resolve alias to a ModelVersion using MLflow 3.x API."""
        if not self.client:
            return None
        try:
            return self.client.get_model_version_by_alias(model_name, alias)
        except Exception as e:
            logger.warning(f"Could not resolve alias '{alias}' for {model_name}: {e}")
            return None

    def _download_model(self, model_name: str, model_version) -> Optional[Path]:
        """Download model artifacts to staging directory. Returns path to model file."""
        ver_num = model_version.version
        artifact_uri = model_version.source

        staging_subdir = self.staging_dir / model_name / f"v{ver_num}"
        staging_subdir.mkdir(parents=True, exist_ok=True)

        logger.info(f"Downloading {model_name} v{ver_num} from {artifact_uri}")
        try:
            mlflow.artifacts.download_artifacts(
                artifact_uri=artifact_uri,
                dst_path=str(staging_subdir),
            )
        except Exception as e:
            logger.error(f"Download failed for {model_name} v{ver_num}: {e}")
            shutil.rmtree(staging_subdir, ignore_errors=True)
            return None

        # Find model file: prefer .engine (TensorRT), then .pt
        engine_files = list(staging_subdir.rglob("*.engine"))
        pt_files = list(staging_subdir.rglob("*.pt"))
        candidates = engine_files or pt_files

        if not candidates:
            logger.error(f"No .engine or .pt file found in {staging_subdir}")
            shutil.rmtree(staging_subdir, ignore_errors=True)
            return None

        model_file = candidates[0]
        logger.info(f"Downloaded: {model_file}")
        return model_file

    # ------------------------------------------------------------------
    # Validation
    # ------------------------------------------------------------------

    def _validate_model(self, path: Path) -> bool:
        """
        Basic model validation:
        1. File exists and has non-zero size.
        2. For .pt files: check PyTorch magic bytes (PK zip header).
        3. For .engine files: check file size > 1 MB (TensorRT engines are large).
        """
        if not path.exists():
            logger.error(f"Validation: file does not exist: {path}")
            return False

        size = path.stat().st_size
        if size == 0:
            logger.error(f"Validation: file is empty: {path}")
            return False

        suffix = path.suffix.lower()

        if suffix == ".pt":
            # PyTorch checkpoint files are zip archives — check PK magic bytes
            with open(path, "rb") as f:
                header = f.read(4)
            if header[:2] != b"PK":
                logger.error(f"Validation: {path} does not appear to be a valid .pt file")
                return False

        elif suffix == ".engine":
            if size < 1_000_000:
                logger.error(f"Validation: .engine file suspiciously small ({size} bytes): {path}")
                return False

        logger.info(f"Validation passed: {path} ({size / 1e6:.1f} MB)")
        return True

    # ------------------------------------------------------------------
    # Restart trigger
    # ------------------------------------------------------------------

    def _trigger_restart(self) -> None:
        on_update = self.config["model_sync"].get("on_update", {})
        if not on_update.get("restart_pilot", True):
            logger.info("Restart disabled by config — models updated, no restart triggered")
            return

        restart_cmd = on_update.get("restart_command", "systemctl restart alpr-pilot")
        logger.info(f"Triggering pilot restart: {restart_cmd}")

        try:
            result = subprocess.run(
                restart_cmd.split(),
                capture_output=True,
                text=True,
                timeout=30,
            )
            if result.returncode == 0:
                logger.info("Pilot restart succeeded")
            else:
                logger.warning(
                    f"Restart command returned {result.returncode}: {result.stderr.strip()}"
                )
                # Fallback: send SIGTERM to any running pilot.py process
                self._sigterm_pilot_fallback()
        except FileNotFoundError:
            logger.warning(f"Restart command not found: {restart_cmd.split()[0]}")
            self._sigterm_pilot_fallback()
        except subprocess.TimeoutExpired:
            logger.error("Restart command timed out")

    def _sigterm_pilot_fallback(self) -> None:
        """Send SIGTERM to pilot.py; systemd with Restart=always will restart it."""
        try:
            result = subprocess.run(
                ["pgrep", "-f", "pilot.py"],
                capture_output=True,
                text=True,
            )
            pids = result.stdout.strip().split()
            for pid_str in pids:
                pid = int(pid_str)
                os.kill(pid, signal.SIGTERM)
                logger.info(f"Sent SIGTERM to pilot.py (PID {pid})")
        except Exception as e:
            logger.warning(f"SIGTERM fallback failed: {e}")

    # ------------------------------------------------------------------
    # Status HTTP server
    # ------------------------------------------------------------------

    def _start_status_server(self, port: int) -> None:
        _StatusHandler.agent = self

        def _serve():
            try:
                self._status_server = HTTPServer(("", port), _StatusHandler)
                logger.info(f"Status endpoint: http://localhost:{port}/status")
                self._status_server.serve_forever()
            except Exception as e:
                logger.warning(f"Status server could not start on port {port}: {e}")

        t = Thread(target=_serve, daemon=True)
        t.start()

    def get_status(self) -> Dict[str, Any]:
        """Return current agent status (served via /status endpoint)."""
        cfg = self.config["model_sync"]
        return {
            "device_id": self._device_id(),
            "mlflow_uri": cfg.get("mlflow_uri"),
            "mlflow_connected": self._mlflow_connected,
            "alias": cfg.get("alias", "champion"),
            "last_sync": self._last_sync,
            "models": self.manifest.get("models", {}),
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }

    # ------------------------------------------------------------------
    # Optional portal reporting
    # ------------------------------------------------------------------

    def _report_status(self) -> None:
        cfg = self.config["model_sync"]
        reporting = cfg.get("reporting", {})
        if not reporting or not reporting.get("enabled"):
            return

        endpoint = reporting.get("endpoint")
        api_key = reporting.get("api_key")
        if not endpoint:
            return

        try:
            import urllib.request
            payload = json.dumps(self.get_status()).encode()
            req = urllib.request.Request(
                endpoint,
                data=payload,
                headers={
                    "Content-Type": "application/json",
                    "X-API-Key": api_key or "",
                },
                method="POST",
            )
            with urllib.request.urlopen(req, timeout=10) as resp:
                logger.info(f"Status reported to portal: HTTP {resp.status}")
        except Exception as e:
            logger.warning(f"Portal reporting failed: {e}")


# ---------------------------------------------------------------------------
# CLI entry point
# ---------------------------------------------------------------------------

def _parse_args():
    p = argparse.ArgumentParser(description="ALPR Model Sync Agent")
    p.add_argument(
        "--config",
        default="config/model_sync.yaml",
        help="Path to model_sync.yaml (default: config/model_sync.yaml)",
    )
    p.add_argument(
        "--once",
        action="store_true",
        help="Run a single sync cycle then exit (useful for cron / testing)",
    )
    return p.parse_args()


def main():
    args = _parse_args()
    agent = ModelSyncAgent(config_path=args.config)

    if args.once:
        agent.run_once()
        return

    # Handle SIGTERM/SIGINT gracefully
    def _handle_signal(signum, frame):
        logger.info(f"Received signal {signum}, shutting down")
        agent.stop()
        sys.exit(0)

    signal.signal(signal.SIGTERM, _handle_signal)
    signal.signal(signal.SIGINT, _handle_signal)

    agent.run()


if __name__ == "__main__":
    main()
