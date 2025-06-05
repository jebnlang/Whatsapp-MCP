#!/bin/bash

echo "Uploading WhatsApp session to Railway..."

# Navigate to the bridge directory
cd whatsapp-mcp/whatsapp-bridge

# Upload chunks one by one
for chunk in session_chunk_*; do
    echo "Uploading $chunk..."
    cat "$chunk" | railway ssh "cat >> /app/persistent/temp_session.b64"
    if [ $? -eq 0 ]; then
        echo "✅ $chunk uploaded successfully"
    else
        echo "❌ Failed to upload $chunk"
        exit 1
    fi
done

echo "Combining chunks on Railway..."
railway ssh "mv /app/persistent/temp_session.b64 /app/persistent/whatsapp_session.b64"

echo "Verifying upload..."
railway ssh "ls -la /app/persistent/whatsapp_session.b64"

echo "🎉 Session upload complete!" 