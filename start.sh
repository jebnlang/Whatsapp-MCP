#!/bin/sh

echo "🚀 Starting WhatsApp Link Forwarder System..."

# Default wait time (can be overridden by environment variable)
WAIT_TIME=${WHATSAPP_BRIDGE_WAIT_TIME:-20}

echo "📱 Starting WhatsApp Bridge..."

# Start WhatsApp bridge in background
./whatsapp-bridge &
BRIDGE_PID=$!

echo "🔌 WhatsApp Bridge started with PID: $BRIDGE_PID"

# Wait for bridge to start up
echo "⏳ Waiting 30 seconds for bridge to initialize..."
sleep 30

# Check if bridge is responsive
echo "🔍 Checking bridge health..."
for i in $(seq 1 10); do
    if curl -s http://localhost:8080/api/send > /dev/null 2>&1; then
        echo "✅ Bridge is responsive!"
        break
    else
        echo "⏳ Bridge not ready yet, waiting... (attempt $i/10)"
        sleep 5
    fi
    
    if [ $i -eq 10 ]; then
        echo "❌ Bridge failed to start properly"
        exit 1
    fi
done

echo "📚 Waiting ${WAIT_TIME} minutes for message sync..."
sleep $((WAIT_TIME * 60))

echo "🔗 Starting link forwarding..."

# Run link forwarding script
python3 forward_links_preview.py \
    --db-path store/messages.db \
    --delay 3.0 \
    --non-interactive

FORWARD_EXIT_CODE=$?

if [ $FORWARD_EXIT_CODE -eq 0 ]; then
    echo "✅ Link forwarding completed successfully!"
else
    echo "❌ Link forwarding failed with exit code: $FORWARD_EXIT_CODE"
fi

# Keep bridge running for potential manual operations
echo "🔄 Keeping bridge running for monitoring..."
wait $BRIDGE_PID 