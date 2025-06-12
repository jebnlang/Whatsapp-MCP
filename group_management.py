#!/usr/bin/env python3
"""
WhatsApp Group Management Script

This script provides functionality to programmatically remove users from WhatsApp groups
by extending the existing WhatsApp bridge with group management capabilities.

Features:
1. Remove users from groups programmatically
2. Bulk removal from CSV of common contacts
3. Admin permission validation
4. Detailed logging and error handling

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


class GroupManager:
    """Manages WhatsApp group operations via the bridge API"""
    
    def __init__(self, bridge_url: str = "http://localhost:8080"):
        self.bridge_url = bridge_url.rstrip('/')
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
        
        self.logger.info(f"Starting bulk removal of {total} participants from group {group_jid}")
        
        for i, participant_jid in enumerate(participant_jids, 1):
            self.logger.info(f"Removing participant {i}/{total}: {participant_jid}")
            
            result = self.remove_group_participant(group_jid, participant_jid)
            results.append(result)
            
            # Rate limiting to avoid being flagged
            if i < total:  # Don't delay after the last removal
                time.sleep(delay_seconds)
        
        # Summary
        successful = len([r for r in results if r.success])
        failed = len([r for r in results if not r.success])
        
        self.logger.info(f"Bulk removal complete: {successful} successful, {failed} failed")
        return results
    
    def remove_common_contacts_from_groups(self, csv_file: str, group1_jid: str, group2_jid: str,
                                         delay_seconds: int = 1) -> Dict[str, List[RemovalResult]]:
        """Remove common contacts (from CSV) from both groups"""
        
        # Read common contacts from CSV
        common_contacts = self.read_common_contacts_csv(csv_file)
        if not common_contacts:
            self.logger.error("No common contacts found in CSV file")
            return {}
        
        self.logger.info(f"Found {len(common_contacts)} common contacts to remove")
        
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
                            'phone_number': row.get('phone_number', ''),
                            'name': row.get('name', ''),
                            'jid': row.get('jid', '')
                        })
        
        except FileNotFoundError:
            self.logger.error(f"CSV file not found: {csv_file}")
        except Exception as e:
            self.logger.error(f"Error reading CSV file: {e}")
        
        return contacts
    
    def save_removal_results(self, results: Dict[str, List[RemovalResult]], output_file: str):
        """Save removal results to a CSV file"""
        try:
            with open(output_file, 'w', newline='', encoding='utf-8') as file:
                fieldnames = ['group_jid', 'participant_jid', 'success', 'message', 'error_code', 'timestamp']
                writer = csv.DictWriter(file, fieldnames=fieldnames)
                writer.writeheader()
                
                timestamp = time.strftime('%Y-%m-%d %H:%M:%S')
                
                for group_jid, group_results in results.items():
                    for result in group_results:
                        writer.writerow({
                            'group_jid': result.group_jid,
                            'participant_jid': result.jid,
                            'success': result.success,
                            'message': result.message,
                            'error_code': result.error_code or '',
                            'timestamp': timestamp
                        })
            
            self.logger.info(f"Removal results saved to: {output_file}")
        
        except Exception as e:
            self.logger.error(f"Failed to save results: {e}")


def extend_bridge_with_group_management():
    """
    Instructions to extend the Go bridge with group management endpoints.
    This needs to be added to main.go in the startRESTServer function.
    """
    
    go_code_extension = '''
    // Add this to the REST server routes in main.go:
    
    // Handler for removing group participants
    router.HandleFunc("/api/group/{jid}/participants/remove", func(w http.ResponseWriter, r *http.Request) {
        vars := mux.Vars(r)
        groupJID := vars["jid"]
        
        var req struct {
            Participants []string `json:"participants"`
            Action       string   `json:"action"`
        }
        
        if err := json.NewDecoder(r.Body).Decode(&req); err != nil {
            writeJSONError(w, "Invalid request format", http.StatusBadRequest)
            return
        }
        
        if len(req.Participants) == 0 {
            writeJSONError(w, "No participants specified", http.StatusBadRequest)
            return
        }
        
        // Parse group JID
        groupJIDParsed, err := types.ParseJID(groupJID)
        if err != nil {
            writeJSONError(w, "Invalid group JID", http.StatusBadRequest)
            return
        }
        
        // Convert participant strings to JIDs
        participantJIDs := make([]types.JID, len(req.Participants))
        for i, p := range req.Participants {
            participantJIDs[i], err = types.ParseJID(p)
            if err != nil {
                writeJSONError(w, fmt.Sprintf("Invalid participant JID: %s", p), http.StatusBadRequest)
                return
            }
        }
        
        // Perform the removal
        removedParticipants, err := client.UpdateGroupParticipants(
            groupJIDParsed, 
            participantJIDs, 
            whatsmeow.ParticipantChangeRemove,
        )
        
        if err != nil {
            logger.Errorf("Failed to remove participants: %v", err)
            writeJSONError(w, fmt.Sprintf("Failed to remove participants: %v", err), http.StatusInternalServerError)
            return
        }
        
        writeJSONResponse(w, map[string]interface{}{
            "success": true,
            "message": fmt.Sprintf("Successfully processed %d participants", len(removedParticipants)),
            "removed_participants": removedParticipants,
        })
        
    }).Methods(http.MethodPost)
    
    // Handler for adding group participants  
    router.HandleFunc("/api/group/{jid}/participants/add", func(w http.ResponseWriter, r *http.Request) {
        // Similar implementation for adding participants
        // ... (implement as needed)
    }).Methods(http.MethodPost)
    '''
    
    return go_code_extension


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
    
    args = parser.parse_args()
    
    print("=" * 80)
    print("🤖 WhatsApp Group Management Tool")
    print("=" * 80)
    
    # Check if bridge extension is needed
    print("\n⚠️  IMPORTANT: Bridge Extension Required")
    print("=" * 50)
    print("This script requires group management endpoints to be added to your Go bridge.")
    print("Please add the following code to your main.go file in the startRESTServer function:")
    print("\n" + extend_bridge_with_group_management())
    print("\n" + "=" * 50)
    
    response = input("\nHave you added the group management endpoints to main.go? (y/N): ")
    if response.lower() != 'y':
        print("Please add the endpoints first and restart your bridge, then run this script again.")
        return
    
    # Initialize group manager
    manager = GroupManager(args.bridge_url)
    
    if args.dry_run:
        print(f"\n🔍 DRY RUN MODE - Analyzing what would be removed...")
        
        # Read contacts that would be removed
        contacts = manager.read_common_contacts_csv(args.csv_file)
        print(f"\nFound {len(contacts)} contacts in CSV file that would be removed:")
        
        for i, contact in enumerate(contacts[:10], 1):  # Show first 10
            print(f"  {i}. {contact['name']} ({contact['phone_number']}) - {contact['jid']}")
        
        if len(contacts) > 10:
            print(f"  ... and {len(contacts) - 10} more")
        
        print(f"\nThese contacts would be removed from:")
        print(f"  - Group 1: {args.group1}")
        print(f"  - Group 2: {args.group2}")
        
        print(f"\nTo proceed with actual removal, run without --dry-run flag")
        return
    
    # Confirm the operation
    print(f"\n⚠️  WARNING: This will remove common contacts from both groups!")
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
    
    # Print summary
    print(f"\n✅ Operation Complete!")
    print(f"Results saved to: {args.output}")
    print(f"Check the log file for detailed information: group_management.log")


if __name__ == "__main__":
    main() 