# WhatsApp Forward Links Preview

This project contains the essential files to run the WhatsApp forward links preview functionality.

## Core Components

1. **forward_links_preview.py** - Main Python script that scans WhatsApp groups for links, fetches preview metadata, and forwards them with images
2. **whatsapp-bridge/** - Go-based WhatsApp API bridge that handles message sending
3. **Docker deployment** - Complete containerized setup for production deployment

## Prerequisites

- Python 3.8+
- Go 1.19+
- Docker (for deployment)
- WhatsApp account for authentication

## Quick Start

### Local Development

1. Install Python dependencies:
```bash
pip install -r requirements.txt
```

2. Start the WhatsApp bridge:
```bash
cd whatsapp-mcp/whatsapp-bridge
go run main.go
```

3. Run the forward preview script:
```bash
python forward_links_preview.py --db-path /path/to/messages.db
```

### Docker Deployment

```bash
docker build -t whatsapp-forward .
docker run -p 8080:8080 whatsapp-forward
```

## Environment Variables for Non-Interactive Mode

- `WHATSAPP_FORWARD_RECIPIENT` - Destination group/contact
- `WHATSAPP_SOURCE_GROUPS` - Comma-separated source group names

## Files Structure

```
├── forward_links_preview.py      # Main Python script
├── requirements.txt              # Python dependencies
├── Dockerfile                    # Docker build configuration
├── start.sh                      # Startup script for deployment
├── health_check.py               # Health monitoring
├── whatsapp-mcp/
│   └── whatsapp-bridge/
│       ├── main.go               # Go WhatsApp bridge
│       ├── go.mod                # Go dependencies
│       ├── go.sum                # Go dependency checksums
│       ├── whatsapp_session.b64  # Session backup
│       └── store/                # WhatsApp databases
└── deployment files...           # Railway/Docker deployment
``` 