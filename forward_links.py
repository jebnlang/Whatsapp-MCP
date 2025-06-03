import sqlite3
import re
import sys
import argparse
from datetime import datetime, timedelta
import os
import json
import time
import requests

# --- Configuration ---
# Remove hardcoded recipient, will use environment variable
WHATSAPP_API_BASE_URL = "http://localhost:8080/api"
DEFAULT_DELAY = 2.0 # Seconds between forwarding messages
MAX_WHATSAPP_MESSAGE_LENGTH = 1500 # For warning only
LAST_RUN_FILE = "last_forward_run.txt"

# --- Timestamp Tracking Functions ---

def get_last_run_time():
    """Get timestamp of last successful run, or 24 hours ago if first run."""
    try:
        if os.path.exists(LAST_RUN_FILE):
            with open(LAST_RUN_FILE, 'r') as f:
                timestamp_str = f.read().strip()
                last_run = datetime.fromisoformat(timestamp_str)
                print(f"Found last run timestamp: {last_run}")
                return last_run
    except Exception as e:
        print(f"Warning: Could not read last run time: {e}")
    
    # Fallback: 24 hours ago for first run
    fallback_time = datetime.now() - timedelta(days=1)
    print(f"No previous run found, using fallback time: {fallback_time}")
    return fallback_time

def update_last_run_time(timestamp=None):
    """Update the last run timestamp file."""
    if timestamp is None:
        timestamp = datetime.now()
    
    try:
        with open(LAST_RUN_FILE, 'w') as f:
            f.write(timestamp.isoformat())
        print(f"Updated last run time to: {timestamp}")
        return True
    except Exception as e:
        print(f"Warning: Could not update last run time: {e}")
        return False

# --- Group Resolution Functions ---

def find_group_by_name(db_path, group_name):
    """Find a group JID by its name (partial match)."""
    try:
        conn = sqlite3.connect(db_path)
        cursor = conn.cursor()
        
        cursor.execute("""
            SELECT 
                jid,
                name
            FROM chats
            WHERE jid LIKE '%@g.us'
            AND LOWER(name) LIKE LOWER(?)
            ORDER BY name
        """, (f"%{group_name}%",))
        
        groups = cursor.fetchall()
        return groups
        
    except sqlite3.Error as e:
        print(f"Database error: {e}")
        return []
    finally:
        if 'conn' in locals():
            conn.close()

def resolve_group_names_to_jids(db_path, group_names):
    """
    Resolve a list of group names to their JIDs.
    Returns a list of (jid, name) tuples for found groups.
    """
    resolved_groups = []
    
    for group_name in group_names:
        group_name = group_name.strip()
        print(f"Resolving group name: '{group_name}'")
        
        matches = find_group_by_name(db_path, group_name)
        
        if not matches:
            print(f"  Warning: No group found matching '{group_name}'")
            continue
        
        if len(matches) == 1:
            jid, name = matches[0]
            print(f"  Found: {name} -> {jid}")
            resolved_groups.append((jid, name))
        else:
            print(f"  Multiple groups found matching '{group_name}':")
            for jid, name in matches:
                print(f"    - {name} ({jid})")
            
            # Use the first match (alphabetically first)
            jid, name = matches[0]
            print(f"  Using first match: {name} -> {jid}")
            resolved_groups.append((jid, name))
    
    return resolved_groups

def resolve_recipient_to_jid(recipient_input, db_path):
    """
    Resolves recipient input to a JID.
    - If recipient looks like a JID (contains @), return as-is
    - If recipient looks like a phone number (digits only), convert to JID
    - If recipient is a group name, resolve to group JID
    """
    if not recipient_input:
        return None
    
    recipient_input = recipient_input.strip()
    
    # If already a JID, return as-is
    if "@" in recipient_input:
        print(f"Recipient appears to be a JID: {recipient_input}")
        return recipient_input
    
    # If it's all digits (phone number), convert to JID
    if recipient_input.replace("+", "").replace("-", "").replace(" ", "").isdigit():
        phone_jid = recipient_input.replace("+", "").replace("-", "").replace(" ", "") + "@s.whatsapp.net"
        print(f"Converted phone number to JID: {phone_jid}")
        return phone_jid
    
    # Otherwise, treat as group name and try to resolve it
    print(f"Attempting to resolve group name '{recipient_input}' to JID...")
    resolved_groups = resolve_group_names_to_jids(db_path, [recipient_input])
    
    if resolved_groups:
        jid, name = resolved_groups[0]
        print(f"Resolved recipient group: {name} -> {jid}")
        return jid
    else:
        print(f"Could not resolve recipient '{recipient_input}' to a valid JID")
        return None

# --- Database and Helper Functions ---

def get_groups(db_path):
    """Get a list of all groups in the database."""
    conn = None
    try:
        conn = sqlite3.connect(db_path)
        cursor = conn.cursor()
        # Use multi-line string for readability
        cursor.execute("""
            SELECT
                jid,
                name
            FROM chats
            WHERE jid LIKE '%@g.us'
            ORDER BY name
        """)
        groups = cursor.fetchall()
        return groups
    except sqlite3.Error as e:
        print(f"Database error getting groups: {e}")
        return []
    finally:
        if conn:
            conn.close()

def extract_links(text):
    """Extract URLs from text using regex. Returns a list of URLs found."""
    if not text:
        return []
    # Use raw string and corrected pattern
    url_pattern = r'https?://[^\s<>"\']+'
    return re.findall(url_pattern, text)

def find_messages_with_links(db_path, group_jid, start_datetime=None, end_datetime=None):
    """
    Finds messages containing links in a specific group within a datetime range.
    Returns a list of full message content strings.
    
    Args:
        db_path: Path to the SQLite database file
        group_jid: The JID of the group chat
        start_datetime: Optional start datetime object
        end_datetime: Optional end datetime object
    """
    conn = None
    messages_content = []
    try:
        conn = sqlite3.connect(db_path)
        cursor = conn.cursor()

        # Use multi-line string for query readability
        query = """
            SELECT content
            FROM messages
            WHERE
                chat_jid = ?
                AND content IS NOT NULL
        """
        params = [group_jid]

        # Add datetime conditions using ISO format
        if start_datetime:
            start_iso = start_datetime.isoformat()
            query += " AND datetime(timestamp) >= datetime(?) "
            params.append(start_iso)

        if end_datetime:
            end_iso = end_datetime.isoformat()
            query += " AND datetime(timestamp) < datetime(?) "
            params.append(end_iso)

        query += " ORDER BY timestamp" # Keep order for potential troubleshooting

        print(f"  Searching DB for messages in group {group_jid}...")
        print(f"    Time range: {start_datetime} to {end_datetime}")

        cursor.execute(query, params)
        all_messages_in_range = cursor.fetchall()
        print(f"    Found {len(all_messages_in_range)} total messages in time range for group.")

        # Filter messages that contain links
        for msg_row in all_messages_in_range:
            content = msg_row[0]
            if content and extract_links(content): # Check if extract_links finds anything
                 messages_content.append(content)

        print(f"    Found {len(messages_content)} messages containing links.")
        return messages_content

    except sqlite3.Error as e:
        print(f"Database error finding messages: {e}")
        return []
    except Exception as e:
         print(f"Error finding messages: {e}")
         return []
    finally:
        if conn:
            conn.close()

# --- WhatsApp Sending Function ---

def send_whatsapp_message(recipient_jid, message_text):
    """Sends a message via the WhatsApp bridge API."""
    print(f"  Forwarding message to {recipient_jid}...")

    if len(message_text) > MAX_WHATSAPP_MESSAGE_LENGTH:
        print(f"    Warning: Message length ({len(message_text)} chars) exceeds {MAX_WHATSAPP_MESSAGE_LENGTH}. Might be truncated/fail.")

    try:
        url = f"{WHATSAPP_API_BASE_URL}/send"
        payload = {"recipient": recipient_jid, "message": message_text}
        # Set a reasonable timeout
        response = requests.post(url, json=payload, timeout=20)

        # Check HTTP status code first
        if response.status_code == 200:
            try:
                # Try to parse JSON only on success
                result = response.json()
                if result.get("success", False):
                    print(f"    Forwarded successfully! Response: {result.get('message', '')}")
                    return True
                else:
                    print(f"    Bridge reported failure: {result.get('message', 'Unknown error')}")
                    return False
            except json.JSONDecodeError:
                # Handle cases where 200 OK is returned but body is not valid JSON
                print(f"    Error parsing success response from bridge (Status 200, Non-JSON body): {response.text}")
                return False
        else:
            # Log error for non-200 responses
            print(f"    Error sending: HTTP {response.status_code} - {response.text}")
            return False
    except requests.exceptions.Timeout:
        print("    Error: Timeout connecting to WhatsApp bridge.")
        return False
    except requests.exceptions.RequestException as e:
        # Catch broader connection/request errors
        print(f"    Error connecting to WhatsApp bridge: {e}")
        return False
    except Exception as e:
        # Catch any other unexpected errors
        print(f"    Unexpected error during WhatsApp send: {e}")
        return False

# --- Main Logic ---

def main():
    parser = argparse.ArgumentParser(description="Interactively select WhatsApp groups/dates and forward messages containing links.")
    parser.add_argument("--db-path", type=str, required=True, help="Path to the WhatsApp messages.db file.")
    parser.add_argument("--delay", type=float, default=DEFAULT_DELAY, help=f"Delay in seconds between forwarding messages (default: {DEFAULT_DELAY}).")
    args = parser.parse_args()

    # --- Interactive Group Selection ---
    print("Fetching available groups...")
    groups_list = get_groups(args.db_path)
    if not groups_list:
        print("Error: No groups found in the database.")
        return

    print("\nAvailable groups:")
    for i, (jid, name) in enumerate(groups_list, 1):
        print(f"{i}. {name} ({jid})")

    selected_groups_jids = []
    while not selected_groups_jids:
        try:
            # Use triple quotes for multi-line prompt clarity if needed, but single line is fine here
            raw_selection = input("\nEnter the numbers of the groups to search (comma-separated): ").strip()
            selected_indices = [int(x.strip()) - 1 for x in raw_selection.split(',') if x.strip()]
            valid_selection = True
            temp_selected_jids = []
            for idx in selected_indices:
                if 0 <= idx < len(groups_list):
                    temp_selected_jids.append(groups_list[idx][0]) # Store only JID
                else:
                    print(f"Error: Invalid group number {idx + 1}.")
                    valid_selection = False
                    break
            if valid_selection and temp_selected_jids:
                selected_groups_jids = temp_selected_jids
            elif valid_selection:
                 print("Error: No groups selected.")
        except ValueError:
            print("Error: Invalid input. Please enter numbers separated by commas.")
        except Exception as e:
             print(f"An unexpected error during group selection: {e}")

    print(f"\nSelected group JIDs: {selected_groups_jids}")

    # --- Interactive Date Selection ---
    today_str = datetime.now().strftime('%Y-%m-%d')
    start_date_str = None
    while True:
        start_date_input = input(f"\nEnter start date (YYYY-MM-DD), 'today', or leave empty [default: no limit]: ").strip().lower()
        if not start_date_input:
            start_date_str = None
            break
        elif start_date_input == 'today':
            start_date_str = today_str
            print(f"  Using start date: {start_date_str}")
            break
        else:
            try:
                datetime.strptime(start_date_input, '%Y-%m-%d')
                start_date_str = start_date_input
                break
            except ValueError:
                print("Invalid format. Please use YYYY-MM-DD, 'today', or leave empty.")

    end_date_str = None
    while True:
        end_date_input = input(f"Enter end date (YYYY-MM-DD), 'today', or leave empty [default: no limit]: ").strip().lower()
        if not end_date_input:
            end_date_str = None
            break
        elif end_date_input == 'today':
            end_date_str = today_str
            print(f"  Using end date: {end_date_str}")
            break
        else:
            try:
                datetime.strptime(end_date_input, '%Y-%m-%d')
                end_date_str = end_date_input
                break
            except ValueError:
                print("Invalid format. Please use YYYY-MM-DD, 'today', or leave empty.")

    # --- Message Finding and Forwarding ---
    total_forwarded = 0
    print("\nStarting message search and forwarding...")
    for group_jid in selected_groups_jids:
        messages_to_forward = find_messages_with_links(args.db_path, group_jid, start_date_str, end_date_str)

        if messages_to_forward:
            print(f"--- Forwarding {len(messages_to_forward)} messages from group {group_jid} ---")
            for message_content in messages_to_forward:
                success = send_whatsapp_message(RECIPIENT_JID, message_content)
                # Increment counter regardless of success for tracking attempts
                total_forwarded += 1
                # Delay even if sending failed to avoid hammering the API
                print(f"    Waiting for {args.delay} seconds...")
                time.sleep(args.delay)
            print(f"--- Finished forwarding for group {group_jid} ---")
        else:
            print(f"--- No link messages found to forward for group {group_jid} in the specified range. ---")

    print(f"\nWorkflow complete. Attempted to forward {total_forwarded} messages.")

if __name__ == "__main__":
    main() 