#!/bin/bash

# Deploy Camera Control to Raspberry Pi
# Usage: ./deploy_to_pi.sh

# Set these (or export PI_USER and PI_HOST in your environment)
PI_USER="${PI_USER:-pi}"
PI_HOST="${PI_HOST:-<PI_HOST>}"
REMOTE_DIR="/home/${PI_USER}/camera_control"

echo "🚀 Deploying Camera Control to Pi..."

# Create remote directory if it doesn't exist
ssh ${PI_USER}@${PI_HOST} "mkdir -p ${REMOTE_DIR}"

# Copy files to Pi
echo "📦 Copying files..."
scp camera_control.py ${PI_USER}@${PI_HOST}:${REMOTE_DIR}/
scp garage_cam_template.html ${PI_USER}@${PI_HOST}:${REMOTE_DIR}/
scp camera_settings.json ${PI_USER}@${PI_HOST}:${REMOTE_DIR}/
scp camera-control.service ${PI_USER}@${PI_HOST}:${REMOTE_DIR}/
scp manage_service.sh ${PI_USER}@${PI_HOST}:${REMOTE_DIR}/

# Make scripts executable
ssh ${PI_USER}@${PI_HOST} "chmod +x ${REMOTE_DIR}/manage_service.sh"

# Install/update systemd service
echo "⚙️  Installing systemd service..."
ssh ${PI_USER}@${PI_HOST} "sudo cp ${REMOTE_DIR}/camera-control.service /etc/systemd/system/ && sudo systemctl daemon-reload"

# Restart service
echo "🔄 Restarting camera-control service..."
ssh ${PI_USER}@${PI_HOST} "sudo systemctl restart camera-control"

# Check status
echo ""
echo "✅ Deployment complete!"
echo ""
echo "📊 Service status:"
ssh ${PI_USER}@${PI_HOST} "sudo systemctl status camera-control --no-pager -l | head -20"

echo ""
echo "🌐 Access camera at: http://${PI_HOST}:5000"
echo ""
echo "📝 View logs with:"
echo "   ssh ${PI_USER}@${PI_HOST} 'sudo journalctl -u camera-control -f'"
