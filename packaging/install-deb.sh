#!/bin/bash
set -euo pipefail
bundle_dir=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)
if (( EUID == 0 )); then
    echo '데스크톱 터미널에서 일반 사용자로 ./install.sh를 실행하세요. 필요한 단계에서 sudo를 사용합니다.' >&2
    exit 1
fi
source /etc/os-release
# HamoniKR·Mint 같은 파생 배포판은 ID가 다르므로 ID_LIKE까지 확인합니다.
if [[ " ${ID:-} ${ID_LIKE:-} " != *" debian "* && " ${ID:-} ${ID_LIKE:-} " != *" ubuntu "* ]]; then
    echo "이 설치 묶음의 대상은 Debian·Ubuntu 계열 x86_64입니다. 현재: ${PRETTY_NAME:-알 수 없음}" >&2
    echo 'Rocky Linux 9에서는 RPM 묶음(install.sh)을 사용하세요.' >&2
    exit 1
fi
if [[ $(uname -m) != x86_64 ]]; then
    echo "이 설치 묶음의 대상은 x86_64입니다. 현재: $(uname -m)" >&2
    exit 1
fi
if [[ -z ${DISPLAY:-} || -z ${DBUS_SESSION_BUS_ADDRESS:-} ]]; then
    echo '데스크톱에 로그인한 뒤 터미널에서 실행하세요.' >&2
    exit 1
fi
(cd "$bundle_dir" && sha256sum --check SHA256SUMS)
sudo apt-get update
sudo apt-get install -y "linux-headers-$(uname -r)"
# --reinstall so rebuilding the same version still replaces the installed files;
# without it apt reports "already the newest version" and silently changes nothing.
sudo apt-get install -y --reinstall --allow-downgrades "$bundle_dir"/debs/*.deb
# The package postinst already builds the module; only retry if that did not take.
if ! dkms status -m msi_ec -v 0.13 -k "$(uname -r)" | grep -q installed; then
    sudo dkms install -m msi_ec -v 0.13 -k "$(uname -r)"
fi
sudo modprobe msi-ec
if [[ ! -e /sys/class/power_supply/BAT1/charge_control_end_threshold ]]; then
    echo '드라이버는 로드됐지만 BAT1 충전 제어가 없습니다. 펌웨어 지원 여부를 확인하세요.' >&2
    exit 1
fi
/usr/bin/python3 /usr/share/gf63-control/install_fonts.py
/usr/bin/gf63-control-setup
echo '설치 완료. /usr/bin/gf63-control로 실행하세요.'
if ! command -v tuned-adm >/dev/null 2>&1; then
    echo 'tuned가 없어 CPU 전원 프리셋은 비활성 상태로 표시됩니다. sudo apt-get install tuned로 설치할 수 있습니다.' >&2
fi
/usr/bin/gf63-control --background &
