#!/usr/bin/env bash
set -euo pipefail

usage() {
    echo "Usage: $0 UPSTREAM_DEB [OUTPUT_DIRECTORY]" >&2
}

[[ $# -ge 1 && $# -le 2 ]] || { usage; exit 2; }

input=$1
output_dir=${2:-dist}
[[ -f "$input" ]] || { echo "Input file not found: $input" >&2; exit 1; }
command -v dpkg-deb >/dev/null || { echo "dpkg-deb is required" >&2; exit 1; }
command -v rpmbuild >/dev/null || { echo "rpmbuild is required" >&2; exit 1; }

version=$(dpkg-deb -f "$input" Version)
deb_arch=$(dpkg-deb -f "$input" Architecture)
package=$(dpkg-deb -f "$input" Package)
[[ "$package" == "workbuddy" ]] || { echo "Unexpected package: $package" >&2; exit 1; }
[[ "$version" =~ ^[0-9][0-9A-Za-z.+~_]*$ ]] || { echo "RPM-incompatible version: $version" >&2; exit 1; }
case "$deb_arch" in
    amd64) rpm_arch=x86_64 ;;
    arm64) rpm_arch=aarch64 ;;
    *) echo "Unsupported architecture: $deb_arch" >&2; exit 1 ;;
esac

work_dir=$(mktemp -d "${TMPDIR:-/tmp}/workbuddy-rpm.XXXXXXXX")
trap 'rm -rf -- "$work_dir"' EXIT
topdir="$work_dir/rpmbuild"
mkdir -p "$topdir"/{BUILD,BUILDROOT,RPMS,SOURCES,SPECS,SRPMS}

payload="$work_dir/payload"
dpkg-deb -x "$input" "$payload"
[[ -x "$payload/opt/apps/workbuddy/workbuddy" ]] || {
    echo "Upstream payload is missing /opt/apps/workbuddy/workbuddy" >&2
    exit 1
}

if [[ -f "$payload/usr/share/applications/workbuddy.desktop" ]]; then
    sed -i 's|^Exec=.*|Exec=/opt/apps/workbuddy/workbuddy %U|' \
        "$payload/usr/share/applications/workbuddy.desktop"
fi
mkdir -p "$payload/usr/bin"
ln -s ../../opt/apps/workbuddy/workbuddy "$payload/usr/bin/workbuddy"
chmod 4755 "$payload/opt/apps/workbuddy/chrome-sandbox"
tar -C "$payload" -czf "$topdir/SOURCES/workbuddy-payload.tar.gz" .

sed \
    -e "s/@VERSION@/$version/g" \
    -e "s/@ARCH@/$rpm_arch/g" \
    packaging/rpm/workbuddy.spec.in > "$topdir/SPECS/workbuddy.spec"

rpmbuild -bb \
    --define "_topdir $topdir" \
    --target "$rpm_arch" \
    "$topdir/SPECS/workbuddy.spec"

rpm_file=$(find "$topdir/RPMS" -type f -name '*.rpm' -print -quit)
[[ -n "$rpm_file" ]] || { echo "rpmbuild did not produce an RPM" >&2; exit 1; }
mkdir -p "$output_dir"
output="$output_dir/$(basename "$rpm_file")"
cp "$rpm_file" "$output"

actual_version=$(rpm -qp --qf '%{VERSION}' "$output")
[[ "$actual_version" == "$version" ]] || {
    echo "Version mismatch: expected $version, got $actual_version" >&2
    exit 1
}
echo "$output"
