#!/usr/bin/env python3

from flask import Flask, jsonify, render_template_string
import subprocess
import threading
import time
import os
import sys
import signal

app = Flask(__name__)

# Global status tracking
service_status = {
    "web_server_ready": True,
    "bridge_process": None,
    "qr_code": None,
    "bridge_logs": [],
    "startup_time": time.time()
}

print("🌐 WEB SERVER STARTING - NOT start.sh!")
print(f"⏰ Startup time: {time.time()}")

def monitor_bridge_logs():
    """Monitor bridge logs for QR codes."""
    try:
        print("📱 Starting WhatsApp Bridge for QR capture...")
        
        # Start bridge process
        bridge_process = subprocess.Popen(
            ['/app/whatsapp-bridge'],
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            bufsize=1,
            universal_newlines=True
        )
        
        service_status["bridge_process"] = bridge_process
        
        # Monitor output for QR codes
        qr_lines = []
        capturing_qr = False
        line_count = 0
        start_time = time.time()
        
        while bridge_process.poll() is None:
            try:
                line = bridge_process.stdout.readline()
                if line:
                    line_count += 1
                    service_status["bridge_logs"].append(line.strip())
                    print(f"Bridge [{line_count}]: {line.strip()}")
                    
                    # More aggressive QR detection
                    if any(phrase in line.lower() for phrase in ["scan this qr", "qr code", "whatsapp app"]):
                        print("🔍 QR code section detected!")
                        capturing_qr = True
                        qr_lines = []
                        continue
                    
                    # Check if already authenticated
                    if any(phrase in line.lower() for phrase in ["logged in", "authenticated", "connected to whatsapp", "session restored"]):
                        print("✅ WhatsApp already authenticated!")
                        service_status["qr_code"] = "AUTHENTICATED"
                        
                        # Auto-trigger deployment flow if not already running
                        if service_status.get("deployment_flow_status") not in ["running", "completed"]:
                            print("🚀 Auto-triggering post-deployment flow...")
                            try:
                                def auto_run_deployment_flow():
                                    try:
                                        result = subprocess.run(
                                            ["python3", "/app/post_deployment.py"],
                                            capture_output=True,
                                            text=True,
                                            timeout=1800
                                        )
                                        
                                        if result.returncode == 0:
                                            print("✅ Auto post-deployment flow completed!")
                                            service_status["deployment_flow_status"] = "completed"
                                            service_status["deployment_flow_output"] = result.stdout
                                        else:
                                            print("❌ Auto post-deployment flow failed!")
                                            service_status["deployment_flow_status"] = "failed"
                                            service_status["deployment_flow_error"] = result.stderr
                                            
                                    except Exception as e:
                                        print(f"❌ Auto deployment flow exception: {str(e)}")
                                        service_status["deployment_flow_status"] = "error"
                                        service_status["deployment_flow_error"] = str(e)
                                
                                # Start auto deployment flow
                                auto_thread = threading.Thread(target=auto_run_deployment_flow, daemon=True)
                                auto_thread.start()
                                service_status["deployment_flow_status"] = "running"
                                
                            except Exception as e:
                                print(f"❌ Failed to auto-trigger deployment flow: {str(e)}")
                        
                        break
                    
                    # Capture QR code lines - even more inclusive
                    if capturing_qr:
                        # Check for ANY line with block characters
                        if any(char in line for char in ['█', '▀', '▄', '▐', '▌', '▆', '▇', '▘', '▝', '▗', '▖']):
                            qr_lines.append(line.rstrip())
                            print(f"📦 QR line captured: {len(qr_lines)} lines so far")
                        # Also capture lines that start with multiple block chars
                        elif line.strip().startswith('██') or '████' in line:
                            qr_lines.append(line.rstrip())
                            print(f"📦 QR border captured: {len(qr_lines)} lines so far")
                        # Stop capturing on empty lines or text after QR
                        elif line.strip() == '' or (line.strip() and not any(char in line for char in ['█', '▀', '▄', '▐', '▌', '▆', '▇', '▘', '▝', '▗', '▖', ' '])):
                            if qr_lines and len(qr_lines) > 15:  # Lower threshold
                                service_status["qr_code"] = '\n'.join(qr_lines)
                                print(f"✅ QR code captured! ({len(qr_lines)} lines)")
                                print(f"🔍 QR preview: {qr_lines[0][:50]}...")
                                break  # Stop monitoring once we have a QR
                            elif qr_lines:
                                print(f"⚠️ QR too short ({len(qr_lines)} lines), continuing...")
                            capturing_qr = False
                    
                # Check for timeout - restart bridge if no QR after 60 seconds
                if time.time() - start_time > 60 and not service_status.get("qr_code"):
                    print("⏰ Timeout: No QR code detected, restarting bridge...")
                    bridge_process.terminate()
                    time.sleep(2)
                    service_status["qr_code"] = None
                    break  # This will restart the function
                    
            except Exception as e:
                print(f"Error reading bridge output: {e}")
                break
                
    except Exception as e:
        print(f"❌ Bridge startup error: {e}")

@app.route('/health')
def health_check():
    """Railway health check endpoint."""
    return jsonify({
        "status": "healthy",
        "web_server": "running",
        "timestamp": time.time()
    }), 200

@app.route('/')
def root():
    """Root endpoint showing service info."""
    return jsonify({
        "service": "WhatsApp Link Forwarder",
        "status": "running",
        "endpoints": ["/health", "/qr", "/logs", "/qr-debug", "/trigger-deployment-flow", "/deployment-status"],
        "bridge_running": service_status["bridge_process"] is not None,
        "deployment_flow_status": service_status.get("deployment_flow_status", "not_started")
    })

@app.route('/qr')
def qr_display():
    """Display QR code for WhatsApp authentication."""
    
    html_template = """
    <!DOCTYPE html>
    <html>
    <head>
        <title>WhatsApp QR Code</title>
        <meta charset="UTF-8">
        <meta name="viewport" content="width=device-width, initial-scale=1.0">
        <style>
            body { 
                font-family: Arial, sans-serif; 
                background: #0a0a0a; 
                color: white; 
                margin: 0; 
                padding: 20px; 
                text-align: center;
            }
            .container { 
                max-width: 900px; 
                margin: 0 auto; 
                background: #1a1a1a; 
                border-radius: 15px; 
                padding: 30px;
                border: 2px solid #25D366;
            }
            .qr-code { 
                font-family: 'Courier New', monospace; 
                font-size: 6px; 
                line-height: 1.1; 
                white-space: pre; 
                background: white; 
                color: black; 
                padding: 15px; 
                border-radius: 8px; 
                display: inline-block; 
                margin: 20px 0;
                max-width: 500px;
                overflow: visible;
                border: 3px solid #000;
                letter-spacing: -0.5px;
                word-spacing: 0px;
                font-weight: normal;
            }
            @media (max-width: 768px) {
                .qr-code {
                    font-size: 4px;
                    line-height: 1.0;
                    max-width: 350px;
                    padding: 10px;
                }
            }
            @media (min-width: 1200px) {
                .qr-code {
                    font-size: 8px;
                    line-height: 1.2;
                    max-width: 600px;
                }
            }
            .status { 
                background: #25D366; 
                color: white; 
                padding: 15px; 
                border-radius: 8px; 
                margin: 15px 0;
                font-size: 18px;
                font-weight: bold;
            }
            .instructions {
                background: #2d2d2d;
                padding: 20px;
                border-radius: 10px;
                margin: 20px 0;
                text-align: left;
                display: inline-block;
            }
            .refresh-btn {
                background: #25D366;
                color: white;
                border: none;
                padding: 15px 30px;
                border-radius: 8px;
                font-size: 16px;
                cursor: pointer;
                margin: 10px;
                font-weight: bold;
            }
            .refresh-btn:hover { background: #1da851; }
            .waiting {
                background: #ff9800;
                color: white;
                padding: 15px;
                border-radius: 8px;
                margin: 15px 0;
            }
        </style>
        <script>
            // Auto-refresh every 10 seconds
            setTimeout(function(){ location.reload(); }, 10000);
        </script>
    </head>
    <body>
        <div class="container">
            <h1>🔐 WhatsApp Authentication</h1>
            {% if qr_code %}
                {% if qr_code == "AUTHENTICATED" %}
                    <div class="status">✅ WhatsApp Already Authenticated!</div>
                    <div class="instructions">
                        <h3>🎉 Great! Your WhatsApp is connected!</h3>
                        <p>No QR code needed - your session is already active.</p>
                        <p>The system is ready for automated link forwarding.</p>
                        
                        <div style="margin-top: 20px;">
                            <button class="refresh-btn" onclick="triggerDeploymentFlow()">
                                🚀 Run Post-Deployment Tests
                            </button>
                            <button class="refresh-btn" onclick="checkDeploymentStatus()" style="background: #2196F3;">
                                📊 Check Status
                            </button>
                        </div>
                        
                        <div id="deployment-status" style="margin-top: 15px; padding: 10px; border-radius: 5px; display: none;">
                            <h4>📋 Deployment Status:</h4>
                            <pre id="deployment-output" style="background: #000; color: #0f0; padding: 10px; border-radius: 5px; max-height: 300px; overflow-y: auto;"></pre>
                        </div>
                    </div>
                    
                    <script>
                        function triggerDeploymentFlow() {
                            document.getElementById('deployment-status').style.display = 'block';
                            document.getElementById('deployment-output').textContent = '🚀 Starting post-deployment flow...';
                            
                            fetch('/trigger-deployment-flow')
                                .then(response => response.json())
                                .then(data => {
                                    if (data.status === 'success') {
                                        document.getElementById('deployment-output').textContent = '✅ Deployment flow triggered successfully!\n📊 Checking status every 5 seconds...';
                                        // Start polling for status
                                        setInterval(checkDeploymentStatus, 5000);
                                    } else {
                                        document.getElementById('deployment-output').textContent = '❌ Failed to trigger deployment flow: ' + data.message;
                                    }
                                })
                                .catch(error => {
                                    document.getElementById('deployment-output').textContent = '❌ Error: ' + error.message;
                                });
                        }
                        
                        function checkDeploymentStatus() {
                            fetch('/deployment-status')
                                .then(response => response.json())
                                .then(data => {
                                    const statusDiv = document.getElementById('deployment-status');
                                    const outputDiv = document.getElementById('deployment-output');
                                    
                                    statusDiv.style.display = 'block';
                                    
                                    let statusText = `📊 Status: ${data.deployment_flow_status}\n`;
                                    
                                    if (data.deployment_flow_output) {
                                        statusText += '\n📋 Output:\n' + data.deployment_flow_output;
                                    }
                                    
                                    if (data.deployment_flow_error) {
                                        statusText += '\n🚨 Error:\n' + data.deployment_flow_error;
                                    }
                                    
                                    outputDiv.textContent = statusText;
                                });
                        }
                    </script>
                {% else %}
                    <div class="status">✅ QR Code Ready - Scan Now!</div>
                    <div class="qr-code">{{ qr_code|safe }}</div>
                    <div class="instructions">
                        <h3>📱 How to Scan:</h3>
                        <ol>
                            <li><strong>Open WhatsApp</strong> on your phone</li>
                            <li>Go to <strong>Settings → Linked Devices</strong></li>
                            <li>Tap <strong>"Link a Device"</strong></li>
                            <li><strong>Scan the QR code above</strong></li>
                            <li>Wait for confirmation ✅</li>
                        </ol>
                    </div>
                {% endif %}
            {% else %}
                <div class="waiting">⏳ Generating QR Code...</div>
                <p>WhatsApp bridge is starting up. The QR code will appear here in ~30 seconds.</p>
                <div class="instructions">
                    <p><strong>What's happening:</strong></p>
                    <ul>
                        <li>WhatsApp bridge is connecting...</li>
                        <li>QR code will be generated automatically</li>
                        <li>This page refreshes every 10 seconds</li>
                    </ul>
                </div>
            {% endif %}
            <button class="refresh-btn" onclick="location.reload()">🔄 Refresh Now</button>
        </div>
    </body>
    </html>
    """
    
    return render_template_string(
        html_template, 
        qr_code=service_status.get("qr_code", "")
    )

@app.route('/logs')
def logs():
    """Show recent bridge logs."""
    recent_logs = service_status["bridge_logs"][-50:]  # Last 50 lines
    return jsonify({
        "logs": recent_logs,
        "total_lines": len(service_status["bridge_logs"]),
        "bridge_running": service_status["bridge_process"] is not None
    })

@app.route('/qr-debug')
def qr_debug():
    """Debug endpoint to show raw QR code data."""
    qr_data = service_status.get("qr_code", "")
    return jsonify({
        "qr_code_present": bool(qr_data),
        "qr_code_length": len(qr_data),
        "qr_code_lines": qr_data.count('\n') + 1 if qr_data else 0,
        "qr_code_preview": qr_data[:200] + "..." if len(qr_data) > 200 else qr_data,
        "qr_code_raw": qr_data
    })

@app.route('/trigger-deployment-flow')
def trigger_deployment_flow():
    """Trigger the post-deployment testing flow."""
    try:
        print("🚀 Triggering post-deployment flow...")
        
        # Run post-deployment script in background
        import subprocess
        import threading
        
        def run_deployment_flow():
            try:
                result = subprocess.run(
                    ["python3", "/app/post_deployment.py"],
                    capture_output=True,
                    text=True,
                    timeout=1800  # 30 minute timeout
                )
                
                if result.returncode == 0:
                    print("✅ Post-deployment flow completed successfully!")
                    service_status["deployment_flow_status"] = "completed"
                    service_status["deployment_flow_output"] = result.stdout
                else:
                    print("❌ Post-deployment flow failed!")
                    service_status["deployment_flow_status"] = "failed"
                    service_status["deployment_flow_error"] = result.stderr
                    
            except Exception as e:
                print(f"❌ Post-deployment flow exception: {str(e)}")
                service_status["deployment_flow_status"] = "error"
                service_status["deployment_flow_error"] = str(e)
        
        # Start deployment flow in background
        deployment_thread = threading.Thread(target=run_deployment_flow, daemon=True)
        deployment_thread.start()
        
        service_status["deployment_flow_status"] = "running"
        
        return jsonify({
            "status": "success",
            "message": "Post-deployment flow triggered",
            "deployment_status": "running"
        })
        
    except Exception as e:
        return jsonify({
            "status": "error",
            "message": f"Failed to trigger deployment flow: {str(e)}"
        }), 500

@app.route('/deployment-status')
def deployment_status():
    """Check the status of the post-deployment flow."""
    return jsonify({
        "deployment_flow_status": service_status.get("deployment_flow_status", "not_started"),
        "deployment_flow_output": service_status.get("deployment_flow_output", ""),
        "deployment_flow_error": service_status.get("deployment_flow_error", ""),
        "bridge_running": service_status["bridge_process"] is not None,
        "qr_code_present": bool(service_status.get("qr_code"))
    })

def signal_handler(signum, frame):
    """Handle shutdown signals."""
    print(f"🛑 Received signal {signum}, shutting down...")
    if service_status["bridge_process"]:
        service_status["bridge_process"].terminate()
    sys.exit(0)

if __name__ == '__main__':
    # Handle shutdown signals
    signal.signal(signal.SIGTERM, signal_handler)
    signal.signal(signal.SIGINT, signal_handler)
    
    print("🌐 Starting WhatsApp QR Web Server...")
    
    # Start bridge monitoring in background thread
    bridge_thread = threading.Thread(target=monitor_bridge_logs, daemon=True)
    bridge_thread.start()
    
    # Start web server immediately
    port = int(os.environ.get('PORT', 8000))
    print(f"🚀 Web server starting on port {port}")
    app.run(host='0.0.0.0', port=port, debug=False) 