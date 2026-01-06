# Raspberry Pi Camera Control with H.264 HLS

A web-based camera control interface for Raspberry Pi Camera 3 with hardware-accelerated H.264 streaming.

## Features

✅ **H.264 Hardware Acceleration** - Uses rpicam-vid with hardware H.264 encoding  
✅ **HLS Streaming** - Low-latency HTTP Live Streaming via ffmpeg  
✅ **Web Interface** - Modern HTML5 video player with HLS.js  
✅ **Camera Controls** - Full control over resolution, framerate, exposure, white balance, etc.  
✅ **Systemd Service** - Runs reliably as a background service  
✅ **No Zombie Processes** - Proper subprocess management prevents defunct processes  

## Architecture

```
┌─────────────────┐
│  rpicam-vid     │  Hardware H.264 encoding
│  (Pi Camera 3)  │  640x480 @ 10fps
└────────┬────────┘
         │ TCP stream (tcp://0.0.0.0:8888)
         ▼
┌─────────────────┐
│     ffmpeg      │  Convert H.264 → HLS segments
│  HLS Converter  │  2-second segments, rolling window
└────────┬────────┘
         │ HLS files (stream.m3u8 + segments)
         ▼
┌─────────────────┐
│  Flask Server   │  Serve web UI and HLS stream
│   Port 5000     │  http://192.168.0.169:5000
└────────┬────────┘
         │
         ▼
┌─────────────────┐
│   Web Browser   │  HLS.js video player
│  (Any device)   │  HTML5 <video> element
└─────────────────┘
```

## Quick Start

### 1. Check Dependencies
```bash
./check_dependencies.sh
```

This checks and installs:
- `ffmpeg` - HLS converter
- `rpicam-vid` - Camera control
- `flask` - Web server

### 2. Deploy to Pi
```bash
./deploy_to_pi.sh
```

This will:
- Copy all files to `/home/aachten/camera_control/`
- Install/update the systemd service
- Restart the camera-control service
- Show service status

### 3. Access Web Interface
Open in your browser:
```
http://192.168.0.169:5000
```

## Service Management

```bash
# Check status
sudo systemctl status camera-control

# View logs
sudo journalctl -u camera-control -f

# Restart
sudo systemctl restart camera-control

# Stop
sudo systemctl stop camera-control

# Start
sudo systemctl start camera-control
```

## Files

- `camera_control.py` - Main Flask application with H.264 streaming
- `garage_cam_template.html` - Web UI with HLS.js player
- `camera_settings.json` - Saved camera settings
- `camera-control.service` - Systemd service file
- `manage_service.sh` - Service management helper
- `deploy_to_pi.sh` - Deployment script
- `check_dependencies.sh` - Dependency checker

## How H.264 HLS Works

### Problem with Previous Approach
- Using `PIPE` for stdout/stderr caused zombie (defunct) processes
- libav HLS encoding was unreliable in systemd context

### Solution
1. **rpicam-vid** with TCP output:
   - Uses `--codec h264` for hardware encoding
   - Outputs to `tcp://0.0.0.0:8888`
   - Uses `DEVNULL` for stdout (no blocking)
   - Logs stderr to file

2. **ffmpeg** as HLS converter:
   - Connects to TCP stream from rpicam-vid
   - Copies H.264 (no re-encoding)
   - Generates HLS segments in `/hls_segments/`
   - Auto-deletes old segments (keeps last 10)

3. **Flask** serves HLS files:
   - `/hls/stream.m3u8` - HLS playlist
   - `/hls/segment_XXX.ts` - Video segments

4. **HLS.js** player in browser:
   - Plays HLS in any browser
   - Adaptive bitrate support
   - Auto-reconnect on errors

## Camera Settings

Adjust via web interface:
- **Resolution**: 640x480, 1280x720, 1920x1080
- **Framerate**: 10-30 fps
- **Brightness**: -1.0 to 1.0
- **Contrast**: 0 to 2.0
- **Saturation**: 0 to 2.0
- **Exposure**: Normal, Sport
- **White Balance**: Auto, Daylight, Cloudy, etc.
- **Flip**: Horizontal/Vertical
- **Rotation**: 0°, 90°, 180°, 270°

## Performance on Pi Zero 2 W

Tested configuration:
- **Hardware**: Pi Zero 2 W (512MB RAM, 4 cores @ 1GHz)
- **Resolution**: 640x480
- **Framerate**: 10 fps
- **Codec**: H.264 (hardware accelerated)
- **CPU Usage**: ~12-15% per process (rpicam-vid + ffmpeg)
- **Memory**: ~50-60MB per process

## Troubleshooting

### No video in browser
1. Check if HLS segments are being created:
   ```bash
   ssh aachten@192.168.0.169 'ls -lh /home/aachten/camera_control/hls_segments/'
   ```

2. Check if processes are running:
   ```bash
   ssh aachten@192.168.0.169 'ps aux | grep -E "(rpicam-vid|ffmpeg)"'
   ```

3. Check service logs:
   ```bash
   ssh aachten@192.168.0.169 'sudo journalctl -u camera-control -f'
   ```

### Zombie processes
Fixed! The new implementation uses:
- `stdout=subprocess.DEVNULL` instead of `PIPE`
- `start_new_session=True` to detach from parent
- Proper process cleanup in stop function

### Stream lag
- Lower resolution (640x480)
- Reduce framerate (10 fps)
- Adjust HLS segment duration in `run_ffmpeg_hls_converter()`

## Credits

Built for Pi Zero 2 W with Camera 3
Hardware H.264 encoding for efficiency
HLS streaming for compatibility

## License

MIT
