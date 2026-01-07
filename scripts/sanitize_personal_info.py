#!/usr/bin/env python3
"""Sanitize personal host/user strings in staged files.

This script scans the currently staged files and replaces occurrences of
common personal placeholders (e.g., `aachten`, `192.168.0.169`, `/home/aachten`)
with generic placeholders (`<user>`, `<PI_HOST>`, `/home/<user>`). It restages
modified files automatically.

Intended to be run as a pre-commit hook (local pre-commit) so accidental
commits of personal data are sanitized before commit.
"""

import os
import re
import subprocess
import sys

# Patterns to search and their replacements
REPLACEMENTS = [
    # IP ranges (private). Replace exact 192.168.0.169 and other local IPs
    (re.compile(r"\b192\.168\.(?:\d{1,3})\.(?:\d{1,3})\b"), "<PI_HOST>"),
    (re.compile(r"\b10\.(?:\d{1,3})\.(?:\d{1,3})\.(?:\d{1,3})\b"), "<PRIVATE_IP>"),
    (re.compile(r"\b172\.(1[6-9]|2[0-9]|3[0-1])\.(?:\d{1,3})\.(?:\d{1,3})\b"), "<PRIVATE_IP>"),

    # Username and home path
    (re.compile(r"\baachten\b"), "<user>"),
    (re.compile(r"/home/aachten"), "/home/<user>"),
    (re.compile(r"\baachten@"), "<user>@"),

    # Specific logged access URL
    (re.compile(r"http://192\.168\.(?:\d{1,3})\.(?:\d{1,3}):?\d*"), "http://<PI_HOST>:<PORT>"),
]

# Files to ignore (binary files, images, compiled files)
IGNORE_EXTS = {'.png', '.jpg', '.jpeg', '.gif', '.gz', '.zip', '.pdf', '.sqlite', '.db'}


def get_staged_files():
    """Return a list of staged files (relative paths)."""
    try:
        out = subprocess.check_output(['git', 'diff', '--cached', '--name-only'], text=True)
        files = [f for f in out.splitlines() if f]
        return files
    except subprocess.CalledProcessError:
        return []


def is_text_file(path):
    # Skip known binary extensions first
    _, ext = os.path.splitext(path)
    if ext.lower() in IGNORE_EXTS:
        return False
    # Fallback to git's check
    try:
        subprocess.check_output(['git', 'check-attr', 'binary', '--', path])
    except Exception:
        pass
    # Simple heuristic: try opening as text
    try:
        with open(path, 'rb') as fh:
            chunk = fh.read(8000)
            if b"\0" in chunk:
                return False
    except Exception:
        return False
    return True


def sanitize_file(path):
    try:
        with open(path, 'r', encoding='utf-8') as fh:
            content = fh.read()
    except UnicodeDecodeError:
        # Not a text file we can edit safely
        return False

    original = content
    for pattern, repl in REPLACEMENTS:
        content, n = pattern.subn(repl, content)
    if content != original:
        with open(path, 'w', encoding='utf-8') as fh:
            fh.write(content)
        return True
    return False


def main():
    files = get_staged_files()
    if not files:
        print('No staged files to sanitize.')
        return 0

    modified = []
    for f in files:
        if not os.path.exists(f):
            continue
        if not is_text_file(f):
            continue
        changed = sanitize_file(f)
        if changed:
            modified.append(f)

    if modified:
        # Restage modified files
        try:
            subprocess.check_call(['git', 'add'] + modified)
        except subprocess.CalledProcessError:
            print('Failed to restage modified files.', file=sys.stderr)
            return 2
        print('Sanitized and restaged files:')
        for f in modified:
            print('  -', f)
    else:
        print('No personal data found in staged files.')

    return 0


if __name__ == '__main__':
    sys.exit(main())
