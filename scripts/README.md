# Scripts Directory

Helper scripts for managing the picamctl camera control system.

## Available Scripts

### check_dependencies.sh
Checks and installs required dependencies on the Raspberry Pi.

**Usage:**
```bash
export PI_USER=aachten
export PI_HOST=pizero2
./scripts/check_dependencies.sh
```

**Checks for:**
- ffmpeg (video transcoding)
- rpicam-vid (Raspberry Pi camera tool)
- Python3
- pip3 (Python package manager)
- Flask (Python web framework)

### deploy_to_pi.sh
Deploys the picamctl application to the Raspberry Pi.

**Usage:**
```bash
export PI_USER=aachten
export PI_HOST=pizero2
./scripts/deploy_to_pi.sh
```

**Actions:**
- Copies Python script, templates, and config files
- Installs systemd service
- Restarts the service
- Shows deployment status

### manage_service.sh
Local script for managing the picamctl systemd service on the Pi.

**Usage (on the Pi):**
```bash
./manage_service.sh [start|stop|restart|status|enable|disable]
```

### sanitize_personal_info.py
Removes sensitive information from files before committing to git.

**Usage:**
```bash
python3 scripts/sanitize_personal_info.py
```

## Environment Variables

Both `check_dependencies.sh` and `deploy_to_pi.sh` use these environment variables:

- `PI_USER` - SSH username for the Raspberry Pi (default: `pi`)
- `PI_HOST` - Hostname or IP address of the Raspberry Pi

**Set them before running scripts:**
```bash
export PI_USER=aachten
export PI_HOST=192.168.0.169  # or hostname like pizero2
```
