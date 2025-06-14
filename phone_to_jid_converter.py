#!/usr/bin/env python3
"""
Phone Number to JID Converter Script

This script takes phone numbers and finds their corresponding WhatsApp JIDs
in the contacts database. Useful for creating whitelists of contacts to skip
during group management operations.

Features:
- Converts phone numbers to JIDs using database lookup
- Handles multiple phone number formats (Israeli, international)
- Cross-references with names when available
- Outputs JIDs that can be used for group management

Usage:
    python phone_to_jid_converter.py

The script will:
1. Prompt for phone numbers (one per line)
2. Search contacts database for matching JIDs
3. Output JIDs for whitelist usage
"""

import sqlite3
import os
import re
from typing import List, Dict, Optional, Tuple
from dataclasses import dataclass


@dataclass
class ContactMatch:
    """Represents a contact match result"""
    phone_number: str
    jid: str
    name: Optional[str] = None
    match_type: str = "exact"  # "exact", "normalized", "name_match"


class PhoneToJIDConverter:
    def __init__(self, contacts_db_path: str):
        """
        Initialize the converter with contacts database path.
        
        Args:
            contacts_db_path: Path to whatsapp.db
        """
        self.contacts_db_path = contacts_db_path
        
    def normalize_phone_number(self, phone: str) -> List[str]:
        """
        Generate possible phone number variations for matching.
        
        Args:
            phone: Input phone number in any format
            
        Returns:
            List of normalized phone number variations
        """
        # Remove all non-digit characters
        digits_only = re.sub(r'[^\d]', '', phone)
        
        variations = [digits_only]
        
        # Handle Israeli numbers (972 country code)
        if digits_only.startswith('972'):
            # Add version without country code
            without_country = digits_only[3:]
            variations.append(without_country)
            # Add version with leading 0
            if not without_country.startswith('0'):
                variations.append('0' + without_country)
        elif digits_only.startswith('0'):
            # Remove leading 0 and add 972
            without_zero = digits_only[1:]
            variations.append('972' + without_zero)
            variations.append(without_zero)
        else:
            # Add 972 prefix
            variations.append('972' + digits_only)
            # Add leading 0
            variations.append('0' + digits_only)
        
        # Remove duplicates while preserving order
        seen = set()
        unique_variations = []
        for var in variations:
            if var not in seen:
                seen.add(var)
                unique_variations.append(var)
        
        return unique_variations
    
    def search_by_phone_number(self, phone: str) -> List[ContactMatch]:
        """
        Search for contacts by phone number.
        
        Args:
            phone: Phone number to search for
            
        Returns:
            List of ContactMatch objects
        """
        variations = self.normalize_phone_number(phone)
        matches = []
        
        conn = sqlite3.connect(self.contacts_db_path)
        cursor = conn.cursor()
        
        for variation in variations:
            # Search for @s.whatsapp.net JIDs
            jid_pattern = f"{variation}@s.whatsapp.net"
            
            query = """
            SELECT their_jid, first_name, full_name, push_name 
            FROM whatsmeow_contacts 
            WHERE their_jid = ?
            """
            
            cursor.execute(query, (jid_pattern,))
            result = cursor.fetchone()
            
            if result:
                jid, first_name, full_name, push_name = result
                name = full_name or push_name or first_name
                
                match_type = "exact" if variation == re.sub(r'[^\d]', '', phone) else "normalized"
                
                matches.append(ContactMatch(
                    phone_number=phone,
                    jid=jid,
                    name=name,
                    match_type=match_type
                ))
                break  # Found exact match, no need to try other variations
        
        conn.close()
        return matches
    
    def search_by_name(self, name: str) -> List[ContactMatch]:
        """
        Search for contacts by name (fallback method).
        
        Args:
            name: Name to search for
            
        Returns:
            List of ContactMatch objects
        """
        matches = []
        
        conn = sqlite3.connect(self.contacts_db_path)
        cursor = conn.cursor()
        
        query = """
        SELECT their_jid, first_name, full_name, push_name 
        FROM whatsmeow_contacts 
        WHERE (first_name LIKE ? OR full_name LIKE ? OR push_name LIKE ?)
        AND their_jid LIKE '%@s.whatsapp.net'
        LIMIT 10
        """
        
        search_pattern = f"%{name}%"
        cursor.execute(query, (search_pattern, search_pattern, search_pattern))
        results = cursor.fetchall()
        
        for jid, first_name, full_name, push_name in results:
            contact_name = full_name or push_name or first_name
            
            # Extract phone number from JID
            phone_from_jid = jid.split('@')[0] if '@' in jid else ""
            
            matches.append(ContactMatch(
                phone_number=phone_from_jid,
                jid=jid,
                name=contact_name,
                match_type="name_match"
            ))
        
        conn.close()
        return matches
    
    def find_contact(self, input_str: str) -> List[ContactMatch]:
        """
        Find contact by phone number or name.
        
        Args:
            input_str: Phone number or name to search for
            
        Returns:
            List of ContactMatch objects
        """
        # Check if input looks like a phone number
        digits_only = re.sub(r'[^\d]', '', input_str)
        
        if len(digits_only) >= 7:  # Probably a phone number
            matches = self.search_by_phone_number(input_str)
            if matches:
                return matches
        
        # Try searching by name
        if len(input_str.strip()) > 0:
            return self.search_by_name(input_str.strip())
        
        return []
    
    def convert_multiple(self, inputs: List[str]) -> Dict[str, List[ContactMatch]]:
        """
        Convert multiple phone numbers/names to JIDs.
        
        Args:
            inputs: List of phone numbers or names
            
        Returns:
            Dictionary mapping input to list of matches
        """
        results = {}
        
        for input_str in inputs:
            input_str = input_str.strip()
            if input_str:
                matches = self.find_contact(input_str)
                results[input_str] = matches
        
        return results
    
    def print_results(self, results: Dict[str, List[ContactMatch]]):
        """Print conversion results in a readable format."""
        print("\n" + "="*70)
        print("PHONE NUMBER TO JID CONVERSION RESULTS")
        print("="*70)
        
        found_count = 0
        total_count = len(results)
        
        for input_str, matches in results.items():
            print(f"\n📱 Input: {input_str}")
            
            if matches:
                found_count += 1
                for i, match in enumerate(matches, 1):
                    print(f"   {i}. Name: {match.name or 'Unknown'}")
                    print(f"      JID: {match.jid}")
                    print(f"      Phone: {match.phone_number}")
                    print(f"      Match: {match.match_type}")
            else:
                print("   ❌ No matches found")
        
        print(f"\n📊 Summary: {found_count}/{total_count} inputs found")
        
        # Generate whitelist
        if found_count > 0:
            print(f"\n🔒 JIDs for whitelist (copy these for group management):")
            print("-" * 50)
            all_jids = []
            for matches in results.values():
                for match in matches:
                    if match.jid not in all_jids:
                        all_jids.append(match.jid)
            
            for jid in all_jids:
                print(f'"{jid}",')
            
            print(f"\n💡 Found {len(all_jids)} unique JIDs to whitelist")


def main():
    """Main function to run the phone to JID converter."""
    # Database path
    script_dir = os.path.dirname(os.path.abspath(__file__))
    contacts_db = os.path.join(script_dir, 'whatsapp-mcp', 'whatsapp-bridge', 'store', 'whatsapp.db')
    
    # Check if database exists
    if not os.path.exists(contacts_db):
        print(f"❌ Error: Contacts database not found at {contacts_db}")
        return
    
    print("📞 WhatsApp Phone Number to JID Converter")
    print("="*50)
    print("Enter phone numbers or names (one per line)")
    print("Supported formats:")
    print("  • +972-52-345-1451")
    print("  • 972523451451")
    print("  • 0523451451")
    print("  • Ben Lang (name search)")
    print("Press Enter twice when done, or Ctrl+C to exit")
    print("-" * 50)
    
    inputs = []
    
    try:
        while True:
            line = input("Enter phone/name: ").strip()
            if not line:
                if inputs:
                    break
                else:
                    continue
            inputs.append(line)
            
    except KeyboardInterrupt:
        print("\n\n👋 Exiting...")
        return
    
    if not inputs:
        print("No inputs provided.")
        return
    
    # Initialize converter and process inputs
    converter = PhoneToJIDConverter(contacts_db)
    results = converter.convert_multiple(inputs)
    
    # Print results
    converter.print_results(results)


if __name__ == "__main__":
    main() 