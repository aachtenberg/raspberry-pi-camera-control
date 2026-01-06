#!/bin/bash

# Check and install dependencies for H.264 HLS streaming

PI_USER="aachten"
PI_HOST="192.168.0.169"

echo "🔍 Checking dependencies on Raspberry Pi..."

# Check if ffmpeg is installed
echo "Checking ffmpeg..."
ssh ${PI_USER}@${PI_HOST} 'which ffmpeg' > /dev/null 2>&1

if [ $? -eq 0 ]; then
    echo "✅ ffmpeg is installed"
    ssh ${PI_USER}@${PI_HOST} 'ffmpeg -version | head -1'
else
    echo "❌ ffmpeg is NOT installed"
    echo ""
    echo "Installing ffmpeg..."
    ssh ${PI_USER}@${PI_HOST} 'sudo apt-get update && sudo apt-get install -y ffmpeg'
    
    if [ $? -eq 0 ]; then
        echo "✅ ffmpeg installed successfully"
    else
        echo "❌ Failed to install ffmpeg"
        exit 1
    fi
fi

echo ""
echo "Checking rpicam-vid..."
ssh ${PI_USER}@${PI_HOST} 'which rpicam-vid' > /dev/null 2>&1

if [ $? -eq 0 ]; then
    echo "✅ rpicam-vid is installed"
else
    echo "⚠️  rpicam-vid is NOT installed"
    echo "Install with: sudo apt install -y rpicam-apps"
fi

echo ""
echo "Checking Python3 and Flask..."
ssh ${PI_USER}@${PI_HOST} 'python3 -c "import flask" 2>/dev/null'

if [ $? -eq 0 ]; then
    echo "✅ Flask is installed"
else
    echo "❌ Flask is NOT installed"
    echo "Installing Flask..."
    ssh ${PI_USER}@${PI_HOST} 'pip3 install flask --break-system-packages'
fi

echo ""
echo "✅ All dependencies checked!"
