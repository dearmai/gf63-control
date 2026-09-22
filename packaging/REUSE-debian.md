# GF63 Control 1.3.0 재설치 묶음 (Debian·Ubuntu 계열)

대상: **Debian·Ubuntu 계열 x86_64** (HamoniKR·Linux Mint·Ubuntu 등), MSI Thin GF63 12VE.
검증한 EC 펌웨어는 `16R8IMS1.108`입니다. 같은 GF63 이름이어도 다른 펌웨어는
드라이버 지원 여부가 다를 수 있습니다. 드라이버가 자동 감지하며 강제 지정하지 않습니다.

Rocky Linux 9에서는 이 묶음이 아니라 RPM 묶음(`gf63-control-1.3.0-rocky9-x86_64.tar.gz`)을 사용하세요.
기능 설명·전원 모드·한영 전환·Mac 단축키 등 사용법은 설치 후
`/usr/share/doc/gf63-control/REUSE.md`와 `README.md`에 함께 설치됩니다.

## 보관할 파일

`gf63-control-1.3.0-debian-x86_64.tar.gz` 전체를 보관하세요.

- `debs/gf63-control_1.3.0-1_all.deb`: GUI, OSD, 배터리 CLI, 권한 정책, 사용자 설정 도구
- `debs/msi-ec-dkms_0.13-1_all.deb`: 고정된 MSI 드라이버 소스와 DKMS 등록
- `sources/gf63-control-1.3.0.tar.gz`: 전체 소스 (향후 수정·재빌드용)
- `install.sh`: 의존 패키지·커널 헤더·사용자 설정 설치
- `SHA256SUMS`: 파일 손상 검증

실행 파일 하나만 복사해서는 동작하지 않습니다. 이 묶음도 모든 OS 패키지를
포함한 오프라인 설치본은 아니며, 의존 패키지 설치에는 인터넷과 배포판 저장소가 필요합니다.

## 다음 설치

데스크톱에 로그인한 뒤 압축을 풀고 **일반 사용자 터미널**에서 실행합니다.

```sh
tar -xzf gf63-control-1.3.0-debian-x86_64.tar.gz
cd gf63-control-1.3.0-debian-x86_64
./install.sh
```

설치 스크립트가 필요한 단계에만 sudo를 사용합니다.
현재 실행 중인 커널용 `linux-headers-$(uname -r)`를 설치합니다.
저장소에 해당 헤더가 없다면 커널을 업데이트하고 재부팅한 뒤 다시 실행하세요.
Secure Boot가 켜져 있으면 DKMS 서명 키 등록이 필요할 수 있으며,
설치 스크립트는 Secure Boot를 끄거나 펌웨어 검사를 우회하지 않습니다.

deb만 수동 설치한 경우, 각 사용자 계정에서 `gf63-control-setup`을 한 번 실행하세요.
GNOME·Cinnamon에서는 `gf63-control-setup`이 앱 자동 실행만 등록합니다.

## 확인

```sh
dkms status msi_ec/0.13
lsmod | grep msi
cat /sys/class/power_supply/BAT1/charge_control_end_threshold
systemctl status gf63-lid.service
```

## 제거 / 복원

```sh
gf63-control-setup --restore        # 이 프로그램이 바꾼 사용자 설정 복원
sudo apt-get remove gf63-control msi-ec-dkms
```

`msi-ec-dkms` 제거 시 DKMS 등록도 함께 해제합니다.
카카오톡·Wine 실행 환경·사용자 글꼴은 자동 삭제하지 않습니다.

## 재빌드

소스 저장소에서 `sudo apt install make dpkg-dev python3` 후 일반 사용자로
`make install-deb`를 실행하면 deb 빌드부터 앱·드라이버·번들 글꼴 설치까지 진행합니다.
빌드만 하려면 다음을 실행합니다.

```sh
python3 packaging/build_deb.py
```

결과는 `dist/`에 생성됩니다. 드라이버 소스가 포함되어 있어 빌드 시 GitHub 접속은 필요 없습니다.
커널 모듈은 deb 빌드 시가 아니라 대상 PC에 설치할 때 해당 커널용으로 컴파일됩니다.

## 이 트랙의 제한

- RPM(Rocky 9) 트랙보다 검증이 적습니다.
- Cinnamon에서는 화면 잠금 감지와 OSD 억제까지만 지원합니다.
  Fn키 재매핑·전원 관리자 연동은 XFCE·KDE 전용입니다.
- `tuned`·`nimf-libhangul | ibus-hangul` 등 배포판마다 이름이 다를 수 있는 패키지는
  `Recommends`로 두었습니다. 없으면 설치는 성공하지만 해당 기능은 비활성으로 표시됩니다.
- 한영 전환은 nimf와 IBus를 모두 지원하며 실행 중인 입력기를 판별해 그쪽 GSettings만 바꿉니다.
  HamoniKR 8 기본값인 nimf에서 설정 읽기·쓰기·복원을 확인했고, 물리 키 입력은 미검증입니다.
  nimf는 키 표가 F12까지여서 F13~F20 기능키 전환은 IBus 세션에서만 제공합니다.
- Fcitx 등 그 밖의 입력기는 감지하지 않으며 설정도 바꾸지 않습니다 (미검증).
