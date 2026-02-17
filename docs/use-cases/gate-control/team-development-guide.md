# Team Development Guide (Without Jetson)

**Created:** 2026-02-17
**Purpose:** Development options for team members without Jetson hardware
**Related:** [GitHub Setup Guide](github-setup-guide.md) | [Project Structure](project-structure.md)

---

## Table of Contents

1. [Overview](#overview)
2. [Development Options](#development-options)
3. [CPU Mode](#cpu-mode)
4. [Mock/Simulation Mode](#mocksimulation-mode)
5. [Cloud GPU (On-Demand)](#cloud-gpu-on-demand)
6. [Remote Access to Jetson](#remote-access-to-jetson)
7. [Unit Tests Without GPU](#unit-tests-without-gpu)
8. [Recommended Team Setup](#recommended-team-setup)
9. [Configuration Examples](#configuration-examples)

---

## Overview

Not everyone on the team needs a Jetson device. Most development work (API, database, business logic, dashboard) doesn't require GPU inference at all.

```
WHAT NEEDS GPU vs WHAT DOESN'T
══════════════════════════════════════════════════════════════════

REQUIRES GPU/JETSON (10% of code)          NO GPU NEEDED (90% of code)
─────────────────────────────────          ─────────────────────────────
• YOLOv11 inference                        • API endpoints
• TensorRT optimization                    • Database operations
• Real-time camera processing              • Whitelist/blacklist logic
• Performance benchmarking                 • Gate control logic
                                           • Dashboard/frontend
                                           • Email/SMS alerts
                                           • License validation
                                           • Configuration management
                                           • Unit tests
                                           • Integration tests (mocked)
```

---

## Development Options

| Option | Speed | Cost | Best For |
|--------|-------|------|----------|
| **CPU Mode** | Slow (1-2 FPS) | Free | Full pipeline testing |
| **Mock Mode** | Fast | Free | Business logic, API development |
| **Cloud GPU** | Fast | ~$0.50/hr | Occasional integration testing |
| **Remote Jetson** | Fast | Free | Final validation |
| **Unit Tests** | Instant | Free | Most development work |

---

## CPU Mode

YOLOv11 and PaddleOCR run on CPU - just much slower than GPU.

### Performance Comparison

| Device | FPS | Latency |
|--------|-----|---------|
| Jetson Orin Nano (GPU) | 25-30 FPS | ~40ms |
| Laptop CPU (i7) | 1-2 FPS | ~500-1000ms |
| Cloud CPU (4 vCPU) | 0.5-1 FPS | ~1000-2000ms |

### Setup

```bash
# Install without GPU dependencies
pip install ultralytics paddleocr paddlepaddle opencv-python

# Or install the project in CPU mode
pip install -e "."  # No [gpu] extras
```

### Running in CPU Mode

```python
# src/alpr_edge/core/detector.py
from ultralytics import YOLO

class PlateDetector:
    def __init__(self, model_path: str, device: str = "cpu"):
        # device="cpu" forces CPU inference
        # device="cuda" or device=0 uses GPU
        self.model = YOLO(model_path)
        self.device = device

    def detect(self, frame):
        results = self.model.predict(
            frame,
            device=self.device,
            verbose=False
        )
        return results
```

### Environment Variable

```bash
# Force CPU mode
export ALPR_DEVICE=cpu

# Or in .env file
ALPR_DEVICE=cpu
```

```python
# config.py
import os

class Settings:
    device: str = os.getenv("ALPR_DEVICE", "cuda")  # Default GPU, override with env
```

### When to Use

- Testing the complete pipeline end-to-end
- Debugging detection/OCR issues
- Developing camera ingestion code
- Testing with real video files

---

## Mock/Simulation Mode

Use pre-recorded data instead of live inference. This is the fastest option for development.

### Mock Detector

```python
# src/alpr_edge/core/detector.py

class MockPlateDetector:
    """Mock detector for testing without GPU."""

    def __init__(self):
        self.mock_results = [
            {"plate": "ABC123", "confidence": 0.95, "bbox": [100, 100, 200, 150]},
            {"plate": "XYZ789", "confidence": 0.92, "bbox": [150, 120, 250, 170]},
            {"plate": "DEF456", "confidence": 0.88, "bbox": [120, 110, 220, 160]},
        ]
        self.index = 0

    def detect(self, frame):
        # Cycle through mock results
        result = self.mock_results[self.index % len(self.mock_results)]
        self.index += 1
        return result


def get_detector(mock: bool = False):
    """Factory function to get real or mock detector."""
    if mock:
        return MockPlateDetector()
    else:
        return PlateDetector("models/yolo11n-plate.pt")
```

### Demo Mode Flag

```python
# src/alpr_edge/main.py
import argparse

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--demo", action="store_true", help="Run in demo mode with mock data")
    parser.add_argument("--dev", action="store_true", help="Development mode")
    args = parser.parse_args()

    if args.demo:
        detector = MockPlateDetector()
        camera = MockCameraSource("samples/test_video.mp4")
    else:
        detector = PlateDetector("models/yolo11n-plate.pt")
        camera = CameraManager(config.cameras)
```

### Sample Test Videos

Create a `samples/` directory with test videos:

```
samples/
├── test_video.mp4          # General test video
├── entry_sequence.mp4      # Car entering gate
├── exit_sequence.mp4       # Car exiting
├── multiple_plates.mp4     # Multiple cars
├── night_vision.mp4        # IR camera footage
└── plates/                 # Individual plate images
    ├── ABC123.jpg
    ├── XYZ789.jpg
    └── DEF456.jpg
```

### Mock Camera Source

```python
# src/alpr_edge/core/camera.py
import cv2

class MockCameraSource:
    """Play video file instead of live RTSP."""

    def __init__(self, video_path: str, loop: bool = True):
        self.video_path = video_path
        self.loop = loop
        self.cap = cv2.VideoCapture(video_path)

    def read(self):
        ret, frame = self.cap.read()
        if not ret and self.loop:
            self.cap.set(cv2.CAP_PROP_POS_FRAMES, 0)
            ret, frame = self.cap.read()
        return ret, frame

    def release(self):
        self.cap.release()
```

### When to Use

- API development
- Dashboard development
- Business logic testing
- Fast iteration cycles
- CI/CD pipelines

---

## Cloud GPU (On-Demand)

Spin up a GPU instance for testing, shut down when done.

### Cloud Options

| Provider | Instance | GPU | Cost/Hour | Best For |
|----------|----------|-----|-----------|----------|
| **AWS** | g4dn.xlarge | T4 | ~$0.50 | Occasional testing |
| **Google Cloud** | n1-standard-4 + T4 | T4 | ~$0.45 | Quick tests |
| **Lambda Labs** | gpu_1x_a10 | A10 | ~$0.60 | ML development |
| **Vast.ai** | Various | Various | ~$0.20+ | Budget option |

### AWS Quick Setup

```bash
# Launch GPU instance
aws ec2 run-instances \
  --image-id ami-0123456789abcdef0 \  # Ubuntu 22.04 with CUDA
  --instance-type g4dn.xlarge \
  --key-name your-key \
  --security-groups allow-ssh

# SSH and setup
ssh -i your-key.pem ubuntu@<instance-ip>

# Install dependencies
pip install ultralytics paddleocr paddlepaddle-gpu

# Clone and test
git clone git@github.com:your-org/alpr-edge.git
cd alpr-edge
pip install -e ".[gpu]"
pytest tests/

# IMPORTANT: Stop instance when done!
aws ec2 stop-instances --instance-ids i-1234567890abcdef0
```

### GitHub Actions with GPU (Limited)

```yaml
# .github/workflows/gpu-test.yml
# Note: GitHub doesn't offer GPU runners by default
# Use self-hosted runner or third-party GPU CI

name: GPU Tests

on:
  workflow_dispatch:  # Manual trigger only (saves cost)

jobs:
  gpu-test:
    runs-on: self-hosted-gpu  # Your GPU runner
    steps:
      - uses: actions/checkout@v4
      - name: Run GPU tests
        run: |
          pytest tests/integration/ -v -m "gpu"
```

### When to Use

- Integration testing with real inference
- Performance benchmarking
- Testing TensorRT exports
- Pre-release validation

---

## Remote Access to Jetson

Share the Jetson with the team for final testing.

### Option A: Cloudflare Tunnel (Recommended)

```bash
# On Jetson - one-time setup
wget https://github.com/cloudflare/cloudflared/releases/latest/download/cloudflared-linux-arm64
chmod +x cloudflared-linux-arm64
sudo mv cloudflared-linux-arm64 /usr/local/bin/cloudflared

# Login and create tunnel
cloudflared tunnel login
cloudflared tunnel create alpr-dev

# Create config
cat > ~/.cloudflared/config.yml << EOF
tunnel: alpr-dev
credentials-file: /home/jetson/.cloudflared/<tunnel-id>.json

ingress:
  - hostname: alpr-ssh.yourdomain.com
    service: ssh://localhost:22
  - hostname: alpr-api.yourdomain.com
    service: http://localhost:8000
  - service: http_status:404
EOF

# Run as service
sudo cloudflared service install
sudo systemctl start cloudflared
```

Team members connect:
```bash
# SSH through tunnel
ssh jetson@alpr-ssh.yourdomain.com

# Or access API directly
curl https://alpr-api.yourdomain.com/health
```

### Option B: Tailscale VPN

```bash
# On Jetson
curl -fsSL https://tailscale.com/install.sh | sh
sudo tailscale up

# Note the Tailscale IP (e.g., 100.x.y.z)

# Team members install Tailscale, join same network
# Then SSH directly
ssh jetson@100.x.y.z
```

### Option C: VS Code Remote SSH

Team members can develop directly on the Jetson:

1. Install VS Code + Remote SSH extension
2. Add Jetson to SSH config
3. Connect and develop as if local

```
# ~/.ssh/config
Host jetson-dev
    HostName alpr-ssh.yourdomain.com  # Or Tailscale IP
    User jetson
    IdentityFile ~/.ssh/id_rsa
```

### Shared Development Environment

```bash
# Create team workspace on Jetson
sudo mkdir -p /opt/alpr-dev
sudo chown jetson:jetson /opt/alpr-dev

# Clone repo there
cd /opt/alpr-dev
git clone git@github.com:your-org/alpr-edge.git

# Each team member works on branches
git checkout -b feature/johns-feature
```

### When to Use

- Final integration testing
- Performance validation
- Testing with real cameras
- Demo preparation

---

## Unit Tests Without GPU

Most code can be tested without any inference.

### Test Structure

```
tests/
├── unit/                      # No GPU needed
│   ├── test_access_list.py    # Whitelist/blacklist logic
│   ├── test_gate_controller.py # Gate trigger logic
│   ├── test_api_endpoints.py  # API routes
│   ├── test_license.py        # License validation
│   ├── test_config.py         # Configuration loading
│   └── test_alerts.py         # Email/SMS logic
│
├── integration/               # May need GPU or mocks
│   ├── test_pipeline.py       # Full pipeline (use mocks)
│   └── test_database.py       # DB operations
│
└── e2e/                       # Needs Jetson
    └── test_full_system.py    # Real hardware tests
```

### Mocking Inference

```python
# tests/unit/test_gate_controller.py
import pytest
from unittest.mock import Mock, patch

from alpr_edge.modules.gate.controller import GateController
from alpr_edge.modules.gate.access_list import AccessList

class TestGateController:

    def test_whitelist_opens_gate(self):
        # No GPU needed - testing business logic only
        access_list = AccessList()
        access_list.add_to_whitelist("ABC123", owner="John")

        controller = GateController(access_list)

        # Mock the actual GPIO/HTTP call
        with patch.object(controller, '_trigger_gate') as mock_trigger:
            result = controller.check_and_act("ABC123")

            assert result.allowed == True
            assert result.reason == "whitelist"
            mock_trigger.assert_called_once()

    def test_blacklist_denies_and_alerts(self):
        access_list = AccessList()
        access_list.add_to_blacklist("BAD999", reason="Stolen")

        controller = GateController(access_list)

        with patch.object(controller, '_send_alert') as mock_alert:
            result = controller.check_and_act("BAD999")

            assert result.allowed == False
            assert result.reason == "blacklist"
            mock_alert.assert_called_once()
```

### Mocking the Detector

```python
# tests/unit/test_pipeline.py
import pytest
from unittest.mock import Mock

from alpr_edge.core.pipeline import Pipeline

@pytest.fixture
def mock_detector():
    detector = Mock()
    detector.detect.return_value = {
        "plate": "ABC123",
        "confidence": 0.95,
        "bbox": [100, 100, 200, 150]
    }
    return detector

@pytest.fixture
def mock_ocr():
    ocr = Mock()
    ocr.read.return_value = ("ABC123", 0.95)
    return ocr

def test_pipeline_processes_frame(mock_detector, mock_ocr):
    pipeline = Pipeline(
        detector=mock_detector,
        ocr=mock_ocr,
        tracker=Mock()
    )

    frame = Mock()  # Fake frame
    result = pipeline.process(frame)

    assert result.plate == "ABC123"
    mock_detector.detect.assert_called_once_with(frame)
```

### Pytest Markers

```python
# conftest.py
import pytest

def pytest_configure(config):
    config.addinivalue_line("markers", "gpu: tests requiring GPU")
    config.addinivalue_line("markers", "jetson: tests requiring Jetson hardware")
    config.addinivalue_line("markers", "slow: slow running tests")
```

```python
# tests/integration/test_detector.py
import pytest

@pytest.mark.gpu
def test_detector_inference():
    """This test only runs when GPU is available."""
    detector = PlateDetector("models/yolo11n-plate.pt", device="cuda")
    # ...

@pytest.mark.jetson
def test_gpio_control():
    """This test only runs on Jetson hardware."""
    import Jetson.GPIO as GPIO
    # ...
```

Run tests selectively:
```bash
# Run only unit tests (no GPU)
pytest tests/unit/ -v

# Skip GPU tests
pytest -v -m "not gpu"

# Run GPU tests only (on Jetson or cloud GPU)
pytest -v -m "gpu"
```

---

## Recommended Team Setup

### Development Workflow by Role

```
TEAM SETUP
══════════════════════════════════════════════════════════════════

┌─────────────────────────────────────────────────────────────────┐
│  BACKEND DEVELOPERS                                              │
│  ─────────────────────                                          │
│  Environment: Laptop (Mac/Linux/Windows)                        │
│  Mode: Mock + Unit Tests                                        │
│  Focus: API, database, business logic, alerts                   │
│                                                                  │
│  Daily workflow:                                                 │
│  1. git pull                                                     │
│  2. Run unit tests: pytest tests/unit/                          │
│  3. Start API in mock mode: python -m alpr_edge.main --demo     │
│  4. Test with Postman/curl                                       │
│  5. Push changes                                                 │
└─────────────────────────────────────────────────────────────────┘

┌─────────────────────────────────────────────────────────────────┐
│  FRONTEND DEVELOPERS                                             │
│  ───────────────────                                            │
│  Environment: Laptop                                             │
│  Mode: Mock API responses                                        │
│  Focus: Dashboard, UI components                                 │
│                                                                  │
│  Daily workflow:                                                 │
│  1. Start mock API server                                        │
│  2. Develop dashboard locally                                    │
│  3. Use sample data/mock responses                               │
└─────────────────────────────────────────────────────────────────┘

┌─────────────────────────────────────────────────────────────────┐
│  ML/DETECTION DEVELOPER (You)                                    │
│  ─────────────────────────────                                  │
│  Environment: Jetson Orin Nano                                   │
│  Mode: Full GPU inference                                        │
│  Focus: Detection, OCR, tracking, performance                   │
│                                                                  │
│  Responsibilities:                                               │
│  1. Optimize models for TensorRT                                 │
│  2. Tune detection parameters                                    │
│  3. Final integration testing                                    │
│  4. Performance benchmarking                                     │
│  5. Validate team's changes on real hardware                     │
└─────────────────────────────────────────────────────────────────┘

┌─────────────────────────────────────────────────────────────────┐
│  CI/CD PIPELINE                                                  │
│  ──────────────                                                 │
│  Environment: GitHub Actions (CPU)                               │
│  Mode: Unit tests + mocked integration tests                     │
│                                                                  │
│  On every PR:                                                    │
│  1. Lint (ruff, black)                                           │
│  2. Unit tests (pytest tests/unit/)                              │
│  3. Integration tests with mocks                                 │
│  4. Build Docker image                                           │
└─────────────────────────────────────────────────────────────────┘
```

### Validation Checkpoints

```
PR MERGE FLOW
══════════════════════════════════════════════════════════════════

Developer's Laptop          CI/CD                    Jetson (You)
─────────────────          ─────                    ────────────
     │                        │                          │
     │ Push PR                │                          │
     ├───────────────────────>│                          │
     │                        │                          │
     │                        │ Run unit tests           │
     │                        │ Run linting              │
     │                        │ Build image              │
     │                        │                          │
     │                        │ ✓ All pass               │
     │                        ├─────────────────────────>│
     │                        │                          │
     │                        │               Pull & test on Jetson
     │                        │               (for critical changes)
     │                        │                          │
     │                        │                    ✓ Works on hardware
     │                        │<─────────────────────────┤
     │                        │                          │
     │         Merge approved │                          │
     │<───────────────────────┤                          │
     │                        │                          │
```

---

## Configuration Examples

### Development .env File

```bash
# .env.development

# Force CPU mode
ALPR_DEVICE=cpu

# Use mock detector
ALPR_MOCK_DETECTOR=true

# Use sample video instead of RTSP
ALPR_CAMERA_SOURCE=samples/test_video.mp4

# Local database
DATABASE_URL=postgresql://dev:dev@localhost:5432/alpr_dev

# Disable external services
ALPR_SMS_ENABLED=false
ALPR_EMAIL_ENABLED=false

# Development license (all features enabled)
ALPR_LICENSE_FILE=config/license.dev.yaml
```

### Development License

```yaml
# config/license.dev.yaml
# Unlocks all features for development

license:
  id: "dev_license"
  customer_id: "development"
  customer_name: "Development Team"
  device_id: "*"  # Any device

  tier: "enterprise"  # All features

  modules:
    - core
    - gate
    - logging
    - logging.duration
    - vehicle.color
    - vehicle.make_model
    - alerts.email
    - alerts.sms
    - analytics
    - integrations.api

  limits:
    max_cameras: 99
    max_whitelist_entries: 99999
    log_retention_days: 365

  expires_at: "2099-12-31T23:59:59Z"
  signature: "development_mode_no_signature"
```

### VS Code Tasks

```json
// .vscode/tasks.json
{
  "version": "2.0.0",
  "tasks": [
    {
      "label": "Run Tests (Unit)",
      "type": "shell",
      "command": "pytest tests/unit/ -v",
      "group": "test"
    },
    {
      "label": "Run API (Demo Mode)",
      "type": "shell",
      "command": "python -m alpr_edge.main --demo",
      "group": "build"
    },
    {
      "label": "Run API (CPU Mode)",
      "type": "shell",
      "command": "ALPR_DEVICE=cpu python -m alpr_edge.main",
      "group": "build"
    }
  ]
}
```

---

## Summary

| Team Member | Setup | Daily Tools |
|-------------|-------|-------------|
| Backend Dev | Laptop + Mock mode | pytest, curl, Postman |
| Frontend Dev | Laptop + Mock API | npm, browser |
| You (ML/Jetson) | Jetson + GPU | Full system, cameras |
| CI/CD | GitHub Actions | Automated tests |

**Key Principle:** 90% of development doesn't need GPU. Use mocks and unit tests for fast iteration, validate on Jetson before release.

---

## Related Documentation

- [GitHub Setup Guide](github-setup-guide.md) - Repository setup
- [Project Structure](project-structure.md) - Code organization
- [Modular Deployment](modular-deployment.md) - License-based features
