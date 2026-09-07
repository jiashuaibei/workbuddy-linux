#!/usr/bin/env bash
set -euo pipefail

[[ $# -ge 1 && $# -le 2 ]] || {
    echo "Usage: $0 UPSTREAM_DEB [OUTPUT_DIRECTORY]" >&2
    exit 2
}

input=$1
output_dir=${2:-dist}
mkdir -p "$output_dir"

scripts/build-deb.sh "$input" "$output_dir"
scripts/build-rpm.sh "$input" "$output_dir"

version=$(dpkg-deb -f "$input" Version)
(
    cd "$output_dir"
    sha256sum *"$version"*.deb *"$version"*.rpm > "SHA256SUMS-$version"
)

