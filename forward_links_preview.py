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
# Remove hardcoded recipient, will use environment variable
WHATSAPP_API_BASE_URL = "http://localhost:8080/api"
DEFAULT_DELAY = 3.0 # Increased default delay due to web requests
MAX_WHATSAPP_MESSAGE_LENGTH = 1500 # For warning only
REQUESTS_TIMEOUT = 10 # Timeout for fetching URLs/images

# Mimic a browser User-Agent
REQUESTS_HEADERS = {
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36'
}

# --- (Removed timestamp tracking functions as we now use automatic time detection) ---

# --- New Function: Get Last Message Time from Destination Group ---

def get_last_message_time_in_group(db_path, group_jid):
    """Get the timestamp of the last REAL message sent in a specific group (excludes system messages like joins/leaves)."""
    conn = None
    try:
        conn = sqlite3.connect(db_path)
        cursor = conn.cursor()
        
        cursor.execute("""
            SELECT MAX(timestamp) as last_message_time
            FROM messages 
            WHERE chat_jid = ?
            AND content IS NOT NULL 
            AND content != ''
            AND sender IS NOT NULL 
            AND sender != ''
            AND content NOT LIKE '%joined%'
            AND content NOT LIKE '%left%'
            AND content NOT LIKE '%added%'
            AND content NOT LIKE '%removed%'
            AND content NOT LIKE '%changed the group%'
            AND content NOT LIKE '%changed this group%'
            AND content NOT LIKE '%created this group%'
            AND content NOT LIKE '%created group%'
            AND content NOT LIKE '%joined using%'
            AND content NOT LIKE '%became an admin%'
            AND content NOT LIKE '%is no longer an admin%'
            AND content NOT LIKE '%requested to join%'
            AND content NOT LIKE '%invitation%'
            AND content NOT LIKE '%invited%'
        """, (group_jid,))
        
        result = cursor.fetchone()
        if result and result[0]:
            # Convert the timestamp string back to datetime
            last_message_time = datetime.fromisoformat(result[0].replace('Z', '+00:00') if result[0].endswith('Z') else result[0])
            # If timezone-aware, convert to naive for consistency
            if last_message_time.tzinfo is not None:
                last_message_time = last_message_time.replace(tzinfo=None)
            print(f"  Last REAL user message in destination group was at: {last_message_time}")
            print(f"  (System messages like joins/leaves/requests are excluded)")
            return last_message_time
        else:
            # No real user messages found in the group, use a default fallback (e.g., 7 days ago)
            fallback_time = datetime.now() - timedelta(days=7)
            print(f"  No real user messages found in destination group, using fallback time: {fallback_time}")
            print(f"  (System messages like joins/leaves/requests are excluded)")
            return fallback_time
            
    except sqlite3.Error as e:
        print(f"  Database error getting last real user message time: {e}")
        # Return fallback time on error
        fallback_time = datetime.now() - timedelta(days=7)
        print(f"  Using fallback time due to error: {fallback_time}")
        return fallback_time
    except Exception as e:
        print(f"  Error parsing timestamp: {e}")
        fallback_time = datetime.now() - timedelta(days=7)
        print(f"  Using fallback time due to parsing error: {fallback_time}")
        return fallback_time
    finally:
        if conn:
            conn.close()

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
    parser = argparse.ArgumentParser(description="Finds links in source WhatsApp groups since the last message in the destination group, fetches preview data, and forwards to the destination group.")
    parser.add_argument("--db-path", type=str, required=True, help="Path to the WhatsApp messages.db file.")
    parser.add_argument("--delay", type=float, default=DEFAULT_DELAY, help=f"Delay between forwarding messages (default: {DEFAULT_DELAY}).")
    parser.add_argument("--non-interactive", action="store_true", help="Force non-interactive mode using environment variables.")
    parser.add_argument("--config", type=str, help="Path to JSON configuration file with group settings.")
    parser.add_argument("--start-date", type=str, help="Manual start date (YYYY-MM-DD HH:MM) - overrides automatic detection.")
    parser.add_argument("--end-date", type=str, help="Manual end date (YYYY-MM-DD HH:MM) - defaults to now if start-date specified.")
    args = parser.parse_args()

    # Check if we should run in config file mode
    if args.config:
        print("🤖 Running in config file mode...")
        success = run_config_mode(args.db_path, args.config, args.delay)
        if success:
            print("✅ Config-based execution completed successfully!")
        else:
            print("❌ Config-based execution failed!")
            sys.exit(1)
        return

    # Check if we should run in non-interactive mode
    # Either --non-interactive flag is set OR environment variables are present
    has_env_vars = os.getenv("WHATSAPP_FORWARD_RECIPIENT") and os.getenv("WHATSAPP_SOURCE_GROUPS")
    
    if args.non_interactive or has_env_vars:
        print("🤖 Running in non-interactive mode...")
        success = run_non_interactive_mode(args.db_path, args.delay)
        if success:
            print("✅ Non-interactive execution completed successfully!")
        else:
            print("❌ Non-interactive execution failed!")
            sys.exit(1)
        return

    print("👤 Running in interactive mode...")
    
    # --- Get Groups --- 
    print("Fetching available groups...")
    groups_list = get_groups(args.db_path)
    if not groups_list:
        print("Error: No groups found in the database.")
        return

    # --- Create a JID to Name mapping for later lookup ---
    group_jid_to_name = {jid: name for jid, name in groups_list}

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

    # --- Determine Time Range (Manual or Automatic) ---
    if args.start_date:
        print(f"\nUsing manual date range...")
        try:
            start_datetime = datetime.strptime(args.start_date, "%Y-%m-%d %H:%M")
            if args.end_date:
                end_datetime = datetime.strptime(args.end_date, "%Y-%m-%d %H:%M")
            else:
                end_datetime = datetime.now()
            print(f"  Manual time range specified:")
        except ValueError as e:
            print(f"Error: Invalid date format. Use YYYY-MM-DD HH:MM format. Error: {e}")
            return
    else:
        print(f"\nDetermining time range based on last message in destination group...")
        start_datetime = get_last_message_time_in_group(args.db_path, destination_group_jid)
        end_datetime = datetime.now()
        print(f"  Automatic time range detected:")
    
    print(f"    From: {start_datetime}")
    print(f"    To: {end_datetime}")
    print(f"    Duration: {end_datetime - start_datetime}")

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
             
    # --- Message Finding, Metadata Fetching, and Forwarding --- 
    total_processed = 0
    total_forwarded_with_preview = 0
    total_forwarded_text_only = 0
    
    # Track seen links to avoid duplicates
    seen_links = set()
    total_duplicates_skipped = 0
    
    print("\nStarting message search and processing...")
    for group_jid in selected_source_group_jids:
        # --- Get Source Group Name ---
        source_group_name = group_jid_to_name.get(group_jid, group_jid) # Fallback to JID if name somehow missing
        print(f"--- Checking source group: {source_group_name} ({group_jid}) ---")
        
        # --- Fetch all messages for the group/time range --- 
        conn = None
        all_messages_in_range = []
        try:
            conn = sqlite3.connect(args.db_path)
            cursor = conn.cursor()
            # Query using datetime objects
            query = """ 
                SELECT content, timestamp, is_reply, quoted_message_id, quoted_sender 
                FROM messages 
                WHERE chat_jid = ? AND content IS NOT NULL 
                AND datetime(timestamp) >= datetime(?) 
                AND datetime(timestamp) < datetime(?) 
                ORDER BY timestamp
            """ 
            params = [group_jid, start_datetime.isoformat(), end_datetime.isoformat()]
            
            cursor.execute(query, params)
            all_messages_in_range = cursor.fetchall()
            print(f"  Found {len(all_messages_in_range)} total messages in time range for this group.")
            
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
                print(f"    DEBUG: is_reply={is_reply} (type: {type(is_reply)}), quoted_id='{quoted_id}', quoted_sender='{quoted_sender_jid}'")
                
                # Links are guaranteed to exist here because we filtered
                links = extract_links(message_content) 
                first_link = links[0]
                print(f"    DEBUG: Found link: {first_link}") # Keep this debug line
                
                # Check for duplicate links
                if first_link in seen_links:
                    print(f"    SKIPPING: Link already processed from another group")
                    total_duplicates_skipped += 1
                    continue
                
                # Add link to seen set
                seen_links.add(first_link)
                
                # --- Get Reply Context --- 
                reply_prefix = "" # Start with empty prefix
                if is_reply and quoted_id:
                     print(f"    DEBUG: Attempting to process as reply.")
                     print(f"    Message is a reply to ID: {quoted_id} from {quoted_sender_jid}")
                     # Fetch the quoted message text
                     quoted_sender_display = quoted_sender_jid.split('@')[0] if quoted_sender_jid else "Unknown"
                     _q_sender, quoted_text = get_quoted_message_text(args.db_path, quoted_id, group_jid) # Fetch from the same group JID
                     if quoted_text:
                         full_quoted = quoted_text.strip() # Keep original newlines if desired, or replace with space
                         reply_prefix = f"[Replying to {quoted_sender_display}: \"{full_quoted}\"]\n---\n"
                     else:
                         reply_prefix = f"[Replying to {quoted_sender_display}]\n---\n" # Prefix even if text isn't found
                elif is_reply:
                     print(f"    DEBUG: is_reply is true, but quoted_id is missing/empty ('{quoted_id}'). Cannot fetch context.")
                else:
                     print(f"    DEBUG: Not a reply (is_reply={is_reply}).")
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
                            # Always use original message content for the text part, even with image
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

    print(f"\nWorkflow complete.")
    print(f"  Messages processed: {total_processed}")
    print(f"  Forwarded with image+text attempt: {total_forwarded_with_preview}")
    print(f"  Forwarded with text only fallback: {total_forwarded_text_only}")
    print(f"  Duplicate links skipped: {total_duplicates_skipped}")
    print(f"  (All forwards sent to group: {destination_group_name} [{destination_group_jid}])")

def run_non_interactive_mode(db_path, delay):
    """
    Run in non-interactive mode using environment variables and automatic time detection.
    """
    print("Running in non-interactive mode using environment variables...")
    
    # Get recipient from environment variable
    recipient_env = os.getenv("WHATSAPP_FORWARD_RECIPIENT")
    if not recipient_env:
        print("Error: WHATSAPP_FORWARD_RECIPIENT environment variable is not set.")
        print("Please set it to a phone number, group name, or JID.")
        return False
    
    print(f"Recipient from env var: {recipient_env}")
    
    # Resolve recipient to JID
    destination_group_jid = resolve_recipient_to_jid(recipient_env, db_path)
    if not destination_group_jid:
        print(f"Error: Could not resolve recipient '{recipient_env}' to a valid JID.")
        return False
    
    destination_group_name = recipient_env  # Use original input as display name
    print(f"Messages will be forwarded to: {destination_group_name} ({destination_group_jid})")
    
    # Get source groups from environment variable
    source_groups_env = os.getenv("WHATSAPP_SOURCE_GROUPS")
    if not source_groups_env:
        print("Error: WHATSAPP_SOURCE_GROUPS environment variable is not set.")
        print("Please set it to a comma-separated list of group names.")
        return False
    
    # Parse group names
    group_names = [name.strip() for name in source_groups_env.split(',') if name.strip()]
    if not group_names:
        print("Error: No valid group names found in WHATSAPP_SOURCE_GROUPS.")
        return False
    
    print(f"Source groups from env var: {group_names}")
    
    # Resolve group names to JIDs
    source_groups_data = resolve_group_names_to_jids(db_path, group_names)
    
    if not source_groups_data:
        print("Error: Could not resolve any group names to valid groups.")
        return False
    
    print(f"\nResolved {len(source_groups_data)} source groups:")
    for jid, name in source_groups_data:
        print(f"- {name} ({jid})")
    
    # Use automatic time detection based on destination group's last message
    print(f"\nDetermining time range based on last message in destination group...")
    start_datetime = get_last_message_time_in_group(db_path, destination_group_jid)
    end_datetime = datetime.now()
    
    print(f"  Time range for link collection:")
    print(f"    From: {start_datetime}")
    print(f"    To: {end_datetime}")
    print(f"    Duration: {end_datetime - start_datetime}")
    
    # Show summary and ask for confirmation
    print(f"\n" + "="*80)
    print(f"📋 AUTOMATION SUMMARY - Please review before proceeding:")
    print(f"="*80)
    print(f"🎯 DESTINATION GROUP (where links will be sent):")
    print(f"   {destination_group_name}")
    print(f"   JID: {destination_group_jid}")
    print(f"")
    print(f"🔍 SOURCE GROUPS (scanning for links):")
    for i, (jid, name) in enumerate(source_groups_data, 1):
        print(f"   {i}. {name}")
        print(f"      JID: {jid}")
    print(f"")
    print(f"📅 TIME RANGE:")
    print(f"   From: {start_datetime.strftime('%Y-%m-%d %H:%M:%S')}")
    print(f"   To:   {end_datetime.strftime('%Y-%m-%d %H:%M:%S')}")
    print(f"   Duration: {end_datetime - start_datetime}")
    print(f"")
    print(f"⚙️  SETTINGS:")
    print(f"   Delay between messages: {delay} seconds")
    print(f"   Rich previews: Enabled (images downloaded when available)")
    print(f"   Duplicate filtering: Enabled")
    print(f"="*80)
    
    # Ask for confirmation
    while True:
        try:
            confirmation = input("\n🤖 Do you want to proceed with this automation? (y/n): ").strip().lower()
            if confirmation in ['y', 'yes']:
                print("✅ Proceeding with link forwarding automation...")
                break
            elif confirmation in ['n', 'no']:
                print("❌ Automation cancelled by user.")
                return True  # Return True because user choice to cancel is not an error
            else:
                print("Please enter 'y' or 'n'")
        except KeyboardInterrupt:
            print("\n❌ Automation cancelled by user (Ctrl+C)")
            return True
        except Exception as e:
            print(f"Error reading input: {e}")
            return False
    
    # Create a JID to Name mapping
    group_jid_to_name = {jid: name for jid, name in source_groups_data}
    selected_source_group_jids = [jid for jid, name in source_groups_data]
    
    # Process messages (using existing logic from main() but with datetime objects)
    total_processed = 0
    total_forwarded_with_preview = 0
    total_forwarded_text_only = 0
    
    # Track seen links to avoid duplicates
    seen_links = set()
    total_duplicates_skipped = 0
    
    print("\nStarting message search and processing...")
    for group_jid in selected_source_group_jids:
        source_group_name = group_jid_to_name.get(group_jid, group_jid)
        print(f"--- Checking source group: {source_group_name} ({group_jid}) ---")
        
        # Fetch all messages for the group/time range
        conn = None
        all_messages_in_range = []
        try:
            conn = sqlite3.connect(db_path)
            cursor = conn.cursor()
            
            # Modified query to use datetime objects
            query = """ 
                SELECT content, timestamp, is_reply, quoted_message_id, quoted_sender 
                FROM messages 
                WHERE chat_jid = ? AND content IS NOT NULL 
                AND datetime(timestamp) >= datetime(?) 
                AND datetime(timestamp) < datetime(?) 
                ORDER BY timestamp
            """ 
            params = [group_jid, start_datetime.isoformat(), end_datetime.isoformat()]
            
            cursor.execute(query, params)
            all_messages_in_range = cursor.fetchall()
            print(f"  Found {len(all_messages_in_range)} total messages in time range for this group.")
            
        except sqlite3.Error as e:
            print(f"  Database error fetching messages for source group {group_jid}: {e}")
            continue
        finally:
            if conn:
                conn.close()
                
        # Filter messages to only include those with links
        messages_with_links = []
        for msg_data in all_messages_in_range:
            message_content = msg_data[0]
            if extract_links(message_content):
                messages_with_links.append(msg_data)
                
        print(f"  Found {len(messages_with_links)} messages containing links.")
        
        # Process messages with links (reusing existing logic)
        if messages_with_links:
            # Send Header Message for the Group
            header_message = f"Links forwarded from group: *{source_group_name}*"
            print(f"  Sending header message to {destination_group_name}: '{header_message}'")
            send_whatsapp_message(destination_group_jid, header_message)
            print("    Waiting 1 second after header...")
            time.sleep(1.0) 
        
            # Process ONLY the messages that contain links
            for message_content, message_timestamp, is_reply, quoted_id, quoted_sender_jid in messages_with_links:
                total_processed += 1
                print(f"\nProcessing message from {message_timestamp}...")
                
                print(f"    DEBUG: is_reply={is_reply} (type: {type(is_reply)}), quoted_id='{quoted_id}', quoted_sender='{quoted_sender_jid}'")
                
                links = extract_links(message_content) 
                first_link = links[0]
                print(f"    DEBUG: Found link: {first_link}")
                
                # Check for duplicate links
                if first_link in seen_links:
                    print(f"    SKIPPING: Link already processed from another group")
                    total_duplicates_skipped += 1
                    continue
                
                # Add link to seen set
                seen_links.add(first_link)
                
                # Get Reply Context
                reply_prefix = ""
                if is_reply and quoted_id:
                     print(f"    DEBUG: Attempting to process as reply.")
                     print(f"    Message is a reply to ID: {quoted_id} from {quoted_sender_jid}")
                     quoted_sender_display = quoted_sender_jid.split('@')[0] if quoted_sender_jid else "Unknown"
                     _q_sender, quoted_text = get_quoted_message_text(db_path, quoted_id, group_jid)
                     if quoted_text:
                         full_quoted = quoted_text.strip()
                         reply_prefix = f"[Replying to {quoted_sender_display}: \"{full_quoted}\"]\n---\n"
                     else:
                         reply_prefix = f"[Replying to {quoted_sender_display}]\n---\n"
                elif is_reply:
                     print(f"    DEBUG: is_reply is true, but quoted_id is missing/empty ('{quoted_id}'). Cannot fetch context.")
                else:
                     print(f"    DEBUG: Not a reply (is_reply={is_reply}).")
                
                # Fetch metadata for preview
                metadata = fetch_link_metadata(first_link)
                temp_image_path = None
                success = False
                
                try:
                    if metadata and metadata.get('image_url'):
                        temp_image_path = download_image_temp(metadata['image_url'])
                        
                        if temp_image_path:
                            final_text_to_send = reply_prefix + message_content
                            success = send_whatsapp_message(destination_group_jid, final_text_to_send, media_path=temp_image_path)
                            if success: total_forwarded_with_preview += 1
                        else:
                            print("    Image download failed, falling back to text only.")
                            final_text_to_send = reply_prefix + message_content
                            success = send_whatsapp_message(destination_group_jid, final_text_to_send)
                            if success: total_forwarded_text_only += 1
                    else:
                        print("    No image metadata found or fetch failed, sending text only.")
                        final_text_to_send = reply_prefix + message_content
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
                print(f"    Waiting for {delay} seconds...")
                time.sleep(delay)
                
            print(f"--- Finished processing source group {source_group_name} ({group_jid}) ---")
        else:
            print(f"  No link-containing messages found for group {source_group_name}. Skipping header and forwarding.")

    print(f"\nWorkflow complete.")
    print(f"  Messages processed: {total_processed}")
    print(f"  Forwarded with image+text attempt: {total_forwarded_with_preview}")
    print(f"  Forwarded with text only fallback: {total_forwarded_text_only}")
    print(f"  Duplicate links skipped: {total_duplicates_skipped}")
    print(f"  (All forwards sent to: {destination_group_name} [{destination_group_jid}])")
    
    return True

def run_config_mode(db_path, config_path, delay_override=None):
    """
    Run in config file mode using a JSON configuration file.
    """
    print(f"Loading configuration from: {config_path}")
    
    # Load configuration file
    try:
        with open(config_path, 'r', encoding='utf-8') as f:
            config = json.load(f)
    except FileNotFoundError:
        print(f"Error: Configuration file not found: {config_path}")
        return False
    except json.JSONDecodeError as e:
        print(f"Error: Invalid JSON in configuration file: {e}")
        return False
    except Exception as e:
        print(f"Error: Failed to read configuration file: {e}")
        return False
    
    # Validate configuration structure
    if "destination_group" not in config:
        print("Error: Configuration missing 'destination_group' section")
        return False
    
    if "source_groups" not in config:
        print("Error: Configuration missing 'source_groups' section")
        return False
    
    destination_config = config["destination_group"]
    if "jid" not in destination_config:
        print("Error: Destination group missing 'jid' field")
        return False
    
    destination_group_jid = destination_config["jid"]
    destination_group_name = destination_config.get("name", destination_group_jid)
    
    print(f"Destination group: {destination_group_name} ({destination_group_jid})")
    
    # Get enabled source groups
    source_groups_data = []
    enabled_count = 0
    
    for group_config in config["source_groups"]:
        if not group_config.get("enabled", True):  # Default to enabled if not specified
            continue
        
        if "jid" not in group_config:
            print(f"Warning: Source group missing 'jid' field, skipping: {group_config}")
            continue
        
        jid = group_config["jid"]
        name = group_config.get("name", jid)
        source_groups_data.append((jid, name))
        enabled_count += 1
    
    if not source_groups_data:
        print("Error: No enabled source groups found in configuration")
        return False
    
    print(f"\nFound {enabled_count} enabled source groups:")
    for jid, name in source_groups_data:
        print(f"- {name} ({jid})")
    
    # Use delay from config file or command line override
    if delay_override is not None:
        delay = delay_override
    else:
        delay = config.get("settings", {}).get("delay_between_messages", DEFAULT_DELAY)
    
    print(f"Using delay between messages: {delay} seconds")
    
    # Use automatic time detection based on destination group's last message
    print(f"\nDetermining time range based on last message in destination group...")
    start_datetime = get_last_message_time_in_group(db_path, destination_group_jid)
    end_datetime = datetime.now()
    
    print(f"  Time range for link collection:")
    print(f"    From: {start_datetime}")
    print(f"    To: {end_datetime}")
    print(f"    Duration: {end_datetime - start_datetime}")
    
    # Create a JID to Name mapping
    group_jid_to_name = {jid: name for jid, name in source_groups_data}
    selected_source_group_jids = [jid for jid, name in source_groups_data]
    
    # Process messages (reusing existing logic from run_non_interactive_mode)
    total_processed = 0
    total_forwarded_with_preview = 0
    total_forwarded_text_only = 0
    
    # Track seen links to avoid duplicates
    seen_links = set()
    total_duplicates_skipped = 0
    
    print("\nStarting message search and processing...")
    for group_jid in selected_source_group_jids:
        source_group_name = group_jid_to_name.get(group_jid, group_jid)
        print(f"--- Checking source group: {source_group_name} ({group_jid}) ---")
        
        # Fetch all messages for the group/time range
        conn = None
        all_messages_in_range = []
        try:
            conn = sqlite3.connect(db_path)
            cursor = conn.cursor()
            
            query = """ 
                SELECT content, timestamp, is_reply, quoted_message_id, quoted_sender 
                FROM messages 
                WHERE chat_jid = ? AND content IS NOT NULL 
                AND datetime(timestamp) >= datetime(?) 
                AND datetime(timestamp) < datetime(?) 
                ORDER BY timestamp
            """ 
            params = [group_jid, start_datetime.isoformat(), end_datetime.isoformat()]
            
            cursor.execute(query, params)
            all_messages_in_range = cursor.fetchall()
            print(f"  Found {len(all_messages_in_range)} total messages in time range for this group.")
            
        except sqlite3.Error as e:
            print(f"  Database error fetching messages for source group {group_jid}: {e}")
            continue
        finally:
            if conn:
                conn.close()
                
        # Filter messages to only include those with links
        messages_with_links = []
        for msg_data in all_messages_in_range:
            message_content = msg_data[0]
            if extract_links(message_content):
                messages_with_links.append(msg_data)
                
        print(f"  Found {len(messages_with_links)} messages containing links.")
        
        # Process messages with links (reusing existing logic)
        if messages_with_links:
            # Send Header Message for the Group
            header_message = f"Links forwarded from group: *{source_group_name}*"
            print(f"  Sending header message to {destination_group_name}: '{header_message}'")
            send_whatsapp_message(destination_group_jid, header_message)
            print("    Waiting 1 second after header...")
            time.sleep(1.0) 
        
            # Process ONLY the messages that contain links
            for message_content, message_timestamp, is_reply, quoted_id, quoted_sender_jid in messages_with_links:
                total_processed += 1
                print(f"\nProcessing message from {message_timestamp}...")
                
                print(f"    DEBUG: is_reply={is_reply} (type: {type(is_reply)}), quoted_id='{quoted_id}', quoted_sender='{quoted_sender_jid}'")
                
                links = extract_links(message_content) 
                first_link = links[0]
                print(f"    DEBUG: Found link: {first_link}")
                
                # Check for duplicate links
                if first_link in seen_links:
                    print(f"    SKIPPING: Link already processed from another group")
                    total_duplicates_skipped += 1
                    continue
                
                # Add link to seen set
                seen_links.add(first_link)
                
                # Get Reply Context
                reply_prefix = ""
                if is_reply and quoted_id:
                     print(f"    DEBUG: Attempting to process as reply.")
                     print(f"    Message is a reply to ID: {quoted_id} from {quoted_sender_jid}")
                     quoted_sender_display = quoted_sender_jid.split('@')[0] if quoted_sender_jid else "Unknown"
                     _q_sender, quoted_text = get_quoted_message_text(db_path, quoted_id, group_jid)
                     if quoted_text:
                         full_quoted = quoted_text.strip()
                         reply_prefix = f"[Replying to {quoted_sender_display}: \"{full_quoted}\"]\n---\n"
                     else:
                         reply_prefix = f"[Replying to {quoted_sender_display}]\n---\n"
                elif is_reply:
                     print(f"    DEBUG: is_reply is true, but quoted_id is missing/empty ('{quoted_id}'). Cannot fetch context.")
                else:
                     print(f"    DEBUG: Not a reply (is_reply={is_reply}).")
                
                # Fetch metadata for preview
                metadata = fetch_link_metadata(first_link)
                temp_image_path = None
                success = False
                
                try:
                    if metadata and metadata.get('image_url'):
                        temp_image_path = download_image_temp(metadata['image_url'])
                        
                        if temp_image_path:
                            final_text_to_send = reply_prefix + message_content
                            success = send_whatsapp_message(destination_group_jid, final_text_to_send, media_path=temp_image_path)
                            if success: total_forwarded_with_preview += 1
                        else:
                            print("    Image download failed, falling back to text only.")
                            final_text_to_send = reply_prefix + message_content
                            success = send_whatsapp_message(destination_group_jid, final_text_to_send)
                            if success: total_forwarded_text_only += 1
                    else:
                        print("    No image metadata found or fetch failed, sending text only.")
                        final_text_to_send = reply_prefix + message_content
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
                print(f"    Waiting for {delay} seconds...")
                time.sleep(delay)
                
            print(f"--- Finished processing source group {source_group_name} ({group_jid}) ---")
        else:
            print(f"  No link-containing messages found for group {source_group_name}. Skipping header and forwarding.")

    print(f"\nWorkflow complete.")
    print(f"  Messages processed: {total_processed}")
    print(f"  Forwarded with image+text attempt: {total_forwarded_with_preview}")
    print(f"  Forwarded with text only fallback: {total_forwarded_text_only}")
    print(f"  Duplicate links skipped: {total_duplicates_skipped}")
    print(f"  (All forwards sent to: {destination_group_name} [{destination_group_jid}])")
    
    return True

if __name__ == "__main__":
    main() 