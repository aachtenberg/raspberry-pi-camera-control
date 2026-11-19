# GitHub Copilot Instructions - Raspberry Pi Camera Control

## Project Context

This is a Raspberry Pi camera control system with web interface and MQTT integration. The system runs on low-resource devices like Raspberry Pi Zero 2 W.

## Critical Technical Details

### Deployment

- **Always use the deployment script**: `PI_USER=aachten PI_HOST=pizero1 ./scripts/deploy_to_pi.sh`
- **Never** manually copy files with `scp` - the script handles dependencies, service restart, and configuration
- The script preserves local settings files on the Pi (doesn't overwrite `picamctl_settings.json`)
- User on Pi Zero: `aachten` (not `pi`)
- Remote directory: `/home/aachten/picamctl/`

### MQTT Configuration

- **Library**: paho-mqtt v2.1.0 (as of 2026-01)
- **API Version**: paho-mqtt 2.x requires `callback_api_version=mqtt.CallbackAPIVersion.VERSION1` when creating client
- **Current broker**: 192.168.0.167:1883 (configured in `/home/aachten/picamctl/picamctl_settings.json` on Pi)
- **Connection check**: Use `nc -zv <broker_ip> 1883` to verify broker is reachable
- **Reconnect logic**: Must handle case where `mqtt_client` is `None` (failed initialization)

### Important Code Patterns

#### MQTT Client Initialization (paho-mqtt v2.x)
```python
mqtt_client = mqtt.Client(
    callback_api_version=mqtt.CallbackAPIVersion.VERSION1,
    client_id=settings['camera_name']
)
```

#### Reconnect Function Must Handle None Client
```python
def reconnect_mqtt():
    if mqtt_client is None:
        init_mqtt()  # Full re-init if never connected
    else:
        mqtt_client.reconnect()
```

### Hardware & Resource Constraints

- **Target device**: Raspberry Pi Zero 2 W (limited CPU/memory)
- **Camera**: Uses `rpicam-vid` (modern libcamera) not legacy `raspivid`
- **Streaming**: `rpicam-vid` hardware H.264 piped into ffmpeg, which writes 1-second HLS segments (stream copy, no re-encode)
- **Resolution**: Default 1280x720 (configurable, but don't exceed hardware limits)

### Streaming Behaviour

- **On-demand is the default**: the camera starts when a viewer requests `/hls/stream.m3u8` (or opens `/web`) and stops after `idle_timeout` seconds (default 60) without stream requests. No camera processes and no segments while idle is normal. `on_demand: false` gives continuous streaming.
- **State**: `/system_info` returns `camera_state` (`streaming`, `starting`, `standby`, `error`, `stopped`). MQTT status carries the same field; `camera_ready` stays true in standby.
- **Segment length depends on keyframes**: `--intra` is set to the framerate so there is one keyframe per second. Without it the encoder uses 60 frames and segments become 4-6 seconds, which adds 10+ seconds of delay in the player.
- **Bitrate**: `--bitrate` is always passed; `bitrate: 0` means automatic by resolution (3 Mbit/s at 720p, 5 Mbit/s at 1080p).
- **Restarting the stream**: use `resume_camera()` after an interruption (snapshot, settings change). It leaves the camera stopped when on-demand mode has no viewer. Use `ensure_camera_running()` for viewer requests.

### Debugging MQTT Issues

1. Check if service is running: `ssh pizero1 "sudo systemctl status picamctl"`
2. View logs: `ssh pizero1 "journalctl -u picamctl -f"`
3. Filter MQTT logs: `ssh pizero1 "journalctl -u picamctl -n 50 --no-pager | grep -i mqtt"`
4. Check broker reachability: `ssh pizero1 "nc -zv 192.168.0.167 1883"`
5. Verify paho-mqtt version: `ssh pizero1 "pip3 show paho-mqtt | grep Version"`

### Service Management

- **Restart service**: `ssh pizero1 "sudo systemctl restart picamctl"`
- **View status**: `ssh pizero1 "sudo systemctl status picamctl"`
- **Enable on boot**: `ssh pizero1 "sudo systemctl enable picamctl"`

### Settings File Location

- **On Pi**: `/home/aachten/picamctl/picamctl_settings.json`
- **In repo**: none. The file is gitignored; defaults live in the `settings` dict in `picamctl.py`
- The deployment script **does not overwrite** the Pi's local settings

### Common Issues & Solutions

#### MQTT Not Connecting

**Symptoms**: Logs show "Attempting MQTT reconnect..." repeatedly with no success

**Causes**:
1. paho-mqtt v2.x API incompatibility (missing `callback_api_version`)
2. Broker not running or unreachable
3. `mqtt_client` is `None` and reconnect logic doesn't handle it

**Solutions**:
1. Update `mqtt.Client()` call to include `callback_api_version=mqtt.CallbackAPIVersion.VERSION1`
2. Check broker: `nc -zv <broker_ip> 1883`
3. Add `if mqtt_client is None: init_mqtt()` to reconnect function

#### No Video

- In on-demand mode the camera is off until someone watches. Check `curl http://pizero1:5000/system_info` for `camera_state` before assuming a fault
- `error` means the last start failed: see `/home/aachten/picamctl/camera.log`
- A stream that stalls with a strong Wi-Fi signal: time a segment download; a 1-second segment must download in under a second

#### Service Won't Start

- Check logs: `journalctl -u picamctl -n 50`
- Verify Python dependencies: `pip3 list | grep -E 'flask|paho-mqtt'`
- Check camera access: `rpicam-hello --list-cameras`

## Development Workflow

1. Make changes on a branch
2. Run the stream tests (no Pi needed, uses the fake camera in `tests/fakes/`): `pytest -v tests/test_stream.py`
3. Run the lint checks listed in the README Testing section
4. Open a pull request. Lint and Detect Secrets run on every PR; Stream Tests and UI Tests run when the app, templates or tests change. All that run must pass. The agent review comments on the PR: reply there saying how each finding was addressed
5. Deploy with script: `PI_USER=aachten PI_HOST=pizero1 ./scripts/deploy_to_pi.sh`
6. Monitor logs: `ssh pizero1 "journalctl -u picamctl -f"`
7. Verify functionality via web UI: `http://pizero1:5000`

## Testing MQTT

```bash
# Subscribe to topics (on broker host or any machine with mosquitto-clients)
mosquitto_sub -h 192.168.0.167 -t "surveillance/#" -v

# Should see messages like:
# surveillance/Kitchen/status {"device":"Kitchen","uptime_seconds":...}
# surveillance/Kitchen/metrics {"device":"Kitchen","mqtt_connected":1,...}
```

## File Structure

```
raspberry-pi-camera-control/
├── picamctl.py              # Main application
├── templates/               # HTML templates
│   ├── garage_cam_template.html
│   ├── landing.html
│   └── vlc_stream.html
├── scripts/
│   ├── deploy_to_pi.sh      # ⭐ Primary deployment tool
│   ├── manage_service.sh
│   └── start_camera.sh
├── systemd/
│   └── picamctl.service     # systemd service definition
├── tests/
│   ├── test_stream.py       # Stream pipeline tests (fake camera, real ffmpeg)
│   ├── test_ui.py           # Playwright UI tests
│   └── fakes/               # Stand-ins for rpicam-vid / rpicam-still
└── requirements.txt
```

## Remember

- **Always deploy with the script** - it handles everything correctly
- **Check MQTT broker is running** before investigating client issues
- **paho-mqtt v2.x requires new API** - don't forget `callback_api_version`
- **Pi Zero is resource-limited** - optimize for low CPU/memory usage
- **User is `aachten`** not `pi` on this system
