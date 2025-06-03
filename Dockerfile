# Multi-stage build for WhatsApp Link Forwarder
FROM golang:1.21-alpine AS go-builder

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

# Copy Python script (only the link forwarding script)
COPY forward_links_preview.py /app/

# Install Python dependencies (removed OpenAI)
RUN pip install --no-cache-dir \
    requests \
    beautifulsoup4

# Create necessary directories
RUN mkdir -p /app/store /app/persistent

# Copy startup script
COPY start.sh /app/
RUN chmod +x /app/start.sh

# Add health check endpoint script
COPY health_check.py /app/
RUN chmod +x /app/health_check.py

# Expose port for WhatsApp bridge API
EXPOSE 8080

# Health check
HEALTHCHECK --interval=30s --timeout=10s --start-period=60s --retries=3 \
    CMD python /app/health_check.py || exit 1

# Run startup script
CMD ["sh", "/app/start.sh"] 