# Multi-stage build for WhatsApp Link Forwarder
FROM golang:1.23-alpine AS go-builder

# Install build dependencies
RUN apk add --no-cache gcc musl-dev sqlite-dev

# Set working directory for Go build
WORKDIR /build

# Copy Go modules files
COPY whatsapp-mcp/whatsapp-bridge/go.mod whatsapp-mcp/whatsapp-bridge/go.sum ./

# Download Go dependencies
RUN go mod download

# Copy Go source code
COPY whatsapp-mcp/whatsapp-bridge/main.go ./

# Build the Go binary
RUN CGO_ENABLED=1 GOOS=linux go build -a -ldflags '-linkmode external -extldflags "-static"' -o whatsapp-bridge .

# Final stage - Python runtime with Go binary
FROM python:3.11-slim

# Install system dependencies
RUN apt-get update && apt-get install -y \
    sqlite3 \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Set working directory
WORKDIR /app

# Copy Go binary from builder stage
COPY --from=go-builder /build/whatsapp-bridge /app/

# Copy Python scripts
COPY forward_links_preview.py /app/
COPY web_server.py /app/
COPY test_bridge.py /app/
COPY post_deployment.py /app/

# Install Python dependencies (added Flask)
RUN pip install --no-cache-dir \
    requests \
    beautifulsoup4 \
    flask

# Create necessary directories
RUN mkdir -p /app/store /app/persistent

# Copy startup script (legacy, not used anymore)
COPY start.sh /app/
RUN chmod +x /app/start.sh

# Add health check endpoint script (legacy, not used anymore)
COPY health_check.py /app/
RUN chmod +x /app/health_check.py

# Make scripts executable
RUN chmod +x /app/web_server.py /app/test_bridge.py /app/post_deployment.py

# Expose port for web service (Railway will set PORT env var)
EXPOSE 8000

# NO HEALTHCHECK - using Railway's built-in health checks via /health endpoint

# ONLY CMD: Run web server (which handles everything)
CMD ["python3", "/app/web_server.py"] 