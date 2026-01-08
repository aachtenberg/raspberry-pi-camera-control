#!/bin/bash

# Deploy picamctl to Raspberry Pi
# Usage: ./deploy_to_pi.sh

# Set these (or export PI_USER and PI_HOST in your environment)
PI_USER="${PI_USER:-pi}"
PI_HOST="${PI_HOST:-<PI_HOST>}"
REMOTE_DIR="/home/${PI_USER}/picamctl"

echo "🚀 Deploying picamctl to Pi..."

# Get the project root directory (parent of scripts/)
PROJECT_ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$PROJECT_ROOT"

# Create remote directory if it doesn't exist
ssh ${PI_USER}@${PI_HOST} "mkdir -p ${REMOTE_DIR}"

# Copy files to Pi
echo "📦 Copying files..."
scp picamctl.py ${PI_USER}@${PI_HOST}:${REMOTE_DIR}/
scp templates/garage_cam_template.html ${PI_USER}@${PI_HOST}:${REMOTE_DIR}/
scp templates/landing.html ${PI_USER}@${PI_HOST}:${REMOTE_DIR}/
scp templates/vlc_stream.html ${PI_USER}@${PI_HOST}:${REMOTE_DIR}/
scp picamctl_settings.json ${PI_USER}@${PI_HOST}:${REMOTE_DIR}/
scp systemd/picamctl.service ${PI_USER}@${PI_HOST}:${REMOTE_DIR}/
scp scripts/manage_service.sh ${PI_USER}@${PI_HOST}:${REMOTE_DIR}/

# Make scripts executable
ssh ${PI_USER}@${PI_HOST} "chmod +x ${REMOTE_DIR}/manage_service.sh"

# Install/update systemd service
echo "⚙️  Installing systemd service..."
ssh ${PI_USER}@${PI_HOST} "sudo cp ${REMOTE_DIR}/picamctl.service /etc/systemd/system/ && sudo systemctl daemon-reload"

# Restart service
echo "🔄 Restarting picamctl service..."
ssh ${PI_USER}@${PI_HOST} "sudo systemctl restart picamctl"

# Check status
echo ""
echo "✅ Deployment complete!"
echo ""
echo "📊 Service status:"
ssh ${PI_USER}@${PI_HOST} "sudo systemctl status picamctl --no-pager -l | head -20"

echo ""
echo "🌐 Access camera at: http://${PI_HOST}:5000"
echo ""
echo "📝 View logs with:"
echo "   ssh ${PI_USER}@${PI_HOST} 'sudo journalctl -u picamctl -f'"
