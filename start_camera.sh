#!/bin/bash
# Simple startup script for camera control
# Add to crontab with: @reboot /home/aachten/camera_control/start_camera.sh

cd /home/aachten/camera_control
python3 camera_control.py >> camera.log 2>&1
