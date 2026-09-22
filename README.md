# GF63 Control

재설치 RPM 묶음과 전원 모드 사용법은 [REUSE.md](REUSE.md)를 참고하세요.

MSI Thin GF63 12VE / Rocky Linux 9 / XFCE·KDE Plasma용 GTK3 제어판과 OSD입니다.
Debian·Ubuntu 계열(HamoniKR·Linux Mint·Ubuntu)에서는 deb 패키지로 설치할 수 있습니다.

## 설치

GitHub Releases에서 `gf63-control-1.3.0-rocky9-x86_64.tar.gz`를 내려받아 압축을 푼 뒤,
Rocky Linux 9 + XFCE에 로그인한 일반 사용자 터미널에서 `./install.sh`를 실행합니다.
의존 패키지를 다운로드하므로 인터넷 연결이 필요합니다. 자세한 내용은 [재설치 안내](REUSE.md)를 참고하세요.

소스 저장소에서는 Rocky Linux 9 데스크톱의 일반 사용자 터미널에서 실행합니다.

```sh
sudo dnf install make rpm-build python3
make install
```

RPM을 빌드하고 기존 설치 스크립트로 앱·드라이버·번들 글꼴을 설치합니다.
시스템 설치 단계에서만 sudo를 사용합니다. GNOME에서는 로그인 자동 실행을 등록하고
앱을 트레이 모드로 실행합니다. 트레이 아이콘에는 아래의 AppIndicator 확장이 필요합니다.
글꼴만 설치하려면 `make install-fonts`, 빌드만 하려면 `make build`를 사용하세요.
글꼴 설치는 기본 글꼴 설정을 변경하지 않습니다.

### Debian·Ubuntu 계열

HamoniKR·Linux Mint·Ubuntu 등에서는 deb 트랙을 사용합니다. 데스크톱에 로그인한
일반 사용자 터미널에서 실행하세요.

```sh
sudo apt install make dpkg-dev python3
make install-deb
```

deb를 빌드하고 apt로 앱·드라이버(DKMS)·번들 글꼴을 설치합니다. 빌드만 하려면 `make build-deb`,
환경만 먼저 확인하려면 `make check-env-deb`를 사용하세요. 자세한 내용은
[packaging/REUSE-debian.md](packaging/REUSE-debian.md)를 참고하세요.

Cinnamon에서는 화면 잠금 감지와 OSD 억제까지 지원하며, Fn키 재매핑과 전원 관리자 연동은
XFCE·KDE 전용입니다. `gf63-control-setup`은 GNOME과 마찬가지로 자동 실행만 등록합니다.

## 실행

응용 프로그램 메뉴의 **GF63 노트북 제어**, `Super+F10`, 또는 다음 명령으로 엽니다.

```sh
gf63-control
```

GUI는 일반 사용자로 실행합니다. sudo로 실행하지 마세요.
창을 닫으면 트레이에서 계속 실행됩니다. `gf63-control-setup --startup`을 한 번
실행하면 XFCE·KDE·GNOME 로그인 때 자동 시작합니다. GNOME에서는 옵션 없는
`gf63-control-setup`도 앱 자동 실행만 등록합니다. 기존 설치는 이 명령으로 다시 등록하세요.
트레이 메뉴 → 프로그램 종료로 완전히 종료할 수 있습니다.
트레이는 AyatanaAppIndicator3 또는 AppIndicator3를 우선 사용하고,
라이브러리가 없으면 기존 Gtk.StatusIcon을 사용합니다. 전용 컬러 아이콘을 함께 설치합니다.
GNOME에서는 [AppIndicator and KStatusNotifierItem Support](https://extensions.gnome.org/extension/615/appindicator-support/)
확장이 필요합니다. 트레이 메뉴의 **제어판 열기**로 창을 표시할 수 있으며,
아이콘이 없는 환경에서는 `gf63-control` 명령으로 열 수 있습니다.
GNOME 트레이 지원은 GNOME 단축키·OSD 지원과는 별개입니다.
OSD 표시 여부는 기능키·OSD 탭에서 설정하며 다음 실행에도 유지됩니다.

## 기능

| 항목 | 동작 |
|---|---|
| 충전 제한 | 60/80/100% 버튼, 10~100% 직접 지정, 실제 값 확인 |
| 화면 밝기 | GUI 5% 단위, 기본 밝기 기능키는 XFCE가 처리 |
| 스피커 | 5% 단위 조절, 100% 상한, 음소거 |
| 마이크 | 기본 입력 장치 음소거 전환 |
| 키보드 조명 | 끄기/1/2/3단계, XFCE의 키보드 조명 키 처리 |
| 터치패드 | 식별된 모든 터치패드 켜기/끄기; 외장 마우스 제외 |
| 웹캠 | msi-ec 웹캠 활성화 전환; 촬영·녹화하지 않음 |
| 팬 부스트 | Cooler Boost 켜기/끄기 |
| 덮개 닫고 사용 | 전원 유지, 내장 화면 끄기·복원, 재부팅 후 유지 |
| 전원 모드 | 저소음·일반·성능, CPU 상한/EPP/터보/팬 세부 설정 |
| OSD | 약 1초 간격으로 실제 상태 변화를 감지, 1.8초 표시 |

화면 보호기가 활성화되면 OSD는 숨깁니다. 잠금 화면의 기능키 제어는
화면 보호기 정책을 따르며 이 프로그램이 입력 잠금을 우회하지 않습니다.
배터리 잔량 변화만으로는 OSD를 띄우지 않습니다.

## 기능키

밝기와 키보드 조명은 XFCE 전원 관리자가 처리합니다. 음량/음소거/마이크는
XFCE 단축키로 이 프로그램에 연결했습니다. 펌웨어가 직접 바꾸는 웹캠·팬·조명도
실제 상태를 읽어 OSD에 표시합니다. Fn+F번호는 키보드 인쇄와 EC 설정에 따라
달라질 수 있으므로 OS의 XF86 기능 이름으로 연결합니다.

| 대체 단축키 | 기능 |
|---|---|
| Super+F5 | 웹캠 전환 |
| Super+F6 | 터치패드 전환 |
| Super+F8 | 팬 부스트 전환 |
| Super+F9 | 마이크 음소거 |
| Super+F10 | 제어판 열기 |

Super는 Windows 로고 키입니다. 기존에 다른 명령이 등록된 조합은 덮어쓰지 않습니다.
OS에 이벤트를 전달하지 않고 장치 상태도 바꾸지 않는 Fn 조합은 자동 처리할 수 없습니다.
물리 키보드의 모든 Fn 조합을 직접 눌러 시험한 것은 아닙니다.

## 시스템 구성

- GUI: `/usr/bin/gf63-control`, `/usr/share/gf63-control/`
- 제한된 하드웨어 제어: `/usr/libexec/gf63-control-helper`
- polkit: `/usr/share/polkit-1/actions/local.gf63.control.policy`
- 사용자 자동 시작: `~/.config/autostart/gf63-control.desktop`
- 사용자 설정과 XFCE 원본 백업: `~/.config/gf63-control/`
- 배터리 CLI `battery-limit`은 그대로 사용 가능

하드웨어 helper는 고정된 sysfs 파일과 정해진 값만 허용합니다.
활성 로컬 세션에서는 버튼/기능키마다 암호를 요구하지 않으며,
비활성·원격 세션에서는 관리자 인증을 요구합니다. GUI 전체를 root로 실행하지 않습니다.
전원 모드 탭에서 TuneD를 통해 CPU 정책과 팬 모드를 설정합니다.
팬 곡선, EC 원시 주소, Fn/Windows 키 위치는 변경하지 않습니다.

### ThinLinc 등 원격 세션에서 반복되는 인증

버튼은 `sudo`가 아닌 `pkexec`(polkit)를 사용하므로 sudoers의 `NOPASSWD`는
적용되지 않습니다. ThinLinc는 활성 상태여도 원격 세션이므로 기본 정책에서
매번 관리자 인증을 요구합니다.

특정 사용자의 활성 원격 세션에도 암호 없는 제어를 허용하려면 관리자가
`/etc/polkit-1/rules.d/40-gf63-control-user.rules`를 root 소유, 권한 `0644`로
만들고 아래의 `YOUR_USERNAME`을 허용할 실제 로그인 이름으로 바꿉니다.
이 예외는 해당 사용자의 활성 세션에서 GF63 helper 실행에만 적용됩니다.

```javascript
polkit.addRule(function(action, subject) {
    if (action.id == "local.gf63.control.hardware" &&
        action.lookup("program") == "/usr/libexec/gf63-control-helper" &&
        subject.user == "YOUR_USERNAME" && subject.active) {
        return polkit.Result.YES;
    }
});
```

polkit은 규칙 변경을 자동으로 읽습니다. 예외를 취소하려면 위 규칙 파일을
삭제합니다. 이 설정은 호스트별 선택 사항이며 RPM에 포함되지 않습니다.

알림 서비스 `xfce4-notifyd`, 내장 오디오용 `alsa-sof-firmware`와 `alsa-ucm`을 설치하고,
사용자 PipeWire 및 WirePlumber를 활성화했습니다. 실제 스피커/마이크 장치 인식을
확인했으나 음질·녹음 품질과 재부팅 후 전체 동작은 사용자 확인이 필요합니다.

## 검증 및 개발

```sh
cd gf63-control
python3 -m unittest -v
gf63-control --test-osd
```

검증: 허용값·잘못된 명령·배터리 식별·음량 파싱·장치 선택 및 전원·덮개 설정 등 61개 테스트.
데스크톱에서 합성 기능키로 음량·밝기·키보드 조명 변화 및 원상복구를 확인했습니다.

## 설정 복원과 제거

일반 사용자로 다음 명령을 실행하면 이 프로그램이 변경한 XFCE 설정만 복원합니다.
설치 이후 다른 값으로 바꾼 설정은 유지합니다.

```sh
gf63-control-setup --restore
gf63-control --quit
rm ~/.config/autostart/gf63-control.desktop
```

시스템 설치 파일은 관리자 권한으로 위 시스템 구성의 GUI/helper/policy/desktop 파일을
제거하면 됩니다. msi-ec 드라이버와 배터리 CLI는 별도 구성입니다.

참고: [MSI 기능키 안내](https://www.msi.com/support/technical_details/NB_KB_Setting),
[XFCE 전원 관리](https://docs.xfce.org/xfce/xfce4-power-manager/preferences),
[msi-ec 드라이버](https://github.com/BeardOverflow/msi-ec).

## 소스 구조와 기여

- `gf63_control.py`: GTK 제어판, 단일 인스턴스, OSD
- `gf63_core.py`: 장치 상태 조회와 작업 전달
- `gf63_helper.py`: polkit으로 실행하는 제한된 하드웨어 제어
- `configure_xfce.py`: 사용자 단축키 등록과 복원
- `battery_limit.py`: 배터리 CLI
- `packaging/`: RPM spec, deb 메타데이터(`deb/`), 빌드 및 설치 스크립트
- `vendor/msi-ec/`: 고정된 upstream 드라이버 소스와 출처

개발 지침과 검증 범위는 [AGENTS.md](AGENTS.md)를 확인하세요.

```sh
sudo dnf install rpm-build python3      # Debian 계열: sudo apt install dpkg-dev python3
python3 -m unittest -v
python3 packaging/build.py              # Debian 계열: python3 packaging/build_deb.py
```

빌드 결과는 `dist/`에 생성됩니다. 드라이버 소스가 포함되어 있어 빌드 중 GitHub에서 코드를 받지 않습니다.
이 프로젝트는 MSI 공식 소프트웨어가 아닙니다. GUI/패키징 코드는 MIT, 포함된 msi-ec 드라이버는 GPL-2.0-or-later입니다.

## 프로그램 설치

제어판의 **프로그램 설치 → 카카오톡 (Wine)**에서 **설치 / 설정 복구**, **카카오톡 실행**,
**상태 확인**을 사용할 수 있습니다. **Pretendard · 글꼴 다듬기 적용**은 카카오톡을
재설치하지 않고 영문·한글 UI 글꼴 대체와 ClearType RGB 설정만 적용합니다.
**Wine 설정 열기**는 카카오톡 전용 환경의 `winecfg`를 엽니다. 화면·오디오·Windows 버전 등을 조절할 수 있습니다. Wine은 사용자용 Flatpak `org.winehq.Wine`의
`stable-25.08` 브랜치를 사용합니다. Flatpak 자체가 없으면 먼저 배포판 패키지 관리자로 설치해야 합니다.
사용자 Flathub 저장소가 없으면 설치 과정에서 등록합니다. 인터넷과 수 GB의 여유 공간이 필요합니다.

설치 파일은 [카카오 공식 다운로드](https://www.kakaocorp.com/page/service/all)에 연결된
64비트 Windows 설치 파일을 받습니다. 실행 환경과 카카오톡을 설치한 뒤 번들 Pretendard로
영문·한글 UI 글꼴(Tahoma·Arial·Segoe UI·MS Sans Serif 등)을 Pretendard로 대체하고
ClearType RGB 안티앨리어싱을 설정한 뒤 **카카오톡 (Wine)** 앱 메뉴를 만듭니다.
이미 실행 중인 카카오톡은 완전히 종료한 뒤 다시 실행해야 글꼴 다듬기가 반영됩니다.
아이콘·이모지 글꼴은 대체하지 않습니다. 기존 글꼴 대체표는 `kakaotalk-install/font-substitutes-before.reg`에 백업합니다.
이전 Wine 바탕 화면 설정은 `kakaotalk-install/font-rendering-before.reg`에 한 번 백업하며 언어 설정은 변경하지 않습니다. 기존 WinApps 카카오톡은 유지합니다.
이미 설치된 카카오톡은 재설치하지 않고 글꼴·메뉴만 복구합니다. 사용자가 수정한 Wine 바로가기는 덮어쓰지 않습니다.
Wine 바로가기의 `XMODIFIERS=@im=`은 현재 세션의 한글 입력기(nimf 또는 IBus)로 맞춥니다.
입력기를 바꾸면 **상태 확인**이 메뉴 재등록을 안내하고, **설치 / 설정 복구**로 바로가기를 다시 씁니다.

설치는 별도 작업 스레드에서 진행해 노트북 제어를 막지 않습니다. 단계와 오류를 탭에서 확인할 수 있습니다.
카카오톡 데이터는 `~/.var/app/org.winehq.Wine/data/kakaotalk`, 설치·실행 로그는 같은 data 아래
`kakaotalk-install/`에 저장합니다. 중간 실패 후 다시 설치를 누르면 완료된 Wine 설치를 재사용합니다.
제어판 패키지 제거 시 카카오톡·대화 데이터·Wine 실행 환경을 자동 삭제하지 않습니다.

Rocky 9 GNOME/X11, Wine 11.0에서 공식 설치 파일의 설치와 로그인 화면 표시를 확인했습니다.
계정 로그인·메시지 송수신·통화 및 XFCE 세션 동작은 미검증입니다. Linux는 카카오톡의 공식 지원 환경이 아닙니다.

## NVIDIA 그래픽 드라이버

제어판의 **프로그램 설치 → NVIDIA 그래픽 드라이버**에서 현재 상태를 확인하고
**터미널에서 설치**, **명령 복사**, **상태 확인**을 사용할 수 있습니다.

상태에는 그래픽 카드 모델, 현재 커널 드라이버, 설치된 패키지 또는 `ubuntu-drivers`가
권장하는 패키지, Secure Boot 상태, 현재 커널의 헤더 유무, PRIME 모드가 표시됩니다.
읽기 전용 조회만 하며 권한을 요구하지 않습니다.

설치 자체는 제어판이 아니라 터미널에서 진행합니다. `apt`는 패키지의 관리자 스크립트를
root로 실행하므로, 이 앱의 polkit 액션과 root helper에는 추가하지 않습니다.
**터미널에서 설치**는 터미널을 열어 `sudo apt update`, `sudo apt install <권장 패키지>`,
`sudo prime-select on-demand`를 순서대로 띄우며, 관리자 암호는 사용자가 터미널에 직접
입력합니다. `-y`를 붙이지 않으므로 apt가 보여주는 변경 내용을 확인한 뒤 진행 여부를
선택할 수 있습니다. 재부팅은 자동으로 하지 않습니다.

설치할 패키지 이름은 `ubuntu-drivers devices`의 `recommended` 항목에서만 읽고,
`nvidia-driver-<숫자>` 형식(`-open`·`-server`·`-server-open` 접미사 허용)만 허용합니다.
그 밖의 문자열은 거부하므로 터미널 명령에 임의의 값이 들어가지 않습니다.

현재 커널의 헤더가 없으면 DKMS 빌드가 실패하므로 설치를 시작하지 않고 안내합니다.
Secure Boot가 켜져 있으면 설치 후 MOK 등록이 필요하다고 표시합니다. Secure Boot를
끄지 않으며 끄도록 안내하지도 않습니다.

패키지 설치만으로는 드라이버가 전환되지 않습니다. 설치된 패키지가 있는데 커널이 아직
`nouveau`를 쓰고 있으면 **재부팅이 필요합니다**로 표시합니다. 재부팅 후 상태 확인을
누르면 실행 중인 드라이버 버전을 `nvidia-smi`에서 읽어 보여줍니다.

apt 계열이 아니거나 NVIDIA 카드가 없으면 기능을 사용할 수 없다고 표시하고 실패하지
않습니다. Rocky 9(RPM 트랙)에서는 지원하지 않으며, 해당 배포판의 저장소를 직접
사용하세요. 터미널 프로그램을 찾지 못하면 **명령 복사**로 직접 실행할 수 있습니다.
MSI GF63의 Intel + NVIDIA 하이브리드 구성에서 기본값은 `on-demand`이며, 필요하면
설치 후 `sudo prime-select nvidia`로 바꿀 수 있습니다.

## 한영 전환

제어판의 **기능키 · OSD → 한영 전환**에서 현재 설정을 확인하고,
**선택한 한영 전환 키 적용** 또는 **원래 키 설정 복원** 버튼을 사용할 수 있습니다.

XFCE에서 `gf63-control-setup`은 설치된 한글 입력기의 한/영 키 전환을 활성화하고,
Caps Lock을 같은 전환 키로 설정합니다. 기존 Shift+Space 등의 전환 키는 유지합니다.
제어판에서 **F1~F20** 중 원하는 키를 여러 개 선택하여 추가할 수 있습니다.
nimf는 키 표가 F12까지이므로 nimf 세션에서는 F13~F20 선택을 비활성화하고 거부합니다.
선택을 해제하고 적용하면 앱이 추가한 기능키 전환만 제거합니다. 원래 등록되어 있던 전환 키는 유지합니다.
기능키는 입력기의 전환 키로 등록하며, 기존 앱 단축키와 겹칠 수 있습니다.
IBus는 `org.freedesktop.ibus.engine.hangul`의 `switch-keys`에,
nimf는 `org.nimf.engines.nimf-libhangul`의 `shortcuts-to-lang`·`shortcuts-to-sys`
두 목록에 모두 추가합니다. 기존 값은 백업하고 복원 시 그대로 되돌립니다.
F13~F20은 해당 키를 전송하는 키보드가 필요하며, 펌웨어 전용 Fn 동작은 전환 키로 처리할 수 없습니다.
Caps Lock의 대문자 고정 기능은 해제되며 XFCE·KDE·GNOME의 X11 로그인 때 키 매핑을 다시 적용합니다.
GNOME에서는 제어판의 **선택한 한영 전환 키 적용**을 한 번 눌러 등록하세요. 기존 설정도
다시 적용하면 이전 백업을 보존하면서 자동 시작을 상태 확인 방식으로 갱신하고 현재 세션에도 시작합니다.
로그인 서비스는 2초 간격으로 키 매핑과 입력기 전환 키 설정만 확인합니다. 로그인 초기화나
입력기 재시작으로 값이 백업 당시 원래 값으로 돌아가면 재적용하며, 다른 사용자 설정은 유지합니다.
키 입력을 수집하지 않으며 정상 상태에서는 설정을 다시 쓰지 않습니다. 원래 키 설정을 복원하면 서비스도 종료합니다.
세션 연결 오류는 최대 30회 재시도합니다. 자동 시작 파일을 삭제하거나 수정하면 서비스가 종료합니다.
Wayland 로그인에서는 키 매핑을 변경하지 않습니다.
사용하는 입력기(nimf 또는 IBus)에서 한글 입력기를 선택한 상태에서 사용하세요.
입력기는 실행 중인 프로세스, `GTK_IM_MODULE`/`QT_IM_MODULE`/`XMODIFIERS`, 설치된 GSettings
스키마 순서로 판별하며, 판별한 입력기를 백업에 기록해 이후 적용·복원에 같은 입력기를 사용합니다.
둘 다 설치되어 있고 실행 중인 입력기도 환경 변수도 없으면 변경하지 않고 오류를 표시합니다.
`gf63-control-setup --restore`는 이 프로그램이 설정한 값이 유지된 항목만 복원합니다.
사용자가 이후 바꾼 키 설정은 보존합니다. GNOME X11에서 Caps Lock 매핑을 직접 초기화한 뒤
자동 복구되는 것을 두 차례 확인했습니다. 이 검증은 키 매핑 직접 변경으로 수행했으며,
수정 후 실제 물리 키 입력·재부팅·재로그인과 XFCE 세션 검증은 별도로 필요합니다.

## 덮개를 닫고 사용

**전원 모드 → 덮개를 닫아도 전원 유지 → 켜기**로 활성화합니다.
전원 연결 및 배터리 모두에서 덮개 때문에 절전하지 않으며, 내장 화면의
백라이트 전원을 끕니다. 덮개를 열거나 기능을 끄면 이전 화면 전원 상태를 복원합니다.
외장 화면과 ThinLinc 가상 화면에는 화면 끄기 명령을 보내지 않습니다.

시스템 서비스 `gf63-lid.service`가 logind의 `handle-lid-switch` 억제 잠금을
보유하므로 GUI 종료·로그아웃 후에도 작동하고 재부팅 시 자동 시작합니다.
센서 또는 화면 제어를 확인할 수 없으면 서비스가 실패하며 제어판에 표시됩니다.
켜기는 현재 사용자의 XFCE 덮개 처리를 logind에 위임하고 원본을 백업합니다.
**끄기 / 복원**은 서비스를 중지·자동 시작 해제하고, 아직 앱이 설정한 값인
XFCE 항목만 복원합니다. 다른 사용자의 XFCE 설정은 바꾸지 않습니다.

수동 절전, 유휴 시간에 따른 자동 절전, 배터리 부족 시 동작 및 화면 잠금은
기존 정책을 따릅니다. 내장 화면을 끄는 것은 화면 잠금을 대신하지 않습니다.
다른 사용자의 전원 관리자가 직접 절전을 요청하면 해당 정책이 적용될 수 있습니다.
설정 복원/제거 전에는 제어판에서 **끄기 / 복원**을 실행하세요.

구현 검증: 덮개 센서 파싱, 화면 끄기·복원, 설정 실패 시 롤백 및 사용자 변경
보존을 포함한 61개 단위 테스트. 실제 덮개를 닫는 동작과 재부팅은 별도 확인이 필요합니다.

## Mac 스타일 단축키

**기능키 · OSD → Mac 스타일 단축키 → Mac 스타일 적용**으로 켭니다.
Windows(Super) 키를 Command처럼 사용하며 기존 Ctrl 조합과 GF63 기능키는 유지합니다.
전체 해제는 **원래 단축키 복원**으로 합니다. 원본을 백업하며 이후 사용자가 바꾼
단축키는 복원 시 덮어쓰지 않습니다. 다른 기능과 충돌하는 조합은 건너뛰고 표시합니다.
설정은 XFCE에 저장되어 다음 로그인에도 유지됩니다.

| 조합 | 기능 |
|---|---|
| Super+C / V / X | 복사 / 붙여넣기 / 잘라내기 |
| Super+A / Z / Shift+Super+Z | 전체 선택 / 실행 취소 / 다시 실행 |
| Super+S / F | 저장 / 검색 |
| Super+T / W | 새 탭 / 탭 닫기 |
| Super+Tab / Shift+Super+Tab | 다음 창 / 이전 창 전환 |
| Super+Space | 앱 실행기 |

**터미널에도 Mac 스타일 적용**은 기본으로 켜져 있습니다. Super+C/V가 명령 중단이
아닌 복사·붙여넣기가 되도록 Ctrl+Shift+C/V로 변환합니다. T/W도 터미널 탭 조작으로
변환하며, Xfce Terminal에서는 A/F로 전체 선택·검색도 가능합니다.
터미널에서 지원하지 않는 잘라내기·실행 취소·저장 조합은 셸 제어로 보내지 않습니다.
호환성 문제가 있으면 체크를 해제하고 **Mac 스타일 적용**을 눌러 터미널의 키 전달만
중지할 수 있습니다. 이 경우 해당 Super 조합은 무동작이며 원래 Ctrl 조합은 유지됩니다.
전체 Mac 스타일을 끄면 단축키 가로채기도 해제됩니다.

XFCE 또는 KDE Plasma의 X11 세션에서 지원합니다. 앱의 표준 Ctrl 단축키를 변환하므로 앱이 다른 키를 사용하면
동작이 다를 수 있습니다. 편집기 내부 터미널은 창 클래스만으로 구분할 수 없으며,
일반 앱으로 처리됩니다. 알려진 터미널도 개별 단축키 커스터마이징은 자동 감지하지 않습니다.
ThinLinc 클라이언트가 먼저 처리하는 Command/Super 조합은 서버에 도달하지 않을 수
있습니다. GNOME 및 Wayland의 Mac 키 변환은 지원하지 않으며, 실제 ThinLinc 클라이언트 입력 호환성은 미검증입니다.
화면 잠금 상태이거나 잠금 여부를 확인할 수 없으면 키를 전달하지 않습니다.

CLI: `gf63-control-setup --mac-shortcuts`, `gf63-control-setup --restore-mac-shortcuts`.
전체 `--restore`에도 Mac 단축키 복원이 포함됩니다.

Mac 단축키 검증: 61개 단위 테스트, XFCE 설정 적용·반복 적용·원본 복원 확인.
실제 X11 세션의 GTK 입력 위젯에서 합성 Super+A/C로 선택·복사 동작을 확인했고,
터미널 클래스를 지정한 테스트 창에서 Ctrl+Shift+C 전달과 터미널 제외를 확인했습니다.
실제 터미널 프로그램의 클립보드·물리 키·ThinLinc 클라이언트 입력은 사용자 검증 대상입니다.

## KDE Plasma

KDE에서는 로그인 화면에서 **Plasma (X11)** 을 선택하세요. ThinLinc도 KDE 세션을
선택해 로그인하면 X11 변환을 사용할 수 있습니다. 로그인한 사용자 터미널에서
`gf63-control-setup`을 한 번 실행하면 KDE용 GF63 대체 단축키와 자동 시작을 등록합니다.
Mac 스타일은 **기능키 · OSD → Mac 스타일 적용**에서 별도로 켭니다.
XFCE와 KDE의 단축키 및 백업은 분리됩니다. Mac 조합과 겹치는 알려진 KDE 5 기본 조합은 백업 후 대체하고 복원 시 되돌립니다.
사용자가 수정한 조합과 기타 충돌은 건너뜁니다.
KDE의 Alt+Tab은 유지하고 Meta+Tab을 추가합니다. Meta는 Windows/Super 키입니다.

KDE에서는 KGlobalAccel 서비스에 앱 전용 데스크톱 동작을 등록하고 KDE 화면 잠금을
감지합니다. Konsole의 Meta+C/V는 복사·붙여넣기, Meta+T/W는 탭 조작,
Meta+F는 검색입니다. Konsole 전체 선택은 기본 단축키가 없어 변환하지 않습니다.
한영 전환 설정은 nimf·IBus와 X11 조합용이며 Fcitx 등 다른 입력기 설정을 바꾸지 않습니다.

덮개 기능이 켜져 있어도 KDE로 처음 전환한 뒤에는 **전원 모드 → 덮개 켜기**를
한 번 눌러 KDE PowerDevil에도 적용하세요. 전원 연결·배터리·저전력 프로필의
덮개 동작만 변경하며 기존 설정을 백업하고 조건부 복원합니다.

배터리·밝기·웹캠·팬·TuneD 전원 설정은 동일한 시스템 helper를 사용합니다.
Wayland에서도 시스템 제어는 가능하지만 Mac 키 변환·xinput 터치패드 제어·X11
키 재매핑은 지원하지 않습니다. KDE 자체의 음량·밝기 OSD와 GF63 OSD가 함께
표시되면 GF63의 OSD 옵션을 끌 수 있습니다.

검증: Rocky 9의 KDE 5.27/KF5 5.116에서 독립된 X11·D-Bus 세션을 사용했습니다.
실제 KGlobalAccel 등록·반복 적용·복원 및 합성 키의 데스크톱 명령 실행,
KConfig 덮개 값 쓰기·읽기·복원, GTK 제어판/OSD 렌더링을 확인했습니다.
PowerDevil 전체 세션의 실제 덮개 개폐, 물리 키, KDE 6 및 Wayland 동작은 미검증입니다.


### KDE · GNOME · Konsole 글꼴

제어판 **기능키 · OSD → KDE · GNOME · Konsole 글꼴 → 설치 및 적용**을 사용하세요.
패키지에 **Pretendard 1.3.9**의 9개 OTF 굵기와 **D2Coding 1.3.3**의
기본형과 **D2Coding Ligature**의 Regular/Bold TTF를 포함합니다. 인터넷 연결이나 관리자 권한 없이 설치합니다.
공식 배포본은 변경하지 않았으며, 두 글꼴의 SIL Open Font License 1.1과 원본 정보,
SHA256 목록도 `vendor/fonts/`에 포함합니다. 프로젝트 MIT 라이선스와 별개입니다.

RPM에는 `/usr/share/gf63-control/vendor/fonts/`로 포함하며 설치·적용 버튼은 파일을
검증한 뒤 `$XDG_DATA_HOME/fonts/gf63-control/`(기본 `~/.local/share/fonts/gf63-control/`)에
복사하고 fontconfig 캐시를 갱신합니다. 다른 사용자 글꼴은 수정하지 않습니다.
기존 설치에는 누락된 글꼴만 추가하며, Ligature는 앱의 글꼴 선택에서 사용할 수 있습니다.
이미 설치된 앱 전용 파일이 달라졌으면 덮어쓰지 않고 오류를 표시합니다.
소스 아카이브, SRPM, 설치 번들에도 같은 리소스를 포함합니다.

- KDE: 일반·메뉴·도구 모음·작은 글꼴·창 제목에 Pretendard, 고정폭에 D2Coding.
  기존 크기·굵기를 유지하며 없는 값은 10pt(작은 글꼴 8pt)를 사용합니다.
- Konsole(KDE): 기존 기본 프로필을 상속하는 `GF63-D2Coding.profile`을 생성하고
  D2Coding 11pt로 설정합니다. 셸·색상은 상속하고 다른 프로필은 수정하지 않습니다.
- GNOME: 일반·문서·창 제목에 Pretendard, 고정폭에 D2Coding. 기존 크기·스타일을 유지합니다.
  X11/Wayland 모두 키 입력 없이 GSettings를 사용합니다. 터미널의 자체 글꼴 설정과
  GNOME Shell 테마 글꼴은 변경하지 않습니다. GNOME용 GF63 단축키·OSD 지원과는 별개입니다.

```bash
# 설치된 패키지에서 실행: 로컬 글꼴 설치 + 현재 데스크톱에 적용
gf63-control-setup --fonts
# GNOME 로그인 시 설치·적용 확인 켜기 (현재 세션에도 설치·적용)
gf63-control-setup --fonts-startup
# 자동 시작만 해제, 현재 글꼴 설정 유지
gf63-control-setup --no-fonts-startup
# 현재 데스크톱의 원래 글꼴 복원 (GNOME에서는 앱 소유 자동 시작도 해제)
gf63-control-setup --restore-fonts
# 소스에서도 로컬 설치·적용 및 상태 확인 가능
python3 configure_fonts.py
python3 configure_fonts.py --status
python3 configure_fonts.py --restore
```

GNOME 자동 시작은 설치된 패키지의 고정 경로를 사용하는
`~/.config/autostart/gf63-control-fonts.desktop`에 등록하며 `OnlyShowIn=GNOME;`으로 제한합니다.
`XDG_CONFIG_HOME`을 설정했다면 해당 경로를 사용합니다.
로그인 시 다운로드하지 않습니다. 반복 적용은 이후 사용자 변경을 덮어쓰지 않습니다.
자동 시작 오류는 세션의 표준 오류 출력으로 남기며, 제어판에서 다시 적용하면 오류를 확인할 수 있습니다.
앱을 삭제하기 전 자동 시작을 해제하세요. 사용자가 수정한 자동 시작 파일은 보존합니다.

설정 백업은 `$XDG_CONFIG_HOME/gf63-control/`의 `kde-fonts.json`과 `gnome-fonts.json`에
분리 저장합니다. 적용했던 데스크톱에서 복원하면 앱이 적용한 값과 일치하는 항목만
원래 값으로 돌립니다. GNOME의 원래 사용자 값이 없었던 항목은 기본값 상속으로 복원합니다.
복원 시 설치된 글꼴 파일은 다른 앱에서도 사용할 수 있도록 유지합니다.

KDE는 KConfig 5/6 도구, GNOME은 PyGObject/Pango와 `gsettings-desktop-schemas`가 필요합니다.
적용·복원 후 앱을 재시작하거나 다시 로그인하세요. KDE에서는 모든 Konsole 창도
종료한 뒤 실행하세요. 현재 앱의 즉시 갱신은 보장하지 않습니다.

검증: 전체 86개 단위 테스트(글꼴·설치·자동 시작 관련 25개 포함). 임시 설정 저장소에서 실제 KF5 KConfig 및
GNOME GSettings(keyfile 저장소)의 적용·읽기 확인·복원 검증.
실제 로그인 자동 실행, 데스크톱 화면 및 KDE 6은 미검증입니다.
원본 출처·라이선스·해시는 [vendor/fonts/UPSTREAM.md](vendor/fonts/UPSTREAM.md)를 참고하세요.
