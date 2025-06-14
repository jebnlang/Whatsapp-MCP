#!/usr/bin/env python3
"""
Enhanced WhatsApp Group Contact Comparison Script

This script compares ALL contacts between two WhatsApp groups (including those who never messaged)
and creates a CSV of contacts that exist in both groups.

Features:
- Gets complete group member lists via WhatsApp bridge API with detailed info
- Uses JID-based identification (no phone number extraction needed)
- Falls back to message-based analysis if API unavailable
- Generates CSV with name, jid, admin status columns

Usage:
    python compare_group_contacts_full.py

The script will:
1. Try to get ALL members from both groups via detailed API
2. Fall back to message senders if API unavailable
3. Find contacts that exist in both groups using JIDs
4. Generate detailed CSV with contact information for group management
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
    source: str = "unknown"  # "api", "messages", or "unknown"
    is_admin: bool = False
    is_super_admin: bool = False


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
    
    def get_group_members_via_detailed_api(self, group_jid: str) -> Optional[List[Contact]]:
        """
        Get ALL group members via the enhanced WhatsApp bridge API with detailed info.
        
        Args:
            group_jid: The JID of the group
            
        Returns:
            List of Contact objects if successful, None if failed
        """
        try:
            url = f"{self.api_base_url}/api/group/{group_jid}/members?detailed=true"
            response = requests.get(url, timeout=15)
            
            if response.status_code == 200:
                data = response.json()
                if "members" in data:
                    contacts = []
                    for member in data["members"]:
                        contact = Contact(
                            jid=member.get("jid", ""),
                            name=member.get("display_name", ""),
                            source="detailed_api",
                            is_admin=member.get("is_admin", False),
                            is_super_admin=member.get("is_super_admin", False)
                        )
                        contacts.append(contact)
                    return contacts
            
            print(f"Detailed API request failed with status {response.status_code}: {response.text}")
            return None
            
        except Exception as e:
            print(f"Error calling detailed API for group {group_jid}: {e}")
            return None
    
    def get_group_members_via_simple_api(self, group_jid: str) -> Optional[Set[str]]:
        """
        Get ALL group members via the simple WhatsApp bridge API (fallback).
        
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
            
            print(f"Simple API request failed with status {response.status_code}: {response.text}")
            return None
            
        except Exception as e:
            print(f"Error calling simple API for group {group_jid}: {e}")
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
    
    def get_contact_name_from_db(self, jid: str) -> Optional[str]:
        """
        Get the name for a contact from the contacts database (fallback).
        
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
    
    def get_group_contacts(self, group_jid: str) -> Tuple[List[Contact], str]:
        """
        Get group contacts with full details, trying enhanced API first.
        
        Args:
            group_jid: The JID of the group
            
        Returns:
            Tuple of (contact list, source method used)
        """
        # Try enhanced detailed API first
        if self.check_api_availability():
            print(f"🌐 Trying detailed API for group {group_jid}...")
            detailed_contacts = self.get_group_members_via_detailed_api(group_jid)
            if detailed_contacts is not None:
                print(f"✅ Got detailed info for {len(detailed_contacts)} members")
                return detailed_contacts, "detailed_api"
            
            print("❌ Detailed API failed, trying simple API...")
            # Try simple API as fallback
            simple_jids = self.get_group_members_via_simple_api(group_jid)
            if simple_jids is not None:
                print(f"✅ Got simple JIDs for {len(simple_jids)} members, enhancing with DB lookup...")
                contacts = []
                for jid in simple_jids:
                    contact = Contact(
                        jid=jid,
                        name=self.get_contact_name_from_db(jid),
                        source="simple_api"
                    )
                    contacts.append(contact)
                return contacts, "simple_api"
            
            print("❌ All API methods failed, falling back to message analysis...")
        else:
            print("❌ API not available, using message analysis...")
        
        # Fallback to message-based approach
        message_jids = self.get_group_contacts_from_messages(group_jid)
        contacts = []
        for jid in message_jids:
            contact = Contact(
                jid=jid,
                name=self.get_contact_name_from_db(jid),
                source="messages"
            )
            contacts.append(contact)
        return contacts, "messages"
    
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
        
        # Create lookup dictionaries by JID
        group1_dict = {contact.jid: contact for contact in group1_contacts}
        group2_dict = {contact.jid: contact for contact in group2_contacts}
        
        # Find intersection (common JIDs)
        common_jids = set(group1_dict.keys()).intersection(set(group2_dict.keys()))
        print(f"\n🎯 Found {len(common_jids)} contacts that exist in both groups")
        
        # Determine overall source method
        if group1_source == "detailed_api" and group2_source == "detailed_api":
            overall_source = "detailed_api"
            print("✨ Complete member lists with admin status obtained via enhanced API")
        elif "api" in group1_source and "api" in group2_source:
            overall_source = "api"
            print("✨ Complete member lists obtained via API")
        elif group1_source == "messages" and group2_source == "messages":
            overall_source = "messages"
            print("⚠️  Limited to members who have sent messages")
        else:
            overall_source = "mixed"
            print("⚠️  Mixed data sources - results may be incomplete")
        
        # Create Contact objects for common contacts, preferring Group 1 data
        common_contacts = []
        for jid in common_jids:
            contact = group1_dict[jid]  # Use Group 1 data as primary
            
            # If Group 1 doesn't have name but Group 2 does, use Group 2's
            if not contact.name and group2_dict[jid].name:
                contact.name = group2_dict[jid].name
            
            # Update source to reflect the overall analysis
            contact.source = overall_source
            
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
            
            # Write header - removed phone_number column
            writer.writerow(['name', 'jid', 'source', 'is_admin', 'is_super_admin'])
            
            # Write contacts
            for contact in contacts:
                writer.writerow([
                    contact.name or '',
                    contact.jid,
                    contact.source,
                    contact.is_admin,
                    contact.is_super_admin
                ])
        
        print(f"\n💾 Exported {len(contacts)} contacts to {filename}")
    
    def print_detailed_summary(self, contacts: List[Contact]):
        """Print a detailed summary of the results."""
        print("\n" + "="*70)
        print("DETAILED SUMMARY OF COMMON CONTACTS")
        print("="*70)
        
        # Statistics
        contacts_with_name = [c for c in contacts if c.name]
        admin_contacts = [c for c in contacts if c.is_admin]
        super_admin_contacts = [c for c in contacts if c.is_super_admin]
        detailed_api_contacts = [c for c in contacts if c.source == "detailed_api"]
        
        print(f"📊 Statistics:")
        print(f"   Total common contacts: {len(contacts)}")
        print(f"   Contacts with names: {len(contacts_with_name)} ({len(contacts_with_name)/len(contacts)*100:.1f}%)")
        print(f"   Admin contacts: {len(admin_contacts)}")
        print(f"   Super admin contacts: {len(super_admin_contacts)}")
        print(f"   Via detailed API: {len(detailed_api_contacts)}")
        
        # Sample contacts
        print(f"\n📝 Sample contacts (first 15):")
        print("-" * 80)
        print(f"{'#':<3} {'Name':<25} {'Admin':<6} {'Source':<12} {'JID'}")
        print("-" * 80)
        
        for i, contact in enumerate(contacts[:15], 1):
            name = contact.name or "Unknown"
            admin_status = "Admin" if contact.is_super_admin else ("Mod" if contact.is_admin else "User")
            source = contact.source
            
            # Truncate long names and JIDs for display
            name = name[:24] if len(name) > 24 else name
            jid_display = contact.jid[:25] + "..." if len(contact.jid) > 28 else contact.jid
            
            print(f"{i:<3} {name:<25} {admin_status:<6} {source:<12} {jid_display}")
        
        if len(contacts) > 15:
            print(f"... and {len(contacts) - 15} more contacts")
        
        print("-" * 80)
        
        # Data source explanation
        print(f"\n💡 Data Source Information:")
        if contacts and contacts[0].source == "detailed_api":
            print("   ✅ Enhanced API: Complete member lists with admin status")
            print("   📱 Includes ALL group members (JIDs are used for identification)")
            print("   👑 Admin status information included")
            print("   🔑 JIDs can be used directly for group management operations")
        elif contacts and "api" in contacts[0].source:
            print("   ✅ API-based: Complete member lists obtained")
            print("   📱 Includes ALL group members")
            print("   🔑 JIDs can be used for group management operations")
        elif contacts and contacts[0].source == "messages":
            print("   ⚠️  Message-based analysis: Only members who sent messages")
            print("   🤐 Silent members are not included in this comparison")
        else:
            print("   ⚠️  Mixed data sources: Results may be incomplete")
        
        print(f"\n💡 JID-Based Identification:")
        print("   🆔 Each contact has a unique JID (WhatsApp identifier)")
        print("   🔄 Same JID = same person across both groups")
        print("   🚀 JIDs work directly with group management APIs")
        print("   🔒 @lid format used in groups (privacy-protected)")


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
        print("🚀 Starting enhanced group comparison using JID-based identification...")
        common_contacts = comparator.compare_groups(group1_jid, group2_jid)
        
        # Export to CSV
        comparator.export_to_csv(common_contacts)
        
        # Print detailed summary
        comparator.print_detailed_summary(common_contacts)
        
        print(f"\n🎉 Analysis complete! Check 'common_contacts_full.csv' for full results.")
        print(f"💡 The JIDs in the CSV can be used directly for group management operations.")
        
    except sqlite3.Error as e:
        print(f"❌ Database error: {e}")
    except Exception as e:
        print(f"❌ An error occurred: {e}")


if __name__ == "__main__":
    main() 