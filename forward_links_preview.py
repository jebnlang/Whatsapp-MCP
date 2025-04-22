# forward_links_preview.py
import sqlite3
import re
import sys
import argparse
from datetime import datetime, timedelta
import os
import json
import time
import requests
from bs4 import BeautifulSoup # For parsing HTML
import tempfile # For temporary image files
import shutil # For saving image data

# --- Configuration ---
# RECIPIENT_JID = "972526060403@s.whatsapp.net" # Removed hardcoded recipient
WHATSAPP_API_BASE_URL = "http://localhost:8080/api"
DEFAULT_DELAY = 3.0 # Increased default delay due to web requests
MAX_WHATSAPP_MESSAGE_LENGTH = 1500 # For warning only
REQUESTS_TIMEOUT = 10 # Timeout for fetching URLs/images
# Mimic a browser User-Agent
REQUESTS_HEADERS = {
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36'
}

# --- Database and Helper Functions ---

def get_groups(db_path):
    """Get a list of all groups in the database."""
    # ... (Same as in forward_links.py) ...
    conn = None
    try:
        conn = sqlite3.connect(db_path)
        cursor = conn.cursor()
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
    # ... (Same as in forward_links.py) ...
    if not text:
        return []
    url_pattern = r'https?://[^\s<>"\']+'
    return re.findall(url_pattern, text)

# --- New Metadata Fetching Functions ---

def fetch_link_metadata(url):
    """Fetches a URL and attempts to extract Open Graph metadata."""
    print(f"    Fetching metadata for: {url}")
    metadata = {'title': None, 'description': None, 'image_url': None}
    try:
        response = requests.get(url, timeout=REQUESTS_TIMEOUT, headers=REQUESTS_HEADERS, allow_redirects=True)
        response.raise_for_status()

        content_type = response.headers.get('content-type', '').lower()
        if 'html' not in content_type:
            print(f"      Content type is not HTML ({content_type}), skipping metadata parse.")
            return metadata # Return empty if not HTML

        soup = BeautifulSoup(response.content, 'html.parser')

        og_title = soup.find('meta', property='og:title')
        og_description = soup.find('meta', property='og:description')
        og_image = soup.find('meta', property='og:image')

        if og_title and og_title.get('content'):
            metadata['title'] = og_title['content'].strip()
            print(f"      Found title: {metadata['title'][:50]}...")
        if og_description and og_description.get('content'):
            metadata['description'] = og_description['content'].strip()
            print(f"      Found description: {metadata['description'][:50]}...")
        if og_image and og_image.get('content'):
            metadata['image_url'] = og_image['content'].strip()
            print(f"      Found image URL: {metadata['image_url']}")

        # Fallback for title if OG title is missing
        if not metadata['title'] and soup.title and soup.title.string:
            metadata['title'] = soup.title.string.strip()
            print(f"      Found fallback title: {metadata['title'][:50]}...")
            
        return metadata

    except requests.exceptions.Timeout:
        print(f"      Error: Timeout fetching metadata from {url}")
    except requests.exceptions.RequestException as e:
        print(f"      Error fetching metadata from {url}: {e}")
    except Exception as e:
        print(f"      Error parsing metadata from {url}: {e}")
        
    return metadata # Return whatever was found, even on error

def download_image_temp(image_url):
    """Downloads an image from a URL and saves it to a temporary file."""
    print(f"      Attempting to download image: {image_url}")
    temp_file_path = None
    try:
        response = requests.get(image_url, stream=True, timeout=REQUESTS_TIMEOUT, headers=REQUESTS_HEADERS)
        response.raise_for_status()

        # Check content type
        content_type = response.headers.get('content-type', '').lower()
        if not content_type.startswith('image/'):
            print(f"        Error: URL content type is not image ({content_type})")
            return None

        # Get suffix from content-type (e.g., .jpg, .png)
        suffix = "." + content_type.split('/')[-1] if '/' in content_type else ".tmp"
        if ";" in suffix: # Handle cases like image/jpeg; charset=... 
             suffix = suffix.split(";")[0]
             
        # Create a temporary file with the correct suffix
        with tempfile.NamedTemporaryFile(delete=False, suffix=suffix) as temp_file:
            temp_file_path = temp_file.name
            # Save the image data to the temp file
            shutil.copyfileobj(response.raw, temp_file)
            print(f"        Image downloaded successfully to temporary file: {temp_file_path}")
            return temp_file_path
            
    except requests.exceptions.Timeout:
        print(f"        Error: Timeout downloading image {image_url}")
    except requests.exceptions.RequestException as e:
        print(f"        Error downloading image {image_url}: {e}")
    except Exception as e:
        print(f"        Error saving image {image_url}: {e}")
        # Clean up temp file if created but writing failed
        if temp_file_path and os.path.exists(temp_file_path):
            os.remove(temp_file_path)
            
    return None # Return None if any error occurred


# --- WhatsApp Sending Function (Modified) ---

def send_whatsapp_message(recipient_jid, message_text, media_path=None):
    """Sends a message via the WhatsApp bridge API, optionally with media."""
    action = "Forwarding text message" if not media_path else "Forwarding image and text"
    print(f"  {action} to {recipient_jid}...")

    if message_text and len(message_text) > MAX_WHATSAPP_MESSAGE_LENGTH:
        print(f"    Warning: Text length ({len(message_text)} chars) exceeds limit. Might be truncated/fail.")

    try:
        url = f"{WHATSAPP_API_BASE_URL}/send"
        payload = {"recipient": recipient_jid, "message": message_text}
        if media_path:
             # Check if file exists before adding to payload
             if os.path.exists(media_path):
                  print(f"    Attaching media: {media_path}")
                  payload["media_path"] = media_path
                  # Optionally add filename if needed by bridge, but likely derived from path
                  # payload["filename"] = os.path.basename(media_path)
             else:
                  print(f"    Error: Media file path not found: {media_path}")
                  media_path = None # Don't send media path if file doesn't exist
                  print("    Falling back to sending text only.")
                  
        response = requests.post(url, json=payload, timeout=30) # Increased timeout for potential uploads

        # ... (Rest of response handling is the same as forward_links.py) ...
        if response.status_code == 200:
            try:
                result = response.json()
                if result.get("success", False):
                    print(f"    Sent successfully! Response: {result.get('message', '')}")
                    return True
                else:
                    print(f"    Bridge reported failure: {result.get('message', 'Unknown error')}")
                    return False
            except json.JSONDecodeError:
                print(f"    Error parsing success response from bridge (Status 200, Non-JSON body): {response.text}")
                return False
        else:
            print(f"    Error sending: HTTP {response.status_code} - {response.text}")
            return False
    except requests.exceptions.Timeout:
        print("    Error: Timeout connecting to WhatsApp bridge.")
        return False
    except requests.exceptions.RequestException as e:
        print(f"    Error connecting to WhatsApp bridge: {e}")
        return False
    except Exception as e:
        print(f"    Unexpected error during WhatsApp send: {e}")
        return False

# --- Main Logic (Modified) ---

def main():
    # Update description
    parser = argparse.ArgumentParser(description="Finds links in source WhatsApp groups/dates, attempts to fetch preview data, and forwards to a selected destination group.")
    parser.add_argument("--db-path", type=str, required=True, help="Path to the WhatsApp messages.db file.")
    parser.add_argument("--delay", type=float, default=DEFAULT_DELAY, help=f"Delay between forwarding messages (default: {DEFAULT_DELAY}).")
    args = parser.parse_args()

    # --- Get Groups --- 
    print("Fetching available groups...")
    groups_list = get_groups(args.db_path)
    if not groups_list:
        print("Error: No groups found in the database.")
        return

    print("\nAvailable groups:")
    for i, (jid, name) in enumerate(groups_list, 1):
        print(f"{i}. {name} ({jid})")
        
    # --- Destination Group Selection --- 
    destination_group_jid = None
    destination_group_name = None
    while not destination_group_jid:
        try:
            raw_dest_selection = input("\nEnter the number of the group to FORWARD MESSAGES TO: ").strip()
            dest_idx = int(raw_dest_selection) - 1
            if 0 <= dest_idx < len(groups_list):
                destination_group_jid = groups_list[dest_idx][0]
                destination_group_name = groups_list[dest_idx][1]
                print(f"  Messages will be forwarded to: {destination_group_name} ({destination_group_jid})")
            else:
                print(f"Error: Invalid group number. Please enter a number between 1 and {len(groups_list)}.")
        except ValueError:
            print("Error: Invalid input. Please enter a single number.")
        except Exception as e:
             print(f"An unexpected error during destination group selection: {e}")

    # --- Source Group Selection --- 
    selected_source_group_jids = []
    while not selected_source_group_jids:
        try:
            raw_selection = input("\nEnter the number(s) of the group(s) to SCAN FOR LINKS (comma-separated): ").strip()
            selected_indices = [int(x.strip()) - 1 for x in raw_selection.split(',') if x.strip()]
            valid_selection = True
            temp_selected_jids = []
            print("  Scanning the following groups for links:")
            for idx in selected_indices:
                if 0 <= idx < len(groups_list):
                    source_jid = groups_list[idx][0]
                    source_name = groups_list[idx][1]
                    temp_selected_jids.append(source_jid)
                    print(f"  - {source_name} ({source_jid})")
                else:
                    print(f"Error: Invalid group number {idx + 1} in source list.")
                    valid_selection = False
                    temp_selected_jids = [] # Reset list on error
                    break
            if valid_selection and temp_selected_jids:
                selected_source_group_jids = temp_selected_jids
            elif valid_selection:
                 print("Error: No source groups selected.")
        except ValueError:
            print("Error: Invalid input. Please enter numbers separated by commas.")
        except Exception as e:
             print(f"An unexpected error during source group selection: {e}")
             
    # print(f"\nSelected source group JIDs: {selected_source_group_jids}") # Redundant now

    # --- Interactive Date Selection --- 
    today_str = datetime.now().strftime('%Y-%m-%d')
    start_date_str = None
    while True:
        start_date_input = input(f"\nEnter start date (YYYY-MM-DD), 'today', or leave empty [default: no limit]: ").strip().lower()
        if not start_date_input: start_date_str = None; break
        elif start_date_input == 'today': start_date_str = today_str; print(f"  Using start date: {start_date_str}"); break
        else:
            try: datetime.strptime(start_date_input, '%Y-%m-%d'); start_date_str = start_date_input; break
            except ValueError: print("Invalid format. Please use YYYY-MM-DD, 'today', or leave empty.")
            
    end_date_str = None
    while True:
        end_date_input = input(f"Enter end date (YYYY-MM-DD), 'today', or leave empty [default: no limit]: ").strip().lower()
        if not end_date_input: end_date_str = None; break
        elif end_date_input == 'today': end_date_str = today_str; print(f"  Using end date: {end_date_str}"); break
        else:
            try: datetime.strptime(end_date_input, '%Y-%m-%d'); end_date_str = end_date_input; break
            except ValueError: print("Invalid format. Please use YYYY-MM-DD, 'today', or leave empty.")
            
    # --- Message Finding, Metadata Fetching, and Forwarding --- 
    total_processed = 0
    total_forwarded_with_preview = 0
    total_forwarded_text_only = 0
    
    print("\nStarting message search and processing...")
    # Loop through SOURCE groups
    for group_jid in selected_source_group_jids:
        print(f"--- Processing source group {group_jid} ---")
        
        # Fetch all messages for the group/date first
        conn = None
        all_messages_in_range = []
        try:
            conn = sqlite3.connect(args.db_path)
            cursor = conn.cursor()
            query = "SELECT content, timestamp FROM messages WHERE chat_jid = ? AND content IS NOT NULL" # Fetch timestamp too for info
            params = [group_jid]
            if start_date_str: query += " AND datetime(timestamp) >= datetime(?) "; params.append(start_date_str + "T00:00:00")
            if end_date_str: query += " AND datetime(timestamp) < datetime(?) "; params.append((datetime.strptime(end_date_str, '%Y-%m-%d') + timedelta(days=1)).isoformat())
            query += " ORDER BY timestamp"
            
            cursor.execute(query, params)
            all_messages_in_range = cursor.fetchall()
            print(f"  Found {len(all_messages_in_range)} total messages in date range for this group.")
            
        except sqlite3.Error as e:
            print(f"  Database error fetching messages for source group {group_jid}: {e}")
            continue # Skip to next group if DB error occurs
        finally:
            if conn:
                conn.close()
                
        # Process messages found
        for message_content, message_timestamp in all_messages_in_range:
            total_processed += 1
            print(f"\nProcessing message from {message_timestamp}...")
            links = extract_links(message_content)
            
            if not links:
                print("  No links found in this message, skipping.")
                continue

            first_link = links[0]
            print(f"  Found link: {first_link}")
            
            # Fetch metadata
            metadata = fetch_link_metadata(first_link)
            temp_image_path = None
            success = False
            
            try: # Use try/finally to ensure temp file cleanup
                if metadata and metadata.get('image_url'):
                    temp_image_path = download_image_temp(metadata['image_url'])
                    
                    if temp_image_path:
                        # Construct text message with metadata
                        preview_text = f"{metadata.get('title', '')}\n{metadata.get('description', '')}\n{first_link}".strip()
                        # Send image + text to the DESTINATION group
                        success = send_whatsapp_message(destination_group_jid, preview_text, media_path=temp_image_path)
                        if success: total_forwarded_with_preview += 1
                    else:
                        print("    Image download failed, falling back to text only.")
                        # Send original content to the DESTINATION group
                        success = send_whatsapp_message(destination_group_jid, message_content) 
                        if success: total_forwarded_text_only += 1
                else:
                    print("    No image metadata found or fetch failed, sending text only.")
                    # Send original content to the DESTINATION group
                    success = send_whatsapp_message(destination_group_jid, message_content) 
                    if success: total_forwarded_text_only += 1
            finally:
                 # Clean up temporary image file if it exists
                 if temp_image_path and os.path.exists(temp_image_path):
                     try:
                         os.remove(temp_image_path)
                         print(f"    Cleaned up temporary file: {temp_image_path}")
                     except OSError as e:
                         print(f"    Error cleaning up temporary file {temp_image_path}: {e}")

            # Delay between processing each message
            print(f"    Waiting for {args.delay} seconds...")
            time.sleep(args.delay)
            
        print(f"--- Finished processing source group {group_jid} ---")

    print(f"\nWorkflow complete.")
    print(f"  Messages processed: {total_processed}")
    print(f"  Forwarded with image+text attempt: {total_forwarded_with_preview}")
    print(f"  Forwarded with text only fallback: {total_forwarded_text_only}")
    print(f"  (All forwards sent to group: {destination_group_name} [{destination_group_jid}])")

if __name__ == "__main__":
    main() 