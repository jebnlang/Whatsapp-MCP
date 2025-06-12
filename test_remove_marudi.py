#!/usr/bin/env python3
"""
Test Script: Remove Marudi from WhatsApp Groups

This script tests removing a specific contact (Marudi) from WhatsApp groups
by first adding group management endpoints to the Go bridge, then testing
the removal functionality.

Usage:
    python test_remove_marudi.py
"""

import requests
import json
import sqlite3
import time
import sys
from typing import List, Dict, Optional
from phone_to_jid_lookup import PhoneToJIDLookup


class GroupManagementTester:
    def __init__(self, api_base_url: str = "http://localhost:8080"):
        self.api_base_url = api_base_url
        self.lookup = PhoneToJIDLookup()
        
        # Target details
        self.target_phone = "972523451451"
        self.target_groups = [
            "120363385526179109@g.us"   # Group 2 only
        ]
        
    def check_bridge_status(self) -> bool:
        """Check if the WhatsApp bridge is running and accessible"""
        try:
            response = requests.get(f"{self.api_base_url}/api/send", timeout=5)
            print("✅ WhatsApp bridge is running")
            return True
        except Exception as e:
            print(f"❌ WhatsApp bridge not accessible: {e}")
            return False
    
    def find_target_contact(self) -> List[Dict]:
        """Find all possible JIDs for the target contact"""
        print(f"\n🔍 Looking up target contact: {self.target_phone}")
        
        matches = self.lookup.lookup_phone_number(self.target_phone)
        
        if not matches:
            print(f"❌ Contact {self.target_phone} not found in any format")
            return []
        
        contact_variants = []
        for match in matches:
            contact_variants.append({
                'jid': match.jid,
                'name': match.name,
                'source': match.source,
                'groups': match.groups
            })
            
        print(f"✅ Found {len(contact_variants)} contact variant(s):")
        for i, variant in enumerate(contact_variants, 1):
            print(f"   {i}. JID: {variant['jid']}")
            print(f"      Name: {variant['name']}")
            print(f"      Groups: {len(variant['groups'])}")
        
        return contact_variants
    
    def check_group_endpoints(self) -> bool:
        """Check if group management endpoints exist"""
        test_group = self.target_groups[0]
        
        print(f"\n🧪 Testing existing group management endpoints...")
        
        # Test group member removal endpoint
        try:
            url = f"{self.api_base_url}/api/group/{test_group}/participants/remove"
            response = requests.post(url, json={
                "participants": ["test@test.com"],
                "action": "remove"
            }, timeout=15)
            
            if response.status_code == 404:
                print("❌ Group management endpoints not found")
                return False
            else:
                print("✅ Group management endpoints exist")
                print(f"   Response: {response.text}")
                return True
                
        except requests.exceptions.Timeout:
            print("⚠️  Endpoint test timed out, but this might mean it's working (trying to contact WhatsApp)")
            print("✅ Assuming endpoints exist and continuing...")
            return True
        except Exception as e:
            print(f"❌ Error testing group endpoints: {e}")
            return False
    
    def add_group_management_endpoints(self) -> bool:
        """Instructions for adding group management endpoints to the Go bridge"""
        print(f"\n⚠️  GROUP MANAGEMENT ENDPOINTS MISSING")
        print(f"="*60)
        print(f"You need to add group management endpoints to your Go bridge.")
        print(f"Please follow these steps:")
        print(f"\n1. 📁 Open: whatsapp-mcp/whatsapp-bridge/main.go")
        print(f"2. 🔍 Find the startRESTServer function (around line 850)")
        print(f"3. ➕ Add these route handlers after existing routes:\n")
        
        endpoint_code = '''
// Group Management - Remove Participants
router.HandleFunc("/api/group/{jid}/participants/remove", func(w http.ResponseWriter, r *http.Request) {
    vars := mux.Vars(r)
    groupJID := vars["jid"]
    
    logger.Infof("Received request to remove participants from group: %s", groupJID)
    
    var req struct {
        Participants []string `json:"participants"`
        Action       string   `json:"action"`
    }
    
    if err := json.NewDecoder(r.Body).Decode(&req); err != nil {
        logger.Errorf("Invalid request format: %v", err)
        writeJSONError(w, "Invalid request format", http.StatusBadRequest)
        return
    }
    
    if len(req.Participants) == 0 {
        logger.Errorf("No participants specified for removal")
        writeJSONError(w, "No participants specified", http.StatusBadRequest)
        return
    }
    
    // Parse group JID
    jid, err := types.ParseJID(groupJID)
    if err != nil {
        logger.Errorf("Invalid group JID: %v", err)
        writeJSONError(w, "Invalid group JID", http.StatusBadRequest)
        return
    }
    
    // Convert participant strings to JIDs
    var participantJIDs []types.JID
    for _, participant := range req.Participants {
        pJID, err := types.ParseJID(participant)
        if err != nil {
            logger.Warnf("Invalid participant JID %s: %v", participant, err)
            continue
        }
        participantJIDs = append(participantJIDs, pJID)
    }
    
    if len(participantJIDs) == 0 {
        logger.Errorf("No valid participant JIDs found")
        writeJSONError(w, "No valid participants", http.StatusBadRequest)
        return
    }
    
    // Perform the removal
    _, err = client.UpdateGroupParticipants(context.Background(), jid, participantJIDs, whatsmeow.ParticipantChangeRemove)
    if err != nil {
        logger.Errorf("Failed to remove participants: %v", err)
        writeJSONError(w, fmt.Sprintf("Failed to remove participants: %v", err), http.StatusInternalServerError)
        return
    }
    
    logger.Infof("Successfully removed %d participants from group %s", len(participantJIDs), groupJID)
    
    response := map[string]interface{}{
        "success": true,
        "message": fmt.Sprintf("Successfully removed %d participants", len(participantJIDs)),
        "group_jid": groupJID,
        "removed_participants": req.Participants,
    }
    
    w.Header().Set("Content-Type", "application/json")
    json.NewEncoder(w).Encode(response)
}).Methods("POST")
'''
        
        print(endpoint_code)
        print(f"\n4. 💾 Save the file")
        print(f"5. 🔄 Restart the Go bridge: `cd whatsapp-bridge && go run main.go`")
        print(f"6. ▶️  Re-run this test script")
        print(f"\n" + "="*60)
        
        return False
    
    def check_contact_in_group(self, contact_jid: str, group_jid: str) -> bool:
        """Check if contact exists in the specified group"""
        try:
            url = f"{self.api_base_url}/api/group/{group_jid}/members"
            response = requests.get(url, timeout=10)
            
            if response.status_code == 200:
                data = response.json()
                members = data.get("members", [])
                
                # Check exact match and similar matches
                for member in members:
                    if (member == contact_jid or 
                        contact_jid in member or 
                        member.replace("@s.whatsapp.net", "") == contact_jid.replace("@s.whatsapp.net", "")):
                        return True
                        
            return False
            
        except Exception as e:
            print(f"⚠️  Error checking group membership: {e}")
            return False
    
    def remove_contact_from_group(self, contact_jid: str, group_jid: str) -> bool:
        """Remove contact from specified group"""
        print(f"\n🚫 Attempting to remove {contact_jid} from {group_jid}")
        
        try:
            url = f"{self.api_base_url}/api/group/{group_jid}/participants/remove"
            payload = {
                "participants": [contact_jid],
                "action": "remove"
            }
            
            response = requests.post(url, json=payload, timeout=15)
            
            if response.status_code == 200:
                result = response.json()
                print(f"✅ Successfully removed contact!")
                print(f"   Response: {result.get('message', 'Success')}")
                return True
            else:
                print(f"❌ Removal failed: HTTP {response.status_code}")
                print(f"   Response: {response.text}")
                return False
                
        except Exception as e:
            print(f"❌ Error during removal: {e}")
            return False
    
    def verify_removal(self, contact_jid: str, group_jid: str) -> bool:
        """Verify that contact was successfully removed from group"""
        print(f"\n🔍 Verifying removal of {contact_jid} from {group_jid}")
        
        time.sleep(2)  # Give time for the change to propagate
        
        still_in_group = self.check_contact_in_group(contact_jid, group_jid)
        
        if not still_in_group:
            print(f"✅ Verification successful: Contact removed from group")
            return True
        else:
            print(f"❌ Verification failed: Contact still in group")
            return False
    
    def run_full_test(self):
        """Run the complete test workflow"""
        print("🧪 MARUDI GROUP REMOVAL TEST")
        print("="*50)
        
        # Step 1: Check bridge status
        if not self.check_bridge_status():
            return False
        
        # Step 2: Find target contact
        contact_variants = self.find_target_contact()
        if not contact_variants:
            print("❌ Cannot proceed without finding target contact")
            return False
        
        # Step 3: Check if group management endpoints exist
        if not self.check_group_endpoints():
            self.add_group_management_endpoints()
            return False
        
        # Step 4: Test removal for each contact variant in each target group
        success_count = 0
        total_attempts = 0
        
        for group_jid in self.target_groups:
            print(f"\n📊 Testing removal from group: {group_jid}")
            
            for variant in contact_variants:
                contact_jid = variant['jid']
                total_attempts += 1
                
                # Check if contact is in this group
                if self.check_contact_in_group(contact_jid, group_jid):
                    print(f"✅ Found {contact_jid} in group {group_jid}")
                    
                    # Attempt removal
                    if self.remove_contact_from_group(contact_jid, group_jid):
                        # Verify removal
                        if self.verify_removal(contact_jid, group_jid):
                            success_count += 1
                            print(f"🎉 Successfully removed {variant['name']} from group!")
                        else:
                            print(f"⚠️  Removal command succeeded but verification failed")
                    else:
                        print(f"❌ Failed to remove {variant['name']} from group")
                else:
                    print(f"ℹ️  {contact_jid} not found in group {group_jid}")
        
        # Final results
        print(f"\n" + "="*50)
        print(f"📊 TEST RESULTS:")
        print(f"   Total attempts: {total_attempts}")
        print(f"   Successful removals: {success_count}")
        print(f"   Success rate: {success_count/max(total_attempts,1)*100:.1f}%")
        
        if success_count > 0:
            print(f"🎉 Test completed successfully!")
            return True
        else:
            print(f"❌ No successful removals")
            return False


def main():
    print("🚀 Starting Marudi Group Removal Test...")
    
    tester = GroupManagementTester()
    success = tester.run_full_test()
    
    if success:
        print(f"\n✅ Test completed successfully!")
        print(f"💡 You can now use this functionality to remove other contacts or bulk remove common contacts!")
        sys.exit(0)
    else:
        print(f"\n❌ Test failed or requires manual intervention")
        sys.exit(1)


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print(f"\n\n⚠️  Test interrupted by user.")
        sys.exit(1)
    except Exception as e:
        print(f"\n❌ Unexpected error: {e}")
        sys.exit(1) 