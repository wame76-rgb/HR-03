"""
الشاشة الرئيسية - نظام إدارة الموارد البشرية
التاريخ: 2026-08-23
سجل التعديلات:
- v1.0.0: الشاشة الرئيسية الأساسية بنظام بطاقات 2x2.
- v1.1.0: المرحلة 3 و 4:
  1. حصر ظهور أيقونة الإعدادات على مسؤولي النظام (is_developer == 1) فقط.
  2. إعادة تصميم الواجهة بالكامل إلى نمط Two-Pane مستوحى من GitHub Desktop و Docker Desktop مع دعم كامل لـ RTL.
  3. دمج شعار النظام الجديد في شريط العنوان ومنطقة الترحيب المركزية.
  4. شريط تنقل جانبي قابل للتوسع ديناميكياً.
"""
import os
from PySide6.QtWidgets import (
    QMainWindow, QWidget, QVBoxLayout, QHBoxLayout, QLabel,
    QPushButton, QMessageBox, QFrame, QStyle, QSizePolicy
)
from PySide6.QtCore import Qt, QSize
from PySide6.QtGui import QFont, QIcon, QPixmap

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
LOGO_PNG_PATH = os.path.join(BASE_DIR, "assets", "logo.png")
LOGO_SVG_PATH = os.path.join(BASE_DIR, "assets", "logo.svg")


class MainWindow(QMainWindow):
    def __init__(self, user_data, config_manager, db_connection):
        super().__init__()
        self.user_data = user_data or {}
        self.config = config_manager
        self.db = db_connection
        self.settings_window = None
        self.variables_window = None
        self.month_prep_window = None

        self.setWindowTitle("نظام إدارة الموارد البشرية - الشاشة الرئيسية")
        self.setMinimumSize(1000, 650)
        self.setLayoutDirection(Qt.RightToLeft)

        # ضبط أيقونة النافذة
        if os.path.exists(LOGO_PNG_PATH):
            self.setWindowIcon(QIcon(LOGO_PNG_PATH))

        self.setup_ui()

    def setup_ui(self):
        central = QWidget()
        self.setCentralWidget(central)

        main_layout = QVBoxLayout(central)
        main_layout.setSpacing(0)
        main_layout.setContentsMargins(0, 0, 0, 0)

        # === 1. الشريط العلوي (Top Bar) ===
        top_bar = QFrame()
        top_bar.setFixedHeight(68)
        top_bar.setStyleSheet(
            "QFrame { background-color: #ffffff; border-bottom: 1px solid #dadce0; }"
        )
        top_layout = QHBoxLayout(top_bar)
        top_layout.setContentsMargins(24, 0, 24, 0)

        # بيانات المستخدم الحالي
        user_name = str(self.user_data.get("name", "مستخدم"))
        user_id = self._format_id(self.user_data.get("id", ""))
        
        user_info = QLabel(f"مرحباً، {user_name}   |   الرقم المالي: {user_id}")
        user_info.setFont(QFont("Segoe UI", 11, QFont.Bold))
        user_info.setStyleSheet("color: #3c4043;")
        top_layout.addWidget(user_info)

        top_layout.addStretch()

        # زر الإعدادات: يظهر فقط إذا كان المستخدم مسؤولاً (is_developer == 1)
        is_dev = bool(self.user_data.get("is_developer"))
        if is_dev:
            self.settings_btn = QPushButton()
            self.settings_btn.setFixedSize(42, 42)
            self.settings_btn.setCursor(Qt.PointingHandCursor)
            self.settings_btn.setIcon(
                self.style().standardIcon(QStyle.StandardPixmap.SP_FileDialogDetailedView)
            )
            self.settings_btn.setIconSize(QSize(22, 22))
            self.settings_btn.setToolTip("إعدادات النظام (مسؤول)")
            self.settings_btn.setStyleSheet(
                "QPushButton {"
                "  background-color: transparent;"
                "  color: #5f6368;"
                "  border: 1px solid #dadce0;"
                "  border-radius: 8px;"
                "}"
                "QPushButton:hover {"
                "  background-color: #f1f3f4;"
                "  color: #1a73e8;"
                "  border-color: #1a73e8;"
                "}"
                "QPushButton:pressed {"
                "  background-color: #e8eaed;"
                "}"
            )
            self.settings_btn.clicked.connect(self._open_settings)
            top_layout.addWidget(self.settings_btn)
        else:
            self.settings_btn = None

        main_layout.addWidget(top_bar)

        # === 2. جسم الواجهة الرئيسي بنمط Two-Pane (شريط جانبي + مساحة ترحيب) ===
        body_widget = QWidget()
        body_layout = QHBoxLayout(body_widget)
        body_layout.setSpacing(0)
        body_layout.setContentsMargins(0, 0, 0, 0)

        # (أ) الشريط الجانبي الأيمن (Right Navigation Sidebar)
        sidebar = self._create_sidebar()
        body_layout.addWidget(sidebar)

        # فاصل رأسي بين القائمة واللوحة الرئيسية
        divider = QFrame()
        divider.setFixedWidth(1)
        divider.setStyleSheet("background-color: #e8eaed;")
        body_layout.addWidget(divider)

        # (ب) لوحة الترحيب والمحتوى الرئيسية (Left / Main Welcome Pane)
        welcome_pane = self._create_welcome_pane()
        body_layout.addWidget(welcome_pane, 1)

        main_layout.addWidget(body_widget, 1)

    def _create_sidebar(self):
        sidebar = QFrame()
        sidebar.setFixedWidth(290)
        sidebar.setStyleSheet("QFrame { background-color: #ffffff; }")

        layout = QVBoxLayout(sidebar)
        layout.setContentsMargins(16, 24, 16, 24)
        layout.setSpacing(10)

        # عنوان قسم التنقل
        section_lbl = QLabel("الأقسام والمهام")
        section_lbl.setFont(QFont("Segoe UI", 11, QFont.Bold))
        section_lbl.setStyleSheet("color: #80868b; padding-right: 6px; padding-bottom: 6px;")
        layout.addWidget(section_lbl)

        # قائمة عناصر التنقل - بنية مرنة وقابلة للتوسع بسهولة
        nav_items = [
            {
                "title": "إدخال المتغيرات",
                "subtitle": "حركات الموظفين اليومية وتقرير 24 شهراً",
                "callback": self._open_variables,
            },
            {
                "title": "تهيئة بداية الشهر",
                "subtitle": "تجهيز التواريخ وتوليد سجلات الشهر الجديد",
                "callback": self._open_month_prep,
            }
        ]

        for item in nav_items:
            nav_btn = self._create_nav_button(
                title=item["title"],
                subtitle=item["subtitle"],
                callback=item["callback"]
            )
            layout.addWidget(nav_btn)

        layout.addStretch()

        # تذييل بسيط للشريط الجانبي
        version_lbl = QLabel("إصدار النظام: 1.1.0")
        version_lbl.setFont(QFont("Segoe UI", 9))
        version_lbl.setStyleSheet("color: #9aa0a6; padding-right: 6px;")
        layout.addWidget(version_lbl)

        return sidebar

    def _create_nav_button(self, title, subtitle, callback):
        btn = QPushButton()
        btn.setFixedHeight(74)
        btn.setCursor(Qt.PointingHandCursor)
        btn.setStyleSheet(
            "QPushButton {"
            "  background-color: #ffffff;"
            "  border: 1px solid #e8eaed;"
            "  border-radius: 10px;"
            "  text-align: right;"
            "  padding: 10px 14px;"
            "}"
            "QPushButton:hover {"
            "  background-color: #f8fbff;"
            "  border: 1px solid #1a73e8;"
            "}"
            "QPushButton:pressed {"
            "  background-color: #e8f0fe;"
            "}"
        )

        btn_layout = QVBoxLayout(btn)
        btn_layout.setSpacing(3)
        btn_layout.setContentsMargins(0, 0, 0, 0)

        title_lbl = QLabel(title)
        title_lbl.setFont(QFont("Segoe UI", 12, QFont.Bold))
        title_lbl.setStyleSheet("color: #1a73e8;")
        btn_layout.addWidget(title_lbl)

        sub_lbl = QLabel(subtitle)
        sub_lbl.setFont(QFont("Segoe UI", 9))
        sub_lbl.setStyleSheet("color: #5f6368;")
        sub_lbl.setWordWrap(True)
        btn_layout.addWidget(sub_lbl)

        btn.clicked.connect(callback)
        return btn

    def _create_welcome_pane(self):
        pane = QWidget()
        pane.setStyleSheet("background-color: #fafbfc;")

        layout = QVBoxLayout(pane)
        layout.setContentsMargins(48, 48, 48, 48)
        layout.setAlignment(Qt.AlignCenter)
        layout.setSpacing(20)

        # 1. الشعار المركزي
        logo_label = QLabel()
        logo_label.setAlignment(Qt.AlignCenter)
        if os.path.exists(LOGO_PNG_PATH):
            pixmap = QPixmap(LOGO_PNG_PATH)
            logo_label.setPixmap(pixmap.scaled(130, 130, Qt.KeepAspectRatio, Qt.SmoothTransformation))
        layout.addWidget(logo_label)

        # 2. رسالة الترحيب الرئيسية
        user_name = str(self.user_data.get("name", "مستخدم"))
        welcome_title = QLabel(f"مرحباً، {user_name}")
        welcome_title.setFont(QFont("Segoe UI", 22, QFont.Bold))
        welcome_title.setStyleSheet("color: #202124;")
        welcome_title.setAlignment(Qt.AlignCenter)
        layout.addWidget(welcome_title)

        # 3. الرقم المالي والبيان
        user_id = self._format_id(self.user_data.get("id", ""))
        user_subtitle = QLabel(f"الرقم المالي: {user_id}")
        user_subtitle.setFont(QFont("Segoe UI", 13))
        user_subtitle.setStyleSheet("color: #5f6368;")
        user_subtitle.setAlignment(Qt.AlignCenter)
        layout.addWidget(user_subtitle)

        # 4. رسالة توجيهية مريحة ومنسجمة بصرياً
        hint_label = QLabel("يرجى اختيار القسم المطلوب من القائمة الجانبية للبدء في إدخال البيانات أو المتابعة.")
        hint_label.setFont(QFont("Segoe UI", 11))
        hint_label.setStyleSheet("color: #80868b; margin-top: 10px;")
        hint_label.setAlignment(Qt.AlignCenter)
        layout.addWidget(hint_label)

        return pane

    def _format_id(self, value):
        try:
            num = float(value)
            if num.is_integer():
                return str(int(num))
        except (ValueError, TypeError):
            pass
        return str(value)

    def _open_settings(self):
        from ui.settings_window import SettingsWindow
        if self.settings_window is None or not self.settings_window.isVisible():
            self.settings_window = SettingsWindow(self.config, self.db, self)
        self.settings_window.show()
        self.settings_window.raise_()
        self.settings_window.activateWindow()

    def _open_variables(self):
        from ui.variables_window import VariablesWindow
        if self.variables_window is None or not self.variables_window.isVisible():
            self.variables_window = VariablesWindow(
                self.config, self.db, self.user_data, self
            )
        self.variables_window.showMaximized()
        self.variables_window.raise_()
        self.variables_window.activateWindow()

    def _open_month_prep(self):
        from ui.month_prep_window import MonthPrepWindow
        if self.month_prep_window is None or not self.month_prep_window.isVisible():
            self.month_prep_window = MonthPrepWindow(
                self.config, self.db, self.user_data, self
            )
        self.month_prep_window.showMaximized()
        self.month_prep_window.raise_()
        self.month_prep_window.activateWindow()
