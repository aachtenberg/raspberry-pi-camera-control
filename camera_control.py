#!/usr/bin/env python3
import subprocess
import signal
import sys
import logging
import json
import os
from flask import Flask, render_template_string, request, jsonify, Response, send_from_directory
import threading
import time

# Configure logging for service operation
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.StreamHandler(sys.stdout)
    ]
)
logger = logging.getLogger(__name__)

app = Flask(__name__)

# Global camera process management
current_camera_process = None
camera_process_lock = threading.Lock()

# Settings persistence
SETTINGS_FILE = os.path.join(os.path.dirname(__file__), 'camera_settings.json')

def save_settings():
    """Save current settings to file"""
    try:
        with open(SETTINGS_FILE, 'w') as f:
            json.dump(settings, f, indent=2)
        logger.info(f"Settings saved to {SETTINGS_FILE}")
    except Exception as e:
        logger.error(f"Failed to save settings: {e}")

def load_settings():
    """Load settings from file"""
    global settings
    try:
        if os.path.exists(SETTINGS_FILE):
            with open(SETTINGS_FILE, 'r') as f:
                loaded_settings = json.load(f)
            # Update settings with loaded values, keeping defaults for missing keys
            settings.update(loaded_settings)
            logger.info(f"Settings loaded from {SETTINGS_FILE}")
            return True
        else:
            logger.info("No saved settings file found, using defaults")
            return False
    except Exception as e:
        logger.error(f"Failed to load settings: {e}")
        return False

# Default settings
settings = {
    'camera_name': 'Garage Cam',  # Camera display name
    'width': 1280,
    'height': 720,
    'framerate': 15,
    'brightness': 0.0,
    'contrast': 1.0,
    'saturation': 1.0,
    'sharpness': 1.0,
    'exposure': 'normal',
    'metering': 'centre',
    'awb': 'auto',
    'rotation': 0,
    'hflip': False,
    'vflip': False,
    'ev': 0,  # EV compensation (-10 to +10)
    'shutter': 0,  # Shutter speed in microseconds (0 = auto)
    'gain': 0,  # Gain value (0 = auto)
    'denoise': 'auto',  # Denoise mode
    'hdr': 'off',  # HDR mode
    'quality': 93,  # JPEG quality (1-100)
    'snapshot_quality': 100  # Snapshot JPEG quality (80-100)
}

# Supported resolutions with fallback priorities (higher index = higher priority)
SUPPORTED_RESOLUTIONS = [
    {'width': 640, 'height': 480, 'name': '640x480 (SD)'},
    {'width': 1280, 'height': 720, 'name': '1280x720 (HD)'},
    {'width': 1920, 'height': 1080, 'name': '1920x1080 (Full HD)'}
]

def validate_resolution(width, height):
    """Check if resolution is supported and return fallback if needed"""
    requested_res = {'width': width, 'height': height}

    # Check if requested resolution is supported
    for res in SUPPORTED_RESOLUTIONS:
        if res['width'] == width and res['height'] == height:
            return requested_res, None

    # Find best fallback (closest lower resolution)
    fallback = SUPPORTED_RESOLUTIONS[0]  # Default to lowest
    for res in SUPPORTED_RESOLUTIONS:
        if res['width'] <= width and res['height'] <= height:
            fallback = res
        else:
            break

    return fallback, f"Resolution {width}x{height} not supported, falling back to {fallback['name']}"

HTML_TEMPLATE_PATH = os.path.join(os.path.dirname(__file__), 'garage_cam_template.html')

def get_html():
    """Load HTML template from file"""
    try:
        with open(HTML_TEMPLATE_PATH, 'r') as f:
            return f.read()
    except Exception as e:
        logger.error(f"Failed to load HTML template: {e}")
        return f'''<!DOCTYPE html>
<html>
<head><title>Error</title></head>
<body><h1>Error loading template</h1><p>{e}</p></body>
</html>'''

HTML = '''
<!DOCTYPE html>
<html>
<head>
    <title>Pi Camera Control</title>
    <meta name="viewport" content="width=device-width, initial-scale=1">
    <style>
        body {
            font-family: Arial;
            max-width: 1400px;
            margin: 10px auto;
            padding: 0 15px;
            background: #1a1a1a;
            color: #e0e0e0;
            transition: all 0.3s ease;
        }
        body.fullscreen {
            max-width: none;
            margin: 0;
            padding: 0;
        }
	.container {
            display: grid;
            grid-template-columns: 1fr 400px;
            gap: 20px;
            align-items: start;
            transition: all 0.3s ease;
        }
        .container.fullscreen {
            grid-template-columns: 1fr;
            gap: 0;
        }
        .container.controls-hidden .controls-panel {
            display: none;
        }
        .video-container {
            background: #000;
            border-radius: 8px;
            overflow: hidden;
            border: 1px solid #333;
            position: relative;
            width: 100%;
            min-height: 60vh;
            max-height: 90vh;
            display: flex;
            align-items: center;
            justify-content: center;
            transition: all 0.3s ease;
        }
        body.fullscreen .video-container {
            border-radius: 0;
            border: none;
            min-height: 100vh;
            max-height: 100vh;
        }
        img {
            width: 100%;
            height: 100%;
            display: block;
            object-fit: contain;
            transition: all 0.3s ease;
        }
        body.fullscreen img {
            object-fit: cover;
        }
        .controls-panel {
            background: #2a2a2a;
            padding: 20px;
            border-radius: 8px;
            border: 1px solid #333;
            transition: all 0.3s ease;
        }
        .video-controls {
            position: absolute;
            top: 10px;
            right: 10px;
            z-index: 10;
            display: flex;
            gap: 10px;
        }
        .video-controls button {
            background: rgba(0, 0, 0, 0.7);
            color: white;
            border: 1px solid #555;
            border-radius: 4px;
            padding: 8px 12px;
            cursor: pointer;
            font-size: 14px;
            transition: all 0.2s ease;
        }
        .video-controls button:hover {
            background: rgba(0, 0, 0, 0.9);
            border-color: #777;
        }
        .fullscreen-btn {
            font-size: 16px;
        }
        .toggle-controls-btn {
            font-size: 14px;
        }
        h1 { 
            grid-column: 1 / -1;
            margin: 0 0 20px 0;
            color: #fff;
        }
        h2 {
            color: #fff;
        }
        .control { 
            margin: 15px 0; 
        }
        label { 
            display: block;
            margin-bottom: 5px;
            font-weight: bold;
            color: #e0e0e0;
        }
        input[type="range"] { 
            width: 100%;
            height: 6px;
            background: #444;
            border-radius: 3px;
            outline: none;
        }
        input[type="range"]::-webkit-slider-thumb {
            appearance: none;
            width: 18px;
            height: 18px;
            background: #4CAF50;
            cursor: pointer;
            border-radius: 50%;
        }
        input[type="range"]::-moz-range-thumb {
            width: 18px;
            height: 18px;
            background: #4CAF50;
            cursor: pointer;
            border-radius: 50%;
            border: none;
        }
        button { 
            width: 100%;
            padding: 12px 20px; 
            background: #4CAF50; 
            color: white; 
            border: none; 
            border-radius: 4px;
            cursor: pointer;
            font-size: 16px;
            margin-top: 10px;
            font-weight: bold;
        }
        button:hover { 
            background: #45a049; 
        }
        .value { 
            float: right;
            color: #888;
        }
        select {
            width: 100%;
            padding: 8px;
            border-radius: 4px;
            border: 1px solid #444;
            background: #333;
            color: #e0e0e0;
        }
        select:focus {
            outline: none;
            border-color: #4CAF50;
        }
        input[type="checkbox"] {
            width: 18px;
            height: 18px;
            cursor: pointer;
            accent-color: #4CAF50;
        }
        .checkbox-group {
            display: flex;
            gap: 15px;
        }
        .checkbox-group label {
            display: inline;
            font-weight: normal;
        }
        @media (max-width: 900px) {
            .container {
                grid-template-columns: 1fr;
            }
            .container.fullscreen .controls-panel {
                display: none;
            }
            .video-controls {
                top: 5px;
                right: 5px;
            }
            .video-controls button {
                padding: 6px 10px;
                font-size: 12px;
            }
        }
        .notification {
            position: fixed;
            top: 20px;
            right: 20px;
            padding: 12px 20px;
            border-radius: 6px;
            color: white;
            font-weight: bold;
            z-index: 1000;
            max-width: 400px;
            box-shadow: 0 4px 12px rgba(0,0,0,0.3);
            transform: translateX(400px);
            transition: transform 0.3s ease;
        }
        .notification.show {
            transform: translateX(0);
        }
        .notification.success {
            background: #4CAF50;
        }
        .notification.warning {
            background: #FF9800;
        }
        .notification.error {
            background: #F44336;
        }
    </style>
</head>
<body>
    <h1>🎥 Pi Camera Control</h1>
    
    <div class="container">
        <div class="video-container">
            <div class="video-controls">
                <button class="toggle-controls-btn" onclick="toggleControls()" title="Toggle Controls (T)">⚙️</button>
                <button class="fullscreen-btn" onclick="toggleFullscreen()" title="Full Screen (F)">⛶</button>
            </div>
            <img id="stream" src="/video_feed" alt="Loading camera feed...">
        </div>
        
        <div class="controls-panel">
            <h2 style="margin-top: 0;">⚙️ Camera Settings</h2>
            
            <div class="control">
                <label>Resolution:</label>
                <select id="resolution">
                    <option value="1920x1080">1920x1080 (Full HD)</option>
                    <option value="1280x720" selected>1280x720 (HD)</option>
                    <option value="640x480">640x480 (SD)</option>
                </select>
            </div>
            
            <div class="control">
                <label>Framerate: <span class="value" id="framerate_val">15</span> fps</label>
                <input type="range" id="framerate" min="10" max="30" value="15" step="5">
            </div>
            
            <div class="control">
                <label>Brightness: <span class="value" id="brightness_val">0.0</span></label>
                <input type="range" id="brightness" min="-1" max="1" value="0" step="0.1">
            </div>
            
            <div class="control">
                <label>Contrast: <span class="value" id="contrast_val">1.0</span></label>
                <input type="range" id="contrast" min="0" max="2" value="1" step="0.1">
            </div>
            
            <div class="control">
                <label>Saturation: <span class="value" id="saturation_val">1.0</span></label>
                <input type="range" id="saturation" min="0" max="2" value="1" step="0.1">
            </div>
            
            <div class="control">
                <label>Sharpness: <span class="value" id="sharpness_val">1.0</span></label>
                <input type="range" id="sharpness" min="0" max="16" value="1" step="0.5">
            </div>

            <div class="control">
                <label>EV Compensation: <span class="value" id="ev_val">0</span></label>
                <input type="range" id="ev" min="-10" max="10" value="0" step="0.5">
            </div>

            <div class="control">
                <label>Shutter Speed (μs): <span class="value" id="shutter_val">Auto</span></label>
                <input type="range" id="shutter" min="0" max="1000000" value="0" step="1000">
                <small style="color: #888; font-size: 11px;">0 = Auto</small>
            </div>

            <div class="control">
                <label>Gain: <span class="value" id="gain_val">Auto</span></label>
                <input type="range" id="gain" min="0" max="16" value="0" step="0.1">
                <small style="color: #888; font-size: 11px;">0 = Auto</small>
            </div>

            <div class="control">
                <label>Denoise:</label>
                <select id="denoise">
                    <option value="auto" selected>Auto</option>
                    <option value="off">Off</option>
                    <option value="cdn_off">CDN Off</option>
                    <option value="cdn_fast">CDN Fast</option>
                    <option value="cdn_hq">CDN High Quality</option>
                </select>
            </div>

            <div class="control">
                <label>HDR Mode:</label>
                <select id="hdr">
                    <option value="off" selected>Off</option>
                    <option value="auto">Auto</option>
                    <option value="sensor">Sensor</option>
                    <option value="single-exp">Single Exposure</option>
                </select>
            </div>

            <div class="control">
                <label>Quality: <span class="value" id="quality_val">93</span>%</label>
                <input type="range" id="quality" min="1" max="100" value="93" step="1">
            </div>

            <div class="control">
                <label>Snapshot Quality: <span class="value" id="snapshot_quality_val">100</span>%</label>
                <input type="range" id="snapshot_quality" min="80" max="100" value="100" step="5">
                <small style="color: #888; font-size: 11px;">Quality for captured pictures</small>
            </div>
            
            <div class="control">
                <label>Exposure:</label>
                <select id="exposure">
                    <option value="normal" selected>Normal</option>
                    <option value="sport">Sport</option>
                </select>
            </div>

            <div class="control">
                <label>Metering:</label>
                <select id="metering">
                    <option value="centre" selected>Centre</option>
                    <option value="spot">Spot</option>
                    <option value="average">Average</option>
                    <option value="custom">Custom</option>
                </select>
            </div>
            
            <div class="control">
                <label>White Balance:</label>
                <select id="awb">
                    <option value="auto" selected>Auto</option>
                    <option value="incandescent">Incandescent</option>
                    <option value="tungsten">Tungsten</option>
                    <option value="fluorescent">Fluorescent</option>
                    <option value="indoor">Indoor</option>
                    <option value="daylight">Daylight</option>
                    <option value="cloudy">Cloudy</option>
                    <option value="custom">Custom</option>
                </select>
            </div>
            
            <div class="control">
                <label>Rotation:</label>
                <select id="rotation">
                    <option value="0" selected>0°</option>
                    <option value="90">90°</option>
                    <option value="180">180°</option>
                    <option value="270">270°</option>
                </select>
            </div>
            
            <div class="control">
                <label>Flip:</label>
                <div class="checkbox-group">
                    <label><input type="checkbox" id="hflip"> Horizontal</label>
                    <label><input type="checkbox" id="vflip"> Vertical</label>
                </div>
            </div>
            
            <button onclick="applySettings()">Apply Settings</button>
            <button onclick="takeSnapshot()" style="background: #2196F3; margin-left: 10px;">📸 Take Picture</button>
        </div>
    </div>
    <script>
        // Load settings from backend on page load
        window.onload = function() {
            // Load current settings from server
            fetch('/settings')
                .then(response => response.json())
                .then(serverSettings => {
                    // Apply server settings to form
                    applyServerSettings(serverSettings);

                    // Also restore from localStorage if available (for UI state)
                    const saved = localStorage.getItem('cameraSettings');
                    if (saved) {
                        const localSettings = JSON.parse(saved);
                        // Merge local settings with server settings (local takes precedence for UI state)
                        applyServerSettings({...serverSettings, ...localSettings});
                    }

                    // Update all value displays
                    document.querySelectorAll('input[type="range"]').forEach(input => {
                        updateValueDisplay(input);
                    });
                })
                .catch(error => {
                    console.error('Failed to load settings:', error);
                    // Fallback to updating displays with current values
                    document.querySelectorAll('input[type="range"]').forEach(input => {
                        updateValueDisplay(input);
                    });
                });
        };

        function applyServerSettings(settings) {
            // Apply settings to form controls
            document.getElementById('resolution').value = settings.width + 'x' + settings.height;
            document.getElementById('framerate').value = settings.framerate;
            document.getElementById('brightness').value = settings.brightness;
            document.getElementById('contrast').value = settings.contrast;
            document.getElementById('saturation').value = settings.saturation;
            document.getElementById('sharpness').value = settings.sharpness;
            document.getElementById('exposure').value = settings.exposure || 'normal';
            document.getElementById('metering').value = settings.metering || 'centre';
            document.getElementById('awb').value = settings.awb || 'auto';
            document.getElementById('rotation').value = settings.rotation || 0;
            document.getElementById('hflip').checked = settings.hflip || false;
            document.getElementById('vflip').checked = settings.vflip || false;

            // Advanced settings
            document.getElementById('ev').value = settings.ev || 0;
            document.getElementById('shutter').value = settings.shutter || 0;
            document.getElementById('gain').value = settings.gain || 0;
            document.getElementById('denoise').value = settings.denoise || 'auto';
            document.getElementById('hdr').value = settings.hdr || 'off';
            document.getElementById('quality').value = settings.quality || 93;
            document.getElementById('snapshot_quality').value = settings.snapshot_quality || 100;
            document.getElementById('snapshot_quality_val').textContent = (settings.snapshot_quality || 100) + '%';
        }

        function updateValueDisplay(input) {
            let displayValue = input.value;
            if (input.id === 'shutter') {
                displayValue = input.value == 0 ? 'Auto' : input.value + 'μs';
            } else if (input.id === 'gain') {
                displayValue = input.value == 0 ? 'Auto' : input.value;
            } else if (input.id === 'quality' || input.id === 'snapshot_quality') {
                displayValue = input.value + '%';
            }
            document.getElementById(input.id + '_val').textContent = displayValue;
        }
        
        document.querySelectorAll('input[type="range"]').forEach(input => {
            input.addEventListener('input', function() {
                updateValueDisplay(this);
            });
        });
        
        function applySettings() {
            const res = document.getElementById('resolution').value.split('x');
            const settings = {
                width: parseInt(res[0]),
                height: parseInt(res[1]),
                framerate: parseInt(document.getElementById('framerate').value),
                brightness: parseFloat(document.getElementById('brightness').value),
                contrast: parseFloat(document.getElementById('contrast').value),
                saturation: parseFloat(document.getElementById('saturation').value),
                sharpness: parseFloat(document.getElementById('sharpness').value),
                exposure: document.getElementById('exposure').value,
                awb: document.getElementById('awb').value,
                metering: document.getElementById('metering').value,
                rotation: parseInt(document.getElementById('rotation').value),
                hflip: document.getElementById('hflip').checked,
                vflip: document.getElementById('vflip').checked,
                ev: parseFloat(document.getElementById('ev').value),
                shutter: parseInt(document.getElementById('shutter').value),
                gain: parseFloat(document.getElementById('gain').value),
                denoise: document.getElementById('denoise').value,
                hdr: document.getElementById('hdr').value,
                quality: parseInt(document.getElementById('quality').value),
                snapshot_quality: parseInt(document.getElementById('snapshot_quality').value)
            };
            
            // Save to localStorage for persistence
            localStorage.setItem('cameraSettings', JSON.stringify(settings));
            
            fetch('/apply', {
                method: 'POST',
                headers: {'Content-Type': 'application/json'},
                body: JSON.stringify(settings)
            }).then(response => response.json()).then(data => {
                // Update UI with actual applied resolution
                if (data.resolution) {
                    document.getElementById('resolution').value = data.resolution;
                }

                // Show warning if resolution was changed
                if (data.warning) {
                    showNotification(data.warning, 'warning');
                } else {
                    showNotification('Settings applied successfully', 'success');
                }

                // Reload the video feed
                const img = document.getElementById('stream');
                img.src = '/video_feed?' + new Date().getTime();
            }).catch(error => {
                showNotification('Failed to apply settings', 'error');
                console.error('Settings apply error:', error);
            });
        }

        function takeSnapshot() {
            const button = event.target;
            const originalText = button.textContent;

            // Disable button and show progress
            button.disabled = true;
            button.textContent = '📸 Taking...';
            button.style.background = '#666';

            fetch('/snapshot', {
                method: 'POST'
            }).then(response => response.json()).then(data => {
                if (data.success) {
                    showNotification(`Picture saved: ${data.filename}`, 'success');

                    // Show download link
                    if (data.url) {
                        const link = document.createElement('a');
                        link.href = data.url;
                        link.download = data.filename;
                        link.textContent = `Download ${data.filename}`;
                        link.style.cssText = `
                            display: inline-block;
                            margin-top: 10px;
                            padding: 8px 16px;
                            background: #4CAF50;
                            color: white;
                            text-decoration: none;
                            border-radius: 4px;
                            font-size: 14px;
                        `;
                        link.onclick = () => setTimeout(() => link.remove(), 1000);

                        // Add to a temporary container
                        const container = document.createElement('div');
                        container.style.cssText = `
                            position: fixed;
                            top: 50%;
                            left: 50%;
                            transform: translate(-50%, -50%);
                            background: white;
                            padding: 20px;
                            border-radius: 8px;
                            box-shadow: 0 4px 12px rgba(0,0,0,0.3);
                            z-index: 10000;
                        `;
                        container.innerHTML = '<h3 style="margin:0 0 10px 0;color:#333;">Picture Captured!</h3>';
                        container.appendChild(link);

                        // Add close button
                        const closeBtn = document.createElement('button');
                        closeBtn.textContent = '×';
                        closeBtn.style.cssText = `
                            position: absolute;
                            top: 5px;
                            right: 10px;
                            background: none;
                            border: none;
                            font-size: 20px;
                            cursor: pointer;
                            color: #666;
                        `;
                        closeBtn.onclick = () => container.remove();
                        container.appendChild(closeBtn);

                        document.body.appendChild(container);

                        // Auto-remove after 30 seconds
                        setTimeout(() => {
                            if (container.parentNode) container.remove();
                        }, 30000);
                    }
                } else {
                    showNotification('Failed to take picture: ' + (data.error || 'Unknown error'), 'error');
                }
            }).catch(error => {
                showNotification('Failed to take picture', 'error');
                console.error('Snapshot error:', error);
            }).finally(() => {
                // Re-enable button
                button.disabled = false;
                button.textContent = originalText;
                button.style.background = '#2196F3';
            });
        }
        
        // Full screen functionality
        function toggleFullscreen() {
            const body = document.body;
            const container = document.querySelector('.container');
            const isFullscreen = body.classList.contains('fullscreen');

            if (!isFullscreen) {
                // Enter fullscreen
                body.classList.add('fullscreen');
                container.classList.add('fullscreen');
                document.querySelector('.fullscreen-btn').textContent = '⛶';
                document.querySelector('.fullscreen-btn').title = 'Exit Full Screen (F or Escape)';
            } else {
                // Exit fullscreen
                body.classList.remove('fullscreen');
                container.classList.remove('fullscreen');
                document.querySelector('.fullscreen-btn').textContent = '⛶';
                document.querySelector('.fullscreen-btn').title = 'Full Screen (F)';
            }
        }

        // Toggle controls visibility
        function toggleControls() {
            const container = document.querySelector('.container');
            const isHidden = container.classList.contains('controls-hidden');

            if (!isHidden) {
                container.classList.add('controls-hidden');
                document.querySelector('.toggle-controls-btn').title = 'Show Controls (T)';
            } else {
                container.classList.remove('controls-hidden');
                document.querySelector('.toggle-controls-btn').title = 'Hide Controls (T)';
            }
        }

        // Keyboard shortcuts
        document.addEventListener('keydown', function(event) {
            if (event.key === 'f' || event.key === 'F') {
                event.preventDefault();
                toggleFullscreen();
            } else if (event.key === 't' || event.key === 'T') {
                event.preventDefault();
                toggleControls();
            } else if (event.key === 'Escape') {
                const body = document.body;
                if (body.classList.contains('fullscreen')) {
                    event.preventDefault();
                    toggleFullscreen();
                }
            }
        });

        // Notification system
        function showNotification(message, type = 'info') {
            // Remove existing notifications
            const existing = document.querySelector('.notification');
            if (existing) {
                existing.remove();
            }

            // Create new notification
            const notification = document.createElement('div');
            notification.className = `notification ${type}`;
            notification.textContent = message;
            document.body.appendChild(notification);

            // Show notification
            setTimeout(() => notification.classList.add('show'), 10);

            // Auto-hide after 4 seconds
            setTimeout(() => {
                notification.classList.remove('show');
                setTimeout(() => notification.remove(), 300);
            }, 4000);
        }

        // Note: Settings are now loaded from server on page load (see window.onload above)
        // localStorage is still used to preserve UI state between page refreshes
    </script>
    
</body>
</html>
'''

def stop_camera_process():
    """Stop the current camera process if running"""
    global current_camera_process
    with camera_process_lock:
        if current_camera_process and current_camera_process.poll() is None:
            try:
                logger.info("Stopping current camera process...")
                current_camera_process.terminate()
                current_camera_process.wait(timeout=2)
                logger.info("Camera process stopped")
            except:
                try:
                    current_camera_process.kill()
                    current_camera_process.wait()
                except:
                    pass
            current_camera_process = None

def start_stream():
    """This function is now just for updating settings"""
    logger.info(f"Settings updated: {settings['width']}x{settings['height']} @ {settings['framerate']}fps")
    # Stop current camera to apply new settings
    stop_camera_process()
    # Save settings whenever they change
    save_settings()

def generate_frames():
    """Capture frames using optimized method - try rpicam-vid first, fallback to rpicam-still"""
    # Use lower quality for streaming to improve performance
    stream_quality = min(settings['quality'], 50)  # Cap at 50 for better CPU efficiency

    last_restart_time = time.time()

    while True:
        process = None
        try:
            # Try using rpicam-vid with MJPEG for better performance
            # This keeps the camera initialized and streams continuously
            cmd = [
                'rpicam-vid',
                '--nopreview',
                '--codec', 'mjpeg',
                '--width', str(settings['width']),
                '--height', str(settings['height']),
                '--framerate', str(settings['framerate']),
                '--timeout', '0',  # Run indefinitely
                '--brightness', str(settings['brightness']),
                '--contrast', str(settings['contrast']),
                '--saturation', str(settings['saturation']),
                '--sharpness', str(settings['sharpness']),
                '--exposure', settings['exposure'],
                '--metering', settings['metering'],
                '--awb', settings['awb'],
                '--rotation', str(settings['rotation']),
                '--quality', str(stream_quality),
                '-o', '-'  # Output to stdout
            ]

            # Add advanced settings
            if settings['ev'] != 0:
                cmd.extend(['--ev', str(settings['ev'])])
            if settings['shutter'] > 0:
                cmd.extend(['--shutter', str(settings['shutter'])])
            if settings['gain'] > 0:
                cmd.extend(['--gain', str(settings['gain'])])
            if settings['denoise'] != 'auto':
                cmd.extend(['--denoise', settings['denoise']])
            if settings['hdr'] != 'off':
                cmd.extend(['--hdr', settings['hdr']])

            if settings['hflip']:
                cmd.append('--hflip')
            if settings['vflip']:
                cmd.append('--vflip')

            # Start continuous video stream
            process = subprocess.Popen(
                cmd,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                bufsize=65536  # Use 64KB buffer instead of unbuffered
            )

            # Register as current camera process
            global current_camera_process
            with camera_process_lock:
                current_camera_process = process

            # Parse MJPEG stream - MJPEG is a series of JPEG frames
            frame_buffer = b''
            jpeg_start = b'\xff\xd8'
            jpeg_end = b'\xff\xd9'

            while True:
                chunk = process.stdout.read(16384)  # Read larger chunks
                if not chunk:
                    if process.poll() is not None:
                        break
                    time.sleep(0.01)
                    continue

                frame_buffer += chunk

                # Extract complete JPEG frames
                # Process only one frame per chunk read to prevent CPU spinning
                frames_processed = 0
                while frames_processed < 1:  # Limit to 1 frame per iteration
                    start_idx = frame_buffer.find(jpeg_start)
                    if start_idx == -1:
                        frame_buffer = frame_buffer[-2048:]  # Keep last 2KB
                        break

                    end_idx = frame_buffer.find(jpeg_end, start_idx + 2)
                    if end_idx == -1:
                        break

                    # Extract and yield frame
                    jpeg_frame = frame_buffer[start_idx:end_idx + 2]
                    frame_buffer = frame_buffer[end_idx + 2:]

                    yield (b'--frame\r\n'
                           b'Content-Type: image/jpeg\r\n\r\n' + jpeg_frame + b'\r\n')

                    frames_processed += 1
                    # Small delay to prevent CPU spinning when processing frames
                    time.sleep(0.001)

        except Exception as e:
            # Check if stream failed quickly (within 5 seconds) and add delay to prevent rapid restarts
            current_time = time.time()
            if current_time - last_restart_time < 5:
                logger.warning("Stream failed quickly, adding delay before restart")
                time.sleep(2)
            last_restart_time = current_time

            logger.error(f"Video stream error: {e}, falling back to still capture")
            # Fallback to optimized still capture
            try:
                frame_interval = 1.0 / settings['framerate']
                cmd = [
                    'rpicam-still',
                    '--nopreview',
                    '--immediate',
                    '--timeout', '300',
                    '--width', str(settings['width']),
                    '--height', str(settings['height']),
                    '--quality', str(stream_quality),
                    '--exposure', settings['exposure'],
                    '--awb', settings['awb'],
                    '-o', '-'
                ]
                
                result = subprocess.run(cmd, capture_output=True, timeout=1)
                if result.returncode == 0 and result.stdout:
                    yield (b'--frame\r\n'
                           b'Content-Type: image/jpeg\r\n\r\n' + result.stdout + b'\r\n')
                time.sleep(frame_interval)
            except Exception as e2:
                logger.error(f"Fallback capture error: {e2}")
                time.sleep(0.5)
        finally:
            if process:
                try:
                    process.terminate()
                    process.wait(timeout=1)
                except:
                    process.kill()
                    process.wait()

@app.route('/')
def index():
    return render_template_string(get_html())

@app.route('/video_feed')
def video_feed():
    return Response(generate_frames(), mimetype='multipart/x-mixed-replace; boundary=frame')

@app.route('/settings')
def get_settings():
    """Get current camera settings"""
    return jsonify(settings)

@app.route('/system_info')
def get_system_info():
    """Get system information for display"""
    import socket
    import shutil
    
    # Get IP address
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.connect(("8.8.8.8", 80))
        ip_address = s.getsockname()[0]
        s.close()
    except:
        ip_address = "Unknown"
    
    # Get disk usage
    try:
        total, used, free = shutil.disk_usage("/")
        total_mb = total // (1024 * 1024)
        used_mb = used // (1024 * 1024)
        disk_info = f"{used_mb:.1f}MB / {total_mb:.1f}MB"
    except:
        disk_info = "Unknown"
    
    # Calculate bandwidth (placeholder - would need actual network monitoring)
    bandwidth_kbps = 0  # TODO: Implement actual bandwidth calculation
    
    return jsonify({
        'ip': ip_address,
        'disk': disk_info,
        'bandwidth': bandwidth_kbps
    })

@app.route('/snapshot', methods=['POST'])
def take_snapshot():
    """Take a high-quality snapshot"""
    try:
        from datetime import datetime
        import os

        # Create snapshots directory if it doesn't exist
        snapshot_dir = os.path.join(os.path.dirname(__file__), 'snapshots')
        os.makedirs(snapshot_dir, exist_ok=True)

        # Generate filename with timestamp
        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
        filename = f'snapshot_{timestamp}.jpg'
        filepath = os.path.join(snapshot_dir, filename)

        # Build command for high-quality snapshot
        cmd = [
            'rpicam-still',
            '--nopreview',
            '--timeout', '3000',  # 3 seconds timeout for high quality
            '--width', str(settings['width']),
            '--height', str(settings['height']),
            '--mode', f"{settings['width']}:{settings['height']}",
            '--quality', str(settings.get('snapshot_quality', 100)),  # High quality for snapshots
            '-o', filepath
        ]

        # Add current settings (but optimize for still capture)
        if settings['brightness'] != 0:
            cmd.extend(['--brightness', str(settings['brightness'])])
        if settings['contrast'] != 1.0:
            cmd.extend(['--contrast', str(settings['contrast'])])
        if settings['saturation'] != 1.0:
            cmd.extend(['--saturation', str(settings['saturation'])])
        if settings['sharpness'] != 1.0:
            cmd.extend(['--sharpness', str(settings['sharpness'])])

        # Always use normal exposure for snapshots (more predictable)
        cmd.extend(['--exposure', 'normal'])

        # Add other relevant settings
        if settings['ev'] != 0:
            cmd.extend(['--ev', str(settings['ev'])])
        if settings['awb'] != 'auto':
            cmd.extend(['--awb', settings['awb']])

        if settings['hflip']:
            cmd.append('--hflip')
        if settings['vflip']:
            cmd.append('--vflip')

        # Capture the image
        result = subprocess.run(cmd, capture_output=True, timeout=10)

        if result.returncode == 0 and os.path.exists(filepath):
            logger.info(f"Snapshot saved: {filepath}")

            # Return success with filename
            return jsonify({
                'success': True,
                'filename': filename,
                'filepath': filepath,
                'url': f'/snapshots/{filename}',
                'timestamp': timestamp
            })
        else:
            logger.error(f"Snapshot failed: {result.stderr.decode()}")
            return jsonify({
                'success': False,
                'error': f'Camera error: {result.stderr.decode() if result.stderr else "Unknown error"}'
            }), 500

    except subprocess.TimeoutExpired:
        logger.error("Snapshot timed out")
        return jsonify({'success': False, 'error': 'Camera timeout'}), 500
    except Exception as e:
        logger.error(f"Snapshot error: {e}")
        return jsonify({'success': False, 'error': str(e)}), 500

@app.route('/snapshots/<filename>')
def serve_snapshot(filename):
    """Serve snapshot images for download"""
    try:
        snapshot_dir = os.path.join(os.path.dirname(__file__), 'snapshots')
        return send_from_directory(snapshot_dir, filename, as_attachment=True)
    except Exception as e:
        logger.error(f"Error serving snapshot {filename}: {e}")
        return jsonify({'error': 'File not found'}), 404

@app.route('/apply', methods=['POST'])
def apply_settings():
    new_settings = request.json
    width = new_settings.get('width', settings['width'])
    height = new_settings.get('height', settings['height'])

    # Validate resolution
    validated_res, warning = validate_resolution(width, height)

    # Update settings with validated resolution
    new_settings['width'] = validated_res['width']
    new_settings['height'] = validated_res['height']
    settings.update(new_settings)

    threading.Thread(target=start_stream, daemon=True).start()

    response = {'status': 'ok', 'resolution': f"{validated_res['width']}x{validated_res['height']}"}
    if warning:
        response['warning'] = warning
        logger.warning(f"Resolution warning: {warning}")

    return jsonify(response)

if __name__ == '__main__':
    # Load saved settings on startup
    load_settings()

    logger.info("Starting camera control interface...")
    logger.info("Access at: http://192.168.0.169:5000")
    app.run(host='0.0.0.0', port=5000, threaded=True)
