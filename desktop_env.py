"""Desktop-specific session services, independent of hardware control."""
import os


def kind():
    names = (os.environ.get('XDG_CURRENT_DESKTOP', '') + ':' +
             os.environ.get('XDG_SESSION_DESKTOP', '')).lower().split(':')
    if any(name in ('kde', 'plasma', 'plasmawayland', 'plasmax11') for name in names):
        return 'kde'
    if any(name in ('cinnamon', 'x-cinnamon') for name in names):
        return 'cinnamon'
    if 'xfce' in names or not any(names):
        return 'xfce'
    return 'unsupported'


def x11():
    return os.environ.get('XDG_SESSION_TYPE') != 'wayland' and not os.environ.get('WAYLAND_DISPLAY')


def require_shortcuts():
    if kind() not in ('xfce', 'kde'):
        raise RuntimeError('Mac 단축키는 XFCE 또는 KDE Plasma에서 지원합니다.')
    if not x11():
        raise RuntimeError('Mac 단축키 변환은 X11 전용입니다. Plasma (X11) 세션에서 사용하세요.')


def screensaver():
    if kind() == 'kde':
        return 'org.freedesktop.ScreenSaver', '/ScreenSaver', 'org.freedesktop.ScreenSaver'
    if kind() == 'cinnamon':
        return 'org.cinnamon.ScreenSaver', '/org/cinnamon/ScreenSaver', 'org.cinnamon.ScreenSaver'
    return 'org.xfce.ScreenSaver', '/org/xfce/ScreenSaver', 'org.xfce.ScreenSaver'


def call(service, path, interface, method, signature=None, values=()):
    from gi.repository import Gio, GLib
    bus = Gio.bus_get_sync(Gio.BusType.SESSION, None)
    return bus.call_sync(service, path, interface, method,
                         GLib.Variant(signature, values) if signature else None,
                         None, Gio.DBusCallFlags.NONE, 5000, None).unpack()


def locked():
    try:
        return bool(call(*screensaver(), 'GetActive')[0])
    except Exception:
        return True
