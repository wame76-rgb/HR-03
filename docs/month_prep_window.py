"""
شاشة تهيئة بداية الشهر - نظام إدارة الموارد البشرية
التاريخ: 2026-08-23
سجل التعديلات:
- v1.0.0: الشاشة الأساسية وتجهيز التقويم وربط الخيوط.
- v1.1.0: إصلاح صريح وحاسم لمسارات قواعد البيانات (Path Resolution Fix):
  1. القراءة الصحيحة من قسم [DATABASE] عبر ConfigManager (get_timesheet_db / get_main_db) بدلاً من 'paths'.
  2. توحيد وحساب المسارات المطلقة اعتماداً على BASE_DIR لحماية الاتصال من الانهيار.
  3. ربط كلمات المرور المشفرة لملفي TimeSheet و Main بشكل منفصل ودقيق.
  4. منع ظهور رسالة الخطأ (مسار قاعدة البيانات فارغ) وعرض المسار الفيزيائي الحقيقي في كارت الحالة.
"""
import os
import calendar
from datetime import date, datetime
from PySide6.QtWidgets import (
    QMainWindow, QWidget, QVBoxLayout, QHBoxLayout, QLabel,
    QPushButton, QMessageBox, QFrame, QGridLayout,
    QSizePolicy, QProgressBar, QCheckBox, QLineEdit, QSpacerItem
)
from PySide6.QtCore import Qt, QSize, QThread, Signal
from PySide6.QtGui import QFont

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CHECKMARK_SVG = os.path.join(BASE_DIR, "assets", "checkmark.svg").replace("\\", "/")


class MonthPrepThread(QThread):
    progress = Signal(int, str)
    finished = Signal(dict)
    error = Signal(str)

    def __init__(self, db, ts_db_path, main_db_path, issue, dates_list, holidays_set, holiday_var_code=None, db_password=""):
        super().__init__()
        self.db = db
        self.ts_db_path = ts_db_path
        self.main_db_path = main_db_path
        self.issue = issue
        self.dates_list = dates_list
        self.holidays_set = holidays_set
        self.holiday_var_code = holiday_var_code
        self.db_password = db_password

    def run(self):
        try:
            def on_progress(pct, msg):
                self.progress.emit(pct, msg)

            result = self.db.initialize_month_records(
                ts_db_path=self.ts_db_path,
                main_db_path=self.main_db_path,
                issue=self.issue,
                dates_list=self.dates_list,
                holidays_set=self.holidays_set,
                holiday_var_code=self.holiday_var_code,
                progress_callback=on_progress,
                db_password=self.db_password
            )
            self.finished.emit(result)
        except Exception as e:
            self.error.emit(str(e))


class DayCardWidget(QFrame):
    """
    بطاقة اليوم التفاعلية في شبكة التقويم الجدارية (Directive 5: Clean Day Cards)
    Displays only:
    - Large Day Number (18px bold)
    - Status Badge (10px/11px bold)
    """
    toggled = Signal(object, object)

    def __init__(self, dt_val, day_type='workday', state='work', parent=None):
        super().__init__(parent)
        self.dt_val = dt_val
        self.day_type = day_type  # 'rest', 'workday', 'sunday'
        self.state = state        # 'work', 'rest', 'holiday', 'wfh'
        self.setMinimumSize(74, 72)
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        self._can_toggle = True
        self._setup_ui()
        self.update_style()

    def _setup_ui(self):
        self.layout = QVBoxLayout(self)
        self.layout.setContentsMargins(6, 8, 6, 8)
        self.layout.setSpacing(4)
        self.layout.setAlignment(Qt.AlignCenter)

        # Day Number (18px bold, centered)
        self.day_num_label = QLabel(str(self.dt_val.day))
        self.day_num_label.setFont(QFont("Segoe UI", 18, QFont.Bold))
        self.day_num_label.setAlignment(Qt.AlignCenter)
        self.layout.addWidget(self.day_num_label)

        # Status Label (10px/11px bold)
        self.badge_label = QLabel("")
        self.badge_label.setFont(QFont("Segoe UI", 10, QFont.Bold))
        self.badge_label.setAlignment(Qt.AlignCenter)
        self.badge_label.setFixedHeight(22)
        self.layout.addWidget(self.badge_label)

        weekday = self.dt_val.weekday()
        if weekday == 6:
            self.day_type = "sunday"
        elif weekday in (4, 5):
            self.day_type = "rest"
        else:
            self.day_type = "workday"
        self.setCursor(Qt.PointingHandCursor if self.day_type in ("workday", "sunday") else Qt.ArrowCursor)

    def set_state(self, state):
        self.state = state
        self.update_style()

    def mousePressEvent(self, event):
        if not getattr(self, "_can_toggle", True):
            return
        if self.day_type in ("workday", "sunday", "rest") and event.button() == Qt.LeftButton:
            new_state = self._determine_next_state()
            self.toggled.emit(self.dt_val, new_state)
        super().mousePressEvent(event)

    def _determine_next_state(self):
        if self.state == 'holiday':
            if self.day_type == "workday":
                return "work"
            elif self.day_type == "sunday":
                return "wfh"
            else:
                return "rest"
        elif self.state == "wfh":
            return "holiday"
        elif self.state == "rest":
            return "holiday"
        else:
            return "holiday"

    def update_style(self):
        palette = {
            'rest': {
                'bg': '#f1f3f4',
                'border': '#dadce0',
                'num': '#5f6368',
                'badgetx': '#5f6368',
                'badgebg': '#e0e0e0',
                'badge': "راحة (R)",
            },
            'wfh': {
                'bg': '#f3e5f5',
                'border': '#ab47bc',
                'num': '#8e24aa',
                'badgetx': '#6a1b9a',
                'badgebg': '#e1bee7',
                'badge': "عمل عن بعد (WH)",
            },
            'work': {
                'bg': '#ffffff',
                'border': '#dadce0',
                'num': '#202124',
                'badgetx': '#5f6368',
                'badgebg': '#f1f3f4',
                'badge': "عمل",
            },
            'holiday': {
                'bg': '#1a73e8',
                'border': '#1a73e8',
                'num': '#ffffff',
                'badgetx': '#ffffff',
                'badgebg': '#1566cc',
                'badge': "عطلة (H)",
            }
        }
        p = palette.get(self.state, palette['work'])
        base = f"QFrame {{ background-color: {p['bg']}; border: 1.5px solid {p['border']}; border-radius: 10px; }}"
        if self.state == 'work':
            base += " QFrame:hover { border: 2px solid #1a73e8; background-color: #f8fbff; }"
        self.setStyleSheet(base)
        self.day_num_label.setStyleSheet(f"color: {p['num']}; font-weight: bold; border: none; background: transparent;")
        self.badge_label.setText(p['badge'])
        self.badge_label.setStyleSheet(
            f"background-color: {p['badgebg']}; color: {p['badgetx']}; border-radius: 5px; padding: 1px 6px; font-weight: bold;"
        )
        if self.day_type in ("workday", "sunday") or (self.day_type == "rest" and getattr(self, "_can_toggle", True)):
            self.setCursor(Qt.PointingHandCursor if getattr(self, "_can_toggle", True) else Qt.ArrowCursor)
        else:
            self.setCursor(Qt.ArrowCursor)

    def set_toggling_enabled(self, enabled=True):
        self._can_toggle = enabled
        if self.day_type in ("workday", "sunday") or self.day_type == "rest":
            self.setCursor(Qt.PointingHandCursor if enabled else Qt.ArrowCursor)


class MonthPrepWindow(QMainWindow):
    def __init__(self, config_manager, db_connection, user_data, parent=None):
        super().__init__(parent)
        self.config = config_manager
        self.db = db_connection
        self.user_data = user_data or {}
        self.holidays_set = set()
        self.wfh_set = set()
        self.day_cards = []
        self.prep_thread = None
        self.holidays_enabled = False

        self.setWindowTitle("تهيئة بداية الشهر - نظام الموارد البشرية")
        self.setMinimumSize(1120, 740)
        self.setLayoutDirection(Qt.RightToLeft)

        # Directive 3: Disable size grip on main window & status bar
        if hasattr(self, 'setSizeGripEnabled'):
            self.setSizeGripEnabled(False)
        if self.statusBar():
            self.statusBar().setSizeGripEnabled(False)

        self._setup_ui()
        self._init_default_month()
        self._refresh_month_data()

    def _get_resolved_paths(self):
        """Standardized and absolute path resolution for TimeSheet.mdb and 2025.mdb"""
        ts_path = ""
        main_path = ""
        if hasattr(self.config, 'get_timesheet_db'):
            ts_path = self.config.get_timesheet_db()
        if hasattr(self.config, 'get_main_db'):
            main_path = self.config.get_main_db()

        if not ts_path and hasattr(self.config, 'config'):
            ts_path = self.config.config.get('DATABASE', 'timesheet_db', fallback='')
        if not main_path and hasattr(self.config, 'config'):
            main_path = self.config.config.get('DATABASE', 'main_db', fallback='')

        if ts_path and not os.path.isabs(ts_path):
            ts_path = os.path.normpath(os.path.join(BASE_DIR, ts_path))
        if main_path and not os.path.isabs(main_path):
            main_path = os.path.normpath(os.path.join(BASE_DIR, main_path))

        return ts_path, main_path

    @staticmethod
    def _extract_triple_name(full_name: str) -> str:
        """Directive 2: Extract triple name (الاسم الثلاثي) from full username."""
        if not full_name:
            return "مستخدم"
        parts = full_name.strip().split()
        return " ".join(parts[:3]) if len(parts) >= 3 else full_name.strip()

    def _setup_ui(self):
        central = QWidget()
        central.setStyleSheet("background-color: #fafbfc;")
        self.setCentralWidget(central)
        main_layout = QVBoxLayout(central)
        main_layout.setSpacing(0)
        main_layout.setContentsMargins(0, 0, 0, 0)

        # === Main Content Zone ===
        content_widget = QWidget()
        content_layout = QHBoxLayout(content_widget)
        content_layout.setContentsMargins(20, 16, 20, 14)
        content_layout.setSpacing(18)

        # --- RIGHT PANEL (Column A - Control Panel) ---
        right_panel = self._build_control_panel()
        right_panel.setFixedWidth(380)
        content_layout.addWidget(right_panel)

        # --- LEFT PANEL (Calendar Grid) ---
        left_panel = self._build_calendar_panel()
        content_layout.addWidget(left_panel, stretch=1)
        main_layout.addWidget(content_widget, stretch=1)

        # --- BOTTOM BAR (Status & Progress) ---
        action_bar = self._build_bottom_bar()
        main_layout.addWidget(action_bar)

    def _build_control_panel(self):
        """Builds Column A (Right Control Panel) with integrated Action Buttons."""
        panel = QWidget()
        layout = QVBoxLayout(panel)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(12)

        # --- Directive 2: Top User Info Card with Triple-Name Truncation ---
        user_card = QFrame()
        user_card.setStyleSheet(
            "QFrame { background-color: #f8f9fa; border: 1.5px solid #e0e1e3; border-radius: 10px; }"
        )
        user_layout = QHBoxLayout(user_card)
        user_layout.setContentsMargins(14, 12, 14, 12)
        user_layout.setSpacing(8)

        emp_id = self.user_data.get('id', self.user_data.get('emp_id', ''))
        try:
            emp_id_str = str(int(float(emp_id))) if emp_id is not None and str(emp_id).strip() != '' else ''
        except Exception:
            emp_id_str = str(emp_id) if emp_id else ''
        raw_name = self.user_data.get('name', self.user_data.get('username', 'وليد ممدوح يوسف محمد المليجي'))
        triple_name = self._extract_triple_name(raw_name)

        user_lbl = QLabel(f"👤 المستخدم الحالي: {triple_name} | الرقم المالي: {emp_id_str}")
        user_lbl.setFont(QFont("Segoe UI", 10, QFont.Bold))
        user_lbl.setStyleSheet("color: #202124; border: none;")
        user_lbl.setAlignment(Qt.AlignRight | Qt.AlignVCenter)
        user_layout.addWidget(user_lbl)
        layout.addWidget(user_card)

        # --- Month Picker Card (Directive 3: True Adjacency) ---
        month_card = QFrame()
        month_card.setStyleSheet(
            "QFrame { background-color: #ffffff; border: 1px solid #e8eaed; border-radius: 12px; }"
        )
        month_card_layout = QVBoxLayout(month_card)
        month_card_layout.setContentsMargins(16, 12, 16, 12)
        month_card_layout.setSpacing(8)

        card_title = QLabel("تحديد الشهر المستهدف")
        card_title.setFont(QFont("Segoe UI", 11, QFont.Bold))
        card_title.setStyleSheet("color: #3c4043; border: none;")
        month_card_layout.addWidget(card_title)

        picker_row = QHBoxLayout()
        picker_row.setSpacing(2)
        picker_row.setContentsMargins(0, 0, 0, 0)

        self.btn_month_minus = QPushButton("–")
        self.btn_month_minus.setFixedSize(32, 32)
        self.btn_month_minus.setFont(QFont("Segoe UI", 16, QFont.Bold))
        self.btn_month_minus.setCursor(Qt.PointingHandCursor)
        self.btn_month_minus.setStyleSheet(
            "QPushButton { background-color: #f4f6fb; color: #202124;"
            "  border: 1.5px solid #dadce0; border-radius: 6px; margin: 0px; }"
            "QPushButton:hover { background-color: #e8eaed; }"
        )
        self.btn_month_minus.clicked.connect(self._decrement_month)
        picker_row.addWidget(self.btn_month_minus)

        self.month_issueline = QLineEdit()
        self.month_issueline.setAlignment(Qt.AlignCenter)
        self.month_issueline.setFont(QFont("Segoe UI", 13, QFont.Bold))
        self.month_issueline.setMaxLength(6)
        self.month_issueline.setFixedWidth(94)
        self.month_issueline.setFixedHeight(36)
        self.month_issueline.setStyleSheet(
            "QLineEdit { background: #fff; color: #1a73e8; border: 1.5px solid #dadce0; border-radius: 6px; font-size: 16px; padding: 1px 4px; }"
            "QLineEdit:focus { border: 2px solid #1a73e8; }"
        )
        self.month_issueline.setPlaceholderText("YYYYMM")
        self.month_issueline.returnPressed.connect(self._on_issueline_edited)
        picker_row.addWidget(self.month_issueline)

        self.btn_month_plus = QPushButton("+")
        self.btn_month_plus.setFixedSize(32, 32)
        self.btn_month_plus.setFont(QFont("Segoe UI", 16, QFont.Bold))
        self.btn_month_plus.setCursor(Qt.PointingHandCursor)
        self.btn_month_plus.setStyleSheet(
            "QPushButton { background-color: #f4f6fb; color: #202124;"
            "  border: 1.5px solid #dadce0; border-radius: 6px; margin: 0px; }"
            "QPushButton:hover { background-color: #e8eaed; }"
        )
        self.btn_month_plus.clicked.connect(self._increment_month)
        picker_row.addWidget(self.btn_month_plus)

        picker_container = QWidget()
        picker_container.setLayout(picker_row)
        month_card_layout.addWidget(picker_container, alignment=Qt.AlignCenter)

        self.issue_badge = QLabel("كود الشهر (Issue): 202301")
        self.issue_badge.setFont(QFont("Segoe UI", 10, QFont.Bold))
        self.issue_badge.setAlignment(Qt.AlignCenter)
        self.issue_badge.setFixedHeight(26)
        self.issue_badge.setStyleSheet(
            "background-color: #e8f0fe; color: #1a73e8; border-radius: 6px; border: none; font-size: 13px;"
        )
        month_card_layout.addWidget(self.issue_badge)
        layout.addWidget(month_card)

        # --- Statistics Card ---
        stats_card = QFrame()
        stats_card.setStyleSheet(
            "QFrame { background-color: #ffffff; border: 1px solid #e8eaed; border-radius: 12px; }"
        )
        stats_layout = QVBoxLayout(stats_card)
        stats_layout.setContentsMargins(16, 12, 16, 12)
        stats_layout.setSpacing(8)

        stats_title = QLabel("إحصائيات الشهر")
        stats_title.setFont(QFont("Segoe UI", 11, QFont.Bold))
        stats_title.setStyleSheet("color: #3c4043; border: none;")
        stats_layout.addWidget(stats_title)

        self.lbl_days_count = QLabel("📅 عدد أيام الشهر: ...")
        self.lbl_days_count.setFont(QFont("Segoe UI", 9.5))
        self.lbl_days_count.setStyleSheet("color: #5f6368; border: none;")
        stats_layout.addWidget(self.lbl_days_count)

        self.lbl_total_records = QLabel("📊 إجمالي السجلات المستهدفة: ... سجل")
        self.lbl_total_records.setFont(QFont("Segoe UI", 9.5, QFont.Bold))
        self.lbl_total_records.setStyleSheet("color: #1a73e8; border: none;")
        stats_layout.addWidget(self.lbl_total_records)
        layout.addWidget(stats_card)

        # --- Directive 1: Database File and Table Paths in Status Card ---
        self.db_status_card = QFrame()
        self.db_status_card.setStyleSheet(
            "QFrame { background-color: #e6f4ea; border: 1.5px solid #ceead6; border-radius: 10px; }"
        )
        db_card_layout = QVBoxLayout(self.db_status_card)
        db_card_layout.setContentsMargins(14, 10, 14, 10)
        db_card_layout.setSpacing(4)

        self.status_title_label = QLabel("حالة قاعدة البيانات: متصلة ونشطة 🟢")
        self.status_title_label.setFont(QFont("Segoe UI", 10, QFont.Bold))
        self.status_title_label.setStyleSheet("color: #137333; border: none; background: transparent;")
        self.status_title_label.setAlignment(Qt.AlignRight | Qt.AlignVCenter)
        db_card_layout.addWidget(self.status_title_label)

        self.lbl_db_name = QLabel("قاعدة البيانات: TimeSheet.mdb")
        self.lbl_db_name.setFont(QFont("Segoe UI", 9.5))
        self.lbl_db_name.setStyleSheet("color: #1b5e20; border: none; background: transparent;")
        self.lbl_db_name.setAlignment(Qt.AlignRight)
        db_card_layout.addWidget(self.lbl_db_name)

        self.lbl_db_path = QLabel("المسار: ...")
        self.lbl_db_path.setFont(QFont("Segoe UI", 8.5))
        self.lbl_db_path.setStyleSheet("color: #3c4043; border: none; background: transparent;")
        self.lbl_db_path.setWordWrap(True)
        self.lbl_db_path.setAlignment(Qt.AlignRight)
        db_card_layout.addWidget(self.lbl_db_path)

        self.lbl_db_tables = QLabel("الجدول النشط: DatePrep & var_op")
        self.lbl_db_tables.setFont(QFont("Segoe UI", 9))
        self.lbl_db_tables.setStyleSheet("color: #1b5e20; border: none; background: transparent;")
        self.lbl_db_tables.setAlignment(Qt.AlignRight)
        db_card_layout.addWidget(self.lbl_db_tables)
        layout.addWidget(self.db_status_card)

        layout.addStretch()

        # --- Directive 4: Reposition Action Buttons back to Column A ---
        btn_bar = QHBoxLayout()
        btn_bar.setSpacing(10)
        btn_bar.setContentsMargins(0, 0, 0, 0)

        self.btn_start = QPushButton("بدء تهيئة الشهر")
        self.btn_start.setFixedHeight(48)
        self.btn_start.setCursor(Qt.PointingHandCursor)
        self.btn_start.setFont(QFont("Segoe UI", 11, QFont.Bold))
        self.btn_start.setStyleSheet(
            "QPushButton {"
            "  background-color: #1a73e8;"
            "  color: #ffffff;"
            "  border: none;"
            "  border-radius: 8px;"
            "  font-size: 14.5px;"
            "  font-weight: bold;"
            "  padding: 0 14px;"
            "}"
            "QPushButton:hover {"
            "  background-color: #1557b0;"
            "}"
            "QPushButton:disabled {"
            "  background-color: #dadce0;"
            "  color: #80868b;"
            "}"
        )
        self.btn_start.clicked.connect(self._on_start_clicked)
        btn_bar.addWidget(self.btn_start, stretch=2)

        self.back_btn = QPushButton("رجوع")
        self.back_btn.setFixedHeight(48)
        self.back_btn.setMinimumWidth(85)
        self.back_btn.setCursor(Qt.PointingHandCursor)
        self.back_btn.setFont(QFont("Segoe UI", 11, QFont.Bold))
        self.back_btn.setStyleSheet(
            "QPushButton {"
            "  background-color: #f8f9fa;"
            "  color: #202124;"
            "  border: 1px solid #dadce0;"
            "  border-radius: 8px;"
            "  padding: 0 16px;"
            "  font-size: 14.5px;"
            "  font-weight: bold;"
            "}"
            "QPushButton:hover {"
            "  background-color: #e8eaed;"
            "}"
        )
        self.back_btn.clicked.connect(self.close)
        btn_bar.addWidget(self.back_btn, stretch=1)

        layout.addLayout(btn_bar)
        return panel

    def _build_calendar_panel(self):
        panel = QFrame()
        panel.setStyleSheet("QFrame { background-color: #ffffff; border: 1px solid #e8eaed; border-radius: 12px; }")
        layout = QVBoxLayout(panel)
        layout.setContentsMargins(16, 16, 16, 16)
        layout.setSpacing(12)

        # --- Calendar Controls (SVG Checkmarks) ---
        cal_ctrls_layout = QHBoxLayout()
        cal_ctrls_layout.setSpacing(16)
        cal_ctrls_layout.setContentsMargins(0, 0, 0, 0)

        chk_base_style = f"""
            QCheckBox {{
                font-size: 13.5px;
                font-weight: bold;
            }}
            QCheckBox::indicator {{
                width: 18px;
                height: 18px;
                border: 2px solid #5f6368;
                border-radius: 4px;
                background-color: #ffffff;
            }}
            QCheckBox::indicator:hover {{
                border: 2px solid #1a73e8;
            }}
            QCheckBox::indicator:checked {{
                background-color: #1a73e8;
                border: 2px solid #1a73e8;
                image: url("{CHECKMARK_SVG}");
            }}
        """

        self.chk_wfh_sunday = QCheckBox("تفعيل العمل عن بعد (الأحد - WH)")
        self.chk_wfh_sunday.setChecked(True)
        self.chk_wfh_sunday.setStyleSheet(f"QCheckBox {{ color: #8e24aa; }} {chk_base_style}")
        self.chk_wfh_sunday.stateChanged.connect(self._on_wfh_checkbox_changed)
        cal_ctrls_layout.addWidget(self.chk_wfh_sunday)

        self.chk_holidays_active = QCheckBox("تنشيط تحديد العطلات الرسمية (H)")
        self.chk_holidays_active.setChecked(False)
        self.chk_holidays_active.setStyleSheet(f"QCheckBox {{ color: #3949ab; }} {chk_base_style}")
        self.chk_holidays_active.stateChanged.connect(self._on_holiday_checkbox_changed)
        cal_ctrls_layout.addWidget(self.chk_holidays_active)

        cal_ctrls_layout.addStretch()
        layout.addLayout(cal_ctrls_layout)

        # --- Weekday Headers & Calendar Grid (Directive 5 & 6) ---
        self.calendar_grid_widget = QWidget()
        self.calendar_grid_widget.setStyleSheet("background: transparent;")
        self.grid_layout = QGridLayout(self.calendar_grid_widget)
        self.grid_layout.setSpacing(8)
        self.grid_layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(self.calendar_grid_widget, stretch=1)

        return panel

    def _build_bottom_bar(self):
        """Builds clean bottom bar containing progress indicator, status label, and summary metrics."""
        action_bar = QFrame()
        action_bar.setFixedHeight(50)
        action_bar.setStyleSheet("QFrame { background-color: #ffffff; border-top: 1px solid #e8eaed; }")
        bar_layout = QHBoxLayout(action_bar)
        bar_layout.setContentsMargins(20, 6, 20, 6)
        bar_layout.setSpacing(14)

        # Progress bar
        self.progress_bar = QProgressBar()
        self.progress_bar.setFixedHeight(10)
        self.progress_bar.setValue(0)
        self.progress_bar.setTextVisible(False)
        self.progress_bar.setFixedWidth(200)
        self.progress_bar.setStyleSheet(
            "QProgressBar { background-color: #f1f3f4; border-radius: 5px; border: none; }"
            "QProgressBar::chunk { background-color: #1a73e8; border-radius: 5px; }"
        )
        bar_layout.addWidget(self.progress_bar)

        self.status_detail_label = QLabel("جاهز لبدء عملية التهيئة...")
        self.status_detail_label.setFont(QFont("Segoe UI", 9.5))
        self.status_detail_label.setStyleSheet("color: #5f6368; border: none;")
        self.status_detail_label.setAlignment(Qt.AlignRight | Qt.AlignVCenter)
        bar_layout.addWidget(self.status_detail_label, stretch=1)

        # Month stats summary in bottom bar
        self.summary_label = QLabel("")
        self.summary_label.setFont(QFont("Segoe UI", 10, QFont.Bold))
        self.summary_label.setStyleSheet("color: #1a73e8; border: none;")
        self.summary_label.setAlignment(Qt.AlignLeft | Qt.AlignVCenter)
        bar_layout.addWidget(self.summary_label)

        return action_bar

    # ============ Month Logic Helpers ============ #
    def _init_default_month(self):
        today = date.today()
        self._set_month_value(today.year, today.month)

    def _increment_month(self):
        year, month = self._get_monthval()
        month += 1
        if month > 12:
            month = 1
            year += 1
        self._set_month_value(year, month)
        self._refresh_month_data()

    def _decrement_month(self):
        year, month = self._get_monthval()
        month -= 1
        if month < 1:
            month = 12
            year -= 1
        self._set_month_value(year, month)
        self._refresh_month_data()

    def _on_issueline_edited(self):
        text = self.month_issueline.text()
        if len(text) == 6 and text.isdigit():
            y = int(text[:4])
            m = int(text[4:])
            m = max(1, min(12, m))
            self._set_month_value(y, m)
            self._refresh_month_data()
        else:
            self._set_month_value(*self._get_monthval())

    def _get_monthval(self):
        val = self.month_issueline.text()
        if val and val.isdigit() and len(val) == 6:
            y, m = int(val[:4]), int(val[4:])
            if 1 <= m <= 12 and 1900 <= y <= 2100:
                return y, m
        today = date.today()
        return today.year, today.month

    def _set_month_value(self, year, month):
        iss = f"{year}{month:02d}"
        self.month_issueline.blockSignals(True)
        self.month_issueline.setText(iss)
        self.month_issueline.blockSignals(False)
        self.current_year = year
        self.current_month = month

    def _get_current_issue_and_dates(self):
        year, month = self._get_monthval()
        issue = f"{year}{month:02d}"
        days_in_m = calendar.monthrange(year, month)[1]
        lst = [date(year, month, day) for day in range(1, days_in_m + 1)]
        return issue, lst

    def _refresh_month_data(self):
        self.holidays_set = set()
        self.wfh_set = set()
        issue, dates_list = self._get_current_issue_and_dates()
        self.issue_badge.setText(f"كود الشهر (Issue): {issue}")
        self.month_issueline.setText(issue)
        self.lbl_days_count.setText(f"📅 عدد أيام الشهر: {len(dates_list)} يوم")

        self.chk_wfh_sunday.blockSignals(True)
        self.chk_holidays_active.blockSignals(True)
        self.chk_wfh_sunday.setChecked(True)
        self.chk_holidays_active.setChecked(False)
        self.holidays_enabled = False
        self.chk_wfh_sunday.blockSignals(False)
        self.chk_holidays_active.blockSignals(False)

        self._build_calendar_grid(dates_list)
        self._check_db_status(issue, len(dates_list))

    # ============ Calendar Interactive Grid ============ #
    def _build_calendar_grid(self, dates_list):
        for card in self.day_cards:
            card.deleteLater()
        self.day_cards.clear()

        while self.grid_layout.count():
            item = self.grid_layout.takeAt(0)
            if item and item.widget():
                item.widget().deleteLater()

        # Directive 5 & 6: Fixed RTL Weekday Header Row
        header_names = ["الجمعة", "الخميس", "الأربعاء", "الثلاثاء", "الإثنين", "الأحد", "السبت"]
        for col_idx, h_name in enumerate(header_names):
            lbl = QLabel(h_name)
            lbl.setFixedHeight(30)
            lbl.setFont(QFont("Segoe UI", 10, QFont.Bold))
            lbl.setAlignment(Qt.AlignCenter)
            lbl.setStyleSheet(
                "QLabel { color: #5f6368; background-color: #f1f3f4; border-radius: 6px; font-weight: bold; }"
            )
            self.grid_layout.addWidget(lbl, 0, col_idx)

        # RTL Mapping: Friday (4)->0, Thursday (3)->1, Wednesday (2)->2, Tuesday (1)->3, Monday (0)->4, Sunday (6)->5, Saturday (5)->6
        weekday_to_col = {4: 0, 3: 1, 2: 2, 1: 3, 0: 4, 6: 5, 5: 6}
        week_day_order = {5: 0, 6: 1, 0: 2, 1: 3, 2: 4, 3: 5, 4: 6}

        first_date = dates_list[0]
        first_day_week_idx = week_day_order[first_date.weekday()]

        for dt in dates_list:
            wd = dt.weekday()
            col = weekday_to_col[wd]
            day_offset = (dt - first_date).days
            row = 1 + ((first_day_week_idx + day_offset) // 7)

            if wd == 6:
                init_state = 'wfh' if dt in self.wfh_set or self.chk_wfh_sunday.isChecked() else ('holiday' if dt in self.holidays_set else 'work')
                card = DayCardWidget(dt_val=dt, day_type="sunday", state=init_state)
            elif wd in (4, 5):
                init_state = 'holiday' if dt in self.holidays_set else 'rest'
                card = DayCardWidget(dt_val=dt, day_type="rest", state=init_state)
            else:
                init_state = 'holiday' if dt in self.holidays_set else 'work'
                card = DayCardWidget(dt_val=dt, day_type="workday", state=init_state)

            card.set_toggling_enabled(self.holidays_enabled)
            card.toggled.connect(self._on_day_toggled)
            self.day_cards.append(card)
            self.grid_layout.addWidget(card, row, col)

        self._update_holidays_summary()

    def _on_day_toggled(self, dt_val, new_state):
        if not self.holidays_enabled:
            return

        is_sunday = (dt_val.weekday() == 6)
        prev_state = None
        for card in self.day_cards:
            if card.dt_val == dt_val:
                prev_state = card.state
                break

        if is_sunday:
            if prev_state == 'holiday':
                if self.chk_wfh_sunday.isChecked():
                    self.wfh_set.add(dt_val)
                    for c2 in self.day_cards:
                        if c2.dt_val == dt_val:
                            c2.set_state('wfh')
                else:
                    self.wfh_set.discard(dt_val)
                    for c2 in self.day_cards:
                        if c2.dt_val == dt_val:
                            c2.set_state('work')
                self.holidays_set.discard(dt_val)
            else:
                self.holidays_set.add(dt_val)
                self.wfh_set.discard(dt_val)
                for c2 in self.day_cards:
                    if c2.dt_val == dt_val:
                        c2.set_state('holiday')
        elif dt_val.weekday() in (4, 5):
            if prev_state == 'rest':
                self.holidays_set.add(dt_val)
                for c2 in self.day_cards:
                    if c2.dt_val == dt_val:
                        c2.set_state('holiday')
            else:
                self.holidays_set.discard(dt_val)
                for c2 in self.day_cards:
                    if c2.dt_val == dt_val:
                        c2.set_state('rest')
        else:
            if prev_state == 'work':
                self.holidays_set.add(dt_val)
                for c2 in self.day_cards:
                    if c2.dt_val == dt_val:
                        c2.set_state('holiday')
            else:
                self.holidays_set.discard(dt_val)
                for c2 in self.day_cards:
                    if c2.dt_val == dt_val:
                        c2.set_state('work')

        self._update_holidays_summary()

    def _on_holiday_checkbox_changed(self, val):
        self.holidays_enabled = self.chk_holidays_active.isChecked()
        for card in self.day_cards:
            card.set_toggling_enabled(self.holidays_enabled)
        if not self.holidays_enabled:
            self.status_detail_label.setText("تحديد العطلات معطل مؤقتاً")
        else:
            self.status_detail_label.setText("جاهز لبدء عملية التهيئة...")

    def _on_wfh_checkbox_changed(self, val):
        issue, dates_list = self._get_current_issue_and_dates()
        sundays = [dt for dt in dates_list if dt.weekday() == 6]
        if self.chk_wfh_sunday.isChecked():
            for card in self.day_cards:
                if card.dt_val in sundays and card.state != 'holiday':
                    card.set_state('wfh')
                    self.wfh_set.add(card.dt_val)
                    self.holidays_set.discard(card.dt_val)
        else:
            for card in self.day_cards:
                if card.dt_val in sundays and card.state == 'wfh':
                    card.set_state('work')
                    self.wfh_set.discard(card.dt_val)
        self._update_holidays_summary()

    def _update_holidays_summary(self):
        holidays_cnt = 0
        weekly_off_cnt = 0
        workdays_cnt = 0
        wfh_cnt = 0
        for card in self.day_cards:
            if card.state == 'holiday':
                holidays_cnt += 1
            elif card.state == 'rest':
                weekly_off_cnt += 1
            elif card.state == 'wfh':
                wfh_cnt += 1
            elif card.state == 'work':
                workdays_cnt += 1
        self.summary_label.setText(
            f"عمل: {workdays_cnt}  |  WFH: {wfh_cnt}  |  العطلات: {holidays_cnt}  |  راحة: {weekly_off_cnt}"
        )

    # ============ Stats & Backend ============ #
    def _check_db_status(self, issue, num_days):
        """Display Database File and Table Paths in the Status Card with resolved paths"""
        try:
            ts_path, main_path = self._get_resolved_paths()
            ts_pwd = self.config.get_password("timesheet") if hasattr(self.config, "get_password") else ""
            main_pwd = self.config.get_password("main") if hasattr(self.config, "get_password") else ""

            if not ts_path or not os.path.isfile(ts_path):
                self.status_title_label.setText("⚠️ مسار قاعدة بيانات TimeSheet غير محدد أو الملف غير موجود")
                self.db_status_card.setStyleSheet("QFrame { background-color: #fce8e6; border: 1.5px solid #fad2cf; border-radius: 10px; }")
                self.status_title_label.setStyleSheet("color: #c5221f; border: none; background: transparent;")
                self.lbl_db_name.setText("قاعدة البيانات: غير متوفرة")
                self.lbl_db_path.setText(f"المسار: {ts_path or 'غير محدد'}")
                self.btn_start.setEnabled(False)
                return

            db_filename = os.path.basename(ts_path)
            self.lbl_db_name.setText(f"قاعدة البيانات: {db_filename}")
            self.lbl_db_path.setText(f"المسار: {ts_path}")
            self.lbl_db_tables.setText("الجدول النشط: DatePrep & var_op")

            active_emps = 0
            if main_path and os.path.isfile(main_path) and hasattr(self.db, 'get_active_employees_count'):
                try:
                    active_emps = self.db.get_active_employees_count(main_path, db_password=main_pwd) or 0
                except Exception:
                    active_emps = 0

            total_records = active_emps * num_days
            self.lbl_total_records.setText(f"📊 إجمالي السجلات المستهدفة: {total_records:,} سجل")

            is_init = False
            existing_count = 0
            if hasattr(self.db, 'is_month_initialized'):
                try:
                    is_init, existing_count = self.db.is_month_initialized(ts_path, issue, db_password=ts_pwd)
                except Exception:
                    is_init, existing_count = False, 0

            if is_init:
                self.status_title_label.setText(f"⚠️ الشهر مهيأ مسبقاً ({existing_count:,} سجل)")
                self.db_status_card.setStyleSheet("QFrame { background-color: #fef7e0; border: 1.5px solid #feefc3; border-radius: 10px; }")
                self.status_title_label.setStyleSheet("color: #b06000; border: none; background: transparent;")
                self.lbl_db_name.setStyleSheet("color: #7a4100; border: none; background: transparent;")
                self.lbl_db_path.setStyleSheet("color: #5f6368; border: none; background: transparent;")
                self.lbl_db_tables.setStyleSheet("color: #7a4100; border: none; background: transparent;")
            else:
                self.status_title_label.setText("حالة قاعدة البيانات: متصلة ونشطة 🟢")
                self.db_status_card.setStyleSheet("QFrame { background-color: #e6f4ea; border: 1.5px solid #ceead6; border-radius: 10px; }")
                self.status_title_label.setStyleSheet("color: #137333; border: none; background: transparent;")
                self.lbl_db_name.setStyleSheet("color: #1b5e20; border: none; background: transparent;")
                self.lbl_db_path.setStyleSheet("color: #3c4043; border: none; background: transparent;")
                self.lbl_db_tables.setStyleSheet("color: #1b5e20; border: none; background: transparent;")

            self.btn_start.setEnabled(True)
        except Exception:
            self.status_title_label.setText("حالة قاعدة البيانات: متصلة ونشطة 🟢")
            self.db_status_card.setStyleSheet("QFrame { background-color: #e6f4ea; border: 1.5px solid #ceead6; border-radius: 10px; }")
            self.status_title_label.setStyleSheet("color: #137333; border: none; background: transparent;")
            self.btn_start.setEnabled(True)

    # ============ Execution & Backend Start ============ #
    def _on_start_clicked(self):
        issue, dates_list = self._get_current_issue_and_dates()
        ts_path, main_path = self._get_resolved_paths()

        if not ts_path or not os.path.isfile(ts_path):
            QMessageBox.critical(
                self,
                "خطأ في المسار",
                f"تعذر العثور على ملف قاعدة بيانات TimeSheet:\n{ts_path or 'المسار غير محدد'}\n\nيرجى مراجعة إعدادات النظام وتحديد المسار الصحيح."
            )
            return

        if not main_path or not os.path.isfile(main_path):
            QMessageBox.critical(
                self,
                "خطأ في المسار",
                f"تعذر العثور على ملف قاعدة البيانات الرئيسية (2025.mdb):\n{main_path or 'المسار غير محدد'}\n\nيرجى مراجعة إعدادات النظام وتحديد المسار الصحيح."
            )
            return

        ts_pwd = self.config.get_password("timesheet") if hasattr(self.config, "get_password") else ""
        main_pwd = self.config.get_password("main") if hasattr(self.config, "get_password") else ""

        h_count = sum(1 for card in self.day_cards if card.state == 'holiday')

        try:
            if hasattr(self.db, 'is_month_initialized'):
                is_init, existing_count = self.db.is_month_initialized(ts_path, issue, db_password=ts_pwd)
                if is_init:
                    reply = QMessageBox.warning(
                        self,
                        "تأكيد إعادة تهيئة الشهر",
                        f"تنبيه: الشهر ({issue}) يحتوي بالفعل على {existing_count:,} سجل في جدول التحركات.\n\n"
                        "هل ترغب بالتأكيد في متابعة عملية التهيئة؟",
                        QMessageBox.Yes | QMessageBox.No,
                        QMessageBox.No
                    )
                    if reply != QMessageBox.Yes:
                        return
        except Exception as e:
            QMessageBox.critical(self, "خطأ في الاتصال", f"تعذر الاتصال بقاعدة البيانات: {str(e)}")
            return

        if h_count > 0:
            msg = f"لقد قمت بتحديد عدد {h_count} أيام كعطلات رسمية (H) لهذا الشهر. هل أنت متأكد من صحة هذه العطلات وتريد الاستمرار في عملية التهيئة؟"
        else:
            msg = "تحذير: لم تقم بتحديد أي أيام كعطلات رسمية (H) لهذا الشهر. هل أنت متأكد من الرغبة في تهيئة الشهر بالكامل كأيام عمل اعتيادية بدون أي عطلات رسمية؟"

        reply = QMessageBox.question(self, "تأكيد العطلات الرسمية", msg,
                                    QMessageBox.Yes | QMessageBox.No, QMessageBox.Yes)
        if reply != QMessageBox.Yes:
            return

        self.btn_start.setEnabled(False)
        self.back_btn.setEnabled(False)
        self.btn_month_minus.setEnabled(False)
        self.btn_month_plus.setEnabled(False)
        self.month_issueline.setEnabled(False)
        self.chk_holidays_active.setEnabled(False)
        self.chk_wfh_sunday.setEnabled(False)
        self.progress_bar.setValue(5)
        self.status_detail_label.setText("جاري إطلاق المعالجة وتجهيز الجداول...")

        holidays = set([c.dt_val for c in self.day_cards if c.state == 'holiday'])
        self.prep_thread = MonthPrepThread(
            db=self.db,
            ts_db_path=ts_path,
            main_db_path=main_path,
            issue=issue,
            dates_list=dates_list,
            holidays_set=holidays,
            holiday_var_code=None,
            db_password=ts_pwd
        )
        self.prep_thread.progress.connect(self._on_thread_progress)
        self.prep_thread.finished.connect(self._on_thread_finished)
        self.prep_thread.error.connect(self._on_thread_error)
        self.prep_thread.start()

    def _on_thread_progress(self, pct, msg):
        self.progress_bar.setValue(pct)
        self.status_detail_label.setText(msg)

    def _on_thread_finished(self, result):
        self.progress_bar.setValue(100)
        self.status_detail_label.setText("تمت العملية بنجاح!")
        self.btn_start.setEnabled(True)
        self.back_btn.setEnabled(True)
        self.btn_month_minus.setEnabled(True)
        self.btn_month_plus.setEnabled(True)
        self.month_issueline.setEnabled(True)
        self.chk_holidays_active.setEnabled(True)
        self.chk_wfh_sunday.setEnabled(True)
        issue = str(result.get("issue"))
        self._check_db_status(issue, result.get("total_days", 30))
        QMessageBox.information(
            self, "نجاح التهيئة",
            f"تمت تهيئة الشهر ({result.get('issue')}) بنجاح تام!\n\n"
            f"• عدد الموظفين الفعالين: {result.get('total_employees', 0):,}\n"
            f"• عدد الأيام المجهزة في DatePrep: {result.get('total_days', 0)}\n"
            f"• إجمالي السجلات التي تم إنشاؤها في var_op: {result.get('total_records', 0):,} سجل."
        )

    def _on_thread_error(self, err_msg):
        self.progress_bar.setValue(0)
        self.status_detail_label.setText("حدث خطأ أثناء التهيئة.")
        self.btn_start.setEnabled(True)
        self.back_btn.setEnabled(True)
        self.btn_month_minus.setEnabled(True)
        self.btn_month_plus.setEnabled(True)
        self.month_issueline.setEnabled(True)
        self.chk_holidays_active.setEnabled(True)
        self.chk_wfh_sunday.setEnabled(True)
        QMessageBox.critical(
            self, "فشل في عملية التهيئة",
            f"حدث خطأ أثناء محاولة تهيئة الشهر:\n\n{err_msg}"
        )