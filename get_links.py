import sqlite3
import re
import sys
from datetime import datetime
import os

# Define the path to the WhatsApp messages database
MESSAGES_DB_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), 
                                "whatsapp-mcp", "whatsapp-bridge", "store", "messages.db")

def extract_links(text):
    """Extract URLs from text using regex."""
    # Regular expression pattern for URLs
    url_pattern = r'https?://(?:[-\w.]|(?:%[\da-fA-F]{2}))+'
    return re.findall(url_pattern, text)

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

def get_links_from_group(group_jid, start_date=None, end_date=None):
    """
    Get links shared in a specific group within a date range.
    
    Args:
        group_jid: The JID of the group chat
        start_date: Optional start date in 'YYYY-MM-DD' format
        end_date: Optional end date in 'YYYY-MM-DD' format
    """
    try:
        conn = sqlite3.connect(MESSAGES_DB_PATH)
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
            # Convert start_date to ISO format for SQLite comparison
            start_datetime = datetime.strptime(start_date, '%Y-%m-%d').isoformat()
            query += " AND timestamp >= ?"
            params.append(start_datetime)
        
        if end_date:
            # Convert end_date to ISO format for SQLite comparison
            end_datetime = datetime.strptime(end_date, '%Y-%m-%d').isoformat()
            query += " AND timestamp <= ?"
            params.append(end_datetime)
        
        query += " ORDER BY timestamp"
        
        cursor.execute(query, params)
        messages = cursor.fetchall()
        
        # Process messages to extract links
        links_with_context = []
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
                    formatted_time = timestamp
                
                for link in links:
                    links_with_context.append({
                        'timestamp': formatted_time,
                        'sender': sender,
                        'link': link,
                        'message': content
                    })
        
        return links_with_context
        
    except sqlite3.Error as e:
        print(f"Database error: {e}")
        return []
    finally:
        if 'conn' in locals():
            conn.close()

def main():
    # List all available groups
    groups = get_groups()
    if not groups:
        print("No groups found in the database.")
        return
    
    print("Available groups:")
    for i, (jid, name) in enumerate(groups, 1):
        print(f"{i}. {name} ({jid})")
    
    try:
        group_idx = int(input("\nEnter the number of the group to search: ")) - 1
        if group_idx < 0 or group_idx >= len(groups):
            print("Invalid group number.")
            return
        
        group_jid, group_name = groups[group_idx]
        
        start_date = input("\nEnter start date (YYYY-MM-DD) or leave empty for all time: ")
        end_date = input("Enter end date (YYYY-MM-DD) or leave empty for all time: ")
        
        # Validate dates if provided
        if start_date:
            try:
                datetime.strptime(start_date, '%Y-%m-%d')
            except ValueError:
                print("Invalid start date format. Please use YYYY-MM-DD.")
                return
        
        if end_date:
            try:
                datetime.strptime(end_date, '%Y-%m-%d')
            except ValueError:
                print("Invalid end date format. Please use YYYY-MM-DD.")
                return
        
        print(f"\nSearching for links in group '{group_name}'...")
        links = get_links_from_group(group_jid, start_date, end_date)
        
        if not links:
            print("No links found in the specified date range.")
            return
        
        print(f"\nFound {len(links)} links:")
        for i, link_data in enumerate(links, 1):
            print(f"\n{i}. {link_data['link']}")
            print(f"   Date: {link_data['timestamp']}")
            print(f"   Sender: {link_data['sender']}")
            print(f"   Message: {link_data['message'][:100]}{'...' if len(link_data['message']) > 100 else ''}")
        
        # Save links to a file
        output_file = f"links_{group_name.replace(' ', '_')}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.txt"
        with open(output_file, 'w') as f:
            for i, link_data in enumerate(links, 1):
                f.write(f"{i}. {link_data['link']}\n")
                f.write(f"   Date: {link_data['timestamp']}\n")
                f.write(f"   Sender: {link_data['sender']}\n")
                f.write(f"   Message: {link_data['message']}\n\n")
        
        print(f"\nLinks saved to {output_file}")
        
    except ValueError:
        print("Invalid input. Please enter a number.")
    except KeyboardInterrupt:
        print("\nOperation cancelled by user.")
    except Exception as e:
        print(f"Error: {str(e)}")

if __name__ == "__main__":
    main() 