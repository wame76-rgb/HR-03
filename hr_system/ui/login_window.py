"""
شاشة تسجيل الدخول - نظام إدارة الموارد البشرية
التاريخ: 2026-08-23
سجل التعديلات:
- v1.0.0: الشاشة الأساسية مع جلب الاسم في QThread منفصل.
- v1.1.0: معالجة الأخطاء الأمنية برقي دون تسريب تفاصيل التكوين أو انهيار الواجهة عند غياب مسارات قاعدة البيانات.
"""
from PySide6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel, QLineEdit,
    QPushButton, QMessageBox
)
from PySide6.QtCore import Qt, QTimer, QThread, Signal
from PySide6.QtGui import QFont, QColor


class NameFetcherThread(QThread):
    """جلب الاسم في خيط منفصل حتى لا تتجمد الواجهة"""
    name_fetched = Signal(str, str)  # (user_id, name)

    def __init__(self, db, db_path, user_id, db_password):
        super().__init__()
        self.db = db
        self.db_path = db_path
        self.user_id = user_id
        self.db_password = db_password

    def run(self):
        try:
            name = self.db.get_employee_name(self.db_path, self.user_id, self.db_password)
            self.name_fetched.emit(self.user_id, name if name else "غير موجود")
        except Exception:
            self.name_fetched.emit(self.user_id, "")


class LoginWindow(QDialog):
    def __init__(self, config_manager, db_connection, parent=None):
        super().__init__(parent)
        self.config = config_manager
        self.db = db_connection
        self.user_data = None
        self._name_thread = None

        self.setWindowTitle("تسجيل الدخول")
        self.setFixedSize(450, 500)
        self.setLayoutDirection(Qt.RightToLeft)
        self.setup_ui()
        self.load_last_user()

    def setup_ui(self):
        layout = QVBoxLayout(self)
        layout.setSpacing(18)
        layout.setContentsMargins(40, 40, 40, 40)

        # العنوان - بدون الوان مزعجة
        title = QLabel("نظام ادارة الموارد البشرية")
        title.setFont(QFont("Segoe UI", 16, QFont.Bold))
        title.setAlignment(Qt.AlignCenter)
        title.setStyleSheet("color: #3c4043; padding: 10px;")
        layout.addWidget(title)

        subtitle = QLabel("الرجاء تسجيل الدخول للمتابعة")
        subtitle.setAlignment(Qt.AlignCenter)
        subtitle.setStyleSheet("color: #80868b; padding-bottom: 20px;")
        layout.addWidget(subtitle)

        # الرقم المالي
        layout.addWidget(self._create_label("الرقم المالي"))
        self.id_input = QLineEdit()
        self.id_input.setMinimumHeight(45)
        self.id_input.setPlaceholderText("ادخل الرقم المالي")
        self.id_input.textChanged.connect(self._on_id_changed)
        # Enter من رقم مالي -> يروح لكلمة السر
        self.id_input.returnPressed.connect(self._focus_password)
        layout.addWidget(self.id_input)

        self._name_timer = QTimer(self)
        self._name_timer.setSingleShot(True)
        self._name_timer.setInterval(350)
        self._name_timer.timeout.connect(self._fetch_name)

        # الاسم (تلقائي)
        layout.addWidget(self._create_label("الاسم"))
        self.name_input = QLineEdit()
        self.name_input.setMinimumHeight(45)
        self.name_input.setPlaceholderText("سيتم الجلب تلقائيا")
        self.name_input.setReadOnly(True)
        layout.addWidget(self.name_input)

        # كلمة المرور
        layout.addWidget(self._create_label("كلمة المرور"))
        self.password_input = QLineEdit()
        self.password_input.setMinimumHeight(45)
        self.password_input.setPlaceholderText("ادخل كلمة المرور")
        self.password_input.setEchoMode(QLineEdit.Password)
        # Enter من كلمة سر -> دخول مباشر
        self.password_input.returnPressed.connect(self._login)
        layout.addWidget(self.password_input)

        layout.addSpacing(15)

        # الازرار
        btn_layout = QHBoxLayout()

        login_btn = QPushButton("دخول")
        login_btn.setMinimumHeight(48)
        login_btn.setCursor(Qt.PointingHandCursor)
        login_btn.setStyleSheet(
            "QPushButton { background-color: #1a73e8; color: white; "
            "border: none; border-radius: 8px; font-size: 14px; font-weight: bold; }"
            "QPushButton:hover { background-color: #1765cc; }"
            "QPushButton:pressed { background-color: #185abc; }"
        )
        login_btn.clicked.connect(self._login)

        exit_btn = QPushButton("خروج")
        exit_btn.setMinimumHeight(48)
        exit_btn.setCursor(Qt.PointingHandCursor)
        exit_btn.setStyleSheet(
            "QPushButton { background-color: #ffffff; color: #5f6368; "
            "border: 1px solid #dadce0; border-radius: 8px; font-size: 14px; }"
            "QPushButton:hover { background-color: #f8f9fa; }"
        )
        exit_btn.clicked.connect(self.reject)

        btn_layout.addWidget(exit_btn)
        btn_layout.addWidget(login_btn)
        layout.addLayout(btn_layout)

    def _create_label(self, text):
        label = QLabel(text)
        label.setFont(QFont("Segoe UI", 11, QFont.Bold))
        label.setStyleSheet("color: #3c4043; padding-top: 5px;")
        return label

    def load_last_user(self):
        last = self.config.get_last_user()
        if last:
            self.id_input.setText(last)
            self.password_input.setFocus()

    def _on_id_changed(self, text):
        if text.strip() and self.config.get_main_db():
            self._name_timer.start()
        else:
            self._name_timer.stop()
            self.name_input.clear()

    def _focus_password(self):
        # الانتقال الذكي: من الرقم المالي لكلمة المرور
        self.password_input.setFocus()
        self.password_input.selectAll()

    def _fetch_name(self):
        user_id = self.id_input.text().strip()
        if not user_id:
            return
        if self._name_thread is not None and self._name_thread.isRunning():
            self._name_thread.requestInterruption()
            self._name_thread.wait(50)
        try:
            main_db = self.config.get_main_db()
            if not main_db:
                self.name_input.setText("")
                return
            db_password = self.config.get_password("main")
            thread = NameFetcherThread(
                self.db, main_db, user_id, db_password
            )
            thread.name_fetched.connect(self._on_name_fetched)
            thread.finished.connect(thread.deleteLater)
            self._name_thread = thread
            thread.start()
        except Exception:
            self.name_input.setText("")

    def _on_name_fetched(self, user_id, name):
        if self.id_input.text().strip() == user_id:
            self.name_input.setText(name)

    def _login(self):
        user_id = self.id_input.text().strip()
        password = self.password_input.text().strip()

        if not user_id:
            self.id_input.setFocus()
            QMessageBox.warning(self, "تنبيه", "الرجاء ادخال الرقم المالي")
            return

        if not password:
            self.password_input.setFocus()
            QMessageBox.warning(self, "تنبيه", "الرجاء ادخال كلمة المرور")
            return

        try:
            main_db = self.config.get_main_db()
            if not main_db:
                raise ValueError("مسار قاعدة البيانات فارغ")
            db_password = self.config.get_password("main")
            result = self.db.authenticate(
                main_db,
                user_id,
                password,
                db_password
            )
            if result:
                self.user_data = result
                self.config.set_last_user(user_id)
                self.accept()
            else:
                QMessageBox.critical(self, "خطأ", "الرقم المالي او كلمة المرور غير صحيحة")
                self.password_input.clear()
                self.password_input.setFocus()
        except Exception:
            QMessageBox.critical(self, "خطأ", "تعذر تسجيل الدخول - يرجى مراجعة مسؤول النظام")
