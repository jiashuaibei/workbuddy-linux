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

version=$(dpkg-deb -f "$input" Version)
arch=$(dpkg-deb -f "$input" Architecture)
package=$(dpkg-deb -f "$input" Package)
[[ "$package" == "workbuddy" ]] || { echo "Unexpected package: $package" >&2; exit 1; }
[[ "$version" =~ ^[0-9][0-9A-Za-z.+:~_-]*$ ]] || { echo "Unsafe version: $version" >&2; exit 1; }
[[ "$arch" == "amd64" || "$arch" == "arm64" ]] || { echo "Unsupported architecture: $arch" >&2; exit 1; }

work_dir=$(mktemp -d "${TMPDIR:-/tmp}/workbuddy-deb.XXXXXXXX")
trap 'rm -rf -- "$work_dir"' EXIT
root="$work_dir/root"
dpkg-deb -R "$input" "$root"

install_dir=/opt/apps/workbuddy
[[ -x "$root$install_dir/workbuddy" ]] || {
    echo "Upstream payload is missing $install_dir/workbuddy" >&2
    exit 1
}

installed_size=$(du -sk "$root" | awk '{print $1}')
cat > "$root/DEBIAN/control" <<EOF
Package: workbuddy
Version: $version
Section: utils
Priority: optional
Architecture: $arch
Maintainer: workbuddy-linux contributors
Installed-Size: $installed_size
Depends: libgtk-3-0, libnotify4, libnss3, libxss1, libxtst6, xdg-utils, libatspi2.0-0, libuuid1, libsecret-1-0, libasound2, libgbm1
Recommends: libayatana-appindicator3-1 | libappindicator3-1
Homepage: https://copilot.tencent.com/work/
Description: WorkBuddy desktop application (community Linux package)
 This package adapts the public Kylin WorkBuddy build for Ubuntu and Debian.
 WorkBuddy itself is proprietary software owned by its respective rights holder.
EOF

cat > "$root/DEBIAN/postinst" <<'EOF'
#!/bin/sh
set -e

install_dir=/opt/apps/workbuddy
executable="$install_dir/workbuddy"

if [ -f "$install_dir/chrome-sandbox" ]; then
    chown root:root "$install_dir/chrome-sandbox"
    chmod 4755 "$install_dir/chrome-sandbox"
fi

update-alternatives --install /usr/bin/workbuddy workbuddy "$executable" 100

if command -v update-desktop-database >/dev/null 2>&1; then
    update-desktop-database /usr/share/applications >/dev/null 2>&1 || true
fi
if command -v update-mime-database >/dev/null 2>&1; then
    update-mime-database /usr/share/mime >/dev/null 2>&1 || true
fi
EOF

cat > "$root/DEBIAN/prerm" <<'EOF'
#!/bin/sh
set -e

if [ "$1" = remove ] || [ "$1" = deconfigure ]; then
    update-alternatives --remove workbuddy /opt/apps/workbuddy/workbuddy || true
fi
EOF

cat > "$root/DEBIAN/postrm" <<'EOF'
#!/bin/sh
set -e

if command -v update-desktop-database >/dev/null 2>&1; then
    update-desktop-database /usr/share/applications >/dev/null 2>&1 || true
fi
if command -v update-mime-database >/dev/null 2>&1; then
    update-mime-database /usr/share/mime >/dev/null 2>&1 || true
fi
EOF

chmod 0755 "$root/DEBIAN/postinst" "$root/DEBIAN/prerm" "$root/DEBIAN/postrm"
if [[ -f "$root/usr/share/applications/workbuddy.desktop" ]]; then
    sed -i 's|^Exec=.*|Exec=/opt/apps/workbuddy/workbuddy %U|' \
        "$root/usr/share/applications/workbuddy.desktop"
fi

(
    cd "$root"
    find . -path ./DEBIAN -prune -o -type f -print0 \
        | sort -z \
        | xargs -0 md5sum \
        | sed 's|  \./|  |' > DEBIAN/md5sums
)

mkdir -p "$output_dir"
output="$output_dir/workbuddy-linux_${version}_${arch}.deb"
temporary_output="$work_dir/workbuddy-linux_${version}_${arch}.deb"
dpkg-deb --build --root-owner-group -Zxz "$root" "$temporary_output" >/dev/null

actual_version=$(dpkg-deb -f "$temporary_output" Version)
[[ "$actual_version" == "$version" ]] || {
    echo "Version mismatch: expected $version, got $actual_version" >&2
    exit 1
}
mv "$temporary_output" "$output"
echo "$output"
