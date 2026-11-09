#!/usr/bin/env python3
"""Deploy only when site content differs from the last successful Pages upload."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import urllib.request

MARKER = 'deployment.json'


def fingerprint(folder):
    files = [(p.relative_to(folder).as_posix(), hashlib.sha256(p.read_bytes()).hexdigest())
             for p in sorted(folder.rglob('*')) if p.is_file() and p != folder / MARKER]
    return hashlib.sha256(json.dumps(files).encode()).hexdigest()


def needs_deploy(folder, remote_marker):
    # Compare with the last *successful deployment*, not the last repository commit.
    # A failed upload is therefore retried on the next hourly run.
    digest = fingerprint(folder)
    return digest, remote_marker.get('digest') != digest


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--directory', type=Path, default=Path('web'))
    parser.add_argument('--url', default='https://jiashuaibei.github.io/workbuddy-linux-tracker/deployment.json')
    args = parser.parse_args()
    remote = {}
    try:
        req = urllib.request.Request(args.url, headers={'Cache-Control': 'no-cache'})
        with urllib.request.urlopen(req, timeout=30) as response:
            remote = json.load(response)
        if not isinstance(remote, dict):
            remote = {}
    except (OSError, ValueError) as exc:
        print('Cannot read deployment marker; retry deployment:', exc)
    digest, deploy = needs_deploy(args.directory, remote)
    (args.directory / MARKER).write_text(json.dumps({'digest': digest}) + '\n')
    if os.getenv('GITHUB_OUTPUT'):
        with open(os.environ['GITHUB_OUTPUT'], 'a') as out:
            out.write(f'deploy={str(deploy).lower()}\n')
    if os.getenv('GITHUB_STEP_SUMMARY'):
        with open(os.environ['GITHUB_STEP_SUMMARY'], 'a') as out:
            out.write(f'\nPages deployment needed: **{str(deploy).lower()}**\n')
    print(json.dumps({'deploy': deploy, 'digest': digest}))


if __name__ == '__main__':
    main()
