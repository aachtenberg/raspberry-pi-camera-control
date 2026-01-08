#!/usr/bin/env python3
import subprocess
import signal
import sys
import logging
import json
import os
import shutil
from flask import Flask, render_template_string, request, jsonify, Response, send_from_directory
import threading
import time
import paho.mqtt.client as mqtt

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
camera_frame_buffer = []  # Shared frame buffer for all clients
camera_running = False
use_hw_acceleration = True  # Use H.264 hardware encoding
h264_stderr = None  # Keep file handle alive to prevent zombie process

# Streaming mode: 'hls' (web UI with HLS) or 'vlc' (direct H.264 TCP)
streaming_mode = 'hls'  # Default to web UI mode
streaming_mode_lock = threading.Lock()

# VLC streaming buffer - circular buffer for H.264 chunks
vlc_stream_buffer = []
vlc_buffer_lock = threading.Lock()
vlc_buffer_thread = None
vlc_buffer_max_chunks = 100  # Keep last N chunks in memory

# Bandwidth tracking
bandwidth_lock = threading.Lock()
bandwidth_data = {
    'last_check_time': 0,
    'last_total_bytes': 0,
    'current_kbps': 0
}

# Directories and files
SETTINGS_FILE = os.path.join(os.path.dirname(__file__), 'picamctl_settings.json')
HLS_DIR = os.path.join(os.path.dirname(__file__), 'hls_segments')

# Template files - check both deployed location and dev location
def get_template_path(filename):
    """Get template path, checking deployed location first, then dev location"""
    deployed = os.path.join(os.path.dirname(__file__), filename)
    if os.path.exists(deployed):
        return deployed
    dev = os.path.join(os.path.dirname(__file__), 'templates', filename)
    if os.path.exists(dev):
        return dev
    return deployed  # Return deployed path anyway for error message

LANDING_PAGE = get_template_path('landing.html')
VLC_PAGE = get_template_path('vlc_stream.html')

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
    'snapshot_quality': 100,  # Snapshot JPEG quality (80-100)
    'zoom': 1.0,  # Digital zoom (1.0 = no zoom, max depends on user preference)
    'mqtt_enabled': True,
    'mqtt_broker': 'localhost',
    'mqtt_port': 1883,
    'mqtt_user': '',
    'mqtt_password': '',
    'mqtt_base_topic': 'surveillance'
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

def calculate_bandwidth():
    """Calculate current bandwidth from HLS segments"""
    global bandwidth_data
    
    try:
        current_time = time.time()
        total_bytes = 0
        
        # Sum up size of all current HLS segment files
        if os.path.exists(HLS_DIR):
            for file in os.listdir(HLS_DIR):
                if file.endswith('.ts'):
                    file_path = os.path.join(HLS_DIR, file)
                    try:
                        total_bytes += os.path.getsize(file_path)
                    except:
                        pass
        
        with bandwidth_lock:
            # Calculate bandwidth if we have a previous measurement
            if bandwidth_data['last_check_time'] > 0:
                time_diff = current_time - bandwidth_data['last_check_time']
                if time_diff > 0:
                    bytes_diff = total_bytes - bandwidth_data['last_total_bytes']
                    # Convert to Kbps: (bytes * 8 bits/byte) / (time_diff seconds) / 1000
                    kbps = (bytes_diff * 8) / (time_diff * 1000)
                    # Smooth the value with exponential moving average
                    if bandwidth_data['current_kbps'] > 0:
                        bandwidth_data['current_kbps'] = 0.7 * bandwidth_data['current_kbps'] + 0.3 * kbps
                    else:
                        bandwidth_data['current_kbps'] = kbps
            
            # Update tracking data
            bandwidth_data['last_check_time'] = current_time
            bandwidth_data['last_total_bytes'] = total_bytes
            
            return bandwidth_data['current_kbps']
    except Exception as e:
        logger.error(f"Error calculating bandwidth: {e}")
        return 0

HTML_TEMPLATE_PATH = get_template_path('garage_cam_template.html')

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
    <title>picamctl</title>
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
        #mqtt-status {
            background: rgba(0, 0, 0, 0.7);
            color: white;
            border: 1px solid #555;
            border-radius: 4px;
            padding: 8px 12px;
            font-size: 14px;
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
    <h1 id="title">🎥 picamctl</h1>
    
    <div class="container">
        <div class="video-container">
            <div class="video-controls">
                <button class="toggle-controls-btn" onclick="toggleControls()" title="Toggle Controls (T)">⚙️</button>
                <button class="fullscreen-btn" onclick="toggleFullscreen()" title="Full Screen (F)">⛶</button>
                <span id="mqtt-status">MQTT: --</span>
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

            <h2>MQTT Settings</h2>
            
            <div class="control">
                <label><input type="checkbox" id="mqtt_enabled"> Enable MQTT</label>
            </div>
            
            <div class="control">
                <label>Broker Host:</label>
                <input type="text" id="mqtt_broker" value="localhost">
            </div>
            
            <div class="control">
                <label>Broker Port: <span class="value" id="mqtt_port_val">1883</span></label>
                <input type="range" id="mqtt_port" min="1" max="65535" value="1883" step="1">
            </div>
            
            <div class="control">
                <label>Username:</label>
                <input type="text" id="mqtt_user" value="">
            </div>
            
            <div class="control">
                <label>Password:</label>
                <input type="password" id="mqtt_password" value="">
            </div>
            
            <div class="control">
                <label>Base Topic:</label>
                <input type="text" id="mqtt_base_topic" value="surveillance">
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

            // MQTT settings
            document.getElementById('mqtt_enabled').checked = settings.mqtt_enabled || false;
            document.getElementById('mqtt_broker').value = settings.mqtt_broker || 'localhost';
            document.getElementById('mqtt_port').value = settings.mqtt_port || 1883;
            document.getElementById('mqtt_port_val').textContent = settings.mqtt_port || 1883;
            document.getElementById('mqtt_user').value = settings.mqtt_user || '';
            document.getElementById('mqtt_password').value = settings.mqtt_password || '';
            document.getElementById('mqtt_base_topic').value = settings.mqtt_base_topic || 'surveillance';
        }

        function updateValueDisplay(input) {
            let displayValue = input.value;
            if (input.id === 'shutter') {
                displayValue = input.value == 0 ? 'Auto' : input.value + 'μs';
            } else if (input.id === 'gain') {
                displayValue = input.value == 0 ? 'Auto' : input.value;
            } else if (input.id === 'quality' || input.id === 'snapshot_quality') {
                displayValue = input.value + '%';
            } else if (input.id === 'mqtt_port') {
                displayValue = input.value;
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
                snapshot_quality: parseInt(document.getElementById('snapshot_quality').value),
                mqtt_enabled: document.getElementById('mqtt_enabled').checked,
                mqtt_broker: document.getElementById('mqtt_broker').value,
                mqtt_port: parseInt(document.getElementById('mqtt_port').value),
                mqtt_user: document.getElementById('mqtt_user').value,
                mqtt_password: document.getElementById('mqtt_password').value,
                mqtt_base_topic: document.getElementById('mqtt_base_topic').value
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

        function updateMqttStatus() {
            fetch('/system_info')
                .then(response => response.json())
                .then(data => {
                    const statusElem = document.getElementById('mqtt-status');
                    if (statusElem) {
                        statusElem.textContent = `MQTT: ${data.mqtt_connected ? 'Connected' : 'Disconnected'}`;
                        statusElem.style.background = data.mqtt_connected ? 'rgba(76, 175, 80, 0.7)' : 'rgba(244, 67, 54, 0.7)';
                    }
                })
                .catch(error => {
                    console.error('Failed to fetch system info:', error);
                });
        }

        function updateSystemInfo() {
            fetch('/system_info')
                .then(response => response.json())
                .then(data => {
                    const titleElem = document.getElementById('title');
                    const mqttStatus = data.mqtt_connected 
                        ? '<span style="color:green;font-size:1.2em;">●</span> connected' 
                        : '<span style="color:gray;font-size:1.2em;">●</span> disconnected';
                    titleElem.innerHTML = `🎥 picamctl - addr: ${data.ip} mqtt: ${mqttStatus}`;
                    
                    const statusElem = document.getElementById('mqtt-status');
                    if (statusElem) {
                        statusElem.textContent = `MQTT: ${data.mqtt_connected ? 'Connected' : 'Disconnected'}`;
                        statusElem.style.background = data.mqtt_connected ? 'rgba(76, 175, 80, 0.7)' : 'rgba(244, 67, 54, 0.7)';
                    }
                })
                .catch(error => {
                    console.error('Failed to fetch system info:', error);
                });
        }

        // Update system info every 5 seconds
        setInterval(updateSystemInfo, 5000);
        // Initial update
        updateSystemInfo();

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
        logger.info("Stopping camera processes (rpicam-vid, ffmpeg)...")
        
        # Kill rpicam-vid and ffmpeg processes by name since they may be detached
        os.system("pkill -f 'rpicam-vid.*h264'")
        os.system("pkill -f 'ffmpeg.*hls'")
        
        time.sleep(0.5)  # Give them time to die
        
        # Stop camera process
        if current_camera_process and current_camera_process.poll() is None:
            try:
                logger.info("Stopping camera process...")
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
        
        # Clean up FIFO
        vlc_fifo = os.path.join(os.path.dirname(__file__), 'vlc_stream.fifo')
        try:
            if os.path.exists(vlc_fifo):
                os.remove(vlc_fifo)
        except:
            pass
        
        logger.info("Camera processes stopped")

def start_h264_camera():
    """Start H.264 hardware-accelerated camera with HLS output"""
    global current_camera_process, camera_running

    # Create HLS directory if it doesn't exist
    os.makedirs(HLS_DIR, exist_ok=True)
    logger.info(f"HLS directory: {HLS_DIR}")

    # Clean up old HLS segments
    try:
        for file in os.listdir(HLS_DIR):
            if file.endswith(('.ts', '.m3u8')):
                try:
                    os.remove(os.path.join(HLS_DIR, file))
                    logger.info(f"Removed old HLS file: {file}")
                except Exception as e:
                    logger.warning(f"Could not remove {file}: {e}")
    except Exception as e:
        logger.error(f"Error cleaning HLS directory: {e}")

    rotation = int(settings.get('rotation', 0))
    needs_transpose = rotation in (90, 270)
    transpose_filter = 'transpose=1' if rotation == 90 else 'transpose=2'

    # Use H.264 encoding - output to stdout, then use process substitution to split stream
    cmd = [
        'rpicam-vid',
        '--nopreview',
        '--codec', 'h264',  # H.264 hardware encoder
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
        '--inline',  # Inline headers for streaming
        '-o', '-'  # Output to stdout
    ]

    # rpicam-vid cannot rotate 90/270 with H.264; offload to ffmpeg when needed
    if not needs_transpose and rotation != 0:
        cmd.extend(['--rotation', str(rotation)])

    # Add advanced settings BEFORE building full command
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

    # Apply digital zoom (ROI)
    zoom_factor = float(settings.get('zoom', 1.0))
    if zoom_factor > 1.0:
        w = 1.0 / zoom_factor
        h = 1.0 / zoom_factor
        x = (1.0 - w) / 2.0
        y = (1.0 - h) / 2.0
        cmd.extend(['--roi', f"{x},{y},{w},{h}"])

    # Build ffmpeg command - read from stdin (will be piped from tee)
    ffmpeg_cmd = [
        'ffmpeg',
        '-hide_banner',
        '-loglevel', 'warning',
        '-f', 'h264',
        '-i', '-',  # Read from stdin
    ]

    if needs_transpose:
        # Decode, rotate, and re-encode when 90/270 is requested
        # Use software x264 for reliability (still lightweight at 720p/10-15fps)
        ffmpeg_cmd.extend([
            '-vf', transpose_filter,
            '-c:v', 'libx264',
            '-preset', 'ultrafast',
            '-tune', 'zerolatency',
            '-pix_fmt', 'yuv420p',
            '-x264-params', 'keyint=30:min-keyint=30:scenecut=0'
        ])
    else:
        # Zero-copy when no rotation transpose is needed
        ffmpeg_cmd.extend(['-c:v', 'copy'])

    ffmpeg_cmd.extend([
        '-f', 'hls',
        '-hls_time', '1',  # 1 second segments for lower latency
        '-hls_list_size', '5',  # Keep last 5 segments (reduced from 10)
        '-hls_flags', 'delete_segments+append_list',
        '-hls_segment_filename', os.path.join(HLS_DIR, 'segment_%03d.ts'),
        os.path.join(HLS_DIR, 'stream.m3u8')
    ])

    # Simple pipe from rpicam-vid to ffmpeg for HLS
    camera_cmd = ' '.join(cmd)
    ffmpeg_cmd_str = ' '.join(ffmpeg_cmd)
    full_cmd = f"{camera_cmd} | {ffmpeg_cmd_str}"
    
    # Log file for debugging
    log_file = os.path.join(os.path.dirname(__file__), 'camera.log')

    try:
        logger.info(f"Starting H.264 camera for HLS streaming (web UI mode)")
        logger.info(f"Command: {full_cmd}")
        
        # Close previous log file if exists
        global h264_stderr, current_camera_process
        if h264_stderr and not h264_stderr.closed:
            try:
                h264_stderr.close()
            except:
                pass
        
        # Start the piped command
        h264_stderr = open(log_file, 'wb', buffering=0)
        camera_process = subprocess.Popen(
            full_cmd,
            shell=True,
            stdout=subprocess.DEVNULL,
            stderr=h264_stderr,
            start_new_session=True
        )
        
        # Wait and check if process started successfully
        time.sleep(2)
        if camera_process.poll() is not None:
            try:
                with open(log_file, 'r') as f:
                    stderr = f.read()
                logger.error(f"Camera process exited immediately. Error: {stderr}")
            except:
                logger.error("Camera process exited immediately")
            h264_stderr.close()
            return False

        with camera_process_lock:
            current_camera_process = camera_process
            camera_running = True

        logger.info("H.264 hardware-accelerated camera started successfully")
        logger.info("HLS streaming active for web UI")
        
        return True
    except Exception as e:
        logger.error(f"Failed to start H.264 camera: {e}")
        return False

def run_ffmpeg_hls_converter():
    """Convert H.264 TCP stream to HLS segments using ffmpeg - ffmpeg acts as TCP server"""
    global ffmpeg_stderr
    ffmpeg_log = os.path.join(os.path.dirname(__file__), 'ffmpeg.log')
    
    while True:
        try:
            # Start immediately, no wait for camera - ffmpeg starts TCP server first
            
            playlist_path = os.path.join(HLS_DIR, 'stream.m3u8')
            segment_pattern = os.path.join(HLS_DIR, 'segment_%03d.ts')
            
            cmd = [
                'ffmpeg',
                '-hide_banner',
                '-loglevel', 'warning',
                '-listen', '1',       # Act as TCP server
                '-i', 'tcp://0.0.0.0:8888?listen_timeout=60000',  # Listen with timeout
                '-c:v', 'copy',  # Copy video without re-encoding
                '-f', 'hls',
                '-hls_time', '1',  # 1 second segments for lower latency
                '-hls_list_size', '5',  # Keep last 5 segments (reduced from 10 for lower latency)
                '-hls_flags', 'delete_segments+append_list',
                '-hls_segment_filename', segment_pattern,
                playlist_path
            ]
            
            logger.info(f"Starting ffmpeg HLS converter as TCP server: {' '.join(cmd)}")
            
            # Close previous log file if it exists  
            if ffmpeg_stderr and not ffmpeg_stderr.closed:
                try:
                    ffmpeg_stderr.close()
                except:
                    pass
            
            # Open log file for stderr - must keep open for process lifetime
            ffmpeg_stderr = open(ffmpeg_log, 'wb', buffering=0)  # Unbuffered binary mode
            
            # Run ffmpeg - CRITICAL: use file for stderr to prevent zombie process
            process = subprocess.Popen(
                cmd,
                stdout=subprocess.DEVNULL,
                stderr=ffmpeg_stderr,
                start_new_session=True
            )
            
            # Monitor process
            while True:
                if process.poll() is not None:
                    logger.warning("ffmpeg HLS converter exited, will restart in 0.5 seconds...")
                    break
                time.sleep(0.5)  # Check frequently to restart fast
                
        except Exception as e:
            logger.error(f"ffmpeg HLS converter error: {e}, restarting in 1 second...")
        
        # Wait before restarting - reduced from 3s to 1s for faster recovery
        time.sleep(1)

def start_stream():
    """This function is now just for updating settings"""
    logger.info(f"Settings updated: {settings['width']}x{settings['height']} @ {settings['framerate']}fps")
    # Save settings whenever they change
    save_settings()

    # Restart H.264 camera if using hardware acceleration
    if use_hw_acceleration:
        stop_camera_process()
        # Wait for ffmpeg to be ready for new connection
        # ffmpeg will auto-restart when old connection closes
        logger.info("Waiting for ffmpeg to be ready for new connection...")
        time.sleep(2)  # Give ffmpeg time to restart and listen
        threading.Thread(target=start_h264_camera, daemon=True).start()


# ============================================================================
# VLC Streaming (Low Latency Direct H.264 Stream via TCP)
# ============================================================================

def vlc_buffer_reader():
    """Background thread that continuously reads from camera and buffers chunks"""
    global vlc_stream_buffer
    fifo_path = os.path.join(os.path.dirname(__file__), 'vlc_stream.fifo')
    
    try:
        logger.info("VLC buffer thread: Opening FIFO for reading...")
        with open(fifo_path, 'rb', buffering=0) as fifo:
            logger.info("VLC buffer thread: Connected to camera FIFO")
            while True:
                chunk = fifo.read(8192)
                if not chunk:
                    logger.warning("VLC buffer thread: No data from FIFO")
                    break
                
                # Add chunk to circular buffer
                with vlc_buffer_lock:
                    vlc_stream_buffer.append(chunk)
                    # Keep buffer size limited
                    if len(vlc_stream_buffer) > vlc_buffer_max_chunks:
                        vlc_stream_buffer.pop(0)
                        
    except Exception as e:
        logger.error(f"VLC buffer thread error: {e}")
    finally:
        logger.info("VLC buffer thread: Exiting")


def start_vlc_camera():
    """Start camera in VLC streaming mode - direct H.264 output"""
    global current_camera_process, camera_running
    
    logger.info("Starting camera in VLC streaming mode")
    
    rotation = int(settings.get('rotation', 0))
    
    # Build rpicam-vid command for TCP streaming (no transcoding)
    cmd = [
        'rpicam-vid',
        '--nopreview',
        '--codec', 'h264',
        '--width', str(settings['width']),
        '--height', str(settings['height']),
        '--framerate', str(settings['framerate']),
        '--timeout', '0',
        '--brightness', str(settings['brightness']),
        '--contrast', str(settings['contrast']),
        '--saturation', str(settings['saturation']),
        '--sharpness', str(settings['sharpness']),
        '--exposure', settings['exposure'],
        '--metering', settings['metering'],
        '--awb', settings['awb'],
        '--inline',
        '-o', '-'  # Output to stdout
    ]
    
    # Add rotation if not 90/270 (those require transcoding)
    if rotation in (0, 180):
        cmd.extend(['--rotation', str(rotation)])
    
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
    
    # Apply digital zoom (ROI)
    zoom_factor = float(settings.get('zoom', 1.0))
    if zoom_factor > 1.0:
        w = 1.0 / zoom_factor
        h = 1.0 / zoom_factor
        x = (1.0 - w) / 2.0
        y = (1.0 - h) / 2.0
        cmd.extend(['--roi', f"{x},{y},{w},{h}"])
    
    log_file = os.path.join(os.path.dirname(__file__), 'vlc_camera.log')
    fifo_path = os.path.join(os.path.dirname(__file__), 'vlc_stream.fifo')
    
    # Remove old FIFO if exists
    try:
        if os.path.exists(fifo_path):
            os.remove(fifo_path)
    except Exception as e:
        logger.error(f"Failed to remove old FIFO: {e}")
    
    try:
        # Output to stdout (we'll read it directly)
        full_cmd = ' '.join(cmd)
        logger.info(f"VLC camera command: {full_cmd}")
        
        global h264_stderr
        if h264_stderr and not h264_stderr.closed:
            try:
                h264_stderr.close()
            except:
                pass
        
        h264_stderr = open(log_file, 'wb', buffering=0)
        camera_process = subprocess.Popen(
            cmd,
            stdout=subprocess.PIPE,
            stderr=h264_stderr,
            start_new_session=True
        )
        
        time.sleep(1)
        if camera_process.poll() is not None:
            try:
                with open(log_file, 'r') as f:
                    stderr = f.read()
                logger.error(f"VLC camera exited immediately. Error: {stderr}")
            except:
                logger.error("VLC camera exited immediately")
            h264_stderr.close()
            return False
        
        with camera_process_lock:
            current_camera_process = camera_process
            camera_running = True
        
        logger.info("VLC camera started successfully")
        logger.info(f"Stream URL: http://192.168.0.169:5000/stream.h264")
        return True
    except Exception as e:
        logger.error(f"Failed to start VLC camera: {e}")
        return False


def generate_vlc_stream():
    """Generator that yields H.264 stream directly from camera process stdout"""
    global current_camera_process
    
    logger.info("VLC HTTP client connecting...")
    
    try:
        # Get camera process
        with camera_process_lock:
            if not current_camera_process or current_camera_process.poll() is not None:
                logger.error("Camera not running for VLC stream")
                return
            
            process = current_camera_process
        
        # Set stdout to non-blocking mode
        import fcntl
        import os
        flags = fcntl.fcntl(process.stdout, fcntl.F_GETFL)
        fcntl.fcntl(process.stdout, fcntl.F_SETFL, flags | os.O_NONBLOCK)
        
        # Read camera output and stream it
        while True:
            try:
                chunk = process.stdout.read(8192)
                if chunk:
                    yield chunk
                else:
                    # No data available, small sleep to prevent busy-wait
                    time.sleep(0.01)
            except BlockingIOError:
                # No data available yet, small sleep
                time.sleep(0.01)
                continue
            except Exception as e:
                logger.error(f"Error reading camera stream: {e}")
                break
            
            # Check if process is still running
            if process.poll() is not None:
                logger.warning("Camera process ended")
                break
            
    except GeneratorExit:
        logger.info("VLC HTTP client disconnected")
    except Exception as e:
        logger.error(f"VLC stream error: {e}")


def generate_frames():
    """Capture frames using optimized method - try rpicam-vid first, fallback to rpicam-still"""
    global camera_running, current_camera_process

    # Check if camera is already running - only allow one stream at a time
    with camera_process_lock:
        if camera_running:
            logger.warning("Camera already in use by another client")
            # Return error frame
            error_msg = b'Camera in use by another viewer'
            yield (b'--frame\r\n'
                   b'Content-Type: text/plain\r\n\r\n' + error_msg + b'\r\n')
            return
        camera_running = True

    try:
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
    finally:
        # Always reset camera_running flag when stream ends
        with camera_process_lock:
            camera_running = False
        logger.info("Camera stream ended, released camera lock")

@app.route('/')
def index():
    """Landing page - choose between web UI or VLC streaming"""
    try:
        with open(LANDING_PAGE, 'r') as f:
            return f.read()
    except:
        return '''
        <html><body>
        <h1>picamctl</h1>
        <p><a href="/web">Web Browser Mode</a> - Full camera control with HLS streaming</p>
        <p><a href="/vlc">VLC Streaming Mode</a> - Low latency direct H.264 stream</p>
        </body></html>
        '''

@app.route('/web')
def web_mode():
    """Full web UI with HLS streaming"""
    global streaming_mode
    with streaming_mode_lock:
        if streaming_mode != 'hls':
            # Switch to HLS mode
            stop_camera_process()
            streaming_mode = 'hls'
            threading.Thread(target=start_h264_camera, daemon=True).start()
            time.sleep(2)  # Wait for camera to start
    return render_template_string(get_html())

@app.route('/vlc')
def vlc_mode():
    """VLC streaming page"""
    global streaming_mode
    with streaming_mode_lock:
        if streaming_mode != 'vlc':
            # Switch to VLC mode
            stop_camera_process()
            streaming_mode = 'vlc'
            threading.Thread(target=start_vlc_camera, daemon=True).start()
            time.sleep(2)  # Wait for camera to start
    try:
        with open(VLC_PAGE, 'r') as f:
            return f.read()
    except:
        return '''
        <html><body>
        <h1>VLC Streaming</h1>
        <p>Stream URL: http://''' + request.host + '''/stream.h264</p>
        <p>Open this URL in VLC Media Player (Media → Open Network Stream)</p>
        <p><a href="/">Back to Mode Selection</a></p>
        </body></html>
        '''

@app.route('/hls/<path:filename>')
def serve_hls(filename):
    """Serve HLS playlist and segments"""
    try:
        return send_from_directory(HLS_DIR, filename)
    except Exception as e:
        logger.error(f"Error serving HLS file {filename}: {e}")
        return jsonify({'error': 'File not found'}), 404

@app.route('/video_feed')
def video_feed():
    """Legacy MJPEG endpoint - kept for fallback"""
    return Response(generate_frames(), mimetype='multipart/x-mixed-replace; boundary=frame')

@app.route('/settings')
def get_settings():
    """Get current camera settings"""
    return jsonify(settings)

@app.route('/system_info')
def get_system_info():
    """Get system information for display"""
    global streaming_mode
    import socket
    import shutil
    
    try:
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
        
        # Calculate actual bandwidth from HLS segments
        bandwidth_kbps = calculate_bandwidth()
        
        return jsonify({
            'ip': ip_address,
            'disk': disk_info,
            'bandwidth': bandwidth_kbps,
            'vlc_stream_running': (streaming_mode == 'vlc'),
            'mqtt_connected': mqtt_connected
        })
    except Exception as e:
        logger.error(f"Error in /system_info: {e}")
        return jsonify({'error': str(e)}), 500


@app.route('/api/stop_vlc_mode', methods=['POST'])
def stop_vlc_mode_endpoint():
    """Stop VLC mode and return to landing page"""
    global streaming_mode
    with streaming_mode_lock:
        streaming_mode = 'hls'  # Reset to default
    stop_camera_process()
    return jsonify({'success': True})


@app.route('/stream.h264')
def stream_h264():
    """Direct H.264 stream for VLC (low latency) - only works in VLC mode"""
    if streaming_mode != 'vlc':
        return jsonify({'error': 'VLC mode not active'}), 400
    
    return Response(
        generate_vlc_stream(),
        mimetype='video/h264',
        headers={
            'Cache-Control': 'no-cache, no-store, must-revalidate',
            'Pragma': 'no-cache',
            'Expires': '0'
        }
    )


@app.route('/snapshot', methods=['POST'])
def take_snapshot():
    """Take a high-quality snapshot by temporarily stopping the video stream"""
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

        logger.info(f"Taking snapshot: {filename}")
        
        # Stop the video stream to release camera lock
        logger.info("Stopping video stream for snapshot...")
        stop_camera_process()
        time.sleep(1)  # Wait for camera to be released

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
        logger.info(f"Executing snapshot command: {' '.join(cmd)}")
        result = subprocess.run(cmd, capture_output=True, timeout=10)

        # Restart video stream immediately after snapshot
        if use_hw_acceleration:
            logger.info("Restarting video stream...")
            time.sleep(0.5)
            threading.Thread(target=start_h264_camera, daemon=True).start()

        if result.returncode == 0 and os.path.exists(filepath):
            logger.info(f"Snapshot saved: {filepath}")
            publish_event("snapshot_taken", "info")

            # Return success with filename
            return jsonify({
                'success': True,
                'filename': filename,
                'filepath': filepath,
                'url': f'/snapshots/{filename}',
                'timestamp': timestamp
            })
        else:
            error_msg = result.stderr.decode() if result.stderr else 'Unknown error'
            logger.error(f"Snapshot failed: {error_msg}")
            publish_event("snapshot_failed", "error")
            return jsonify({
                'success': False,
                'error': f'Camera error: {error_msg}'
            }), 500

    except subprocess.TimeoutExpired:
        logger.error("Snapshot timed out")
        if use_hw_acceleration:
            time.sleep(0.5)
            threading.Thread(target=start_h264_camera, daemon=True).start()
        return jsonify({'success': False, 'error': 'Camera timeout'}), 500
    except Exception as e:
        logger.error(f"Snapshot error: {e}")
        if use_hw_acceleration:
            time.sleep(0.5)
            threading.Thread(target=start_h264_camera, daemon=True).start()
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
    global camera_running

    new_settings = request.json
    width = new_settings.get('width', settings['width'])
    height = new_settings.get('height', settings['height'])

    # Validate resolution
    validated_res, warning = validate_resolution(width, height)

    # Update settings with validated resolution
    new_settings['width'] = validated_res['width']
    new_settings['height'] = validated_res['height']
    settings.update(new_settings)
    
    # Save settings to disk immediately after updating
    save_settings()

    # Determine if restart is needed
    # Only restart for settings that require rpicam-vid restart
    restart_required_settings = {
        'width', 'height', 'framerate', 'vflip', 'hflip',
        'rotation', 'exposure', 'denoise', 'hdr', 'zoom'
    }
    
    # Check if any restart-required settings changed
    needs_restart = any(key in new_settings for key in restart_required_settings)
    
    # If MQTT settings changed, reinitialize MQTT
    mqtt_settings = {'mqtt_enabled', 'mqtt_broker', 'mqtt_port', 'mqtt_user', 'mqtt_password', 'mqtt_base_topic'}
    mqtt_changed = any(key in new_settings for key in mqtt_settings)
    if mqtt_changed:
        logger.info("MQTT settings changed - reinitializing MQTT client")
        if mqtt_client:
            mqtt_client.disconnect()
            mqtt_client.loop_stop()
        init_mqtt()

    if needs_restart:
        logger.info(f"Camera restart required for settings: {list(set(new_settings.keys()) & restart_required_settings)}")
        stop_camera_process()
        with camera_process_lock:
            camera_running = False
        # Start new stream in background
        threading.Thread(target=start_stream, daemon=True).start()
    # Publish settings change event if any changes were made
    if new_settings:
        publish_event("settings_changed", "info")

    else:
        logger.info(f"No restart needed for settings: {list(new_settings.keys())}")
        # Settings are already saved above

    response = {'status': 'ok', 'resolution': f"{validated_res['width']}x{validated_res['height']}"}
    if warning:
        response['warning'] = warning
        logger.warning(f"Resolution warning: {warning}")

    return jsonify(response)

@app.route('/reset', methods=['POST'])
def reset_settings():
    """Reset all settings to defaults"""
    global camera_running

    # Reset to default settings
    default_settings = {
        'camera_name': 'Garage Cam',
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
        'ev': 0,
        'shutter': 0,
        'gain': 0,
        'denoise': 'auto',
        'hdr': 'off',
        'quality': 93,
        'snapshot_quality': 100,
        'zoom': 1.0
    }

    # Update runtime settings
    settings.update(default_settings)

    # Stop camera and reset flag
    stop_camera_process()
    with camera_process_lock:
        camera_running = False

    # Save to disk
    save_settings()

    logger.info("Camera settings reset to defaults")
    return jsonify({'status': 'ok', 'message': 'Settings reset to defaults'})

@app.route('/restart_service', methods=['POST'])
def restart_service():
    """Restart the camera service"""
    global camera_running
    
    try:
        logger.info("Restarting camera service...")
        
        # Stop the current stream
        stop_camera_process()
        with camera_process_lock:
            camera_running = False
        
        # Wait a moment for cleanup
        time.sleep(1)
        
        # Restart the stream
        if use_hw_acceleration:
            threading.Thread(target=start_h264_camera, daemon=True).start()
        
        logger.info("Camera service restart initiated")
        return jsonify({'status': 'ok', 'message': 'Camera service restarting'})
    except Exception as e:
        logger.error(f"Error restarting camera service: {e}")
        return jsonify({'status': 'error', 'error': str(e)}), 500

if __name__ == '__main__':
    # Load saved settings on startup
    load_settings()

    # Start H.264 camera if using hardware acceleration
    if use_hw_acceleration:
        logger.info("Starting H.264 hardware-accelerated camera...")
        # Start the combined rpicam | ffmpeg pipeline
        threading.Thread(target=start_h264_camera, daemon=True).start()
        time.sleep(1)  # Give camera time to initialize

    logger.info("Starting picamctl interface...")
    logger.info("Access at: http://<your-pi-ip>:5000 (replace with your host IP)")
    logger.info(f"Hardware acceleration: {'enabled (H.264)' if use_hw_acceleration else 'disabled (MJPEG)'}")

    # MQTT globals
mqtt_client = None
mqtt_connected = False
mqtt_reconnect_interval = 5  # seconds
mqtt_last_reconnect = 0

# Publishing intervals
MQTT_STATUS_INTERVAL = 30  # seconds
MQTT_METRICS_INTERVAL = 60  # seconds
last_status_publish = 0
last_metrics_publish = 0

# App start time for uptime
app_start_time = time.time()

def on_mqtt_connect(client, userdata, flags, rc):
    global mqtt_connected
    if rc == 0:
        mqtt_connected = True
        logger.info("MQTT connected successfully")
        publish_event("device_boot", "info")
    else:
        mqtt_connected = False
        logger.error(f"MQTT connection failed with code {rc}")

def on_mqtt_disconnect(client, userdata, rc):
    global mqtt_connected
    mqtt_connected = False
    logger.warning(f"MQTT disconnected (code {rc}), will attempt reconnect")

def init_mqtt():
    global mqtt_client
    if not settings.get('mqtt_enabled', False):
        logger.info("MQTT disabled in settings")
        return

    mqtt_client = mqtt.Client(client_id=settings['camera_name'])
    mqtt_client.on_connect = on_mqtt_connect
    mqtt_client.on_disconnect = on_mqtt_disconnect

    if settings['mqtt_user']:
        mqtt_client.username_pw_set(settings['mqtt_user'], settings['mqtt_password'])

    try:
        mqtt_client.connect(settings['mqtt_broker'], settings['mqtt_port'], keepalive=60)
        mqtt_client.loop_start()
        logger.info("MQTT client initialized")
    except Exception as e:
        logger.error(f"Failed to initialize MQTT: {e}")

def reconnect_mqtt():
    global mqtt_last_reconnect
    current_time = time.time()
    if current_time - mqtt_last_reconnect >= mqtt_reconnect_interval:
        logger.info("Attempting MQTT reconnect...")
        try:
            mqtt_client.reconnect()
            mqtt_last_reconnect = current_time
        except Exception as e:
            logger.error(f"MQTT reconnect failed: {e}")

# In main - after load_settings()
init_mqtt()

# Add background thread for reconnection handling
def mqtt_monitor():
    while True:
        if settings.get('mqtt_enabled', False) and not mqtt_connected:
            reconnect_mqtt()
        time.sleep(1)

threading.Thread(target=mqtt_monitor, daemon=True).start()

def get_uptime():
    """Get system uptime in seconds"""
    with open('/proc/uptime', 'r') as f:
        return float(f.readline().split()[0])

def format_uptime(seconds):
    """Format uptime as human-readable string"""
    days = int(seconds // 86400)
    hours = int((seconds % 86400) // 3600)
    minutes = int((seconds % 3600) // 60)
    secs = int(seconds % 60)
    return f"{days}d {hours}h {minutes}m {secs}s"

def get_topic(suffix):
    """Build device-specific topic"""
    return f"{settings['mqtt_base_topic']}/{settings['camera_name']}/{suffix}"

def publish_mqtt(topic, payload, retain=False):
    """Publish to MQTT if connected"""
    if mqtt_client and mqtt_connected:
        try:
            result = mqtt_client.publish(topic, json.dumps(payload), retain=retain)
            if result.rc != mqtt.MQTT_ERR_SUCCESS:
                logger.warning(f"Failed to publish to {topic}")
        except Exception as e:
            logger.error(f"Publish error: {e}")

def publish_status():
    """Publish camera status"""
    uptime_secs = int(get_uptime())
    
    # Get IP address for status
    import socket
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.connect(("8.8.8.8", 80))
        ip_address = s.getsockname()[0]
        s.close()
    except:
        ip_address = "unknown"
    
    payload = {
        "device": settings['camera_name'],
        "uptime_seconds": uptime_secs,
        "uptime": format_uptime(uptime_secs),
        "resolution": f"{settings['width']}x{settings['height']}",
        "framerate": settings['framerate'],
        "camera_ready": camera_running,
        "ip": ip_address,
        "timestamp": int(time.time())
    }
    publish_mqtt(get_topic("status"), payload, retain=True)

def publish_metrics():
    """Publish camera metrics"""
    bandwidth_kbps = calculate_bandwidth()
    
    # Get system memory info
    try:
        import psutil
        mem = psutil.virtual_memory()
        free_heap = mem.available
    except:
        free_heap = 0
    
    payload = {
        "device": settings['camera_name'],
        "location": "surveillance",
        "timestamp": int(time.time()),
        "uptime_seconds": int(get_uptime()),
        "free_heap": free_heap,
        "camera_ready": 1 if camera_running else 0,
        "mqtt_connected": 1 if mqtt_connected else 0,
        "bandwidth_kbps": round(bandwidth_kbps, 2)
    }
    publish_mqtt(get_topic("metrics"), payload, retain=True)

def publish_event(event_type, severity):
    """Publish event"""
    payload = {
        "event": event_type,
        "severity": severity,
        "timestamp": int(time.time())
    }
    publish_mqtt(get_topic("events"), payload)

# Background publishing thread
def mqtt_publisher():
    global last_status_publish, last_metrics_publish
    while True:
        current_time = time.time()
        if settings.get('mqtt_enabled', False) and mqtt_connected:
            if current_time - last_status_publish >= MQTT_STATUS_INTERVAL:
                publish_status()
                last_status_publish = current_time
            if current_time - last_metrics_publish >= MQTT_METRICS_INTERVAL:
                publish_metrics()
                last_metrics_publish = current_time
        time.sleep(1)

threading.Thread(target=mqtt_publisher, daemon=True).start()

@app.errorhandler(404)
def not_found(error):
    return jsonify({'error': 'Not found'}), 404

@app.errorhandler(500)
def internal_error(error):
    return jsonify({'error': 'Internal server error'}), 500

app.run(host='0.0.0.0', port=5000, threaded=True)
