#!/bin/bash

# picamctl Service Management Script

SERVICE_NAME="picamctl"

case "$1" in
    start)
        echo "Starting picamctl service..."
        sudo systemctl start $SERVICE_NAME
        ;;
    stop)
        echo "Stopping picamctl service..."
        sudo systemctl stop $SERVICE_NAME
        ;;
    restart)
        echo "Restarting picamctl service..."
        sudo systemctl restart $SERVICE_NAME
        ;;
    status)
        echo "picamctl service status:"
        sudo systemctl status $SERVICE_NAME
        # Check for Pi Zero 2 W and show resource usage
        PI_MODEL=$(cat /proc/device-tree/model 2>/dev/null || echo "Unknown")
        if echo "$PI_MODEL" | grep -q "Zero 2 W"; then
            echo ""
            echo "⚠️ Raspberry Pi Zero 2 W detected - Resource usage:"
            top -bn1 | grep python || echo "Service not running"
            echo "Recommendation: Monitor CPU usage and use lower resolution/framerate if high."
        fi
        ;;
    logs)
        echo "picamctl service logs:"
        sudo journalctl -u $SERVICE_NAME -f
        ;;
    enable)
        echo "Enabling picamctl service to start on boot..."
        sudo systemctl enable $SERVICE_NAME
        ;;
    disable)
        echo "Disabling picamctl service from starting on boot..."
        sudo systemctl disable $SERVICE_NAME
        ;;
    optimize)
        echo "Optimizing for Raspberry Pi Zero 2 W..."
        PI_MODEL=$(cat /proc/device-tree/model 2>/dev/null || echo "Unknown")
        if echo "$PI_MODEL" | grep -q "Zero 2 W"; then
            # Set nice priority for the service process
            SERVICE_PID=$(pgrep -f picamctl.py)
            if [ -n "$SERVICE_PID" ]; then
                sudo renice -n 10 -p $SERVICE_PID
                echo "✅ Set lower priority (nice 10) for picamctl process"
            else
                echo "❌ Service not running - start the service first"
            fi
        else
            echo "❌ Not a Pi Zero 2 W - no optimization needed"
        fi
        ;;
    *)
        echo "Usage: $0 {start|stop|restart|status|logs|enable|disable|optimize}"
        echo ""
        echo "Commands:"
        echo "  start   - Start the service"
        echo "  stop    - Stop the service"
        echo "  restart - Restart the service"
        echo "  status  - Show service status"
        echo "  logs    - Show and follow service logs"
        echo "  enable  - Enable service to start on boot"
        echo "  disable - Disable service from starting on boot"
        echo "  optimize - Apply Pi Zero 2 W optimizations (lower priority)"
        exit 1
        ;;
esac

