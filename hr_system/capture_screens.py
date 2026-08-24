import sys
from PySide6.QtWidgets import QApplication
from PySide6.QtCore import Qt

from config_manager import ConfigManager
from db_connection import DatabaseConnection
from ui.login_window import LoginWindow
from ui.settings_window import SettingsWindow
from ui.main_window import MainWindow

OUT = "/tmp/opencode/screens"


def grab(widget, filename):
    pixmap = widget.grab()
    pixmap.save(f"{OUT}/{filename}")
    print("saved", filename)


def main():
    app = QApplication(sys.argv)
    app.setLayoutDirection(Qt.RightToLeft)
    app.setStyle('Fusion')

    cfg = ConfigManager(config_path="/tmp/opencode/t3.ini", key_path="/tmp/opencode/t3.key")
    db = DatabaseConnection()

    login = LoginWindow(cfg, db)
    login.id_input.setText("2107")
    login.name_input.setText("احمد محمد")
    grab(login, "01_login.png")

    settings = SettingsWindow(cfg, db)
    settings.main_db_input.setText("C:/PROJECTS/amr/06-08-2026/Source/2025.mdb")
    settings.ts_db_input.setText("C:/PROJECTS/amr/06-08-2026/Source/TimeSheet.mdb")
    settings._update_main_status("ok", "الملف موجود (2025.mdb) - تم الحفظ")
    settings._update_ts_status("ok", "الملف موجود (TimeSheet.mdb) - تم الحفظ")
    settings.resize(750, 480)
    grab(settings, "02_settings.png")

    main_win = MainWindow({"id": 2107.0, "name": "احمد محمد", "agor": 1, "is_developer": 0}, cfg, db)
    main_win.resize(900, 600)
    grab(main_win, "03_main.png")

    print("DONE")


if __name__ == "__main__":
    main()
