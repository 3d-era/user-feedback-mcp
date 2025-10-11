import os
import sys
import json
import psutil
import argparse
import subprocess
import threading
from typing import Optional, TypedDict

from PySide6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
    QLabel, QLineEdit, QPushButton, QCheckBox, QTextEdit, QGroupBox, QTextBrowser, QSplitter, QComboBox, QFileDialog
)
from PySide6.QtCore import Qt, Signal, QObject, QTimer, QSettings
from PySide6.QtGui import QTextCursor, QIcon, QKeyEvent, QFont, QFontDatabase, QPalette, QColor, QShortcut, QKeySequence

class FeedbackResult(TypedDict):
    command_logs: str
    user_feedback: str

class FeedbackConfig(TypedDict):
    run_command: str
    execute_automatically: bool = False
    command_templates: list = []  # List of saved command templates

def detect_log_level(line: str) -> str:
    """Detect log level from line content"""
    import re

    if re.search(r'\b(error|ERROR|Error|failed|FAILED|Failed|exception|Exception|EXCEPTION)\b', line):
        return "Error"
    elif re.search(r'\b(warning|WARNING|Warning|warn|WARN|Warn)\b', line):
        return "Warning"
    elif re.search(r'\b(success|SUCCESS|Success|passed|PASSED|Passed|completed|COMPLETED|Completed|✓|✔)\b', line):
        return "Success"
    elif re.search(r'\b(info|INFO|Info|note|NOTE|Note)\b', line):
        return "Info"
    else:
        return "Other"

def highlight_log_line(line: str) -> str:
    """Apply syntax highlighting to a log line"""
    import re

    # Escape HTML special characters
    line = line.replace('&', '&amp;').replace('<', '&lt;').replace('>', '&gt;')

    # Error patterns (red)
    if re.search(r'\b(error|ERROR|Error|failed|FAILED|Failed|exception|Exception|EXCEPTION)\b', line):
        return f'<span style="color: #e74c3c; font-weight: bold;">{line}</span>'

    # Warning patterns (yellow/orange)
    if re.search(r'\b(warning|WARNING|Warning|warn|WARN|Warn)\b', line):
        return f'<span style="color: #f39c12; font-weight: bold;">{line}</span>'

    # Success patterns (green)
    if re.search(r'\b(success|SUCCESS|Success|passed|PASSED|Passed|completed|COMPLETED|Completed|✓|✔)\b', line):
        return f'<span style="color: #2ecc71; font-weight: bold;">{line}</span>'

    # Info patterns (blue)
    if re.search(r'\b(info|INFO|Info|note|NOTE|Note)\b', line):
        return f'<span style="color: #3498db;">{line}</span>'

    # File paths (cyan)
    line = re.sub(r'([/\\][\w/\\.-]+\.\w+)', r'<span style="color: #1abc9c;">\1</span>', line)

    # URLs (blue underline)
    line = re.sub(r'(https?://[^\s]+)', r'<span style="color: #3498db; text-decoration: underline;">\1</span>', line)

    # Numbers (purple)
    line = re.sub(r'\b(\d+)\b', r'<span style="color: #9b59b6;">\1</span>', line)

    # Timestamps (gray)
    line = re.sub(r'(\d{2}:\d{2}:\d{2})', r'<span style="color: #95a5a6;">\1</span>', line)

    return line

def markdown_to_html(markdown_text: str, is_dark_theme: bool = True) -> str:
    """Convert markdown to HTML with proper formatting support"""
    import re

    # Theme colors
    if is_dark_theme:
        text_color = "#ecf0f1"
        code_bg = "#1e1e1e"
        code_color = "#d4d4d4"
        header_color = "#3498db"
    else:
        text_color = "#212529"
        code_bg = "#f5f5f5"
        code_color = "#c7254e"
        header_color = "#0056b3"

    lines = markdown_text.split('\n')
    html_lines = []
    in_code_block = False
    code_block_content = []
    in_list = False

    for line in lines:
        # Code blocks
        if line.strip().startswith('```'):
            if in_code_block:
                # End code block
                code_content = '\n'.join(code_block_content)
                html_lines.append(f'<pre style="background-color: {code_bg}; padding: 8px; margin: 5px 0; border-radius: 3px; color: {code_color}; font-family: monospace; font-size: 10pt;"><code>{code_content}</code></pre>')
                code_block_content = []
                in_code_block = False
            else:
                # Start code block
                in_code_block = True
            continue

        if in_code_block:
            code_block_content.append(line)
            continue

        # Headers
        if line.startswith('### '):
            html_lines.append(f'<h3 style="color: {header_color}; margin: 8px 0 4px 0; font-size: 13pt;">{line[4:]}</h3>')
            continue
        elif line.startswith('## '):
            html_lines.append(f'<h2 style="color: {header_color}; margin: 10px 0 5px 0; font-size: 14pt;">{line[3:]}</h2>')
            continue
        elif line.startswith('# '):
            html_lines.append(f'<h1 style="color: {header_color}; margin: 12px 0 6px 0; font-size: 16pt;">{line[2:]}</h1>')
            continue

        # Lists
        if line.strip().startswith('- '):
            if not in_list:
                html_lines.append('<ul style="margin: 3px 0; padding-left: 20px;">')
                in_list = True
            content = line.strip()[2:]
            # Process inline formatting
            content = re.sub(r'\*\*(.+?)\*\*', r'<b>\1</b>', content)
            content = re.sub(r'`(.+?)`', f'<code style="background-color: {code_bg}; padding: 1px 4px; border-radius: 2px; color: {code_color}; font-size: 10pt;">\\1</code>', content)
            html_lines.append(f'<li style="margin: 2px 0; font-size: 11pt;">{content}</li>')
            continue
        else:
            if in_list:
                html_lines.append('</ul>')
                in_list = False

        # Empty lines - use double <br> to create proper paragraph spacing
        if not line.strip():
            html_lines.append('<br><br>')
            continue

        # Regular text with inline formatting
        processed_line = line
        # Bold
        processed_line = re.sub(r'\*\*(.+?)\*\*', r'<b>\1</b>', processed_line)
        processed_line = re.sub(r'__(.+?)__', r'<b>\1</b>', processed_line)
        # Italic
        processed_line = re.sub(r'\*([^*]+?)\*', r'<i>\1</i>', processed_line)
        # Inline code
        processed_line = re.sub(r'`(.+?)`', f'<code style="background-color: {code_bg}; padding: 1px 4px; border-radius: 2px; color: {code_color}; font-size: 10pt;">\\1</code>', processed_line)

        # Add line break after each regular text line to preserve single \n
        html_lines.append(f'<span style="font-size: 11pt;">{processed_line}</span><br>')

    # Close any open list
    if in_list:
        html_lines.append('</ul>')

    html_content = ''.join(html_lines)

    return f'<div style="color: {text_color}; font-family: Arial, sans-serif; font-size: 11pt; line-height: 1.4; white-space: pre-wrap;">{html_content}</div>'

def set_dark_title_bar(widget: QWidget, dark_title_bar: bool) -> None:
    # Ensure we're on Windows
    if sys.platform != "win32":
        return

    from ctypes import windll, c_uint32, byref

    # Get Windows build number
    build_number = sys.getwindowsversion().build
    if build_number < 17763:  # Windows 10 1809 minimum
        return

    # Check if the widget's property already matches the setting
    dark_prop = widget.property("DarkTitleBar")
    if dark_prop is not None and dark_prop == dark_title_bar:
        return

    # Set the property (True if dark_title_bar != 0, False otherwise)
    widget.setProperty("DarkTitleBar", dark_title_bar)

    # Load dwmapi.dll and call DwmSetWindowAttribute
    dwmapi = windll.dwmapi
    hwnd = widget.winId()  # Get the window handle
    attribute = 20 if build_number >= 18985 else 19  # Use newer attribute for newer builds
    c_dark_title_bar = c_uint32(dark_title_bar)  # Convert to C-compatible uint32
    dwmapi.DwmSetWindowAttribute(hwnd, attribute, byref(c_dark_title_bar), 4)

    # HACK: Create a 1x1 pixel frameless window to force redraw
    temp_widget = QWidget(None, Qt.FramelessWindowHint)
    temp_widget.resize(1, 1)
    temp_widget.move(widget.pos())
    temp_widget.show()
    temp_widget.deleteLater()  # Safe deletion in Qt event loop

def get_dark_mode_palette(app: QApplication):
    darkPalette = app.palette()
    darkPalette.setColor(QPalette.Window, QColor(53, 53, 53))
    darkPalette.setColor(QPalette.WindowText, Qt.white)
    darkPalette.setColor(QPalette.Disabled, QPalette.WindowText, QColor(127, 127, 127))
    darkPalette.setColor(QPalette.Base, QColor(42, 42, 42))
    darkPalette.setColor(QPalette.AlternateBase, QColor(66, 66, 66))
    darkPalette.setColor(QPalette.ToolTipBase, QColor(53, 53, 53))
    darkPalette.setColor(QPalette.ToolTipText, Qt.white)
    darkPalette.setColor(QPalette.Text, Qt.white)
    darkPalette.setColor(QPalette.Disabled, QPalette.Text, QColor(127, 127, 127))
    darkPalette.setColor(QPalette.Dark, QColor(35, 35, 35))
    darkPalette.setColor(QPalette.Shadow, QColor(20, 20, 20))
    darkPalette.setColor(QPalette.Button, QColor(53, 53, 53))
    darkPalette.setColor(QPalette.ButtonText, Qt.white)
    darkPalette.setColor(QPalette.Disabled, QPalette.ButtonText, QColor(127, 127, 127))
    darkPalette.setColor(QPalette.BrightText, Qt.red)
    darkPalette.setColor(QPalette.Link, QColor(42, 130, 218))
    darkPalette.setColor(QPalette.Highlight, QColor(42, 130, 218))
    darkPalette.setColor(QPalette.Disabled, QPalette.Highlight, QColor(80, 80, 80))
    darkPalette.setColor(QPalette.HighlightedText, Qt.white)
    darkPalette.setColor(QPalette.Disabled, QPalette.HighlightedText, QColor(127, 127, 127))
    darkPalette.setColor(QPalette.PlaceholderText, QColor(127, 127, 127))
    return darkPalette

def get_light_mode_palette(app: QApplication):
    lightPalette = QPalette()
    lightPalette.setColor(QPalette.Window, QColor(240, 240, 240))
    lightPalette.setColor(QPalette.WindowText, Qt.black)
    lightPalette.setColor(QPalette.Base, QColor(255, 255, 255))
    lightPalette.setColor(QPalette.AlternateBase, QColor(245, 245, 245))
    lightPalette.setColor(QPalette.ToolTipBase, Qt.white)
    lightPalette.setColor(QPalette.ToolTipText, Qt.black)
    lightPalette.setColor(QPalette.Text, Qt.black)
    lightPalette.setColor(QPalette.Button, QColor(240, 240, 240))
    lightPalette.setColor(QPalette.ButtonText, Qt.black)
    lightPalette.setColor(QPalette.BrightText, Qt.red)
    lightPalette.setColor(QPalette.Link, QColor(0, 0, 255))
    lightPalette.setColor(QPalette.Highlight, QColor(42, 130, 218))
    lightPalette.setColor(QPalette.HighlightedText, Qt.white)
    return lightPalette

def kill_tree(process: subprocess.Popen):
    killed: list[psutil.Process] = []
    parent = psutil.Process(process.pid)
    for proc in parent.children(recursive=True):
        try:
            proc.kill()
            killed.append(proc)
        except psutil.Error:
            pass
    try:
        parent.kill()
    except psutil.Error:
        pass
    killed.append(parent)

    # Terminate any remaining processes
    for proc in killed:
        try:
            if proc.is_running():
                proc.terminate()
        except psutil.Error:
            pass

def get_user_environment() -> dict[str, str]:
    if sys.platform != "win32":
        return os.environ.copy()

    import ctypes
    from ctypes import wintypes

    # Load required DLLs
    advapi32 = ctypes.WinDLL("advapi32")
    userenv = ctypes.WinDLL("userenv")
    kernel32 = ctypes.WinDLL("kernel32")

    # Constants
    TOKEN_QUERY = 0x0008

    # Function prototypes
    OpenProcessToken = advapi32.OpenProcessToken
    OpenProcessToken.argtypes = [wintypes.HANDLE, wintypes.DWORD, ctypes.POINTER(wintypes.HANDLE)]
    OpenProcessToken.restype = wintypes.BOOL

    CreateEnvironmentBlock = userenv.CreateEnvironmentBlock
    CreateEnvironmentBlock.argtypes = [ctypes.POINTER(ctypes.c_void_p), wintypes.HANDLE, wintypes.BOOL]
    CreateEnvironmentBlock.restype = wintypes.BOOL

    DestroyEnvironmentBlock = userenv.DestroyEnvironmentBlock
    DestroyEnvironmentBlock.argtypes = [wintypes.LPVOID]
    DestroyEnvironmentBlock.restype = wintypes.BOOL

    GetCurrentProcess = kernel32.GetCurrentProcess
    GetCurrentProcess.argtypes = []
    GetCurrentProcess.restype = wintypes.HANDLE

    CloseHandle = kernel32.CloseHandle
    CloseHandle.argtypes = [wintypes.HANDLE]
    CloseHandle.restype = wintypes.BOOL

    # Get process token
    token = wintypes.HANDLE()
    if not OpenProcessToken(GetCurrentProcess(), TOKEN_QUERY, ctypes.byref(token)):
        raise RuntimeError("Failed to open process token")

    try:
        # Create environment block
        environment = ctypes.c_void_p()
        if not CreateEnvironmentBlock(ctypes.byref(environment), token, False):
            raise RuntimeError("Failed to create environment block")

        try:
            # Convert environment block to list of strings
            result = {}
            env_ptr = ctypes.cast(environment, ctypes.POINTER(ctypes.c_wchar))
            offset = 0

            while True:
                # Get string at current offset
                current_string = ""
                while env_ptr[offset] != "\0":
                    current_string += env_ptr[offset]
                    offset += 1

                # Skip null terminator
                offset += 1

                # Break if we hit double null terminator
                if not current_string:
                    break

                equal_index = current_string.index("=")
                if equal_index == -1:
                    continue

                key = current_string[:equal_index]
                value = current_string[equal_index + 1:]
                result[key] = value

            return result

        finally:
            DestroyEnvironmentBlock(environment)

    finally:
        CloseHandle(token)

class DragDropLineEdit(QLineEdit):
    """QLineEdit with drag & drop support for files"""
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setAcceptDrops(True)

    def dragEnterEvent(self, event):
        if event.mimeData().hasUrls():
            event.acceptProposedAction()
        else:
            super().dragEnterEvent(event)

    def dropEvent(self, event):
        if event.mimeData().hasUrls():
            urls = event.mimeData().urls()
            if urls:
                # Get file path from first URL
                file_path = urls[0].toLocalFile()
                if file_path:
                    # Insert file path at cursor position
                    cursor_pos = self.cursorPosition()
                    current_text = self.text()
                    new_text = current_text[:cursor_pos] + file_path + current_text[cursor_pos:]
                    self.setText(new_text)
                    # Move cursor after inserted path
                    self.setCursorPosition(cursor_pos + len(file_path))
            event.acceptProposedAction()
        else:
            super().dropEvent(event)

class FeedbackTextEdit(QTextEdit):
    def __init__(self, parent=None):
        super().__init__(parent)

    def keyPressEvent(self, event: QKeyEvent):
        if event.key() == Qt.Key_Return and event.modifiers() == Qt.ControlModifier:
            # Find the parent FeedbackUI instance and call submit
            parent = self.parent()
            while parent and not isinstance(parent, FeedbackUI):
                parent = parent.parent()
            if parent:
                parent._submit_feedback()
        else:
            super().keyPressEvent(event)

class LogSignals(QObject):
    append_log = Signal(str)

class FeedbackUI(QMainWindow):
    def __init__(self, project_directory: str, prompt: str):
        super().__init__()
        self.project_directory = project_directory
        self.prompt = prompt
        self.config_path = os.path.join(project_directory, ".user-feedback.json")
        self.history_path = os.path.join(project_directory, ".user-feedback-history.json")
        self.config = self._load_config()
        self.history = self._load_history()

        # Load theme preference
        self.settings = QSettings("UserFeedback", "MainWindow")
        self.is_dark_theme = self.settings.value("dark_theme", True, type=bool)

        self.process: Optional[subprocess.Popen] = None
        self.log_buffer = []
        self.log_entries = []  # Store log entries with metadata: [(line, level, line_number), ...]
        self.feedback_result = None
        self.log_signals = LogSignals()
        self.log_signals.append_log.connect(self._append_log)

        self.setWindowTitle("User Feedback")
        self.setWindowIcon(QIcon("icons/feedback.png"))
        self.setWindowFlags(self.windowFlags() | Qt.WindowStaysOnTopHint)

        self._create_ui()

        # Restore window geometry
        settings = QSettings("UserFeedback", "MainWindow")
        geometry = settings.value("geometry")
        if geometry:
            self.restoreGeometry(geometry)
        else:
            # Default size and center on screen
            self.resize(800, 600)
            screen = QApplication.primaryScreen().geometry()
            x = (screen.width() - 800) // 2
            y = (screen.height() - 600) // 2
            self.move(x, y)

        # Restore window state
        state = settings.value("windowState")
        if state:
            self.restoreState(state)

        set_dark_title_bar(self, True)

        if self.config.get("execute_automatically", False):
            self._run_command()

    def _load_config(self) -> FeedbackConfig:
        try:
            if os.path.exists(self.config_path):
                with open(self.config_path, "r") as f:
                    return FeedbackConfig(**json.load(f))
        except Exception:
            pass
        return FeedbackConfig(run_command="", execute_automatically=False)

    def _save_config(self):
        with open(self.config_path, "w") as f:
            json.dump(self.config, f, indent=2)

    def _load_history(self) -> list:
        """Load feedback history from file"""
        try:
            if os.path.exists(self.history_path):
                with open(self.history_path, "r") as f:
                    return json.load(f)
        except Exception:
            pass
        return []

    def _save_history(self):
        """Save feedback history to file (keep last 20 entries)"""
        try:
            # Keep only last 20 entries
            history_to_save = self.history[-20:] if len(self.history) > 20 else self.history
            with open(self.history_path, "w") as f:
                json.dump(history_to_save, f, indent=2)
        except Exception as e:
            print(f"Failed to save history: {e}")

    def _add_to_history(self, feedback: str):
        """Add feedback to history"""
        import datetime
        entry = {
            "timestamp": datetime.datetime.now().isoformat(),
            "feedback": feedback,
            "prompt": self.prompt[:100]  # Store first 100 chars of prompt
        }
        self.history.append(entry)
        self._save_history()

    def _format_windows_path(self, path: str) -> str:
        if sys.platform == "win32":
            # Convert forward slashes to backslashes
            path = path.replace("/", "\\")
            # Capitalize drive letter if path starts with x:\
            if len(path) >= 2 and path[1] == ":" and path[0].isalpha():
                path = path[0].upper() + path[1:]
        return path

    def _create_menu_bar(self):
        """Create menu bar with View options"""
        menubar = self.menuBar()

        # View menu
        view_menu = menubar.addMenu("&View")

        # Show Command action
        self.show_command_action = view_menu.addAction("Show &Command")
        self.show_command_action.setCheckable(True)
        self.show_command_action.setChecked(self.settings.value("show_command", True, type=bool))
        self.show_command_action.triggered.connect(self._toggle_command_visibility)

        # Show Console action
        self.show_console_action = view_menu.addAction("Show C&onsole")
        self.show_console_action.setCheckable(True)
        self.show_console_action.setChecked(self.settings.value("show_console", True, type=bool))
        self.show_console_action.triggered.connect(self._toggle_console_visibility)

        view_menu.addSeparator()

        # Toggle Theme action
        toggle_theme_action = view_menu.addAction("Toggle &Theme")
        toggle_theme_action.triggered.connect(self._toggle_theme)

    def _toggle_command_visibility(self, from_button=False):
        """Toggle Command section visibility with collapse/expand"""
        # If called from button, toggle current state
        if from_button:
            current_visible = self.command_group.isVisible()
            is_visible = not current_visible
            # Update action to match
            self.show_command_action.setChecked(is_visible)
        else:
            # Called from menu action
            is_visible = self.show_command_action.isChecked()

        # Toggle visibility of content only (keep header visible)
        self.command_group.setVisible(is_visible)

        # Update button text
        self.command_collapse_button.setText("▼" if is_visible else "▶")

        # Save state
        self.settings.setValue("show_command", is_visible)

    def _toggle_console_visibility(self, from_button=False):
        """Toggle Console section visibility with collapse/expand"""
        # If called from button, toggle current state
        if from_button:
            current_visible = self.console_group.isVisible()
            is_visible = not current_visible
            # Update action to match
            self.show_console_action.setChecked(is_visible)
        else:
            # Called from menu action
            is_visible = self.show_console_action.isChecked()

        # Toggle visibility of content only (keep header visible)
        self.console_group.setVisible(is_visible)

        # Force splitter to recalculate sizes
        if not is_visible:
            # When collapsing, set console container to minimum size
            sizes = self.splitter.sizes()
            console_index = self.splitter.indexOf(self.console_container)
            if console_index >= 0:
                sizes[console_index] = 30  # Just enough for header
                self.splitter.setSizes(sizes)

        # Update button text
        self.console_collapse_button.setText("▼" if is_visible else "▶")

        # Save state
        self.settings.setValue("show_console", is_visible)

    def _create_ui(self):
        # Create menu bar
        self._create_menu_bar()

        central_widget = QWidget()
        self.setCentralWidget(central_widget)
        layout = QVBoxLayout(central_widget)

        # Command section with collapse button
        self.command_container = QWidget()
        command_container_layout = QVBoxLayout(self.command_container)
        command_container_layout.setContentsMargins(0, 0, 0, 0)

        # Command header with collapse button
        command_header = QHBoxLayout()
        command_title = QLabel("<b>Command</b>")
        self.command_collapse_button = QPushButton("▼")
        self.command_collapse_button.setMaximumWidth(30)
        self.command_collapse_button.setToolTip("Collapse/Expand Command section")
        self.command_collapse_button.clicked.connect(lambda: self._toggle_command_visibility(from_button=True))
        command_header.addWidget(command_title)
        command_header.addStretch()
        command_header.addWidget(self.command_collapse_button)
        command_container_layout.addLayout(command_header)

        self.command_group = QGroupBox()
        command_layout = QVBoxLayout(self.command_group)

        # Working directory label
        formatted_path = self._format_windows_path(self.project_directory)
        working_dir_label = QLabel(f"Working directory: {formatted_path}")
        command_layout.addWidget(working_dir_label)

        # Command templates row
        templates_layout = QHBoxLayout()
        templates_label = QLabel("Templates:")
        self.templates_combo = QComboBox()
        self.templates_combo.addItem("-- Select template --")
        self._populate_templates_combo()
        self.templates_combo.currentIndexChanged.connect(self._on_template_selected)

        save_template_button = QPushButton("💾")
        save_template_button.setMaximumWidth(35)
        save_template_button.setToolTip("Save current command as template")
        save_template_button.clicked.connect(self._save_template)

        templates_layout.addWidget(templates_label)
        templates_layout.addWidget(self.templates_combo, stretch=1)
        templates_layout.addWidget(save_template_button)
        command_layout.addLayout(templates_layout)

        # Command input row
        command_input_layout = QHBoxLayout()
        self.command_entry = DragDropLineEdit()
        self.command_entry.setText(self.config["run_command"])
        self.command_entry.setPlaceholderText("Enter command or drag & drop files here...")
        self.command_entry.returnPressed.connect(self._run_command)
        self.command_entry.textChanged.connect(self._update_config)
        self.run_button = QPushButton("&Run (Ctrl+R / F5)")
        self.run_button.clicked.connect(self._run_command)

        command_input_layout.addWidget(self.command_entry)
        command_input_layout.addWidget(self.run_button)
        command_layout.addLayout(command_input_layout)

        # Auto-execute and save config row
        auto_layout = QHBoxLayout()
        self.auto_check = QCheckBox("Execute automatically")
        self.auto_check.setChecked(self.config.get("execute_automatically", False))
        self.auto_check.stateChanged.connect(self._update_config)

        # Theme toggle button
        self.theme_button = QPushButton("🌙 Dark (Ctrl+T)" if self.is_dark_theme else "☀️ Light (Ctrl+T)")
        self.theme_button.setMaximumWidth(130)
        self.theme_button.clicked.connect(self._toggle_theme)

        save_button = QPushButton("&Save Config (Ctrl+S)")
        save_button.clicked.connect(self._save_config)

        auto_layout.addWidget(self.auto_check)
        auto_layout.addStretch()
        auto_layout.addWidget(self.theme_button)
        auto_layout.addWidget(save_button)
        command_layout.addLayout(auto_layout)

        command_container_layout.addWidget(self.command_group)
        layout.addWidget(self.command_container)

        # Create a splitter for resizable sections
        self.splitter = QSplitter(Qt.Vertical)

        # Console section with collapse button
        self.console_container = QWidget()
        console_container_layout = QVBoxLayout(self.console_container)
        console_container_layout.setContentsMargins(0, 0, 0, 0)

        # Console header with collapse button
        console_header = QHBoxLayout()
        console_title = QLabel("<b>Console</b>")
        self.console_collapse_button = QPushButton("▼")
        self.console_collapse_button.setMaximumWidth(30)
        self.console_collapse_button.setToolTip("Collapse/Expand Console section")
        self.console_collapse_button.clicked.connect(lambda: self._toggle_console_visibility(from_button=True))
        console_header.addWidget(console_title)
        console_header.addStretch()
        console_header.addWidget(self.console_collapse_button)
        console_container_layout.addLayout(console_header)

        self.console_group = QGroupBox()
        console_layout = QVBoxLayout(self.console_group)
        self.console_group.setMinimumHeight(80)

        # Search box
        search_layout = QHBoxLayout()
        search_label = QLabel("🔍")
        self.search_entry = QLineEdit()
        self.search_entry.setPlaceholderText("Search in logs...")
        self.search_entry.textChanged.connect(self._search_logs)
        self.search_entry.returnPressed.connect(self._search_next)

        search_prev_button = QPushButton("↑")
        search_prev_button.setMaximumWidth(30)
        search_prev_button.clicked.connect(self._search_prev)

        search_next_button = QPushButton("↓")
        search_next_button.setMaximumWidth(30)
        search_next_button.clicked.connect(self._search_next)

        self.search_result_label = QLabel("")
        self.search_result_label.setStyleSheet("color: #95a5a6; font-size: 9pt;")

        search_layout.addWidget(search_label)
        search_layout.addWidget(self.search_entry, stretch=1)
        search_layout.addWidget(search_prev_button)
        search_layout.addWidget(search_next_button)
        search_layout.addWidget(self.search_result_label)
        console_layout.addLayout(search_layout)

        # Filter and options row
        filter_layout = QHBoxLayout()

        # Log level filter
        filter_label = QLabel("Filter:")
        self.log_level_filter = QComboBox()
        self.log_level_filter.addItems(["All", "Error", "Warning", "Success", "Info"])
        self.log_level_filter.setMaximumWidth(100)
        self.log_level_filter.currentTextChanged.connect(self._apply_log_filter)

        # Line numbers toggle
        self.show_line_numbers_check = QCheckBox("Line #")
        self.show_line_numbers_check.setChecked(self.settings.value("show_line_numbers", False, type=bool))
        self.show_line_numbers_check.stateChanged.connect(self._toggle_line_numbers)

        filter_layout.addWidget(filter_label)
        filter_layout.addWidget(self.log_level_filter)
        filter_layout.addWidget(self.show_line_numbers_check)
        filter_layout.addStretch()
        console_layout.addLayout(filter_layout)

        # Log text area with syntax highlighting
        self.log_text = QTextEdit()
        self.log_text.setReadOnly(True)
        self.log_text.setAcceptRichText(True)
        font = QFont(QFontDatabase.systemFont(QFontDatabase.FixedFont))
        # Restore saved font size or use default (9pt)
        saved_font_size = self.settings.value("console_font_size", 9, type=int)
        font.setPointSize(saved_font_size)
        self.log_text.setFont(font)
        console_layout.addWidget(self.log_text)

        # Console buttons
        button_layout = QHBoxLayout()

        # Copy button
        copy_button = QPushButton("📋 Copy")
        copy_button.setMaximumWidth(80)
        copy_button.clicked.connect(self._copy_logs)
        button_layout.addWidget(copy_button)

        # Export button
        export_button = QPushButton("💾 Export")
        export_button.setMaximumWidth(80)
        export_button.clicked.connect(self._export_logs)
        button_layout.addWidget(export_button)

        button_layout.addStretch()

        # Clear button
        self.clear_button = QPushButton("&Clear (Ctrl+L)")
        self.clear_button.clicked.connect(self.clear_logs)
        button_layout.addWidget(self.clear_button)

        console_layout.addLayout(button_layout)

        console_container_layout.addWidget(self.console_group)
        self.splitter.addWidget(self.console_container)

        # Feedback Content section (MAIN FOCUS - displays MCP prompt/summary with Markdown)
        feedback_content_group = QGroupBox("Feedback Content")
        feedback_content_layout = QVBoxLayout(feedback_content_group)
        feedback_content_group.setMinimumHeight(150)

        self.prompt_display = QTextBrowser()
        self.prompt_display.setReadOnly(True)
        self.prompt_display.setOpenExternalLinks(True)
        # Ensure content is scrollable and not clipped
        self.prompt_display.setVerticalScrollBarPolicy(Qt.ScrollBarAsNeeded)
        self.prompt_display.setHorizontalScrollBarPolicy(Qt.ScrollBarAsNeeded)
        # Set minimum height to ensure content is visible
        self.prompt_display.setMinimumHeight(200)
        # Theme will be applied in _apply_theme()
        feedback_content_layout.addWidget(self.prompt_display)

        self.splitter.addWidget(feedback_content_group)

        # User Feedback Input section (resizable)
        user_feedback_group = QGroupBox("Your Feedback")
        user_feedback_layout = QVBoxLayout(user_feedback_group)
        user_feedback_group.setMinimumHeight(80)

        # Templates and History row
        templates_history_layout = QHBoxLayout()

        # Feedback templates
        templates_label = QLabel("Templates:")
        self.feedback_templates_combo = QComboBox()
        self.feedback_templates_combo.addItem("-- Insert template --")
        self._populate_feedback_templates_combo()
        self.feedback_templates_combo.currentIndexChanged.connect(self._on_feedback_template_selected)

        save_feedback_template_button = QPushButton("💾")
        save_feedback_template_button.setMaximumWidth(30)
        save_feedback_template_button.setToolTip("Save current feedback as template")
        save_feedback_template_button.clicked.connect(self._save_feedback_template)

        delete_feedback_template_button = QPushButton("🗑️")
        delete_feedback_template_button.setMaximumWidth(30)
        delete_feedback_template_button.setToolTip("Delete selected template")
        delete_feedback_template_button.clicked.connect(self._delete_feedback_template)

        templates_history_layout.addWidget(templates_label)
        templates_history_layout.addWidget(self.feedback_templates_combo, stretch=1)
        templates_history_layout.addWidget(save_feedback_template_button)
        templates_history_layout.addWidget(delete_feedback_template_button)

        # History dropdown
        history_label = QLabel("Recent:")
        self.history_combo = QComboBox()
        self.history_combo.addItem("-- Select from history --")
        self._populate_history_combo()
        self.history_combo.currentIndexChanged.connect(self._on_history_selected)
        templates_history_layout.addWidget(history_label)
        templates_history_layout.addWidget(self.history_combo, stretch=1)

        user_feedback_layout.addLayout(templates_history_layout)

        self.feedback_text = FeedbackTextEdit()
        self.feedback_text.setMinimumHeight(40)
        self.feedback_text.setPlaceholderText("Enter your feedback here...")
        submit_button = QPushButton("Submit &Feedback (Ctrl+Enter)")
        submit_button.clicked.connect(self._submit_feedback)

        user_feedback_layout.addWidget(self.feedback_text)
        user_feedback_layout.addWidget(submit_button)

        self.splitter.addWidget(user_feedback_group)

        # Restore splitter sizes or set defaults
        saved_sizes = self.settings.value("splitter_sizes")
        if saved_sizes:
            self.splitter.setSizes(saved_sizes)
        else:
            # Default sizes: Console=2, Feedback Content=4, User Feedback=2
            self.splitter.setSizes([200, 400, 200])

        layout.addWidget(self.splitter)

        # Apply initial theme
        self._apply_theme()

        # Apply initial visibility state
        show_command = self.settings.value("show_command", True, type=bool)
        show_console = self.settings.value("show_console", True, type=bool)
        self.command_group.setVisible(show_command)
        self.console_group.setVisible(show_console)
        self.command_collapse_button.setText("▼" if show_command else "▶")
        self.console_collapse_button.setText("▼" if show_console else "▶")

        # If console is collapsed on init, adjust splitter size
        if not show_console:
            sizes = self.splitter.sizes()
            console_index = self.splitter.indexOf(self.console_container)
            if console_index >= 0:
                sizes[console_index] = 30  # Just enough for header
                self.splitter.setSizes(sizes)

        # Setup keyboard shortcuts
        self._setup_shortcuts()

    def _setup_shortcuts(self):
        """Setup keyboard shortcuts"""
        # Ctrl+R: Run command
        run_shortcut = QShortcut(QKeySequence("Ctrl+R"), self)
        run_shortcut.activated.connect(self._run_command)

        # Ctrl+L: Clear logs
        clear_shortcut = QShortcut(QKeySequence("Ctrl+L"), self)
        clear_shortcut.activated.connect(self.clear_logs)

        # Ctrl+S: Save configuration
        save_shortcut = QShortcut(QKeySequence("Ctrl+S"), self)
        save_shortcut.activated.connect(self._save_config)

        # Ctrl+T: Toggle theme
        theme_shortcut = QShortcut(QKeySequence("Ctrl+T"), self)
        theme_shortcut.activated.connect(self._toggle_theme)

        # Ctrl+Plus: Increase font size
        increase_font_shortcut = QShortcut(QKeySequence("Ctrl++"), self)
        increase_font_shortcut.activated.connect(self._increase_font_size)

        # Ctrl+Minus: Decrease font size
        decrease_font_shortcut = QShortcut(QKeySequence("Ctrl+-"), self)
        decrease_font_shortcut.activated.connect(self._decrease_font_size)

        # Ctrl+0: Reset font size
        reset_font_shortcut = QShortcut(QKeySequence("Ctrl+0"), self)
        reset_font_shortcut.activated.connect(self._reset_font_size)

        # Ctrl+Enter: Submit feedback (already handled in FeedbackTextEdit)
        # F5: Run command (alternative)
        f5_shortcut = QShortcut(QKeySequence("F5"), self)
        f5_shortcut.activated.connect(self._run_command)

    def _toggle_theme(self):
        """Toggle between dark and light theme"""
        self.is_dark_theme = not self.is_dark_theme
        self.settings.setValue("dark_theme", self.is_dark_theme)
        self.theme_button.setText("🌙 Dark" if self.is_dark_theme else "☀️ Light")
        self._apply_theme()

    def _increase_font_size(self):
        """Increase font size for console"""
        font = self.log_text.font()
        current_size = font.pointSize()
        if current_size < 20:  # Max size
            font.setPointSize(current_size + 1)
            self.log_text.setFont(font)
            self.settings.setValue("console_font_size", current_size + 1)

    def _decrease_font_size(self):
        """Decrease font size for console"""
        font = self.log_text.font()
        current_size = font.pointSize()
        if current_size > 6:  # Min size
            font.setPointSize(current_size - 1)
            self.log_text.setFont(font)
            self.settings.setValue("console_font_size", current_size - 1)

    def _reset_font_size(self):
        """Reset font size to default (9pt)"""
        font = self.log_text.font()
        font.setPointSize(9)
        self.log_text.setFont(font)
        self.settings.setValue("console_font_size", 9)

    def _apply_theme(self):
        """Apply the current theme to the application"""
        app = QApplication.instance()
        if self.is_dark_theme:
            app.setPalette(get_dark_mode_palette(app))
            # Dark theme for prompt display
            self.prompt_display.setStyleSheet("""
                QTextBrowser {
                    background-color: #2c3e50;
                    color: #ecf0f1;
                    border: 1px solid #34495e;
                    border-radius: 5px;
                    padding: 10px;
                }
            """)
        else:
            app.setPalette(get_light_mode_palette(app))
            # Light theme for prompt display
            self.prompt_display.setStyleSheet("""
                QTextBrowser {
                    background-color: #f8f9fa;
                    color: #212529;
                    border: 1px solid #dee2e6;
                    border-radius: 5px;
                    padding: 10px;
                }
            """)
        # Re-render markdown with appropriate colors
        html_content = markdown_to_html(self.prompt, self.is_dark_theme)
        # Debug: Print first 500 chars of HTML to help diagnose rendering issues
        print(f"DEBUG: HTML content (first 500 chars):\n{html_content[:500]}\n")
        self.prompt_display.setHtml(html_content)

    def _update_config(self):
        self.config = {
            "run_command": self.command_entry.text(),
            "execute_automatically": self.auto_check.isChecked(),
            "command_templates": self.config.get("command_templates", [])
        }

    def _populate_templates_combo(self):
        """Populate templates combobox"""
        self.templates_combo.clear()
        self.templates_combo.addItem("-- Select template --")

        templates = self.config.get("command_templates", [])
        for template in templates:
            self.templates_combo.addItem(template)

    def _on_template_selected(self, index: int):
        """Handle template selection"""
        if index > 0:  # Skip placeholder
            template = self.templates_combo.currentText()
            self.command_entry.setText(template)
            # Reset to placeholder
            self.templates_combo.setCurrentIndex(0)

    def _save_template(self):
        """Save current command as template"""
        command = self.command_entry.text().strip()
        if not command:
            return

        templates = self.config.get("command_templates", [])
        if command not in templates:
            templates.append(command)
            self.config["command_templates"] = templates
            self._save_config()
            self._populate_templates_combo()
            # Show feedback
            original_text = self.run_button.text()
            self.run_button.setText("✓ Saved!")
            QTimer.singleShot(1500, lambda: self.run_button.setText(original_text))

    def _populate_history_combo(self):
        """Populate history combobox with recent feedback"""
        self.history_combo.clear()
        self.history_combo.addItem("-- Select from history --")

        # Add recent history items (newest first)
        for entry in reversed(self.history[-10:]):  # Show last 10
            timestamp = entry.get("timestamp", "")
            feedback = entry.get("feedback", "")
            # Create display text (first 50 chars of feedback)
            display_text = feedback[:50] + "..." if len(feedback) > 50 else feedback
            if timestamp:
                try:
                    import datetime
                    dt = datetime.datetime.fromisoformat(timestamp)
                    time_str = dt.strftime("%m/%d %H:%M")
                    display_text = f"[{time_str}] {display_text}"
                except:
                    pass
            self.history_combo.addItem(display_text, entry)

    def _on_history_selected(self, index: int):
        """Handle history selection"""
        if index > 0:  # Skip the placeholder item
            entry = self.history_combo.itemData(index)
            if entry:
                self.feedback_text.setPlainText(entry.get("feedback", ""))
            # Reset to placeholder
            self.history_combo.setCurrentIndex(0)

    def _populate_feedback_templates_combo(self):
        """Populate feedback templates combobox"""
        self.feedback_templates_combo.clear()
        self.feedback_templates_combo.addItem("-- Insert template --")

        templates = self.config.get("feedback_templates", [])
        for template in templates:
            # Show first 50 chars in dropdown
            display_text = template[:50] + "..." if len(template) > 50 else template
            self.feedback_templates_combo.addItem(display_text, template)

    def _on_feedback_template_selected(self, index: int):
        """Handle feedback template selection - INSERT mode"""
        if index > 0:  # Skip placeholder
            template = self.feedback_templates_combo.itemData(index)
            if template:
                # Get current cursor position
                cursor = self.feedback_text.textCursor()
                # Insert template at cursor position
                cursor.insertText(template)
            # Reset to placeholder
            self.feedback_templates_combo.setCurrentIndex(0)

    def _save_feedback_template(self):
        """Save current feedback as template"""
        from PySide6.QtWidgets import QInputDialog

        feedback = self.feedback_text.toPlainText().strip()
        if not feedback:
            return

        # Ask for template name/description (optional)
        text, ok = QInputDialog.getText(
            self,
            "Save Feedback Template",
            "Template will be saved as:\n" + (feedback[:100] + "..." if len(feedback) > 100 else feedback) + "\n\nPress OK to save:",
        )

        if ok:
            templates = self.config.get("feedback_templates", [])
            if feedback not in templates:
                templates.append(feedback)
                self.config["feedback_templates"] = templates
                self._save_config()
                self._populate_feedback_templates_combo()
                # Show feedback - use submit button for visual feedback
                original_text = self.feedback_text.placeholderText()
                self.feedback_text.setPlaceholderText("✓ Template saved!")
                QTimer.singleShot(1500, lambda: self.feedback_text.setPlaceholderText(original_text))

    def _delete_feedback_template(self):
        """Delete selected feedback template"""
        from PySide6.QtWidgets import QMessageBox

        index = self.feedback_templates_combo.currentIndex()
        if index <= 0:  # Skip placeholder
            return

        template = self.feedback_templates_combo.itemData(index)
        if not template:
            return

        # Confirm deletion
        reply = QMessageBox.question(
            self,
            "Delete Template",
            f"Delete this template?\n\n{template[:100] + '...' if len(template) > 100 else template}",
            QMessageBox.Yes | QMessageBox.No,
            QMessageBox.No
        )

        if reply == QMessageBox.Yes:
            templates = self.config.get("feedback_templates", [])
            if template in templates:
                templates.remove(template)
                self.config["feedback_templates"] = templates
                self._save_config()
                self._populate_feedback_templates_combo()

    def _append_log(self, text: str):
        self.log_buffer.append(text)

        # Apply syntax highlighting to each line and store metadata
        lines = text.rstrip().split('\n')
        for line in lines:
            level = detect_log_level(line)
            line_number = len(self.log_entries) + 1
            self.log_entries.append((line, level, line_number))

            # Apply filter
            current_filter = self.log_level_filter.currentText()
            if current_filter != "All" and level != current_filter and level != "Other":
                continue  # Skip lines that don't match filter

            # Add line number if enabled
            show_line_numbers = self.show_line_numbers_check.isChecked()
            if show_line_numbers:
                line_prefix = f'<span style="color: #95a5a6;">{line_number:4d} | </span>'
            else:
                line_prefix = ''

            highlighted = highlight_log_line(line)
            self.log_text.append(line_prefix + highlighted)

        cursor = self.log_text.textCursor()
        cursor.movePosition(QTextCursor.End)
        self.log_text.setTextCursor(cursor)

    def _apply_log_filter(self):
        """Re-render logs with current filter"""
        self.log_text.clear()
        current_filter = self.log_level_filter.currentText()
        show_line_numbers = self.show_line_numbers_check.isChecked()

        for line, level, line_number in self.log_entries:
            # Apply filter
            if current_filter != "All" and level != current_filter and level != "Other":
                continue

            # Add line number if enabled
            if show_line_numbers:
                line_prefix = f'<span style="color: #95a5a6;">{line_number:4d} | </span>'
            else:
                line_prefix = ''

            highlighted = highlight_log_line(line)
            self.log_text.append(line_prefix + highlighted)

    def _toggle_line_numbers(self):
        """Toggle line numbers display"""
        self.settings.setValue("show_line_numbers", self.show_line_numbers_check.isChecked())
        self._apply_log_filter()  # Re-render with/without line numbers

    def _check_process_status(self):
        if self.process and self.process.poll() is not None:
            # Process has terminated
            exit_code = self.process.poll()
            self._append_log(f"\nProcess exited with code {exit_code}\n")
            self.run_button.setText("&Run")
            self.process = None
            self.activateWindow()
            self.feedback_text.setFocus()

    def _run_command(self):
        if self.process:
            kill_tree(self.process)
            self.process = None
            self.run_button.setText("&Run")
            return

        # Clear the log buffer but keep UI logs visible
        self.log_buffer = []

        command = self.command_entry.text()
        if not command:
            self._append_log("Please enter a command to run\n")
            return

        self._append_log(f"$ {command}\n")
        self.run_button.setText("Sto&p")

        try:
            self.process = subprocess.Popen(
                command,
                shell=True,
                cwd=self.project_directory,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                env=get_user_environment(),
                text=True,
                bufsize=1,
                encoding="utf-8",
                errors="ignore",
                close_fds=True,
            )

            def read_output(pipe):
                for line in iter(pipe.readline, ""):
                    self.log_signals.append_log.emit(line)

            threading.Thread(
                target=read_output,
                args=(self.process.stdout,),
                daemon=True
            ).start()

            threading.Thread(
                target=read_output,
                args=(self.process.stderr,),
                daemon=True
            ).start()

            # Start process status checking
            self.status_timer = QTimer()
            self.status_timer.timeout.connect(self._check_process_status)
            self.status_timer.start(100)  # Check every 100ms

        except Exception as e:
            self._append_log(f"Error running command: {str(e)}\n")
            self.run_button.setText("&Run")

    def _submit_feedback(self):
        feedback_text = self.feedback_text.toPlainText().strip()

        # Save to history if not empty
        if feedback_text:
            self._add_to_history(feedback_text)

        self.feedback_result = FeedbackResult(
            logs="".join(self.log_buffer),
            user_feedback=feedback_text,
        )
        self.close()

    def _search_logs(self):
        """Search for text in logs"""
        search_text = self.search_entry.text()
        if not search_text:
            self.search_result_label.setText("")
            return

        # Move cursor to start for new search
        cursor = self.log_text.textCursor()
        cursor.movePosition(QTextCursor.Start)
        self.log_text.setTextCursor(cursor)

        # Find first occurrence
        self._search_next()

    def _search_next(self):
        """Find next occurrence"""
        search_text = self.search_entry.text()
        if not search_text:
            return

        found = self.log_text.find(search_text)
        if found:
            self.search_result_label.setText("✓")
        else:
            # Wrap around to start
            cursor = self.log_text.textCursor()
            cursor.movePosition(QTextCursor.Start)
            self.log_text.setTextCursor(cursor)
            found = self.log_text.find(search_text)
            if found:
                self.search_result_label.setText("✓ (wrapped)")
            else:
                self.search_result_label.setText("Not found")

    def _search_prev(self):
        """Find previous occurrence"""
        from PySide6.QtGui import QTextDocument

        search_text = self.search_entry.text()
        if not search_text:
            return

        found = self.log_text.find(search_text, QTextDocument.FindBackward)
        if found:
            self.search_result_label.setText("✓")
        else:
            # Wrap around to end
            cursor = self.log_text.textCursor()
            cursor.movePosition(QTextCursor.End)
            self.log_text.setTextCursor(cursor)
            found = self.log_text.find(search_text, QTextDocument.FindBackward)
            if found:
                self.search_result_label.setText("✓ (wrapped)")
            else:
                self.search_result_label.setText("Not found")

    def _copy_logs(self):
        """Copy logs to clipboard"""
        logs = "".join(self.log_buffer)
        clipboard = QApplication.clipboard()
        clipboard.setText(logs)
        # Show temporary feedback
        original_text = self.clear_button.text()
        self.clear_button.setText("✓ Copied!")
        QTimer.singleShot(1500, lambda: self.clear_button.setText(original_text))

    def _export_logs(self):
        """Export logs to file"""
        import datetime
        default_filename = f"feedback-logs-{datetime.datetime.now().strftime('%Y%m%d-%H%M%S')}.txt"
        filename, _ = QFileDialog.getSaveFileName(
            self,
            "Export Logs",
            os.path.join(self.project_directory, default_filename),
            "Text Files (*.txt);;All Files (*)"
        )
        if filename:
            try:
                with open(filename, "w") as f:
                    f.write("".join(self.log_buffer))
                # Show temporary feedback
                original_text = self.clear_button.text()
                self.clear_button.setText("✓ Exported!")
                QTimer.singleShot(1500, lambda: self.clear_button.setText(original_text))
            except Exception as e:
                self._append_log(f"Failed to export logs: {e}\n")

    def clear_logs(self):
        self.log_buffer = []
        self.log_text.clear()

    def closeEvent(self, event):
        # Save window geometry, state, and splitter sizes
        settings = QSettings("UserFeedback", "MainWindow")
        settings.setValue("geometry", self.saveGeometry())
        settings.setValue("windowState", self.saveState())
        settings.setValue("splitter_sizes", self.splitter.sizes())

        if self.process:
            kill_tree(self.process)
        super().closeEvent(event)

    def run(self) -> FeedbackResult:
        self.show()
        QApplication.instance().exec()

        if self.process:
            kill_tree(self.process)

        if not self.feedback_result:
            return FeedbackResult(logs="".join(self.log_buffer), user_feedback="")

        return self.feedback_result

def feedback_ui(project_directory: str, prompt: str, output_file: Optional[str] = None) -> Optional[FeedbackResult]:
    app = QApplication.instance() or QApplication()
    app.setPalette(get_dark_mode_palette(app))
    app.setStyle("Fusion")
    ui = FeedbackUI(project_directory, prompt)
    result = ui.run()

    if output_file and result:
        # Ensure the directory exists
        os.makedirs(os.path.dirname(output_file) if os.path.dirname(output_file) else ".", exist_ok=True)
        # Save the result to the output file
        with open(output_file, "w") as f:
            json.dump(result, f)
        return None

    return result

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Run the feedback UI")
    parser.add_argument("--project-directory", default=os.getcwd(), help="The project directory to run the command in")
    parser.add_argument("--prompt", default="I implemented the changes you requested.", help="The prompt to show to the user")
    parser.add_argument("--output-file", help="Path to save the feedback result as JSON")
    args = parser.parse_args()

    result = feedback_ui(args.project_directory, args.prompt, args.output_file)
    if result:
        print(f"\nLogs collected: \n{result['logs']}")
        print(f"\nFeedback received:\n{result['user_feedback']}")
    sys.exit(0)
