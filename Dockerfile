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

# Stage 2: Setup Python environment and final image
FROM python:3.10-slim
WORKDIR /app

# Install system dependencies:
# - cron: for scheduling the Python script
# - tini: a lightweight init system to properly manage processes (like our Go bridge)
# - procps: provides `ps` and other utilities, good for debugging
# - libsqlite3-0: runtime library for SQLite
RUN apt-get update && \
    apt-get install -y --no-install-recommends cron tini procps libsqlite3-0 && \
    rm -rf /var/lib/apt/lists/*

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

# Setup cron job for the Python script
# Create a crontab file that runs the script at 11:50 PM server time daily
# Output and errors from the cron job will be logged to /var/log/cron.log
RUN echo "50 23 * * * python /app/forward_links_preview.py >> /var/log/cron.log 2>&1" > /etc/cron.d/whatsapp-forwarder
# Give execution rights on the cron job file
RUN chmod 0644 /etc/cron.d/whatsapp-forwarder
# Create log file for cron output
RUN touch /var/log/cron.log

# Copy the entrypoint script and make it executable
COPY entrypoint.sh ./
RUN chmod +x entrypoint.sh
RUN ls -la /app  # <--- DEBUG: List contents after setting up entrypoint.sh

# Expose the Go bridge port (default 8080)
EXPOSE 8080

# Set tini as the entrypoint, which will manage our entrypoint.sh script.
# tini helps handle signals correctly and reaps zombie processes.
ENTRYPOINT ["/usr/bin/tini", "--"]

# Command to run when the container starts
CMD ["/app/entrypoint.sh"] 