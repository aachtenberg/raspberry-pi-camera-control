"""
Stream pipeline tests.

These run the real app and the real ffmpeg HLS stage against a fake camera
(tests/fakes/rpicam-vid), so they need no Raspberry Pi. They cover what the UI
tests cannot see: segment length, bitrate, and the on-demand start/stop cycle.

Requires ffmpeg with libx264 on PATH. The tests share one app instance and run
in file order; each builds on the state the previous one left.

    pytest -v tests/test_stream.py
"""
import json
import os
import re
import shutil
import signal
import subprocess
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parent.parent
FAKES = Path(__file__).resolve().parent / 'fakes'
PORT = int(os.environ.get('STREAM_TEST_PORT', '5057'))
BASE = f'http://127.0.0.1:{PORT}'

FRAMERATE = 10
IDLE_TIMEOUT = 15  # seconds; the app's minimum

if shutil.which('ffmpeg') is None:
    if os.environ.get('CI'):
        raise RuntimeError('ffmpeg is required for the stream tests')
    pytestmark = pytest.mark.skip(reason='ffmpeg is required for the stream tests')


# --------------------------------------------------------------------------
# Helpers
# --------------------------------------------------------------------------

def http(path, data=None, timeout=10):
    """GET, or POST JSON when data is given. Returns (status, body bytes)."""
    request = urllib.request.Request(
        BASE + path,
        data=json.dumps(data).encode() if data is not None else None,
        headers={'Content-Type': 'application/json'},
        method='POST' if data is not None else 'GET',
    )
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            return response.status, response.read()
    except urllib.error.HTTPError as error:
        return error.code, error.read()
    except Exception as error:  # connection refused, timeout
        return 0, str(error).encode()


def info():
    status, body = http('/system_info')
    return json.loads(body) if status == 200 else {}


def state():
    """Camera state. /system_info does not count as a viewer, so polling it is safe."""
    return info().get('camera_state')


def playlist():
    """Fetch the playlist the way a player does. This counts as a viewer."""
    status, body = http('/hls/stream.m3u8')
    return status, body.decode(errors='replace')


def segment_names(text):
    return [line for line in text.splitlines() if line.endswith('.ts')]


def segment_durations(text):
    return [float(value) for value in re.findall(r'#EXTINF:([0-9.]+)', text)]


def wait_for(check, timeout, what, interval=0.5):
    """Poll check() until it returns something truthy; fail with a clear message otherwise."""
    deadline = time.time() + timeout
    while time.time() < deadline:
        result = check()
        if result:
            return result
        time.sleep(interval)
    raise AssertionError(f'Timed out after {timeout}s waiting for {what} (camera state: {state()})')


def playlist_with(min_segments):
    """Return the playlist text once it lists at least min_segments segments."""
    status, text = playlist()
    return text if status == 200 and len(segment_names(text)) >= min_segments else None


def option(args, name):
    return args[args.index(name) + 1] if name in args else None


class App:
    def __init__(self, workdir):
        self.workdir = workdir
        self.camera_log = workdir / 'fake_camera.log'
        self.hls_dir = workdir / 'hls_segments'
        self.first_run_segments = set()

    def camera_calls(self, program='rpicam-vid'):
        """Argument lists of every stream the app asked the fake camera for."""
        if not self.camera_log.exists():
            return []
        calls = [json.loads(line) for line in self.camera_log.read_text().splitlines() if line.strip()]
        return [call[1:] for call in calls if call[0] == program and '--list-cameras' not in call]

    def hls_files(self):
        return sorted(p.name for p in self.hls_dir.glob('*')) if self.hls_dir.exists() else []

    def average_segment_bytes(self, text):
        """Average size of the complete segments listed in a playlist."""
        sizes = [(self.hls_dir / name).stat().st_size for name in segment_names(text)[:-1]
                 if (self.hls_dir / name).exists()]
        assert sizes, 'no complete segments on disk'
        return sum(sizes) / len(sizes)

    def camera_processes(self):
        result = subprocess.run(['pgrep', '-f', str(FAKES / 'rpicam-vid')], capture_output=True, text=True)
        return result.stdout.split()


@pytest.fixture(scope='module')
def app(tmp_path_factory):
    workdir = Path(os.environ.get('STREAM_TEST_WORKDIR') or tmp_path_factory.mktemp('picamctl'))
    workdir.mkdir(parents=True, exist_ok=True)
    shutil.copy(REPO / 'picamctl.py', workdir)
    for folder in ('templates', 'static'):
        shutil.copytree(REPO / folder, workdir / folder, dirs_exist_ok=True)
    (workdir / 'picamctl_settings.json').write_text(json.dumps({
        'width': 640, 'height': 480, 'framerate': FRAMERATE,
        'on_demand': True, 'idle_timeout': IDLE_TIMEOUT, 'bitrate': 0,
        'mqtt_enabled': False,
    }))

    env = dict(os.environ)
    env['PATH'] = f"{FAKES}{os.pathsep}{env['PATH']}"
    env['FAKE_CAMERA_LOG'] = str(workdir / 'fake_camera.log')
    env['PICAMCTL_PORT'] = str(PORT)

    log = open(workdir / 'app.log', 'wb')
    process = subprocess.Popen([sys.executable, 'picamctl.py'], cwd=workdir, env=env,
                               stdout=log, stderr=subprocess.STDOUT, start_new_session=True)
    try:
        wait_for(lambda: http('/system_info')[0] == 200, 30, 'the app to start')
        yield App(workdir)
    finally:
        try:
            os.killpg(process.pid, signal.SIGTERM)
        except ProcessLookupError:
            pass
        # Camera pipelines run in their own sessions, so stop them separately
        subprocess.run(['pkill', '-f', str(FAKES / 'rpicam-vid')])
        subprocess.run(['pkill', '-f', str(workdir / 'hls_segments')])
        log.close()


# --------------------------------------------------------------------------
# Tests (in order)
# --------------------------------------------------------------------------

def test_boots_into_standby_without_starting_the_camera(app):
    assert state() == 'standby'
    assert info()['on_demand'] is True
    assert app.camera_calls() == [], 'the camera must not start before anyone watches'
    assert app.hls_files() == []


def test_first_request_starts_the_camera(app):
    status, _ = playlist()
    assert status == 503, 'an idle camera must answer "starting", not serve a playlist'
    wait_for(lambda: playlist()[0] == 200, 20, 'the playlist to appear')
    assert state() == 'streaming'
    assert len(app.camera_calls()) == 1


def test_encoder_is_asked_for_one_keyframe_per_second_and_a_bitrate(app):
    args = app.camera_calls()[-1]
    assert option(args, '--intra') == str(FRAMERATE)
    assert option(args, '--bitrate') == '1500000', 'automatic bitrate below 720p'
    assert '--inline' in args


def test_segments_are_one_second_long(app):
    text = wait_for(lambda: playlist_with(4), 20, 'four segments')
    durations = segment_durations(text)
    assert all(0.9 <= d <= 1.1 for d in durations), f'segment durations: {durations}'
    assert '#EXT-X-TARGETDURATION:1' in text

    status, body = http('/hls/' + segment_names(text)[-2])
    assert status == 200 and len(body) > 1000

    app.first_run_segments = set(segment_names(text))
    app.first_run_bytes = app.average_segment_bytes(text)


def test_bitrate_setting_restarts_the_stream_at_the_new_rate(app):
    status, _ = http('/apply', {'bitrate': 400000})
    assert status == 200

    def restarted():
        calls = app.camera_calls()
        text = playlist_with(4)  # keep watching, like an open page
        return text if text and option(calls[-1], '--bitrate') == '400000' else None

    text = wait_for(restarted, 40, 'the stream to restart at 400 kbit/s')
    assert info()['bitrate'] == 400000
    assert not set(segment_names(text)) & app.first_run_segments, 'segment names must not repeat after a restart'
    assert app.average_segment_bytes(text) < app.first_run_bytes * 0.6, 'segments should be much smaller'


def test_camera_stops_when_nobody_is_watching(app):
    playlist()  # last viewer request
    started = time.time()
    wait_for(lambda: state() == 'standby', IDLE_TIMEOUT + 20, 'the camera to stop', interval=1)
    assert time.time() - started >= IDLE_TIMEOUT - 2, 'stopped while a viewer had only just left'
    assert app.hls_files() == [], 'old segments must be removed so they are never served'
    wait_for(lambda: not app.camera_processes(), 5, 'the camera process to exit')


def test_idle_camera_restarts_on_the_next_request(app):
    status, _ = playlist()
    assert status == 503, 'a stale playlist must not be served while the camera is stopped'
    wait_for(lambda: playlist()[0] == 200, 20, 'the playlist to reappear')
    assert state() == 'streaming'


def test_snapshot_while_watching_resumes_the_stream(app):
    playlist()  # a viewer is present
    streams_before = len(app.camera_calls())
    status, body = http('/snapshot', {}, timeout=40)
    assert status == 200 and json.loads(body)['success']

    wait_for(lambda: playlist()[0] == 200, 25, 'the stream to resume after the snapshot')
    assert state() == 'streaming'
    assert len(app.camera_calls()) == streams_before + 1


def test_continuous_mode_keeps_running_without_viewers(app):
    assert http('/apply', {'on_demand': False})[0] == 200
    wait_for(lambda: state() == 'streaming', 15, 'continuous mode to be streaming')
    time.sleep(IDLE_TIMEOUT + 8)
    assert state() == 'streaming', 'continuous mode must not stop when idle'

    assert http('/apply', {'on_demand': True})[0] == 200
    wait_for(lambda: state() == 'standby', 15, 'on-demand mode to stop the idle camera', interval=1)


def test_snapshot_from_standby_leaves_the_camera_stopped(app):
    assert state() == 'standby'
    streams_before = len(app.camera_calls())
    status, body = http('/snapshot', {}, timeout=40)
    result = json.loads(body)
    assert status == 200 and result['success'], result

    status, image = http(result['url'])
    assert status == 200 and image[:2] == b'\xff\xd8', 'snapshot should be a JPEG'

    time.sleep(4)  # long enough for a restart to have begun
    assert state() == 'standby'
    assert len(app.camera_calls()) == streams_before, 'no stream should start when nobody is watching'


def test_settings_change_in_standby_does_not_start_the_camera(app):
    streams_before = len(app.camera_calls())
    assert http('/apply', {'framerate': FRAMERATE})[0] == 200  # a restart-required setting

    time.sleep(6)  # the restart path waits 2 seconds before starting
    assert state() == 'standby'
    assert len(app.camera_calls()) == streams_before, 'no stream should start when nobody is watching'


def test_vlc_mode_and_back_to_the_web_stream(app):
    assert http('/vlc', timeout=20)[0] == 200
    wait_for(lambda: info().get('vlc_stream_running'), 10, 'VLC mode to start')
    assert option(app.camera_calls()[-1], '--bitrate') == '400000'

    received = 0
    with urllib.request.urlopen(BASE + '/stream.h264', timeout=10) as stream:
        deadline = time.time() + 10
        while received < 20000 and time.time() < deadline:
            received += len(stream.read(4096))
    assert received >= 20000, f'only {received} bytes from the direct stream'

    assert http('/api/stop_vlc_mode', {})[0] == 200
    assert info()['vlc_stream_running'] is False
    wait_for(lambda: playlist()[0] == 200, 20, 'the web stream to come back after VLC mode')
    assert state() == 'streaming'
