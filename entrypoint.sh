#!/bin/sh

# Start cron in the background
# cron -f will run it in the foreground, but we want it in bg
# and let the Go bridge be the main foreground process for Tini
/usr/sbin/cron

# Start the Go WhatsApp bridge
echo "Starting WhatsApp Bridge..."
# The bridge will create/use files in /app/store
/app/whatsapp-bridge 