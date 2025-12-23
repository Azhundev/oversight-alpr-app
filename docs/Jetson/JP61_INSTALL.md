# Quick Install for JetPack 6.1

## Automated Installation

```bash
./install_jetson.sh
```

The script auto-detects JP 6.1 and installs the correct versions.

## Manual Installation (JP 6.1 Specific)

### 1. System Preparation

```bash
sudo apt update && sudo apt upgrade -y

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
    libomp-dev

# Add CUDA repository keyring (for cuSPARSELt)
wget https://developer.download.nvidia.com/compute/cuda/repos/ubuntu2204/arm64/cuda-keyring_1.1-1_all.deb
sudo dpkg -i cuda-keyring_1.1-1_all.deb
sudo apt update

# Install cuSPARSELt (required for PyTorch 2.5.0)
sudo apt install -y libcusparselt0 libcusparselt-dev

# Set CUDA paths
export PATH=/usr/local/cuda/bin:$PATH
export LD_LIBRARY_PATH=/usr/local/cuda/lib64:$LD_LIBRARY_PATH
```

**Important:** cuSPARSELt is required for PyTorch 2.5.0 to avoid `libcusparseLt.so` dependency errors.

### 2. Install PyTorch 2.5.0

**Option A: Direct Install (Recommended - Faster)**

```bash
# Install directly from Ultralytics mirror (no download needed)
pip3 install https://github.com/ultralytics/assets/releases/download/v0.0.0/torch-2.5.0a0+872d972e41.nv24.08-cp310-cp310-linux_aarch64.whl

# Verify
python3 << EOF
import torch
print(f"PyTorch version: {torch.__version__}")
print(f"CUDA available: {torch.cuda.is_available()}")
print(f"CUDA version: {torch.version.cuda}")
print(f"Device: {torch.cuda.get_device_name(0)}")
EOF
```

**Option B: Manual Download**

```bash
# Download from NVIDIA
wget https://developer.download.nvidia.com/compute/redist/jp/v61/pytorch/torch-2.5.0a0+872d972e41.nv24.08.17622132-cp310-cp310-linux_aarch64.whl

# Install
pip3 install torch-2.5.0a0+872d972e41.nv24.08.17622132-cp310-cp310-linux_aarch64.whl
```

Expected output:
```
PyTorch version: 2.5.0a0+872d972e41.nv24.08.17622132
CUDA available: True
CUDA version: 12.6
Device: Orin NX
```

### 3. Install TorchVision 0.20.0

**Option A: Prebuilt Wheel (Recommended - 30 seconds)**

```bash
# Install directly from Ultralytics mirror
pip3 install https://github.com/ultralytics/assets/releases/download/v0.0.0/torchvision-0.20.0a0+afc54f7-cp310-cp310-linux_aarch64.whl

# Verify
python3 -c "import torchvision; print(f'TorchVision: {torchvision.__version__}')"
```

**Option B: Build from Source (if wheel doesn't work - 10-15 minutes)**

```bash
# Clone TorchVision v0.20.0 (matches PyTorch 2.5.0)
git clone --branch v0.20.0 --depth 1 https://github.com/pytorch/vision torchvision
cd torchvision

# Set build variables
export BUILD_VERSION=0.20.0
export TORCH_CUDA_ARCH_LIST="8.7"  # Orin NX Ampere architecture

# Build
python3 setup.py install --user

# Verify
cd ..
python3 -c "import torchvision; print(f'TorchVision: {torchvision.__version__}')"
```

### 4. Install Ultralytics (YOLOv11)

```bash
# Install base dependencies first
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
    seaborn \
    psutil \
    py-cpuinfo

# Install Ultralytics WITHOUT dependencies (critical!)
pip3 install ultralytics --no-deps

# Verify
python3 << EOF
from ultralytics import YOLO
model = YOLO('yolo11n.pt')
print("✓ Ultralytics YOLOv11 loaded successfully")
EOF
```

### 5. Install ONNX Runtime GPU (For Model Export)

```bash
# Install ONNX Runtime GPU (required for ONNX/TensorRT exports)
pip3 install https://github.com/ultralytics/assets/releases/download/v0.0.0/onnxruntime_gpu-1.20.0-cp310-cp310-linux_aarch64.whl

# Fix numpy version (ONNX Runtime reverts to latest, causing conflicts)
pip3 install numpy==1.23.5
```

**Important:** ONNX Runtime GPU enables ONNX and TensorRT model exports. The numpy downgrade is critical - newer versions cause compatibility issues with TorchVision.

### 6. Install ALPR Dependencies

```bash
pip3 install \
    opencv-python \
    opencv-contrib-python \
    pydantic \
    loguru \
    python-dotenv \
    redis \
    hiredis
```

### 7. Optimize Performance

```bash
# Set maximum performance mode
sudo nvpmodel -m 0

# Lock clocks to maximum
sudo jetson_clocks

# Verify
sudo tegrastats
```

### 8. Test Installation and TensorRT Export

```bash
cd /home/jetson/OVR-ALPR

# Quick CUDA test
python3 -c "import torch; print(f'CUDA: {torch.cuda.is_available()}')"

# Export YOLOv11n to TensorRT (one-time, ~30 seconds)
yolo export model=yolo11n.pt format=engine  # Creates 'yolo11n.engine'

# Run inference with TensorRT engine
yolo predict model=yolo11n.engine source='a.mp4'

# Or run the pilot script (auto-exports on first run)
python3 pilot.py
```

**TensorRT Benefits:**
- 2-3x faster inference vs PyTorch
- FP16 precision reduces memory usage
- Optimized for Jetson hardware
- Engine file cached for subsequent runs

## JetPack 6.1 Specifications

| Component | Version |
|-----------|---------|
| JetPack | 6.1 |
| CUDA | 12.6 |
| cuDNN | 9.3 |
| TensorRT | 10.3 |
| Python | 3.10 |
| PyTorch | 2.5.0 |
| TorchVision | 0.20.0 |

## Performance Expectations (Orin NX)

| Model | Resolution | FPS | Latency |
|-------|-----------|-----|---------|
| YOLOv11n | 1920x1080 | 28-32 | ~32ms |
| YOLOv11n | 1280x720 | 40-45 | ~23ms |
| YOLOv11s | 1920x1080 | 20-24 | ~45ms |
| YOLOv11m | 1920x1080 | 14-16 | ~65ms |

*With TensorRT FP16 optimization*

## Troubleshooting JP 6.1

### Issue: "ImportError: libcudnn.so.9: cannot open shared object file"

```bash
# Check cuDNN installation
find /usr -name "libcudnn.so*"

# If missing, reinstall JetPack
sudo apt install --reinstall nvidia-cudnn9-cuda-12
```

### Issue: TorchVision build fails

```bash
# Ensure CUDA is in PATH
export PATH=/usr/local/cuda-12.6/bin:$PATH
export LD_LIBRARY_PATH=/usr/local/cuda-12.6/lib64:$LD_LIBRARY_PATH

# Try build again
cd torchvision
python3 setup.py clean
python3 setup.py install --user
```

### Issue: Low FPS

```bash
# Check power mode
sudo nvpmodel -q

# Should show: MAXN (mode 0)
# If not:
sudo nvpmodel -m 0
sudo jetson_clocks

# Monitor GPU usage
sudo tegrastats
```

### Issue: TensorRT Export Fails

**Symptoms:** "onnxruntime not found" or export errors

**Solution:**
```bash
# Verify ONNX Runtime GPU is installed
python3 -c "import onnxruntime; print(onnxruntime.__version__)"

# If missing, install ARM64 wheel
pip3 install https://github.com/ultralytics/assets/releases/download/v0.0.0/onnxruntime_gpu-1.20.0-cp310-cp310-linux_aarch64.whl

# Fix numpy version
pip3 install numpy==1.23.5
```

### Issue: Numpy Compatibility Errors

**Symptoms:** ImportError with TorchVision or OpenCV

**Solution:**
```bash
# ONNX Runtime may have upgraded numpy - downgrade it
pip3 install numpy==1.23.5

# Verify
python3 -c "import numpy; print(f'Numpy: {numpy.__version__}')"
# Should show: 1.23.5
```

## Version Compatibility Matrix

| JetPack | CUDA | PyTorch | TorchVision | Python | Wheel URL |
|---------|------|---------|-------------|--------|-----------|
| 6.1 | 12.6 | 2.5.0 | 0.20.0 | 3.10 | [Link](https://developer.download.nvidia.com/compute/redist/jp/v61/pytorch/) |
| 6.0 | 12.2 | 2.3.0 | 0.18.0 | 3.10 | [Link](https://developer.download.nvidia.com/compute/redist/jp/v60/pytorch/) |
| 5.1.3 | 11.4 | 2.1.0 | 0.16.0 | 3.8 | [Link](https://developer.download.nvidia.com/compute/redist/jp/v512/pytorch/) |

## Quick Commands Summary

### Super Fast Install (5 minutes - Recommended!)

```bash
# 0. Install cuSPARSELt (required for PyTorch 2.5.0)
wget https://developer.download.nvidia.com/compute/cuda/repos/ubuntu2204/arm64/cuda-keyring_1.1-1_all.deb
sudo dpkg -i cuda-keyring_1.1-1_all.deb
sudo apt update
sudo apt install -y libcusparselt0 libcusparselt-dev

# 1. Install PyTorch 2.5.0 (direct URL)
pip3 install https://github.com/ultralytics/assets/releases/download/v0.0.0/torch-2.5.0a0+872d972e41.nv24.08-cp310-cp310-linux_aarch64.whl

# 2. Install TorchVision 0.20.0 (prebuilt wheel - saves 15 minutes!)
pip3 install https://github.com/ultralytics/assets/releases/download/v0.0.0/torchvision-0.20.0a0+afc54f7-cp310-cp310-linux_aarch64.whl

# 3. Install dependencies
pip3 install numpy pillow pyyaml opencv-python loguru pydantic

# 4. Install Ultralytics (without deps!)
pip3 install ultralytics --no-deps

# 5. Install ONNX Runtime GPU (for TensorRT export)
pip3 install https://github.com/ultralytics/assets/releases/download/v0.0.0/onnxruntime_gpu-1.20.0-cp310-cp310-linux_aarch64.whl

# 6. Fix numpy version (ONNX Runtime breaks compatibility)
pip3 install numpy==1.23.5

# 7. Verify
python3 -c "import torch; import torchvision; print(f'PyTorch: {torch.__version__}'); print(f'TorchVision: {torchvision.__version__}'); print(f'CUDA: {torch.cuda.is_available()}')"

# 8. Export to TensorRT
yolo export model=yolo11n.pt format=engine

# 9. Run pilot
python3 pilot.py
```

### OR Use Automated Script

```bash
# One command install (includes all optimizations)
./install_jetson.sh
```

## Success Indicators

✅ PyTorch imports without errors
✅ `torch.cuda.is_available()` returns `True`
✅ CUDA version shows `12.6`
✅ TorchVision imports successfully
✅ ONNX Runtime GPU installed (enables TensorRT export)
✅ Numpy version is 1.23.5 (not latest)
✅ YOLOv11 model loads
✅ TensorRT engine exports successfully (`yolo11n.engine` created)
✅ Pilot runs at 28-32 FPS with TensorRT

## Resources

- **PyTorch for Jetson:** https://forums.developer.nvidia.com/t/pytorch-for-jetson/72048
- **JetPack 6.1 Release Notes:** https://developer.nvidia.com/embedded/jetpack
- **NVIDIA Jetson Orin:** https://developer.nvidia.com/embedded/jetson-orin
