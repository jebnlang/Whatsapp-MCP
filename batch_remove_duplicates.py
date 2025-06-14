#!/usr/bin/env python3
"""
Batch Duplicate Removal Script

This script removes duplicate contacts from WhatsApp groups in controlled batches:
- Removes 10 contacts at a time
- 2-second delay between each removal
- Respects whitelist to protect important contacts
- Asks for approval before each batch
- Detailed logging and progress tracking

Usage:
    python batch_remove_duplicates.py
"""

import requests
import json
import csv
import time
import logging
import sys
from typing import List, Dict, Set, Optional
from dataclasses import dataclass


@dataclass
class RemovalResult:
    """Result of a user removal operation"""
    jid: str
    group_jid: str
    success: bool
    message: str
    skipped: bool = False
    skip_reason: Optional[str] = None


class BatchGroupManager:
    """Manages WhatsApp group operations in batches with approval prompts"""
    
    def __init__(self, bridge_url: str = "http://localhost:8080", batch_size: int = 10, delay_seconds: int = 2):
        self.bridge_url = bridge_url.rstrip('/')
        self.batch_size = batch_size
        self.delay_seconds = delay_seconds
        self.whitelist = self.load_whitelist()
        
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
                logging.FileHandler('batch_removal.log'),
                logging.StreamHandler(sys.stdout)
            ]
        )
        self.logger = logging.getLogger(__name__)
        
        if self.whitelist:
            self.logger.info(f"🔒 Whitelist loaded with {len(self.whitelist)} protected JIDs")
    
    def load_whitelist(self) -> Set[str]:
        """Load whitelist JIDs from whitelist.txt file"""
        whitelist = set()
        
        try:
            with open('whitelist.txt', 'r', encoding='utf-8') as f:
                for line in f:
                    line = line.strip()
                    if line and not line.startswith('#'):
                        whitelist.add(line)
            
            print(f"🔒 Loaded whitelist with {len(whitelist)} protected contacts")
            
        except FileNotFoundError:
            print("⚠️  No whitelist.txt found - no contacts will be protected")
        except Exception as e:
            print(f"❌ Error reading whitelist: {e}")
        
        return whitelist
    
    def is_whitelisted(self, jid: str) -> bool:
        """Check if a JID is in the whitelist"""
        return jid in self.whitelist
    
    def load_common_contacts(self, csv_file: str) -> List[Dict[str, str]]:
        """Load common contacts from CSV file"""
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
            
            response = self.session.post(url, json=payload, timeout=15)
            
            if response.status_code == 200:
                self.logger.info(f"✅ Successfully removed {participant_jid} from {group_jid}")
                return RemovalResult(
                    jid=participant_jid,
                    group_jid=group_jid,
                    success=True,
                    message="Successfully removed from group"
                )
            else:
                error_msg = f"HTTP {response.status_code}: {response.text}"
                self.logger.error(f"❌ Failed to remove {participant_jid} from {group_jid}: {error_msg}")
                return RemovalResult(
                    jid=participant_jid,
                    group_jid=group_jid,
                    success=False,
                    message=error_msg
                )
                
        except Exception as e:
            error_msg = f"Request failed: {str(e)}"
            self.logger.error(f"❌ Failed to remove {participant_jid} from {group_jid}: {error_msg}")
            return RemovalResult(
                jid=participant_jid,
                group_jid=group_jid,
                success=False,
                message=error_msg
            )
    
    def remove_batch(self, group_jid: str, contacts_batch: List[Dict], batch_num: int, total_batches: int) -> List[RemovalResult]:
        """Remove a batch of contacts from a group"""
        results = []
        
        print(f"\n🚀 Processing Batch {batch_num}/{total_batches}")
        print(f"   Group: {group_jid}")
        print(f"   Contacts in batch: {len(contacts_batch)}")
        
        for i, contact in enumerate(contacts_batch, 1):
            jid = contact['jid']
            name = contact['name'] or 'Unknown'
            
            print(f"\n   [{i}/{len(contacts_batch)}] Removing: {name} ({jid})")
            
            result = self.remove_group_participant(group_jid, jid)
            results.append(result)
            
            if result.skipped:
                print(f"      🔒 Skipped (whitelisted)")
            elif result.success:
                print(f"      ✅ Removed successfully")
            else:
                print(f"      ❌ Failed: {result.message}")
            
            # Delay between removals (but not if skipped or after last item)
            if not result.skipped and i < len(contacts_batch):
                print(f"      ⏱️  Waiting {self.delay_seconds} seconds...")
                time.sleep(self.delay_seconds)
        
        return results
    
    def process_group_in_batches(self, group_jid: str, contacts: List[Dict]) -> List[RemovalResult]:
        """Process all contacts for a group in batches with approval prompts"""
        
        # Filter out whitelisted contacts for planning
        removable_contacts = [c for c in contacts if not self.is_whitelisted(c['jid'])]
        whitelisted_contacts = [c for c in contacts if self.is_whitelisted(c['jid'])]
        
        print(f"\n📊 Group Processing Plan:")
        print(f"   Total contacts: {len(contacts)}")
        print(f"   Will be removed: {len(removable_contacts)}")
        print(f"   Will be skipped: {len(whitelisted_contacts)} (whitelisted)")
        
        if not removable_contacts:
            print("   ✅ No contacts to remove (all whitelisted)")
            return []
        
        # Split into batches
        batches = []
        for i in range(0, len(removable_contacts), self.batch_size):
            batch = removable_contacts[i:i + self.batch_size]
            batches.append(batch)
        
        print(f"   Batches needed: {len(batches)} (max {self.batch_size} contacts per batch)")
        
        all_results = []
        
        for batch_num, batch in enumerate(batches, 1):
            # Show batch preview
            print(f"\n🔍 Batch {batch_num}/{len(batches)} Preview:")
            for i, contact in enumerate(batch, 1):
                name = contact['name'] or 'Unknown'
                admin_status = " [ADMIN]" if contact.get('is_admin') or contact.get('is_super_admin') else ""
                print(f"   {i}. {name}{admin_status} - {contact['jid']}")
            
            # Ask for approval
            print(f"\n⚠️  Ready to remove {len(batch)} contacts from group")
            print(f"   Group: {group_jid}")
            print(f"   Batch: {batch_num}/{len(batches)}")
            print(f"   Delay: {self.delay_seconds} seconds between removals")
            
            while True:
                response = input(f"\nProceed with batch {batch_num}? (y/n/q): ").lower().strip()
                
                if response == 'y':
                    batch_results = self.remove_batch(group_jid, batch, batch_num, len(batches))
                    all_results.extend(batch_results)
                    
                    # Summary for this batch
                    successful = len([r for r in batch_results if r.success])
                    failed = len([r for r in batch_results if not r.success and not r.skipped])
                    skipped = len([r for r in batch_results if r.skipped])
                    
                    print(f"\n✅ Batch {batch_num} Complete!")
                    print(f"   ✓ Successful: {successful}")
                    print(f"   ✗ Failed: {failed}")
                    print(f"   🔒 Skipped: {skipped}")
                    
                    if batch_num < len(batches):
                        print(f"\n⏸️  Batch complete. Ready for next batch...")
                    
                    break
                    
                elif response == 'n':
                    print(f"⏭️  Skipping batch {batch_num}")
                    # Add skipped results
                    for contact in batch:
                        all_results.append(RemovalResult(
                            jid=contact['jid'],
                            group_jid=group_jid,
                            success=False,
                            message="Skipped by user",
                            skipped=True,
                            skip_reason="user_skip"
                        ))
                    break
                    
                elif response == 'q':
                    print(f"🛑 Operation cancelled by user")
                    return all_results
                    
                else:
                    print("❌ Please enter 'y' (yes), 'n' (skip batch), or 'q' (quit)")
        
        return all_results
    
    def run_batch_removal(self, csv_file: str = "common_contacts_full.csv"):
        """Run the complete batch removal process"""
        
        print("🤖 WhatsApp Duplicate Removal - Batch Mode")
        print("=" * 60)
        
        # Load contacts
        contacts = self.load_common_contacts(csv_file)
        if not contacts:
            print("❌ No contacts found to process")
            return
        
        print(f"\n📋 Loaded {len(contacts)} contacts from {csv_file}")
        
        # Group configuration
        groups = {
            "Group 2 (BSG - General 2)": "120363385526179109@g.us"
        }
        
        print(f"\n🎯 Target Groups:")
        for name, jid in groups.items():
            print(f"   • {name}: {jid}")
        
        print(f"\n⚙️  Batch Configuration:")
        print(f"   • Batch size: {self.batch_size} contacts")
        print(f"   • Delay between removals: {self.delay_seconds} seconds")
        print(f"   • Whitelisted contacts: {len(self.whitelist)}")
        
        # Final confirmation
        print(f"\n⚠️  FINAL WARNING: This will remove duplicate contacts from both groups!")
        confirm = input("Type 'START' to begin batch removal: ")
        
        if confirm != 'START':
            print("❌ Operation cancelled")
            return
        
        # Process each group
        all_results = {}
        
        for group_name, group_jid in groups.items():
            print(f"\n" + "="*60)
            print(f"🎯 Processing {group_name}")
            print(f"   JID: {group_jid}")
            print("="*60)
            
            group_results = self.process_group_in_batches(group_jid, contacts)
            all_results[group_jid] = group_results
            
            print(f"\n✅ Completed processing {group_name}")
        
        # Final summary
        self.print_final_summary(all_results)
    
    def print_final_summary(self, all_results: Dict[str, List[RemovalResult]]):
        """Print final summary of all operations"""
        
        print(f"\n" + "="*60)
        print(f"📊 FINAL SUMMARY")
        print("="*60)
        
        total_successful = 0
        total_failed = 0
        total_skipped = 0
        
        for group_jid, results in all_results.items():
            successful = len([r for r in results if r.success])
            failed = len([r for r in results if not r.success and not r.skipped])
            skipped = len([r for r in results if r.skipped])
            
            total_successful += successful
            total_failed += failed
            total_skipped += skipped
            
            print(f"\nGroup: {group_jid}")
            print(f"   ✓ Successfully removed: {successful}")
            print(f"   ✗ Failed to remove: {failed}")
            print(f"   🔒 Skipped (protected): {skipped}")
        
        print(f"\n🏆 OVERALL TOTALS:")
        print(f"   ✓ Successfully removed: {total_successful}")
        print(f"   ✗ Failed to remove: {total_failed}")
        print(f"   🔒 Skipped (protected): {total_skipped}")
        
        print(f"\n📝 Detailed logs saved to: batch_removal.log")
        print(f"✅ Batch removal operation complete!")


def main():
    """Main function"""
    print("🚀 Starting WhatsApp Batch Duplicate Removal...")
    
    # Initialize manager with your specifications
    manager = BatchGroupManager(
        bridge_url="http://localhost:8080",
        batch_size=10,  # Remove 10 contacts per batch
        delay_seconds=2  # 2 seconds between each removal
    )
    
    # Run the batch removal process
    manager.run_batch_removal("common_contacts_full.csv")


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print(f"\n\n⚠️  Operation interrupted by user")
        sys.exit(1)
    except Exception as e:
        print(f"\n❌ Unexpected error: {e}")
        sys.exit(1) 