# Changelog

All notable changes to this project will be documented in this file.

## [Unreleased]
- Fix: at 12 fps the second segment after every camera start was 2 seconds long (ffmpeg skipped a cut on timestamp rounding), slowing the start. The segment target is now 0.9s so every keyframe starts a segment; the stream tests run at 12 fps to cover it.
- CI: the Detect Secrets workflow compared files in a way that could never fail. It now scans every tracked file against `.secrets.baseline`.
- Removed the unused `run_ffmpeg_hls_converter()` (the old TCP hand-off).
- Docs: README and Copilot instructions brought in line with the current pipeline (pipe instead of TCP, 1s segments, on-demand, bitrate, test workflow, supported resolutions and framerate range).
- CI: stream pipeline tests against a fake camera (`tests/test_stream.py`), a lint workflow (shellcheck, ruff, template JavaScript), and UI tests for the on-demand toggle and bitrate dropdown.
- Removed the unused `vlc_buffer_reader()` (it referenced undefined names) and fixed shellcheck warnings in the scripts.
- Streaming: on-demand mode (default, switchable to continuous in Settings > Streaming). The camera starts when a viewer opens the page and stops after `idle_timeout` seconds (default 60) without stream requests.
- Streaming: bitrate cap, set in Settings > Streaming. Auto is 3 Mbit/s at 720p, 5 Mbit/s at 1080p, 1.5 Mbit/s below that.
- Streaming: faster start (ffmpeg no longer holds back the first ~5 seconds) and clock-based segment numbers so names never repeat across camera restarts.
- MQTT: `camera_ready` stays true in standby; new `camera_state` (streaming, starting, standby, error, stopped) and `on_demand` in status, `streaming` (0/1) in metrics.
- Fix: MQTT connected before its publish helpers were defined, which could drop the boot event with a NameError.
- VLC mode: leaving it now resets the camera state so the web stream starts again on the next view.
- Streaming: request one keyframe per second from the encoder so HLS segments are really 1s long (they were 4-6s, putting the web player 10s+ behind live).
- Deploy script: abort early when the Pi cannot resolve public DNS names, and apply host settings (Wi-Fi power save off, 100M journal cap, Raspberry Pi Connect disabled).
- Document recent updates that were applied directly to `master` and to ensure they go through PRs in the future.

## 2026-01-10
- Condense VLC streaming instructions and add mobile device guidance (commit: 6d58ca4) — PR: #10
- Update favicon to Raspberry Pi themed icon (commit: d5603b1) — PR: #8 (merged)
- Tests: improve `tests/run_tests.sh` defaults and add `--base-url` / `--pi-host` options (commit: 3fb8eba)
- UI: Add camera status icon and set page title to "Garage Cam" (commit: d2bebdd)


> Note: Some of the above changes were applied directly to `master` as quick fixes. Going forward, all changes will be submitted as pull requests for review and CI validation.
