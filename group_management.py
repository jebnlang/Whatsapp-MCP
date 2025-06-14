#!/usr/bin/env python3
"""
WhatsApp Group Management Script

This script provides functionality to programmatically remove users from WhatsApp groups
by extending the existing WhatsApp bridge with group management capabilities.

Features:
1. Remove users from groups programmatically
2. Bulk removal from CSV of common contacts
3. Whitelist support to protect important contacts
4. Admin permission validation
5. Detailed logging and error handling

Requirements:
- WhatsApp bridge server running on localhost:8080
- Admin permissions in the target groups
- CSV file with contacts to remove (from previous analysis)
"""

import requests
import json
import csv
import time
import logging
from typing import List, Dict, Set, Optional, Tuple
from dataclasses import dataclass
import argparse
import sys


@dataclass
class RemovalResult:
    """Result of a user removal operation"""
    jid: str
    group_jid: str
    success: bool
    message: str
    error_code: Optional[str] = None
    skipped: bool = False
    skip_reason: Optional[str] = None


class GroupManager:
    """Manages WhatsApp group operations via the bridge API"""
    
    def __init__(self, bridge_url: str = "http://localhost:8080", whitelist: Optional[Set[str]] = None):
        self.bridge_url = bridge_url.rstrip('/')
        self.whitelist = whitelist or set()
        self.session = requests.Session()
        self.session.headers.update({
            'Content-Type': 'application/json',
            'Accept': 'application/json'
        })
        
        # Setup logging
        logging.basicConfig(
            level=logging.INFO,
            format='%(asctime)s - %(levelname)s - %(message)s',
            handlers=[
                logging.FileHandler('group_management.log'),
                logging.StreamHandler(sys.stdout)
            ]
        )
        self.logger = logging.getLogger(__name__)
        
        if self.whitelist:
            self.logger.info(f"🔒 Whitelist active with {len(self.whitelist)} protected JIDs")
    
    def is_whitelisted(self, jid: str) -> bool:
        """Check if a JID is in the whitelist"""
        return jid in self.whitelist
    
    def get_group_members(self, group_jid: str) -> List[str]:
        """Get all members of a group"""
        try:
            url = f"{self.bridge_url}/api/group/{group_jid}/members"
            response = self.session.get(url)
            response.raise_for_status()
            
            data = response.json()
            return data.get('members', [])
            
        except requests.exceptions.RequestException as e:
            self.logger.error(f"Failed to get members for group {group_jid}: {e}")
            return []
    
    def remove_group_participant(self, group_jid: str, participant_jid: str) -> RemovalResult:
        """Remove a single participant from a group"""
        
        # Check whitelist first
        if self.is_whitelisted(participant_jid):
            self.logger.info(f"🔒 Skipping whitelisted contact: {participant_jid}")
            return RemovalResult(
                jid=participant_jid,
                group_jid=group_jid,
                success=False,
                message="Skipped - contact is whitelisted",
                skipped=True,
                skip_reason="whitelisted"
            )
        
        try:
            url = f"{self.bridge_url}/api/group/{group_jid}/participants/remove"
            payload = {
                "participants": [participant_jid],
                "action": "remove"
            }
            
            response = self.session.post(url, json=payload)
            
            if response.status_code == 200:
                self.logger.info(f"✓ Successfully removed {participant_jid} from {group_jid}")
                return RemovalResult(
                    jid=participant_jid,
                    group_jid=group_jid,
                    success=True,
                    message="Successfully removed from group"
                )
            else:
                error_msg = f"HTTP {response.status_code}: {response.text}"
                self.logger.error(f"✗ Failed to remove {participant_jid} from {group_jid}: {error_msg}")
                return RemovalResult(
                    jid=participant_jid,
                    group_jid=group_jid,
                    success=False,
                    message=error_msg,
                    error_code=str(response.status_code)
                )
                
        except requests.exceptions.RequestException as e:
            error_msg = f"Request failed: {str(e)}"
            self.logger.error(f"✗ Failed to remove {participant_jid} from {group_jid}: {error_msg}")
            return RemovalResult(
                jid=participant_jid,
                group_jid=group_jid,
                success=False,
                message=error_msg
            )
    
    def bulk_remove_participants(self, group_jid: str, participant_jids: List[str], 
                               delay_seconds: int = 1) -> List[RemovalResult]:
        """Remove multiple participants from a group with rate limiting"""
        results = []
        total = len(participant_jids)
        
        # Count whitelisted contacts
        whitelisted_count = len([jid for jid in participant_jids if self.is_whitelisted(jid)])
        
        self.logger.info(f"Starting bulk removal of {total} participants from group {group_jid}")
        if whitelisted_count > 0:
            self.logger.info(f"🔒 {whitelisted_count} contacts will be skipped (whitelisted)")
        
        for i, participant_jid in enumerate(participant_jids, 1):
            self.logger.info(f"Processing participant {i}/{total}: {participant_jid}")
            
            result = self.remove_group_participant(group_jid, participant_jid)
            results.append(result)
            
            # Only delay if we actually made a removal request (not skipped)
            if not result.skipped and i < total:
                time.sleep(delay_seconds)
        
        # Summary
        successful = len([r for r in results if r.success])
        failed = len([r for r in results if not r.success and not r.skipped])
        skipped = len([r for r in results if r.skipped])
        
        self.logger.info(f"Bulk removal complete: {successful} successful, {failed} failed, {skipped} skipped")
        return results
    
    def remove_common_contacts_from_groups(self, csv_file: str, group1_jid: str, group2_jid: str,
                                         delay_seconds: int = 1) -> Dict[str, List[RemovalResult]]:
        """Remove common contacts (from CSV) from both groups"""
        
        # Read common contacts from CSV
        common_contacts = self.read_common_contacts_csv(csv_file)
        if not common_contacts:
            self.logger.error("No common contacts found in CSV file")
            return {}
        
        self.logger.info(f"Found {len(common_contacts)} common contacts to process")
        
        # Check whitelist impact
        whitelisted_contacts = [c for c in common_contacts if self.is_whitelisted(c['jid'])]
        if whitelisted_contacts:
            self.logger.info(f"🔒 {len(whitelisted_contacts)} contacts are whitelisted and will be skipped:")
            for contact in whitelisted_contacts[:5]:  # Show first 5
                self.logger.info(f"   • {contact['name']} ({contact['jid']})")
            if len(whitelisted_contacts) > 5:
                self.logger.info(f"   • ... and {len(whitelisted_contacts) - 5} more")
        
        results = {}
        
        # Remove from Group 1
        self.logger.info(f"Removing common contacts from Group 1: {group1_jid}")
        results[group1_jid] = self.bulk_remove_participants(
            group1_jid, 
            [contact['jid'] for contact in common_contacts],
            delay_seconds
        )
        
        # Wait between groups
        time.sleep(delay_seconds * 2)
        
        # Remove from Group 2
        self.logger.info(f"Removing common contacts from Group 2: {group2_jid}")
        results[group2_jid] = self.bulk_remove_participants(
            group2_jid,
            [contact['jid'] for contact in common_contacts],
            delay_seconds
        )
        
        return results
    
    def read_common_contacts_csv(self, csv_file: str) -> List[Dict[str, str]]:
        """Read the common contacts CSV file generated by the comparison script"""
        contacts = []
        
        try:
            with open(csv_file, 'r', newline='', encoding='utf-8') as file:
                reader = csv.DictReader(file)
                for row in reader:
                    if row.get('jid'):  # Only include rows with valid JID
                        contacts.append({
                            'name': row.get('name', ''),
                            'jid': row.get('jid', ''),
                            'source': row.get('source', ''),
                            'is_admin': row.get('is_admin', 'False').lower() == 'true',
                            'is_super_admin': row.get('is_super_admin', 'False').lower() == 'true'
                        })
        
        except FileNotFoundError:
            self.logger.error(f"CSV file not found: {csv_file}")
        except Exception as e:
            self.logger.error(f"Error reading CSV file: {e}")
        
        return contacts
    
    def load_whitelist_from_file(self, whitelist_file: str) -> Set[str]:
        """Load whitelist JIDs from a text file (one JID per line)"""
        whitelist = set()
        
        try:
            with open(whitelist_file, 'r', encoding='utf-8') as file:
                for line in file:
                    jid = line.strip()
                    if jid and not jid.startswith('#'):  # Skip empty lines and comments
                        whitelist.add(jid)
            
            self.logger.info(f"Loaded {len(whitelist)} JIDs from whitelist file: {whitelist_file}")
            
        except FileNotFoundError:
            self.logger.warning(f"Whitelist file not found: {whitelist_file}")
        except Exception as e:
            self.logger.error(f"Error reading whitelist file: {e}")
        
        return whitelist
    
    def save_removal_results(self, results: Dict[str, List[RemovalResult]], output_file: str):
        """Save removal results to a CSV file"""
        try:
            with open(output_file, 'w', newline='', encoding='utf-8') as file:
                fieldnames = ['group_jid', 'participant_jid', 'success', 'skipped', 'skip_reason', 'message', 'error_code', 'timestamp']
                writer = csv.DictWriter(file, fieldnames=fieldnames)
                writer.writeheader()
                
                timestamp = time.strftime('%Y-%m-%d %H:%M:%S')
                
                for group_jid, group_results in results.items():
                    for result in group_results:
                        writer.writerow({
                            'group_jid': result.group_jid,
                            'participant_jid': result.jid,
                            'success': result.success,
                            'skipped': result.skipped,
                            'skip_reason': result.skip_reason or '',
                            'message': result.message,
                            'error_code': result.error_code or '',
                            'timestamp': timestamp
                        })
            
            self.logger.info(f"Removal results saved to: {output_file}")
        
        except Exception as e:
            self.logger.error(f"Failed to save results: {e}")





def main():
    parser = argparse.ArgumentParser(description='WhatsApp Group Management Tool')
    parser.add_argument('--csv-file', default='common_contacts_full.csv', 
                       help='CSV file with contacts to remove')
    parser.add_argument('--group1', default='120363315467665376@g.us',
                       help='First group JID')
    parser.add_argument('--group2', default='120363385526179109@g.us', 
                       help='Second group JID')
    parser.add_argument('--delay', type=int, default=2,
                       help='Delay between removals in seconds')
    parser.add_argument('--bridge-url', default='http://localhost:8080',
                       help='WhatsApp bridge URL')
    parser.add_argument('--dry-run', action='store_true',
                       help='Show what would be removed without actually removing')
    parser.add_argument('--output', default='removal_results.csv',
                       help='Output file for removal results')
    parser.add_argument('--whitelist', type=str,
                       help='File containing JIDs to whitelist (one per line)')
    parser.add_argument('--whitelist-jids', type=str, nargs='*',
                       help='Individual JIDs to whitelist (space separated)')
    
    args = parser.parse_args()
    
    print("=" * 80)
    print("🤖 WhatsApp Group Management Tool")
    print("=" * 80)
    
    # Build whitelist
    whitelist = set()
    
    # Load from file
    if args.whitelist:
        manager_temp = GroupManager()  # Temporary instance for loading
        whitelist.update(manager_temp.load_whitelist_from_file(args.whitelist))
    
    # Add individual JIDs
    if args.whitelist_jids:
        whitelist.update(args.whitelist_jids)
        print(f"Added {len(args.whitelist_jids)} JIDs from command line to whitelist")
    
    if whitelist:
        print(f"\n🔒 Whitelist Configuration:")
        print(f"   Protected contacts: {len(whitelist)}")
        print("   Sample whitelisted JIDs:")
        for jid in list(whitelist)[:3]:
            print(f"     • {jid}")
        if len(whitelist) > 3:
            print(f"     • ... and {len(whitelist) - 3} more")
    
    # Initialize group manager with whitelist
    manager = GroupManager(args.bridge_url, whitelist)
    
    if args.dry_run:
        print(f"\n🔍 DRY RUN MODE - Analyzing what would be removed...")
        
        # Read contacts that would be processed
        contacts = manager.read_common_contacts_csv(args.csv_file)
        print(f"\nFound {len(contacts)} contacts in CSV file:")
        
        # Categorize contacts
        to_remove = [c for c in contacts if not manager.is_whitelisted(c['jid'])]
        to_skip = [c for c in contacts if manager.is_whitelisted(c['jid'])]
        
        print(f"\n📋 Contacts that WOULD BE REMOVED ({len(to_remove)}):")
        for i, contact in enumerate(to_remove[:10], 1):
            admin_status = " [ADMIN]" if contact.get('is_admin') or contact.get('is_super_admin') else ""
            print(f"  {i}. {contact['name']}{admin_status} - {contact['jid']}")
        if len(to_remove) > 10:
            print(f"  ... and {len(to_remove) - 10} more")
        
        if to_skip:
            print(f"\n🔒 Contacts that WOULD BE SKIPPED ({len(to_skip)}):")
            for i, contact in enumerate(to_skip[:5], 1):
                admin_status = " [ADMIN]" if contact.get('is_admin') or contact.get('is_super_admin') else ""
                print(f"  {i}. {contact['name']}{admin_status} - {contact['jid']} (whitelisted)")
            if len(to_skip) > 5:
                print(f"  ... and {len(to_skip) - 5} more")
        
        print(f"\nThese changes would be applied to:")
        print(f"  - Group 1: {args.group1}")
        print(f"  - Group 2: {args.group2}")
        
        print(f"\nTo proceed with actual removal, run without --dry-run flag")
        return
    
    # Confirm the operation
    contacts = manager.read_common_contacts_csv(args.csv_file)
    to_remove = [c for c in contacts if not manager.is_whitelisted(c['jid'])]
    to_skip = [c for c in contacts if manager.is_whitelisted(c['jid'])]
    
    print(f"\n⚠️  WARNING: This will remove {len(to_remove)} contacts from both groups!")
    if to_skip:
        print(f"🔒 {len(to_skip)} contacts will be skipped (whitelisted)")
    print(f"CSV file: {args.csv_file}")
    print(f"Group 1: {args.group1}")
    print(f"Group 2: {args.group2}")
    print(f"Delay: {args.delay} seconds between removals")
    
    confirm = input("\nDo you want to proceed? Type 'REMOVE' to confirm: ")
    if confirm != 'REMOVE':
        print("Operation cancelled.")
        return
    
    # Execute the removal
    print(f"\n🚀 Starting group contact removal process...")
    
    results = manager.remove_common_contacts_from_groups(
        args.csv_file,
        args.group1, 
        args.group2,
        args.delay
    )
    
    # Save results
    manager.save_removal_results(results, args.output)
    
    # Print final summary
    total_successful = 0
    total_failed = 0
    total_skipped = 0
    
    for group_results in results.values():
        total_successful += len([r for r in group_results if r.success])
        total_failed += len([r for r in group_results if not r.success and not r.skipped])
        total_skipped += len([r for r in group_results if r.skipped])
    
    print(f"\n✅ Operation Complete!")
    print(f"📊 Final Summary:")
    print(f"   ✓ Successfully removed: {total_successful}")
    print(f"   ✗ Failed to remove: {total_failed}")
    print(f"   🔒 Skipped (whitelisted): {total_skipped}")
    print(f"Results saved to: {args.output}")
    print(f"Check the log file for detailed information: group_management.log")


if __name__ == "__main__":
    main() 