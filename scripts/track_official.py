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

def fetch(fmt, now):
    endpoint = 'https://www.workbuddy.cn/v2/update?platform=workbuddy-linux-x64-' + fmt
    request = urllib.request.Request(endpoint, headers={'User-Agent': 'workbuddy-linux-tracker/1.0'})
    with urllib.request.urlopen(request, timeout=30) as response:
        return normalize(json.load(response), fmt, now)

def merge(data, records, now, errors):
    history = data.setdefault('history', [])
    current = data.setdefault('current', {})
    for record in records:
        key = lambda r: (r['format'], r['version'], r['url'], r['reportedSha256'])
        existing = next((r for r in history if key(r) == key(record)), None)
        if existing is None:
            history.insert(0, record)
            existing = record
        current[record['format']] = dict(existing, lastSuccessfulCheck=now)
    data.update(schemaVersion=1, lastAttempt=now, errors=errors)
    return data

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--output', default='web/data/releases.json')
    args = parser.parse_args()
    path = Path(args.output)
    data = json.loads(path.read_text()) if path.exists() else {}
    now = datetime.datetime.now(datetime.timezone.utc).isoformat(timespec='seconds')
    records, errors = [], {}
    with concurrent.futures.ThreadPoolExecutor(max_workers=2) as pool:
        futures = {fmt: pool.submit(fetch, fmt, now) for fmt in ('deb', 'rpm')}
        for fmt, future in futures.items():
            try:
                records.append(future.result())
            except Exception as exc:
                errors[fmt] = str(exc)
    merge(data, records, now, errors)
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix('.tmp')
    temporary.write_text(json.dumps(data, ensure_ascii=False, indent=2) + '\n')
    os.replace(temporary, path)
    print(json.dumps({'versions': {r['format']: r['version'] for r in records}, 'errors': errors}))
    return bool(errors)

if __name__ == '__main__':
    raise SystemExit(main())
