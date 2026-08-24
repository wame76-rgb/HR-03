"""
شاشة إعدادات التطبيق - نظام إدارة الموارد البشرية
التاريخ: 2026-08-23
سجل التعديلات:
- v1.0.0: الشاشة الأساسية لإعداد مسارات وكلمات مرور قواعد البيانات 2025.mdb و TimeSheet.mdb.
- v1.1.0: تحسين تجربة المستخدم (UX Cleanup): تعديل تسمية زر الإغلاق إلى "موافق" وضمان عدم إظهار أي تحذيرات عند صحة الإعدادات.
"""
from PySide6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel, QLineEdit,
    QPushButton, QFileDialog, QFrame
)
from PySide6.QtCore import Qt, QTimer
from PySide6.QtGui import QFont, QColor
import os


class SettingsWindow(QDialog):
    def __init__(self, config_manager, db_connection, parent=None):
        super().__init__(parent)
        self.config = config_manager
        self.db = db_connection

        self.setWindowTitle("اعدادات التطبيق")
        self.setMinimumSize(750, 480)
        self.setLayoutDirection(Qt.RightToLeft)
        self.setup_ui()
        self.load_settings()

    def setup_ui(self):
        layout = QVBoxLayout(self)
        layout.setSpacing(15)
        layout.setContentsMargins(30, 30, 30, 30)

        title = QLabel("اعدادات التطبيق")
        title.setFont(QFont("Segoe UI", 18, QFont.Bold))
        title.setStyleSheet("color: #1a73e8;")
        layout.addWidget(title)

        # === ملف 2025.mdb ===
        layout.addWidget(self._create_section_label("ملف البيانات الرئيسي (2025.mdb)"))

        # صف المسار + شارة الحالة
        main_path_row = QHBoxLayout()
        self.main_db_input = QLineEdit()
        self.main_db_input.setPlaceholderText("اختر مسار الملف 2025.mdb")
        self.main_db_input.setMinimumHeight(40)
        self.main_db_input.textChanged.connect(self._on_main_path_changed)
        main_btn = QPushButton("اختيار")
        main_btn.setMinimumHeight(40)
        main_btn.setCursor(Qt.PointingHandCursor)
        main_btn.clicked.connect(lambda: self._browse_file(self.main_db_input))
        main_path_row.addWidget(self.main_db_input)
        main_path_row.addWidget(main_btn)
        layout.addLayout(main_path_row)

        # شارة الحالة (خلفية ملونة)
        self.main_status_frame = QFrame()
        self.main_status_frame.setMinimumHeight(35)
        self.main_status_frame.setStyleSheet("background-color: transparent; border: none;")
        main_status_layout = QHBoxLayout(self.main_status_frame)
        main_status_layout.setContentsMargins(0, 0, 0, 0)
        self.main_status_label = QLabel("")
        self.main_status_label.setFont(QFont("Segoe UI", 10))
        main_status_layout.addWidget(self.main_status_label)
        main_status_layout.addStretch()
        layout.addWidget(self.main_status_frame)

        # كلمة سر 2025
        pwd1_layout = QHBoxLayout()
        pwd1_label = QLabel("كلمة السر:")
        pwd1_label.setFixedWidth(80)
        self.main_pwd_input = QLineEdit()
        self.main_pwd_input.setEchoMode(QLineEdit.Password)
        self.main_pwd_input.setPlaceholderText("كلمة سر 2025.mdb")
        self.main_pwd_input.setMinimumHeight(40)
        self.main_pwd_input.textChanged.connect(self._on_main_pwd_changed)
        pwd1_layout.addWidget(pwd1_label)
        pwd1_layout.addWidget(self.main_pwd_input)
        layout.addLayout(pwd1_layout)

        layout.addSpacing(15)

        # === ملف TimeSheet.mdb ===
        layout.addWidget(self._create_section_label("ملف الجداول (TimeSheet.mdb)"))

        ts_path_row = QHBoxLayout()
        self.ts_db_input = QLineEdit()
        self.ts_db_input.setPlaceholderText("اختر مسار الملف TimeSheet.mdb")
        self.ts_db_input.setMinimumHeight(40)
        self.ts_db_input.textChanged.connect(self._on_ts_path_changed)
        ts_btn = QPushButton("اختيار")
        ts_btn.setMinimumHeight(40)
        ts_btn.setCursor(Qt.PointingHandCursor)
        ts_btn.clicked.connect(lambda: self._browse_file(self.ts_db_input))
        ts_path_row.addWidget(self.ts_db_input)
        ts_path_row.addWidget(ts_btn)
        layout.addLayout(ts_path_row)

        self.ts_status_frame = QFrame()
        self.ts_status_frame.setMinimumHeight(35)
        self.ts_status_frame.setStyleSheet("background-color: transparent; border: none;")
        ts_status_layout = QHBoxLayout(self.ts_status_frame)
        ts_status_layout.setContentsMargins(0, 0, 0, 0)
        self.ts_status_label = QLabel("")
        self.ts_status_label.setFont(QFont("Segoe UI", 10))
        ts_status_layout.addWidget(self.ts_status_label)
        ts_status_layout.addStretch()
        layout.addWidget(self.ts_status_frame)

        # كلمة سر TimeSheet
        pwd2_layout = QHBoxLayout()
        pwd2_label = QLabel("كلمة السر:")
        pwd2_label.setFixedWidth(80)
        self.ts_pwd_input = QLineEdit()
        self.ts_pwd_input.setEchoMode(QLineEdit.Password)
        self.ts_pwd_input.setPlaceholderText("كلمة سر TimeSheet.mdb")
        self.ts_pwd_input.setMinimumHeight(40)
        self.ts_pwd_input.textChanged.connect(self._on_ts_pwd_changed)
        pwd2_layout.addWidget(pwd2_label)
        pwd2_layout.addWidget(self.ts_pwd_input)
        layout.addLayout(pwd2_layout)

        layout.addStretch()

        info = QLabel("يتم حفظ الاعدادات تلقائيا عند نجاح الفحص")
        info.setStyleSheet("color: #5f6368; font-style: italic;")
        info.setAlignment(Qt.AlignCenter)
        layout.addWidget(info)

        btn_layout = QHBoxLayout()
        close_btn = QPushButton("موافق")
        close_btn.setMinimumHeight(52)
        close_btn.setMinimumWidth(140)
        close_btn.setCursor(Qt.PointingHandCursor)
        close_btn.setStyleSheet(
            "QPushButton { background-color: #f8f9fa; color: #3c4043; "
            "border: 1px solid #dadce0; border-radius: 8px; font-size: 15px; font-weight: bold; }"
            "QPushButton:hover { background-color: #e8eaed; }"
        )
        close_btn.clicked.connect(self.accept)
        btn_layout.addStretch()
        btn_layout.addWidget(close_btn)
        layout.addLayout(btn_layout)

        self.main_timer = QTimer()
        self.main_timer.setSingleShot(True)
        self.main_timer.timeout.connect(self._check_main_file)

        self.ts_timer = QTimer()
        self.ts_timer.setSingleShot(True)
        self.ts_timer.timeout.connect(self._check_ts_file)

    def _create_section_label(self, text):
        label = QLabel(text)
        label.setFont(QFont("Segoe UI", 12, QFont.Bold))
        label.setStyleSheet("color: #5f6368;")
        return label

    def _browse_file(self, input_field):
        path, _ = QFileDialog.getOpenFileName(
            self, "اختر ملف قاعدة البيانات", "",
            "Access Files (*.mdb *.accdb)"
        )
        if path:
            input_field.setText(path)

    def _on_main_path_changed(self, text):
        self._update_main_status("neutral", "جاري الفحص...")
        self.main_timer.start(500)

    def _on_ts_path_changed(self, text):
        self._update_ts_status("neutral", "جاري الفحص...")
        self.ts_timer.start(500)

    def _on_main_pwd_changed(self, text):
        if self._is_main_path_valid():
            self.config.set_password("main", text)

    def _on_ts_pwd_changed(self, text):
        if self._is_ts_path_valid():
            self.config.set_password("timesheet", text)

    def _is_main_path_valid(self):
        path = self.main_db_input.text().strip()
        if not path or not os.path.isfile(path):
            return False
        return self._has_correct_name(path, "2025")

    def _is_ts_path_valid(self):
        path = self.ts_db_input.text().strip()
        if not path or not os.path.isfile(path):
            return False
        return self._has_correct_name(path, "TimeSheet")

    def _has_correct_name(self, path, expected):
        filename = os.path.basename(path).lower()
        return filename.startswith(expected.lower()) and (filename.endswith(".mdb") or filename.endswith(".accdb"))

    def _check_main_file(self):
        path = self.main_db_input.text().strip()
        if not path:
            self._update_main_status("neutral", "")
            return
        if self._is_main_path_valid():
            self._update_main_status("ok", "الملف موجود (2025.mdb) - تم الحفظ")
            self.config.set_main_db(path)
        else:
            self._update_main_status("error", "الملف غير موجود او الاسم غير صحيح (يجب ان يكون 2025.mdb)")

    def _check_ts_file(self):
        path = self.ts_db_input.text().strip()
        if not path:
            self._update_ts_status("neutral", "")
            return
        if self._is_ts_path_valid():
            self._update_ts_status("ok", "الملف موجود (TimeSheet.mdb) - تم الحفظ")
            self.config.set_timesheet_db(path)
        else:
            self._update_ts_status("error", "الملف غير موجود او الاسم غير صحيح (يجب ان يكون TimeSheet.mdb)")

    def _update_main_status(self, state, text):
        if state == "ok":
            self.main_status_label.setText("✓ " + text)
            self.main_status_label.setStyleSheet(
                "color: white; background-color: #34a853; "
                "padding: 6px 12px; border-radius: 6px; font-weight: bold;"
            )
        elif state == "error":
            self.main_status_label.setText("✗ " + text)
            self.main_status_label.setStyleSheet(
                "color: white; background-color: #ea4335; "
                "padding: 6px 12px; border-radius: 6px; font-weight: bold;"
            )
        else:
            self.main_status_label.setText(text)
            self.main_status_label.setStyleSheet(
                "color: #5f6368; background-color: #f1f3f4; "
                "padding: 6px 12px; border-radius: 6px;"
            )

    def _update_ts_status(self, state, text):
        if state == "ok":
            self.ts_status_label.setText("✓ " + text)
            self.ts_status_label.setStyleSheet(
                "color: white; background-color: #34a853; "
                "padding: 6px 12px; border-radius: 6px; font-weight: bold;"
            )
        elif state == "error":
            self.ts_status_label.setText("✗ " + text)
            self.ts_status_label.setStyleSheet(
                "color: white; background-color: #ea4335; "
                "padding: 6px 12px; border-radius: 6px; font-weight: bold;"
            )
        else:
            self.ts_status_label.setText(text)
            self.ts_status_label.setStyleSheet(
                "color: #5f6368; background-color: #f1f3f4; "
                "padding: 6px 12px; border-radius: 6px;"
            )

    def load_settings(self):
        self.main_db_input.blockSignals(True)
        self.ts_db_input.blockSignals(True)
        self.main_pwd_input.blockSignals(True)
        self.ts_pwd_input.blockSignals(True)

        self.main_db_input.setText(self.config.get_main_db())
        self.ts_db_input.setText(self.config.get_timesheet_db())

        main_pwd = self.config.get_password("main")
        if main_pwd:
            self.main_pwd_input.setText(main_pwd)

        ts_pwd = self.config.get_password("timesheet")
        if ts_pwd:
            self.ts_pwd_input.setText(ts_pwd)

        self.main_db_input.blockSignals(False)
        self.ts_db_input.blockSignals(False)
        self.main_pwd_input.blockSignals(False)
        self.ts_pwd_input.blockSignals(False)

        if self._is_main_path_valid():
            self._update_main_status("ok", "الملف موجود (2025.mdb)")
        if self._is_ts_path_valid():
            self._update_ts_status("ok", "الملف موجود (TimeSheet.mdb)")
