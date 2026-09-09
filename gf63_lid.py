#!/usr/bin/python3 -I
"""System lid inhibitor and internal-panel blanking; no session/display access."""
import os
from pathlib import Path
import re
import signal
import socket
import time

PANEL = Path('/sys/class/backlight/intel_backlight/bl_power')
LIDS = Path('/proc/acpi/button/lid')


def lid_closed():
    paths = list(LIDS.glob('*/state'))
    if len(paths) != 1:
        raise RuntimeError('덮개 센서를 하나로 식별할 수 없습니다.')
    match = re.fullmatch(r'state:\s*(open|closed)\s*', paths[0].read_text())
    if not match:
        raise RuntimeError('덮개 상태를 읽을 수 없습니다.')
    return match[1] == 'closed'


class Panel:
    def __init__(self):
        self.original = None

    def update(self, closed):
        current = PANEL.read_text().strip()
        if closed:
            if self.original is None:
                self.original = current
            if current != '4':
                PANEL.write_text('4\n')
            if PANEL.read_text().strip() != '4':
                raise RuntimeError('내장 화면 끄기 검증 실패')
        else:
            self.restore()

    def restore(self):
        if self.original is not None:
            if PANEL.read_text().strip() == '4':
                PANEL.write_text(self.original + '\n')
                if PANEL.read_text().strip() != self.original:
                    raise RuntimeError('내장 화면 복원 검증 실패')
            self.original = None


def main():
    from gi.repository import Gio, GLib
    bus = Gio.bus_get_sync(Gio.BusType.SYSTEM, None)
    result, fds = bus.call_with_unix_fd_list_sync(
        'org.freedesktop.login1', '/org/freedesktop/login1', 'org.freedesktop.login1.Manager',
        'Inhibit', GLib.Variant('(ssss)', ('handle-lid-switch', 'GF63 Control',
        'Keep running with lid closed; blank internal panel', 'block')),
        GLib.VariantType.new('(h)'), Gio.DBusCallFlags.NONE, 8000, None, None)
    fd = fds.get(result.unpack()[0])
    panel = Panel()
    stopping = False

    def stop(*_):
        nonlocal stopping
        stopping = True

    signal.signal(signal.SIGTERM, stop)
    signal.signal(signal.SIGINT, stop)
    try:
        panel.update(lid_closed())
        address = os.environ['NOTIFY_SOCKET']
        if address.startswith('@'):
            address = '\0' + address[1:]
        with socket.socket(socket.AF_UNIX, socket.SOCK_DGRAM) as notify:
            notify.sendto(b'READY=1', address)
        while not stopping:
            panel.update(lid_closed())
            time.sleep(.5)
    finally:
        try:
            panel.restore()
        finally:
            os.close(fd)


if __name__ == '__main__':
    main()
