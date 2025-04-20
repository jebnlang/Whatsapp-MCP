# WhatsApp MCP Tools

This repository contains scripts to interact with your WhatsApp messages using the WhatsApp MCP (Model Context Protocol) server.

## Prerequisites

- Make sure the WhatsApp bridge is running:
  ```
  cd whatsapp-mcp/whatsapp-bridge && go run main.go
  ```

- Python 3.6+ with the requests library installed

## Available Tools

### 1. Send Message (`send_message.py`)

Send WhatsApp messages to contacts directly from the command line.

**Usage:**
```python
python3 send_message.py
```

This script sends a predefined message to a specific contact (currently set to "Hamster"). You can modify the script to change the recipient and message.

### 2. Interactive Link Extractor (`get_links.py`)

Extract links shared in WhatsApp group chats using an interactive interface.

**Usage:**
```python
python3 get_links.py
```

This script will:
1. List all available groups
2. Ask you to select a group
3. Ask for start and end dates (optional)
4. Extract all links shared in the group within the specified date range
5. Save the links to a text file

### 3. Command-Line Link Extractor (`get_links_cli.py`)

A more flexible command-line version for extracting links from WhatsApp group chats.

**Usage:**
```python
python3 get_links_cli.py [OPTIONS]
```

**Options:**
- `--list-groups`: List all available groups
- `--group-name NAME`: Search for a group by name (partial match)
- `--group-jid JID`: Specify the group JID directly
- `--start-date DATE`: Start date in YYYY-MM-DD format
- `--end-date DATE`: End date in YYYY-MM-DD format
- `--output FILE`: Output file name
- `--format FORMAT`: Output format (text or json, default: text)

**Examples:**

List all available groups:
```python
python3 get_links_cli.py --list-groups
```

Extract links from a specific group:
```python
python3 get_links_cli.py --group-name "BSG - General"
```

Extract links within a date range:
```python
python3 get_links_cli.py --group-name "BSG - General" --start-date 2025-04-01 --end-date 2025-04-30
```

Extract links and save as JSON:
```python
python3 get_links_cli.py --group-name "BSG - General" --format json
```

## Output Examples

Links are extracted with their context:
- URL
- Date and time
- Sender (phone number or JID)
- Full message containing the link

## Tips

1. Use `--list-groups` to find the exact name of your groups
2. If multiple groups match your search term, the script will list them
3. Date ranges are inclusive
4. For the most recent messages, leave the end date empty

## Troubleshooting

If you encounter any issues:

1. Ensure the WhatsApp bridge is running
2. Check that the SQLite database path is correct in the script
3. Make sure the dates are in the correct format (YYYY-MM-DD)
4. For permissions errors, ensure you have read access to the database files 