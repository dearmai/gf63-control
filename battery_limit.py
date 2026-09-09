#!/usr/bin/python3
"""Terminal battery charge control using the kernel power_supply interface."""
import argparse
import json
import os
from pathlib import Path
import sys

POWER = Path('/sys/class/power_supply')
END = 'charge_control_end_threshold'
START = 'charge_control_start_threshold'


class ControlError(Exception):
    pass


def read(path):
    try:
        return path.read_text().strip()
    except FileNotFoundError:
        return None


def select_battery(root=POWER, name=None):
    batteries = [p for p in sorted(root.iterdir())
                 if read(p / 'type') == 'Battery'
                 and read(p / 'scope') != 'Device'
                 and (p / 'capacity').exists()]
    if name is not None:
        batteries = [p for p in batteries if p.name == name]
    supported = [p for p in batteries if (p / END).exists()]
    candidates = supported or batteries
    if not candidates:
        raise ControlError('노트북 배터리를 찾을 수 없습니다.')
    if len(candidates) != 1:
        raise ControlError('배터리가 여러 개입니다. --battery 이름으로 지정하세요.')
    return candidates[0]


def status(battery, root=POWER):
    return {
        'battery': battery.name,
        'capacity': read(battery / 'capacity'),
        'status': read(battery / 'status'),
        'ac_online': any(read(p / 'online') == '1' for p in root.iterdir()
                         if read(p / 'type') == 'Mains'),
        'start_threshold': read(battery / START),
        'end_threshold': read(battery / END),
        'supported': (battery / END).exists(),
    }


def show(data):
    states = {'Not charging': '충전 안 함', 'Charging': '충전 중',
              'Discharging': '배터리 사용 중', 'Full': '완충'}
    print(f"배터리: {data['battery']} · 잔량: {data['capacity']}%")
    print(f"어댑터: {'연결됨' if data['ac_online'] else '연결 안 됨'} · "
          f"상태: {states.get(data['status'], data['status'])}")
    if data['supported']:
        print(f"충전 시작 기준: {data['start_threshold'] or '알 수 없음'}% · "
              f"충전 상한: {data['end_threshold']}%")
    else:
        print('충전 제한 인터페이스 없음: 호환되는 msi-ec 드라이버가 필요합니다.')


def set_limit(battery, value):
    if not 10 <= value <= 100:
        raise ControlError('충전 상한은 10~100 사이의 정수여야 합니다.')
    target = battery / END
    if not target.exists():
        raise ControlError('충전 제한을 지원하는 드라이버가 없습니다. '
                           'sudo modprobe msi-ec 실행 후 다시 확인하세요.')
    # Read before writing: fail closed if the interface cannot be read.
    previous = read(target)
    if previous is None:
        raise ControlError('충전 상한을 읽을 수 없습니다.')
    if previous == str(value):
        return False
    if os.geteuid() != 0:
        raise ControlError(f'변경에는 관리자 권한이 필요합니다: '
                           f'sudo battery-limit --battery {battery.name} set {value}')
    target.write_text(f'{value}\n')
    actual = read(target)
    if actual != str(value):
        raise ControlError(f'변경 검증 실패: 요청 {value}%, 실제 {actual}%. '
                           'battery-limit status로 확인하세요.')
    return True


def menu(battery):
    while True:
        show(status(battery))
        print('\n1) 60%  2) 80%  3) 100%  4) 직접 입력  5) 새로고침  0) 종료')
        choice = input('선택: ').strip()
        if choice in ('0', 'q', 'quit'):
            return
        if choice == '5':
            continue
        values = {'1': 60, '2': 80, '3': 100}
        if choice == '4':
            try:
                value = int(input('충전 상한 (10~100): '))
            except ValueError:
                print('정수를 입력하세요.\n')
                continue
        elif choice in values:
            value = values[choice]
        else:
            print('메뉴 번호를 입력하세요.\n')
            continue
        try:
            changed = set_limit(battery, value)
            print('설정을 적용하고 확인했습니다.\n' if changed else '이미 같은 설정입니다.\n')
        except (ControlError, OSError) as exc:
            print(f'오류: {exc}\n', file=sys.stderr)


def main():
    parser = argparse.ArgumentParser(description='배터리 충전 상한 조회 및 설정')
    parser.add_argument('--battery', help='배터리 이름 (예: BAT1)')
    sub = parser.add_subparsers(dest='command')
    query = sub.add_parser('status', help='현재 상태 조회')
    query.add_argument('--json', action='store_true', help='JSON 출력')
    change = sub.add_parser('set', help='충전 상한 설정 (10~100)')
    change.add_argument('percent', type=int)
    sub.add_parser('menu', help='대화형 메뉴')
    args = parser.parse_args()
    try:
        battery = select_battery(name=args.battery)
        command = args.command or ('menu' if sys.stdin.isatty() else 'status')
        if command == 'menu':
            menu(battery)
        elif command == 'set':
            changed = set_limit(battery, args.percent)
            print('설정을 적용하고 확인했습니다.' if changed else '이미 같은 설정입니다.')
            show(status(battery))
        else:
            data = status(battery)
            if getattr(args, 'json', False):
                print(json.dumps(data, ensure_ascii=False))
            else:
                show(data)
        return 0
    except (ControlError, OSError) as exc:
        print(f'오류: {exc}', file=sys.stderr)
        return 1
    except (KeyboardInterrupt, EOFError):
        print()
        return 0


if __name__ == '__main__':
    sys.exit(main())
