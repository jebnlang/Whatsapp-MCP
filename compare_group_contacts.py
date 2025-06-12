#!/usr/bin/env python3
"""
WhatsApp Group Contact Comparison Script

This script compares contacts between two WhatsApp groups and creates a CSV 
of contacts that exist in both groups.

Usage:
    python compare_group_contacts.py

The script will:
1. Extract all contacts from group 1: 120363315467665376@g.us
2. Extract all contacts from group 2: 120363370824880933@g.us
3. Find contacts that exist in both groups
4. Generate a CSV with phone_number, name, jid columns
"""

import sqlite3
import csv
import os
import re
from typing import Set, Dict, List, Tuple, Optional
from dataclasses import dataclass


@dataclass
class Contact:
    """Represents a WhatsApp contact"""
    jid: str
    name: Optional[str] = None
    phone_number: Optional[str] = None


class WhatsAppGroupComparator:
    def __init__(self, messages_db_path: str, contacts_db_path: str):
        """
        Initialize the comparator with database paths.
        
        Args:
            messages_db_path: Path to messages.db
            contacts_db_path: Path to whatsapp.db
        """
        self.messages_db_path = messages_db_path
        self.contacts_db_path = contacts_db_path
        
    def extract_phone_number(self, jid: str) -> Optional[str]:
        """
        Extract phone number from JID if possible.
        
        Args:
            jid: WhatsApp JID (e.g., '972545831336@s.whatsapp.net' or '66846921380038@lid')
            
        Returns:
            Phone number if extractable, None otherwise
        """
        # For @s.whatsapp.net format, the phone number is before the @
        if "@s.whatsapp.net" in jid:
            return jid.split("@")[0]
        
        # For @lid format, we can't extract a phone number
        return None
    
    def get_group_contacts(self, group_jid: str) -> Set[str]:
        """
        Get all unique contacts (senders) from a specific group.
        
        Args:
            group_jid: The JID of the group (e.g., '120363315467665376@g.us')
            
        Returns:
            Set of unique sender JIDs from the group
        """
        conn = sqlite3.connect(self.messages_db_path)
        cursor = conn.cursor()
        
        query = """
        SELECT DISTINCT sender 
        FROM messages 
        WHERE chat_jid = ? AND sender IS NOT NULL AND sender != ''
        """
        
        cursor.execute(query, (group_jid,))
        contacts = {row[0] for row in cursor.fetchall()}
        
        conn.close()
        return contacts
    
    def get_contact_name(self, jid: str) -> Optional[str]:
        """
        Get the name for a contact from the contacts database.
        
        Args:
            jid: The contact's JID
            
        Returns:
            Contact name if found, None otherwise
        """
        conn = sqlite3.connect(self.contacts_db_path)
        cursor = conn.cursor()
        
        query = """
        SELECT first_name, full_name, push_name 
        FROM whatsmeow_contacts 
        WHERE their_jid = ?
        """
        
        cursor.execute(query, (jid,))
        result = cursor.fetchone()
        
        conn.close()
        
        if result:
            first_name, full_name, push_name = result
            # Return the most complete name available
            return full_name or push_name or first_name
        
        return None
    
    def compare_groups(self, group1_jid: str, group2_jid: str) -> List[Contact]:
        """
        Compare contacts between two groups and return common contacts.
        
        Args:
            group1_jid: JID of the first group
            group2_jid: JID of the second group
            
        Returns:
            List of Contact objects that exist in both groups
        """
        print(f"Extracting contacts from Group 1: {group1_jid}")
        group1_contacts = self.get_group_contacts(group1_jid)
        print(f"Found {len(group1_contacts)} unique contacts in Group 1")
        
        print(f"\nExtracting contacts from Group 2: {group2_jid}")
        group2_contacts = self.get_group_contacts(group2_jid)
        print(f"Found {len(group2_contacts)} unique contacts in Group 2")
        
        # Find intersection (common contacts)
        common_jids = group1_contacts.intersection(group2_contacts)
        print(f"\nFound {len(common_jids)} contacts that exist in both groups")
        
        # Create Contact objects with names and phone numbers
        common_contacts = []
        for jid in common_jids:
            contact = Contact(
                jid=jid,
                name=self.get_contact_name(jid),
                phone_number=self.extract_phone_number(jid)
            )
            common_contacts.append(contact)
        
        # Sort by name (put unnamed contacts at the end)
        common_contacts.sort(key=lambda c: (c.name is None, c.name or ""))
        
        return common_contacts
    
    def export_to_csv(self, contacts: List[Contact], filename: str = "common_contacts.csv"):
        """
        Export contacts to a CSV file.
        
        Args:
            contacts: List of Contact objects
            filename: Output CSV filename
        """
        with open(filename, 'w', newline='', encoding='utf-8') as csvfile:
            writer = csv.writer(csvfile)
            
            # Write header
            writer.writerow(['phone_number', 'name', 'jid'])
            
            # Write contacts
            for contact in contacts:
                writer.writerow([
                    contact.phone_number or '',
                    contact.name or '',
                    contact.jid
                ])
        
        print(f"\nExported {len(contacts)} contacts to {filename}")
    
    def print_summary(self, contacts: List[Contact]):
        """Print a summary of the results."""
        print("\n" + "="*60)
        print("SUMMARY OF COMMON CONTACTS")
        print("="*60)
        
        contacts_with_phone = [c for c in contacts if c.phone_number]
        contacts_with_name = [c for c in contacts if c.name]
        
        print(f"Total common contacts: {len(contacts)}")
        print(f"Contacts with phone numbers: {len(contacts_with_phone)}")
        print(f"Contacts with names: {len(contacts_with_name)}")
        
        print(f"\nFirst 10 contacts:")
        for i, contact in enumerate(contacts[:10], 1):
            name = contact.name or "Unknown"
            phone = contact.phone_number or "No phone"
            print(f"{i:2d}. {name:<25} | {phone:<15} | {contact.jid}")
        
        if len(contacts) > 10:
            print(f"... and {len(contacts) - 10} more contacts")


def main():
    """Main function to run the group comparison."""
    # Database paths
    script_dir = os.path.dirname(os.path.abspath(__file__))
    messages_db = os.path.join(script_dir, 'whatsapp-mcp', 'whatsapp-bridge', 'store', 'messages.db')
    contacts_db = os.path.join(script_dir, 'whatsapp-mcp', 'whatsapp-bridge', 'store', 'whatsapp.db')
    
    # Check if databases exist
    if not os.path.exists(messages_db):
        print(f"Error: Messages database not found at {messages_db}")
        return
    
    if not os.path.exists(contacts_db):
        print(f"Error: Contacts database not found at {contacts_db}")
        return
    
    # Group JIDs to compare
    group1_jid = "120363315467665376@g.us"
    group2_jid = "120363385526179109@g.us"
    
    print("WhatsApp Group Contact Comparison")
    print("="*40)
    print(f"Group 1: {group1_jid}")
    print(f"Group 2: {group2_jid}")
    print()
    
    # Initialize comparator and run comparison
    comparator = WhatsAppGroupComparator(messages_db, contacts_db)
    
    try:
        common_contacts = comparator.compare_groups(group1_jid, group2_jid)
        
        # Export to CSV
        comparator.export_to_csv(common_contacts)
        
        # Print summary
        comparator.print_summary(common_contacts)
        
    except sqlite3.Error as e:
        print(f"Database error: {e}")
    except Exception as e:
        print(f"An error occurred: {e}")


if __name__ == "__main__":
    main() 