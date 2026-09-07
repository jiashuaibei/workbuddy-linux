#!/usr/bin/env python3
"""Discover WorkBuddy packages in the public Kylin repository."""

from __future__ import annotations

import argparse
import html.parser
import json
import os
import re
import subprocess
import sys
import urllib.parse
import urllib.request
from dataclasses import asdict, dataclass

DEFAULT_INDEX = (
    "https://software.openkylin.top/openkylin/yangtze/"
    "pool/main/deb/workbuddy/"
)
PACKAGE_RE = re.compile(r"^workbuddy_(?P<version>.+)_(?P<arch>amd64|arm64)\.deb$")


@dataclass(frozen=True)
class Package:
    version: str
    arch: str
    filename: str
    url: str


class LinkParser(html.parser.HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.links: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag.lower() != "a":
            return
        href = dict(attrs).get("href")
        if href:
            self.links.append(href)


def parse_index(content: str, index_url: str) -> list[Package]:
    parser = LinkParser()
    parser.feed(content)
    packages: dict[tuple[str, str], Package] = {}
    for href in parser.links:
        filename = urllib.parse.unquote(urllib.parse.urlparse(href).path.rsplit("/", 1)[-1])
        match = PACKAGE_RE.fullmatch(filename)
        if not match:
            continue
        package = Package(
            version=match.group("version"),
            arch=match.group("arch"),
            filename=filename,
            url=urllib.parse.urljoin(index_url, href),
        )
        packages[(package.version, package.arch)] = package
    return list(packages.values())


def version_compare(left: str, op: str, right: str) -> bool:
    return subprocess.run(
        ["dpkg", "--compare-versions", left, op, right], check=False
    ).returncode == 0


def sorted_packages(packages: list[Package]) -> list[Package]:
    result: list[Package] = []
    for package in packages:
        for index, current in enumerate(result):
            if version_compare(package.version, "lt", current.version):
                result.insert(index, package)
                break
            if package.version == current.version and package.arch < current.arch:
                result.insert(index, package)
                break
        else:
            result.append(package)
    return result


def fetch_index(index_url: str) -> str:
    request = urllib.request.Request(
        index_url,
        headers={"User-Agent": "workbuddy-linux-upstream-tracker/1.0"},
    )
    with urllib.request.urlopen(request, timeout=30) as response:
        return response.read().decode("utf-8", errors="replace")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("command", choices=("list", "latest"))
    parser.add_argument("--arch", choices=("amd64", "arm64"), default="amd64")
    parser.add_argument(
        "--index",
        default=os.environ.get("WORKBUDDY_UPSTREAM_INDEX", DEFAULT_INDEX),
    )
    parser.add_argument("--input", help="Read an HTML fixture instead of the network")
    parser.add_argument("--format", choices=("json", "tsv"), default="json")
    args = parser.parse_args()

    content = (
        open(args.input, encoding="utf-8").read()
        if args.input
        else fetch_index(args.index)
    )
    packages = sorted_packages(
        [package for package in parse_index(content, args.index) if package.arch == args.arch]
    )
    if not packages:
        print(f"No WorkBuddy packages found for {args.arch}", file=sys.stderr)
        return 1

    selected = packages[-1:] if args.command == "latest" else packages
    if args.format == "tsv":
        for package in selected:
            print(f"{package.version}\t{package.arch}\t{package.filename}\t{package.url}")
    elif args.command == "latest":
        print(json.dumps(asdict(selected[0]), ensure_ascii=False))
    else:
        print(json.dumps([asdict(package) for package in selected], ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

