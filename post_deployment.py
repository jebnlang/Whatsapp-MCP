#!/usr/bin/env python3

import subprocess
import sys
import time
import os
from datetime import datetime, timedelta

def run_command(command, description):
    """Run a command and return success status."""
    print(f"🔄 {description}")
    print(f"💻 Command: {command}")
    
    try:
        result = subprocess.run(command, shell=True, capture_output=True, text=True, timeout=300)
        
        if result.returncode == 0:
            print(f"✅ {description} - SUCCESS")
            if result.stdout.strip():
                print(f"📋 Output: {result.stdout.strip()}")
            return True
        else:
            print(f"❌ {description} - FAILED")
            if result.stderr.strip():
                print(f"🚨 Error: {result.stderr.strip()}")
            return False
            
    except subprocess.TimeoutExpired:
        print(f"⏰ {description} - TIMEOUT")
        return False
    except Exception as e:
        print(f"❌ {description} - EXCEPTION: {str(e)}")
        return False

def wait_for_bridge_startup(max_wait_minutes=5):
    """Wait for WhatsApp bridge to start up."""
    print(f"⏳ Waiting up to {max_wait_minutes} minutes for bridge startup...")
    
    wait_seconds = int(os.environ.get('WHATSAPP_BRIDGE_WAIT_TIME', '2')) * 60
    print(f"🕐 Bridge sync wait time: {wait_seconds} seconds")
    
    time.sleep(wait_seconds)
    return True

def run_initial_link_preview():
    """Run link preview script for yesterday 00:00 to current time."""
    print("📊 Running initial link preview script...")
    
    # Calculate time range: yesterday 00:00 to now
    now = datetime.now()
    yesterday_start = (now - timedelta(days=1)).replace(hour=0, minute=0, second=0, microsecond=0)
    
    print(f"📅 Time range: {yesterday_start} to {now}")
    
    # Set environment variables for the script
    env = os.environ.copy()
    env['INITIAL_RUN'] = 'true'
    env['START_TIME'] = yesterday_start.isoformat()
    env['END_TIME'] = now.isoformat()
    
    # Run the forward links preview script
    command = "python3 /app/forward_links_preview.py --db-path /app/persistent/messages.db --non-interactive"
    
    try:
        result = subprocess.run(command, shell=True, capture_output=True, text=True, timeout=600, env=env)
        
        if result.returncode == 0:
            print("✅ Initial link preview completed successfully!")
            if result.stdout.strip():
                print(f"📋 Output: {result.stdout.strip()}")
            return True
        else:
            print("❌ Initial link preview failed!")
            if result.stderr.strip():
                print(f"🚨 Error: {result.stderr.strip()}")
            return False
            
    except subprocess.TimeoutExpired:
        print("⏰ Initial link preview timed out!")
        return False
    except Exception as e:
        print(f"❌ Initial link preview exception: {str(e)}")
        return False

def main():
    """Main post-deployment flow."""
    print("🚀 Starting Post-Deployment Flow")
    print("=" * 60)
    
    # Check if this is a Railway cron execution
    is_cron_run = os.environ.get('RAILWAY_RUN_TYPE') == 'cron'
    
    if is_cron_run:
        print("⏰ Detected Railway cron execution - running link preview only")
        # For cron runs, just run the link preview script normally
        if run_command("python3 /app/forward_links_preview.py --db-path /app/persistent/messages.db --non-interactive", 
                      "Running scheduled link preview"):
            print("✅ Scheduled link preview completed successfully!")
        else:
            print("❌ Scheduled link preview failed!")
            sys.exit(1)
        return
    
    print("🔄 Post-deployment initialization detected")
    
    # Step 1: Wait for bridge startup and sync
    print("\n" + "=" * 40)
    print("STEP 1: Bridge Startup & Sync")
    print("=" * 40)
    
    if not wait_for_bridge_startup():
        print("❌ Bridge startup failed!")
        sys.exit(1)
    
    # Step 2: Test bridge functionality
    print("\n" + "=" * 40)
    print("STEP 2: Bridge Functionality Test")
    print("=" * 40)
    
    if not run_command("python3 /app/test_bridge.py", "Testing WhatsApp bridge functionality"):
        print("❌ Post-deployment failed: Bridge test failed!")
        sys.exit(1)
    
    # Step 3: Run initial link preview
    print("\n" + "=" * 40)
    print("STEP 3: Initial Link Preview")
    print("=" * 40)
    
    if not run_initial_link_preview():
        print("❌ Post-deployment failed: Initial link preview failed!")
        sys.exit(1)
    
    # Step 4: Success
    print("\n" + "=" * 60)
    print("✅ POST-DEPLOYMENT FLOW COMPLETED SUCCESSFULLY!")
    print("=" * 60)
    print("📱 WhatsApp bridge is functioning")
    print("🔗 Link preview system is operational")
    print("⏰ System ready for Railway cron automation")
    print("🔄 Next execution will be triggered by Railway cron")

if __name__ == "__main__":
    main() 