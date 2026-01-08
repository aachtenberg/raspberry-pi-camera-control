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
    *)
        echo "Usage: $0 {start|stop|restart|status|logs|enable|disable}"
        echo ""
        echo "Commands:"
        echo "  start   - Start the service"
        echo "  stop    - Stop the service"
        echo "  restart - Restart the service"
        echo "  status  - Show service status"
        echo "  logs    - Show and follow service logs"
        echo "  enable  - Enable service to start on boot"
        echo "  disable - Disable service from starting on boot"
        exit 1
        ;;
esac

