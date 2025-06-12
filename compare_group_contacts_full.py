#!/usr/bin/env python3
"""
Enhanced WhatsApp Group Contact Comparison Script

This script compares ALL contacts between two WhatsApp groups (including those who never messaged)
and creates a CSV of contacts that exist in both groups.

Features:
- Gets complete group member lists via WhatsApp bridge API
- Falls back to message-based analysis if API unavailable
- Extracts phone numbers and contact names
- Generates CSV with phone_number, name, jid columns

Usage:
    python compare_group_contacts_full.py

The script will:
1. Try to get ALL members from both groups via API
2. Fall back to message senders if API unavailable
3. Find contacts that exist in both groups
4. Generate detailed CSV with contact information
"""

import sqlite3
import csv
import os
import requests
import json
import time
from typing import Set, Dict, List, Tuple, Optional
from dataclasses import dataclass


@dataclass
class Contact:
    """Represents a WhatsApp contact"""
    jid: str
    name: Optional[str] = None
    phone_number: Optional[str] = None
    source: str = "unknown"  # "api", "messages", or "unknown"


class EnhancedWhatsAppGroupComparator:
    def __init__(self, messages_db_path: str, contacts_db_path: str, api_base_url: str = "http://localhost:8080"):
        """
        Initialize the comparator with database paths and API URL.
        
        Args:
            messages_db_path: Path to messages.db
            contacts_db_path: Path to whatsapp.db
            api_base_url: Base URL for WhatsApp bridge API
        """
        self.messages_db_path = messages_db_path
        self.contacts_db_path = contacts_db_path
        self.api_base_url = api_base_url
        
    def check_api_availability(self) -> bool:
        """
        Check if the WhatsApp bridge API is available.
        
        Returns:
            True if API is available, False otherwise
        """
        try:
            response = requests.get(f"{self.api_base_url}/api/send", timeout=5)
            return True
        except:
            return False
    
    def get_group_members_via_api(self, group_jid: str) -> Optional[Set[str]]:
        """
        Get ALL group members via the WhatsApp bridge API.
        
        Args:
            group_jid: The JID of the group
            
        Returns:
            Set of member JIDs if successful, None if failed
        """
        try:
            url = f"{self.api_base_url}/api/group/{group_jid}/members"
            response = requests.get(url, timeout=10)
            
            if response.status_code == 200:
                data = response.json()
                if "members" in data:
                    return set(data["members"])
            
            print(f"API request failed with status {response.status_code}: {response.text}")
            return None
            
        except Exception as e:
            print(f"Error calling API for group {group_jid}: {e}")
            return None
    
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
    
    def get_group_contacts_from_messages(self, group_jid: str) -> Set[str]:
        """
        Get unique contacts (senders) from a specific group using message database.
        This is the fallback method when API is not available.
        
        Args:
            group_jid: The JID of the group
            
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
    
    def get_group_contacts(self, group_jid: str) -> Tuple[Set[str], str]:
        """
        Get group contacts, trying API first, then falling back to messages.
        
        Args:
            group_jid: The JID of the group
            
        Returns:
            Tuple of (contact set, source method used)
        """
        # Try API first
        if self.check_api_availability():
            print(f"🌐 Trying API for group {group_jid}...")
            api_contacts = self.get_group_members_via_api(group_jid)
            if api_contacts is not None:
                return api_contacts, "api"
            print("❌ API failed, falling back to message analysis...")
        else:
            print("❌ API not available, using message analysis...")
        
        # Fallback to message-based approach
        message_contacts = self.get_group_contacts_from_messages(group_jid)
        return message_contacts, "messages"
    
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
        print("="*60)
        print("ENHANCED GROUP CONTACT COMPARISON")
        print("="*60)
        print(f"Group 1: {group1_jid}")
        print(f"Group 2: {group2_jid}")
        print()
        
        # Get contacts from both groups
        print("📋 Extracting contacts from Group 1...")
        group1_contacts, group1_source = self.get_group_contacts(group1_jid)
        print(f"✅ Found {len(group1_contacts)} contacts in Group 1 (via {group1_source})")
        
        print(f"\n📋 Extracting contacts from Group 2...")
        group2_contacts, group2_source = self.get_group_contacts(group2_jid)
        print(f"✅ Found {len(group2_contacts)} contacts in Group 2 (via {group2_source})")
        
        # Find intersection (common contacts)
        common_jids = group1_contacts.intersection(group2_contacts)
        print(f"\n🎯 Found {len(common_jids)} contacts that exist in both groups")
        
        # Determine overall source method
        if group1_source == "api" and group2_source == "api":
            overall_source = "api"
            print("✨ Complete member lists obtained via API")
        elif group1_source == "messages" and group2_source == "messages":
            overall_source = "messages"
            print("⚠️  Limited to members who have sent messages")
        else:
            overall_source = "mixed"
            print("⚠️  Mixed data sources - results may be incomplete")
        
        # Create Contact objects with names and phone numbers
        print(f"\n🔍 Looking up contact details...")
        common_contacts = []
        for jid in common_jids:
            contact = Contact(
                jid=jid,
                name=self.get_contact_name(jid),
                phone_number=self.extract_phone_number(jid),
                source=overall_source
            )
            common_contacts.append(contact)
        
        # Sort by name (put unnamed contacts at the end)
        common_contacts.sort(key=lambda c: (c.name is None, c.name or ""))
        
        return common_contacts
    
    def export_to_csv(self, contacts: List[Contact], filename: str = "common_contacts_full.csv"):
        """
        Export contacts to a CSV file.
        
        Args:
            contacts: List of Contact objects
            filename: Output CSV filename
        """
        with open(filename, 'w', newline='', encoding='utf-8') as csvfile:
            writer = csv.writer(csvfile)
            
            # Write header
            writer.writerow(['phone_number', 'name', 'jid', 'source'])
            
            # Write contacts
            for contact in contacts:
                writer.writerow([
                    contact.phone_number or '',
                    contact.name or '',
                    contact.jid,
                    contact.source
                ])
        
        print(f"\n💾 Exported {len(contacts)} contacts to {filename}")
    
    def print_detailed_summary(self, contacts: List[Contact]):
        """Print a detailed summary of the results."""
        print("\n" + "="*70)
        print("DETAILED SUMMARY OF COMMON CONTACTS")
        print("="*70)
        
        # Statistics
        contacts_with_phone = [c for c in contacts if c.phone_number]
        contacts_with_name = [c for c in contacts if c.name]
        contacts_api_source = [c for c in contacts if c.source == "api"]
        contacts_message_source = [c for c in contacts if c.source == "messages"]
        
        print(f"📊 Statistics:")
        print(f"   Total common contacts: {len(contacts)}")
        print(f"   Contacts with phone numbers: {len(contacts_with_phone)}")
        print(f"   Contacts with names: {len(contacts_with_name)}")
        print(f"   Via API (complete): {len(contacts_api_source)}")
        print(f"   Via messages (limited): {len(contacts_message_source)}")
        
        # Sample contacts
        print(f"\n📝 Sample contacts (first 15):")
        print("-" * 70)
        print(f"{'#':<3} {'Name':<25} {'Phone':<15} {'Source':<8} {'JID'}")
        print("-" * 70)
        
        for i, contact in enumerate(contacts[:15], 1):
            name = contact.name or "Unknown"
            phone = contact.phone_number or "No phone"
            source = contact.source
            
            # Truncate long names and JIDs for display
            name = name[:24] if len(name) > 24 else name
            jid_display = contact.jid[:30] + "..." if len(contact.jid) > 33 else contact.jid
            
            print(f"{i:<3} {name:<25} {phone:<15} {source:<8} {jid_display}")
        
        if len(contacts) > 15:
            print(f"... and {len(contacts) - 15} more contacts")
        
        print("-" * 70)
        
        # Data source explanation
        print(f"\n💡 Data Source Information:")
        if contacts and contacts[0].source == "api":
            print("   ✅ Complete member lists: Includes ALL group members")
            print("   📱 This includes members who never sent messages")
        elif contacts and contacts[0].source == "messages":
            print("   ⚠️  Message-based analysis: Only members who sent messages")
            print("   🤐 Silent members are not included in this comparison")
        else:
            print("   ⚠️  Mixed data sources: Results may be incomplete")


def main():
    """Main function to run the enhanced group comparison."""
    # Database paths
    script_dir = os.path.dirname(os.path.abspath(__file__))
    messages_db = os.path.join(script_dir, 'whatsapp-mcp', 'whatsapp-bridge', 'store', 'messages.db')
    contacts_db = os.path.join(script_dir, 'whatsapp-mcp', 'whatsapp-bridge', 'store', 'whatsapp.db')
    
    # Check if databases exist
    if not os.path.exists(messages_db):
        print(f"❌ Error: Messages database not found at {messages_db}")
        return
    
    if not os.path.exists(contacts_db):
        print(f"❌ Error: Contacts database not found at {contacts_db}")
        return
    
    # Group JIDs to compare
    group1_jid = "120363315467665376@g.us"
    group2_jid = "120363385526179109@g.us"
    
    # Initialize comparator and run comparison
    comparator = EnhancedWhatsAppGroupComparator(messages_db, contacts_db)
    
    try:
        common_contacts = comparator.compare_groups(group1_jid, group2_jid)
        
        # Export to CSV
        comparator.export_to_csv(common_contacts)
        
        # Print detailed summary
        comparator.print_detailed_summary(common_contacts)
        
        print(f"\n🎉 Analysis complete! Check 'common_contacts_full.csv' for full results.")
        
    except sqlite3.Error as e:
        print(f"❌ Database error: {e}")
    except Exception as e:
        print(f"❌ An error occurred: {e}")


if __name__ == "__main__":
    main() 