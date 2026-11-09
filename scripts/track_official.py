#!/usr/bin/env python3
"""Observe official Linux update endpoints without repackaging binaries."""
import argparse
import concurrent.futures
import datetime
import json
import os
from pathlib import Path
import re
import urllib.parse
import urllib.request

HOSTS = {'download.codebuddy.cn', 'www.workbuddy.cn'}

def normalize(payload, fmt, now):
    url = payload.get('url', '')
    parsed = urllib.parse.urlsplit(url)
    if (parsed.scheme != 'https' or parsed.hostname not in HOSTS
            or parsed.username or parsed.password or parsed.port not in (None, 443)
            or not parsed.path.endswith('.' + fmt)):
        raise ValueError('Unexpected official download URL')
    version = payload.get('version', '')
    if not re.fullmatch(r'[0-9]+(?:\.[0-9]+)*', version):
        raise ValueError('Invalid version')
    digest = payload.get('sha256hash', '')
    if digest and not re.fullmatch(r'[a-fA-F0-9]{64}', digest):
        raise ValueError('Invalid SHA-256')
    return dict(format=fmt, architecture='x86_64', version=version,
                productVersion=payload.get('productVersion'), url=url,
                domain=parsed.hostname, reportedSha256=digest,
                upstreamTimestamp=payload.get('timestamp'), firstSeen=now,
                source='https://www.workbuddy.cn/v2/update?platform=workbuddy-linux-x64-' + fmt)

def fetch(fmt, now, snapshot_dir=None):
    endpoint = 'https://www.workbuddy.cn/v2/update?platform=workbuddy-linux-x64-' + fmt
    request = urllib.request.Request(endpoint, headers={'User-Agent': 'workbuddy-linux-tracker/1.0'})
    with urllib.request.urlopen(request, timeout=30) as response:
        raw = response.read()
    record = normalize(json.loads(raw), fmt, now)
    if snapshot_dir is not None:
        snapshot_dir.mkdir(parents=True, exist_ok=True)
        (snapshot_dir / (fmt + '.json')).write_bytes(raw)
    return record

def identity(record):
    return tuple(record[k] for k in ('format', 'version', 'url', 'reportedSha256'))


def merge(data, records, now, errors):
    # schema v2 stores release facts only. Every attempt belongs in check-status.json.
    history = data.setdefault('history', [])
    current = data.setdefault('current', {})
    data.pop('lastAttempt', None)
    data.pop('errors', None)
    for record in current.values():
        record.pop('lastSuccessfulCheck', None)
    data.setdefault('lastChanged', max((r['firstSeen'] for r in current.values()), default=None))
    for record in records:
        existing = next((r for r in history if identity(r) == identity(record)), None)
        if existing is None:
            history.insert(0, record)
            existing = record
        previous = current.get(record['format'])
        if previous is None or identity(previous) != identity(record):
            current[record['format']] = dict(existing)
            data['lastChanged'] = now
    data['schemaVersion'] = 2
    return data


def write_if_changed(path, data):
    content = json.dumps(data, ensure_ascii=False, indent=2) + '\n'
    if path.exists() and path.read_text() == content:
        return False
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix('.tmp')
    temporary.write_text(content)
    os.replace(temporary, path)
    return True


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--output', default='web/data/releases.json')
    parser.add_argument('--status', default='dist/check/check-status.json')
    parser.add_argument('--snapshot-dir', type=Path, default=Path('dist/check/upstream'))
    args = parser.parse_args()
    path = Path(args.output)
    data = json.loads(path.read_text()) if path.exists() else {}
    now = datetime.datetime.now(datetime.timezone.utc).isoformat(timespec='seconds')
    records, errors = [], {}
    # Remove stale snapshots when a local directory is reused after a failed request.
    for fmt in ('deb', 'rpm'):
        (args.snapshot_dir / (fmt + '.json')).unlink(missing_ok=True)
    with concurrent.futures.ThreadPoolExecutor(max_workers=2) as pool:
        futures = {fmt: pool.submit(fetch, fmt, now, args.snapshot_dir) for fmt in ('deb', 'rpm')}
        for fmt, future in futures.items():
            try:
                records.append(future.result())
            except Exception as exc:
                errors[fmt] = str(exc)
    before = {fmt: identity(r) for fmt, r in data.get('current', {}).items()}
    merge(data, records, now, errors)
    changed_formats = [r['format'] for r in records if before.get(r['format']) != identity(r)]
    changed = write_if_changed(path, data)
    status = dict(checkedAt=now, versions={r['format']: r['version'] for r in records},
                  errors=errors, changedFormats=changed_formats, recordsUpdated=changed)
    write_if_changed(Path(args.status), status)
    if os.getenv('GITHUB_OUTPUT'):
        with open(os.environ['GITHUB_OUTPUT'], 'a') as out:
            out.write(f"changed={str(changed).lower()}\n")
            for fmt in ('deb', 'rpm'):
                out.write(f"{fmt}={str(fmt in status['versions']).lower()}\n")
    if os.getenv('GITHUB_STEP_SUMMARY'):
        with open(os.environ['GITHUB_STEP_SUMMARY'], 'a') as out:
            out.write('## Official Linux check\n\n```json\n' + json.dumps(status, indent=2) + '\n```\n')
    print(json.dumps(status))
    return bool(errors)

if __name__ == '__main__':
    raise SystemExit(main())
