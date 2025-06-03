#!/usr/bin/env python3

import requests
import sys
import os

def check_bridge_health():
    """Check if the WhatsApp bridge is healthy and responsive."""
    try:
        # Check if bridge is responding
        response = requests.get("http://localhost:8080/api/send", timeout=5)
        
        # Even if it returns an error, as long as it responds, the service is up
        if response.status_code in [200, 400, 405]:  # 405 = Method Not Allowed for GET on POST endpoint
            print("✅ WhatsApp Bridge is healthy")
            return True
        else:
            print(f"❌ Bridge responded with unexpected status: {response.status_code}")
            return False
            
    except requests.exceptions.ConnectionError:
        print("❌ Cannot connect to WhatsApp Bridge")
        return False
    except requests.exceptions.Timeout:
        print("❌ WhatsApp Bridge timeout")
        return False
    except Exception as e:
        print(f"❌ Health check error: {e}")
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

def main():
    """Main health check function."""
    print("🔍 Running health check...")
    
    # Check files first
    if not check_files():
        sys.exit(1)
    
    # Check bridge health
    if not check_bridge_health():
        sys.exit(1)
    
    print("✅ All health checks passed")
    sys.exit(0)

if __name__ == "__main__":
    main() 