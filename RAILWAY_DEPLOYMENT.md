# 🚀 Railway Deployment Guide

This guide walks you through deploying the WhatsApp Link Forwarder to Railway with automated daily execution.

## 📋 Prerequisites

1. ✅ **Railway Account** - Sign up at [railway.app](https://railway.app)
2. ✅ **Working Local Setup** - Your WhatsApp bridge should be authenticated locally

## 🔧 Step 1: Initial Railway Setup

### 1. Create New Railway Project
```bash
# Install Railway CLI
npm install -g @railway/cli

# Login to Railway
railway login

# Create new project
railway new
```

### 2. Connect to Git Repository
1. Push your code to GitHub/GitLab
2. Connect Railway to your repository
3. Railway will auto-detect the Dockerfile

## 🔑 Step 2: Environment Variables

Set these in your Railway dashboard under **Variables**:

### Required Variables:
```bash
WHATSAPP_SOURCE_GROUPS=BSG - General,Tech Discussions
WHATSAPP_FORWARD_RECIPIENT=BSG - General
WHATSAPP_BRIDGE_WAIT_TIME=20
```

### Variable Descriptions:
- **WHATSAPP_SOURCE_GROUPS**: Comma-separated group names to scan for links
- **WHATSAPP_FORWARD_RECIPIENT**: Group name or phone number to forward links to
- **WHATSAPP_BRIDGE_WAIT_TIME**: Minutes to wait for message sync (default: 20)

## 📁 Step 3: Session Upload (CRITICAL)

Since this is the first deployment, you need to upload your authenticated WhatsApp session:

### Method 1: Railway CLI Upload
```bash
# First, deploy to get the service running
railway up

# Get your service URL
railway domain

# Copy your local session to Railway volume
railway shell
mkdir -p /app/persistent
exit

# Upload session file (from your local machine)
railway shell
cat > /app/persistent/whatsapp.db
# Then paste your base64 session and press Ctrl+D
```

### Method 2: Base64 Environment Variable (Temporary)
```bash
# For initial setup only, you can use env var
# Generate base64 of your session
base64 -i whatsapp-mcp/whatsapp-bridge/store/whatsapp.db

# Add as WHATSAPP_SESSION_B64 environment variable
# NOTE: Remove this after first successful run
```

## ⏰ Step 4: Cron Job Setup

### Option A: Railway Cron Jobs
1. Go to your Railway project dashboard
2. Click **Settings** → **Cron Jobs**
3. Add new cron job:
   ```bash
   Schedule: 0 23 * * *  # 11 PM daily
   Command: sh start.sh
   ```

### Option B: GitHub Actions (Alternative)
Create `.github/workflows/daily-forward.yml`:
```yaml
name: Daily Link Forward
on:
  schedule:
    - cron: '0 23 * * *'  # 11 PM UTC daily
  workflow_dispatch:  # Manual trigger

jobs:
  forward-links:
    runs-on: ubuntu-latest
    steps:
      - name: Trigger Railway Deployment
        run: |
          curl -X POST "${{ secrets.RAILWAY_WEBHOOK_URL }}"
```

## 🧪 Step 5: Testing

### Local Testing
```bash
# Test non-interactive mode locally
WHATSAPP_SOURCE_GROUPS="Test Group" \
WHATSAPP_FORWARD_RECIPIENT="1234567890" \
python3 forward_links_preview.py \
  --db-path whatsapp-mcp/whatsapp-bridge/store/messages.db \
  --non-interactive
```

### Railway Testing
```bash
# Check logs
railway logs

# Check health
curl https://your-app.railway.app/health

# Manual trigger
railway shell
sh start.sh
```

## 🔍 Step 6: Monitoring

### Railway Dashboard
- Monitor logs in real-time
- Check resource usage
- View deployment history

### Health Checks
The service includes automatic health monitoring:
- Bridge connectivity check
- File integrity verification
- API responsiveness

### Troubleshooting Common Issues

#### ❌ "No session found"
**Solution**: Upload your session file to `/app/persistent/whatsapp.db`

#### ❌ "Could not resolve group name"
**Solution**: Check group names in `WHATSAPP_SOURCE_GROUPS` match exactly

#### ❌ "Bridge not responsive"
**Solution**: Check if session is valid and WhatsApp hasn't logged out the device

## 📊 Expected Flow

1. **11:00 PM**: Railway cron triggers deployment
2. **11:00-11:01**: Container starts, WhatsApp bridge initializes
3. **11:01-11:21**: Bridge syncs messages (20 min wait)
4. **11:21**: Link forwarding starts
5. **11:21-11:25**: Process yesterday's links, forward with previews
6. **11:25**: Update timestamp, ready for next day

## 🔐 Security Notes

- Session files are stored in Railway's encrypted persistent volumes
- Environment variables are encrypted in Railway
- No sensitive data in code repository
- API keys are never logged

## 📞 Support

If you encounter issues:
1. Check Railway logs first
2. Verify all environment variables
3. Test locally with same configuration
4. Check WhatsApp Web status 