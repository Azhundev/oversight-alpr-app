"""
Model Sync Agent package for ALPR edge devices.
Polls MLflow for new champion model versions and automatically updates local models.
"""

from .model_sync_agent import ModelSyncAgent

__all__ = ["ModelSyncAgent"]
