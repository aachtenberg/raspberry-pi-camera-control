#!/bin/bash

# Check and install dependencies for H.264 HLS streaming

# Set these (or export PI_USER and PI_HOST in your environment)
PI_USER="${PI_USER:-pi}"
PI_HOST="${PI_HOST:-<PI_HOST>}"

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
echo "Checking Python3..."
ssh ${PI_USER}@${PI_HOST} 'which python3' > /dev/null 2>&1

if [ $? -eq 0 ]; then
    echo "✅ Python3 is installed"
    ssh ${PI_USER}@${PI_HOST} 'python3 --version'
else
    echo "❌ Python3 is NOT installed"
    echo "Installing Python3..."
    ssh ${PI_USER}@${PI_HOST} 'sudo apt-get update && sudo apt-get install -y python3'
fi

echo ""
echo "Checking pip3..."
ssh ${PI_USER}@${PI_HOST} 'which pip3' > /dev/null 2>&1

if [ $? -eq 0 ]; then
    echo "✅ pip3 is installed"
else
    echo "❌ pip3 is NOT installed"
    echo "Installing pip3..."
    ssh ${PI_USER}@${PI_HOST} 'sudo apt-get install -y python3-pip'
    
    if [ $? -eq 0 ]; then
        echo "✅ pip3 installed successfully"
    else
        echo "❌ Failed to install pip3"
        exit 1
    fi
fi

echo ""
echo "Checking Flask..."
ssh ${PI_USER}@${PI_HOST} 'python3 -c "import flask" 2>/dev/null'

if [ $? -eq 0 ]; then
    echo "✅ Flask is installed"
    ssh ${PI_USER}@${PI_HOST} 'python3 -c "import flask; print(f\"Flask version: {flask.__version__}\")"'
else
    echo "❌ Flask is NOT installed"
    echo "Installing Flask..."
    ssh ${PI_USER}@${PI_HOST} 'pip3 install flask --break-system-packages'
    
    if [ $? -eq 0 ]; then
        echo "✅ Flask installed successfully"
    else
        echo "❌ Failed to install Flask"
        exit 1
    fi
fi

echo ""
echo "✅ All dependencies checked!"
