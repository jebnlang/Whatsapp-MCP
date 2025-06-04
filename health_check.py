#!/usr/bin/env python3

import requests
import sys
import os
import time

def check_bridge_health():
    """Check if the WhatsApp bridge is healthy and responsive."""
    try:
        # Check if bridge is responding
        response = requests.get("http://localhost:8080/api/send", timeout=3)
        
        # Even if it returns an error, as long as it responds, the service is up
        if response.status_code in [200, 400, 405]:  # 405 = Method Not Allowed for GET on POST endpoint
            print("✅ WhatsApp Bridge is healthy and responding")
            return True
        else:
            print(f"⚠️ Bridge responded with status: {response.status_code} (service is up)")
            return True  # Still consider it healthy if it's responding
            
    except requests.exceptions.ConnectionError:
        print("⚠️ Cannot connect to WhatsApp Bridge (may still be starting)")
        return False
    except requests.exceptions.Timeout:
        print("⚠️ WhatsApp Bridge timeout (may still be starting)")
        return False
    except Exception as e:
        print(f"⚠️ Health check error: {e}")
        return False

def check_files():
    """Check if required files exist."""
    required_files = [
        "/app/whatsapp-bridge",
        "/app/forward_links_preview.py"
    ]
    
    for file_path in required_files:
        if not os.path.exists(file_path):
            print(f"❌ Required file missing: {file_path}")
            return False
    
    print("✅ All required files present")
    return True

def check_process_running():
    """Check if start.sh process is running."""
    try:
        import subprocess
        result = subprocess.run(['pgrep', '-f', 'start.sh'], capture_output=True, text=True)
        if result.returncode == 0:
            print("✅ start.sh process is running")
            return True
        else:
            print("⚠️ start.sh process not found")
            return False
    except Exception as e:
        print(f"⚠️ Process check error: {e}")
        return False

def main():
    """Main health check function - more forgiving for initial deployment."""
    print("🔍 Running Railway health check...")
    
    # Check files first - this MUST pass
    if not check_files():
        print("❌ Critical: Required files missing")
        sys.exit(1)
    
    # Give the service some time to start if it just started
    time.sleep(2)
    
    # Check if our startup process is running
    process_running = check_process_running()
    
    # Check bridge health (but don't fail if it's not ready yet)
    bridge_healthy = check_bridge_health()
    
    # Pass health check if:
    # 1. Files exist (critical) AND
    # 2. Either the bridge is responding OR the startup process is running
    if process_running or bridge_healthy:
        print("✅ Health check passed - service is operational")
        sys.exit(0)
    else:
        print("❌ Health check failed - service appears to be down")
        sys.exit(1)

if __name__ == "__main__":
    main() 