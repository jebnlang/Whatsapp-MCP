#!/usr/bin/env python3

import requests
import json
import time
import sys
import os

# WhatsApp Bridge API Configuration
BRIDGE_API_BASE_URL = "http://localhost:8080/api"
TEST_RECIPIENT = "972526060403@s.whatsapp.net"
TEST_MESSAGE = "hello world"

def wait_for_bridge(max_wait_seconds=60):
    """Wait for WhatsApp bridge to be ready."""
    print("🔍 Waiting for WhatsApp bridge to be ready...")
    
    for attempt in range(max_wait_seconds):
        try:
            response = requests.get(f"{BRIDGE_API_BASE_URL}/status", timeout=5)
            if response.status_code == 200:
                status = response.json()
                if status.get("connected", False):
                    print("✅ WhatsApp bridge is connected and ready!")
                    return True
                else:
                    print(f"⏳ Bridge starting... (attempt {attempt + 1}/{max_wait_seconds})")
            else:
                print(f"⏳ Bridge not ready... (attempt {attempt + 1}/{max_wait_seconds})")
        except requests.RequestException:
            print(f"⏳ Waiting for bridge... (attempt {attempt + 1}/{max_wait_seconds})")
        
        time.sleep(1)
    
    print("❌ Bridge failed to become ready within timeout")
    return False

def send_test_message():
    """Send test message to verify bridge functionality."""
    try:
        print(f"📱 Sending test message to {TEST_RECIPIENT}")
        print(f"💬 Message: '{TEST_MESSAGE}'")
        
        url = f"{BRIDGE_API_BASE_URL}/send"
        payload = {
            "recipient": TEST_RECIPIENT,
            "message": TEST_MESSAGE,
        }
        
        response = requests.post(url, json=payload, timeout=10)
        
        if response.status_code == 200:
            result = response.json()
            success = result.get("success", False)
            message = result.get("message", "Unknown response")
            
            if success:
                print("✅ Test message sent successfully!")
                print(f"📋 Response: {message}")
                return True
            else:
                print(f"❌ Failed to send message: {message}")
                return False
        else:
            print(f"❌ HTTP Error {response.status_code}: {response.text}")
            return False
            
    except requests.RequestException as e:
        print(f"❌ Request error: {str(e)}")
        return False
    except json.JSONDecodeError as e:
        print(f"❌ JSON decode error: {str(e)}")
        return False
    except Exception as e:
        print(f"❌ Unexpected error: {str(e)}")
        return False

def main():
    """Main bridge test function."""
    print("🚀 Starting WhatsApp Bridge Test")
    print("=" * 50)
    
    # Step 1: Wait for bridge to be ready
    if not wait_for_bridge(max_wait_seconds=120):
        print("❌ Bridge test failed: Bridge not ready")
        sys.exit(1)
    
    # Step 2: Send test message
    if not send_test_message():
        print("❌ Bridge test failed: Could not send test message")
        sys.exit(1)
    
    print("=" * 50)
    print("✅ Bridge test completed successfully!")
    print("📱 WhatsApp bridge is functioning correctly")
    return True

if __name__ == "__main__":
    main() 