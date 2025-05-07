#!/bin/sh

# Start cronie daemon in the background
# -b: run in background
# -S: log to syslog (which often gets redirected to container logs)
/usr/sbin/crond -b -S

echo "--- DEBUG: About to start WhatsApp Bridge ---"
echo "--- DEBUG: Current directory: $(pwd) ---"
echo "--- DEBUG: PATH variable: $PATH ---"
echo "--- DEBUG: LD_LIBRARY_PATH variable: $LD_LIBRARY_PATH ---"

echo "--- DEBUG: Listing /app contents: ---"
ls -la /app

echo "--- DEBUG: Listing /usr/bin for file utility: ---"
ls -la /usr/bin/file || echo "/usr/bin/file not found"

echo "--- DEBUG: Attempting to use /usr/bin/file on whatsapp-bridge: ---"
/usr/bin/file /app/whatsapp-bridge || echo "/usr/bin/file command failed"

echo "--- DEBUG: Listing /lib for musl libc: ---"
ls -la /lib/libc.musl-x86_64.so.1 || echo "/lib/libc.musl-x86_64.so.1 not found"
ls -la /lib || echo "/lib directory listing failed"

echo "--- DEBUG: Checking /app/whatsapp-bridge ldd (shared libraries): ---"
ldd /app/whatsapp-bridge || echo "ldd command failed or not applicable" # ldd is a bash script on Alpine, bash is installed.
echo "--- DEBUG: Attempting to execute /app/whatsapp-bridge ---"

# Start the Go WhatsApp bridge
echo "Starting WhatsApp Bridge..." # This is the original echo
/app/whatsapp-bridge 