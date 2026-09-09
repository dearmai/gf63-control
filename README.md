# GF63 Control

재설치 RPM 묶음과 전원 모드 사용법은 [REUSE.md](REUSE.md)를 참고하세요.

MSI Thin GF63 12VE / Rocky Linux 9 / XFCE용 GTK3 제어판과 OSD입니다.

## 설치

GitHub Releases에서 `gf63-control-1.0.0-rocky9-x86_64.tar.gz`를 내려받아 압축을 푼 뒤,
Rocky Linux 9 + XFCE에 로그인한 일반 사용자 터미널에서 `./install.sh`를 실행합니다.
의존 패키지를 다운로드하므로 인터넷 연결이 필요합니다. 자세한 내용은 [재설치 안내](REUSE.md)를 참고하세요.

## 실행

응용 프로그램 메뉴의 **GF63 노트북 제어**, `Super+F10`, 또는 다음 명령으로 엽니다.

```sh
gf63-control
```

GUI는 일반 사용자로 실행합니다. sudo로 실행하지 마세요.
창을 닫으면 트레이에서 계속 실행되며 다음 로그인 때 자동 시작합니다.
트레이 우클릭 → 프로그램 종료로 완전히 종료할 수 있습니다.
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

검증: 허용값·잘못된 명령·배터리 식별·음량 파싱·장치 선택 및 전원 설정 등 19개 테스트.
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
- `packaging/`: RPM spec, 빌드 및 설치 스크립트
- `vendor/msi-ec/`: 고정된 upstream 드라이버 소스와 출처

개발 지침과 검증 범위는 [AGENTS.md](AGENTS.md)를 확인하세요.

```sh
sudo dnf install rpm-build python3
python3 -m unittest -v
python3 packaging/build.py
```

빌드 결과는 `dist/`에 생성됩니다. 드라이버 소스가 포함되어 있어 빌드 중 GitHub에서 코드를 받지 않습니다.
이 프로젝트는 MSI 공식 소프트웨어가 아닙니다. GUI/패키징 코드는 MIT, 포함된 msi-ec 드라이버는 GPL-2.0-or-later입니다.
