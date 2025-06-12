#!/usr/bin/env python3
"""
Phone Number to WhatsApp JID Lookup Tool

This script takes a phone number and finds the corresponding WhatsApp JID(s)
by searching through:
1. WhatsApp contacts database
2. Group member lists 
3. Message history

Usage:
    python phone_to_jid_lookup.py +972523451451
    python phone_to_jid_lookup.py 972523451451
"""

import sqlite3
import requests
import json
import re
import sys
import argparse
from typing import List, Dict, Set, Optional, Tuple
from dataclasses import dataclass


@dataclass
class ContactMatch:
    """Represents a contact match found in the system"""
    jid: str
    name: Optional[str] = None
    phone_number: Optional[str] = None
    source: str = ""  # where we found this match
    groups: List[str] = None  # which groups this contact is in
    
    def __post_init__(self):
        if self.groups is None:
            self.groups = []


class PhoneToJIDLookup:
    def __init__(self, messages_db_path: str = "whatsapp-mcp/whatsapp-bridge/store/messages.db", 
                 contacts_db_path: str = "whatsapp-mcp/whatsapp-bridge/store/whatsapp.db",
                 api_base_url: str = "http://localhost:8080"):
        self.messages_db_path = messages_db_path
        self.contacts_db_path = contacts_db_path
        self.api_base_url = api_base_url
        
    def normalize_phone_number(self, phone: str) -> List[str]:
        """
        Normalize phone number to different possible formats
        
        Args:
            phone: Input phone number (e.g., "+972523451451", "972523451451")
            
        Returns:
            List of possible normalized formats to search for
        """
        # Remove all non-digits
        digits_only = re.sub(r'[^\d]', '', phone)
        
        # Generate possible formats
        formats = [
            digits_only,  # 972523451451
            f"+{digits_only}",  # +972523451451
            f"{digits_only}@s.whatsapp.net",  # 972523451451@s.whatsapp.net
            f"+{digits_only}@s.whatsapp.net",  # +972523451451@s.whatsapp.net
        ]
        
        # Handle Israeli numbers specifically (remove leading 972, add 0)
        if digits_only.startswith('972') and len(digits_only) == 12:
            israeli_format = '0' + digits_only[3:]  # 0523451451
            formats.extend([
                israeli_format,
                f"{israeli_format}@s.whatsapp.net"
            ])
        
        # Remove duplicates while preserving order
        seen = set()
        unique_formats = []
        for fmt in formats:
            if fmt not in seen:
                seen.add(fmt)
                unique_formats.append(fmt)
                
        return unique_formats
    
    def search_contacts_database(self, phone: str) -> List[ContactMatch]:
        """
        Search the WhatsApp contacts database for phone number matches
        
        Args:
            phone: Phone number to search for
            
        Returns:
            List of ContactMatch objects found in contacts database
        """
        matches = []
        phone_formats = self.normalize_phone_number(phone)
        
        try:
            conn = sqlite3.connect(self.contacts_db_path)
            cursor = conn.cursor()
            
            # Search in contacts table
            for phone_format in phone_formats:
                # Search by JID
                cursor.execute("""
                    SELECT their_jid, first_name, full_name, push_name 
                    FROM whatsmeow_contacts 
                    WHERE their_jid LIKE ? OR their_jid = ?
                """, (f"%{phone_format}%", phone_format))
                
                results = cursor.fetchall()
                for row in results:
                    jid, first_name, full_name, push_name = row
                    name = full_name or first_name or push_name or "Unknown"
                    
                    matches.append(ContactMatch(
                        jid=jid,
                        name=name,
                        phone_number=phone_format,
                        source="contacts_database"
                    ))
            
        except sqlite3.Error as e:
            print(f"Database error: {e}")
        finally:
            if conn:
                conn.close()
        
        return matches
    
    def search_message_history(self, phone: str) -> List[ContactMatch]:
        """
        Search message history for senders matching the phone number
        
        Args:
            phone: Phone number to search for
            
        Returns:
            List of ContactMatch objects found in message history
        """
        matches = []
        phone_formats = self.normalize_phone_number(phone)
        
        try:
            conn = sqlite3.connect(self.messages_db_path)
            cursor = conn.cursor()
            
            for phone_format in phone_formats:
                # Search message senders
                cursor.execute("""
                    SELECT DISTINCT sender, chat_jid, COUNT(*) as message_count
                    FROM messages 
                    WHERE sender LIKE ? OR sender = ?
                    GROUP BY sender, chat_jid
                    ORDER BY message_count DESC
                """, (f"%{phone_format}%", phone_format))
                
                results = cursor.fetchall()
                for row in results:
                    sender_jid, chat_jid, msg_count = row
                    
                    matches.append(ContactMatch(
                        jid=sender_jid,
                        name=f"Message Sender ({msg_count} messages)",
                        phone_number=phone_format,
                        source=f"message_history_{chat_jid}",
                        groups=[chat_jid] if chat_jid.endswith('@g.us') else []
                    ))
            
        except sqlite3.Error as e:
            print(f"Database error: {e}")
        finally:
            if conn:
                conn.close()
        
        return matches
    
    def get_group_lists(self) -> Dict[str, List[str]]:
        """
        Get member lists for all groups via API
        
        Returns:
            Dictionary mapping group_jid -> list of member JIDs
        """
        groups = {}
        
        # Get list of group chats
        try:
            conn = sqlite3.connect(self.messages_db_path)
            cursor = conn.cursor()
            cursor.execute("SELECT DISTINCT jid FROM chats WHERE jid LIKE '%@g.us'")
            group_jids = [row[0] for row in cursor.fetchall()]
            conn.close()
            
            # Get members for each group via API
            for group_jid in group_jids:
                try:
                    url = f"{self.api_base_url}/api/group/{group_jid}/members"
                    response = requests.get(url, timeout=5)
                    if response.status_code == 200:
                        data = response.json()
                        if "members" in data:
                            groups[group_jid] = data["members"]
                except Exception as e:
                    print(f"Warning: Could not get members for {group_jid}: {e}")
                    
        except Exception as e:
            print(f"Error getting group lists: {e}")
        
        return groups
    
    def search_group_members(self, phone: str) -> List[ContactMatch]:
        """
        Search group member lists for phone number matches
        
        Args:
            phone: Phone number to search for
            
        Returns:
            List of ContactMatch objects found in group members
        """
        matches = []
        phone_formats = self.normalize_phone_number(phone)
        
        print(f"🔍 Searching for phone formats: {phone_formats}")
        
        # Get all group member lists
        groups = self.get_group_lists()
        
        for group_jid, members in groups.items():
            for member_jid in members:
                # Check if any phone format matches the member JID
                for phone_format in phone_formats:
                    if (phone_format in member_jid or 
                        member_jid == phone_format or
                        member_jid.startswith(phone_format.replace('+', ''))):
                        
                        matches.append(ContactMatch(
                            jid=member_jid,
                            name="Group Member",
                            phone_number=phone_format,
                            source=f"group_member_{group_jid}",
                            groups=[group_jid]
                        ))
        
        return matches
    
    def fuzzy_search_by_name(self, phone: str) -> List[ContactMatch]:
        """
        Try to find contacts by searching for partial matches or known names
        This is useful when phone formats don't match exactly
        
        Args:
            phone: Phone number to search for
            
        Returns:
            List of ContactMatch objects found via fuzzy matching
        """
        matches = []
        
        # Extract the last 7-10 digits for fuzzy matching
        digits = re.sub(r'[^\d]', '', phone)
        if len(digits) >= 7:
            last_digits = digits[-7:]  # Last 7 digits
            
            try:
                conn = sqlite3.connect(self.contacts_db_path)
                cursor = conn.cursor()
                
                # Search for JIDs containing these digits
                cursor.execute("""
                    SELECT their_jid, first_name, full_name, push_name 
                    FROM whatsmeow_contacts 
                    WHERE their_jid LIKE ?
                """, (f"%{last_digits}%",))
                
                results = cursor.fetchall()
                for row in results:
                    jid, first_name, full_name, push_name = row
                    name = full_name or first_name or push_name or "Unknown"
                    
                    matches.append(ContactMatch(
                        jid=jid,
                        name=name,
                        phone_number=f"fuzzy_match_{last_digits}",
                        source="fuzzy_search"
                    ))
                    
            except sqlite3.Error as e:
                print(f"Database error in fuzzy search: {e}")
            finally:
                if conn:
                    conn.close()
        
        return matches
    
    def lookup_phone_number(self, phone: str, include_fuzzy: bool = True) -> List[ContactMatch]:
        """
        Main lookup function - searches all sources for phone number matches
        
        Args:
            phone: Phone number to search for
            include_fuzzy: Whether to include fuzzy matching results
            
        Returns:
            List of all ContactMatch objects found across all sources
        """
        print(f"🔍 Looking up phone number: {phone}")
        print(f"📋 Normalized formats: {self.normalize_phone_number(phone)}")
        
        all_matches = []
        
        # Search contacts database
        print("\n📖 Searching contacts database...")
        contacts_matches = self.search_contacts_database(phone)
        all_matches.extend(contacts_matches)
        print(f"   Found {len(contacts_matches)} matches in contacts database")
        
        # Search message history
        print("\n💬 Searching message history...")
        message_matches = self.search_message_history(phone)
        all_matches.extend(message_matches)
        print(f"   Found {len(message_matches)} matches in message history")
        
        # Search group members
        print("\n👥 Searching group members...")
        group_matches = self.search_group_members(phone)
        all_matches.extend(group_matches)
        print(f"   Found {len(group_matches)} matches in group members")
        
        # Fuzzy search if enabled and no exact matches found
        if include_fuzzy and len(all_matches) == 0:
            print("\n🔍 Performing fuzzy search...")
            fuzzy_matches = self.fuzzy_search_by_name(phone)
            all_matches.extend(fuzzy_matches)
            print(f"   Found {len(fuzzy_matches)} fuzzy matches")
        
        # Remove duplicates based on JID
        unique_matches = {}
        for match in all_matches:
            if match.jid not in unique_matches:
                unique_matches[match.jid] = match
            else:
                # Merge group information
                existing = unique_matches[match.jid]
                existing.groups.extend(match.groups)
                existing.groups = list(set(existing.groups))  # Remove duplicates
                
                # Update name if current match has a better name
                if match.name and match.name != "Group Member" and existing.name == "Group Member":
                    existing.name = match.name
        
        return list(unique_matches.values())
    
    def print_results(self, matches: List[ContactMatch], phone: str):
        """
        Print formatted results of the phone number lookup
        
        Args:
            matches: List of ContactMatch objects to display
            phone: Original phone number searched for
        """
        print(f"\n" + "="*60)
        print(f"📞 PHONE NUMBER LOOKUP RESULTS FOR: {phone}")
        print(f"="*60)
        
        if not matches:
            print("❌ No matches found for this phone number.")
            print("\n💡 Suggestions:")
            print("   - Try with/without country code (+972 vs 972)")
            print("   - Try with/without leading zero (0523... vs 523...)")
            print("   - Check if the contact uses WhatsApp Business or has a different number")
            return
        
        print(f"✅ Found {len(matches)} match(es):\n")
        
        for i, match in enumerate(matches, 1):
            print(f"🔹 Match #{i}:")
            print(f"   📱 JID: {match.jid}")
            print(f"   👤 Name: {match.name or 'Unknown'}")
            print(f"   📞 Phone: {match.phone_number or 'N/A'}")
            print(f"   🔍 Source: {match.source}")
            
            if match.groups:
                print(f"   👥 Groups ({len(match.groups)}):")
                for group in match.groups:
                    print(f"      - {group}")
            else:
                print(f"   👥 Groups: None")
            print()


def main():
    parser = argparse.ArgumentParser(description='Look up WhatsApp JID from phone number')
    parser.add_argument('phone', help='Phone number to look up (e.g., +972523451451)')
    parser.add_argument('--no-fuzzy', action='store_true', help='Disable fuzzy matching')
    parser.add_argument('--messages-db', default='whatsapp-mcp/whatsapp-bridge/store/messages.db',
                        help='Path to messages database')
    parser.add_argument('--contacts-db', default='whatsapp-mcp/whatsapp-bridge/store/whatsapp.db',
                        help='Path to contacts database')
    parser.add_argument('--api-url', default='http://localhost:8080',
                        help='WhatsApp bridge API base URL')
    
    args = parser.parse_args()
    
    # Create lookup instance
    lookup = PhoneToJIDLookup(
        messages_db_path=args.messages_db,
        contacts_db_path=args.contacts_db,
        api_base_url=args.api_url
    )
    
    # Perform lookup
    matches = lookup.lookup_phone_number(args.phone, include_fuzzy=not args.no_fuzzy)
    
    # Print results
    lookup.print_results(matches, args.phone)
    
    # Return matches for programmatic use
    return matches


if __name__ == "__main__":
    try:
        matches = main()
        
        # Exit with appropriate code
        if matches:
            print(f"\n✅ Successfully found {len(matches)} match(es)!")
            sys.exit(0)
        else:
            print(f"\n❌ No matches found.")
            sys.exit(1)
            
    except KeyboardInterrupt:
        print(f"\n\n⚠️  Search interrupted by user.")
        sys.exit(1)
    except Exception as e:
        print(f"\n❌ Error during lookup: {e}")
        sys.exit(1) 