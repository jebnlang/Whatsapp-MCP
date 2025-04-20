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

def get_unique_phone_numbers_from_group(group_jid):
    """
    Get all unique phone numbers that have sent messages in a specific group.
    
    Args:
        group_jid: The JID of the group chat
    
    Returns:
        List of unique phone numbers without the WhatsApp suffix
    """
    try:
        conn = sqlite3.connect(MESSAGES_DB_PATH)
        cursor = conn.cursor()
        
        query = """
            SELECT DISTINCT
                sender
            FROM messages
            WHERE 
                chat_jid = ?
                AND sender IS NOT NULL
                AND sender != ''
            ORDER BY sender
        """
        
        cursor.execute(query, (group_jid,))
        senders = cursor.fetchall()
        
        # Extract phone numbers from JIDs
        phone_numbers = []
        for (sender,) in senders:
            # Skip system messages
            if sender == 'status@broadcast':
                continue
                
            # Extract number from JID (format: number@s.whatsapp.net)
            if '@' in sender:
                phone_number = sender.split('@')[0]
                phone_numbers.append(phone_number)
            else:
                phone_numbers.append(sender)
        
        return phone_numbers
        
    except sqlite3.Error as e:
        print(f"Database error: {e}")
        return []
    finally:
        if 'conn' in locals():
            conn.close()

def save_phone_numbers_to_csv(phone_numbers, output_file, include_plus=False):
    """Save phone numbers to a CSV file."""
    with open(output_file, 'w', newline='') as f:
        writer = csv.writer(f)
        writer.writerow(['Phone Number'])  # Header
        
        for number in phone_numbers:
            if include_plus and not number.startswith('+'):
                writer.writerow([f'+{number}'])
            else:
                writer.writerow([number])

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
        group_idx = int(input("\nEnter the number of the group to extract phone numbers from: ")) - 1
        if group_idx < 0 or group_idx >= len(groups):
            print("Invalid group number.")
            return
        
        group_jid, group_name = groups[group_idx]
        
        include_plus = input("\nInclude '+' prefix in phone numbers? (y/n): ").lower() == 'y'
        
        print(f"\nExtracting phone numbers from group '{group_name}'...")
        phone_numbers = get_unique_phone_numbers_from_group(group_jid)
        
        if not phone_numbers:
            print("No phone numbers found in this group.")
            return
        
        print(f"\nFound {len(phone_numbers)} unique phone numbers.")
        
        # Save phone numbers to a file
        safe_name = group_name.replace(' ', '_').replace('/', '_')
        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
        output_file = f"phone_numbers_{safe_name}_{timestamp}.csv"
        
        save_phone_numbers_to_csv(phone_numbers, output_file, include_plus)
        print(f"\nPhone numbers saved to {output_file}")
        
    except ValueError:
        print("Invalid input. Please enter a number.")
    except KeyboardInterrupt:
        print("\nOperation cancelled by user.")
    except Exception as e:
        print(f"Error: {str(e)}")

def main():
    parser = argparse.ArgumentParser(description="Extract phone numbers from WhatsApp group chats")
    parser.add_argument("--list-groups", action="store_true", help="List all available groups")
    parser.add_argument("--group-name", type=str, help="Search for group by name (partial match)")
    parser.add_argument("--group-jid", type=str, help="The JID of the group to search")
    parser.add_argument("--output", type=str, help="Output CSV file name")
    parser.add_argument("--include-plus", action="store_true", help="Include '+' prefix in phone numbers")
    parser.add_argument("--interactive", action="store_true", help="Run in interactive mode")
    
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
    
    # Search for group by name
    if args.group_name:
        groups = find_group_by_name(args.group_name)
        if not groups:
            print(f"No groups found matching '{args.group_name}'.")
            return
        
        if len(groups) > 1:
            print(f"Multiple groups found matching '{args.group_name}':")
            for i, (jid, name) in enumerate(groups, 1):
                print(f"{i}. {name} ({jid})")
            return
        
        group_jid, group_name = groups[0]
    elif args.group_jid:
        # Query the database to get the group name
        try:
            conn = sqlite3.connect(MESSAGES_DB_PATH)
            cursor = conn.cursor()
            cursor.execute("SELECT name FROM chats WHERE jid = ?", (args.group_jid,))
            result = cursor.fetchone()
            if result:
                group_name = result[0]
                group_jid = args.group_jid
            else:
                print(f"No group found with JID '{args.group_jid}'.")
                return
        except sqlite3.Error as e:
            print(f"Database error: {e}")
            return
        finally:
            if 'conn' in locals():
                conn.close()
    else:
        print("Either --group-name or --group-jid must be provided.")
        return
    
    print(f"Extracting phone numbers from group '{group_name}'...")
    phone_numbers = get_unique_phone_numbers_from_group(group_jid)
    
    if not phone_numbers:
        print("No phone numbers found in this group.")
        return
    
    print(f"Found {len(phone_numbers)} unique phone numbers.")
    
    # Save phone numbers to a file
    if args.output:
        output_file = args.output
    else:
        safe_name = group_name.replace(' ', '_').replace('/', '_')
        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
        output_file = f"phone_numbers_{safe_name}_{timestamp}.csv"
    
    save_phone_numbers_to_csv(phone_numbers, output_file, args.include_plus)
    print(f"Phone numbers saved to {output_file}")

if __name__ == "__main__":
    if len(sys.argv) == 1:
        # If no arguments provided, run in interactive mode
        interactive_mode()
    else:
        main() 