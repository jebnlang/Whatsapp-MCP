#!/usr/bin/env python3
import sqlite3
import re
import sys
import argparse
import csv
from datetime import datetime
import os

# Define the path to the WhatsApp messages database
MESSAGES_DB_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), 
                                "whatsapp-mcp", "whatsapp-bridge", "store", "messages.db")
WHATSAPP_DB_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), 
                                "whatsapp-mcp", "whatsapp-bridge", "store", "whatsapp.db")

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

def find_groups_by_names(group_names):
    """Find multiple groups by their names."""
    result = []
    for name in group_names:
        groups = find_group_by_name(name)
        if groups:
            if len(groups) > 1:
                print(f"Multiple groups found matching '{name}':")
                for i, (jid, group_name) in enumerate(groups, 1):
                    print(f"  {i}. {group_name} ({jid})")
                print(f"Using the first match: {groups[0][1]}")
            result.append(groups[0])
    return result

def get_all_group_members(group_jid):
    """
    Get all members of a group, even those who haven't sent messages.
    Attempts to combine different sources to get as many members as possible.
    
    Args:
        group_jid: The JID of the group chat
    
    Returns:
        Set of unique phone numbers in the group
    """
    phone_numbers = set()
    
    # First, try to get group members from messages (those who have sent messages)
    sent_messages_members = get_members_from_messages(group_jid)
    phone_numbers.update(sent_messages_members)
    
    # Try to get additional group members from contacts related to the group
    try:
        conn = sqlite3.connect(WHATSAPP_DB_PATH)
        cursor = conn.cursor()
        
        # Find all contacts associated with the group
        cursor.execute("""
            SELECT their_jid
            FROM whatsmeow_contacts
            WHERE their_jid LIKE '%@s.whatsapp.net'
        """)
        
        contacts = cursor.fetchall()
        
        for (contact_jid,) in contacts:
            # Extract number from JID (format: number@s.whatsapp.net)
            if '@' in contact_jid:
                phone_number = contact_jid.split('@')[0]
                phone_numbers.add(phone_number)
    
    except sqlite3.Error as e:
        print(f"  Error accessing WhatsApp contacts: {e}")
    finally:
        if 'conn' in locals():
            conn.close()
    
    print(f"  Found {len(phone_numbers)} unique phone numbers (including both active and inactive members).")
    return list(phone_numbers)

def get_members_from_messages(group_jid):
    """Get all phone numbers that have sent messages in a specific group."""
    try:
        conn = sqlite3.connect(MESSAGES_DB_PATH)
        # Make sure to fetch all results, not just the first few
        conn.execute("PRAGMA temp_store = MEMORY")  # Store temp tables in memory
        conn.execute("PRAGMA mmap_size = 30000000000")  # 30GB memory map
        conn.execute("PRAGMA page_size = 4096")  # Increase page size
        conn.execute("PRAGMA cache_size = 100000")  # Increase cache size
        
        cursor = conn.cursor()
        
        # First, count the total distinct senders
        cursor.execute("""
            SELECT COUNT(DISTINCT sender)
            FROM messages
            WHERE 
                chat_jid = ?
                AND sender IS NOT NULL
                AND sender != ''
        """, (group_jid,))
        
        count = cursor.fetchone()[0]
        print(f"  Members who have sent messages: {count}")
        
        # Now, fetch the distinct senders
        query = """
            SELECT DISTINCT sender
            FROM messages
            WHERE 
                chat_jid = ?
                AND sender IS NOT NULL
                AND sender != ''
        """
        
        cursor.execute(query, (group_jid,))
        senders = cursor.fetchall()
        
        # Extract phone numbers from JIDs
        phone_numbers = set()  # Use a set for faster deduplication
        for (sender,) in senders:
            # Skip system messages
            if sender == 'status@broadcast':
                continue
                
            # Extract number from JID (format: number@s.whatsapp.net)
            if '@' in sender:
                phone_number = sender.split('@')[0]
                phone_numbers.add(phone_number)
            else:
                phone_numbers.add(sender)
        
        return list(phone_numbers)
        
    except sqlite3.Error as e:
        print(f"Database error: {e}")
        return []
    finally:
        if 'conn' in locals():
            conn.close()

def get_unique_phone_numbers_from_group(group_jid, max_numbers=10000):
    """
    Get all unique phone numbers from a specific group, including all members.
    
    Args:
        group_jid: The JID of the group chat
        max_numbers: Maximum number of phone numbers to extract (default 10000)
    
    Returns:
        List of unique phone numbers without the WhatsApp suffix
    """
    # Try to get all group members
    all_members = get_all_group_members(group_jid)
    
    # Limit to max_numbers
    if len(all_members) > max_numbers:
        print(f"  Limiting to {max_numbers} phone numbers (out of {len(all_members)}).")
        all_members = all_members[:max_numbers]
    
    return all_members

def get_unique_phone_numbers_from_group_batched(group_jid, max_numbers=10000):
    """
    Alternative implementation that processes results in batches to handle large groups.
    Now also tries to get all group members, not just active ones.
    
    Args:
        group_jid: The JID of the group chat
        max_numbers: Maximum number of phone numbers to extract
    
    Returns:
        List of unique phone numbers without the WhatsApp suffix
    """
    # Try the more comprehensive approach first
    return get_unique_phone_numbers_from_group(group_jid, max_numbers)

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

def extract_from_multiple_groups(group_names=None, include_plus=False, country_code=None, output_file=None, merge=False, max_numbers=10000):
    """Extract phone numbers from multiple groups."""
    if not group_names:
        # If no group names provided, get all groups
        groups = get_groups()
    else:
        # Find groups matching the provided names
        groups = find_groups_by_names(group_names)
    
    if not groups:
        print("No groups found.")
        return
    
    # Collect all phone numbers
    all_phone_numbers = set()
    group_data = {}
    
    for group_jid, group_name in groups:
        print(f"Extracting phone numbers from group '{group_name}'...")
        
        # Try enhanced approach to get ALL members
        try:
            phone_numbers = get_unique_phone_numbers_from_group(group_jid, max_numbers)
        except Exception as e:
            print(f"  Error with standard extraction: {e}")
            print("  Trying batch extraction method...")
            phone_numbers = get_unique_phone_numbers_from_group_batched(group_jid, max_numbers)
        
        if not phone_numbers:
            print(f"  No phone numbers found in this group.")
            continue
        
        print(f"  Found {len(phone_numbers)} unique phone numbers.")
        
        # Add to the all_phone_numbers set
        all_phone_numbers.update(phone_numbers)
        
        # Store group-specific data
        group_data[group_name] = phone_numbers
        
        # Save group-specific file if not merging
        if not merge:
            safe_name = group_name.replace(' ', '_').replace('/', '_')
            timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
            group_output_file = output_file or f"phone_numbers_{safe_name}_{timestamp}.csv"
            
            save_phone_numbers_to_csv(phone_numbers, group_output_file, include_plus, country_code)
            print(f"  Phone numbers saved to {group_output_file}")
        
        # If we have reached the maximum number of unique phone numbers, stop
        if len(all_phone_numbers) >= max_numbers:
            print(f"\nReached the maximum limit of {max_numbers} unique phone numbers.")
            break
    
    # Save merged file if requested
    if merge:
        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
        merged_output_file = output_file or f"phone_numbers_merged_{timestamp}.csv"
        
        # Limit to max_numbers
        merged_numbers = list(all_phone_numbers)
        if len(merged_numbers) > max_numbers:
            merged_numbers = merged_numbers[:max_numbers]
            print(f"\nLimiting to {max_numbers} unique phone numbers.")
        
        save_phone_numbers_to_csv(merged_numbers, merged_output_file, include_plus, country_code)
        print(f"\nAll {len(merged_numbers)} unique phone numbers saved to {merged_output_file}")
    
    return all_phone_numbers, group_data

def interactive_mode():
    """Run the script in interactive mode."""
    # List all available groups
    groups = get_groups()
    if not groups:
        print("No groups found in the database.")
        return
    
    print("Available groups:")
    for i, (jid, name) in enumerate(groups, 1):
        print(f"{i}. {name} ({jid})")
    
    try:
        selection = input("\nEnter the number(s) of the group(s) to extract phone numbers from (comma-separated): ")
        group_indices = [int(idx.strip()) - 1 for idx in selection.split(',')]
        
        selected_groups = []
        for idx in group_indices:
            if idx < 0 or idx >= len(groups):
                print(f"Invalid group number: {idx + 1}")
                continue
            selected_groups.append(groups[idx])
        
        if not selected_groups:
            print("No valid groups selected.")
            return
        
        include_plus = input("\nInclude '+' prefix in phone numbers? (y/n): ").lower() == 'y'
        
        country_code = input("\nAdd country code (leave empty for none): ").strip()
        if country_code and not country_code.isdigit():
            print("Country code must be digits only.")
            return
        
        merge = input("\nMerge phone numbers from all selected groups? (y/n): ").lower() == 'y'
        
        max_numbers = 10000
        max_input = input(f"\nMaximum number of phone numbers to extract (default: {max_numbers}): ").strip()
        if max_input:
            try:
                max_numbers = int(max_input)
                if max_numbers <= 0:
                    print("Maximum number must be positive.")
                    return
            except ValueError:
                print("Invalid number. Using default.")
                max_numbers = 10000
        
        # Extract phone numbers
        extract_from_multiple_groups(
            group_names=[name for _, name in selected_groups],
            include_plus=include_plus,
            country_code=country_code if country_code else None,
            merge=merge,
            max_numbers=max_numbers
        )
        
    except ValueError:
        print("Invalid input. Please enter number(s).")
    except KeyboardInterrupt:
        print("\nOperation cancelled by user.")
    except Exception as e:
        print(f"Error: {str(e)}")

def main():
    parser = argparse.ArgumentParser(description="Extract phone numbers from WhatsApp group chats")
    parser.add_argument("--list-groups", action="store_true", help="List all available groups")
    parser.add_argument("--group-name", type=str, nargs='+', help="Search for group(s) by name (partial match)")
    parser.add_argument("--output", type=str, help="Output CSV file name")
    parser.add_argument("--include-plus", action="store_true", help="Include '+' prefix in phone numbers")
    parser.add_argument("--country-code", type=str, help="Add country code to phone numbers without it")
    parser.add_argument("--merge", action="store_true", help="Merge phone numbers from all selected groups into a single file")
    parser.add_argument("--interactive", action="store_true", help="Run in interactive mode")
    parser.add_argument("--max-numbers", type=int, default=10000, help="Maximum number of phone numbers to extract (default: 10000)")
    
    args = parser.parse_args()
    
    # Run in interactive mode if specified
    if args.interactive:
        interactive_mode()
        return
    
    # List all groups
    if args.list_groups:
        groups = get_groups()
        if not groups:
            print("No groups found in the database.")
            return
        
        print("Available groups:")
        for i, (jid, name) in enumerate(groups, 1):
            print(f"{i}. {name} ({jid})")
        return
    
    # Extract phone numbers from groups
    if args.group_name:
        extract_from_multiple_groups(
            group_names=args.group_name,
            include_plus=args.include_plus,
            country_code=args.country_code,
            output_file=args.output,
            merge=args.merge,
            max_numbers=args.max_numbers
        )
    else:
        parser.print_help()

if __name__ == "__main__":
    if len(sys.argv) == 1:
        # If no arguments provided, run in interactive mode
        interactive_mode()
    else:
        main() 