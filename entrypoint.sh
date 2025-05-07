#!/bin/sh

# Start cronie daemon in the background
# -b: run in background
# -S: log to syslog (which often gets redirected to container logs)
/usr/sbin/crond -b -S

echo "--- DEBUG: About to start WhatsApp Bridge ---"
echo "--- DEBUG: Current directory: $(pwd) ---"
echo "--- DEBUG: Listing /app contents: ---"
ls -la /app
echo "--- DEBUG: Checking /app/whatsapp-bridge file type: ---"
file /app/whatsapp-bridge
echo "--- DEBUG: Checking /app/whatsapp-bridge ldd (shared libraries): ---"
ldd /app/whatsapp-bridge || echo "ldd command failed or not applicable" # ldd is a bash script on Alpine, bash is installed.
echo "--- DEBUG: Attempting to execute /app/whatsapp-bridge ---"

# Start the Go WhatsApp bridge
echo "Starting WhatsApp Bridge..." # This is the original echo
/app/whatsapp-bridge 