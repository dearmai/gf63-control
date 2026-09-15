#!/bin/bash
set -euo pipefail
bundle_dir=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)
if (( EUID == 0 )); then
    echo '데스크톱 터미널에서 일반 사용자로 ./install.sh를 실행하세요. 필요한 단계에서 sudo를 사용합니다.' >&2
    exit 1
fi
source /etc/os-release
if [[ ${ID:-} != rocky || ${VERSION_ID%%.*} != 9 || $(uname -m) != x86_64 ]]; then
    echo '이 설치 묶음의 대상은 Rocky Linux 9 x86_64입니다.' >&2
    exit 1
fi
if [[ -z ${DISPLAY:-} || -z ${DBUS_SESSION_BUS_ADDRESS:-} ]]; then
    echo 'XFCE·KDE·GNOME에 로그인한 뒤 데스크톱 터미널에서 실행하세요.' >&2
    exit 1
fi
(cd "$bundle_dir" && sha256sum --check SHA256SUMS)
sudo dnf install -y epel-release dnf-plugins-core
sudo dnf config-manager --set-enabled crb
app_rpms=("$bundle_dir"/rpms/gf63-control-*.noarch.rpm)
installed_app=$(rpm -q --qf '%{VERSION}-%{RELEASE}' gf63-control 2>/dev/null || true)
bundle_app=$(rpm -qp --qf '%{VERSION}-%{RELEASE}' "${app_rpms[0]}")
sudo dnf install -y "kernel-devel-$(uname -r)" "$bundle_dir"/rpms/*.rpm
if [[ "$installed_app" == "$bundle_app" ]]; then
    sudo dnf reinstall -y "${app_rpms[0]}"
fi
sudo dkms install -m msi_ec -v 0.13 -k "$(uname -r)"
sudo modprobe msi-ec
if [[ ! -e /sys/class/power_supply/BAT1/charge_control_end_threshold ]]; then
    echo '드라이버는 로드됐지만 BAT1 충전 제어가 없습니다. 펌웨어 지원 여부를 확인하세요.' >&2
    exit 1
fi
/usr/bin/python3 /usr/share/gf63-control/install_fonts.py
/usr/bin/gf63-control-setup
echo '설치 완료. /usr/bin/gf63-control로 실행하세요.'
if [[ -e /usr/local/bin/gf63-control ]]; then
    echo '기존 수동 설치가 /usr/local/bin에 있습니다. 새 버전은 /usr/bin/gf63-control을 사용하세요.'
fi
/usr/bin/gf63-control --background &
