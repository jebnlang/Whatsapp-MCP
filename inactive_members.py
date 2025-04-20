#!/usr/bin/env python3
import sqlite3
import re
import sys
import argparse
import csv
from datetime import datetime
import os
import requests  # Added for API calls
import json      # Added for parsing API response

# Define the path to the WhatsApp databases
MESSAGES_DB_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), 
                                "whatsapp-mcp", "whatsapp-bridge", "store", "messages.db")
WHATSAPP_DB_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), 
                                "whatsapp-mcp", "whatsapp-bridge", "store", "whatsapp.db")

# Define the Go bridge API base URL
BRIDGE_API_BASE_URL = "http://localhost:8080" # Assuming the Go bridge runs locally on port 8080

def get_groups():
    """Get a list of all groups in the database."""
    try:
        conn = sqlite3.connect(MESSAGES_DB_PATH)
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

def find_group_by_name(group_name):
    """Find a group JID by its name (partial match)."""
    try:
        conn = sqlite3.connect(MESSAGES_DB_PATH)
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

def get_members_who_sent_messages(group_jid):
    """Get all phone numbers that have sent messages in a specific group."""
    try:
        conn = sqlite3.connect(MESSAGES_DB_PATH)
        cursor = conn.cursor()
        
        cursor.execute("""
            SELECT DISTINCT sender
            FROM messages
            WHERE 
                chat_jid = ?
                AND sender IS NOT NULL
                AND sender != ''
        """, (group_jid,))
        
        senders = cursor.fetchall()
        
        # Extract phone numbers from JIDs
        active_members = set()
        for (sender,) in senders:
            # Skip system messages
            if sender == 'status@broadcast':
                continue
                
            # Extract number from JID (format: number@s.whatsapp.net)
            if '@' in sender:
                phone_number = sender.split('@')[0]
                active_members.add(phone_number)
            else:
                active_members.add(sender)
        
        return active_members
        
    except sqlite3.Error as e:
        print(f"Database error: {e}")
        return set()
    finally:
        if 'conn' in locals():
            conn.close()

def parse_timestamp(timestamp_str):
    """
    Parse a timestamp string with various possible formats.
    Returns a datetime object or None if parsing fails.
    """
    if not timestamp_str:
        return None
    
    # Try different timestamp formats
    formats = [
        "%Y-%m-%d %H:%M:%S",        # Standard format
        "%Y-%m-%d %H:%M:%S%z",      # With timezone offset
        "%Y-%m-%d %H:%M:%S.%f",     # With microseconds
        "%Y-%m-%d %H:%M:%S.%f%z"    # With microseconds and timezone
    ]
    
    # Remove any timezone information if present (handling "+02:00" format)
    if "+" in timestamp_str or "-" in timestamp_str:
        # Find the last occurrence of + or -
        for i in range(len(timestamp_str) - 1, -1, -1):
            if timestamp_str[i] in ['+', '-']:
                # Remove timezone part
                timestamp_str = timestamp_str[:i]
                break
    
    # Try each format
    for fmt in formats:
        try:
            return datetime.strptime(timestamp_str, fmt)
        except ValueError:
            continue
    
    # If all formats fail, print the problematic timestamp and return None
    print(f"Warning: Could not parse timestamp: {timestamp_str}")
    return None

def estimate_earliest_activity_date(group_jid, phone_number):
    """
    Estimate when a member first appeared in a group by checking their earliest message.
    Returns datetime object or None if no activity found.
    """
    try:
        conn = sqlite3.connect(MESSAGES_DB_PATH)
        cursor = conn.cursor()
        
        # Check the earliest message from this member
        cursor.execute("""
            SELECT MIN(timestamp)
            FROM messages
            WHERE 
                chat_jid = ?
                AND sender = ?
        """, (group_jid, f"{phone_number}@s.whatsapp.net"))
        
        row = cursor.fetchone()
        
        if row and row[0]:
            return parse_timestamp(row[0])
        
        return None
        
    except sqlite3.Error as e:
        print(f"Database error when checking activity date: {e}")
        return None
    finally:
        if 'conn' in locals():
            conn.close()

def format_phone_number(number, include_plus=False, country_code=None):
    """Format a phone number based on the options."""
    # Remove any non-digit characters
    digits_only = ''.join(c for c in number if c.isdigit())
    
    # Add plus sign if requested
    if include_plus:
        return f"+{digits_only}"
    
    # Add country code if requested and not already present
    if country_code and not digits_only.startswith(country_code):
        return f"{country_code}{digits_only}"
    
    return digits_only

def save_phone_numbers_to_csv(phone_numbers, output_file, include_plus=False, country_code=None):
    """Save phone numbers to a CSV file."""
    with open(output_file, 'w', newline='') as f:
        writer = csv.writer(f)
        writer.writerow(['Phone Number'])  # Header
        
        for number in phone_numbers:
            formatted_number = format_phone_number(number, include_plus, country_code)
            writer.writerow([formatted_number])

# New function to get live members from the Go bridge API
def get_live_group_members(group_jid):
    """
    Fetch the current list of group members from the Go bridge API.

    Args:
        group_jid: The JID of the group chat

    Returns:
        Set of phone numbers of current members, or None if API call fails.
    """
    endpoint = f"{BRIDGE_API_BASE_URL}/api/group/{group_jid}/members"
    print(f"Attempting to fetch live member list from: {endpoint}")
    members = set()
    try:
        response = requests.get(endpoint, timeout=15) # Added timeout
        response.raise_for_status() # Raises HTTPError for bad responses (4XX or 5XX)

        data = response.json()
        if 'members' in data and isinstance(data['members'], list):
            for member_jid in data['members']:
                if isinstance(member_jid, str) and '@' in member_jid:
                    phone_number = member_jid.split('@')[0]
                    members.add(phone_number)
            print(f"Successfully fetched {len(members)} live members from API.")
            return members
        else:
            print(f"Error: API response format is incorrect. Expected JSON with a 'members' list.")
            print(f"Received data: {data}")
            return None

    except requests.exceptions.ConnectionError:
        print(f"Error: Could not connect to the Go bridge API at {BRIDGE_API_BASE_URL}.")
        print("Please ensure the Go whatsapp-bridge application is running.")
        return None
    except requests.exceptions.Timeout:
        print(f"Error: Request to the Go bridge API timed out.")
        return None
    except requests.exceptions.HTTPError as e:
        print(f"Error: API request failed with status {e.response.status_code}.")
        try:
            # Try to print error message from API if available
            error_details = e.response.json()
            print(f"API Error Details: {error_details}")
        except json.JSONDecodeError:
            print(f"API Response Content: {e.response.text}")
        print("This might indicate the group JID is incorrect or the API endpoint is not available.")
        return None
    except json.JSONDecodeError:
        print(f"Error: Could not decode JSON response from the API.")
        print(f"Received content: {response.text}")
        return None
    except Exception as e:
        print(f"An unexpected error occurred while fetching members from API: {e}")
        return None

def extract_inactive_members(group_name, include_plus=False, country_code=None, output_file=None, group_index=None):
    """
    Extract phone numbers of group members who never sent a message,
    based on the live member list from the Go bridge API.

    Args:
        group_name: Name or partial name of the group
        include_plus: Whether to include + prefix in phone numbers
        country_code: Country code to add to phone numbers
        output_file: Output file name
        group_index: Index of group to use when multiple matches found (1-based index)

    Returns:
        List of inactive members' phone numbers, or empty list on failure.
    """
    # Find the group by name
    groups = find_group_by_name(group_name)

    if not groups:
        print(f"No group found matching '{group_name}'.")
        return []

    group_jid, group_name_selected = "", ""
    if len(groups) > 1:
        print(f"Multiple groups found matching '{group_name}':")
        for i, (jid, name) in enumerate(groups, 1):
            print(f"  {i}. {name} ({jid})")

        if group_index is not None:
            if group_index < 1 or group_index > len(groups):
                print(f"Invalid group index: {group_index}. Valid range: 1-{len(groups)}")
                return []
            group_jid, group_name_selected = groups[group_index - 1]
            print(f"Using group: {group_name_selected}")
        else:
            try:
                selection = int(input("Enter the number of the group to use: "))
                if selection < 1 or selection > len(groups):
                    print("Invalid selection. Exiting.")
                    return []
                group_jid, group_name_selected = groups[selection - 1]
            except ValueError:
                print("Invalid input. Exiting.")
                return []
            except KeyboardInterrupt:
                print("\nOperation cancelled by user.")
                return []
    else:
        group_jid, group_name_selected = groups[0]

    print(f"\nExtracting inactive members from group '{group_name_selected}' ({group_jid})...")

    # Step 1: Get the live list of all members from the Go bridge API
    total_members = get_live_group_members(group_jid)

    if total_members is None:
        print("Failed to retrieve live member list from the API. Cannot proceed.")
        return []

    if not total_members:
        print("API returned an empty member list for this group.")
        # Decide whether to proceed or exit. Let's proceed but warn.
        print("Warning: The group appears to have no members according to the API.")

    print(f"Total current members found via API: {len(total_members)}")

    # Step 2: Get active members (those who have sent messages) from the database
    active_members = get_members_who_sent_messages(group_jid)
    print(f"Found {len(active_members)} members who have sent at least one message (from DB).")

    # Step 3: Identify inactive members (total members - active members)
    inactive_members = total_members - active_members
    print(f"Identified {len(inactive_members)} inactive members.")

    # Filter out any potential empty strings just in case
    inactive_members = {m for m in inactive_members if m}

    # Save to CSV file
    if inactive_members:
        if not output_file:
            timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
            # Use the selected group name for the file
            safe_name = group_name_selected.replace(' ', '_').replace('/', '_').replace('\\','_')
            output_file = f"inactive_members_{safe_name}_{timestamp}.csv"

        save_phone_numbers_to_csv(inactive_members, output_file, include_plus, country_code)
        print(f"\nInactive member phone numbers saved to {output_file}")
    else:
        print("\nNo inactive members found (or API failed).")

    return list(inactive_members)

def parse_date(date_string):
    """Parse a date string in format YYYY-MM-DD."""
    try:
        return datetime.strptime(date_string, "%Y-%m-%d")
    except ValueError:
        print(f"Invalid date format: {date_string}. Please use YYYY-MM-DD format.")
        return None

def main():
    parser = argparse.ArgumentParser(description="Extract phone numbers of inactive WhatsApp group members using the live API")
    parser.add_argument("--list-groups", action="store_true", help="List all available groups (from DB)")
    parser.add_argument("--group-name", type=str, help="Name or partial name of the group (from DB)")
    parser.add_argument("--group-index", type=int, help="Index of group to use when multiple matches found (1-based)")
    # parser.add_argument("--before-date", type=str, help="Only include members who joined before this date (YYYY-MM-DD)") # Removed as join date isn't available from API yet
    parser.add_argument("--output", type=str, help="Output CSV file name")
    parser.add_argument("--include-plus", action="store_true", help="Include '+' prefix in phone numbers")
    parser.add_argument("--country-code", type=str, help="Add country code to phone numbers without it")

    args = parser.parse_args()

    # List all groups
    if args.list_groups:
        groups = get_groups()
        if not groups:
            print("No groups found in the database.")
            return

        print("Available groups (from database cache):")
        for i, (jid, name) in enumerate(groups, 1):
            print(f"{i}. {name} ({jid})")
        return

    # Extract inactive members
    if args.group_name:
        # cutoff_date = None # Removed
        # if args.before_date:
        #     cutoff_date = parse_date(args.before_date)
        #     if not cutoff_date:
        #         return

        extract_inactive_members(
            group_name=args.group_name,
            # cutoff_date=cutoff_date, # Removed
            include_plus=args.include_plus,
            country_code=args.country_code,
            output_file=args.output,
            group_index=args.group_index
        )
    else:
        parser.print_help()

def interactive_mode():
    """Run the script in interactive mode."""
    # List all available groups from DB
    groups = get_groups()
    if not groups:
        print("No groups found in the database.")
        return

    print("Available groups (from database cache):")
    for i, (jid, name) in enumerate(groups, 1):
        print(f"{i}. {name} ({jid})")

    try:
        selection = input("\nEnter the number of the group to extract inactive members from: ")
        group_idx = int(selection.strip()) - 1

        if group_idx < 0 or group_idx >= len(groups):
            print(f"Invalid group number: {group_idx + 1}")
            return

        # We still use group_name for selection, but jid is the key input now
        group_jid, group_name = groups[group_idx]

        # date_input = input("\nEnter cutoff date (YYYY-MM-DD, leave empty for no date filter): ").strip() # Removed
        # cutoff_date = None
        # if date_input:
        #     cutoff_date = parse_date(date_input)
        #     if not cutoff_date:
        #         return

        include_plus = input("\nInclude '+' prefix in phone numbers? (y/n): ").lower() == 'y'

        country_code = input("\nAdd country code (leave empty for none): ").strip()
        if country_code and not country_code.isdigit():
            print("Country code must be digits only.")
            return

        # Extract inactive members using the selected group name (to find JID)
        extract_inactive_members(
            group_name=group_name, # Pass name to find the JID again inside the function
            # cutoff_date=cutoff_date, # Removed
            include_plus=include_plus,
            country_code=country_code if country_code else None
        )

    except ValueError:
        print("Invalid input. Please enter a number.")
    except KeyboardInterrupt:
        print("\nOperation cancelled by user.")
    except Exception as e:
        print(f"An unexpected error occurred: {str(e)}")


if __name__ == "__main__":
    if len(sys.argv) == 1:
        # If no arguments provided, run in interactive mode
        interactive_mode()
    else:
        main() 