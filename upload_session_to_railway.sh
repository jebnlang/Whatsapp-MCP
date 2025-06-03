#!/bin/bash

echo "🔐 WhatsApp Session Upload to Railway"
echo "======================================"

# Check if Railway CLI is installed
if ! command -v railway &> /dev/null; then
    echo "❌ Railway CLI not found. Please install it first:"
    echo "   npm install -g @railway/cli"
    exit 1
fi

# Check if session file exists
SESSION_FILE="whatsapp-mcp/whatsapp-bridge/store/whatsapp.db"
if [ ! -f "$SESSION_FILE" ]; then
    echo "❌ Session file not found at: $SESSION_FILE"
    echo "   Please authenticate locally first by running the WhatsApp bridge."
    exit 1
fi

echo "✅ Found session file: $SESSION_FILE"

# Get file size
SESSION_SIZE=$(stat -f%z "$SESSION_FILE" 2>/dev/null || stat -c%s "$SESSION_FILE" 2>/dev/null)
echo "📊 Session size: $SESSION_SIZE bytes"

# Login check
echo "🔑 Checking Railway login status..."
if ! railway whoami &> /dev/null; then
    echo "❌ Not logged in to Railway. Please login first:"
    echo "   railway login"
    exit 1
fi

echo "✅ Railway login verified"

# Project selection
echo "📂 Selecting Railway project..."
echo "   Use 'railway link' if you need to connect to your project first"

# Create base64 of session for upload
echo "🔄 Encoding session file..."
SESSION_B64=$(base64 -i "$SESSION_FILE")

if [ ${#SESSION_B64} -gt 50000 ]; then
    echo "⚠️  Large session detected (${#SESSION_B64} chars)"
    echo "   Using persistent volume method..."
    
    # Method 1: Direct file upload via Railway shell
    echo "📤 Uploading to Railway persistent volume..."
    
    # Create the upload script
    cat > temp_upload.sh << EOF
mkdir -p /app/persistent
echo '$SESSION_B64' | base64 -d > /app/persistent/whatsapp.db
echo "✅ Session uploaded to persistent volume"
ls -la /app/persistent/whatsapp.db
EOF
    
    echo "🚀 Executing upload on Railway..."
    railway shell < temp_upload.sh
    
    # Clean up
    rm temp_upload.sh
    
else
    echo "📤 Session size acceptable for environment variable"
    echo "   You can set WHATSAPP_SESSION_B64 in Railway dashboard"
    echo "   Value: (first 100 chars) ${SESSION_B64:0:100}..."
fi

echo ""
echo "🎉 Session upload process completed!"
echo ""
echo "📋 Next steps:"
echo "1. Verify upload: railway shell, then ls -la /app/persistent/"
echo "2. Set environment variables in Railway dashboard"
echo "3. Deploy your application: railway up"
echo "4. Test the deployment: railway logs --follow"
echo ""
echo "🔗 Environment variables needed:"
echo "   OPENAI_API_KEY=your-openai-key"
echo "   WHATSAPP_SOURCE_GROUPS=Group1,Group2"
echo "   WHATSAPP_FORWARD_RECIPIENT=recipient-group-or-phone"
echo "" 