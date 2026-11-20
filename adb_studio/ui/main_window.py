"""Main window for ADB Studio."""

from __future__ import annotations

from collections.abc import Callable
from datetime import datetime
from pathlib import Path
from typing import Any

from PySide6.QtCore import Qt, QThreadPool, QTimer, QUrl
from PySide6.QtGui import (
    QAction,
    QDesktopServices,
    QIcon,
    QImage,
    QKeySequence,
    QPixmap,
    QShortcut,
)
from PySide6.QtWidgets import (
    QAbstractItemView,
    QApplication,
    QCheckBox,
    QComboBox,
    QFileDialog,
    QFrame,
    QGridLayout,
    QGroupBox,
    QHBoxLayout,
    QKeySequenceEdit,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QMainWindow,
    QMenu,
    QMessageBox,
    QPlainTextEdit,
    QPushButton,
    QScrollArea,
    QSizePolicy,
    QSpinBox,
    QSplitter,
    QSystemTrayIcon,
    QTabWidget,
    QVBoxLayout,
    QWidget,
)

from adb_studio.adb_client import AdbClient
from adb_studio.branding import load_app_icon
from adb_studio.config import DEFAULT_CONFIG_PATH, AppConfig
from adb_studio.hotkey import GlobalHotkeyManager
from adb_studio.models import CommandResult, DeviceInfo
from adb_studio.recorder import RecordingOutcome, ScreenRecorderSession
from adb_studio.startup import is_autostart_enabled, set_autostart
from adb_studio.ui.hud_toast import ScreenshotHudToast
from adb_studio.workers import AsyncTask


class MainWindow(QMainWindow):
    """Primary desktop window for managing ADB devices and executing commands."""

    def __init__(
        self,
        config: AppConfig | None = None,
        config_path: Path = DEFAULT_CONFIG_PATH,
    ) -> None:
        super().__init__()
        self.config_path = config_path
        self.config = config or AppConfig.load(self.config_path)
        self.client = AdbClient(self.config.adb_path)
        self.thread_pool = QThreadPool.globalInstance()

        self._devices: dict[str, DeviceInfo] = {}
        self._selected_serial: str | None = None
        self._last_screenshot_path: Path | None = None
        self._all_packages: list[str] = []
        self._poll_in_flight = False
        self._active_tasks = 0
        self._pending_tasks: set[AsyncTask] = set()
        self._device_widgets: list[QWidget] = []
        self._rec_session: ScreenRecorderSession | None = None
        self._rec_elapsed_secs = 0
        self._rec_timer = QTimer(self)
        self._rec_timer.setInterval(1000)
        self._rec_timer.timeout.connect(self._on_record_tick)
        self._force_quit = False
        self._tray_notified_once = False
        self.hud_toast = ScreenshotHudToast()

        self.setWindowTitle("ADB Studio — Android Debug Bridge Control Center")
        self.setWindowIcon(self._create_app_icon())
        self.resize(1140, 720)
        self.setMinimumSize(840, 560)

        self._build_ui()
        self._bind_shortcuts()
        self._setup_tray()
        self._setup_global_hotkey()

        self.poll_timer = QTimer(self)
        self.poll_timer.setInterval(3000)
        self.poll_timer.timeout.connect(self._poll_devices_if_enabled)
        if self.config.auto_refresh_devices:
            self.poll_timer.start()

        self._check_adb_status()
        self.refresh_devices()
        self._update_device_controls_state()

    # ------------------------------------------------------------------
    # UI Construction
    # ------------------------------------------------------------------

    def _build_ui(self) -> None:
        root = QWidget()
        self.setCentralWidget(root)
        main_layout = QVBoxLayout(root)
        main_layout.setContentsMargins(12, 10, 12, 12)
        main_layout.setSpacing(10)

        main_layout.addLayout(self._build_header_bar())

        body_splitter = QSplitter(Qt.Horizontal)
        body_splitter.addWidget(self._build_device_sidebar())
        body_splitter.addWidget(self._build_right_workspace())
        body_splitter.setCollapsible(0, False)
        body_splitter.setCollapsible(1, False)
        body_splitter.setStretchFactor(0, 1)
        body_splitter.setStretchFactor(1, 3)
        body_splitter.setSizes([290, 850])

        main_layout.addWidget(body_splitter, stretch=1)

    def _build_header_bar(self) -> QHBoxLayout:
        header = QHBoxLayout()
        header.setSpacing(10)

        title = QLabel("ADB Studio")
        title.setStyleSheet("font-size: 18px; font-weight: 700; color: #ffffff;")
        header.addWidget(title)

        self.adb_badge = QLabel("Checking ADB...")
        self.adb_badge.setObjectName("badgeBusy")
        header.addWidget(self.adb_badge)

        self.busy_badge = QLabel("Running...")
        self.busy_badge.setObjectName("badgeBusy")
        self.busy_badge.setVisible(False)
        header.addWidget(self.busy_badge)

        header.addStretch(1)

        adb_path_btn = QPushButton("Set ADB Path...")
        adb_path_btn.clicked.connect(self._choose_adb_path)
        header.addWidget(adb_path_btn)

        return header

    def _build_device_sidebar(self) -> QWidget:
        panel = QWidget()
        panel.setMinimumWidth(240)
        layout = QVBoxLayout(panel)
        layout.setContentsMargins(0, 0, 4, 0)
        layout.setSpacing(8)

        box = QGroupBox("Connected Devices (Select One)")
        box_layout = QVBoxLayout(box)
        box_layout.setSpacing(8)

        self.device_list = QListWidget()
        self.device_list.setSelectionMode(QAbstractItemView.SingleSelection)
        self.device_list.itemSelectionChanged.connect(self._on_device_selection_changed)
        box_layout.addWidget(self.device_list, stretch=1)

        self.selected_device_label = QLabel("No device selected")
        self.selected_device_label.setWordWrap(True)
        self.selected_device_label.setStyleSheet(
            "background-color: #0d1218; border: 1px solid #26303d; "
            "border-radius: 6px; padding: 8px; color: #9fb0c3;"
        )
        box_layout.addWidget(self.selected_device_label)

        refresh_row = QHBoxLayout()
        self.refresh_btn = QPushButton("Refresh Devices")
        self.refresh_btn.clicked.connect(self.refresh_devices)
        refresh_row.addWidget(self.refresh_btn)

        self.auto_refresh_cb = QCheckBox("Auto (3s)")
        self.auto_refresh_cb.setChecked(self.config.auto_refresh_devices)
        self.auto_refresh_cb.toggled.connect(self._on_auto_refresh_toggled)
        refresh_row.addWidget(self.auto_refresh_cb)
        box_layout.addLayout(refresh_row)

        server_row = QHBoxLayout()
        start_srv_btn = QPushButton("Start ADB Server")
        start_srv_btn.clicked.connect(
            lambda: self._run_adb_task("Start ADB Server", self.client.start_server, refresh_after=True)
        )
        kill_srv_btn = QPushButton("Kill ADB Server")
        kill_srv_btn.setObjectName("dangerBtn")
        kill_srv_btn.clicked.connect(
            lambda: self._run_adb_task("Kill ADB Server", self.client.kill_server, refresh_after=True)
        )
        server_row.addWidget(start_srv_btn)
        server_row.addWidget(kill_srv_btn)
        box_layout.addLayout(server_row)

        layout.addWidget(box)
        return panel

    def _wrap_in_scroll_area(self, content: QWidget) -> QScrollArea:
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.NoFrame)
        scroll.setWidget(content)
        return scroll

    def _build_right_workspace(self) -> QWidget:
        panel = QWidget()
        panel.setMinimumWidth(520)
        layout = QVBoxLayout(panel)
        layout.setContentsMargins(4, 0, 0, 0)
        layout.setSpacing(8)

        layout.addWidget(self._build_screenshot_hero())

        vertical_splitter = QSplitter(Qt.Vertical)
        self.tabs = QTabWidget()
        self.tabs.addTab(self._wrap_in_scroll_area(self._build_controls_tab()), "Controls && Keys")
        self.tabs.addTab(self._wrap_in_scroll_area(self._build_device_screen_tab()), "Device && Screen")
        self.tabs.addTab(self._wrap_in_scroll_area(self._build_apps_tab()), "Apps (APK)")
        self.tabs.addTab(self._wrap_in_scroll_area(self._build_files_wireless_tab()), "Files && Wireless")
        self.tabs.addTab(self._wrap_in_scroll_area(self._build_shell_logcat_tab()), "Shell && Logcat")
        self.tabs.addTab(self._wrap_in_scroll_area(self._build_settings_tab()), "Settings")

        vertical_splitter.addWidget(self.tabs)
        vertical_splitter.addWidget(self._build_console_box())
        vertical_splitter.setCollapsible(0, False)
        vertical_splitter.setCollapsible(1, False)
        vertical_splitter.setStretchFactor(0, 3)
        vertical_splitter.setStretchFactor(1, 2)
        vertical_splitter.setSizes([360, 190])

        layout.addWidget(vertical_splitter, stretch=1)
        return panel

    def _build_screenshot_hero(self) -> QGroupBox:
        box = QGroupBox("Screenshot && Clipboard Studio")
        box.setSizePolicy(QSizePolicy.Preferred, QSizePolicy.Fixed)
        outer = QHBoxLayout(box)
        outer.setSpacing(12)

        left_col = QVBoxLayout()
        left_col.setSpacing(8)

        top_row = QHBoxLayout()
        self.screenshot_btn = QPushButton("Take Screenshot (Ctrl+S)")
        self.screenshot_btn.setObjectName("primaryBtn")
        self.screenshot_btn.clicked.connect(self.capture_screenshot)
        self._device_widgets.append(self.screenshot_btn)
        top_row.addWidget(self.screenshot_btn)

        self.auto_copy_cb = QCheckBox("Auto-copy latest screenshot to Clipboard")
        self.auto_copy_cb.setChecked(self.config.auto_copy_clipboard)
        self.auto_copy_cb.toggled.connect(self._on_auto_copy_toggled)
        top_row.addWidget(self.auto_copy_cb)

        self.copy_last_btn = QPushButton("Copy Last Again")
        self.copy_last_btn.setEnabled(False)
        self.copy_last_btn.clicked.connect(self._copy_last_screenshot)
        top_row.addWidget(self.copy_last_btn)
        top_row.addStretch(1)
        left_col.addLayout(top_row)

        path_row = QHBoxLayout()
        path_row.addWidget(QLabel("Save Folder:"))
        self.screenshot_dir_edit = QLineEdit(self.config.screenshot_dir)
        self.screenshot_dir_edit.editingFinished.connect(self._on_screenshot_dir_edited)
        path_row.addWidget(self.screenshot_dir_edit, stretch=1)

        browse_btn = QPushButton("Browse...")
        browse_btn.clicked.connect(self._browse_screenshot_dir)
        path_row.addWidget(browse_btn)

        open_dir_btn = QPushButton("Open Folder")
        open_dir_btn.clicked.connect(self._open_screenshot_dir)
        path_row.addWidget(open_dir_btn)
        left_col.addLayout(path_row)

        self.screenshot_status_label = QLabel("Ready — select a connected device and click Take Screenshot.")
        self.screenshot_status_label.setStyleSheet("color: #8b9bb0; font-size: 12px;")
        left_col.addWidget(self.screenshot_status_label)

        outer.addLayout(left_col, stretch=1)

        self.preview_label = QLabel("No Preview")
        self.preview_label.setFixedSize(116, 116)
        self.preview_label.setAlignment(Qt.AlignCenter)
        self.preview_label.setStyleSheet(
            "background-color: #0d1218; border: 1px dashed #303c4d; "
            "border-radius: 6px; color: #64748b; font-size: 11px;"
        )
        outer.addWidget(self.preview_label)

        return box

    def _build_controls_tab(self) -> QWidget:
        tab = QWidget()
        layout = QVBoxLayout(tab)
        layout.setSpacing(10)

        # Navigation & Hardware keys
        keys_box = QGroupBox("Navigation && Hardware Keys")
        keys_grid = QGridLayout(keys_box)
        key_buttons = [
            ("Home", "KEYCODE_HOME"),
            ("Back", "KEYCODE_BACK"),
            ("Recents", "KEYCODE_APP_SWITCH"),
            ("Power", "KEYCODE_POWER"),
            ("Wake Up", "KEYCODE_WAKEUP"),
            ("Sleep", "KEYCODE_SLEEP"),
            ("Volume +", "KEYCODE_VOLUME_UP"),
            ("Volume -", "KEYCODE_VOLUME_DOWN"),
            ("Mute", "KEYCODE_VOLUME_MUTE"),
            ("Enter", "KEYCODE_ENTER"),
            ("Menu", "KEYCODE_MENU"),
            ("Media Play/Pause", "KEYCODE_MEDIA_PLAY_PAUSE"),
        ]
        for idx, (label, keycode) in enumerate(key_buttons):
            btn = QPushButton(label)
            btn.clicked.connect(
                lambda _checked=False, kc=keycode, lbl=label: self._run_device_task(
                    f"Key: {lbl}", lambda s: self.client.send_keyevent(s, kc)
                )
            )
            self._device_widgets.append(btn)
            keys_grid.addWidget(btn, idx // 4, idx % 4)
        layout.addWidget(keys_box)

        # Quick Text & URL Input
        input_box = QGroupBox("Send Text && Open URL")
        input_grid = QGridLayout(input_box)

        self.send_text_edit = QLineEdit()
        self.send_text_edit.setPlaceholderText("Type text to send to focused Android input...")
        send_text_btn = QPushButton("Send Text")
        send_text_btn.clicked.connect(self._send_text)
        self._device_widgets.extend([self.send_text_edit, send_text_btn])
        input_grid.addWidget(QLabel("Text:"), 0, 0)
        input_grid.addWidget(self.send_text_edit, 0, 1)
        input_grid.addWidget(send_text_btn, 0, 2)

        self.open_url_edit = QLineEdit()
        self.open_url_edit.setPlaceholderText("https://example.com")
        open_url_btn = QPushButton("Open URL")
        open_url_btn.clicked.connect(self._open_url)
        self._device_widgets.extend([self.open_url_edit, open_url_btn])
        input_grid.addWidget(QLabel("URL:"), 1, 0)
        input_grid.addWidget(self.open_url_edit, 1, 1)
        input_grid.addWidget(open_url_btn, 1, 2)
        layout.addWidget(input_box)

        # Developer Toggles & Reboot
        bottom_row = QHBoxLayout()

        dev_box = QGroupBox("Developer Toggles")
        dev_grid = QGridLayout(dev_box)
        toggles = [
            ("Show Touches ON", lambda s: self.client.set_show_touches(s, True)),
            ("Show Touches OFF", lambda s: self.client.set_show_touches(s, False)),
            ("Layout Bounds ON", lambda s: self.client.set_layout_bounds(s, True)),
            ("Layout Bounds OFF", lambda s: self.client.set_layout_bounds(s, False)),
            ("Stay Awake ON", lambda s: self.client.set_stay_awake(s, True)),
            ("Stay Awake OFF", lambda s: self.client.set_stay_awake(s, False)),
        ]
        for idx, (label, fn) in enumerate(toggles):
            btn = QPushButton(label)
            btn.clicked.connect(lambda _c=False, l=label, f=fn: self._run_device_task(l, f))
            self._device_widgets.append(btn)
            dev_grid.addWidget(btn, idx // 2, idx % 2)
        bottom_row.addWidget(dev_box)

        reboot_box = QGroupBox("Reboot Options")
        reboot_grid = QGridLayout(reboot_box)
        reboot_modes = [
            ("Reboot System", ""),
            ("Reboot Recovery", "recovery"),
            ("Reboot Bootloader", "bootloader"),
            ("Reboot Fastboot", "fastboot"),
        ]
        for idx, (label, mode) in enumerate(reboot_modes):
            btn = QPushButton(label)
            btn.setObjectName("dangerBtn")
            btn.clicked.connect(lambda _c=False, l=label, m=mode: self._confirm_reboot(l, m))
            self._device_widgets.append(btn)
            reboot_grid.addWidget(btn, idx // 2, idx % 2)
        bottom_row.addWidget(reboot_box)

        layout.addLayout(bottom_row)
        layout.addStretch(1)
        return tab

    def _build_device_screen_tab(self) -> QWidget:
        tab = QWidget()
        layout = QVBoxLayout(tab)
        layout.setSpacing(10)

        info_box = QGroupBox("Device Diagnostics")
        info_row = QHBoxLayout(info_box)
        for label, fn in [
            ("Device Summary", self.client.get_device_summary),
            ("Battery Status", self.client.get_battery_info),
            ("Network / IP Info", self.client.get_network_info),
        ]:
            btn = QPushButton(label)
            btn.clicked.connect(lambda _c=False, l=label, f=fn: self._run_device_task(l, f))
            self._device_widgets.append(btn)
            info_row.addWidget(btn)
        layout.addWidget(info_box)

        display_box = QGroupBox("Display Resolution & Density (wm)")
        disp_grid = QGridLayout(display_box)

        self.wm_size_edit = QLineEdit()
        self.wm_size_edit.setPlaceholderText("e.g. 1080x2400")
        set_size_btn = QPushButton("Set Size")
        set_size_btn.clicked.connect(self._set_screen_size)
        reset_size_btn = QPushButton("Reset Size")
        reset_size_btn.clicked.connect(
            lambda: self._run_device_task("Reset Screen Size", lambda s: self.client.set_screen_size(s, "reset"))
        )
        self._device_widgets.extend([self.wm_size_edit, set_size_btn, reset_size_btn])
        disp_grid.addWidget(QLabel("Resolution:"), 0, 0)
        disp_grid.addWidget(self.wm_size_edit, 0, 1)
        disp_grid.addWidget(set_size_btn, 0, 2)
        disp_grid.addWidget(reset_size_btn, 0, 3)

        self.wm_dpi_edit = QLineEdit()
        self.wm_dpi_edit.setPlaceholderText("e.g. 420")
        set_dpi_btn = QPushButton("Set DPI")
        set_dpi_btn.clicked.connect(self._set_screen_dpi)
        reset_dpi_btn = QPushButton("Reset DPI")
        reset_dpi_btn.clicked.connect(
            lambda: self._run_device_task("Reset Screen DPI", lambda s: self.client.set_screen_density(s, "reset"))
        )
        self._device_widgets.extend([self.wm_dpi_edit, set_dpi_btn, reset_dpi_btn])
        disp_grid.addWidget(QLabel("Density (DPI):"), 1, 0)
        disp_grid.addWidget(self.wm_dpi_edit, 1, 1)
        disp_grid.addWidget(set_dpi_btn, 1, 2)
        disp_grid.addWidget(reset_dpi_btn, 1, 3)
        layout.addWidget(display_box)

        rec_box = QGroupBox("Screen Recording (MP4 saved to Screenshot Folder)")
        rec_row = QHBoxLayout(rec_box)
        rec_row.addWidget(QLabel("Max Duration (s):"))
        self.record_duration_spin = QSpinBox()
        self.record_duration_spin.setRange(3, 180)
        self.record_duration_spin.setValue(30)
        self.record_btn = QPushButton("Start Recording")
        self.record_btn.clicked.connect(self._toggle_recording)
        rec_mode_hint = (
            "Ready (scrcpy 60fps detected)"
            if self.config.scrcpy_path
            else "Idle (native screenrecord / screencap fallback)"
        )
        self.record_status_label = QLabel(rec_mode_hint)
        self.record_status_label.setStyleSheet("color: #8b9bb0; font-size: 12px;")
        self._device_widgets.extend([self.record_duration_spin, self.record_btn])
        rec_row.addWidget(self.record_duration_spin)
        rec_row.addWidget(self.record_btn)
        rec_row.addWidget(self.record_status_label, stretch=1)
        layout.addWidget(rec_box)

        layout.addStretch(1)
        return tab

    def _build_apps_tab(self) -> QWidget:
        tab = QWidget()
        layout = QVBoxLayout(tab)
        layout.setSpacing(8)

        top_row = QHBoxLayout()
        self.pkg_filter_combo = QComboBox()
        self.pkg_filter_combo.addItem("3rd Party Apps", "third_party")
        self.pkg_filter_combo.addItem("All Packages", "all")
        self.pkg_filter_combo.addItem("System Apps", "system")

        load_pkgs_btn = QPushButton("Load Packages")
        load_pkgs_btn.clicked.connect(self._load_packages)

        self.pkg_search_edit = QLineEdit()
        self.pkg_search_edit.setPlaceholderText("Filter package name...")
        self.pkg_search_edit.textChanged.connect(self._filter_packages_list)

        install_apk_btn = QPushButton("Install APK...")
        install_apk_btn.clicked.connect(self._install_apk)

        self._device_widgets.extend([self.pkg_filter_combo, load_pkgs_btn, self.pkg_search_edit, install_apk_btn])

        top_row.addWidget(self.pkg_filter_combo)
        top_row.addWidget(load_pkgs_btn)
        top_row.addWidget(self.pkg_search_edit, stretch=1)
        top_row.addWidget(install_apk_btn)
        layout.addLayout(top_row)

        self.package_list = QListWidget()
        self._device_widgets.append(self.package_list)
        layout.addWidget(self.package_list, stretch=1)

        actions_row = QHBoxLayout()
        for label, handler, danger in [
            ("Launch", self._launch_selected_pkg, False),
            ("Force Stop", self._force_stop_selected_pkg, False),
            ("Clear Data", self._clear_data_selected_pkg, True),
            ("Pull APK...", self._pull_selected_pkg_apk, False),
            ("Uninstall", self._uninstall_selected_pkg, True),
        ]:
            btn = QPushButton(label)
            if danger:
                btn.setObjectName("dangerBtn")
            btn.clicked.connect(handler)
            self._device_widgets.append(btn)
            actions_row.addWidget(btn)
        layout.addLayout(actions_row)
        return tab

    def _build_files_wireless_tab(self) -> QWidget:
        tab = QWidget()
        layout = QVBoxLayout(tab)
        layout.setSpacing(10)

        files_box = QGroupBox("File Transfer (Push / Pull)")
        files_grid = QGridLayout(files_box)

        self.push_remote_edit = QLineEdit("/sdcard/Download/")
        push_btn = QPushButton("Push Local File...")
        push_btn.clicked.connect(self._push_file)
        self._device_widgets.extend([self.push_remote_edit, push_btn])
        files_grid.addWidget(QLabel("Remote Target:"), 0, 0)
        files_grid.addWidget(self.push_remote_edit, 0, 1)
        files_grid.addWidget(push_btn, 0, 2)

        self.pull_remote_edit = QLineEdit()
        self.pull_remote_edit.setPlaceholderText("/sdcard/Download/file.txt")
        pull_btn = QPushButton("Pull to PC...")
        pull_btn.clicked.connect(self._pull_file)
        self._device_widgets.extend([self.pull_remote_edit, pull_btn])
        files_grid.addWidget(QLabel("Remote Source:"), 1, 0)
        files_grid.addWidget(self.pull_remote_edit, 1, 1)
        files_grid.addWidget(pull_btn, 1, 2)
        layout.addWidget(files_box)

        wifi_box = QGroupBox("Wireless ADB (Wi-Fi)")
        wifi_grid = QGridLayout(wifi_box)

        tcpip_btn = QPushButton("Enable TCP/IP :5555 on Selected USB Device")
        tcpip_btn.clicked.connect(
            lambda: self._run_device_task("Enable TCP/IP 5555", lambda s: self.client.enable_tcpip(s, 5555))
        )
        self._device_widgets.append(tcpip_btn)
        wifi_grid.addWidget(tcpip_btn, 0, 0, 1, 4)

        self.wifi_target_combo = QComboBox()
        self.wifi_target_combo.setEditable(True)
        self.wifi_target_combo.setInsertPolicy(QComboBox.NoInsert)
        for target in self.config.wireless_history:
            self.wifi_target_combo.addItem(target)
        if self.wifi_target_combo.lineEdit():
            self.wifi_target_combo.lineEdit().setPlaceholderText("192.168.1.100:5555")

        connect_btn = QPushButton("Connect")
        connect_btn.clicked.connect(self._connect_wireless)
        disconnect_btn = QPushButton("Disconnect")
        disconnect_btn.clicked.connect(self._disconnect_wireless)

        wifi_grid.addWidget(QLabel("IP:Port:"), 1, 0)
        wifi_grid.addWidget(self.wifi_target_combo, 1, 1)
        wifi_grid.addWidget(connect_btn, 1, 2)
        wifi_grid.addWidget(disconnect_btn, 1, 3)

        self.pair_target_edit = QLineEdit()
        self.pair_target_edit.setPlaceholderText("192.168.1.100:37123")
        self.pair_code_edit = QLineEdit()
        self.pair_code_edit.setPlaceholderText("6-digit code")
        pair_btn = QPushButton("Pair (Android 11+)")
        pair_btn.clicked.connect(self._pair_wireless)

        wifi_grid.addWidget(QLabel("Pair IP:Port:"), 2, 0)
        wifi_grid.addWidget(self.pair_target_edit, 2, 1)
        wifi_grid.addWidget(self.pair_code_edit, 2, 2)
        wifi_grid.addWidget(pair_btn, 2, 3)

        layout.addWidget(wifi_box)
        layout.addStretch(1)
        return tab

    def _build_shell_logcat_tab(self) -> QWidget:
        tab = QWidget()
        layout = QVBoxLayout(tab)
        layout.setSpacing(10)

        cmd_box = QGroupBox("Custom ADB Command")
        cmd_layout = QVBoxLayout(cmd_box)

        cmd_row = QHBoxLayout()
        self.custom_cmd_edit = QLineEdit()
        self.custom_cmd_edit.setPlaceholderText("e.g. shell getprop ro.build.version.release  (adb prefix optional)")
        self.custom_cmd_edit.returnPressed.connect(self._run_custom_cmd)
        run_cmd_btn = QPushButton("Run Command")
        run_cmd_btn.clicked.connect(self._run_custom_cmd)
        cmd_row.addWidget(self.custom_cmd_edit, stretch=1)
        cmd_row.addWidget(run_cmd_btn)
        cmd_layout.addLayout(cmd_row)

        presets_row = QHBoxLayout()
        presets_row.addWidget(QLabel("Presets:"))
        for label, cmd in [
            ("getprop", "shell getprop"),
            ("top -n 1", "shell top -n 1 -b"),
            ("df -h", "shell df -h"),
            ("wm size", "shell wm size"),
            ("dumpsys meminfo", "shell dumpsys meminfo"),
        ]:
            btn = QPushButton(label)
            btn.clicked.connect(lambda _c=False, c=cmd, l=label: self._run_preset_cmd(l, c))
            self._device_widgets.append(btn)
            presets_row.addWidget(btn)
        presets_row.addStretch(1)
        cmd_layout.addLayout(presets_row)
        layout.addWidget(cmd_box)

        logcat_box = QGroupBox("Logcat")
        logcat_row = QHBoxLayout(logcat_box)
        for label, handler in [
            ("Dump Logcat (400 lines)", self._dump_logcat),
            ("Clear Logcat", lambda: self._run_device_task("Clear Logcat", self.client.clear_logcat)),
            ("Save Logcat to File...", self._save_logcat),
        ]:
            btn = QPushButton(label)
            btn.clicked.connect(handler)
            self._device_widgets.append(btn)
            logcat_row.addWidget(btn)
        logcat_row.addStretch(1)
        layout.addWidget(logcat_box)

        layout.addStretch(1)
        return tab

    def _build_settings_tab(self) -> QWidget:
        tab = QWidget()
        layout = QVBoxLayout(tab)
        layout.setSpacing(10)

        # Global Hotkey Box
        hk_box = QGroupBox("Global Screenshot Hotkey (Works From Any App / Window)")
        hk_grid = QGridLayout(hk_box)

        self.hotkey_edit = QKeySequenceEdit(QKeySequence(self.config.global_hotkey))
        apply_hk_btn = QPushButton("Apply Hotkey")
        apply_hk_btn.clicked.connect(self._apply_global_hotkey)
        clear_hk_btn = QPushButton("Disable")
        clear_hk_btn.clicked.connect(self._clear_global_hotkey)

        self.hotkey_status_label = QLabel("")
        self.hotkey_status_label.setStyleSheet("color: #8b9bb0; font-size: 12px;")

        hk_grid.addWidget(QLabel("Shortcut:"), 0, 0)
        hk_grid.addWidget(self.hotkey_edit, 0, 1)
        hk_grid.addWidget(apply_hk_btn, 0, 2)
        hk_grid.addWidget(clear_hk_btn, 0, 3)
        hk_grid.addWidget(self.hotkey_status_label, 1, 0, 1, 4)
        layout.addWidget(hk_box)

        # Background & Startup Box
        bg_box = QGroupBox("Background Run && Windows Auto-Startup")
        bg_layout = QVBoxLayout(bg_box)
        bg_layout.setSpacing(8)

        self.run_bg_cb = QCheckBox("Keep running in System Tray when window is closed")
        self.run_bg_cb.setChecked(self.config.run_in_background)
        self.run_bg_cb.toggled.connect(self._on_bg_toggled)
        bg_layout.addWidget(self.run_bg_cb)

        self.autostart_cb = QCheckBox("Launch ADB Studio automatically when Windows starts")
        self.autostart_cb.setChecked(is_autostart_enabled())
        self.autostart_cb.toggled.connect(self._on_autostart_toggled)
        bg_layout.addWidget(self.autostart_cb)

        self.start_min_cb = QCheckBox("Start minimized in System Tray on Windows boot")
        self.start_min_cb.setChecked(self.config.start_minimized)
        self.start_min_cb.toggled.connect(self._on_start_min_toggled)
        bg_layout.addWidget(self.start_min_cb)

        self.startup_status_label = QLabel("")
        self.startup_status_label.setStyleSheet("color: #8b9bb0; font-size: 12px;")
        bg_layout.addWidget(self.startup_status_label)
        layout.addWidget(bg_box)

        # Tool Paths & Naming Box
        paths_box = QGroupBox("Tool Paths && Screenshot Naming")
        paths_grid = QGridLayout(paths_box)

        self.adb_path_edit = QLineEdit(self.config.adb_path)
        self.adb_path_edit.setReadOnly(True)
        adb_browse_btn = QPushButton("Browse...")
        adb_browse_btn.clicked.connect(self._choose_adb_path)
        paths_grid.addWidget(QLabel("ADB Executable:"), 0, 0)
        paths_grid.addWidget(self.adb_path_edit, 0, 1)
        paths_grid.addWidget(adb_browse_btn, 0, 2)

        self.scrcpy_path_edit = QLineEdit(self.config.scrcpy_path)
        self.scrcpy_path_edit.setPlaceholderText("Optional: path to scrcpy.exe for 60fps recording")
        self.scrcpy_path_edit.setReadOnly(True)
        scrcpy_browse_btn = QPushButton("Browse...")
        scrcpy_browse_btn.clicked.connect(self._choose_scrcpy_path)
        paths_grid.addWidget(QLabel("scrcpy Executable:"), 1, 0)
        paths_grid.addWidget(self.scrcpy_path_edit, 1, 1)
        paths_grid.addWidget(scrcpy_browse_btn, 1, 2)

        self.prefix_edit = QLineEdit(self.config.screenshot_prefix)
        save_prefix_btn = QPushButton("Save Prefix")
        save_prefix_btn.clicked.connect(self._on_prefix_saved)
        paths_grid.addWidget(QLabel("Filename Prefix:"), 2, 0)
        paths_grid.addWidget(self.prefix_edit, 2, 1)
        paths_grid.addWidget(save_prefix_btn, 2, 2)

        layout.addWidget(paths_box)
        layout.addStretch(1)
        return tab

    def _build_console_box(self) -> QGroupBox:
        box = QGroupBox("Command Output Log")
        box.setMinimumHeight(130)
        layout = QVBoxLayout(box)
        layout.setSpacing(6)

        self.console_log = QPlainTextEdit()
        self.console_log.setObjectName("consoleLog")
        self.console_log.setReadOnly(True)
        layout.addWidget(self.console_log, stretch=1)

        footer = QHBoxLayout()
        footer.addStretch(1)
        copy_log_btn = QPushButton("Copy Output")
        copy_log_btn.clicked.connect(self._copy_console_log)
        clear_log_btn = QPushButton("Clear Log")
        clear_log_btn.clicked.connect(self.console_log.clear)
        footer.addWidget(copy_log_btn)
        footer.addWidget(clear_log_btn)
        layout.addLayout(footer)
        return box

    def _bind_shortcuts(self) -> None:
        QShortcut(QKeySequence("Ctrl+S"), self, activated=self.capture_screenshot)
        QShortcut(QKeySequence("F5"), self, activated=self.refresh_devices)

    # ------------------------------------------------------------------
    # Async Execution & Logging
    # ------------------------------------------------------------------

    def _set_busy(self, delta: int) -> None:
        self._active_tasks = max(0, self._active_tasks + delta)
        self.busy_badge.setVisible(self._active_tasks > 0)

    def _submit_task(
        self,
        fn: Callable[[], Any],
        on_success: Callable[[Any], None],
        on_error: Callable[[str], None] | None = None,
        show_busy: bool = True,
    ) -> None:
        if show_busy:
            self._set_busy(1)
        task = AsyncTask(fn)
        self._pending_tasks.add(task)

        def handle_done(result: Any) -> None:
            self._pending_tasks.discard(task)
            if show_busy:
                self._set_busy(-1)
            on_success(result)

        def handle_fail(err: str) -> None:
            self._pending_tasks.discard(task)
            if show_busy:
                self._set_busy(-1)
            if on_error:
                on_error(err)
            else:
                self._append_log(f"[ERROR] {err}")

        task.signals.finished.connect(handle_done, Qt.QueuedConnection)
        task.signals.failed.connect(handle_fail, Qt.QueuedConnection)
        self.thread_pool.start(task)

    def _append_log(self, text: str) -> None:
        stamp = datetime.now().astimezone().strftime("%H:%M:%S")
        self.console_log.appendPlainText(f"[{stamp}] {text}")

    def _log_result(self, title: str, result: CommandResult) -> None:
        cmd_str = " ".join(result.command)
        status = "OK" if result.ok else f"ERR({result.returncode})"
        header = f"{title} [{status}, {result.duration_ms:.0f} ms] $ {cmd_str}"
        self._append_log(header)
        if result.combined_output:
            self._append_log(result.combined_output)

    # ------------------------------------------------------------------
    # ADB Status & Device Discovery
    # ------------------------------------------------------------------

    def _check_adb_status(self) -> None:
        def on_done(res: CommandResult) -> None:
            if res.ok:
                first_line = res.stdout.splitlines()[0] if res.stdout else "ADB Ready"
                self.adb_badge.setObjectName("badgeReady")
                self.adb_badge.setText(first_line.replace("Android Debug Bridge version", "ADB"))
            else:
                self.adb_badge.setObjectName("badgeError")
                self.adb_badge.setText("ADB Not Found")
                self._append_log(res.stderr or "ADB binary not found.")
            self.adb_badge.style().unpolish(self.adb_badge)
            self.adb_badge.style().polish(self.adb_badge)

        self._submit_task(self.client.check_version, on_done, show_busy=False)

    def _choose_adb_path(self) -> None:
        path, _ = QFileDialog.getOpenFileName(
            self,
            "Select adb.exe",
            self.config.adb_path,
            "Executable (*.exe);;All Files (*)",
        )
        if path:
            self.config.adb_path = path
            self.adb_path_edit.setText(path)
            self._save_config()
            self.client = AdbClient(path)
            self._check_adb_status()
            self.refresh_devices()

    def _poll_devices_if_enabled(self) -> None:
        if self.auto_refresh_cb.isChecked() and not self._poll_in_flight:
            self.refresh_devices(silent=True)

    def refresh_devices(self, silent: bool = False) -> None:
        if self._poll_in_flight:
            return
        self._poll_in_flight = True

        def on_done(payload: tuple[list[DeviceInfo], CommandResult]) -> None:
            self._poll_in_flight = False
            devices, res = payload
            if not res.ok and not silent:
                self._log_result("Refresh Devices", res)
            self._apply_device_list(devices)

        def on_err(err: str) -> None:
            self._poll_in_flight = False
            if not silent:
                self._append_log(f"Device refresh failed: {err}")

        self._submit_task(self.client.list_devices, on_done, on_err, show_busy=not silent)

    def _apply_device_list(self, devices: list[DeviceInfo]) -> None:
        previous = self._selected_serial
        self._devices = {d.serial: d for d in devices}

        self.device_list.blockSignals(True)
        self.device_list.clear()

        target_row = -1
        first_ready_row = -1
        for idx, dev in enumerate(devices):
            icon = "●"
            conn = "Wi-Fi" if dev.is_wireless else "USB"
            label = f"{icon}  {dev.display_name}\n    [{dev.state.upper()} • {conn}]"
            item = QListWidgetItem(label)
            item.setData(Qt.UserRole, dev.serial)
            if dev.is_ready:
                item.setForeground(Qt.green)
                if first_ready_row == -1:
                    first_ready_row = idx
            elif dev.state == "unauthorized":
                item.setForeground(Qt.yellow)
            else:
                item.setForeground(Qt.red)
            self.device_list.addItem(item)
            if dev.serial == previous:
                target_row = idx

        if target_row == -1 and first_ready_row != -1:
            target_row = first_ready_row

        if target_row != -1:
            self.device_list.setCurrentRow(target_row)
            self._selected_serial = self.device_list.item(target_row).data(Qt.UserRole)
        else:
            self._selected_serial = None

        self.device_list.blockSignals(False)
        self._update_device_controls_state()

    def _on_device_selection_changed(self) -> None:
        items = self.device_list.selectedItems()
        self._selected_serial = items[0].data(Qt.UserRole) if items else None
        self._update_device_controls_state()

    def _selected_device(self) -> DeviceInfo | None:
        if not self._selected_serial:
            return None
        return self._devices.get(self._selected_serial)

    def _update_device_controls_state(self) -> None:
        dev = self._selected_device()
        ready = bool(dev and dev.is_ready)

        for widget in self._device_widgets:
            widget.setEnabled(ready)

        if dev is None:
            self.selected_device_label.setText("No device selected. Connect a phone via USB or Wi-Fi.")
        elif dev.is_ready:
            self.selected_device_label.setText(f"Active: {dev.display_name}\nState: READY")
        elif dev.state == "unauthorized":
            self.selected_device_label.setText(
                f"Selected: {dev.serial}\nState: UNAUTHORIZED — Accept USB debugging prompt on phone."
            )
        else:
            self.selected_device_label.setText(f"Selected: {dev.serial}\nState: {dev.state.upper()}")

    def _on_auto_refresh_toggled(self, checked: bool) -> None:
        self.config.auto_refresh_devices = checked
        self.config.save()
        if checked:
            self.poll_timer.start()
        else:
            self.poll_timer.stop()

    # ------------------------------------------------------------------
    # Screenshot & Clipboard
    # ------------------------------------------------------------------

    def _on_auto_copy_toggled(self, checked: bool) -> None:
        self.config.auto_copy_clipboard = checked
        self.config.save()

    def _on_screenshot_dir_edited(self) -> None:
        new_dir = self.screenshot_dir_edit.text().strip()
        if new_dir:
            self.config.screenshot_dir = new_dir
            self.config.save()

    def _browse_screenshot_dir(self) -> None:
        folder = QFileDialog.getExistingDirectory(
            self,
            "Select Screenshot Save Folder",
            self.config.screenshot_dir,
        )
        if folder:
            self.screenshot_dir_edit.setText(folder)
            self.config.screenshot_dir = folder
            self.config.save()

    def _open_screenshot_dir(self) -> None:
        target = Path(self.screenshot_dir_edit.text().strip() or self.config.screenshot_dir)
        target.mkdir(parents=True, exist_ok=True)
        QDesktopServices.openUrl(QUrl.fromLocalFile(str(target)))

    def capture_screenshot(self) -> None:
        dev = self._selected_device()
        if not dev or not dev.is_ready:
            self.screenshot_status_label.setText("Select a ready device before taking a screenshot.")
            self.hud_toast.show_error("No ready ADB device selected")
            return

        save_dir = self.screenshot_dir_edit.text().strip() or self.config.screenshot_dir
        self.config.screenshot_dir = save_dir
        self.config.save()

        self.screenshot_status_label.setText(f"Capturing screenshot from {dev.serial}...")
        self.hud_toast.show_capturing()

        def work() -> tuple[Path | None, CommandResult]:
            return self.client.take_screenshot(
                serial=dev.serial,
                save_dir=save_dir,
                prefix=self.config.screenshot_prefix,
            )

        def on_done(payload: tuple[Path | None, CommandResult]) -> None:
            out_path, res = payload
            self._log_result("Take Screenshot", res)
            if not out_path or not out_path.exists():
                self.screenshot_status_label.setText("Screenshot failed. Check Output Log.")
                self.hud_toast.show_error("Screenshot Failed")
                return

            self._last_screenshot_path = out_path
            self.copy_last_btn.setEnabled(True)
            self._update_preview(out_path)

            if self.auto_copy_cb.isChecked():
                copied = self._copy_image_to_clipboard(out_path)
                if copied:
                    msg = f"Saved & Copied to Clipboard: {out_path.name}"
                    self.screenshot_status_label.setText(msg)
                    self.hud_toast.show_captured(copied=True)
                else:
                    self.screenshot_status_label.setText(f"Saved {out_path.name} (Clipboard copy failed)")
                    self.hud_toast.show_captured(copied=False)
            else:
                self.screenshot_status_label.setText(f"Saved: {out_path.name}")
                self.hud_toast.show_captured(copied=False)

        def on_err(err: str) -> None:
            self.screenshot_status_label.setText("Screenshot failed. Check Output Log.")
            self.hud_toast.show_error("Screenshot Failed")
            self._append_log(f"[ERROR] Screenshot: {err}")

        self._submit_task(work, on_done, on_err)

    def _copy_last_screenshot(self) -> None:
        if (
            self._last_screenshot_path
            and self._last_screenshot_path.exists()
            and self._copy_image_to_clipboard(self._last_screenshot_path)
        ):
            self.screenshot_status_label.setText(
                f"Copied to Clipboard: {self._last_screenshot_path.name}"
            )

    def _copy_image_to_clipboard(self, image_path: Path) -> bool:
        img = QImage(str(image_path))
        if img.isNull():
            return False
        QApplication.clipboard().setImage(img)
        return True

    def _update_preview(self, image_path: Path) -> None:
        pix = QPixmap(str(image_path))
        if pix.isNull():
            return
        scaled = pix.scaled(
            self.preview_label.size(),
            Qt.KeepAspectRatio,
            Qt.SmoothTransformation,
        )
        self.preview_label.setPixmap(scaled)

    # ------------------------------------------------------------------
    # Generic Task Runners
    # ------------------------------------------------------------------

    def _run_adb_task(
        self,
        title: str,
        fn: Callable[[], CommandResult],
        refresh_after: bool = False,
    ) -> None:
        def on_done(res: CommandResult) -> None:
            self._log_result(title, res)
            if refresh_after:
                self.refresh_devices(silent=True)

        self._submit_task(fn, on_done)

    def _run_device_task(
        self,
        title: str,
        fn: Callable[[str], CommandResult],
        refresh_after: bool = False,
    ) -> None:
        dev = self._selected_device()
        if not dev or not dev.is_ready:
            self._append_log(f"[{title}] No ready device selected.")
            return
        serial = dev.serial

        def on_done(res: CommandResult) -> None:
            self._log_result(title, res)
            if refresh_after:
                self.refresh_devices(silent=True)

        self._submit_task(lambda: fn(serial), on_done)

    # ------------------------------------------------------------------
    # Controls, Screen, Apps, Files, Wireless, Shell Handlers
    # ------------------------------------------------------------------

    def _send_text(self) -> None:
        text = self.send_text_edit.text()
        if not text:
            return
        self._run_device_task("Send Text", lambda s: self.client.send_text(s, text))

    def _open_url(self) -> None:
        url = self.open_url_edit.text().strip()
        if not url:
            return
        self._run_device_task("Open URL", lambda s: self.client.open_url(s, url))

    def _confirm_reboot(self, label: str, mode: str) -> None:
        reply = QMessageBox.question(
            self,
            "Confirm Reboot",
            f"Run '{label}' on the selected device?",
            QMessageBox.Yes | QMessageBox.No,
        )
        if reply == QMessageBox.Yes:
            self._run_device_task(label, lambda s: self.client.reboot(s, mode), refresh_after=True)

    def _set_screen_size(self) -> None:
        val = self.wm_size_edit.text().strip()
        if not val:
            return
        self._run_device_task(f"Set Screen Size ({val})", lambda s: self.client.set_screen_size(s, val))

    def _set_screen_dpi(self) -> None:
        val = self.wm_dpi_edit.text().strip()
        if not val:
            return
        self._run_device_task(f"Set Screen DPI ({val})", lambda s: self.client.set_screen_density(s, val))

    def _toggle_recording(self) -> None:
        if self._rec_session is not None:
            self.record_btn.setEnabled(False)
            self.record_status_label.setText("Stopping & saving MP4...")
            self._rec_session.request_stop()
            return

        dev = self._selected_device()
        if not dev or not dev.is_ready:
            return

        max_secs = self.record_duration_spin.value()
        save_dir = self.screenshot_dir_edit.text().strip() or self.config.screenshot_dir
        session = ScreenRecorderSession(
            self.client,
            dev.serial,
            save_dir,
            max_secs,
            scrcpy_path=self.config.scrcpy_path,
        )
        self._rec_session = session
        self._rec_elapsed_secs = 0
        self.record_duration_spin.setEnabled(False)
        self.record_btn.setText("Stop Recording")
        self.record_btn.setObjectName("dangerBtn")
        self.record_btn.style().unpolish(self.record_btn)
        self.record_btn.style().polish(self.record_btn)
        self.record_status_label.setText("Starting recorder...")

        def work() -> RecordingOutcome:
            mode = session.start()
            QTimer.singleShot(0, self, lambda m=mode: self._on_record_started(m))
            return session.run_until_stopped()

        def on_done(outcome: RecordingOutcome) -> None:
            self._rec_timer.stop()
            self._rec_session = None
            self.record_duration_spin.setEnabled(True)
            self.record_btn.setEnabled(True)
            self.record_btn.setText("Start Recording")
            self.record_btn.setObjectName("")
            self.record_btn.style().unpolish(self.record_btn)
            self.record_btn.style().polish(self.record_btn)

            self._log_result(f"Screen Record ({outcome.mode})", outcome.result)
            if outcome.output_path:
                self.record_status_label.setText(f"Saved: {outcome.output_path.name}")
                self._append_log(f"Recording saved: {outcome.output_path}")
            else:
                self.record_status_label.setText("Recording failed — check Output Log.")

        def on_err(err: str) -> None:
            self._rec_timer.stop()
            self._rec_session = None
            self.record_duration_spin.setEnabled(True)
            self.record_btn.setEnabled(True)
            self.record_btn.setText("Start Recording")
            self.record_btn.setObjectName("")
            self.record_btn.style().unpolish(self.record_btn)
            self.record_btn.style().polish(self.record_btn)
            self.record_status_label.setText("Recording failed.")
            self._append_log(f"[ERROR] Screen Record: {err}")

        self._submit_task(work, on_done, on_err)

    def _record_mode_label(self, mode: str) -> str:
        if mode == "scrcpy":
            return "scrcpy 60fps"
        if mode == "native":
            return "Native"
        return "Fallback screencap->MP4"

    def _on_record_started(self, mode: str) -> None:
        if self._rec_session is None:
            return
        self._rec_elapsed_secs = 0
        mode_label = self._record_mode_label(mode)
        self.record_status_label.setText(f"Recording ({mode_label}): 00:00")
        self._rec_timer.start()
        self._append_log(f"Screen recording started ({mode_label})...")

    def _on_record_tick(self) -> None:
        if self._rec_session is None:
            self._rec_timer.stop()
            return
        self._rec_elapsed_secs += 1
        mins, secs = divmod(self._rec_elapsed_secs, 60)
        mode_label = self._record_mode_label(self._rec_session.mode)
        self.record_status_label.setText(f"Recording ({mode_label}): {mins:02d}:{secs:02d}")

    def _load_packages(self) -> None:
        dev = self._selected_device()
        if not dev or not dev.is_ready:
            return
        mode = self.pkg_filter_combo.currentData()

        def on_done(payload: tuple[list[str], CommandResult]) -> None:
            pkgs, res = payload
            self._log_result(f"List Packages ({mode})", res)
            if res.ok:
                self._all_packages = pkgs
                self._filter_packages_list()

        self._submit_task(lambda: self.client.list_packages(dev.serial, mode), on_done)

    def _filter_packages_list(self) -> None:
        query = self.pkg_search_edit.text().strip().lower()
        self.package_list.clear()
        for pkg in self._all_packages:
            if not query or query in pkg.lower():
                self.package_list.addItem(pkg)

    def _selected_package(self) -> str | None:
        item = self.package_list.currentItem()
        return item.text() if item else None

    def _install_apk(self) -> None:
        apk_path, _ = QFileDialog.getOpenFileName(
            self,
            "Select APK to Install",
            str(Path.home()),
            "Android Package (*.apk);;All Files (*)",
        )
        if apk_path:
            self._run_device_task(
                f"Install {Path(apk_path).name}",
                lambda s: self.client.install_apk(s, apk_path, replace=True),
            )

    def _launch_selected_pkg(self) -> None:
        pkg = self._selected_package()
        if pkg:
            self._run_device_task(f"Launch {pkg}", lambda s: self.client.launch_package(s, pkg))

    def _force_stop_selected_pkg(self) -> None:
        pkg = self._selected_package()
        if pkg:
            self._run_device_task(f"Force Stop {pkg}", lambda s: self.client.force_stop_package(s, pkg))

    def _clear_data_selected_pkg(self) -> None:
        pkg = self._selected_package()
        if not pkg:
            return
        reply = QMessageBox.question(
            self,
            "Clear App Data",
            f"Clear all app data for '{pkg}'?",
            QMessageBox.Yes | QMessageBox.No,
        )
        if reply == QMessageBox.Yes:
            self._run_device_task(f"Clear Data {pkg}", lambda s: self.client.clear_package_data(s, pkg))

    def _pull_selected_pkg_apk(self) -> None:
        pkg = self._selected_package()
        if not pkg:
            return
        dest_dir = QFileDialog.getExistingDirectory(self, "Select Destination Folder", self.config.screenshot_dir)
        if dest_dir:
            self._run_device_task(f"Pull APK {pkg}", lambda s: self.client.pull_apk(s, pkg, dest_dir))

    def _uninstall_selected_pkg(self) -> None:
        pkg = self._selected_package()
        if not pkg:
            return
        reply = QMessageBox.question(
            self,
            "Uninstall App",
            f"Uninstall '{pkg}' from the device?",
            QMessageBox.Yes | QMessageBox.No,
        )
        if reply == QMessageBox.Yes:
            self._run_device_task(f"Uninstall {pkg}", lambda s: self.client.uninstall_package(s, pkg))

    def _push_file(self) -> None:
        local_file, _ = QFileDialog.getOpenFileName(self, "Select File to Push", str(Path.home()))
        if not local_file:
            return
        remote = self.push_remote_edit.text().strip() or "/sdcard/Download/"
        self._run_device_task(
            f"Push {Path(local_file).name}",
            lambda s: self.client.push_file(s, local_file, remote),
        )

    def _pull_file(self) -> None:
        remote = self.pull_remote_edit.text().strip()
        if not remote:
            return
        dest_dir = QFileDialog.getExistingDirectory(self, "Select Local Destination Folder", str(Path.home()))
        if not dest_dir:
            return
        self._run_device_task(f"Pull {remote}", lambda s: self.client.pull_file(s, remote, dest_dir))

    def _connect_wireless(self) -> None:
        target = self.wifi_target_combo.currentText().strip()
        if not target:
            return
        self.config.add_wireless_target(target)
        self.config.save()
        if self.wifi_target_combo.findText(target) == -1:
            self.wifi_target_combo.insertItem(0, target)
        self._run_adb_task(
            f"Connect {target}",
            lambda: self.client.connect_wireless(target),
            refresh_after=True,
        )

    def _disconnect_wireless(self) -> None:
        target = self.wifi_target_combo.currentText().strip()
        self._run_adb_task(
            f"Disconnect {target or 'All'}",
            lambda: self.client.disconnect_wireless(target),
            refresh_after=True,
        )

    def _pair_wireless(self) -> None:
        target = self.pair_target_edit.text().strip()
        code = self.pair_code_edit.text().strip()
        if not target or not code:
            return
        self._run_adb_task(
            f"Pair {target}",
            lambda: self.client.pair_wireless(target, code),
            refresh_after=True,
        )

    def _run_custom_cmd(self) -> None:
        raw = self.custom_cmd_edit.text().strip()
        if not raw:
            return
        dev = self._selected_device()
        serial = dev.serial if dev and dev.is_ready else None
        self._run_adb_task("Custom Command", lambda: self.client.run_custom(serial, raw))

    def _run_preset_cmd(self, label: str, cmd: str) -> None:
        self._run_device_task(f"Preset: {label}", lambda s: self.client.run_custom(s, cmd))

    def _dump_logcat(self) -> None:
        self._run_device_task("Logcat Dump", lambda s: self.client.dump_logcat(s, 400))

    def _save_logcat(self) -> None:
        dev = self._selected_device()
        if not dev or not dev.is_ready:
            return
        out_file, _ = QFileDialog.getSaveFileName(
            self,
            "Save Logcat",
            str(Path(self.config.screenshot_dir) / "logcat.txt"),
            "Text Files (*.txt);;All Files (*)",
        )
        if not out_file:
            return

        def work() -> CommandResult:
            res = self.client.dump_logcat(dev.serial, 2000)
            if res.ok:
                Path(out_file).write_text(res.stdout, encoding="utf-8")
            return res

        self._run_adb_task(f"Save Logcat -> {Path(out_file).name}", work)

    def _copy_console_log(self) -> None:
        QApplication.clipboard().setText(self.console_log.toPlainText())

    # ------------------------------------------------------------------
    # Tray, Global Hotkey & Startup Settings
    # ------------------------------------------------------------------

    @staticmethod
    def _create_app_icon() -> QIcon:
        return load_app_icon()

    def _setup_tray(self) -> None:
        self.tray_icon: QSystemTrayIcon | None = None
        if not QSystemTrayIcon.isSystemTrayAvailable():
            return
        tray = QSystemTrayIcon(self.windowIcon(), self)
        tray.setToolTip("ADB Studio")

        menu = QMenu(self)
        show_action = QAction("Show ADB Studio", self)
        show_action.triggered.connect(self._restore_from_tray)
        shot_action = QAction("Take Screenshot", self)
        shot_action.triggered.connect(self.capture_screenshot)
        quit_action = QAction("Quit ADB Studio", self)
        quit_action.triggered.connect(self._quit_app)

        menu.addAction(show_action)
        menu.addAction(shot_action)
        menu.addSeparator()
        menu.addAction(quit_action)

        tray.setContextMenu(menu)
        tray.activated.connect(self._on_tray_activated)
        tray.show()
        self.tray_icon = tray

    def tray_available(self) -> bool:
        return self.tray_icon is not None

    def show_tray_message(self, title: str, message: str) -> None:
        if self.tray_icon is not None:
            self.tray_icon.showMessage(title, message, QSystemTrayIcon.Information, 2500)

    def _on_tray_activated(self, reason: QSystemTrayIcon.ActivationReason) -> None:
        if reason in (QSystemTrayIcon.Trigger, QSystemTrayIcon.DoubleClick):
            self._restore_from_tray()

    def _restore_from_tray(self) -> None:
        self.showNormal()
        self.raise_()
        self.activateWindow()

    def _setup_global_hotkey(self) -> None:
        app = QApplication.instance()
        self.hotkey_manager = GlobalHotkeyManager(app)
        self.hotkey_manager.triggered.connect(self.capture_screenshot)
        ok, msg = self.hotkey_manager.register(self.config.global_hotkey)
        self._update_hotkey_status(ok, msg)

    def _update_hotkey_status(self, ok: bool, msg: str) -> None:
        color = "#6ee7b7" if ok else "#fca5a5"
        self.hotkey_status_label.setStyleSheet(f"color: {color}; font-size: 12px;")
        self.hotkey_status_label.setText(msg)

    def _apply_global_hotkey(self) -> None:
        seq_str = self.hotkey_edit.keySequence().toString(QKeySequence.PortableText).strip()
        ok, msg = self.hotkey_manager.register(seq_str)
        self._update_hotkey_status(ok, msg)
        if ok:
            self.config.global_hotkey = seq_str
            self._save_config()
            self._append_log(msg)

    def _clear_global_hotkey(self) -> None:
        self.hotkey_edit.clear()
        self.hotkey_manager.unregister()
        self.config.global_hotkey = ""
        self._save_config()
        self._update_hotkey_status(True, "Global hotkey disabled.")

    def _on_bg_toggled(self, checked: bool) -> None:
        self.config.run_in_background = checked
        self._save_config()

    def _main_script_path(self) -> Path:
        return Path(__file__).resolve().parents[2] / "main.py"

    def _on_autostart_toggled(self, checked: bool) -> None:
        ok, msg = set_autostart(
            checked,
            self._main_script_path(),
            start_minimized=self.start_min_cb.isChecked(),
        )
        color = "#6ee7b7" if ok else "#fca5a5"
        self.startup_status_label.setStyleSheet(f"color: {color}; font-size: 12px;")
        self.startup_status_label.setText(msg)
        if not ok:
            self.autostart_cb.blockSignals(True)
            self.autostart_cb.setChecked(not checked)
            self.autostart_cb.blockSignals(False)

    def _on_start_min_toggled(self, checked: bool) -> None:
        self.config.start_minimized = checked
        self._save_config()
        if self.autostart_cb.isChecked():
            _ok, msg = set_autostart(True, self._main_script_path(), start_minimized=checked)
            self.startup_status_label.setText(msg)

    def _choose_scrcpy_path(self) -> None:
        path, _ = QFileDialog.getOpenFileName(
            self,
            "Select scrcpy.exe",
            self.config.scrcpy_path or str(Path.home()),
            "Executable (*.exe);;All Files (*)",
        )
        if path:
            self.config.scrcpy_path = path
            self.scrcpy_path_edit.setText(path)
            self._save_config()
            self._append_log(f"scrcpy path updated: {path}")

    def _on_prefix_saved(self) -> None:
        prefix = self.prefix_edit.text().strip()
        if prefix:
            self.config.screenshot_prefix = prefix
            self._save_config()
            self._append_log(f"Screenshot filename prefix set to: {prefix}")

    def _save_config(self) -> None:
        self.config.save(self.config_path)

    def _quit_app(self) -> None:
        self._force_quit = True
        self.close()
        QApplication.quit()

    def closeEvent(self, event) -> None:
        if self.config.run_in_background and not self._force_quit and self.tray_available():
            event.ignore()
            self.hide()
            if not self._tray_notified_once:
                self._tray_notified_once = True
                hk = self.config.global_hotkey or "None"
                self.show_tray_message(
                    "ADB Studio Running in Background",
                    f"Use tray icon to reopen. Global screenshot hotkey: {hk}",
                )
            return

        self.hotkey_manager.unregister()
        self.hud_toast.close()
        if self.tray_icon is not None:
            self.tray_icon.hide()
        self.poll_timer.stop()
        self._rec_timer.stop()
        if self._rec_session is not None:
            self._rec_session.request_stop()
        self._save_config()
        super().closeEvent(event)
