"""Translate only explicit XFCE shortcuts; never hook arbitrary keyboard input."""
import desktop_env
import configure_mac
import subprocess
import sys

GENERAL = {'copy': 'ctrl+c', 'paste': 'ctrl+v', 'cut': 'ctrl+x', 'select-all': 'ctrl+a',
           'undo': 'ctrl+z', 'redo': 'ctrl+shift+z', 'save': 'ctrl+s', 'find': 'ctrl+f',
           'new-tab': 'ctrl+t', 'close-tab': 'ctrl+w'}
TERMINAL = {'copy': 'ctrl+shift+c', 'paste': 'ctrl+shift+v',
            'new-tab': 'ctrl+shift+t', 'close-tab': 'ctrl+shift+w'}
TERMINALS = {'xfce4-terminal', 'xterm', 'uxterm', 'gnome-terminal', 'gnome-terminal-server',
             'konsole', 'kitty', 'alacritty', 'terminator', 'tilix', 'org.wezfurlong.wezterm'}


def run(*args):
    return subprocess.run(args, check=True, text=True, capture_output=True, timeout=3).stdout.strip()


def locked():
    return desktop_env.locked()


def sequence(action, window_class, terminal_mode='clipboard'):
    if action not in GENERAL:
        raise ValueError('지원하지 않는 Mac 단축키입니다.')
    if terminal_mode not in configure_mac.TERMINAL_MODES:
        raise ValueError('지원하지 않는 터미널 단축키 모드입니다.')
    if window_class.lower() in TERMINALS:
        if terminal_mode == 'disabled':
            return None
        if terminal_mode == 'clipboard':
            if window_class.lower() == 'xfce4-terminal':
                return dict(TERMINAL, **{'select-all': 'ctrl+shift+a', 'find': 'ctrl+shift+f'}).get(action)
            if window_class.lower() == 'konsole':
                return dict(TERMINAL, find='ctrl+shift+f').get(action)
            return TERMINAL.get(action)
    return GENERAL[action]


def dispatch(action):
    if action not in GENERAL:
        raise ValueError('지원하지 않는 Mac 단축키입니다.')
    if not desktop_env.x11() or locked():
        return
    window = run('xdotool', 'getactivewindow')
    window_class = run('xdotool', 'getwindowclassname', window)
    key = sequence(action, window_class, configure_mac.terminal_mode())
    if key is None:
        return
    # A focus change while launching the shortcut must not target a different app.
    if locked() or run('xdotool', 'getactivewindow') != window:
        return
    run('xdotool', 'key', '--clearmodifiers', '--delay', '0', key)


def main():
    try:
        if len(sys.argv) != 2:
            raise ValueError('단축키 동작 하나가 필요합니다.')
        dispatch(sys.argv[1])
        return 0
    except (OSError, ValueError, subprocess.SubprocessError) as exc:
        print(str(exc), file=sys.stderr)
        return 1


if __name__ == '__main__':
    sys.exit(main())
