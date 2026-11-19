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
cd "$PROJECT_ROOT" || exit 1

# Preflight: the Pi must be able to resolve public names. Without this the apt
# step below fails with only a warning and the deploy still reports success.
# Set SKIP_DNS_CHECK=1 for a Pi that is deliberately offline.
if [ "${SKIP_DNS_CHECK:-0}" != "1" ]; then
    echo "🔎 Checking DNS on the Pi..."
    ssh ${PI_USER}@${PI_HOST} 'timeout 10 getent ahostsv4 deb.debian.org >/dev/null 2>&1'
    DNS_RC=$?
    if [ $DNS_RC -eq 255 ]; then
        echo "❌ Cannot reach ${PI_USER}@${PI_HOST} over SSH - aborting."
        exit 1
    elif [ $DNS_RC -ne 0 ]; then
        echo "❌ ${PI_HOST} cannot resolve deb.debian.org - aborting before anything is changed."
        ssh ${PI_USER}@${PI_HOST} 'bash -s' << 'EOF'
            BACKUP=/etc/resolv.pre-tailscale-backup.conf
            if grep -qs '^nameserver 100\.100\.100\.100' /etc/resolv.conf && [ -f "$BACKUP" ] && ! grep -qs '^nameserver' "$BACKUP"; then
                # Tailscale saved an empty resolv.conf (written mid Wi-Fi reconnect) as its upstream list
                echo "   Cause: Tailscale owns /etc/resolv.conf but its saved upstream list ($BACKUP) is empty."
                echo "   Fix:   sudo cp /run/NetworkManager/resolv.conf $BACKUP && sudo systemctl restart tailscaled"
            else
                echo "   /etc/resolv.conf on the Pi:"
                grep -v '^#' /etc/resolv.conf | sed 's/^/     /'
            fi
EOF
        echo "   Set SKIP_DNS_CHECK=1 to deploy anyway (dependency installs will fail)."
        exit 1
    fi
fi

# Host setup: OS settings the camera needs for a steady stream. Idempotent -
# each item is skipped when already in place.
echo "🛠️  Applying host settings..."
ssh ${PI_USER}@${PI_HOST} "KEEP_RPI_CONNECT='${KEEP_RPI_CONNECT:-0}' bash -s" << 'EOF'
    # Wi-Fi power save off: it adds latency spikes to the stream
    if [ -d /etc/NetworkManager/conf.d ] && ! grep -rqsE '^\s*wifi\.powersave\s*=\s*2' /etc/NetworkManager/conf.d/; then
        printf '[connection]\nwifi.powersave = 2\n' | sudo tee /etc/NetworkManager/conf.d/picamctl-wifi-powersave.conf >/dev/null
        sudo nmcli general reload conf
        echo "   Wi-Fi power save: disabled in NetworkManager config"
    fi
    for IFACE in $(ls /sys/class/net | grep '^wl'); do
        sudo iw dev "$IFACE" set power_save off 2>/dev/null
        echo "   $IFACE: $(sudo iw dev "$IFACE" get power_save 2>/dev/null || echo 'power save state unknown')"
    done

    # Cap the journal so a misbehaving service cannot fill the SD card
    if ! grep -rqsE '^\s*SystemMaxUse=' /etc/systemd/journald.conf /etc/systemd/journald.conf.d/; then
        sudo mkdir -p /etc/systemd/journald.conf.d
        printf '[Journal]\nSystemMaxUse=100M\n' | sudo tee /etc/systemd/journald.conf.d/picamctl-size.conf >/dev/null
        sudo systemctl restart systemd-journald
        echo "   Journal: capped at 100M"
    fi

    # Raspberry Pi Connect: on a headless Pi its wayvnc unit restart-loops every
    # 5 seconds, burning CPU and SD writes. Set KEEP_RPI_CONNECT=1 to leave it on.
    if [ "$KEEP_RPI_CONNECT" != "1" ]; then
        UNITS=$(systemctl --user list-unit-files --no-legend 'rpi-connect*' 2>/dev/null | awk '$2=="enabled"{print $1}')
        if [ -n "$UNITS" ]; then
            systemctl --user disable --now $UNITS >/dev/null 2>&1
            systemctl --user reset-failed 'rpi-connect*' 2>/dev/null
            echo "   Raspberry Pi Connect: disabled ($(echo $UNITS))"
        fi
    fi
EOF
# --- end host setup ---

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

# Install system dependencies (required for fresh installs)
echo "📦 Installing system dependencies..."
ssh ${PI_USER}@${PI_HOST} "set -e; echo '   Running apt-get update...'; sudo apt-get update -qq; echo '   Installing system packages...'; sudo apt-get install -y -qq python3-pip python3-flask python3-paho-mqtt ffmpeg" && echo "   System dependencies installed" || echo "   ⚠️  Some dependencies may have failed - check the apt-get output above"

# Install Python dependencies (for any extras not in apt)
echo "📦 Installing Python dependencies..."
# shellcheck disable=SC2087  # REMOTE_DIR is meant to expand locally
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
    # shellcheck disable=SC2087  # REMOTE_DIR is meant to expand locally
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

# Enable and restart service
echo "🔄 Enabling and restarting picamctl service..."
ssh ${PI_USER}@${PI_HOST} "sudo systemctl enable picamctl && sudo systemctl restart picamctl"

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
