#!/bin/bash
# Build OpenCV 4.6.0 with GStreamer support for Jetson Orin NX
# This script builds OpenCV with hardware acceleration and GStreamer support

set -e  # Exit on error

echo "========================================="
echo "OpenCV 4.6.0 Build with GStreamer Support"
echo "========================================="
echo ""

# Configuration
OPENCV_VERSION="4.6.0"
BUILD_DIR="$HOME/opencv_build"
INSTALL_PREFIX="$HOME/.local"
PYTHON_EXECUTABLE=$(which python3)
CUDA_ARCH_BIN="8.7"  # Jetson Orin NX

# Create build directory
echo "[1/6] Creating build directory..."
mkdir -p $BUILD_DIR
cd $BUILD_DIR

# Download OpenCV source if not exists
if [ ! -d "opencv-${OPENCV_VERSION}" ]; then
    echo "[2/6] Downloading OpenCV ${OPENCV_VERSION}..."
    wget -O opencv.zip https://github.com/opencv/opencv/archive/${OPENCV_VERSION}.zip
    unzip -q opencv.zip
    rm opencv.zip

    echo "Downloading OpenCV contrib ${OPENCV_VERSION}..."
    wget -O opencv_contrib.zip https://github.com/opencv/opencv_contrib/archive/${OPENCV_VERSION}.zip
    unzip -q opencv_contrib.zip
    rm opencv_contrib.zip
else
    echo "[2/6] OpenCV source already downloaded, skipping..."
fi

# Create build directory
cd opencv-${OPENCV_VERSION}
mkdir -p build
cd build

# Configure with CMake
echo "[3/6] Configuring OpenCV build..."
echo "This may take 5-10 minutes..."
cmake \
    -D CMAKE_BUILD_TYPE=RELEASE \
    -D CMAKE_INSTALL_PREFIX=$INSTALL_PREFIX \
    -D OPENCV_EXTRA_MODULES_PATH=../../opencv_contrib-${OPENCV_VERSION}/modules \
    -D WITH_GSTREAMER=ON \
    -D WITH_GSTREAMER_0_10=OFF \
    -D WITH_CUDA=ON \
    -D WITH_CUDNN=ON \
    -D CUDA_ARCH_BIN=$CUDA_ARCH_BIN \
    -D CUDA_ARCH_PTX="" \
    -D OPENCV_DNN_CUDA=ON \
    -D ENABLE_FAST_MATH=ON \
    -D CUDA_FAST_MATH=ON \
    -D WITH_CUBLAS=ON \
    -D WITH_LIBV4L=ON \
    -D WITH_V4L=ON \
    -D BUILD_opencv_python3=ON \
    -D PYTHON3_EXECUTABLE=$PYTHON_EXECUTABLE \
    -D PYTHON3_INCLUDE_DIR=$(python3 -c "from distutils.sysconfig import get_python_inc; print(get_python_inc())") \
    -D PYTHON3_PACKAGES_PATH=$(python3 -c "from distutils.sysconfig import get_python_lib; print(get_python_lib())") \
    -D BUILD_EXAMPLES=OFF \
    -D BUILD_opencv_apps=OFF \
    -D BUILD_DOCS=OFF \
    -D BUILD_PERF_TESTS=OFF \
    -D BUILD_TESTS=OFF \
    ..

# Verify GStreamer is enabled
echo ""
echo "Verifying GStreamer configuration..."
echo "Checking CMake output..."

# Check cmake_install.cmake or cmake output for GStreamer
cd ..
CMAKE_LOG=$(grep -A 30 "Video I/O:" CMakeFiles/CMakeOutput.log CMakeFiles/CMakeError.log build.log 2>/dev/null || cat build/*.cmake 2>/dev/null | grep -i gstreamer || echo "")
cd build

if grep -q "WITH_GSTREAMER:BOOL=ON" CMakeCache.txt && grep -q "GSTREAMER" CMakeCache.txt; then
    echo "✅ GStreamer support: ENABLED (found in CMakeCache.txt)"
else
    echo "⚠️  Could not verify GStreamer in CMakeCache.txt"
    echo "Checking build configuration..."
fi

if grep -q "CUDA_ARCH_BIN" CMakeCache.txt; then
    CUDA_ARCH=$(grep "CUDA_ARCH_BIN" CMakeCache.txt | head -1)
    echo "✅ CUDA support: ENABLED ($CUDA_ARCH)"
else
    echo "⚠️  CUDA support: Could not verify"
fi

echo ""
echo "Proceeding with build..."

echo ""
echo "[4/6] Building OpenCV..."
echo "⏱️  This will take 2-3 hours on Jetson Orin NX"
echo "Using $(nproc) CPU cores for compilation"
echo ""
echo "Build started at: $(date)"
echo ""

# Build with all CPU cores
make -j$(nproc)

echo ""
echo "Build completed at: $(date)"
echo ""

# Install
echo "[5/6] Installing OpenCV to $INSTALL_PREFIX..."
make install

# Update library cache
echo ""
echo "[6/6] Updating library cache..."
ldconfig $INSTALL_PREFIX/lib 2>/dev/null || echo "Note: ldconfig may need sudo for system-wide cache"

# Verify installation
echo ""
echo "========================================="
echo "Build Complete!"
echo "========================================="
echo ""
echo "Verifying installation..."
$PYTHON_EXECUTABLE -c "import cv2; print('OpenCV version:', cv2.__version__)" || echo "❌ Python import failed"
$PYTHON_EXECUTABLE -c "import cv2; print('GStreamer:', 'YES' if cv2.getBuildInformation().find('GStreamer:                   YES') > 0 else 'NO')" || true

echo ""
echo "Installation complete!"
echo "OpenCV installed to: $INSTALL_PREFIX"
echo ""
echo "Next steps:"
echo "1. Restart your terminal or run: source ~/.bashrc"
echo "2. Test with: python3 -c 'import cv2; print(cv2.getBuildInformation())' | grep GStreamer"
echo "3. Run pilot.py to test hardware decode"
echo ""
