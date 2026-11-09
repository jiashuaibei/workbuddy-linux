#!/usr/bin/env python3
"""Mirror bytes from the official API; never execute or repackage a package."""
import argparse
import datetime
import hashlib
import json
import os
from pathlib import Path
import subprocess
import urllib.parse
import urllib.request

from track_official import HOSTS, normalize


def validate_url(url):
    p = urllib.parse.urlsplit(url)
    if (p.scheme != 'https' or p.hostname not in HOSTS or p.username
            or p.password or p.port not in (None, 443)):
        raise ValueError('Unapproved HTTPS source: ' + url)


class OfficialRedirects(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        validate_url(newurl)
        return super().redirect_request(req, fp, code, msg, headers, newurl)


def open_official(url):
    validate_url(url)
    return urllib.request.build_opener(OfficialRedirects()).open(
        urllib.request.Request(url, headers={'User-Agent': 'workbuddy-linux-tracker/2.0',
                                             'Accept-Encoding': 'identity'}), timeout=90)


def release_tag(record):
    identity = json.dumps([record[k] for k in ('version', 'url', 'reportedSha256')]).encode()
    return f"official-{record['version']}-{record['format']}-{hashlib.sha256(identity).hexdigest()[:16]}"


def download(url, path, fmt):
    digest = hashlib.sha256()
    size = 0
    with open_official(url) as response, path.open('wb') as out:
        final_url = response.url
        validate_url(final_url)
        expected = response.headers.get('Content-Length')
        while chunk := response.read(1024 * 1024):
            out.write(chunk)
            digest.update(chunk)
            size += len(chunk)
    if expected is not None and size != int(expected):
        raise ValueError('Incomplete download')
    with path.open('rb') as f:
        magic = f.read(8)
    if not (magic == b'!<arch>\n' if fmt == 'deb' else magic[:4] == b'\xed\xab\xee\xdb'):
        raise ValueError('Unexpected package signature (possibly an error page)')
    return digest.hexdigest(), size, final_url


def gh(*args):
    return subprocess.check_output(['gh', *args], text=True).strip()


def existing_release(repo, tag):
    # Only a real 404 is absence: permission/rate/network errors stop publication.
    result = subprocess.run(['gh', 'api', f'repos/{repo}/releases/tags/{tag}'],
                            text=True, capture_output=True)
    if result.returncode == 0:
        return json.loads(result.stdout)
    if 'HTTP 404' in result.stderr:
        # GitHub's tag endpoint may hide drafts until their tag exists.
        # Authenticated release listing includes drafts and supports recovery.
        pages = json.loads(gh('api', f'repos/{repo}/releases?per_page=100',
                              '--paginate', '--slurp'))
        return next((r for page in pages for r in page if r['tag_name'] == tag), None)
    raise RuntimeError(result.stderr)


def publish(fmt, repo, output, dry_run=False):
    now = datetime.datetime.now(datetime.timezone.utc).isoformat(timespec='seconds')
    endpoint = 'https://www.workbuddy.cn/v2/update?platform=workbuddy-linux-x64-' + fmt
    with open_official(endpoint) as response:
        raw = response.read()
    record = normalize(json.loads(raw), fmt, now)
    tag = release_tag(record)
    filename = f"WorkBuddy-{record['version']}-linux-x86_64.{fmt}"
    required = {filename, 'SHA256SUMS', 'provenance.json', 'upstream-response.json'}
    old = None if dry_run else existing_release(repo, tag)
    if old and not old['draft']:
        if not required.issubset({a['name'] for a in old['assets']}):
            raise RuntimeError('Published release is incomplete; manual review required: ' + tag)
        print('Already published: ' + tag)
        return
    folder = output / tag
    folder.mkdir(parents=True, exist_ok=True)
    actual, size, final_url = download(record['url'], folder / filename, fmt)
    reported = record['reportedSha256'].lower()
    status = ('match' if reported == actual else 'mismatch') if reported else 'not-provided'
    provenance = dict(record, downloadedAt=now, finalUrl=final_url, filename=filename,
                      size=size, actualSha256=actual, upstreamHashStatus=status,
                      repository=repo, commit=os.getenv('GITHUB_SHA'),
                      workflowRun=(f"https://github.com/{repo}/actions/runs/{os.environ['GITHUB_RUN_ID']}"
                                   if os.getenv('GITHUB_RUN_ID') else None),
                      publicationMethod='Original HTTPS response bytes; no repackaging')
    (folder / 'upstream-response.json').write_bytes(raw)
    (folder / 'provenance.json').write_text(json.dumps(provenance, ensure_ascii=False, indent=2) + '\n')
    (folder / 'SHA256SUMS').write_text(f'{actual}  {filename}\n')
    warning = {'match': '接口哈希与下载文件一致。',
               'mismatch': '**注意：接口哈希与实际文件不一致，不能宣称通过上游哈希验证。这里保留官方 HTTPS 返回的原始字节，请通过官方下载地址独立比对。**',
               'not-provided': '**接口没有提供 SHA-256；请通过官方下载地址独立比对。**'}[status]
    notes = f'''WorkBuddy {record['version']} · Linux x86_64 · {fmt.upper()}

社区自动镜像，非腾讯官方 Release。安装包从下方官方 URL 原样下载，未解包、修改或重新封装。

- [官方更新接口]({endpoint})
- [官方原始下载]({record['url']})
- 实测 SHA-256：`{actual}`
- 接口 SHA-256：`{reported or '未提供'}`
- 比对状态：`{status}`
- 下载时间：{now}
- 工作流：{provenance['workflowRun'] or '本地运行（无 Actions 证明）'}
- 脚本提交：`{provenance['commit'] or '未记录'}`

{warning}

下载安装包及 SHA256SUMS 后运行 `sha256sum -c SHA256SUMS`。这验证附件与本项目记录一致，不是官方数字签名。更强的独立核验方式：从 provenance.json 的 url 自行下载，使用 `sha256sum` 或 `cmp` 比较两份文件。附件还包含原始接口响应及完整来源记录。软件安全性与发行版兼容性不由哈希保证。
'''
    (folder / 'release-notes.md').write_text(notes)
    print(json.dumps({'tag': tag, 'sha256': actual, 'upstreamHashStatus': status}))
    if dry_run:
        return
    if not old:
        gh('release', 'create', tag, '--repo', repo, '--draft', '--target', os.environ['GITHUB_SHA'],
           '--title', f"WorkBuddy {record['version']} · {fmt.upper()} · 官方原包镜像",
           '--notes-file', str(folder / 'release-notes.md'))
    # Recover only drafts. Published assets are never overwritten.
    gh('release', 'upload', tag, *[str(folder / n) for n in sorted(required)],
       '--repo', repo, '--clobber')
    uploaded = existing_release(repo, tag)
    assets = {a['name']: a for a in uploaded['assets']}
    for name in required:
        asset = assets.get(name, {})
        if asset.get('size') != (folder / name).stat().st_size:
            raise RuntimeError('Uploaded asset size mismatch: ' + name)
        server_digest = asset.get('digest')
        if server_digest:
            with (folder / name).open('rb') as stream:
                local_digest = hashlib.file_digest(stream, 'sha256').hexdigest()
            if server_digest != 'sha256:' + local_digest:
                raise RuntimeError('Uploaded asset digest mismatch: ' + name)
    gh('release', 'edit', tag, '--repo', repo, '--notes-file', str(folder / 'release-notes.md'),
       '--draft=false', '--latest=false')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--format', choices=['deb', 'rpm'], required=True)
    parser.add_argument('--repo', default=os.getenv('GITHUB_REPOSITORY', 'jiashuaibei/workbuddy-linux-tracker'))
    parser.add_argument('--output', type=Path, default=Path('dist/official'))
    parser.add_argument('--dry-run', action='store_true', help='Download and prepare evidence without publishing')
    args = parser.parse_args()
    publish(args.format, args.repo, args.output, args.dry_run)


if __name__ == '__main__':
    main()
