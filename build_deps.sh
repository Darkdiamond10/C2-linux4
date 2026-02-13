#!/bin/bash
set -euo pipefail

PREFIX="${PREFIX:-$HOME/musl}"
BUILD_DIR=$(mktemp -d)
NPROC=$(nproc 2>/dev/null || echo 4)

cleanup() {
    rm -rf "$BUILD_DIR"
}
trap cleanup EXIT

echo "[*] Building in $BUILD_DIR"
echo "[*] Prefix: $PREFIX"

mkdir -p "$PREFIX"

cd "$BUILD_DIR"

# Build musl (using system gcc)
if [ ! -f "$PREFIX/bin/musl-gcc" ]; then
    echo "[+] Building musl..."
    curl -L -f --retry 3 -O https://musl.libc.org/releases/musl-1.2.4.tar.gz || {
        echo "[-] Failed to download musl"
        exit 1
    }
    tar xzf musl-1.2.4.tar.gz
    cd musl-1.2.4
    # Ensure we use system gcc for this step
    CC=gcc ./configure --prefix="$PREFIX" --syslibdir="$PREFIX/lib" --disable-shared
    make -j"$NPROC"
    make install
    cd ..
    echo "[+] musl built successfully"
else
    echo "[*] musl already built, skipping"
fi

# Set compiler to musl-gcc for subsequent builds
export CC="${PREFIX}/bin/musl-gcc"
export CFLAGS="${CFLAGS:--static -fPIC -DOPENSSL_NO_SECURE_MEMORY}"

echo "[*] Switched CC to $CC"

# Build OpenSSL
if [ ! -f "$PREFIX/lib/libssl.a" ]; then
    echo "[+] Building OpenSSL..."
    curl -L -f --retry 3 -O https://www.openssl.org/source/openssl-1.1.1w.tar.gz || {
        echo "[-] Failed to download OpenSSL"
        exit 1
    }
    tar xzf openssl-1.1.1w.tar.gz
    cd openssl-1.1.1w
    ./config --prefix="$PREFIX" --openssldir="$PREFIX/ssl" \
             no-shared no-zlib no-async no-tests no-engine "$CFLAGS"
    make -j"$NPROC"
    make install_sw
    cd ..
    echo "[+] OpenSSL built successfully"
else
    echo "[*] OpenSSL already built, skipping"
fi

# Build curl
if [ ! -f "$PREFIX/lib/libcurl.a" ]; then
    echo "[+] Building curl..."
    curl -L -f --retry 3 -O https://curl.se/download/curl-8.5.0.tar.gz || {
        echo "[-] Failed to download curl"
        exit 1
    }
    tar xzf curl-8.5.0.tar.gz
    cd curl-8.5.0
    # curl configure needs help finding the static openssl in prefix
    ./configure --prefix="$PREFIX" --disable-shared --enable-static \
                --with-openssl="$PREFIX" --disable-ldap --disable-ldaps \
                --disable-rtsp --disable-dict --disable-telnet --disable-tftp \
                --disable-pop3 --disable-imap --disable-smtp --disable-gopher \
                --disable-manual --disable-libcurl-option --without-zlib \
                CC="$CC" CFLAGS="$CFLAGS" LIBS="-ldl -lpthread"
    make -j"$NPROC"
    make install
    cd ..
    echo "[+] curl built successfully"
else
    echo "[*] curl already built, skipping"
fi

echo "[+] All dependencies built successfully."
