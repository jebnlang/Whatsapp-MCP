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
WHATSAPP_API_BASE_URL = os.getenv("WHATSAPP_API_BASE_URL", "http://localhost:8080/api") # Get from Env
DEFAULT_DELAY = float(os.getenv("DEFAULT_DELAY", "3.0")) # Increased default delay due to web requests
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

# --- Helper function to get quoted message text (limited length) ---
def get_quoted_message_text(db_path, quoted_id, chat_jid):
    """Fetches the content of the original message being replied to."""
    # Basic validation
    if not quoted_id or not chat_jid:
        return None, None # Return None for both sender and content
        
    conn = None
    try:
        conn = sqlite3.connect(db_path)
        cursor = conn.cursor()
        # Fetch sender and content of the quoted message
        cursor.execute("""
            SELECT sender, content 
            FROM messages 
            WHERE id = ? AND chat_jid = ?
        """, (quoted_id, chat_jid))
        result = cursor.fetchone()
        if result:
            # Return sender JID and the content
            return result[0], result[1] 
        else:
            # Quoted message might be too old or not synced
            print(f"    Quoted message ID {quoted_id} not found in DB for chat {chat_jid}.")
            return None, None
    except sqlite3.Error as e:
        print(f"  Database error fetching quoted message {quoted_id}: {e}")
        return None, None
    finally:
        if conn:
            conn.close()


# --- Main Logic (Modified) ---

def main():
    # Update description
    parser = argparse.ArgumentParser(description="Finds links in source WhatsApp groups/dates, attempts to fetch preview data, and forwards to a selected destination group.")
    # DB Path can still be an argument for local testing, but will default to env var
    parser.add_argument("--db-path", type=str, default=os.getenv("WHATSAPP_DB_PATH", "store/messages.db"), help="Path to the WhatsApp messages.db file.")
    parser.add_argument("--delay", type=float, default=DEFAULT_DELAY, help=f"Delay between forwarding messages (default: {DEFAULT_DELAY}).")
    args = parser.parse_args()

    # --- Get Configuration from Environment Variables ---
    destination_group_jid = os.getenv("DESTINATION_GROUP_JID")
    source_group_jids_str = os.getenv("SOURCE_GROUP_JIDS")

    if not destination_group_jid:
        print("Error: DESTINATION_GROUP_JID environment variable not set.")
        sys.exit(1)
    if not source_group_jids_str:
        print("Error: SOURCE_GROUP_JIDS environment variable not set.")
        sys.exit(1)

    selected_source_group_jids = [jid.strip() for jid in source_group_jids_str.split(',') if jid.strip()]
    if not selected_source_group_jids:
        print("Error: No valid source group JIDs found in SOURCE_GROUP_JIDS environment variable.")
        sys.exit(1)

    print(f"Configuration:")
    print(f"  Database Path: {args.db_path}")
    print(f"  Destination Group JID: {destination_group_jid}")
    print(f"  Source Group JIDs: {selected_source_group_jids}")
    print(f"  Delay: {args.delay}s")
    print(f"  API Base URL: {WHATSAPP_API_BASE_URL}")


    # --- Get Groups (for JID to Name mapping) ---
    print("\nFetching available groups for name mapping...")
    groups_list = get_groups(args.db_path)
    if not groups_list:
        print("Warning: No groups found in the database for name mapping. Using JIDs as names.")
        group_jid_to_name = {}
    else:
        group_jid_to_name = {jid: name for jid, name in groups_list}

    destination_group_name = group_jid_to_name.get(destination_group_jid, destination_group_jid)
    print(f"  Messages will be forwarded to: {destination_group_name} ({destination_group_jid})")

    print("  Scanning the following groups for links:")
    for source_jid in selected_source_group_jids:
        source_name_display = group_jid_to_name.get(source_jid, source_jid)
        print(f"  - {source_name_display} ({source_jid})")


    # --- Date Selection (Automated for "Today") ---
    today_str = datetime.now().strftime('%Y-%m-%d')
    start_date_str = today_str
    end_date_str = today_str # The script logic correctly handles end_date to include the whole day
    print(f"\nProcessing messages for date: {today_str}")
    # --- End Date Selection ---

    # --- Message Finding, Metadata Fetching, and Forwarding ---
    total_processed = 0
    total_forwarded_with_preview = 0
    total_forwarded_text_only = 0
    
    print("\nStarting message search and processing...")
    for group_jid in selected_source_group_jids:
        # --- Get Source Group Name ---
        source_group_name = group_jid_to_name.get(group_jid, group_jid) # Fallback to JID if name somehow missing
        print(f"--- Checking source group: {source_group_name} ({group_jid}) ---")
        
        # --- Fetch all messages for the group/date first --- 
        conn = None
        all_messages_in_range = []
        try:
            conn = sqlite3.connect(args.db_path)
            cursor = conn.cursor()
            # Update query to select new reply columns
            query = """ 
                SELECT content, timestamp, is_reply, quoted_message_id, quoted_sender 
                FROM messages 
                WHERE chat_jid = ? AND content IS NOT NULL 
            """ 
            params = [group_jid]
            # Append date conditions
            if start_date_str: query += " AND datetime(timestamp) >= datetime(?) "; params.append(start_date_str + "T00:00:00")
            if end_date_str: query += " AND datetime(timestamp) < datetime(?) "; params.append((datetime.strptime(end_date_str, '%Y-%m-%d') + timedelta(days=1)).isoformat())
            query += " ORDER BY timestamp"
            
            cursor.execute(query, params)
            all_messages_in_range = cursor.fetchall()
            print(f"  Found {len(all_messages_in_range)} total messages in date range for this group.")
            
        except sqlite3.Error as e:
            print(f"  Database error fetching messages for source group {group_jid}: {e}")
            # If we can't fetch messages, we definitely can't forward any or send a header
            continue # Skip to next group if DB error occurs
        finally:
            if conn:
                conn.close()
                
        # --- Filter messages to only include those with links --- 
        messages_with_links = []
        for msg_data in all_messages_in_range:
            message_content = msg_data[0] # Content is the first element
            if extract_links(message_content):
                messages_with_links.append(msg_data)
                
        print(f"  Found {len(messages_with_links)} messages containing links.")
        
        # --- Conditionally Send Header and Process Link Messages --- 
        if messages_with_links: # Only proceed if there are links to forward
            # Send Header Message for the Group (with bold name)
            # header_message = f"--- Following links forwarded from group: *{source_group_name}* ---"
            # Try simpler format without --- to see if bold works
            header_message = f"Links forwarded from group: *{source_group_name}*"
            print(f"  Sending header message to {destination_group_name}: '{header_message}'") # Log the exact header being sent
            send_whatsapp_message(destination_group_jid, header_message)
            # Add a small delay so the header stands out
            print("    Waiting 1 second after header...")
            time.sleep(1.0) 
        
            # Process ONLY the messages that contain links
            # Unpack new columns from the filtered data
            for message_content, message_timestamp, is_reply, quoted_id, quoted_sender_jid in messages_with_links:
                total_processed += 1 # Increment here as we are now actually processing it
                print(f"\nProcessing message from {message_timestamp}...")
                
                # --- DEBUG: Print raw reply info from DB --- 
                # This debug line might be less useful now that we pre-filter, but keep for now
                print(f"    DEBUG: is_reply={is_reply} (type: {type(is_reply)}), quoted_id='{quoted_id}', quoted_sender='{quoted_sender_jid}'")
                # --- END DEBUG --- 
                
                # Links are guaranteed to exist here because we filtered
                links = extract_links(message_content) 
                first_link = links[0]
                print(f"    DEBUG: Found link: {first_link}") # Keep this debug line
                
                # --- Get Reply Context --- 
                reply_prefix = "" # Start with empty prefix
                if is_reply and quoted_id:
                     # --- DEBUG: Entering reply processing --- 
                     print(f"    DEBUG: Attempting to process as reply.")
                     # --- END DEBUG --- 
                     print(f"    Message is a reply to ID: {quoted_id} from {quoted_sender_jid}")
                     # Fetch the quoted message text
                     quoted_sender_display = quoted_sender_jid.split('@')[0] if quoted_sender_jid else "Unknown"
                     _q_sender, quoted_text = get_quoted_message_text(args.db_path, quoted_id, group_jid) # Fetch from the same group JID
                     if quoted_text:
                         # Use full quoted text, remove newline replacement and limit
                         # snippet = quoted_text.strip().replace('\n', ' ')[:60] # Limit length
                         full_quoted = quoted_text.strip() # Keep original newlines if desired, or replace with space
                         # reply_prefix = f"[Replying to {quoted_sender_display}: \"{snippet}...\"]\n---\n" 
                         reply_prefix = f"[Replying to {quoted_sender_display}: \"{full_quoted}\"]\n---\n"
                     else:
                         reply_prefix = f"[Replying to {quoted_sender_display}]\n---\n" # Prefix even if text isn't found
                elif is_reply:
                     # --- DEBUG: is_reply is true but quoted_id is missing --- 
                     print(f"    DEBUG: is_reply is true, but quoted_id is missing/empty ('{quoted_id}'). Cannot fetch context.")
                     # --- END DEBUG --- 
                else:
                     # --- DEBUG: Not a reply --- 
                     print(f"    DEBUG: Not a reply (is_reply={is_reply}).")
                     # --- END DEBUG --- 
                     pass # Not a reply
                # --- End Get Reply Context ---
                
                # Fetch metadata for preview
                metadata = fetch_link_metadata(first_link)
                temp_image_path = None
                success = False
                
                try: # Use try/finally to ensure temp file cleanup
                    if metadata and metadata.get('image_url'):
                        temp_image_path = download_image_temp(metadata['image_url'])
                        
                        if temp_image_path:
                            # Construct text message with metadata AND reply prefix
                            # preview_text = f"{metadata.get('title', '')}\n{metadata.get('description', '')}\n{first_link}".strip()
                            # CHANGE: Always use original message content for the text part, even with image
                            final_text_to_send = reply_prefix + message_content # Prepend reply info
                            # Send image + text to the DESTINATION group
                            success = send_whatsapp_message(destination_group_jid, final_text_to_send, media_path=temp_image_path)
                            if success: total_forwarded_with_preview += 1
                        else:
                            print("    Image download failed, falling back to text only.")
                            final_text_to_send = reply_prefix + message_content # Prepend reply info to original content
                            success = send_whatsapp_message(destination_group_jid, final_text_to_send)
                            if success: total_forwarded_text_only += 1
                    else:
                        print("    No image metadata found or fetch failed, sending text only.")
                        final_text_to_send = reply_prefix + message_content # Prepend reply info to original content
                        success = send_whatsapp_message(destination_group_jid, final_text_to_send)
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
            # End of loop for messages_with_links
            print(f"--- Finished processing source group {source_group_name} ({group_jid}) ---") # Use name here too
        else:
            # If no messages with links were found, print a message and move to the next group
            print(f"  No link-containing messages found for group {source_group_name}. Skipping header and forwarding.")
            # No need to print "Finished processing" if nothing was processed

    print(f"\nWorkflow complete.")
    print(f"  Messages processed: {total_processed}")
    print(f"  Forwarded with image+text attempt: {total_forwarded_with_preview}")
    print(f"  Forwarded with text only fallback: {total_forwarded_text_only}")
    print(f"  (All forwards sent to group: {destination_group_name} [{destination_group_jid}])")

if __name__ == "__main__":
    main() 