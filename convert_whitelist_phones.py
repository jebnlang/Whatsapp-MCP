#!/usr/bin/env python3
"""
Convert Phone Numbers to JIDs for Whitelist

This script converts the specified phone numbers to JIDs and updates the whitelist file.
"""

import sqlite3
import os
import re
from typing import List, Dict, Optional, Set

class PhoneToJIDConverter:
    def __init__(self, contacts_db_path: str):
        self.contacts_db_path = contacts_db_path
        
    def normalize_phone_number(self, phone: str) -> List[str]:
        """Generate possible phone number variations for matching."""
        digits_only = re.sub(r'[^\d]', '', phone)
        variations = [digits_only]
        
        # Handle Israeli numbers (972 country code)
        if digits_only.startswith('972'):
            without_country = digits_only[3:]
            variations.append(without_country)
            if not without_country.startswith('0'):
                variations.append('0' + without_country)
        elif digits_only.startswith('0'):
            without_zero = digits_only[1:]
            variations.append('972' + without_zero)
            variations.append(without_zero)
        else:
            variations.append('972' + digits_only)
            variations.append('0' + digits_only)
        
        # Remove duplicates while preserving order
        seen = set()
        unique_variations = []
        for var in variations:
            if var not in seen:
                seen.add(var)
                unique_variations.append(var)
        
        return unique_variations
    
    def find_jid_for_phone(self, phone: str) -> Optional[str]:
        """Find JID for a phone number in contacts database."""
        variations = self.normalize_phone_number(phone)
        
        conn = sqlite3.connect(self.contacts_db_path)
        cursor = conn.cursor()
        
        for variation in variations:
            jid_pattern = f"{variation}@s.whatsapp.net"
            
            query = """
            SELECT their_jid, first_name, full_name, push_name 
            FROM whatsmeow_contacts 
            WHERE their_jid = ?
            """
            
            cursor.execute(query, (jid_pattern,))
            result = cursor.fetchone()
            
            if result:
                conn.close()
                return result[0]  # Return the JID
                
        conn.close()
        return None

def main():
    # Phone numbers to whitelist
    phones_to_whitelist = [
        "0528209295",
        "0546667650", 
        "0546732529",
        "0527455314",
        "0546666890"
    ]
    
    print("🔒 Converting Phone Numbers to JIDs for Whitelist")
    print("=" * 55)
    
    # Database path
    script_dir = os.path.dirname(os.path.abspath(__file__))
    contacts_db = os.path.join(script_dir, 'whatsapp-mcp', 'whatsapp-bridge', 'store', 'whatsapp.db')
    
    if not os.path.exists(contacts_db):
        print(f"❌ Error: Contacts database not found at {contacts_db}")
        return
    
    converter = PhoneToJIDConverter(contacts_db)
    
    # Convert phone numbers to JIDs
    whitelist_jids = []
    found_count = 0
    
    for phone in phones_to_whitelist:
        print(f"\n📱 Converting: {phone}")
        jid = converter.find_jid_for_phone(phone)
        
        if jid:
            whitelist_jids.append(jid)
            found_count += 1
            print(f"   ✅ Found: {jid}")
        else:
            print(f"   ❌ Not found in contacts database")
    
    print(f"\n📊 Summary: {found_count}/{len(phones_to_whitelist)} phone numbers converted to JIDs")
    
    if not whitelist_jids:
        print("❌ No JIDs found to add to whitelist")
        return
    
    # Read existing whitelist
    whitelist_file = "whitelist.txt"
    existing_jids = set()
    
    if os.path.exists(whitelist_file):
        with open(whitelist_file, 'r', encoding='utf-8') as f:
            for line in f:
                line = line.strip()
                if line and not line.startswith('#'):
                    existing_jids.add(line)
    
    # Add new JIDs to whitelist
    new_jids = []
    for jid in whitelist_jids:
        if jid not in existing_jids:
            new_jids.append(jid)
    
    if new_jids:
        print(f"\n🔒 Adding {len(new_jids)} new JIDs to whitelist:")
        
        with open(whitelist_file, 'a', encoding='utf-8') as f:
            f.write(f"\n# Auto-added from phone numbers on {__import__('datetime').datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")
            for jid in new_jids:
                f.write(f"{jid}\n")
                print(f"   • {jid}")
        
        print(f"\n✅ Updated whitelist file: {whitelist_file}")
        print(f"💡 Total protected contacts: {len(existing_jids) + len(new_jids)}")
    else:
        print(f"\n✅ All found JIDs were already in the whitelist")
        print(f"💡 Total protected contacts: {len(existing_jids)}")

if __name__ == "__main__":
    main() 