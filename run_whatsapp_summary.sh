#!/bin/bash

# --- Configuration ---
# Set the path to your WhatsApp database
DB_PATH="whatsapp-mcp/whatsapp-bridge/store/messages.db"
# Set the WhatsApp JID to send the summary to (Your number + @s.whatsapp.net)
RECIPIENT_JID="972526060403@s.whatsapp.net"
# Temporary file for intermediate results
ENRICHED_JSON_OUTPUT="temp_enriched_links_$(date +%Y%m%d_%H%M%S).json"
# Final Hebrew summary text file
HEBREW_TXT_OUTPUT="hebrew_summary_$(date +%Y%m%d_%H%M%S).txt"
# Delay between AI API calls (in seconds) - passed to both scripts if needed
API_DELAY=1.0
# --- End Configuration ---

echo "========================================================"
echo "=== WhatsApp Link Summary Workflow Starting...       ==="
echo "========================================================"
echo "DB Path: $DB_PATH"
echo "Recipient: $RECIPIENT_JID"
echo "--------------------------------------------------------"
echo ""

echo "--- Running Phase 1 & 2: Link Extraction and Analysis ---"
# Run the first script (interactive prompts for groups/dates happen here)
python get_links_cli.py \
  --db-path "$DB_PATH" \
  --output "$ENRICHED_JSON_OUTPUT" \
  --delay "$API_DELAY"

# Check if the first script succeeded and created the output file
if [ $? -ne 0 ] || [ ! -f "$ENRICHED_JSON_OUTPUT" ]; then
    echo ""
    echo "Error: Script 'get_links_cli.py' failed or did not produce the expected output file ($ENRICHED_JSON_OUTPUT)."
    echo "Workflow aborted."
    exit 1
fi
echo "--- Phase 1 & 2 Complete. Enriched data saved to: $ENRICHED_JSON_OUTPUT ---"
echo ""
echo "--------------------------------------------------------"
echo ""

echo "--- Running Phase 3: Hebrew Summary Generation & Sending ---"
# Run the second script (includes translation and sending)
python generate_hebrew_summary.py \
  --input-json "$ENRICHED_JSON_OUTPUT" \
  --output "$HEBREW_TXT_OUTPUT" \
  --recipient "$RECIPIENT_JID" \
  --delay "$API_DELAY"

if [ $? -ne 0 ]; then
     echo ""
     echo "Error: Script 'generate_hebrew_summary.py' reported an error."
     # You might still have the text file generated even if sending failed
     echo "Please check the output above and the file: $HEBREW_TXT_OUTPUT"
     # Optionally delete the temp json file even on error
     # rm -f "$ENRICHED_JSON_OUTPUT"
     exit 1
fi
echo "--- Phase 3 Complete. Hebrew summary saved to: $HEBREW_TXT_OUTPUT ---"
echo ""
echo "--------------------------------------------------------"

# Optional: Clean up the temporary intermediate JSON file
echo "Cleaning up temporary file: $ENRICHED_JSON_OUTPUT"
rm -f "$ENRICHED_JSON_OUTPUT"

echo ""
echo "========================================================"
echo "=== Workflow Finished Successfully!                  ==="
echo "========================================================"

exit 0
