import requests
import json

WHATSAPP_API_BASE_URL = "http://localhost:8080/api"

def send_message(recipient, message):
    """Send a WhatsApp message to the specified recipient."""
    try:
        url = f"{WHATSAPP_API_BASE_URL}/send"
        payload = {
            "recipient": recipient,
            "message": message,
        }
        
        response = requests.post(url, json=payload)
        
        # Check if the request was successful
        if response.status_code == 200:
            result = response.json()
            return result.get("success", False), result.get("message", "Unknown response")
        else:
            return False, f"Error: HTTP {response.status_code} - {response.text}"
            
    except requests.RequestException as e:
        return False, f"Request error: {str(e)}"
    except json.JSONDecodeError:
        return False, f"Error parsing response: {response.text}"
    except Exception as e:
        return False, f"Unexpected error: {str(e)}"

# Send message to Hamster
recipient = "972507217120@s.whatsapp.net"  # Hamster's JID
message = "Hi, this is a MCP messagew"

print("Sending message to Hamster...")
success, message_response = send_message(recipient, message)
print(f"Success: {success}")
print(f"Response: {message_response}") 