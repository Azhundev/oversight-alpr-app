# Model Sync Agent

**Service:** `alpr-model-sync`
**Port:** 8005 (status endpoint)
**Unit:** `scripts/systemd/alpr-model-sync.service`
**Config:** `config/model_sync.yaml`

The Model Sync Agent is a background service that automatically distributes new model versions to edge devices. It polls the MLflow Model Registry for models tagged with the `champion` alias, downloads them, validates integrity, and swaps them into the active `models/` directory — then restarts the ALPR pipeline to pick them up.

---

## Quick Start

```bash
# One-shot sync (useful for testing)
python3 edge_services/model_sync/model_sync_agent.py --once

# Run as a daemon
python3 edge_services/model_sync/model_sync_agent.py

# Custom config path
python3 edge_services/model_sync/model_sync_agent.py --config config/model_sync.yaml

# Check status
curl http://localhost:8005/status
```

---

## Architecture

```
MLflow Model Registry (localhost:5000)
         │
         │  poll every N minutes
         │  resolve alias → "champion"
         ▼
  ModelSyncAgent
         │
         ├── compare version to models/manifest.json
         │
         ├── if up to date → skip, log, sleep
         │
         └── if newer version found:
               │
               ├── download artifacts → models/staging/
               │   (MLflow → MinIO → local file)
               │
               ├── validate file
               │   .pt  → check PK magic bytes (zip header)
               │   .engine → check file size > 1 MB
               │
               ├── atomic swap → models/<filename>
               │   (backup old → move new → remove backup)
               │
               ├── update models/manifest.json
               │
               ├── write models/.update-pending flag (optional)
               │
               └── trigger restart
                     primary:  systemctl restart alpr-pilot
                     fallback: SIGTERM to pilot.py PID
                               (systemd Restart=always handles the rest)
```

---

## Configuration (`config/model_sync.yaml`)

```yaml
model_sync:
  poll_interval_seconds: 3600   # how often to check MLflow
  mlflow_uri: "http://localhost:5000"
  alias: "champion"             # only versions with this alias are downloaded

  models_dir: "models"

  models:
    - mlflow_name: "alpr-florida-plate-detector"
      local_filename: "yolo11n-plate.pt"
    - mlflow_name: "alpr-vehicle-detector"
      local_filename: "yolo11n.pt"

  manifest_path: "models/manifest.json"

  on_update:
    restart_pilot: true
    restart_command: "systemctl restart alpr-pilot"
    flag_file: "models/.update-pending"

  reporting:
    enabled: false              # Phase 2: portal reporting
    endpoint: null
    device_id: null             # auto-detected from hostname
    api_key: null

  status_port: 8005
```

### Adding a model

Add an entry to `models:` in `config/model_sync.yaml`:

```yaml
- mlflow_name: "alpr-vehicle-classifier"
  local_filename: "yolo11n-vehicle.pt"
```

The agent picks up config changes on the next poll cycle (no restart required).

---

## Manifest (`models/manifest.json`)

Written by the agent after each successful update. Do not edit manually.

```json
{
  "device_id": "jetson-site-001",
  "last_sync": "2026-02-25T21:00:00Z",
  "models": {
    "yolo11n-plate.pt": {
      "mlflow_name": "alpr-florida-plate-detector",
      "version": 3,
      "alias": "champion",
      "downloaded_at": "2026-02-25T21:00:00Z",
      "run_id": "e8d5ef84a1b2c3d4e5f6..."
    }
  }
}
```

The manifest always reflects what is actually on disk. If a download fails mid-transfer, the manifest is not updated and the previous model remains active.

---

## Status Endpoint

`GET http://localhost:8005/status`

```json
{
  "device_id": "jetson-site-001",
  "mlflow_uri": "http://localhost:5000",
  "mlflow_connected": true,
  "alias": "champion",
  "last_sync": "2026-02-25T21:00:00Z",
  "models": {
    "yolo11n-plate.pt": {
      "mlflow_name": "alpr-florida-plate-detector",
      "version": 3,
      "alias": "champion",
      "downloaded_at": "2026-02-25T21:00:00Z",
      "run_id": "e8d5ef84..."
    }
  },
  "timestamp": "2026-02-25T22:15:00Z"
}
```

---

## Systemd Installation

### 1. Copy unit files

```bash
sudo cp scripts/systemd/alpr-pilot.service /etc/systemd/system/
sudo cp scripts/systemd/alpr-model-sync.service /etc/systemd/system/
sudo systemctl daemon-reload
```

### 2. Grant sudo for restart command

Add to `/etc/sudoers` via `sudo visudo`:

```
jetson ALL=(ALL) NOPASSWD: /bin/systemctl restart alpr-pilot
jetson ALL=(ALL) NOPASSWD: /bin/systemctl stop alpr-pilot
jetson ALL=(ALL) NOPASSWD: /bin/systemctl start alpr-pilot
```

### 3. Enable and start

```bash
sudo systemctl enable alpr-pilot alpr-model-sync
sudo systemctl start alpr-pilot
sudo systemctl start alpr-model-sync
```

### 4. Verify

```bash
# Check both services are running
systemctl status alpr-pilot alpr-model-sync

# Follow sync agent logs
journalctl -u alpr-model-sync -f

# Follow pilot logs
journalctl -u alpr-pilot -f

# Check status endpoint
curl http://localhost:8005/status
```

---

## Deploying a New Model

This is the normal workflow after retraining:

```bash
# 1. Train and register (on the training machine)
python scripts/training/train_with_mlflow.py --data plates.yaml --epochs 100

# 2. Promote to champion in MLflow UI or via CLI
mlflow models set-model-alias \
    --model-name alpr-florida-plate-detector \
    --alias champion \
    --version 4

# 3. Wait for next poll cycle (or trigger immediately)
python3 edge_services/model_sync/model_sync_agent.py --once

# 4. Confirm update on device
cat models/manifest.json
curl http://localhost:8005/status
```

The agent handles the rest: download, validate, swap, restart. No SSH to the device required.

---

## Offline Resilience

| Failure scenario | Behaviour |
|---|---|
| MLflow unreachable | Log warning, skip sync cycle, keep existing models, retry next poll |
| Download fails mid-transfer | Discard partial file in staging, keep previous model, manifest unchanged |
| Validation fails | Discard downloaded file, keep previous model, log error |
| Swap fails (disk full, permissions) | Restore backup, log error, manifest unchanged |
| `systemctl restart` not available | Fall back to `SIGTERM` to pilot PID; systemd auto-restarts |

The local model files are never overwritten unless a full download + validation succeeds.

---

## Troubleshooting

**Agent starts but no sync happens**

- Confirm MLflow is reachable: `curl http://localhost:5000/health`
- Confirm at least one model has the `champion` alias set in MLflow UI
- Check `mlflow_name` values in `config/model_sync.yaml` exactly match the registered model names in MLflow

**`systemctl restart alpr-pilot` fails with permission denied**

- Add the sudoers entry shown in the installation section
- Or set `restart_command: ""` and `restart_pilot: false` to disable the restart trigger (update the flag file only)

**Staging files left behind**

- `models/staging/` accumulates downloaded artifacts; safe to delete between syncs:
  ```bash
  rm -rf models/staging/
  ```

**Manifest out of sync with actual files**

- Delete `models/manifest.json` and run `--once`; the agent will re-download all champion versions and rebuild the manifest

---

## Related

- `edge_services/detector/mlflow_model_loader.py` — loads models from MLflow at pilot startup (complementary to sync agent)
- `scripts/mlflow/register_existing_models.py` — one-time registration of existing model files
- `scripts/training/train_with_mlflow.py` — training with MLflow experiment tracking
- `docs/services/MLFlow/mlflow-model-registry.md` — MLflow registry overview
- `docs/services/MLFlow/model-training-guide.md` — training workflow
