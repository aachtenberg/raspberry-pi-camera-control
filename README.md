# Raspberry Pi Camera Control with H.264 HLS

A web-based camera control interface for Raspberry Pi Camera 3 with hardware-accelerated H.264 streaming.

## Features

✅ **H.264 Hardware Acceleration** - Uses rpicam-vid with hardware H.264 encoding  
✅ **HLS Streaming** - Low-latency HTTP Live Streaming via ffmpeg  
✅ **Web Interface** - Modern HTML5 video player with HLS.js  
✅ **Camera Controls** - Full control over resolution, framerate, exposure, white balance, etc.  
✅ **Systemd Service** - Runs reliably as a background service  
✅ **No Zombie Processes** - Proper subprocess management prevents defunct processes  

## Recent Changes ✅
- Snapshot fixes: snapshots now temporarily pause the stream, capture with `rpicam-still`, then automatically restart; snapshot auto-download works in the UI. 📸
- Reboot implemented: **Reboot Device** button now restarts the camera service and shows a full-screen "Rebooting..." overlay. 🔁
- UI & UX improvements: play/pause fixes (resume after Stop), snapshot button preserves icon while disabled, timestamp moved to bottom-left. 🎛️
- Resolution guidance: HD modes restored (1080p/720p) with a recommendation to use lower resolutions on Pi Zero 2 W for stability. ⚠️


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

## Secret scanning / Pre-commit hooks 🔒
We use `pre-commit` + `detect-secrets` to prevent accidental commits of secrets.

Quick setup for developers:

```bash
# Install tools (do this in your dev environment)
python3 -m pip install --user pre-commit detect-secrets

# Generate baseline (only needed once, review and commit output):
detect-secrets scan > .secrets.baseline

# Install git hooks
pre-commit install
```

The repository includes `.pre-commit-config.yaml` and a `.secrets.baseline` file. If you add a new secret intentionally (e.g. CI helper key), add it to the baseline after review using `detect-secrets audit`.

CI: A GitHub Actions workflow runs `detect-secrets` on pushes and pull requests and will fail the check if new potential secrets are detected that are not present in `.secrets.baseline`.


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
- **Resolution**: 1920x1080 (1080p), 1280x720 (720p), 640x480 (VGA), 320x240 (QVGA). Note: higher resolutions may be unstable on Pi Zero 2 W — use lower resolutions for reliability.
- **Framerate**: 3-120 fps (higher framerates available at lower resolutions). For Pi Zero 2 W we recommend **5–15 fps** for stable streaming.
- **Snapshot**: Captures high-quality stills by pausing the stream, then auto-downloads the JPEG. (Exclusive camera access is required.)
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
