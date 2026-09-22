PYTHON ?= python3
BUNDLE_BASE = $(shell $(PYTHON) -c 'import runpy; print(runpy.run_path("packaging/build.py")["NAME"])')
BUNDLE_NAME = $(BUNDLE_BASE)-rocky9-x86_64
DEB_BUNDLE_NAME = $(BUNDLE_BASE)-debian-x86_64

.PHONY: help build install install-fonts test check-env build-deb install-deb check-env-deb

help:
	@echo 'make install       [Rocky 9] 앱·글꼴 설치 및 로그인 트레이 자동 실행 등록 (일반 사용자로 실행)'
	@echo 'make install-deb   [Debian 계열] 같은 설치를 deb 패키지로 수행 (일반 사용자로 실행)'
	@echo 'make install-fonts Pretendard · D2Coding · D2Coding Ligature만 설치'
	@echo 'make build         [Rocky 9] RPM·소스·설치 번들 생성 (rpm-build 필요)'
	@echo 'make build-deb     [Debian 계열] deb·소스·설치 번들 생성 (dpkg-dev 필요)'
	@echo 'make check-env     빌드 전 Rocky Linux 9 x86_64 및 rpm-build 설치 여부 점검'
	@echo 'make check-env-deb 빌드 전 Debian 계열 x86_64 및 dpkg-deb 설치 여부 점검'
	@echo 'make test          단위 테스트 실행'

check-env:
	@if [ ! -r /etc/os-release ]; then \
		echo '/etc/os-release를 읽을 수 없습니다. 지원 환경(Rocky Linux 9 x86_64)인지 확인하세요.' >&2; \
		exit 1; \
	fi; \
	. /etc/os-release; \
	if [ "$$ID" != rocky ] || [ "$${VERSION_ID%%.*}" != 9 ] || [ "$$(uname -m)" != x86_64 ]; then \
		echo "make install / make build는 Rocky Linux 9 x86_64 대상입니다. 현재 환경: $${PRETTY_NAME:-알 수 없음} ($$(uname -m))" >&2; \
		case " $${ID:-} $${ID_LIKE:-} " in \
			*" debian "*|*" ubuntu "*) echo 'Debian 계열입니다. make install-deb 또는 make build-deb를 사용하세요.' >&2 ;; \
			*) echo '다른 배포판·아키텍처는 검증되지 않았습니다 (AGENTS.md 참고).' >&2 ;; \
		esac; \
		exit 1; \
	fi; \
	if ! command -v rpmbuild >/dev/null 2>&1; then \
		echo 'rpmbuild가 없습니다: sudo dnf install rpm-build 로 설치하세요.' >&2; \
		exit 1; \
	fi; \
	echo '환경 점검 통과: Rocky Linux 9 x86_64, rpmbuild 확인됨.'

build: check-env
	$(PYTHON) packaging/build.py

install:
	@test "$$(id -u)" != 0 || { echo '일반 사용자로 make install을 실행하세요. sudo를 붙이지 마세요.' >&2; exit 1; }
	$(MAKE) build
	bash "dist/$(BUNDLE_NAME)/install.sh"

check-env-deb:
	@if [ ! -r /etc/os-release ]; then \
		echo '/etc/os-release를 읽을 수 없습니다. 지원 환경(Debian 계열 x86_64)인지 확인하세요.' >&2; \
		exit 1; \
	fi; \
	. /etc/os-release; \
	case " $${ID:-} $${ID_LIKE:-} " in \
		*" debian "*|*" ubuntu "*) ;; \
		*) echo "make install-deb / make build-deb는 Debian·Ubuntu 계열 대상입니다. 현재 환경: $${PRETTY_NAME:-알 수 없음}" >&2; \
			echo 'Rocky Linux 9에서는 make install 또는 make build를 사용하세요.' >&2; \
			exit 1 ;; \
	esac; \
	if [ "$$(uname -m)" != x86_64 ]; then \
		echo "이 프로젝트는 x86_64를 대상으로 합니다. 현재 아키텍처: $$(uname -m)" >&2; \
		exit 1; \
	fi; \
	if ! command -v dpkg-deb >/dev/null 2>&1; then \
		echo 'dpkg-deb가 없습니다: sudo apt install dpkg-dev 로 설치하세요.' >&2; \
		exit 1; \
	fi; \
	echo "환경 점검 통과: $${PRETTY_NAME:-Debian 계열} x86_64, dpkg-deb 확인됨."

build-deb: check-env-deb
	$(PYTHON) packaging/build_deb.py

install-deb:
	@test "$$(id -u)" != 0 || { echo '일반 사용자로 make install-deb를 실행하세요. sudo를 붙이지 마세요.' >&2; exit 1; }
	$(MAKE) build-deb
	bash "dist/$(DEB_BUNDLE_NAME)/install.sh"

install-fonts:
	$(PYTHON) install_fonts.py

test:
	$(PYTHON) -m unittest -v
