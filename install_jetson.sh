#!/bin/bash
# ALPR System - Jetson Orin NX Installation Script
# Installs PyTorch, TorchVision, and all dependencies for ARM64

set -e  # Exit on error

echo "========================================="
echo "ALPR System - Jetson Installation"
echo "========================================="
echo ""

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

# Check if running on Jetson
if [ ! -f /etc/nv_tegra_release ]; then
    echo -e "${RED}ERROR: This script is for NVIDIA Jetson only!${NC}"
    echo "For desktop/server, use standard pip installation."
    exit 1
fi

echo -e "${GREEN}✓ Detected Jetson platform${NC}"

# Check JetPack version
JETPACK_VERSION=$(sudo apt-cache show nvidia-jetpack | grep Version | head -n1 | awk '{print $2}')
echo -e "${GREEN}✓ JetPack Version: ${JETPACK_VERSION}${NC}"

# Check CUDA
CUDA_VERSION=$(nvcc --version | grep "release" | awk '{print $6}' | cut -c2-)
echo -e "${GREEN}✓ CUDA Version: ${CUDA_VERSION}${NC}"

# Update system
echo ""
echo "Updating system packages..."
sudo apt update
sudo apt install -y python3-pip python3-dev build-essential cmake git wget \
    libopenblas-dev libopenmpi-dev libomp-dev libssl-dev libffi-dev \
    openmpi-bin

# Set CUDA path
export PATH=/usr/local/cuda/bin:$PATH
export LD_LIBRARY_PATH=/usr/local/cuda/lib64:$LD_LIBRARY_PATH

# Add to bashrc if not already there
if ! grep -q "CUDA" ~/.bashrc; then
    echo "" >> ~/.bashrc
    echo "# CUDA paths" >> ~/.bashrc
    echo 'export PATH=/usr/local/cuda/bin:$PATH' >> ~/.bashrc
    echo 'export LD_LIBRARY_PATH=/usr/local/cuda/lib64:$LD_LIBRARY_PATH' >> ~/.bashrc
    echo -e "${GREEN}✓ Added CUDA to ~/.bashrc${NC}"
fi

# Install PyTorch (Jetson-specific wheel)
echo ""
echo "========================================="
echo "Installing PyTorch for Jetson..."
echo "========================================="

# Check if PyTorch already installed
if python3 -c "import torch" 2>/dev/null; then
    PYTORCH_VERSION=$(python3 -c "import torch; print(torch.__version__)")
    echo -e "${YELLOW}PyTorch already installed: ${PYTORCH_VERSION}${NC}"
    read -p "Reinstall? (y/N): " -n 1 -r
    echo
    if [[ ! $REPLY =~ ^[Yy]$ ]]; then
        echo "Skipping PyTorch installation"
    else
        pip3 uninstall -y torch
    fi
fi

# Download and install PyTorch wheel based on JetPack version
# https://forums.developer.nvidia.com/t/pytorch-for-jetson/72048

# Determine PyTorch version based on JetPack
if [[ $JETPACK_VERSION == 6.1* ]]; then
    echo "Detected JetPack 6.1 - Using PyTorch 2.5.0"
    # Using Ultralytics mirror (faster, more reliable)
    PYTORCH_URL="https://github.com/ultralytics/assets/releases/download/v0.0.0/torch-2.5.0a0+872d972e41.nv24.08-cp310-cp310-linux_aarch64.whl"
    TORCHVISION_URL="https://github.com/ultralytics/assets/releases/download/v0.0.0/torchvision-0.20.0a0+afc54f7-cp310-cp310-linux_aarch64.whl"
    TORCHVISION_VERSION="v0.20.0"
    PYTHON_VERSION="cp310"
    USE_PREBUILT_TORCHVISION=true
elif [[ $JETPACK_VERSION == 6.0* ]]; then
    echo "Detected JetPack 6.0 - Using PyTorch 2.3.0"
    PYTORCH_WHEEL="torch-2.3.0-cp310-cp310-linux_aarch64.whl"
    PYTORCH_URL="https://developer.download.nvidia.com/compute/redist/jp/v60/pytorch/${PYTORCH_WHEEL}"
    TORCHVISION_VERSION="v0.18.0"
    PYTHON_VERSION="cp310"
elif [[ $JETPACK_VERSION == 5.1* ]]; then
    echo "Detected JetPack 5.1 - Using PyTorch 2.1.0"
    PYTORCH_WHEEL="torch-2.1.0a0+41361538.nv23.06-cp38-cp38-linux_aarch64.whl"
    PYTORCH_URL="https://developer.download.nvidia.com/compute/redist/jp/v512/pytorch/${PYTORCH_WHEEL}"
    TORCHVISION_VERSION="v0.16.0"
    PYTHON_VERSION="cp38"
else
    echo -e "${RED}ERROR: Unsupported JetPack version: ${JETPACK_VERSION}${NC}"
    echo "Please install manually. See docs/JETSON_SETUP.md"
    exit 1
fi

echo "PyTorch URL: ${PYTORCH_URL}"
echo "TorchVision version: ${TORCHVISION_VERSION}"

# Install cuSPARSELt for PyTorch 2.5.0 (JP 6.1)
if [[ $JETPACK_VERSION == 6.1* ]]; then
    echo "Installing cuSPARSELt (required for PyTorch 2.5.0)..."

    # Add CUDA repository keyring
    if [ ! -f /usr/share/keyrings/cuda-archive-keyring.gpg ]; then
        echo "Adding CUDA repository keyring..."
        wget https://developer.download.nvidia.com/compute/cuda/repos/ubuntu2204/arm64/cuda-keyring_1.1-1_all.deb
        sudo dpkg -i cuda-keyring_1.1-1_all.deb
        rm cuda-keyring_1.1-1_all.deb
    fi

    # Install cuSPARSELt
    sudo apt update
    sudo apt install -y libcusparselt0 libcusparselt-dev
fi

echo "Installing PyTorch..."
pip3 install ${PYTORCH_URL}

# Verify PyTorch
echo "Verifying PyTorch installation..."
python3 << EOF
import torch
print(f"PyTorch version: {torch.__version__}")
print(f"CUDA available: {torch.cuda.is_available()}")
if torch.cuda.is_available():
    print(f"CUDA device: {torch.cuda.get_device_name(0)}")
    print(f"cuDNN version: {torch.backends.cudnn.version()}")
else:
    print("ERROR: CUDA not available!")
    exit(1)
EOF

if [ $? -ne 0 ]; then
    echo -e "${RED}ERROR: PyTorch installation failed!${NC}"
    exit 1
fi

echo -e "${GREEN}✓ PyTorch installed successfully${NC}"

# Install TorchVision from source
echo ""
echo "========================================="
echo "Installing TorchVision from source..."
echo "========================================="

# Check if torchvision already installed
if python3 -c "import torchvision" 2>/dev/null; then
    TORCHVISION_VERSION=$(python3 -c "import torchvision; print(torchvision.__version__)")
    echo -e "${YELLOW}TorchVision already installed: ${TORCHVISION_VERSION}${NC}"
    read -p "Rebuild? (y/N): " -n 1 -r
    echo
    if [[ ! $REPLY =~ ^[Yy]$ ]]; then
        echo "Skipping TorchVision build"
        SKIP_TORCHVISION=1
    else
        pip3 uninstall -y torchvision
    fi
fi

if [ -z "$SKIP_TORCHVISION" ]; then
    # Check if we have a prebuilt wheel (JP 6.1 only for now)
    if [ "$USE_PREBUILT_TORCHVISION" = true ]; then
        echo "Installing TorchVision from prebuilt wheel (much faster!)..."
        pip3 install ${TORCHVISION_URL}
    else
        # Build from source for other JetPack versions
        if [ -d "torchvision" ]; then
            rm -rf torchvision
        fi

        echo "Cloning TorchVision ${TORCHVISION_VERSION}..."
        git clone --branch ${TORCHVISION_VERSION} --depth 1 https://github.com/pytorch/vision torchvision
        cd torchvision

        # Build settings
        export BUILD_VERSION=${TORCHVISION_VERSION#v}  # Remove 'v' prefix
        export TORCH_CUDA_ARCH_LIST="8.7"  # Orin NX (Ampere)

        # Build and install
        echo "Building TorchVision (this may take 10-15 minutes)..."
        python3 setup.py install --user

        cd ..
    fi

    # Verify
    python3 -c "import torchvision; print(f'TorchVision version: {torchvision.__version__}')"

    if [ $? -ne 0 ]; then
        echo -e "${RED}ERROR: TorchVision build failed!${NC}"
        exit 1
    fi

    echo -e "${GREEN}✓ TorchVision installed successfully${NC}"
fi

# Install Ultralytics (without dependencies to avoid x86_64 PyTorch)
echo ""
echo "========================================="
echo "Installing Ultralytics (YOLOv11)..."
echo "========================================="

# Install dependencies separately
pip3 install \
    numpy \
    pillow \
    pyyaml \
    requests \
    scipy \
    tqdm \
    matplotlib \
    pandas \
    seaborn \
    psutil \
    py-cpuinfo \
    thop

# Install Ultralytics without dependencies
pip3 install ultralytics --no-deps

# Verify
python3 << EOF
from ultralytics import YOLO
print("Ultralytics YOLO imported successfully")
model = YOLO('yolov8n.pt')
print("YOLO model loaded successfully")
EOF

if [ $? -ne 0 ]; then
    echo -e "${RED}ERROR: Ultralytics installation failed!${NC}"
    exit 1
fi

echo -e "${GREEN}✓ Ultralytics installed successfully${NC}"

# Install ONNX Runtime GPU for model export
echo ""
echo "========================================="
echo "Installing ONNX Runtime GPU..."
echo "========================================="

if [[ $JETPACK_VERSION == 6.1* ]]; then
    echo "Installing ONNX Runtime GPU for JetPack 6.1..."
    pip3 install https://github.com/ultralytics/assets/releases/download/v0.0.0/onnxruntime_gpu-1.20.0-cp310-cp310-linux_aarch64.whl

    # Fix numpy version compatibility (ONNX Runtime reverts numpy to latest)
    echo "Fixing numpy version compatibility..."
    pip3 install numpy==1.23.5

    echo -e "${GREEN}✓ ONNX Runtime GPU installed${NC}"
fi

# Install other ALPR dependencies
echo ""
echo "========================================="
echo "Installing ALPR dependencies..."
echo "========================================="

pip3 install \
    opencv-python \
    opencv-contrib-python \
    pydantic \
    loguru \
    python-dotenv \
    redis \
    hiredis

echo -e "${GREEN}✓ ALPR dependencies installed${NC}"

# Performance optimization
echo ""
echo "========================================="
echo "Optimizing Jetson performance..."
echo "========================================="

# Set max performance mode
echo "Setting max performance mode (nvpmodel -m 0)..."
sudo nvpmodel -m 0

# Lock clocks
echo "Locking clocks to maximum..."
sudo jetson_clocks

echo -e "${GREEN}✓ Performance optimized${NC}"

# Final verification
echo ""
echo "========================================="
echo "Final Verification"
echo "========================================="

python3 << EOF
import torch
import torchvision
from ultralytics import YOLO

print("=" * 50)
print("Installation Summary:")
print("=" * 50)
print(f"✓ PyTorch: {torch.__version__}")
print(f"✓ TorchVision: {torchvision.__version__}")
print(f"✓ CUDA Available: {torch.cuda.is_available()}")
if torch.cuda.is_available():
    print(f"✓ CUDA Device: {torch.cuda.get_device_name(0)}")
    print(f"✓ cuDNN Version: {torch.backends.cudnn.version()}")
print(f"✓ Ultralytics: installed")
print("=" * 50)

# Quick benchmark
print("\nRunning quick benchmark...")
import numpy as np
import time

model = YOLO('yolo11n.pt')
dummy = np.zeros((640, 640, 3), dtype=np.uint8)

# Warmup
for _ in range(5):
    model(dummy, verbose=False)

# Benchmark
times = []
for _ in range(20):
    start = time.time()
    model(dummy, verbose=False)
    times.append(time.time() - start)

avg_time = np.mean(times) * 1000
fps = 1 / np.mean(times)

print(f"Average inference: {avg_time:.1f}ms")
print(f"Estimated FPS: {fps:.1f}")
print("=" * 50)
EOF

echo ""
echo -e "${GREEN}=========================================${NC}"
echo -e "${GREEN}Installation Complete!${NC}"
echo -e "${GREEN}=========================================${NC}"
echo ""
echo "Next steps:"
echo "1. cd /home/jetson/OVR-ALPR"
echo "2. python3 pilot.py"
echo ""
echo "Expected performance: 25-30 FPS @ 1080p with YOLOv11n"
echo ""
echo "Documentation:"
echo "- QUICKSTART.md - How to use the pilot"
echo "- docs/JETSON_SETUP.md - Detailed Jetson setup guide"
echo ""
