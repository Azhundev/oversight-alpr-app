# Jetson Orin NX Setup Guide

## Important: ARM64 Architecture Requirements

Jetson uses ARM64 architecture, which requires special PyTorch builds from NVIDIA.
**DO NOT use standard pip PyTorch** - it won't work!

## Prerequisites

### 1. Verify JetPack Version

```bash
# Check JetPack version
sudo apt-cache show nvidia-jetpack

# Check CUDA version
nvcc --version

# Check cuDNN
cat /usr/include/cudnn_version.h | grep CUDNN_MAJOR -A 2
```

Common configurations:
- **JetPack 5.1.x** → CUDA 11.4, cuDNN 8.6
- **JetPack 6.0** → CUDA 12.2, cuDNN 8.9

### 2. System Updates

```bash
sudo apt update
sudo apt upgrade -y

# Install system dependencies
sudo apt install -y \
    python3-pip \
    python3-dev \
    build-essential \
    cmake \
    git \
    wget \
    libopenblas-dev \
    libopenmpi-dev \
    libomp-dev \
    libssl-dev \
    libffi-dev
```

## PyTorch Installation (Jetson-Specific)

### Method 1: NVIDIA Pre-built Wheels (Recommended)

**Check your JetPack version first:**
```bash
sudo apt-cache show nvidia-jetpack | grep Version
```

#### For JetPack 6.1 (CUDA 12.6):

```bash
# Download PyTorch 2.5.0 for JetPack 6.1
wget https://developer.download.nvidia.com/compute/redist/jp/v61/pytorch/torch-2.5.0a0+872d972e41.nv24.08.17622132-cp310-cp310-linux_aarch64.whl

# Install PyTorch
pip3 install torch-2.5.0a0+872d972e41.nv24.08.17622132-cp310-cp310-linux_aarch64.whl

# Verify
python3 -c "import torch; print(f'PyTorch: {torch.__version__}'); print(f'CUDA: {torch.cuda.is_available()}')"
```

Expected output:
```
PyTorch: 2.5.0a0+872d972e41.nv24.08.17622132
CUDA: True
```

#### For JetPack 6.0 (CUDA 12.2):

```bash
# Download PyTorch 2.3.0
wget https://developer.download.nvidia.com/compute/redist/jp/v60/pytorch/torch-2.3.0-cp310-cp310-linux_aarch64.whl

# Install
pip3 install torch-2.3.0-cp310-cp310-linux_aarch64.whl
```

#### For JetPack 5.1.x (CUDA 11.4):

```bash
# Download PyTorch 2.1.0
wget https://developer.download.nvidia.com/compute/redist/jp/v512/pytorch/torch-2.1.0a0+41361538.nv23.06-cp38-cp38-linux_aarch64.whl

# Install
pip3 install torch-2.1.0a0+41361538.nv23.06-cp38-cp38-linux_aarch64.whl
```

**All versions:** Check available wheels at https://forums.developer.nvidia.com/t/pytorch-for-jetson/72048

### Method 2: Install via nvidia-pyindex (Alternative)

```bash
# Add NVIDIA Python index
pip3 install nvidia-pyindex

# Install PyTorch (this pulls Jetson-compatible version)
pip3 install --upgrade torch
```

## TorchVision Installation

### Option A: From Source (Recommended for Latest)

**Match TorchVision version to your PyTorch:**

#### For PyTorch 2.5.0 (JetPack 6.1):

```bash
# Clone torchvision v0.20.0
git clone --branch v0.20.0 https://github.com/pytorch/vision torchvision
cd torchvision

# Set environment variables
export BUILD_VERSION=0.20.0
export TORCH_CUDA_ARCH_LIST="8.7"  # Orin NX (Ampere)

# Build and install
python3 setup.py install --user

# Verify
python3 -c "import torchvision; print(torchvision.__version__)"
```

#### For PyTorch 2.3.0 (JetPack 6.0):

```bash
git clone --branch v0.18.0 https://github.com/pytorch/vision torchvision
cd torchvision
export BUILD_VERSION=0.18.0
export TORCH_CUDA_ARCH_LIST="8.7"
python3 setup.py install --user
```

#### For PyTorch 2.1.0 (JetPack 5.1):

```bash
git clone --branch v0.16.0 https://github.com/pytorch/vision torchvision
cd torchvision
export BUILD_VERSION=0.16.0
export TORCH_CUDA_ARCH_LIST="8.7"
python3 setup.py install --user
```

**Version Compatibility:**
| JetPack | PyTorch | TorchVision | Python |
|---------|---------|-------------|--------|
| 6.1     | 2.5.0   | 0.20.0      | 3.10   |
| 6.0     | 2.3.0   | 0.18.0      | 3.10   |
| 5.1.x   | 2.1.0   | 0.16.0      | 3.8    |

### Option B: Pre-built Wheel (Faster)

```bash
# Check for available wheels
# https://forums.developer.nvidia.com/t/pytorch-for-jetson/72048

# Download matching torchvision wheel
wget https://developer.download.nvidia.com/compute/redist/jp/v512/pytorch/torchvision-0.16.0a0+0e3dfe4.nv23.06-cp38-cp38-linux_aarch64.whl

# Install
pip3 install torchvision-0.16.0a0+0e3dfe4.nv23.06-cp38-cp38-linux_aarch64.whl
```

## Ultralytics (YOLOv11) Installation

```bash
# Install dependencies first
pip3 install \
    numpy \
    pillow \
    pyyaml \
    requests \
    scipy \
    tqdm \
    matplotlib \
    opencv-python \
    pandas \
    seaborn

# Install Ultralytics (will use existing PyTorch, not reinstall)
pip3 install ultralytics --no-deps

# Then install only missing dependencies
pip3 install \
    psutil \
    py-cpuinfo \
    thop
```

**Important:** Use `--no-deps` to prevent pip from trying to install x86_64 PyTorch!

## Verify Complete Installation

```bash
python3 << EOF
import torch
import torchvision
from ultralytics import YOLO

print(f"✓ PyTorch: {torch.__version__}")
print(f"✓ TorchVision: {torchvision.__version__}")
print(f"✓ CUDA Available: {torch.cuda.is_available()}")
print(f"✓ CUDA Device: {torch.cuda.get_device_name(0)}")
print(f"✓ cuDNN Enabled: {torch.backends.cudnn.enabled}")
print(f"✓ cuDNN Version: {torch.backends.cudnn.version()}")

# Test YOLO
model = YOLO('yolov8n.pt')
print(f"✓ Ultralytics YOLO loaded successfully")
EOF
```

Expected output:
```
✓ PyTorch: 2.1.0a0+41361538.nv23.06
✓ TorchVision: 0.16.0a0+0e3dfe4.nv23.06
✓ CUDA Available: True
✓ CUDA Device: Orin NX
✓ cuDNN Enabled: True
✓ cuDNN Version: 8600
✓ Ultralytics YOLO loaded successfully
```

## Install Other ALPR Dependencies

```bash
# PaddleOCR and dependencies
pip3 install \
    paddlepaddle-gpu \
    paddleocr \
    pydantic \
    loguru \
    pyyaml \
    redis \
    python-dotenv

# Camera and video processing
pip3 install opencv-python opencv-contrib-python

# For ONVIF camera discovery
pip3 install onvif-zeep wsdiscovery
```

## Common Issues & Fixes

### Issue 1: "ImportError: cannot import name 'PILLOW_VERSION'"

```bash
# Downgrade Pillow
pip3 install "Pillow<10.0.0"
```

### Issue 2: "OSError: libmpi_cxx.so.40: cannot open shared object file"

```bash
# Install OpenMPI
sudo apt install libopenmpi-dev openmpi-bin
```

### Issue 3: TorchVision build fails with "nvcc not found"

```bash
# Add CUDA to PATH
export PATH=/usr/local/cuda/bin:$PATH
export LD_LIBRARY_PATH=/usr/local/cuda/lib64:$LD_LIBRARY_PATH

# Add to .bashrc for persistence
echo 'export PATH=/usr/local/cuda/bin:$PATH' >> ~/.bashrc
echo 'export LD_LIBRARY_PATH=/usr/local/cuda/lib64:$LD_LIBRARY_PATH' >> ~/.bashrc
```

### Issue 4: Low performance / not using GPU

```bash
# Check GPU utilization
sudo tegrastats

# Enable max performance mode
sudo nvpmodel -m 0  # Max performance
sudo jetson_clocks   # Lock clocks to max
```

## Performance Optimization for Jetson

### 1. Enable TensorRT

TensorRT is pre-installed on Jetson. Ultralytics will auto-export:

```python
from ultralytics import YOLO

model = YOLO('yolo11n.pt')

# Export to TensorRT (automatic on first inference)
# Or force export:
model.export(format='engine', half=True, device=0)
```

### 2. Set Power Mode

```bash
# Check current mode
sudo nvpmodel -q

# Set to max performance (mode 0)
sudo nvpmodel -m 0

# Lock clocks
sudo jetson_clocks

# Verify
sudo tegrastats
```

### 3. Increase Swap (if needed)

```bash
# Check current swap
free -h

# Add 8GB swap
sudo fallocate -l 8G /swapfile
sudo chmod 600 /swapfile
sudo mkswap /swapfile
sudo swapon /swapfile

# Make permanent
echo '/swapfile none swap sw 0 0' | sudo tee -a /etc/fstab
```

## Quick Start After Installation

```bash
cd /home/jetson/OVR-ALPR

# Test PyTorch + CUDA
python3 -c "import torch; print(torch.cuda.is_available())"

# Run pilot
python3 pilot.py

# Expected: 25-30 FPS with YOLOv11n @ 1080p
```

## Benchmark Your System

```bash
python3 << EOF
from ultralytics import YOLO
import time
import numpy as np

model = YOLO('yolo11n.pt')
model.export(format='engine', half=True)  # Export to TensorRT

# Warmup
dummy = np.zeros((640, 640, 3), dtype=np.uint8)
for _ in range(10):
    model(dummy, verbose=False)

# Benchmark
times = []
for _ in range(100):
    start = time.time()
    model(dummy, verbose=False)
    times.append(time.time() - start)

print(f"Average inference: {np.mean(times)*1000:.1f}ms")
print(f"FPS: {1/np.mean(times):.1f}")
EOF
```

Expected performance:
- **YOLOv11n:** ~30-35ms (28-30 FPS)
- **YOLOv11s:** ~45-55ms (18-22 FPS)
- **YOLOv11m:** ~70-85ms (12-14 FPS)

## Resources

- **NVIDIA PyTorch for Jetson:** https://forums.developer.nvidia.com/t/pytorch-for-jetson/72048
- **JetPack SDK:** https://developer.nvidia.com/embedded/jetpack
- **Jetson Software:** https://developer.nvidia.com/embedded/downloads
- **Performance Tuning:** https://docs.nvidia.com/jetson/archives/r35.1/DeveloperGuide/text/SD/PlatformPowerAndPerformance.html

## Architecture-Specific Notes

### ARM64 vs x86_64

| Package | x86_64 (Desktop) | ARM64 (Jetson) |
|---------|------------------|----------------|
| PyTorch | `pip install torch` | NVIDIA wheel |
| TorchVision | `pip install torchvision` | Build from source |
| CUDA | Desktop CUDA | JetPack CUDA |
| cuDNN | Separate install | Included in JetPack |
| TensorRT | Optional | Pre-installed |

### Why This Matters

1. **ABI Compatibility:** Jetson ARM64 binaries are incompatible with x86_64
2. **CUDA Version:** Jetson uses JetPack CUDA (different from desktop CUDA)
3. **Optimizations:** NVIDIA wheels include Jetson-specific optimizations
4. **TensorRT:** Deeply integrated on Jetson for maximum performance

## Summary

✅ **DO:**
- Use NVIDIA pre-built PyTorch wheels for Jetson
- Build TorchVision from source (matching PyTorch version)
- Install Ultralytics with `--no-deps`
- Enable TensorRT for best performance
- Use `nvpmodel -m 0` for max performance

❌ **DON'T:**
- Use standard `pip install torch torchvision`
- Let pip auto-install dependencies (will pull x86_64 versions)
- Skip TensorRT export (huge performance loss)
- Run without setting power mode
