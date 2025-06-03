import sqlite3
import re
import sys
import argparse
from datetime import datetime, timedelta
import os
import json
import time # Added for potential delays
import requests # Added for fetching URL content
import openai # Added for AI analysis

# --- OpenAI API Setup ---
# Use environment variable for API key instead of hardcoding
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")

if not OPENAI_API_KEY:
    print("Error: OPENAI_API_KEY environment variable is not set.")
    print("Please set your OpenAI API key as an environment variable.")
    exit(1)

try:
    client = openai.OpenAI(api_key=OPENAI_API_KEY)
except Exception as e:
    print(f"Error initializing OpenAI client: {e}")
    print("Please ensure the OpenAI library is installed and the API key is valid.")
    client = None

# Database path is now handled via args

def extract_links(text):
    """Extract URLs from text using regex."""
    if not text:
        return []
    # Regular expression pattern for URLs - Improved to capture more characters in path/query
    # This pattern aims to be more inclusive of characters often found in URLs
    url_pattern = r'https?://[^\s<>\"\'()]+'
    return re.findall(url_pattern, text)

def get_groups(db_path):
    """Get a list of all groups in the database."""
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
        print(f"Database error: {e}")
        return []
    finally:
        if 'conn' in locals():
            conn.close()

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

def get_links_from_group(db_path, group_jid, group_name, start_date=None, end_date=None):
    """
    Get links shared in a specific group within a date range.
    Includes messages from the start_date up to the end of the end_date.
    
    Args:
        db_path: Path to the SQLite database file
        group_jid: The JID of the group chat
        group_name: The name of the group chat
        start_date: Optional start date in 'YYYY-MM-DD' format
        end_date: Optional end date in 'YYYY-MM-DD' format
    """
    # --- DEBUGGING --- 
    print(f"\n--- Debugging get_links_from_group ---")
    print(f"  Database Path: {db_path}")
    print(f"  Group JID: {group_jid}")
    print(f"  Group Name: {group_name}")
    print(f"  Start Date Input: {start_date}")
    print(f"  End Date Input: {end_date}")
    # --- END DEBUGGING ---
    
    links_with_context = [] # Initialize here for clarity in case of early return
    conn = None # Initialize conn
    try:
        conn = sqlite3.connect(db_path)
        # Optional: Set row factory for dictionary access if needed later, but not required now
        # conn.row_factory = sqlite3.Row 
        cursor = conn.cursor()
        
        query = """
            SELECT 
                timestamp,
                sender,
                content
            FROM messages
            WHERE 
                chat_jid = ?
                AND content IS NOT NULL
        """
        
        params = [group_jid]
        
        if start_date:
            start_datetime_obj = datetime.strptime(start_date, '%Y-%m-%d')
            start_iso = start_datetime_obj.isoformat()
            # Apply datetime() function to both column and parameter
            query += " AND datetime(timestamp) >= datetime(?) "
            params.append(start_iso)
        
        if end_date:
            end_date_obj = datetime.strptime(end_date, '%Y-%m-%d')
            next_day_obj = end_date_obj + timedelta(days=1)
            end_iso_exclusive = next_day_obj.isoformat()
            # Apply datetime() function to both column and parameter
            query += " AND datetime(timestamp) < datetime(?) "
            params.append(end_iso_exclusive)
        
        query += " ORDER BY timestamp"
        
        # --- DEBUGGING --- 
        print(f"  Executing SQL Query:")
        print(f"    Query: {query}") # Query string now includes datetime()
        print(f"    Params: {params}")
        # --- END DEBUGGING ---
        
        cursor.execute(query, params)
        messages = cursor.fetchall()
        
        # --- DEBUGGING --- 
        print(f"  Messages fetched from DB: {len(messages)}")
        if messages:
             # Optional: Print first message timestamp for format check
             try:
                  first_ts = messages[0][0] # Assuming timestamp is the first column
                  print(f"    Timestamp of first fetched message: {first_ts} (Type: {type(first_ts)})")
             except IndexError:
                  print("    Could not access first message data.")
        # --- END DEBUGGING ---
        
        # Process messages to extract links (only if messages were found)
        # links_with_context = [] # Moved initialization up
        for msg in messages:
            timestamp, sender, content = msg
            
            # Extract links from message content
            links = extract_links(content)
            
            if links:
                # Convert ISO timestamp to readable format
                try:
                    dt = datetime.fromisoformat(timestamp)
                    formatted_time = dt.strftime("%Y-%m-%d %H:%M:%S")
                except ValueError:
                    formatted_time = timestamp # Keep original if parsing fails
                
                for link in links:
                    links_with_context.append({
                        'timestamp': formatted_time,
                        'sender': sender,
                        'link': link,
                        'message': content,
                        'group_name': group_name
                    })
        
        # --- DEBUGGING --- 
        print(f"  Links extracted after processing: {len(links_with_context)}")
        print(f"--- End Debugging get_links_from_group ---\n")
        # --- END DEBUGGING ---
        
        return links_with_context
        
    except sqlite3.Error as e:
        print(f"Database error in get_links_from_group: {e}")
        return []
    except ValueError as e:
         print(f"Date parsing error in get_links_from_group: {e}")
         return [] # Return empty list on date format error
    finally:
        if conn:
            conn.close()

def save_links_to_file(links, output_file):
    """Save links data to a JSON file."""
    # Always save as JSON
    with open(output_file, 'w', encoding='utf-8') as f: # Ensure UTF-8 encoding
        json.dump(links, f, indent=2, ensure_ascii=False) # Use ensure_ascii=False for Hebrew

# --- New AI Analysis Function --- 

def analyze_link(link_url, message_context):
    """Analyzes a given URL using OpenAI to extract purpose, type, and insights."""
    if not client:
        print("OpenAI client not initialized. Skipping analysis.")
        return {"purpose": "Error: OpenAI client not ready", "type": "Error", "insights": []}
        
    print(f"  Fetching content from: {link_url}")
    try:
        # Fetch URL content - use timeout, allow redirects, handle errors
        # Add a user-agent header to mimic a browser
        headers = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36'}
        response = requests.get(link_url, timeout=10, allow_redirects=True, headers=headers)
        response.raise_for_status() # Raise HTTPError for bad responses (4xx or 5xx)
        
        # Basic content type check - focus on HTML for now
        content_type = response.headers.get('content-type', '').lower()
        if 'html' in content_type:
            page_content = response.text[:15000] # Limit content length to avoid large prompts
            print("    Content fetched successfully (HTML).")
        else:
            print(f"    Content is not HTML ({content_type}), skipping content analysis.")
            page_content = "[Content is not HTML]"
            
    except requests.exceptions.Timeout:
        print(f"    Error: Timeout while fetching {link_url}")
        page_content = "[Error: Timeout fetching content]"
    except requests.exceptions.RequestException as e:
        print(f"    Error fetching {link_url}: {e}")
        page_content = f"[Error fetching content: {e}]"
    except Exception as e:
        print(f"    Unexpected error during fetch {link_url}: {e}")
        page_content = f"[Unexpected error fetching content: {e}]"

    print("  Requesting analysis from OpenAI...")
    try:
        # Construct prompt
        prompt_messages = [
            {
                "role": "system",
                "content": "You are an AI assistant analyzing shared links. Analyze the provided URL and message context. Respond ONLY with a JSON object containing three keys: 'purpose' (string: a brief summary of what the link is for), 'type' (string: one of Tool, Article, Social, Video, Code Repository, Other), and 'insights' (array of strings: 2-4 key bullet points about the link/content). If you cannot analyze the link or content reliably, return appropriate error messages within the JSON structure."
            },
            {
                "role": "user",
                "content": f"Analyze the following link:\nURL: {link_url}\nOriginal Message Context: {message_context}\n\nFetched Content Snippet (if relevant):\n```\n{page_content}\n```\n\nPlease provide the analysis in the specified JSON format."
            }
        ]

        # Make API call
        completion = client.chat.completions.create(
            model="gpt-3.5-turbo", # Or use "gpt-4" if preferred/available
            messages=prompt_messages,
            response_format={ "type": "json_object" } # Request JSON output
        )
        
        ai_response_content = completion.choices[0].message.content
        print("    OpenAI analysis received.")
        
        # Parse the JSON response from AI
        analysis_result = json.loads(ai_response_content)
        
        # Basic validation of the received structure
        if not all(k in analysis_result for k in ['purpose', 'type', 'insights']):
             print("    Warning: AI response missing expected keys.")
             return {"purpose": "Error: Malformed AI response", "type": "Error", "insights": [ai_response_content]} # Return raw response on error
             
        return analysis_result
        
    except openai.APIConnectionError as e:
        print(f"    OpenAI Error: Connection error: {e}")
        return {"purpose": f"Error: OpenAI Connection: {e}", "type": "Error", "insights": []}
    except openai.RateLimitError as e:
         print(f"    OpenAI Error: Rate limit exceeded: {e}")
         return {"purpose": f"Error: OpenAI Rate Limit: {e}", "type": "Error", "insights": []}
    except openai.APIStatusError as e:
        print(f"    OpenAI Error: API status error: {e}")
        return {"purpose": f"Error: OpenAI API Status {e.status_code}: {e.response}", "type": "Error", "insights": []}
    except json.JSONDecodeError:
        print(f"    Error: Failed to decode JSON response from AI: {ai_response_content}")
        return {"purpose": "Error: Invalid JSON from AI", "type": "Error", "insights": [ai_response_content] } # Return raw response
    except Exception as e:
        print(f"    Unexpected error during OpenAI analysis: {e}")
        return {"purpose": f"Error: Unexpected AI analysis error: {e}", "type": "Error", "insights": []}

def main():
    # Modify parser: remove group/date args, keep db-path and output
    parser = argparse.ArgumentParser(description="Interactively select WhatsApp groups, extract links, analyze them with AI, and save results to a JSON file.")
    parser.add_argument("--db-path", type=str, required=True, help="Path to the WhatsApp messages.db file")
    parser.add_argument("--output", type=str, help="Optional output JSON file name for enriched data")
    parser.add_argument("--delay", type=float, default=1.0, help="Delay in seconds between AI API calls (default: 1.0)")
    
    args = parser.parse_args()

    # --- Interactive Flow --- 
    
    # 1. Get and list groups
    print("Fetching available groups...")
    groups_list = get_groups(args.db_path)
    if not groups_list:
        print("Error: No groups found in the database.")
        return
        
    print("\nAvailable groups:")
    for i, (jid, name) in enumerate(groups_list, 1):
        print(f"{i}. {name} ({jid})")
        
    # 2. Prompt for group selection
    selected_groups_data = []
    while not selected_groups_data:
        try:
            raw_selection = input("\nEnter the numbers of the groups to search (comma-separated, e.g., 1,3,5): ")
            selected_indices = [int(x.strip()) - 1 for x in raw_selection.split(',') if x.strip()]
            
            # Validate indices
            valid_selection = True
            temp_selected_groups = []
            for idx in selected_indices:
                if 0 <= idx < len(groups_list):
                    temp_selected_groups.append(groups_list[idx])
                else:
                    print(f"Error: Invalid group number {idx + 1}. Please enter numbers between 1 and {len(groups_list)}.")
                    valid_selection = False
                    break
            
            if valid_selection and temp_selected_groups:
                selected_groups_data = temp_selected_groups
            elif valid_selection and not temp_selected_groups:
                 print("Error: No groups selected. Please enter at least one valid number.")
                 
        except ValueError:
            print("Error: Invalid input. Please enter numbers separated by commas.")
        except Exception as e:
             print(f"An unexpected error occurred during group selection: {e}")

    print("\nSelected groups:")
    for jid, name in selected_groups_data:
        print(f"- {name} ({jid})")

    # 3. Prompt for dates (with "today" option)
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
                # Validate format if not empty or 'today'
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
                # Validate format if not empty or 'today'
                datetime.strptime(end_date_input, '%Y-%m-%d')
                end_date_str = end_date_input
                break
            except ValueError:
                print("Invalid format. Please use YYYY-MM-DD, 'today', or leave empty.")

    # --- Link Extraction --- 
    
    all_extracted_links = []
    print("\nStarting link extraction...")
    for group_jid, group_name in selected_groups_data:
        print(f"- Searching in group: '{group_name}'")
        try:
            links_in_group = get_links_from_group(args.db_path, group_jid, group_name, start_date_str, end_date_str)
            if links_in_group:
                all_extracted_links.extend(links_in_group)
                print(f"  Found {len(links_in_group)} links in '{group_name}'.")
            else:
                 print(f"  No links found in '{group_name}' for the specified period.")
        except Exception as e:
             print(f"Error processing group {group_name} ({group_jid}): {e}")

    if not all_extracted_links:
        print("\nNo links found in any of the selected groups for the specified date range.")
        return
        
    print(f"\nExtracted {len(all_extracted_links)} links. Starting AI analysis...")

    # --- AI Enrichment --- 
    enriched_links = []
    for i, link_data in enumerate(all_extracted_links):
        print(f"\nAnalyzing link {i+1}/{len(all_extracted_links)}: {link_data['link']}")
        
        analysis = analyze_link(link_data['link'], link_data['message'])
        
        # Merge analysis into the original data
        link_data['ai_purpose'] = analysis.get('purpose', 'N/A')
        link_data['ai_type'] = analysis.get('type', 'N/A')
        link_data['ai_insights'] = analysis.get('insights', [])
        
        enriched_links.append(link_data)
        
        # Add a delay to avoid rate limiting
        print(f"Waiting for {args.delay} seconds...")
        time.sleep(args.delay)
        
    # --- Output --- 

    print(f"\nFinished analysis. Found a total of {len(enriched_links)} links with analysis attempts.")

    # Determine output file name for enriched data
    if args.output:
        # Ensure output file has .json extension if specified
        output_file = args.output if args.output.lower().endswith('.json') else args.output + '.json'
    else:
        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
        # Suggest a different name for enriched file
        output_file = f"enriched_links_{timestamp}.json" 
    
    # Save the enriched list to JSON
    try:
        save_links_to_file(enriched_links, output_file)
        print(f"Enriched links data saved successfully to {output_file}")
    except Exception as e:
        print(f"Error saving enriched data to file {output_file}: {e}")

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

def run_non_interactive_mode(db_path, delay, output_file):
    """
    Run in non-interactive mode using environment variables.
    """
    print("Running in non-interactive mode using environment variables...")
    
    # Get source groups from environment variable
    source_groups_env = os.getenv("WHATSAPP_SOURCE_GROUPS")
    if not source_groups_env:
        print("Error: WHATSAPP_SOURCE_GROUPS environment variable is not set.")
        print("Please set it to a comma-separated list of group names.")
        return
    
    # Parse group names
    group_names = [name.strip() for name in source_groups_env.split(',') if name.strip()]
    if not group_names:
        print("Error: No valid group names found in WHATSAPP_SOURCE_GROUPS.")
        return
    
    print(f"Source groups from env var: {group_names}")
    
    # Resolve group names to JIDs
    selected_groups_data = resolve_group_names_to_jids(db_path, group_names)
    
    if not selected_groups_data:
        print("Error: Could not resolve any group names to valid groups.")
        return
    
    print(f"\nResolved {len(selected_groups_data)} groups:")
    for jid, name in selected_groups_data:
        print(f"- {name} ({jid})")
    
    # Get date range from environment variables
    scan_days = int(os.getenv("WHATSAPP_SCAN_DAYS", "1"))
    print(f"\nScanning last {scan_days} day(s) for links...")
    
    # Calculate date range
    end_date = datetime.now()
    start_date = end_date - timedelta(days=scan_days)
    
    start_date_str = start_date.strftime('%Y-%m-%d')
    end_date_str = end_date.strftime('%Y-%m-%d')
    
    print(f"Date range: {start_date_str} to {end_date_str}")
    
    # Extract links
    all_extracted_links = []
    print("\nStarting link extraction...")
    for group_jid, group_name in selected_groups_data:
        print(f"- Searching in group: '{group_name}'")
        try:
            links_in_group = get_links_from_group(db_path, group_jid, group_name, start_date_str, end_date_str)
            if links_in_group:
                all_extracted_links.extend(links_in_group)
                print(f"  Found {len(links_in_group)} links in '{group_name}'.")
            else:
                 print(f"  No links found in '{group_name}' for the specified period.")
        except Exception as e:
             print(f"Error processing group {group_name} ({group_jid}): {e}")

    if not all_extracted_links:
        print("\nNo links found in any of the selected groups for the specified date range.")
        return
        
    print(f"\nExtracted {len(all_extracted_links)} links. Starting AI analysis...")

    # AI Enrichment
    enriched_links = []
    for i, link_data in enumerate(all_extracted_links):
        print(f"\nAnalyzing link {i+1}/{len(all_extracted_links)}: {link_data['link']}")
        
        analysis = analyze_link(link_data['link'], link_data['message'])
        
        # Merge analysis into the original data
        link_data['ai_purpose'] = analysis.get('purpose', 'N/A')
        link_data['ai_type'] = analysis.get('type', 'N/A')
        link_data['ai_insights'] = analysis.get('insights', [])
        
        enriched_links.append(link_data)
        
        # Add a delay to avoid rate limiting
        print(f"Waiting for {delay} seconds...")
        time.sleep(delay)
        
    # Output
    print(f"\nFinished analysis. Found a total of {len(enriched_links)} links with analysis attempts.")

    # Determine output file name for enriched data
    if not output_file:
        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
        output_file = f"enriched_links_{timestamp}.json" 
    elif not output_file.lower().endswith('.json'):
        output_file = output_file + '.json'
    
    # Save the enriched list to JSON
    try:
        save_links_to_file(enriched_links, output_file)
        print(f"Enriched links data saved successfully to {output_file}")
        return output_file
    except Exception as e:
        print(f"Error saving enriched data to file {output_file}: {e}")
        return None

if __name__ == "__main__":
    main()