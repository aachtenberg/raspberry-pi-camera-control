#!/bin/bash
# Simple startup script for picamctl
# Add to crontab with: @reboot /home/aachten/picamctl/start_camera.sh

cd /home/aachten/picamctl
python3 picamctl.py >> camera.log 2>&1
