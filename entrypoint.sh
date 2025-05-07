#!/bin/sh

# Start cron in the background
# cron -f will run it in the foreground, but we want it in bg
# and let the Go bridge be the main foreground process for Tini
/usr/sbin/cron

echo "--- DEBUG: About to start WhatsApp Bridge ---"
echo "--- DEBUG: Current directory: $(pwd) ---"
echo "--- DEBUG: Listing /app contents: ---"
ls -la /app
echo "--- DEBUG: Checking /app/whatsapp-bridge file type: ---"
file /app/whatsapp-bridge
echo "--- DEBUG: Checking /app/whatsapp-bridge ldd (shared libraries): ---"
ldd /app/whatsapp-bridge || echo "ldd command failed or not applicable"
echo "--- DEBUG: Attempting to execute /app/whatsapp-bridge ---"

# Start the Go WhatsApp bridge
echo "Starting WhatsApp Bridge..."
# The bridge will create/use files in /app/store
/app/whatsapp-bridge 