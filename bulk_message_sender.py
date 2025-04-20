#!/usr/bin/env python3
import csv
import requests
import time
import argparse
import sys
import os
import json

# Define the Go bridge API base URL and send endpoint
BRIDGE_API_BASE_URL = "http://localhost:8080" # Assuming the Go bridge runs locally on port 8080
SEND_API_ENDPOINT = f"{BRIDGE_API_BASE_URL}/api/send"

# Minimum recommended delay to reduce risk of being blocked
MIN_DELAY_RECOMMENDED = 15 
DEFAULT_DELAY = 30

def send_message_via_bridge(phone_number, message):
    """
    Sends a message to a specific phone number via the Go bridge API.

    Args:
        phone_number (str): The recipient's phone number (digits only).
        message (str): The text message to send.

    Returns:
        tuple: (bool: success, str: status message)
    """
    payload = {
        "recipient": phone_number, # API expects number for individual chat
        "message": message
    }
    headers = {"Content-Type": "application/json"}

    try:
        response = requests.post(SEND_API_ENDPOINT, headers=headers, json=payload, timeout=20)
        response.raise_for_status() # Raises HTTPError for bad responses (4XX or 5XX)
        
        try:
            response_data = response.json()
            if response_data.get("success", False):
                return True, f"Successfully sent to {phone_number}. Bridge response: {response_data.get('message', 'OK')}"
            else:
                 return False, f"Bridge reported failure for {phone_number}: {response_data.get('message', 'Unknown error')}"
        except json.JSONDecodeError:
             return False, f"Failed to decode bridge response for {phone_number}. Status: {response.status_code}, Body: {response.text}"

    except requests.exceptions.ConnectionError:
        return False, f"Connection Error: Could not connect to the Go bridge API at {SEND_API_ENDPOINT}. Is it running?"
    except requests.exceptions.Timeout:
        return False, f"Timeout Error: Request to the Go bridge API timed out for {phone_number}."
    except requests.exceptions.HTTPError as e:
         return False, f"HTTP Error: API request failed for {phone_number} with status {e.response.status_code}. Response: {e.response.text}"
    except Exception as e:
        return False, f"An unexpected error occurred for {phone_number}: {e}"

def main():
    parser = argparse.ArgumentParser(
        description="Send a bulk message to phone numbers listed in a CSV file via the WhatsApp bridge.",
        formatter_class=argparse.RawTextHelpFormatter # To preserve newlines in help text
    )
    parser.add_argument("--csv-file", required=True, help="Path to the CSV file containing phone numbers (one per row, header expected).")
    parser.add_argument("--message-file", required=True, help="Path to a text file containing the message to send (UTF-8 encoded).")
    parser.add_argument(
        "--delay", 
        type=int, 
        default=DEFAULT_DELAY, 
        help=f"Delay in seconds between sending messages (default: {DEFAULT_DELAY}, recommended minimum: {MIN_DELAY_RECOMMENDED})."
    )
    parser.add_argument(
        "--limit", 
        type=int, 
        default=0, # Default 0 means no limit
        help="Optional: Send only to the first N numbers from the CSV file (default: 0, send to all)."
    )
    parser.add_argument(
        "--skip", 
        type=int, 
        default=0, # Default 0 means don't skip any
        help="Optional: Skip the first M numbers from the CSV file before sending (default: 0)."
    )

    print("""
    ***************************************************************************
    ** WARNING: Sending bulk messages via WhatsApp carries a SIGNIFICANT RISK *
    ** of your account being temporarily or permanently BANNED by Meta.       *
    ** Use this script responsibly and at your own risk.                      *
    ** Ensure adequate delays between messages ({MIN_DELAY_RECOMMENDED}+ seconds recommended).    *
    ***************************************************************************
    """)

    args = parser.parse_args()

    csv_file_path = args.csv_file
    message_file_path = args.message_file
    delay_seconds = args.delay
    limit_count = args.limit
    skip_count = args.skip

    if not os.path.exists(csv_file_path):
        print(f"Error: CSV file not found at '{csv_file_path}'")
        sys.exit(1)
        
    if delay_seconds < MIN_DELAY_RECOMMENDED:
         print(f"Warning: Delay is set to {delay_seconds} seconds, which is less than the recommended minimum of {MIN_DELAY_RECOMMENDED}. This increases ban risk.")

    if delay_seconds < 1:
        print("Warning: Delay is less than 1 second. Setting to 1 second.")
        delay_seconds = 1

    phone_numbers = []
    try:
        with open(csv_file_path, 'r', newline='') as f:
            reader = csv.reader(f)
            header = next(reader) # Skip header row
            print(f"Reading numbers from {csv_file_path} (skipped header: {header})")
            for row in reader:
                if row: # Ensure row is not empty
                    number = row[0].strip() # Assume number is in the first column
                    if number.isdigit(): # Basic validation
                         phone_numbers.append(number)
                    else:
                         print(f"Warning: Skipping invalid entry in CSV: {row[0]}")
    except FileNotFoundError:
        print(f"Error: CSV file not found at '{csv_file_path}'")
        sys.exit(1)
    except Exception as e:
        print(f"Error reading CSV file: {e}")
        sys.exit(1)

    if not phone_numbers:
        print("Error: No valid phone numbers found in the CSV file.")
        sys.exit(1)

    total_numbers_in_file = len(phone_numbers)
    print(f"Found {total_numbers_in_file} phone numbers in the CSV file.")

    # Apply skip if specified
    original_indices_skipped = 0
    if skip_count > 0:
        if skip_count < total_numbers_in_file:
            original_indices_skipped = skip_count
            phone_numbers = phone_numbers[skip_count:]
            print(f"Skipping the first {skip_count} numbers.")
        else:
            print(f"Skip count ({skip_count}) is greater than or equal to total numbers ({total_numbers_in_file}). No numbers left to send.")
            phone_numbers = [] # Empty the list
    
    # Apply limit if specified (applied *after* skipping)
    numbers_after_skip = len(phone_numbers)
    if limit_count > 0:
        if limit_count < numbers_after_skip:
            phone_numbers = phone_numbers[:limit_count]
            print(f"Applying limit: Sending to {limit_count} numbers after skipping.")
        # else: Limit is >= remaining numbers, so send to all remaining
            
    # Now total_numbers refers to the actual count we will process
    total_numbers_to_send = len(phone_numbers)
    if total_numbers_to_send == 0:
         print("No numbers to send messages to after applying skip/limit (or file was empty).")
         sys.exit(0)

    # Read message from file
    if not os.path.exists(message_file_path):
        print(f"Error: Message file not found at '{message_file_path}'")
        sys.exit(1)
        
    message_to_send = ""
    try:
        with open(message_file_path, 'r', encoding='utf-8') as f:
            message_to_send = f.read().strip()
        if not message_to_send:
             print(f"Error: Message file '{message_file_path}' is empty.")
             sys.exit(1)
    except Exception as e:
        print(f"Error reading message file '{message_file_path}': {e}")
        sys.exit(1)

    # Display message read from file (ensure terminal supports UTF-8 for emojis)
    print("Message to send (read from file):")
    print("-" * 30)
    print(message_to_send)
    print("-" * 30)
    print(f"Delay between messages: {delay_seconds} seconds")
    print(f"Number of messages to send: {total_numbers_to_send}")
    
    confirm = input("Proceed with sending? (yes/no): ").lower()
    if confirm != 'yes':
        print("Operation cancelled by user.")
        sys.exit(0)

    print("\nStarting bulk send operation...")
    success_count = 0
    failure_count = 0

    for i, number in enumerate(phone_numbers, 1):
        # Calculate the original index for logging/reference if needed
        original_index = i + original_indices_skipped
        print(f"\n[{i}/{total_numbers_to_send}] (Original Index: {original_index}) Sending to {number}...")
        
        success, status_msg = send_message_via_bridge(number, message_to_send)
        
        if success:
            print(f"  Result: SUCCESS - {status_msg}")
            success_count += 1
        else:
            print(f"  Result: FAILED - {status_msg}")
            failure_count += 1
            # Optional: Stop on first critical error (like connection error)
            if "Connection Error" in status_msg:
                 print("Critical connection error. Aborting further sends.")
                 break

        # Wait before sending the next message (unless it's the last one)
        if i < total_numbers_to_send:
            print(f"  Waiting {delay_seconds} seconds...")
            time.sleep(delay_seconds)

    print("\n--- Bulk Send Summary ---")
    print(f"Total attempted: {i}") # Use 'i' in case loop was aborted
    print(f"Successful sends: {success_count}")
    print(f"Failed sends: {failure_count}")
    print("-------------------------")

if __name__ == "__main__":
    main() 