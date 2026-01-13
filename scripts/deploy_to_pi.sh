#!/bin/bash

# Deploy picamctl to Raspberry Pi
# Usage: ./deploy_to_pi.sh

# Set these (or export PI_USER and PI_HOST in your environment)
[ -f .env ] && source .env
PI_USER="${PI_USER:-pi}"
PI_HOST="${PI_HOST:-your-pi-hostname}"
REMOTE_DIR="/home/${PI_USER}/picamctl"

if [ "$PI_HOST" = "your-pi-hostname" ]; then
  echo "Error: PI_HOST is not set. Please export PI_HOST or edit scripts/deploy_to_pi.sh to set your Raspberry Pi hostname."
  exit 1
fi

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
scp -r static/ ${PI_USER}@${PI_HOST}:${REMOTE_DIR}/
# Skip settings file - preserve local Pi settings
# scp picamctl_settings.json ${PI_USER}@${PI_HOST}:${REMOTE_DIR}/
scp systemd/picamctl.service ${PI_USER}@${PI_HOST}:${REMOTE_DIR}/
scp scripts/manage_service.sh ${PI_USER}@${PI_HOST}:${REMOTE_DIR}/
scp requirements.txt ${PI_USER}@${PI_HOST}:${REMOTE_DIR}/

# Install Python dependencies
echo "📦 Installing Python dependencies..."
ssh ${PI_USER}@${PI_HOST} << EOF
    cd ${REMOTE_DIR}
    pip3 install -r requirements.txt --break-system-packages
EOF

# Make scripts executable
ssh ${PI_USER}@${PI_HOST} "chmod +x ${REMOTE_DIR}/manage_service.sh"

# Detect Pi model and optimize if Zero 2 W
echo "🔍 Detecting Pi model..."
PI_MODEL=$(ssh ${PI_USER}@${PI_HOST} 'cat /proc/device-tree/model || echo "Unknown"')
echo "Pi Model: $PI_MODEL"

if echo "$PI_MODEL" | grep -q "Zero 2 W"; then
    echo "ℹ️  Detected Raspberry Pi Zero 2 W - Applying optimizations..."
    # Set lower default resolution/framerate if settings file doesn't exist
    ssh ${PI_USER}@${PI_HOST} << EOF
        SETTINGS_FILE="${REMOTE_DIR}/picamctl_settings.json"
        if [ ! -f "\$SETTINGS_FILE" ]; then
            echo '{
                "width": 1280,
                "height": 720,
                "framerate": 10
            }' > \$SETTINGS_FILE
            echo "Created optimized default settings for Pi Zero 2 W"
        else
            echo "Existing settings found - manual optimization recommended: 1280x720 @ 10fps"
        fi
EOF
fi

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
