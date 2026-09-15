PYTHON ?= python3
BUNDLE_NAME = $(shell $(PYTHON) -c 'import runpy; print(runpy.run_path("packaging/build.py")["NAME"])')-rocky9-x86_64

.PHONY: help build install install-fonts test

help:
	@echo 'make install       앱·글꼴 설치 및 로그인 트레이 자동 실행 등록 (일반 사용자로 실행)'
	@echo 'make install-fonts Pretendard · D2Coding · D2Coding Ligature만 설치'
	@echo 'make build         RPM·소스·설치 번들 생성 (rpm-build 필요)'
	@echo 'make test          단위 테스트 실행'

build:
	$(PYTHON) packaging/build.py

install:
	@test "$$(id -u)" != 0 || { echo '일반 사용자로 make install을 실행하세요. sudo를 붙이지 마세요.' >&2; exit 1; }
	$(MAKE) build
	bash "dist/$(BUNDLE_NAME)/install.sh"

install-fonts:
	$(PYTHON) install_fonts.py

test:
	$(PYTHON) -m unittest -v
