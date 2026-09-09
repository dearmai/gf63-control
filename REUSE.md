# GF63 Control 1.0.0 재설치 묶음

대상: **Rocky Linux 9 x86_64 + XFCE**, MSI Thin GF63 12VE.
검증한 EC 펌웨어는 `16R8IMS1.108`입니다. 같은 GF63 이름이어도 다른 펌웨어는
드라이버 지원 여부가 다를 수 있습니다. 드라이버가 자동 감지하며 강제 지정하지 않습니다.

## 보관할 파일

`gf63-control-1.0.0-rocky9-x86_64.tar.gz` 전체를 보관하세요.

- `rpms/gf63-control-1.0.0-1.el9.noarch.rpm`: GUI, OSD, 배터리 CLI, 권한 정책, 사용자 설정 도구
- `rpms/msi-ec-dkms-0.13-1.el9.noarch.rpm`: 고정된 MSI 드라이버 소스와 DKMS 등록
- `sources/`: 전체 소스 압축과 SRPM (향후 수정·재빌드용)
- `install.sh`: 저장소·의존 패키지·커널 개발 파일·사용자 설정 설치
- `SHA256SUMS`: 파일 손상 검증

실행 파일 하나만 복사해서는 동작하지 않습니다. 이 묶음도 모든 OS 패키지를
포함한 오프라인 설치본은 아니며, 의존 패키지 설치에는 인터넷과 Rocky/EPEL 저장소가 필요합니다.

## 다음 설치

먼저 Rocky Linux 9와 XFCE를 설치하고 데스크톱에 로그인하세요.
압축을 풀고 **일반 사용자 터미널**에서 실행합니다.

```sh
tar -xzf gf63-control-1.0.0-rocky9-x86_64.tar.gz
cd gf63-control-1.0.0-rocky9-x86_64
./install.sh
```

설치 스크립트가 필요한 단계에만 sudo를 사용합니다.
현재 실행 중인 커널과 정확히 일치하는 `kernel-devel`을 설치합니다.
오래된 커널 개발 패키지가 저장소에 없다면 커널을 업데이트하고 재부팅한 뒤 다시 실행하세요.
Secure Boot가 켜져 있으면 DKMS 서명 키 등록이 필요할 수 있으며,
설치 스크립트는 Secure Boot를 끄거나 펌웨어 검사를 우회하지 않습니다.

RPM만 수동 설치한 경우, 각 XFCE 사용자 계정에서 `gf63-control-setup`을 한 번 실행하세요.
현재 PC의 기존 수동 설치가 `/usr/local/bin`에 남아 있으면 `/usr/bin/gf63-control`로
RPM 버전을 명시적으로 실행합니다. 설치 스크립트가 기존 파일을 임의 삭제하지 않습니다.

## 전원 모드 및 세부 설정

GUI의 **전원 모드** 탭에서 선택합니다.

| 모드 | CPU 정책 | 성능 상한 | 터보 | 팬 |
|---|---|---|---|---|
| 저소음 | 절전 우선 | 60% | 끄기 | 저소음 |
| 일반 | 균형/성능 | 100% | 켜기 | 자동 |
| 성능 | 성능 우선 | 100% | 켜기 | 자동 |

세부 설정: CPU 전력/성능 정책(EPP), 성능 상한 20~100%, 터보 허용,
자동/저소음 팬, Cooler Boost. 값은 TuneD 사용자 프로필에 저장됩니다.
CPU 성능 상한은 CPU 사용률 제한이 아닙니다. 저소음 모드도 온도에 따라 팬이 작동합니다.
GPU 전력 한도와 팬 온도/RPM 곡선은 이 드라이버에서 제공하지 않아 포함하지 않습니다.

다른 전원 관리 앱이 TuneD 프로필을 바꾸면 이 설정이 대체될 수 있습니다.
GUI에 실제 CPU 정책과 팬 상태를 함께 표시합니다. RPM 설치 자체는 전원 모드나
기존 충전 상한을 변경하지 않습니다. 기존 `unknown (192)` EC 성능 모드는 직접 쓰지 않습니다.

## 확인

```sh
battery-limit status
dkms status -m msi_ec
gf63-control
```

하드웨어가 지원되지 않으면 GUI가 해당 제어를 사용할 수 없다고 표시합니다.
재부팅 후 전체 동작과 실제 키보드의 모든 Fn 조합은 별도 확인이 필요합니다.

## 제거 / 복원

먼저 일반 사용자로 `gf63-control-setup --restore`를 실행해 기능키와 자동 시작을 복원합니다.
전원 모드를 사용했다면 제거 전 `sudo tuned-adm profile balanced`로 시스템 기본 모드를 선택하세요.
그 뒤 `sudo dnf remove gf63-control msi-ec-dkms`를 실행합니다.
사용자 설정과 `/etc/tuned/gf63-custom/`, `/etc/gf63-control/power.json`은 보존됩니다.
드라이버 제거는 배터리에 저장된 충전 상한을 해제하지 않습니다.

## 재빌드

소스 압축을 풀고 Rocky 9에서 실행합니다.

```sh
sudo dnf install rpm-build python3
python3 packaging/build.py
```

결과는 `dist/`에 생성됩니다. 드라이버 소스가 포함되어 있어 빌드 시 GitHub 접속은 필요 없습니다.
커널 모듈은 RPM 빌드 시가 아니라 대상 PC에 설치할 때 해당 커널용으로 컴파일됩니다.
