# WhatsApp Group Management Setup Guide

## Overview

This guide explains how to add programmatic group management capabilities to your WhatsApp bridge, specifically for removing users from groups.

## Step 1: Extend the Go Bridge with Group Management Endpoints

You need to add the group management endpoints to your `whatsapp-mcp/whatsapp-bridge/main.go` file.

### Where to Add the Code

In the `startRESTServer` function, after the existing routes (around line 850), add the following import if not already present:

```go
import (
    "strings"  // Add this if not already imported
    // ... other imports
)
```

Then add these handlers in the `startRESTServer` function after the existing route handlers:

```go
// ============================================================================
// GROUP MANAGEMENT ENDPOINTS
// ============================================================================

// Handler for removing group participants
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
        logger.Warnf("No participants specified for removal")
        writeJSONError(w, "No participants specified", http.StatusBadRequest)
        return
    }
    
    // Parse group JID
    groupJIDParsed, err := types.ParseJID(groupJID)
    if err != nil {
        logger.Errorf("Invalid group JID '%s': %v", groupJID, err)
        writeJSONError(w, "Invalid group JID", http.StatusBadRequest)
        return
    }
    
    if groupJIDParsed.Server != types.GroupServer {
        logger.Warnf("Attempted to modify non-group JID: %s", groupJID)
        writeJSONError(w, "Provided JID is not a group JID", http.StatusBadRequest)
        return
    }
    
    // Convert participant strings to JIDs
    participantJIDs := make([]types.JID, len(req.Participants))
    for i, p := range req.Participants {
        participantJIDs[i], err = types.ParseJID(p)
        if err != nil {
            logger.Errorf("Invalid participant JID '%s': %v", p, err)
            writeJSONError(w, fmt.Sprintf("Invalid participant JID: %s", p), http.StatusBadRequest)
            return
        }
    }
    
    logger.Infof("Attempting to remove %d participants from group %s", len(participantJIDs), groupJID)
    
    // Perform the removal using whatsmeow's UpdateGroupParticipants
    removedParticipants, err := client.UpdateGroupParticipants(
        groupJIDParsed, 
        participantJIDs, 
        whatsmeow.ParticipantChangeRemove,
    )
    
    if err != nil {
        logger.Errorf("Failed to remove participants from group %s: %v", groupJID, err)
        
        // Check for specific error types to provide better error messages
        errorMessage := fmt.Sprintf("Failed to remove participants: %v", err)
        statusCode := http.StatusInternalServerError
        
        // Check if it's a permission error
        if strings.Contains(err.Error(), "not-authorized") || strings.Contains(err.Error(), "forbidden") {
            errorMessage = "Not authorized to remove participants. You must be an admin of the group."
            statusCode = http.StatusForbidden
        } else if strings.Contains(err.Error(), "item-not-found") {
            errorMessage = "Group not found or you're not a member of the group."
            statusCode = http.StatusNotFound
        }
        
        writeJSONError(w, errorMessage, statusCode)
        return
    }
    
    // Build response with detailed information
    response := map[string]interface{}{
        "success": true,
        "message": fmt.Sprintf("Successfully processed %d participants", len(removedParticipants)),
        "group_jid": groupJID,
        "requested_removals": len(req.Participants),
        "successful_removals": len(removedParticipants),
        "removed_participants": make([]map[string]interface{}, 0),
    }
    
    // Add details about each removed participant
    for _, participant := range removedParticipants {
        participantInfo := map[string]interface{}{
            "jid": participant.JID.String(),
            "phone_number": participant.PhoneNumber.String(),
            "was_admin": participant.IsAdmin,
            "was_super_admin": participant.IsSuperAdmin,
        }
        response["removed_participants"] = append(response["removed_participants"].([]map[string]interface{}), participantInfo)
    }
    
    logger.Infof("Successfully removed %d participants from group %s", len(removedParticipants), groupJID)
    writeJSONResponse(w, response)
    
}).Methods(http.MethodPost)

// Handler for adding group participants (bonus functionality)
router.HandleFunc("/api/group/{jid}/participants/add", func(w http.ResponseWriter, r *http.Request) {
    vars := mux.Vars(r)
    groupJID := vars["jid"]
    
    logger.Infof("Received request to add participants to group: %s", groupJID)
    
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
        logger.Warnf("No participants specified for addition")
        writeJSONError(w, "No participants specified", http.StatusBadRequest)
        return
    }
    
    // Parse group JID
    groupJIDParsed, err := types.ParseJID(groupJID)
    if err != nil {
        logger.Errorf("Invalid group JID '%s': %v", groupJID, err)
        writeJSONError(w, "Invalid group JID", http.StatusBadRequest)
        return
    }
    
    if groupJIDParsed.Server != types.GroupServer {
        logger.Warnf("Attempted to modify non-group JID: %s", groupJID)
        writeJSONError(w, "Provided JID is not a group JID", http.StatusBadRequest)
        return
    }
    
    // Convert participant strings to JIDs
    participantJIDs := make([]types.JID, len(req.Participants))
    for i, p := range req.Participants {
        participantJIDs[i], err = types.ParseJID(p)
        if err != nil {
            logger.Errorf("Invalid participant JID '%s': %v", p, err)
            writeJSONError(w, fmt.Sprintf("Invalid participant JID: %s", p), http.StatusBadRequest)
            return
        }
    }
    
    logger.Infof("Attempting to add %d participants to group %s", len(participantJIDs), groupJID)
    
    // Perform the addition using whatsmeow's UpdateGroupParticipants
    addedParticipants, err := client.UpdateGroupParticipants(
        groupJIDParsed, 
        participantJIDs, 
        whatsmeow.ParticipantChangeAdd,
    )
    
    if err != nil {
        logger.Errorf("Failed to add participants to group %s: %v", groupJID, err)
        
        // Check for specific error types
        errorMessage := fmt.Sprintf("Failed to add participants: %v", err)
        statusCode := http.StatusInternalServerError
        
        if strings.Contains(err.Error(), "not-authorized") || strings.Contains(err.Error(), "forbidden") {
            errorMessage = "Not authorized to add participants. You must be an admin of the group."
            statusCode = http.StatusForbidden
        } else if strings.Contains(err.Error(), "item-not-found") {
            errorMessage = "Group not found or you're not a member of the group."
            statusCode = http.StatusNotFound
        }
        
        writeJSONError(w, errorMessage, statusCode)
        return
    }
    
    // Build response
    response := map[string]interface{}{
        "success": true,
        "message": fmt.Sprintf("Successfully processed %d participants", len(addedParticipants)),
        "group_jid": groupJID,
        "requested_additions": len(req.Participants),
        "successful_additions": len(addedParticipants),
        "added_participants": make([]map[string]interface{}, 0),
    }
    
    // Add details about each added participant
    for _, participant := range addedParticipants {
        participantInfo := map[string]interface{}{
            "jid": participant.JID.String(),
            "phone_number": participant.PhoneNumber.String(),
            "error_code": participant.Error,
        }
        response["added_participants"] = append(response["added_participants"].([]map[string]interface{}), participantInfo)
    }
    
    logger.Infof("Successfully added %d participants to group %s", len(addedParticipants), groupJID)
    writeJSONResponse(w, response)
    
}).Methods(http.MethodPost)
```

## Step 2: Restart the WhatsApp Bridge

After adding the code:

1. Stop the current bridge process (Ctrl+C if running in foreground)
2. Rebuild and restart:

```bash
cd whatsapp-mcp/whatsapp-bridge
go run main.go
```

## Step 3: Install Python Dependencies

```bash
pip install requests
```

## Step 4: Run the Group Management Script

### Test Mode (Recommended First):
```bash
python group_management.py --dry-run
```

### Actual Removal:
```bash
python group_management.py
```

### Custom Options:
```bash
python group_management.py \
    --csv-file common_contacts_full.csv \
    --group1 120363315467665376@g.us \
    --group2 120363385526179109@g.us \
    --delay 3 \
    --output my_removal_results.csv
```

## API Endpoints Added

After implementation, you'll have these new endpoints:

### Remove Participants
```bash
curl -X POST http://localhost:8080/api/group/120363315467665376@g.us/participants/remove \
  -H "Content-Type: application/json" \
  -d '{
    "participants": ["1234567890@s.whatsapp.net"],
    "action": "remove"
  }'
```

### Add Participants
```bash
curl -X POST http://localhost:8080/api/group/120363315467665376@g.us/participants/add \
  -H "Content-Type: application/json" \
  -d '{
    "participants": ["1234567890@s.whatsapp.net"],
    "action": "add"
  }'
```

## Important Considerations

### ⚠️ **Requirements & Limitations:**

1. **Admin Status Required**: You must be an admin of the groups to remove/add participants
2. **Rate Limiting**: The script includes delays to avoid being flagged by WhatsApp
3. **Error Handling**: Not all removals may succeed (users might have left, changed numbers, etc.)
4. **Bulk Operations**: The script processes one user at a time for safety

### 🔒 **Security & Ethics:**

1. **Permission-Based**: Only works if you have legitimate admin access
2. **Audit Trail**: All operations are logged and saved to CSV
3. **Confirmation Required**: Script requires explicit confirmation before proceeding
4. **Dry Run Available**: Test mode to see what would happen without making changes

### 📊 **Expected Results:**

Based on your previous analysis:
- **322 common contacts** found between the two groups
- Script will attempt to remove these from both groups
- Expect some failures (users who already left, permission issues, etc.)
- Detailed log and CSV results will show exactly what happened

## Step 5: Monitor Results

The script will create:
- `group_management.log` - Detailed operation log
- `removal_results.csv` - Structured results of all removal attempts

## Troubleshooting

### Common Issues:

1. **"Not authorized" errors**: Ensure you're an admin in both groups
2. **Connection errors**: Ensure the WhatsApp bridge is running on localhost:8080
3. **Rate limiting**: Increase delay between operations if you get temporary blocks
4. **Invalid JIDs**: Check that your CSV file has valid WhatsApp JIDs

### Testing the Setup:

```bash
# Test if bridge is responding
curl http://localhost:8080/api/group/120363315467665376@g.us/members

# Test removal endpoint (should return error about missing participants)
curl -X POST http://localhost:8080/api/group/120363315467665376@g.us/participants/remove \
  -H "Content-Type: application/json" \
  -d '{"participants": [], "action": "remove"}'
```

## Summary

This solution provides:
- ✅ **Programmatic user removal** from WhatsApp groups
- ✅ **Bulk processing** of your common contacts CSV
- ✅ **Safety features** (dry run, confirmations, logging)
- ✅ **Error handling** and detailed reporting
- ✅ **Rate limiting** to avoid WhatsApp restrictions
- ✅ **Complete audit trail** of all operations

The implementation leverages the existing whatsmeow library's `UpdateGroupParticipants` function through a REST API, making it safe and reliable for group management operations. 