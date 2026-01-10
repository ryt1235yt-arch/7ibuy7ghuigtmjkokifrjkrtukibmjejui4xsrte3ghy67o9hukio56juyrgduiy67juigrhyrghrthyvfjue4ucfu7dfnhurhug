import os
import time
import hashlib
import threading
import subprocess
from urllib.request import Request, urlopen
from urllib.error import URLError
from PySide6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout, QFrame,
    QLabel, QPushButton, QCheckBox, QTextEdit, QLineEdit, QProgressBar, QFileDialog
)
from PySide6.QtCore import Signal, QObject
from PySide6.QtGui import QFont
import sys

# ==========================
# НАСТРОЙКИ
# ==========================
APP_NAME = "APSLauncher"
PUBLISHER = "APS265Team"

DOWNLOAD_URL = "https://github.com/ryt1235yt-arch/7ibuy7ghuigtmjkokifrjkrtukibmjejui4xsrte3ghy67o9hukio56juyrgduiy67juigrhyrghrthyvfjue4ucfu7dfnhurhug/releases/download/progs/APSLauncher.exe"
EXPECTED_SHA256 = ""

INSTALL_ROOT = os.path.join(os.environ.get("APPDATA", os.path.expanduser("~")), APP_NAME)
INSTALL_EXE = os.path.join(INSTALL_ROOT, f"{APP_NAME}.exe")
TEMP_EXE = os.path.join(INSTALL_ROOT, "download.tmp")

LICENSE_TEXT = (
    "ПОЛЬЗОВАТЕЛЬСКОЕ СОГЛАШЕНИЕ (EULA)\n\n"
    "⚠️ Важно / Предупреждение о безопасности\n\n"
    "🛡️ Установщик скачивает файлы с серверов проекта.\n\n"
    "💥 В случае атак на сервер, взлома или подмены файлов третьими лицами и замены их на вредоносные, "
    "авторы не несут ответственности за возможный ущерб.\n\n"
    "👤 Скачивая и используя программу, вы берёте на себя полную ответственность "
    "за безопасность своей системы и последствия использования.\n\n"
    "🔒 Рекомендуется использовать актуальный антивирус и скачивать программу только из официальных источников.\n\n"
    "Продолжая установку, вы подтверждаете, что прочитали и принимаете условия."
)

# ==========================
# УТИЛИТЫ
# ==========================
def ensure_dir(path: str):
    os.makedirs(path, exist_ok=True)

def sha256_file(path: str) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()

def human_bytes(n: float) -> str:
    units = ["B", "KB", "MB", "GB", "TB"]
    n = float(n)
    for u in units:
        if n < 1024.0 or u == units[-1]:
            return f"{n:.2f} {u}" if u != "B" else f"{int(n)} {u}"
        n /= 1024.0
    return f"{n:.2f} TB"

import subprocess
import os
import winreg

def get_desktop_path():
    """
    Получает реальный путь к рабочему столу из реестра Windows
    """
    try:
        # Пытаемся получить путь из реестра
        key = winreg.OpenKey(
            winreg.HKEY_CURRENT_USER,
            r'Software\Microsoft\Windows\CurrentVersion\Explorer\Shell Folders'
        )
        desktop_path = winreg.QueryValueEx(key, 'Desktop')[0]
        winreg.CloseKey(key)
        return desktop_path
    except Exception as e:
        print(f"[WARNING] Не удалось получить путь из реестра: {e}")
        
        # Запасные варианты
        possible_paths = [
            os.path.join(os.environ.get('USERPROFILE', ''), 'Desktop'),
            os.path.join(os.environ.get('USERPROFILE', ''), 'Рабочий стол'),
            os.path.join(os.environ.get('OneDrive', ''), 'Desktop'),
            os.path.join(os.environ.get('OneDrive', ''), 'Рабочий стол'),
        ]
        
        for path in possible_paths:
            if os.path.exists(path):
                return path
        
        return None


def create_desktop_shortcut(target_path, shortcut_name, icon_path=None):
    """
    Создает ярлык на рабочем столе
    """
    # Получаем правильный путь к рабочему столу
    desktop = get_desktop_path()
    
    if not desktop:
        print("[ERROR] Не удалось найти рабочий стол")
        print("Возможные причины:")
        print("- Рабочий стол синхронизируется с OneDrive")
        print("- Нестандартное расположение папки рабочего стола")
        return False
    
    print(f"[INFO] Рабочий стол найден: {desktop}")
    
    shortcut_path = os.path.join(desktop, f"{shortcut_name}.lnk")
    
    # Проверяем существование целевого файла
    if not os.path.exists(target_path):
        print(f"[ERROR] Целевой файл не найден: {target_path}")
        return False
    
    # Формируем PowerShell скрипт
    ps_script = f"""
$WshShell = New-Object -ComObject WScript.Shell
$Shortcut = $WshShell.CreateShortcut('{shortcut_path}')
$Shortcut.TargetPath = '{target_path}'
$Shortcut.WorkingDirectory = '{os.path.dirname(target_path)}'
"""
    
    if icon_path and os.path.exists(icon_path):
        ps_script += f"$Shortcut.IconLocation = '{icon_path}'\n"
    
    ps_script += "$Shortcut.Save()"
    
    try:
        result = subprocess.run(
            ["powershell", "-NoProfile", "-ExecutionPolicy", "Bypass", "-Command", ps_script],
            capture_output=True,
            text=True,
            encoding='cp866',  # Для русской Windows часто нужна эта кодировка
            errors='replace'
        )
        
        if result.returncode != 0:
            print(f"[ERROR] PowerShell ошибка (code {result.returncode})")
            print(f"STDERR: {result.stderr}")
            print(f"STDOUT: {result.stdout}")
            return False
        
        if os.path.exists(shortcut_path):
            print(f"[OK] Ярлык создан: {shortcut_path}")
            return True
        else:
            print("[ERROR] Ярлык не был создан (неизвестная причина)")
            return False
        
    except Exception as e:
        print(f"[ERROR] Исключение: {e}")
        return False
# ==========================
# СИГНАЛЫ
# ==========================
class WorkerSignals(QObject):
    status_changed = Signal(str)
    progress_changed = Signal(int)
    amount_changed = Signal(str)
    speed_changed = Signal(str)
    finished = Signal()
    error = Signal(str)

# ==========================
# GUI
# ==========================
class Wizard(QMainWindow):
    def __init__(self):
        super().__init__()
        
        self.setWindowTitle(f"{APP_NAME} Installer")
        self.setGeometry(100, 100, 900, 700)
        self.setMinimumSize(900, 700)
        self.setMaximumSize(1100, 800)
        
        # Цвета - темная тема с фиолетовым
        self.bg_dark = "#0a0a0f"
        self.bg_secondary = "#1a1a2e"
        self.accent_purple = "#7c3aed"
        self.accent_purple_light = "#a78bfa"
        self.accent_purple_dark = "#5b21b6"
        self.text_light = "#e9d5ff"
        self.text_muted = "#c084fc"
        self.border_color = "#5b21b6"
        
        # Стиль
        self.setStyleSheet(f"""
            QMainWindow {{ 
                background-color: {self.bg_dark}; 
            }}
            QLabel {{ 
                color: {self.text_light}; 
                background-color: transparent;
            }}
            QPushButton {{ 
                color: {self.bg_dark}; 
                background-color: {self.accent_purple};
                border: 2px solid {self.accent_purple};
                padding: 8px 20px;
                border-radius: 6px;
                font-weight: bold;
                font-size: 11px;
            }}
            QPushButton:hover {{ 
                background-color: {self.accent_purple_light};
                border: 2px solid {self.accent_purple_light};
            }}
            QPushButton:pressed {{ 
                background-color: {self.accent_purple_dark};
                border: 2px solid {self.accent_purple_dark};
            }}
            QPushButton:disabled {{
                background-color: #333333;
                color: #666666;
                border: 2px solid #444444;
            }}
            QCheckBox {{ 
                color: {self.text_light};
                background-color: transparent;
                spacing: 8px;
            }}
            QCheckBox::indicator {{
                width: 18px;
                height: 18px;
                border: 2px solid {self.accent_purple};
                border-radius: 4px;
                background-color: {self.bg_secondary};
            }}
            QCheckBox::indicator:checked {{
                background-color: {self.accent_purple};
            }}
            QLineEdit, QTextEdit {{ 
                background-color: {self.bg_secondary};
                color: {self.text_light};
                border: 2px solid {self.border_color};
                padding: 8px;
                border-radius: 6px;
                selection-background-color: {self.accent_purple};
            }}
            QLineEdit:focus, QTextEdit:focus {{
                border: 2px solid {self.accent_purple_light};
            }}
            QProgressBar {{
                background-color: {self.bg_secondary};
                border: 2px solid {self.border_color};
                border-radius: 6px;
                height: 12px;
            }}
            QProgressBar::chunk {{
                background-color: {self.accent_purple};
                border-radius: 4px;
            }}
        """)
        
        # Переменные состояния
        self.agreed = False
        self.opt_shortcut = True
        self.opt_run_after = True
        self.install_root = INSTALL_ROOT
        self.current_page = None
        
        # Сигналы воркера
        self.worker_signals = WorkerSignals()
        self.worker_signals.status_changed.connect(self._on_status_changed)
        self.worker_signals.progress_changed.connect(self._on_progress_changed)
        self.worker_signals.amount_changed.connect(self._on_amount_changed)
        self.worker_signals.speed_changed.connect(self._on_speed_changed)
        self.worker_signals.finished.connect(self._on_install_finished)
        self.worker_signals.error.connect(self._on_install_error)
        
        # Построение интерфейса
        self._build_ui()
        self.show_page("welcome")
    
    def _build_ui(self):
        central = QWidget()
        self.setCentralWidget(central)
        
        main_layout = QVBoxLayout(central)
        main_layout.setContentsMargins(30, 30, 30, 30)
        main_layout.setSpacing(15)
        
        # Область страниц
        self.page_container = QFrame()
        self.page_container.setStyleSheet(f"""
            QFrame {{
                background-color: {self.bg_secondary};
                border: 2px solid {self.accent_purple};
                border-radius: 8px;
                padding: 20px;
            }}
        """)
        self.page_layout = QVBoxLayout(self.page_container)
        self.page_layout.setContentsMargins(0, 0, 0, 0)
        main_layout.addWidget(self.page_container, 1)
        
        # Прогресс
        self.progress_bar = QProgressBar()
        self.progress_bar.setMaximum(100)
        self.progress_bar.setStyleSheet(f"""
            QProgressBar {{
                background-color: {self.bg_secondary};
                border: 2px solid {self.border_color};
                border-radius: 6px;
                height: 16px;
            }}
            QProgressBar::chunk {{
                background-color: qlineargradient(
                    x1:0, y1:0, x2:1, y2:0,
                    stop:0 {self.accent_purple},
                    stop:1 {self.accent_purple_light}
                );
                border-radius: 4px;
            }}
        """)
        main_layout.addWidget(self.progress_bar)
        
        # Информация о загрузке
        info_layout = QHBoxLayout()
        self.label_amount = QLabel("")
        self.label_amount.setStyleSheet(f"color: {self.text_muted};")
        self.label_speed = QLabel("")
        self.label_speed.setStyleSheet(f"color: {self.text_muted};")
        info_layout.addWidget(self.label_amount)
        info_layout.addStretch()
        info_layout.addWidget(self.label_speed)
        main_layout.addLayout(info_layout)
        
        # Статус
        self.label_status = QLabel("")
        self.label_status.setStyleSheet(f"color: {self.accent_purple_light}; font-weight: bold;")
        main_layout.addWidget(self.label_status)
        
        # Кнопки
        buttons_layout = QHBoxLayout()
        self.btn_back = QPushButton("← Назад")
        self.btn_back.clicked.connect(self.on_back)
        self.btn_next = QPushButton("Далее →")
        self.btn_next.clicked.connect(self.on_next)
        self.btn_cancel = QPushButton("Отмена")
        self.btn_cancel.clicked.connect(self.close)
        
        buttons_layout.addWidget(self.btn_back)
        buttons_layout.addStretch()
        buttons_layout.addWidget(self.btn_cancel)
        buttons_layout.addWidget(self.btn_next)
        main_layout.addLayout(buttons_layout)
        
        # Страницы
        self.pages = {
            "welcome": self._page_welcome(),
            "license": self._page_license(),
            "options": self._page_options(),
            "download": self._page_download(),
            "finish": self._page_finish(),
        }
    
    def _page_welcome(self):
        frame = QFrame()
        frame.setStyleSheet("background-color: transparent;")
        layout = QVBoxLayout(frame)
        
        title = QLabel(f"✨ Добро пожаловать в {APP_NAME}")
        title.setFont(QFont("Segoe UI", 24, QFont.Bold))
        title.setStyleSheet(f"color: {self.accent_purple_light};")
        layout.addWidget(title)
        
        layout.addSpacing(20)
        
        text = QLabel(
            f"🎯 Издатель: {PUBLISHER}\n\n"
            f"📦 Этот мастер скачает и установит {APP_NAME} на ваш компьютер.\n\n"
            f"🚀 Нажмите «Далее», чтобы продолжить."
        )
        text.setFont(QFont("Segoe UI", 12))
        text.setWordWrap(True)
        text.setStyleSheet(f"color: {self.text_light}; line-height: 1.6;")
        layout.addWidget(text)
        layout.addStretch()
        
        return frame
    
    def _page_license(self):
        frame = QFrame()
        frame.setStyleSheet("background-color: transparent;")
        layout = QVBoxLayout(frame)
        
        title = QLabel("📜 Пользовательское соглашение")
        title.setFont(QFont("Segoe UI", 18, QFont.Bold))
        title.setStyleSheet(f"color: {self.accent_purple_light};")
        layout.addWidget(title)
        
        text_box = QTextEdit()
        text_box.setText(LICENSE_TEXT)
        text_box.setReadOnly(True)
        text_box.setStyleSheet(f"""
            QTextEdit {{
                background-color: {self.bg_dark};
                color: {self.text_light};
                border: 2px solid {self.accent_purple_dark};
                border-radius: 6px;
                padding: 12px;
            }}
        """)
        layout.addWidget(text_box)
        
        hint = QLabel("Чтобы продолжить, поставьте галочку ниже.")
        hint.setFont(QFont("Segoe UI", 10))
        hint.setStyleSheet(f"color: {self.text_muted};")
        layout.addWidget(hint)
        
        self.check_agree = QCheckBox("✅ Я прочитал(а) и принимаю условия")
        self.check_agree.setFont(QFont("Segoe UI", 11))
        self.check_agree.stateChanged.connect(self._sync_buttons)
        layout.addWidget(self.check_agree)
        
        return frame
    
    def _page_options(self):
        frame = QFrame()
        frame.setStyleSheet("background-color: transparent;")
        layout = QVBoxLayout(frame)
        
        title = QLabel("⚙️ Параметры установки")
        title.setFont(QFont("Segoe UI", 18, QFont.Bold))
        title.setStyleSheet(f"color: {self.accent_purple_light};")
        layout.addWidget(title)
        
        layout.addSpacing(15)
        
        label_path = QLabel("📁 Папка установки:")
        label_path.setFont(QFont("Segoe UI", 11, QFont.Bold))
        label_path.setStyleSheet(f"color: {self.text_light};")
        layout.addWidget(label_path)
        
        path_layout = QHBoxLayout()
        self.input_path = QLineEdit(self.install_root)
        self.input_path.setFont(QFont("Segoe UI", 10))
        path_layout.addWidget(self.input_path)
        
        btn_browse = QPushButton("📂 Обзор")
        btn_browse.clicked.connect(self._browse_folder)
        path_layout.addWidget(btn_browse)
        layout.addLayout(path_layout)
        
        layout.addSpacing(10)
        
        self.check_shortcut = QCheckBox("📌 Создать ярлык на рабочем столе")
        self.check_shortcut.setFont(QFont("Segoe UI", 11))
        self.check_shortcut.setChecked(True)
        layout.addWidget(self.check_shortcut)
        
        self.check_run = QCheckBox("🚀 Открыть программу после установки")
        self.check_run.setFont(QFont("Segoe UI", 11))
        self.check_run.setChecked(True)
        layout.addWidget(self.check_run)
        
        layout.addSpacing(30)
        hint = QLabel("Нажмите «Скачать», чтобы начать загрузку.")
        hint.setFont(QFont("Segoe UI", 11))
        hint.setStyleSheet(f"color: {self.accent_purple_light}; font-weight: bold;")
        layout.addWidget(hint)
        layout.addStretch()
        
        return frame
    
    def _page_download(self):
        frame = QFrame()
        frame.setStyleSheet("background-color: transparent;")
        layout = QVBoxLayout(frame)
        
        title = QLabel("⬇️ Загрузка и установка")
        title.setFont(QFont("Segoe UI", 18, QFont.Bold))
        title.setStyleSheet(f"color: {self.accent_purple_light};")
        layout.addWidget(title)
        
        text = QLabel("Идёт скачивание. Не закрывайте установщик.")
        text.setFont(QFont("Segoe UI", 12))
        text.setStyleSheet(f"color: {self.text_light};")
        layout.addWidget(text)
        layout.addStretch()
        
        return frame
    
    def _page_finish(self):
        frame = QFrame()
        frame.setStyleSheet("background-color: transparent;")
        layout = QVBoxLayout(frame)
        
        title = QLabel("✅ Установка завершена!")
        title.setFont(QFont("Segoe UI", 20, QFont.Bold))
        title.setStyleSheet(f"color: {self.accent_purple_light};")
        layout.addWidget(title)
        
        layout.addSpacing(15)
        
        text = QLabel(f"🎉 {APP_NAME} успешно установлен на ваш компьютер.")
        text.setFont(QFont("Segoe UI", 12))
        text.setStyleSheet(f"color: {self.text_light};")
        layout.addWidget(text)
        layout.addStretch()
        
        return frame
    
    def show_page(self, name: str):
        # Очистить старую страницу
        while self.page_layout.count():
            self.page_layout.takeAt(0).widget().hide()
        
        # Показать новую страницу
        self.page_layout.addWidget(self.pages[name])
        self.pages[name].show()
        self.current_page = name
        self._sync_buttons()
    
    def _sync_buttons(self):
        if self.current_page == "welcome":
            self.btn_back.setEnabled(False)
            self.btn_cancel.setEnabled(True)
            self.btn_next.setEnabled(True)
            self.btn_next.setText("Далее →")
        
        elif self.current_page == "license":
            self.btn_back.setEnabled(True)
            self.btn_cancel.setEnabled(True)
            self.btn_next.setEnabled(self.check_agree.isChecked())
            self.btn_next.setText("Далее →")
        
        elif self.current_page == "options":
            self.btn_back.setEnabled(True)
            self.btn_cancel.setEnabled(True)
            self.btn_next.setEnabled(True)
            self.btn_next.setText("Скачать")
        
        elif self.current_page == "download":
            self.btn_back.setEnabled(False)
            self.btn_cancel.setEnabled(False)
            self.btn_next.setEnabled(False)
            self.btn_next.setText("Скачать")
        
        elif self.current_page == "finish":
            self.btn_back.setEnabled(False)
            self.btn_cancel.setEnabled(True)
            self.btn_next.setEnabled(True)
            self.btn_next.setText("Готово")
    
    def _browse_folder(self):
        folder = QFileDialog.getExistingDirectory(self, "Выберите папку установки")
        if folder:
            self.input_path.setText(folder)
    
    def on_back(self):
        if self.current_page == "license":
            self.show_page("welcome")
        elif self.current_page == "options":
            self.show_page("license")
    
    def on_next(self):
        if self.current_page == "welcome":
            self.show_page("license")
        elif self.current_page == "license":
            self.agreed = self.check_agree.isChecked()
            self.show_page("options")
        elif self.current_page == "options":
            self.install_root = self.input_path.text()
            self.opt_shortcut = self.check_shortcut.isChecked()
            self.opt_run_after = self.check_run.isChecked()
            self.show_page("download")
            self.progress_bar.setValue(0)
            self.label_amount.setText("")
            self.label_speed.setText("")
            threading.Thread(target=self._install_worker, daemon=True).start()
        elif self.current_page == "finish":
            self.close()
    
    def _install_worker(self):
        try:
            install_root = self.install_root
            install_exe = os.path.join(install_root, f"{APP_NAME}.exe")
            temp_exe = os.path.join(install_root, "download.tmp")
            
            ensure_dir(install_root)
            
            self.worker_signals.status_changed.emit("Скачивание файла…")
            self._download_with_progress(DOWNLOAD_URL, temp_exe)
            
            if EXPECTED_SHA256.strip():
                self.worker_signals.status_changed.emit("Проверка SHA-256…")
                got = sha256_file(temp_exe).lower()
                if got != EXPECTED_SHA256.lower():
                    try:
                        os.remove(temp_exe)
                    except:
                        pass
                    raise RuntimeError(
                        "Контрольная сумма не совпала!\n\n"
                        "Установка остановлена.\n\n"
                        f"Ожидалось: {EXPECTED_SHA256}\n"
                        f"Получено:  {got}"
                    )
            
            self.worker_signals.status_changed.emit("Установка…")
            if os.path.exists(install_exe):
                try:
                    os.remove(install_exe)
                except:
                    pass
            os.replace(temp_exe, install_exe)
            
            if self.opt_shortcut:
                self.worker_signals.status_changed.emit("Создание ярлыка…")
                create_desktop_shortcut(install_exe, APP_NAME)
            
            self.worker_signals.progress_changed.emit(100)
            self.worker_signals.status_changed.emit("Готово ✅")
            
            if self.opt_run_after:
                self.worker_signals.status_changed.emit("Запуск…")
                subprocess.Popen([install_exe], cwd=os.path.dirname(install_exe), shell=False)
            
            self.worker_signals.finished.emit()
        
        except Exception as e:
            self.worker_signals.error.emit(str(e))
    
    def _download_with_progress(self, url: str, out_path: str):
        req = Request(url, headers={"User-Agent": f"{APP_NAME}-Installer/1.0"})
        downloaded = 0
        last_t = time.time()
        last_b = 0
        
        try:
            with urlopen(req, timeout=30) as resp:
                total = resp.headers.get("Content-Length")
                total = int(total) if total else None
                
                ctype = (resp.headers.get("Content-Type") or "").lower()
                if "text/html" in ctype:
                    raise RuntimeError(
                        "Сервер вернул HTML вместо файла.\n"
                        "Проверь прямую ссылку на EXE (без Cloudflare verify/редиректов)."
                    )
                
                with open(out_path, "wb") as f:
                    while True:
                        chunk = resp.read(64 * 1024)
                        if not chunk:
                            break
                        f.write(chunk)
                        downloaded += len(chunk)
                        
                        if total:
                            self.worker_signals.progress_changed.emit(int(downloaded * 100.0 / total))
                            self.worker_signals.amount_changed.emit(
                                f"{human_bytes(downloaded)} / {human_bytes(total)}"
                            )
                        else:
                            self.worker_signals.amount_changed.emit(f"{human_bytes(downloaded)}")
                        
                        now = time.time()
                        if now - last_t >= 0.3:
                            sp = (downloaded - last_b) / (now - last_t)
                            self.worker_signals.speed_changed.emit(f"{human_bytes(sp)}/s")
                            last_t = now
                            last_b = downloaded
        
        except URLError as e:
            raise RuntimeError(f"Ошибка сети: {e.reason}")
    
    def _on_status_changed(self, status: str):
        self.label_status.setText(status)
    
    def _on_progress_changed(self, value: int):
        self.progress_bar.setValue(value)
    
    def _on_amount_changed(self, amount: str):
        self.label_amount.setText(amount)
    
    def _on_speed_changed(self, speed: str):
        self.label_speed.setText(speed)
    
    def _on_install_finished(self):
        self.show_page("finish")
    
    def _on_install_error(self, error: str):
        from PySide6.QtWidgets import QMessageBox
        msg = QMessageBox(self)
        msg.setWindowTitle("Ошибка установки")
        msg.setText(error)
        msg.setIcon(QMessageBox.Critical)
        msg.setStyleSheet(f"""
            QMessageBox {{
                background-color: {self.bg_secondary};
            }}
            QMessageBox QLabel {{
                color: {self.text_light};
            }}
            QMessageBox QPushButton {{
                min-width: 60px;
            }}
        """)
        msg.exec()
        self.close()

def main():
    app = QApplication(sys.argv)
    wizard = Wizard()
    wizard.show()
    sys.exit(app.exec())

if __name__ == "__main__":
    main()
