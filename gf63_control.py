#!/usr/bin/python3
"""GF63 GTK control panel and single-instance OSD service."""
import concurrent.futures
import json
import importlib
from pathlib import Path
import sys
import gi
gi.require_version('Gtk', '3.0')
from gi.repository import Gtk, Gdk, Gio, GLib
import gf63_core as core
import configure_keyboard as keyboard
import configure_mac as mac
import configure_cinnamon as cinnamon
import desktop_env
import configure_fonts as fonts
import install_programs as programs
import install_graphics as graphics


class Control(Gtk.Application):
    KEYBOARD_NOTE = ('한/영 또는 Caps Lock 키로 한국어와 영어를 전환합니다.\n'
                     'Caps Lock의 대문자 고정 기능은 해제됩니다.\n'
                     '기능키를 추가 선택한 뒤 적용하세요. 기존 앱 단축키와 겹칠 수 있습니다.\n'
                     '{label}에서 한글 입력기를 선택한 상태에서 사용하세요.')

    def __init__(self):
        super().__init__(application_id='local.gf63.Control', flags=Gio.ApplicationFlags.HANDLES_COMMAND_LINE)
        self.pool = concurrent.futures.ThreadPoolExecutor(max_workers=1)
        self.program_pool = concurrent.futures.ThreadPoolExecutor(max_workers=1)
        self.pending = False
        self.state = {}
        self.window = None
        self.labels = {}
        self.controls = {}
        self.osd = None
        self.hide_timer = 0
        self.osd_enabled = True
        self.preferences = Path.home() / '.config/gf63-control/preferences.json'
        try:
            self.osd_enabled = bool(json.loads(self.preferences.read_text()).get('osd', True))
        except (OSError, ValueError, AttributeError):
            pass
        self.screen_active = True
        self.events = []
        self.action_queue = []

    def do_startup(self):
        Gtk.Application.do_startup(self)
        self.hold()
        self.create_tray()
        self.bus = Gio.bus_get_sync(Gio.BusType.SESSION, None)
        saver_service, saver_path, saver_interface = desktop_env.screensaver()
        self.bus.signal_subscribe(saver_service, saver_interface,
                                  'ActiveChanged', saver_path, None,
                                  Gio.DBusSignalFlags.NONE, self.screensaver_changed)
        try:
            result = self.bus.call_sync(saver_service, saver_path,
                saver_interface, 'GetActive', None, GLib.VariantType.new('(b)'),
                Gio.DBusCallFlags.NO_AUTO_START, 1000, None)
            self.screen_active = result.unpack()[0]
        except GLib.Error:
            pass
        GLib.timeout_add(1000, self.poll)
        self.poll()

    def screensaver_changed(self, connection, sender, path, interface, signal, parameters, *unused):
        self.screen_active = parameters.unpack()[0]
        if self.screen_active and self.osd:
            self.osd.hide()

    def save_osd(self, widget):
        self.osd_enabled = widget.get_active()
        try:
            self.preferences.parent.mkdir(parents=True, exist_ok=True)
            self.preferences.write_text(json.dumps({'osd': self.osd_enabled}))
        except OSError as exc:
            self.message.set_text('설정 저장 실패: ' + str(exc))

    def do_command_line(self, command_line):
        args = command_line.get_arguments()[1:]
        if args == ['--quit']:
            self.quit()
        elif args == ['--background']:
            pass
        elif args == ['--test-osd']:
            self.popup('OSD 미리보기', '화면 밝기 60%', .6)
        elif len(args) == 2 and args[0] == '--action':
            self.action(args[1])
        elif not args:
            self.activate()
        else:
            command_line.printerr('사용법: gf63-control [--background|--test-osd|--action 기능|--quit]\n')
            return 2
        return 0

    def create_tray(self):
        # An explicit, full-colour asset also works on dark panel themes.
        icon_path = str(Path(__file__).resolve().with_name('gf63-control.svg'))
        self.tray_menu_widget = self.build_tray_menu()
        for namespace in ('AyatanaAppIndicator3', 'AppIndicator3'):
            try:
                gi.require_version(namespace, '0.1')
                indicator = importlib.import_module('gi.repository.' + namespace)
            except (ValueError, ImportError):
                continue
            self.tray = indicator.Indicator.new(
                'gf63-control', icon_path, indicator.IndicatorCategory.HARDWARE)
            self.tray.set_title('GF63 Control · 노트북 제어')
            self.tray.set_menu(self.tray_menu_widget)
            self.tray.set_status(indicator.IndicatorStatus.ACTIVE)
            return
        # Keep classic XFCE installations working without an indicator library.
        self.tray = Gtk.StatusIcon.new_from_file(icon_path)
        self.tray.set_tooltip_text('GF63 Control · 노트북 제어')
        self.tray.connect('activate', lambda *_: self.activate())
        self.tray.connect('popup-menu', self.tray_menu)

    def build_tray_menu(self):
        menu = Gtk.Menu()
        for text, callback in [('제어판 열기', lambda *_: self.activate()), ('프로그램 종료', lambda *_: self.quit())]:
            item = Gtk.MenuItem(label=text)
            item.connect('activate', callback)
            menu.append(item)
        menu.show_all()
        return menu

    def tray_menu(self, icon, button, time):
        self.tray_menu_widget.popup(None, None, None, None, button, time)

    def do_activate(self):
        if self.window is None:
            self.build_window()
        self.window.show_all()
        self.window.present()
        self.keyboard_settings()
        self.capture_settings()
        self.mac_settings()
        self.font_settings()
        self.program_settings()
        self.graphics_settings()

    def add_section(self, box, title):
        label = Gtk.Label()
        label.set_markup(f'<b>{title}</b>')
        label.set_xalign(0)
        label.set_margin_top(14)
        box.pack_start(label, False, False, 4)

    def row(self, box, key, buttons):
        row = Gtk.Box(spacing=10)
        name = Gtk.Label(label=core.LABELS[key], xalign=0)
        name.set_size_request(125, -1)
        row.pack_start(name, False, False, 0)
        label = Gtk.Label(label='확인 중…', xalign=0)
        row.pack_start(label, True, True, 0)
        self.labels[key] = label
        self.controls[key] = []
        for text, action, value in buttons:
            button = Gtk.Button(label=text)
            button.connect('clicked', lambda _, a=action, v=value: self.action(a, v))
            row.pack_start(button, False, False, 0)
            self.controls[key].append(button)
        box.pack_start(row, False, False, 6)

    def build_window(self):
        self.window = Gtk.ApplicationWindow(application=self)
        self.window.set_title('GF63 Control')
        self.window.set_default_size(730, 690)
        self.window.connect('delete-event', lambda win, _: win.hide() or True)
        header = Gtk.HeaderBar(title='GF63 Control', subtitle='MSI Thin GF63 · 노트북 제어')
        header.set_show_close_button(True)
        self.window.set_titlebar(header)
        notebook = Gtk.Notebook()
        self.window.add(notebook)
        scroll = Gtk.ScrolledWindow()
        scroll.set_policy(Gtk.PolicyType.NEVER, Gtk.PolicyType.AUTOMATIC)
        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=2, margin=20)
        scroll.add(box)
        notebook.append_page(scroll, Gtk.Label(label='노트북 제어'))
        self.summary = Gtk.Label(label='상태 확인 중…', xalign=0)
        box.pack_start(self.summary, False, False, 6)
        self.add_section(box, '배터리 보호')
        self.row(box, 'battery', [('60%', 'battery', 60), ('80%', 'battery', 80), ('100%', 'battery', 100)])
        custom = Gtk.Box(spacing=10)
        self.limit = Gtk.SpinButton.new_with_range(10, 100, 1)
        self.limit.set_value(60)
        custom.pack_start(Gtk.Label(label='직접 지정'), False, False, 0)
        custom.pack_start(self.limit, False, False, 0)
        apply_button = Gtk.Button(label='충전 상한 적용')
        apply_button.connect('clicked', lambda _: self.action('battery', self.limit.get_value_as_int()))
        self.controls['battery'].append(apply_button)
        custom.pack_start(apply_button, False, False, 0)
        box.pack_start(custom, False, False, 3)
        note = Gtk.Label(label='충전은 상한보다 10% 낮은 기준에서 재개됩니다.', xalign=0)
        box.pack_start(note, False, False, 4)
        self.add_section(box, '화면과 소리')
        self.row(box, 'brightness', [('−', 'brightness-down', None), ('+', 'brightness-up', None)])
        self.row(box, 'volume', [('−', 'volume-down', None), ('+', 'volume-up', None), ('음소거', 'mute', None)])
        self.row(box, 'microphone', [('음소거 전환', 'mic-mute', None)])
        self.add_section(box, '키보드와 장치')
        self.row(box, 'keyboard', [('끄기', 'keyboard', 0), ('1', 'keyboard', 1), ('2', 'keyboard', 2), ('3', 'keyboard', 3)])
        self.row(box, 'touchpad', [('켜기 / 끄기', 'touchpad', None)])
        self.row(box, 'webcam', [('켜기 / 끄기', 'webcam', None)])
        self.row(box, 'cooler_boost', [('켜기 / 끄기', 'cooler_boost', None)])
        self.message = Gtk.Label(label='', xalign=0)
        self.message.set_line_wrap(True)
        self.message.set_max_width_chars(70)
        box.pack_start(self.message, False, False, 10)

        power = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=14, margin=20)
        power_scroll = Gtk.ScrolledWindow()
        power_scroll.set_policy(Gtk.PolicyType.NEVER, Gtk.PolicyType.AUTOMATIC)
        power_scroll.add(power)
        notebook.append_page(power_scroll, Gtk.Label(label='전원 모드'))
        self.add_section(power, '덮개를 닫아도 전원 유지')
        self.row(power, 'lid', [('켜기', 'lid', 'on'), ('끄기 / 복원', 'lid', 'off')])
        lid_note = Gtk.Label(label='전원 연결·배터리 모두 적용됩니다. 덮개를 닫으면 내장 화면을 끄고,\n'
                                  '열면 화면 전원 상태를 복원합니다. 재부팅 후에도 유지됩니다.\n'
                                  '수동 절전·유휴 절전·배터리 부족 동작과 화면 잠금은 기존 설정을 따릅니다.', xalign=0)
        lid_note.set_line_wrap(True)
        power.pack_start(lid_note, False, False, 0)
        self.lid_message = Gtk.Label(xalign=0)
        self.lid_message.set_line_wrap(True)
        self.lid_message.set_max_width_chars(65)
        power.pack_start(self.lid_message, False, False, 0)
        self.row(power, 'power', [('저소음', 'power', 'quiet'), ('일반', 'power', 'balanced'), ('성능', 'power', 'performance')])
        self.power_summary = Gtk.Label(xalign=0)
        self.power_summary.set_line_wrap(True)
        power.pack_start(self.power_summary, False, False, 0)
        modes = Gtk.Label(label='저소음: 절전 우선 · CPU 상한 60% · 터보 끄기 · 저소음 팬\n'
                               '일반: 균형 정책 · CPU 상한 100% · 터보 켜기 · 자동 팬\n'
                               '성능: 성능 우선 · CPU 상한 100% · 터보 켜기 · 자동 팬', xalign=0)
        modes.set_line_wrap(True)
        power.pack_start(modes, False, False, 0)
        self.add_section(power, '세부 설정')
        self.epp = Gtk.ComboBoxText()
        for key, text in [('power', '절전 우선'), ('balance_power', '균형 / 절전'),
                          ('balance_performance', '균형 / 성능'), ('performance', '성능 우선')]:
            self.epp.append(key, text)
        self.epp.set_active_id('balance_performance')
        self.cpu_max = Gtk.SpinButton.new_with_range(20, 100, 5)
        self.cpu_max.set_value(100)
        self.turbo = Gtk.CheckButton(label='CPU 터보 부스트 허용')
        self.turbo.set_active(True)
        self.fan = Gtk.ComboBoxText()
        self.fan.append('auto', '자동 팬')
        self.fan.append('silent', '저소음 팬')
        self.fan.set_active_id('auto')
        self.boost = Gtk.CheckButton(label='Cooler Boost (최대 냉각)')
        for title, widget in [('CPU 전력 / 성능 정책', self.epp), ('CPU 성능 상한 (%)', self.cpu_max),
                              ('팬 제어', self.fan)]:
            row = Gtk.Box(spacing=12)
            row.pack_start(Gtk.Label(label=title, xalign=0), True, True, 0)
            row.pack_start(widget, False, False, 0)
            power.pack_start(row, False, False, 0)
        power.pack_start(self.turbo, False, False, 0)
        power.pack_start(self.boost, False, False, 0)
        actions = Gtk.Box(spacing=12)
        load = Gtk.Button(label='현재 값 불러오기')
        load.connect('clicked', self.load_power)
        apply_power = Gtk.Button(label='세부 설정 적용')
        apply_power.connect('clicked', lambda _: self.action('power', {
            'mode': 'custom', 'epp': self.epp.get_active_id(), 'max': self.cpu_max.get_value_as_int(),
            'turbo': self.turbo.get_active(), 'fan': self.fan.get_active_id(), 'boost': self.boost.get_active()}))
        self.controls['power'].append(apply_power)
        actions.pack_start(load, True, True, 0)
        actions.pack_start(apply_power, True, True, 0)
        power.pack_start(actions, False, False, 0)
        note = Gtk.Label(label='설정은 TuneD에 저장되어 재부팅 후에도 적용됩니다.\n'
                              'CPU 상한은 사용률 제한이 아닌 성능 상태 제한입니다.\n'
                              '저소음은 무소음을 보장하지 않으며 팬은 온도에 따라 동작합니다.\n'
                              '팬 RPM 곡선·GPU 전력 한도는 현재 드라이버에서 제공하지 않습니다.', xalign=0)
        note.set_line_wrap(True)
        power.pack_start(note, False, False, 0)

        settings = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=12, margin=20)
        settings_scroll = Gtk.ScrolledWindow()
        settings_scroll.set_policy(Gtk.PolicyType.NEVER, Gtk.PolicyType.AUTOMATIC)
        settings_scroll.add(settings)
        notebook.append_page(settings_scroll, Gtk.Label(label='기능키 · OSD'))
        self.add_section(settings, 'KDE · GNOME · Konsole 글꼴')
        font_note = Gtk.Label(label='KDE·GNOME 일반 글꼴: Pretendard · 고정폭: D2Coding\n'
                                   '패키지에 포함된 글꼴을 오프라인으로 설치합니다. Konsole은 11pt입니다.\n'
                                   '적용·복원 후 다시 로그인하고 Konsole을 재시작하세요.', xalign=0)
        font_note.set_line_wrap(True)
        settings.pack_start(font_note, False, False, 0)
        self.font_status = Gtk.Label(label='설정 확인 중…', xalign=0)
        self.font_status.set_line_wrap(True)
        self.font_status.set_max_width_chars(65)
        settings.pack_start(self.font_status, False, False, 0)
        font_buttons = Gtk.Box(spacing=8)
        self.font_buttons = []
        self.font_busy = False
        for title, operation in [('설치 및 적용', 'apply'), ('원래 글꼴 복원', 'restore'), ('상태 확인', 'status')]:
            button = Gtk.Button(label=title)
            button.connect('clicked', lambda _, op=operation: self.font_settings(op))
            font_buttons.pack_start(button, False, False, 0)
            self.font_buttons.append(button)
        settings.pack_start(font_buttons, False, False, 0)
        startup_buttons = Gtk.Box(spacing=8)
        for title, operation in [('GNOME 로그인 시 적용 켜기', 'enable-startup'),
                                 ('로그인 시 적용 끄기', 'disable-startup')]:
            button = Gtk.Button(label=title)
            button.connect('clicked', lambda _, op=operation: self.font_settings(op))
            startup_buttons.pack_start(button, False, False, 0)
            self.font_buttons.append(button)
        settings.pack_start(startup_buttons, False, False, 0)
        self.add_section(settings, 'Mac 스타일 단축키')
        mac_note = Gtk.Label(label='Windows(Super) 키를 Command처럼 사용합니다.\n'
                                  'Super+C/V/X/A/Z/S/F/T/W · Shift+Super+Z 다시 실행\n'
                                  'Super+Tab 창 전환 · Shift+Super+Tab 역순 · Super+Space 실행기\n'
                                  '터미널 동작은 아래에서 선택할 수 있습니다.\n'
                                  '기존 Ctrl 및 GF63 단축키는 유지됩니다.', xalign=0)
        mac_note.set_line_wrap(True)
        settings.pack_start(mac_note, False, False, 0)
        self.mac_terminal = Gtk.CheckButton(label='터미널에도 Mac 스타일 적용 (Super+C/V 복사·붙여넣기)')
        self.mac_terminal.set_active(True)
        settings.pack_start(self.mac_terminal, False, False, 0)
        terminal_note = Gtk.Label(label='호환성 문제가 있으면 터미널 적용만 해제할 수 있습니다.\n'
                                       '전체를 끄려면 원래 단축키 복원을 누르세요.\n'
                                       '선택을 바꾼 후 Mac 스타일 적용을 누르면 저장됩니다.', xalign=0)
        terminal_note.set_line_wrap(True)
        settings.pack_start(terminal_note, False, False, 0)
        self.mac_status = Gtk.Label(label='설정 확인 중…', xalign=0)
        self.mac_status.set_line_wrap(True)
        self.mac_status.set_max_width_chars(65)
        settings.pack_start(self.mac_status, False, False, 0)
        mac_buttons = Gtk.Box(spacing=8)
        self.mac_buttons = []
        self.mac_busy = False
        for title, operation in [('Mac 스타일 적용', 'apply'), ('원래 단축키 복원', 'restore'),
                                 ('상태 확인', 'status')]:
            button = Gtk.Button(label=title)
            button.connect('clicked', lambda _, op=operation: self.mac_settings(op))
            mac_buttons.pack_start(button, False, False, 0)
            self.mac_buttons.append(button)
        settings.pack_start(mac_buttons, False, False, 0)
        self.add_section(settings, '한영 전환')
        self.keyboard_note = Gtk.Label(label=self.KEYBOARD_NOTE.format(label='한글 입력기'),
                                       xalign=0)
        self.keyboard_note.set_line_wrap(True)
        settings.pack_start(self.keyboard_note, False, False, 0)
        function_grid = Gtk.Grid(column_spacing=8, row_spacing=4)
        self.keyboard_function_keys = {}
        for index, key in enumerate(keyboard.FUNCTION_KEYS):
            toggle = Gtk.CheckButton(label=key)
            self.keyboard_function_keys[key] = toggle
            function_grid.attach(toggle, index % 5, index // 5, 1, 1)
        settings.pack_start(function_grid, False, False, 0)
        self.keyboard_status = Gtk.Label(label='설정 확인 중…', xalign=0)
        self.keyboard_status.set_line_wrap(True)
        self.keyboard_status.set_max_width_chars(65)
        settings.pack_start(self.keyboard_status, False, False, 0)
        keyboard_buttons = Gtk.Box(spacing=8)
        self.keyboard_buttons = []
        self.keyboard_busy = False
        for title, operation in [('선택한 한영 전환 키 적용', 'apply'),
                                 ('원래 키 설정 복원', 'restore'), ('상태 확인', 'status')]:
            button = Gtk.Button(label=title)
            button.connect('clicked', lambda _, op=operation: self.keyboard_settings(op))
            keyboard_buttons.pack_start(button, False, False, 0)
            self.keyboard_buttons.append(button)
        settings.pack_start(keyboard_buttons, False, False, 0)
        self.build_capture_section(settings)
        self.add_section(settings, '기능키와 OSD')
        explanation = Gtk.Label(xalign=0)
        explanation.set_text('밝기·음량·음소거·마이크·키보드 조명 키를 연결합니다.\n'
                             '웹캠·팬·터치패드처럼 펌웨어나 XFCE가 처리한 변화도 표시합니다.\n'
                             'Fn 조합이 OS에 전달되지 않으면 아래 대체 단축키를 사용하세요.')
        explanation.set_line_wrap(True)
        settings.pack_start(explanation, False, False, 0)
        shortcuts = Gtk.Label(xalign=0)
        shortcuts.set_text('Super + F5    웹캠 전환\nSuper + F6    터치패드 전환\n'
                           'Super + F8    팬 부스트 전환\nSuper + F9    마이크 음소거\n'
                           'Super + F10  제어판 열기\n\n'
                           'Super는 Windows 로고 키입니다.\n'
                           'Fn 키 자체는 보통 OS에 독립 키로 전달되지 않습니다.')
        settings.pack_start(shortcuts, False, False, 0)
        check = Gtk.CheckButton(label='상태 변화 시 OSD 표시')
        check.set_active(self.osd_enabled)
        check.connect('toggled', self.save_osd)
        settings.pack_start(check, False, False, 0)
        preview = Gtk.Button(label='OSD 미리보기')
        preview.connect('clicked', lambda _: self.popup('OSD 미리보기', '화면 밝기 60%', .6))
        settings.pack_start(preview, False, False, 0)
        info = Gtk.Label(label='창을 닫아도 트레이에서 실행됩니다. 로그인 시 자동 시작합니다.\n'
                              '완전히 종료하려면 트레이 메뉴의 프로그램 종료를 선택하세요.', xalign=0)
        info.set_line_wrap(True)
        settings.pack_start(info, False, False, 0)
        self.history = Gtk.Label(label='최근 상태 변화가 여기에 표시됩니다.', xalign=0)
        self.history.set_selectable(True)
        settings.pack_start(self.history, False, False, 0)
        self.build_program_tab(notebook)
        self.update_ui()

    def build_program_tab(self, notebook):
        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=16, margin=20)
        scroll = Gtk.ScrolledWindow()
        scroll.set_policy(Gtk.PolicyType.NEVER, Gtk.PolicyType.AUTOMATIC)
        scroll.add(box)
        notebook.append_page(scroll, Gtk.Label(label='프로그램 설치'))
        self.add_section(box, '카카오톡 (Wine)')
        note = Gtk.Label(label='Windows 카카오톡을 이 컴퓨터에서 실행합니다.\n'
                               'Wine 실행 환경, 공식 카카오톡, 한글 글꼴과 앱 메뉴를 설정합니다.\n'
                               '인터넷 연결이 필요하며 첫 설치에는 수 분과 수 GB의 공간이 필요합니다.\n'
                               '설치 후 카카오 계정 로그인은 직접 진행하세요.', xalign=0)
        note.set_line_wrap(True)
        box.pack_start(note, False, False, 0)
        link = Gtk.LinkButton.new_with_label('https://www.kakaocorp.com/page/service/all', '카카오톡 공식 다운로드 안내')
        link.set_halign(Gtk.Align.START)
        box.pack_start(link, False, False, 0)
        self.program_status = Gtk.Label(label='설치 상태 확인 중…', xalign=0)
        self.program_status.set_line_wrap(True)
        self.program_status.set_max_width_chars(65)
        self.program_status.set_selectable(True)
        box.pack_start(self.program_status, False, False, 0)
        self.program_spinner = Gtk.Spinner()
        self.program_spinner.set_halign(Gtk.Align.START)
        box.pack_start(self.program_spinner, False, False, 0)
        buttons = Gtk.Box(spacing=8)
        self.program_buttons = []
        self.program_busy = False
        for title, operation in [('설치 / 설정 복구', 'install'), ('카카오톡 실행', 'launch'), ('상태 확인', 'status')]:
            button = Gtk.Button(label=title)
            button.connect('clicked', lambda _, op=operation: self.program_settings(op))
            buttons.pack_start(button, False, False, 0)
            self.program_buttons.append(button)
        box.pack_start(buttons, False, False, 0)

        font_buttons = Gtk.Box(spacing=8)
        for title, operation in [('Pretendard · 글꼴 다듬기 적용', 'fonts'), ('Wine 설정 열기', 'wine-settings')]:
            button = Gtk.Button(label=title)
            button.connect('clicked', lambda _, op=operation: self.program_settings(op))
            font_buttons.pack_start(button, False, False, 0)
            self.program_buttons.append(button)
        box.pack_start(font_buttons, False, False, 0)
        note = Gtk.Label(label='글꼴만 적용하면 카카오톡을 재설치하지 않습니다.\n'
                               '영문·한글 UI는 Pretendard로, 글꼴 다듬기는 ClearType RGB로 설정합니다.\n'
                               '적용 후 카카오톡을 트레이에서도 완전히 종료하고 다시 실행하세요.', xalign=0)
        note.set_line_wrap(True)
        box.pack_start(note, False, False, 0)
        self.build_graphics_section(box)

    def build_graphics_section(self, box):
        self.add_section(box, 'NVIDIA 그래픽 드라이버')
        note = Gtk.Label(label='내장 Intel 그래픽과 함께 쓰는 NVIDIA 드라이버를 설치합니다.\n'
                               '설치는 관리자 권한이 필요하므로 제어판이 아닌 터미널에서 진행합니다.\n'
                               '터미널에 표시되는 내용을 확인하고 관리자 암호를 입력하세요.\n'
                               '설치 후에는 재부팅해야 새 드라이버로 전환됩니다.', xalign=0)
        note.set_line_wrap(True)
        box.pack_start(note, False, False, 0)
        self.graphics_status = Gtk.Label(label='그래픽 드라이버 상태 확인 중…', xalign=0)
        self.graphics_status.set_line_wrap(True)
        self.graphics_status.set_max_width_chars(65)
        self.graphics_status.set_selectable(True)
        box.pack_start(self.graphics_status, False, False, 0)
        buttons = Gtk.Box(spacing=8)
        self.graphics_buttons = []
        self.graphics_busy = False
        for title, operation in [('터미널에서 설치', 'install'), ('명령 복사', 'copy'),
                                 ('상태 확인', 'status')]:
            button = Gtk.Button(label=title)
            button.connect('clicked', lambda _, op=operation: self.graphics_settings(op))
            buttons.pack_start(button, False, False, 0)
            self.graphics_buttons.append(button)
        box.pack_start(buttons, False, False, 0)

    def program_settings(self, operation='status'):
        if self.program_busy:
            return
        self.program_busy = True
        for button in self.program_buttons:
            button.set_sensitive(False)
        self.program_spinner.start()
        self.program_status.set_text('설치 상태 확인 중…' if operation == 'status' else '처리 중…')
        def progress(message):
            GLib.idle_add(self.program_progress, message)
        def work():
            if operation == 'install':
                return programs.install(progress)
            if operation == 'launch':
                return programs.launch()
            if operation == 'fonts':
                return programs.repair_fonts()
            if operation == 'wine-settings':
                return programs.open_wine_settings()
            return programs.status()
        future = self.program_pool.submit(work)
        future.add_done_callback(lambda result: GLib.idle_add(self.program_finished, result))

    def program_progress(self, message):
        self.program_status.set_text(message)
        return False

    def program_finished(self, future):
        self.program_busy = False
        self.program_spinner.stop()
        for button in self.program_buttons:
            button.set_sensitive(True)
        try:
            self.program_status.set_text(future.result())
        except Exception as exc:
            self.program_status.set_text('프로그램 설치·실행 실패: ' + str(exc)[-1500:])
        return False

    def graphics_settings(self, operation='status'):
        if self.graphics_busy:
            return
        self.graphics_busy = True
        for button in self.graphics_buttons:
            button.set_sensitive(False)
        self.graphics_status.set_text({'install': '터미널을 여는 중…',
                                       'copy': '설치 명령을 확인하는 중…'}.get(
                                           operation, '그래픽 드라이버 상태 확인 중…'))

        def progress(message):
            GLib.idle_add(self.graphics_progress, message)

        # Every branch reads hardware or the package database, so none of it
        # may run on the main thread. The clipboard is set from the callback.
        def work():
            if operation == 'install':
                return graphics.install(progress) + '\n\n' + graphics.status(), None
            if operation == 'copy':
                text = '\n'.join(graphics.commands())
                return '설치 명령을 클립보드에 복사했습니다.\n\n' + text, text
            return graphics.status(), None

        future = self.program_pool.submit(work)
        future.add_done_callback(lambda result: GLib.idle_add(self.graphics_finished, result))

    def graphics_progress(self, message):
        self.graphics_status.set_text(message)
        return False

    def graphics_finished(self, future):
        self.graphics_busy = False
        for button in self.graphics_buttons:
            button.set_sensitive(True)
        try:
            message, copied = future.result()
            if copied:
                Gtk.Clipboard.get(Gdk.SELECTION_CLIPBOARD).set_text(copied, -1)
            self.graphics_status.set_text(message)
        except Exception as exc:
            self.graphics_status.set_text('그래픽 드라이버 설치 실패: ' + str(exc)[-1500:])
        return False

    def font_settings(self, operation='status'):
        if self.font_busy:
            return
        self.font_busy = True
        self.font_status.set_text('글꼴 설정 확인 중…' if operation == 'status' else '글꼴 설정 변경 중…')
        for button in self.font_buttons:
            button.set_sensitive(False)
        future = self.pool.submit(lambda: fonts.dispatch(operation))
        future.add_done_callback(lambda result: GLib.idle_add(self.font_finished, result))

    def font_finished(self, future):
        self.font_busy = False
        for button in self.font_buttons:
            button.set_sensitive(True)
        self.font_buttons[0].set_sensitive(fonts.environment() in ('kde', 'gnome'))
        self.font_buttons[3].set_sensitive(fonts.environment() == 'gnome')
        try:
            self.font_status.set_text(future.result())
        except Exception as exc:
            self.font_status.set_text('글꼴 설정 실패: ' + str(exc))
        return False

    def mac_settings(self, operation='status'):
        if self.mac_busy:
            return
        self.mac_busy = True
        self.mac_status.set_text('단축키 설정 확인 중…' if operation == 'status' else '단축키 변경 중…')
        for button in self.mac_buttons:
            button.set_sensitive(False)
        mode = 'clipboard' if self.mac_terminal.get_active() else 'disabled'
        self.mac_terminal.set_sensitive(False)
        def work():
            if operation == 'apply':
                mac.set_terminal_mode(mode)
            message = mac.status() if operation == 'status' else mac.configure(restore=operation == 'restore')
            return message, mac.terminal_mode()
        future = self.pool.submit(work)
        future.add_done_callback(lambda result: GLib.idle_add(self.mac_finished, result))

    def mac_finished(self, future):
        self.mac_busy = False
        self.mac_terminal.set_sensitive(True)
        for button in self.mac_buttons:
            button.set_sensitive(True)
        try:
            message, mode = future.result()
            self.mac_status.set_text(message)
            self.mac_terminal.set_active(mode == 'clipboard')
        except Exception as exc:
            self.mac_status.set_text('Mac 단축키 설정 실패: ' + str(exc))
        return False

    def build_capture_section(self, settings):
        self.add_section(settings, '화면 영역 캡처')
        note = Gtk.Label(label='단축키를 누르면 영역을 선택해 클립보드로 바로 복사합니다.\n'
                               '파일로 저장하지 않으므로 그대로 붙여넣을 수 있습니다.\n'
                               'Cinnamon 세션에서만 지원하며 다른 기능이 쓰는 키는 거부합니다.', xalign=0)
        note.set_line_wrap(True)
        settings.pack_start(note, False, False, 0)
        self.capture_choice = Gtk.ComboBoxText()
        for binding, label in cinnamon.CHOICES:
            self.capture_choice.append(binding, label)
        self.capture_choice.set_active_id(cinnamon.DEFAULT)
        self.capture_choice.set_halign(Gtk.Align.START)
        settings.pack_start(self.capture_choice, False, False, 0)
        self.capture_status = Gtk.Label(label='설정 확인 중…', xalign=0)
        self.capture_status.set_line_wrap(True)
        self.capture_status.set_max_width_chars(65)
        settings.pack_start(self.capture_status, False, False, 0)
        buttons = Gtk.Box(spacing=8)
        self.capture_buttons = []
        self.capture_busy = False
        for title, operation in [('선택한 캡처 단축키 적용', 'apply'),
                                 ('원래 설정 복원', 'restore'), ('상태 확인', 'status')]:
            button = Gtk.Button(label=title)
            button.connect('clicked', lambda _, op=operation: self.capture_settings(op))
            buttons.pack_start(button, False, False, 0)
            self.capture_buttons.append(button)
        settings.pack_start(buttons, False, False, 0)

    def capture_settings(self, operation='status'):
        if self.capture_busy:
            return
        self.capture_busy = True
        binding = self.capture_choice.get_active_id()
        self.capture_choice.set_sensitive(False)
        for button in self.capture_buttons:
            button.set_sensitive(False)
        self.capture_status.set_text('설정 확인 중…' if operation == 'status' else '단축키 설정 중…')

        def work():
            if operation == 'apply':
                return cinnamon.configure(binding), cinnamon.selected()
            if operation == 'restore':
                return cinnamon.configure(restore=True), cinnamon.selected()
            return cinnamon.status(), cinnamon.selected()

        future = self.pool.submit(work)
        future.add_done_callback(lambda result: GLib.idle_add(self.capture_finished, result))

    def capture_finished(self, future):
        self.capture_busy = False
        self.capture_choice.set_sensitive(True)
        for button in self.capture_buttons:
            button.set_sensitive(True)
        try:
            message, current = future.result()
            self.capture_status.set_text(message)
            if current:
                self.capture_choice.set_active_id(current)
        except Exception as exc:
            self.capture_status.set_text('캡처 단축키 설정 실패: ' + str(exc))
        return False

    def keyboard_settings(self, operation='status'):
        if self.keyboard_busy:
            return
        self.keyboard_busy = True
        selected = [key for key, toggle in self.keyboard_function_keys.items() if toggle.get_active()]
        for toggle in self.keyboard_function_keys.values():
            toggle.set_sensitive(False)
        self.keyboard_status.set_text('설정 확인 중…' if operation == 'status' else '키 설정 변경 중…')
        for button in self.keyboard_buttons:
            button.set_sensitive(False)

        def work():
            if operation == 'apply':
                keyboard.configure(function_keys=selected)
            elif operation == 'restore':
                keyboard.configure(restore=True)
            return (keyboard.status(), keyboard.selected_function_keys(),
                    keyboard.method_label(), list(keyboard.supported_function_keys()))

        future = self.pool.submit(work)
        future.add_done_callback(lambda result: GLib.idle_add(self.keyboard_finished, result))

    def keyboard_finished(self, future):
        self.keyboard_busy = False
        for button in self.keyboard_buttons:
            button.set_sensitive(True)
        try:
            message, selected, label, supported = future.result()
            self.keyboard_status.set_text(message)
            self.keyboard_note.set_text(self.KEYBOARD_NOTE.format(label=label))
            for key, toggle in self.keyboard_function_keys.items():
                toggle.set_active(key in selected)
                # nimf's key table stops at F12; do not offer keys it cannot register.
                toggle.set_sensitive(key in supported)
        except Exception as exc:
            for toggle in self.keyboard_function_keys.values():
                toggle.set_sensitive(True)
            self.keyboard_status.set_text('한영 전환 설정 실패: ' + str(exc))
        return False

    def load_power(self, *_):
        self.epp.set_active_id(self.state.get('epp') or 'balance_performance')
        self.cpu_max.set_value(self.state.get('cpu_max') or 100)
        self.turbo.set_active(self.state.get('no_turbo') == 0)
        self.fan.set_active_id(self.state.get('fan') if self.state.get('fan') in ('auto', 'silent') else 'auto')
        self.boost.set_active(bool(self.state.get('cooler_boost')))

    def popup(self, title, detail, fraction=None):
        if not self.osd_enabled or self.screen_active:
            return
        if self.osd is None:
            self.osd = Gtk.Window(type=Gtk.WindowType.POPUP)
            self.osd.set_title('GF63 OSD')
            self.osd.set_accept_focus(False)
            self.osd.set_focus_on_map(False)
            self.osd.set_keep_above(True)
            self.osd.set_type_hint(Gdk.WindowTypeHint.NOTIFICATION)
            self.osd.set_default_size(340, 100)
            self.osd.get_style_context().add_class('osd')
            box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=10, margin=20)
            self.osd.add(box)
            self.osd_title = Gtk.Label()
            self.osd_detail = Gtk.Label()
            self.osd_bar = Gtk.ProgressBar()
            for widget in (self.osd_title, self.osd_detail, self.osd_bar):
                box.pack_start(widget, False, False, 0)
        self.osd_title.set_markup('<b>' + GLib.markup_escape_text(title) + '</b>')
        self.osd_detail.set_text(detail)
        self.osd_bar.set_fraction(max(0, min(1, fraction or 0)))
        self.osd.show_all()
        self.osd_bar.set_visible(fraction is not None)
        display = Gdk.Display.get_default()
        monitor = display.get_primary_monitor() or display.get_monitor(0)
        area = monitor.get_workarea()
        width, height = self.osd.get_size()
        self.osd.move(area.x + (area.width - width) // 2, area.y + area.height - height - 70)
        if self.hide_timer:
            GLib.source_remove(self.hide_timer)
        self.hide_timer = GLib.timeout_add(1800, self.hide_osd)

    def hide_osd(self):
        self.osd.hide()
        self.hide_timer = 0
        return False

    def submit(self, function, action=False):
        if self.pending:
            if action:
                if len(self.action_queue) < 20:
                    self.action_queue.append(function)
            return
        self.pending = True
        future = self.pool.submit(function)
        future.add_done_callback(lambda result: GLib.idle_add(self.complete, result, action))

    def poll(self):
        self.submit(core.snapshot)
        return True

    def action(self, action, value=None):
        if self.window and action == 'lid':
            self.lid_message.set_text('덮개 설정 적용 중…')
        self.submit(lambda: core.apply(action, value), action=True)

    def complete(self, future, action):
        self.pending = False
        try:
            new = future.result()
            for key in core.LABELS:
                if self.state.get(key) is not None and new.get(key) is not None and new[key] != self.state[key]:
                    value = new[key]
                    fraction = value[0] / 100 if key in ('volume', 'microphone') else (
                        value / 3 if key == 'keyboard' else value / 100 if key in ('brightness', 'battery') else None)
                    self.popup(core.LABELS[key], core.description(key, value), fraction)
                    self.events.insert(0, core.LABELS[key] + ': ' + core.description(key, value))
                    self.events = self.events[:7]
            self.state = new
            if self.window and action:
                self.message.set_text('적용 상태를 확인했습니다.')
                self.lid_message.set_text('적용 상태를 확인했습니다.')
            self.update_ui()
        except Exception as exc:
            if action:
                self.popup('적용하지 못했습니다', str(exc)[:100])
            if self.window:
                self.message.set_text(str(exc))
                self.lid_message.set_text(str(exc))
        if self.action_queue:
            self.submit(self.action_queue.pop(0), action=True)
        return False

    def update_ui(self):
        if self.window is None:
            return
        for key, label in self.labels.items():
            label.set_text(core.description(key, self.state.get(key)))
            for button in self.controls[key]:
                button.set_sensitive(self.state.get(key) is not None)
        capacity = self.state.get('capacity')
        temp = self.state.get('cpu_temp')
        self.summary.set_text(f"배터리 {capacity if capacity is not None else '—'}%   ·   "
                              f"CPU {temp if temp is not None else '—'}°C")
        self.history.set_text('\n'.join(self.events) or '최근 상태 변화가 여기에 표시됩니다.')
        self.power_summary.set_text('실제 CPU 정책: {} · 성능 상한: {}%\n터보: {} · 팬: {}'.format(
            self.state.get('epp') or '지원 안 됨', self.state.get('cpu_max', '—'),
            '켜짐' if self.state.get('no_turbo') == 0 else '꺼짐', self.state.get('fan') or '지원 안 됨'))

    def do_shutdown(self):
        self.program_pool.shutdown(wait=False)
        self.pool.shutdown(wait=False)
        Gtk.Application.do_shutdown(self)


if __name__ == '__main__':
    sys.exit(Control().run(sys.argv))
