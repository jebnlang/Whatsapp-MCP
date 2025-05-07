# Stage 1: Build the Go application
FROM golang:1.24-alpine AS builder
WORKDIR /app

# Install C build tools needed for cgo (for go-sqlite3)
RUN apk add --no-cache build-base gcc musl-dev 

# Copy go.mod and go.sum first to leverage Docker cache
COPY whatsapp-mcp/whatsapp-bridge/go.mod whatsapp-mcp/whatsapp-bridge/go.sum ./
RUN go mod download

# Copy the rest of the Go bridge source code
COPY whatsapp-mcp/whatsapp-bridge/ ./

# Build the Go application
RUN CGO_ENABLED=1 GOOS=linux go build -a -installsuffix cgo -o /whatsapp-bridge main.go

# Stage 2: Setup Python environment and final image ON ALPINE
FROM python:3.10-alpine
WORKDIR /app

# Install system dependencies using apk:
# - tini: for proper signal handling and zombie reaping
# - cronie: cron implementation for Alpine (busybox-cron is also an option)
# - procps: for utilities like ps (often included in busybox on Alpine)
# - sqlite-libs: runtime SQLite libraries for Alpine
# - file: the 'file' utility for debugging
# - bash: for ldd script and general utility
RUN apk add --no-cache musl tini cronie procps sqlite-libs file bash

# Copy the compiled Go executable from the builder stage
COPY --from=builder /whatsapp-bridge ./
RUN ls -la /app  # <--- DEBUG: List contents after copying whatsapp-bridge

# Copy the Python script
COPY forward_links_preview.py ./

# Install Python dependencies
COPY requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt

# Create directory for WhatsApp store (session and messages DB)
# This directory will be mounted as a volume in Railway
RUN mkdir -p /app/store

# Setup cron job for the Python script with cronie
# cronie reads crontabs from /var/spool/cron/crontabs/ or /etc/crontabs/
RUN mkdir -p /var/spool/cron/crontabs
RUN echo "50 23 * * * python /app/forward_links_preview.py >> /var/log/cron.log 2>&1" > /var/spool/cron/crontabs/root
# Ensure root crontab has correct permissions if needed (usually handled by cronie daemon)
# Create log file for cron output
RUN touch /var/log/cron.log

# Copy the entrypoint script and make it executable
COPY entrypoint.sh ./
RUN chmod +x entrypoint.sh
RUN ls -la /app  # <--- DEBUG: List contents after setting up entrypoint.sh

# Expose the Go bridge port (default 8080)
EXPOSE 8080

# Set tini as the entrypoint
ENTRYPOINT ["/usr/sbin/tini", "--"]

# Command to run when the container starts. cronie daemon started by entrypoint.sh
CMD ["/app/entrypoint.sh"] 