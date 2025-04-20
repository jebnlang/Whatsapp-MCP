import json
import argparse
import os
import time
import openai
import requests # Ensure requests is imported
from datetime import datetime

# --- OpenAI API Setup ---
# WARNING: Hardcoding keys is insecure. Use environment variables in production.
OPENAI_API_KEY = "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"

try:
    client = openai.OpenAI(api_key=OPENAI_API_KEY)
    print("OpenAI client initialized successfully.")
except Exception as e:
    print(f"Error initializing OpenAI client: {e}")
    print("Please ensure the OpenAI library is installed and the API key is valid.")
    client = None

# --- WhatsApp Bridge Setup ---
# Assumes the bridge runs locally on the default port
WHATSAPP_API_BASE_URL = "http://localhost:8080/api"
MAX_WHATSAPP_MESSAGE_LENGTH = 1500 # Approximate safe length

# --- Translation Function ---

def translate_analysis_to_hebrew(purpose_en, type_en, insights_en):
    """Translates English analysis fields to Hebrew, generating an insightful opening sentence."""
    if not client:
        print("OpenAI client not initialized. Skipping translation.")
        # Provide basic Hebrew placeholders on error
        return {"he_opening_sentence": "*שגיאה: לא ניתן לתרגם*", "he_insights": []}

    # Remove type mapping guidance - AI will infer from purpose/type_en
    # type_mapping_guidance = """ ... """

    # Prepare insights list for prompt
    insights_en_str = "\n- ".join(insights_en) if insights_en else "None"

    print(f"  Requesting Hebrew translation and opening sentence for: {purpose_en} (Type: {type_en})...")
    try:
        prompt_messages = [
            {
                "role": "system",
                # Revised prompt: Ask for opening sentence and insights
                "content": "You are an AI assistant translating link analysis details from English to Hebrew. Respond ONLY with a JSON object containing two keys: 'he_opening_sentence' (string: a concise, insightful opening sentence in Hebrew, up to 15 words, incorporating the link's type and purpose) and 'he_insights' (array of strings: Hebrew translation of the key insights). Do not add any explanations."
            },
            {
                "role": "user",
                # Updated user content
                "content": f"Create a Hebrew summary based on the following English analysis:\n\nEnglish Purpose: {purpose_en}\nEnglish Type: {type_en}\nEnglish Insights:\n- {insights_en_str}\n\nPlease provide the result in the specified JSON format (keys: 'he_opening_sentence', 'he_insights')."
            }
        ]

        completion = client.chat.completions.create(
            model="gpt-3.5-turbo",
            messages=prompt_messages,
            response_format={"type": "json_object"}
        )

        ai_response_content = completion.choices[0].message.content
        print("    Hebrew translation/summary received.")

        translation_result = json.loads(ai_response_content)

        # Updated validation
        if not all(k in translation_result for k in ['he_opening_sentence', 'he_insights']):
             print("    Warning: AI translation response missing expected keys.")
             return {"he_opening_sentence": f"*שגיאה: תגובת תרגום שגויה* ({purpose_en})", "he_insights": insights_en} # Return English insights on error

        return translation_result

    # --- Keep existing error handling, adjust return values --- 
    except openai.APIConnectionError as e:
        print(f"    OpenAI Translation Error: Connection error: {e}")
        return {"he_opening_sentence": f"*שגיאת תרגום: {e}*", "he_insights": insights_en}
    except openai.RateLimitError as e:
         print(f"    OpenAI Translation Error: Rate limit exceeded: {e}")
         return {"he_opening_sentence": f"*שגיאת תרגום: {e}*", "he_insights": insights_en}
    except openai.APIStatusError as e:
        print(f"    OpenAI Translation Error: API status error: {e}")
        return {"he_opening_sentence": f"*שגיאת תרגום: {e.status_code}*", "he_insights": insights_en}
    except json.JSONDecodeError:
        print(f"    Error: Failed to decode JSON translation response from AI: {ai_response_content}")
        return {"he_opening_sentence": "*שגיאת תרגום: JSON שגוי*", "he_insights": insights_en }
    except Exception as e:
        print(f"    Unexpected error during OpenAI translation: {e}")
        return {"he_opening_sentence": f"*שגיאת תרגום: {e}*", "he_insights": insights_en}

# --- WhatsApp Sending Function ---

def send_whatsapp_message(recipient_jid, message_text):
    """Sends a message via the WhatsApp bridge API."""
    print(f"\nAttempting to send summary to {recipient_jid} via WhatsApp bridge...")
    
    if len(message_text) > MAX_WHATSAPP_MESSAGE_LENGTH:
        print(f"Warning: Summary length ({len(message_text)} chars) exceeds {MAX_WHATSAPP_MESSAGE_LENGTH}. Message might be truncated or fail.")
        # Consider splitting the message here in a future enhancement if needed
        
    try:
        url = f"{WHATSAPP_API_BASE_URL}/send"
        payload = {
            "recipient": recipient_jid,
            "message": message_text,
        }
        response = requests.post(url, json=payload, timeout=20) # Increased timeout for potentially long messages
        
        if response.status_code == 200:
            try:
                result = response.json()
                if result.get("success", False):
                    print(f"WhatsApp message sent successfully! Response: {result.get('message', '')}")
                    return True
                else:
                    print(f"WhatsApp bridge reported failure: {result.get('message', 'Unknown error')}")
                    return False
            except json.JSONDecodeError:
                print(f"Error: Failed to parse success response from WhatsApp bridge: {response.text}")
                return False
        else:
            print(f"Error sending WhatsApp message: HTTP {response.status_code} - {response.text}")
            return False
            
    except requests.exceptions.Timeout:
        print("Error: Timeout while connecting to WhatsApp bridge API.")
        return False
    except requests.exceptions.RequestException as e:
        print(f"Error connecting to WhatsApp bridge API: {e}")
        return False
    except Exception as e:
        print(f"Unexpected error during WhatsApp send: {e}")
        return False

# --- Main Logic ---

def main():
    parser = argparse.ArgumentParser(description="Generate a Hebrew summary, save to file, and optionally send via WhatsApp.")
    parser.add_argument("--input-json", type=str, required=True, help="Path to the input JSON file (output of Phase 2).")
    parser.add_argument("--output", type=str, help="Optional output TXT file name for the Hebrew summary.")
    parser.add_argument("--delay", type=float, default=1.0, help="Delay in seconds between AI translation calls (default: 1.0).")
    parser.add_argument("--recipient", type=str, help="Optional WhatsApp JID (e.g., 1234567890@s.whatsapp.net) to send the summary to.")
    args = parser.parse_args()

    # 1. Read Input JSON
    try:
        with open(args.input_json, 'r', encoding='utf-8') as f:
            enriched_links = json.load(f)
        print(f"Successfully loaded {len(enriched_links)} links from {args.input_json}")
    except FileNotFoundError:
        print(f"Error: Input file not found at {args.input_json}")
        return
    except json.JSONDecodeError:
        print(f"Error: Could not decode JSON from {args.input_json}")
        return
    except Exception as e:
        print(f"Error reading input file {args.input_json}: {e}")
        return

    if not enriched_links:
        print("Input file contains no links to process.")
        return

    # 2. Process and Translate
    summary_parts = []
    print("\nStarting Hebrew translation and formatting...")
    for i, link_data in enumerate(enriched_links):
        print(f"\nProcessing link {i+1}/{len(enriched_links)}: {link_data.get('link', 'N/A')}")

        # Get English analysis results
        purpose_en = link_data.get('ai_purpose', 'N/A')
        type_en = link_data.get('ai_type', 'Other') # Still useful for the prompt
        insights_en = link_data.get('ai_insights', [])

        # Translate/Summarize
        translation = translate_analysis_to_hebrew(purpose_en, type_en, insights_en)
        # Get the new opening sentence and insights
        he_opening_sentence = translation.get('he_opening_sentence', 'כותרת לא זמינה') 
        he_insights = translation.get('he_insights', [])

        # Get original metadata
        timestamp = link_data.get('timestamp', 'זמן לא ידוע')
        sender = link_data.get('sender', 'שולח לא ידוע')
        group_name = link_data.get('group_name', 'קבוצה לא ידועה')
        link_url = link_data.get('link', 'קישור לא זמין')
        message = link_data.get('message', 'הודעה לא זמינה')

        # Format insights as bullet points
        if he_insights:
            insight_lines = [f"- {insight}" for insight in he_insights]
            insights_formatted_block = '\n'.join(insight_lines)
        else:
            insights_formatted_block = "- אין תובנות זמינות"

        # Revised formatting f-string with bolding and no internal separators
        summary_part = f"""
*{he_opening_sentence}*
*קישור:* {link_url}
*פורסם בתאריך:* {timestamp}
*על ידי:* {sender}
*בקבוצה:* {group_name}
*הודעה מקורית:*
{message}

*תובנות עיקריות:*
{insights_formatted_block}
"""
        # Append the formatted block (strip unnecessary leading/trailing whitespace)
        summary_parts.append(summary_part.strip())

        # Delay
        print(f"Waiting for {args.delay} seconds...")
        time.sleep(args.delay)

    # 3. Aggregate and Save Output
    # Join parts with the new custom separator
    final_summary = "\n🔗🚀------------------🚀 🔗\n".join(summary_parts)

    # Determine output file name
    if args.output:
        output_file = args.output if args.output.lower().endswith('.txt') else args.output + '.txt'
    else:
        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
        output_file = f"hebrew_summary_{timestamp}.txt"

    try:
        with open(output_file, 'w', encoding='utf-8') as f:
            f.write(final_summary)
        print(f"\nHebrew summary saved successfully to {output_file}")
    except Exception as e:
        print(f"\nError saving summary to file {output_file}: {e}")
        # Decide if we should still try to send
        # For now, let's proceed even if file saving failed, but the summary exists

    # 4. Send via WhatsApp (if recipient provided)
    if args.recipient:
        if not args.recipient.endswith("@s.whatsapp.net"):
            print(f"Warning: Recipient JID '{args.recipient}' does not look like a valid JID (should end with @s.whatsapp.net). Attempting anyway.")
        
        send_whatsapp_message(args.recipient, final_summary)
    else:
        print("\n--recipient not provided, skipping WhatsApp send.")

if __name__ == "__main__":
    main()
