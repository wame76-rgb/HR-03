# -*- coding: utf-8 -*-
"""
شاشة تهيئة بداية الشهر - نظام إدارة الموارد البشرية
التاريخ: 2026-08-24
سجل التعديلات:
- v1.0.0: الشاشة الأساسية وتجهيز التقويم وربط الخيوط.
- v1.1.0: إصلاح صريح وحاسم لمسارات قواعد البيانات (Path Resolution Fix).
- v2.0.0 (HR-03): إعادة تصميم شاملة وفق المواصفات:
  1. إصلاح انهيار ODBC (HY000) وانتهاك القيد الرئيسي (EmpId + EntryDate):
     فحص مسبق صامت، رسالة تأكيد إعادة التهيئة، حذف آمن، وإدراج مجزأ بدفعات
     صغيرة (200 صف) عبر execute_with_retry.
  2. تحويل انتقائي: فقط H / R / WH تُعبأ، وأيام العمل العادية تبقى 0.
  3. حارس الجمعة/السبت/الأحد: حفظ التعديلات اليدوية غير الصفرية دون الكتابة فوقها.
  4. تخطيط RTL: التقويم يميناً، وسجل الإخراج/حالة الاتصال/الأزرار يساراً.
  5. شبكة تقويم على نمط Excel بخطوط رفيعة #D1D5DB تبدأ من الأحد أقصى اليمين.
  6. خانتا اختيار برسالة (علامة) واضحة بدلاً من تظليل الخلفية.
- v2.2.0 (HR-03 Grid Overhaul): تحويل التقويم إلى QTableWidget حقيقي 7x7 برؤوس
  مخفية وأسماء الأيام داخل الصف 0، تلوين العمود كاملاً (أحد موف / جمعة وسبت أحمر)،
  خلايا بنص عادي متعدد الأسطر، إزالة كل QFrame/صناديق فرعية وزوايا دائرية،
  واستعادة أنماط QMessageBox النظامية الافتراضية عالية التباين.
"""

import os
import calendar
import tempfile
from datetime import date, datetime

from PySide6.QtWidgets import (
    QMainWindow, QWidget, QVBoxLayout, QHBoxLayout, QLabel,
    QPushButton, QLineEdit, QListWidget, QListWidgetItem, QMessageBox,
    QFrame, QCheckBox, QProgressBar, QTableWidget, QTableWidgetItem,
    QAbstractItemView, QHeaderView
)
from PySide6.QtCore import Qt, QThread, Signal, QRectF, QRect
from PySide6.QtGui import QFont, QColor, QPainter, QPainterPath, QImage, QPen, QBrush, QIcon

from db_connection import DatabaseConnection

# BASE_DIR Resolution (مجلد hr_system نفسه)
BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


# ======================================================================
# دوال مساعدة للتصميم
# ======================================================================

def make_checkmark_png(color_hex):
    """توليد صورة علامة صح (box + ✔) ملوّنة بمسار مؤقت لاستخدامها في خانة الاختيار."""
    file_path = os.path.join(tempfile.gettempdir(), f"hr_check_{color_hex.lstrip('#')}.png")
    if os.path.exists(file_path):
        return file_path.replace("\\", "/")

    box = 20
    img = QImage(box, box, QImage.Format_ARGB32)
    img.fill(Qt.transparent)
    painter = QPainter(img)
    painter.setRenderHint(QPainter.Antialiasing, True)

    color = QColor(color_hex)
    painter.setPen(QPen(color, 2))
    painter.setBrush(QBrush(QColor("#ffffff")))
    painter.drawRoundedRect(QRectF(1, 1, box - 2, box - 2), 4, 4)

    painter.setPen(QPen(color, 3, Qt.SolidLine, Qt.RoundCap, Qt.RoundJoin))
    path = QPainterPath()
    path.moveTo(4, box * 0.55)
    path.lineTo(box * 0.42, box * 0.78)
    path.lineTo(box * 0.82, box * 0.26)
    painter.drawPath(path)
    painter.end()

    img.save(file_path, "PNG")
    return file_path.replace("\\", "/")


def checkbox_stylesheet(color_hex, check_png):
    """ورقة أنماط خانة الاختيار: إطار ملوّن وعلامة صح واضحة داخل الصندوق دون تظليل الخلفية."""
    return f"""
        QCheckBox {{
            color: #202124; font-weight: bold; spacing: 8px;
            background: transparent;
        }}
        QCheckBox::indicator {{
            width: 20px; height: 20px;
            border: 2px solid {color_hex};
            border-radius: 5px; background: #ffffff;
        }}
        QCheckBox::indicator:hover {{ background: #f8f9fa; }}
        QCheckBox::indicator:checked {{
            background: #ffffff; border: 2px solid {color_hex};
            image: url({check_png});
        }}
    """


def translate_odbc_error(error_msg):
    """ترجمة الأخطاء التقنية الشائعة إلى عربية احترافية واضحة مع إبقاء الخطأ الأصلي."""
    msg = (error_msg or "").lower()
    if not msg.strip():
        return "حدث خطأ غير معروف أثناء العملية."
    if "primary key" in msg or "unique" in msg or "duplicate" in msg or "constraint" in msg:
        return ("انتهاك القيد الرئيسي (EmpId + EntryDate): سجل مكرر في جدول var_op. "
                "تمت معالجة الحذف المسبق تلقائياً، حاول مرة أخرى.")
    if "hy000" in msg or "driver did not supply" in msg:
        return ("خطأ من برنامج تشغيل Access (HY000): \"The driver did not supply an error!\". "
                "أغلق أي نافذة Access تفتح الملف نفسه، ثم أعد المحاولة بعد لحظات.")
    if "locked" in msg or "busy" in msg or "could not use" in msg or "record" in msg:
        return ("ملف قاعدة البيانات مقفل أو قيد الاستخدام من برنامج آخر. "
                "أغلق ملف Access من أي نافذة مفتوحة ثم أعد المحاولة.")
    if "could not find" in msg or "file not found" in msg or "dbq" in msg:
        return "تعذر العثور على ملف قاعدة البيانات المحدد في المسار المُعد."
    if "timeout" in msg:
        return "انتهت مهلة الاتصال بقاعدة البيانات. تأكد من سلامة الشبكة أو المسار."
    if "password" in msg or "pwd" in msg:
        return "كلمة مرور قاعدة البيانات غير صحيحة أو غير مشفرة بشكل سليم."
    return error_msg


# ======================================================================
# خيط الفحص المسبق (Pre-Check) — لا يجمد الواجهة
# ======================================================================

class MonthPreCheckThread(QThread):
    """فحص مسبق صامت: هل الشهر مُهيأ مسبقاً؟ وهل كل أيامه موجودة في var_op؟"""
    pre_check_result = Signal(bool, bool, int, set, str)

    def __init__(self, db_helper, ts_path, ts_pwd, issue, parent=None):
        super().__init__(parent)
        self.db = db_helper
        self.ts_path = ts_path
        self.ts_pwd = ts_pwd
        self.issue = issue

    def run(self):
        try:
            count, present_days = self.db.pre_check_month(self.ts_path, self.issue, self.ts_pwd)
            self.pre_check_result.emit(True, count > 0, count, present_days, "")
        except Exception as e:
            self.pre_check_result.emit(False, False, 0, set(), str(e))


# ======================================================================
# خيط المعالجة الخلفية للتهيئة المليونية
# ======================================================================

class MonthPrepThread(QThread):
    """خيط مستقل لتنفيذ عملية تهيئة الشهر دون تجميد الواجهة (حذف آمن + إدراج مجزأ)."""
    progress_updated = Signal(int)
    status_updated = Signal(str)
    initialization_completed = Signal(int, int)  # (employees, records)
    initialization_failed = Signal(str)

    def __init__(self, db_helper, main_path, ts_path, main_pwd, ts_pwd,
                 year, month, issue, num_days, wfh_active, holidays_list, parent=None):
        super().__init__(parent)
        self.db = db_helper
        self.main_path = main_path
        self.ts_path = ts_path
        self.main_pwd = main_pwd
        self.ts_pwd = ts_pwd
        self.year = year
        self.month = month
        self.issue = issue
        self.num_days = num_days
        self.wfh_active = wfh_active
        self.holidays_list = holidays_list  # قائمة أرقام الأيام (integers)

    def run(self):
        try:
            self.status_updated.emit("جارٍ الاتصال بقواعد البيانات...")

            # قراءة رموز المتغيرات من جدول variables
            self.status_updated.emit("جارٍ قراءة رموز المتغيرات (R / WH / H)...")
            code_map = {}
            for v in self.db.get_variables(self.ts_path, self.ts_pwd):
                key = str(v.get('var', '')).strip().upper()
                if key in ('R', 'WH', 'H'):
                    code_map[key] = int(v['code'])
            code_map.setdefault('R', 5)
            code_map.setdefault('WH', 35)
            code_map.setdefault('H', 4)

            dates_list = [date(self.year, self.month, day) for day in range(1, self.num_days + 1)]
            holidays_set = {date(self.year, self.month, d) for d in self.holidays_list}

            def progress(pct, msg):
                self.progress_updated.emit(pct)
                self.status_updated.emit(msg)

            self.status_updated.emit("جارٍ تنفيذ التهيئة الآمنة (حذف الشهر + إدراج مجزأ بدفعات 200)...")
            result = self.db.initialize_month_records(
                ts_db_path=self.ts_path,
                main_db_path=self.main_path,
                issue=self.issue,
                dates_list=dates_list,
                code_map=code_map,
                holidays_set=holidays_set,
                wfh_active=self.wfh_active,
                preserve_weekend_overrides=True,
                batch_size=200,
                main_db_password=self.main_pwd,
                ts_db_password=self.ts_pwd,
                interrupt_check=lambda: self.isInterruptionRequested(),
                progress_callback=progress,
            )

            self.initialization_completed.emit(result['total_employees'], result['total_records'])

        except InterruptedError as e:
            self.initialization_failed.emit(str(e))
        except Exception as e:
            self.initialization_failed.emit(str(e))


# ======================================================================
# الشاشة الرئيسية
# ======================================================================

class DayCardWidget(QFrame):
    """خلية يوم في شبكة Excel المتصلة — لون العمود كاملاً في كتلة نص واحدة بدون صناديق فرعية."""
    def __init__(self, day_num, day_type, parent_window):
        super().__init__()
        self.day_num = day_num
        self.day_type = day_type  # 'WORK', 'REST', 'WH', 'HOLIDAY'
        self.parent_window = parent_window
        self.init_ui()

    def init_ui(self):
        self.setFrameShape(QFrame.NoFrame)
        self.setFixedSize(96, 62)

        self.layout = QVBoxLayout(self)
        self.layout.setContentsMargins(2, 4, 2, 2)
        self.layout.setSpacing(0)

        self.text_label = QLabel("", self)
        self.text_label.setAlignment(Qt.AlignCenter)
        self.layout.addWidget(self.text_label)

        self.apply_state_style()

    def apply_state_style(self):
        """تلوين الخلية حسب العمود: كتلة نص واحدة (رقم اليوم فوق + الكود أسفله) بخط كبير عريض."""
        if self.day_type == 'HOLIDAY':
            bg, day_color, code, code_color = "#E0F2FE", "#1F2937", "H", "#0369A1"
        elif self.day_type == 'REST':
            bg, day_color, code, code_color = "#FFEAEA", "#1F2937", "R", "#991B1B"
        elif self.day_type == 'WH':
            bg, day_color, code, code_color = "#F3E5F5", "#8E24AA", "WH", "#8E24AA"
        else:
            bg, day_color, code, code_color = "#FFFFFF", "#1F2937", "", "#1F2937"

        self.setStyleSheet(
            f"DayCardWidget {{ background-color: {bg}; border: 1px solid #D1D5DB; }}"
        )
        if code:
            html = (f"<div style='font-size:20pt; font-weight:bold; color:{day_color};'>{self.day_num}</div>"
                    f"<div style='font-size:15pt; font-weight:bold; color:{code_color};'>{code}</div>")
        else:
            html = (f"<div style='font-size:20pt; font-weight:bold; color:{day_color};'>{self.day_num}</div>")
        self.text_label.setText(html)

    def default_type(self):
        """الحالة الافتراضية للعمود حسب يوم الأسبوع."""
        current_date = datetime(self.parent_window.current_year,
                                self.parent_window.current_month, self.day_num)
        dow = current_date.weekday()
        if dow in (4, 5):
            return 'REST'
        if dow == 6:
            return 'WH' if self.parent_window.wfh_chk.isChecked() else 'WORK'
        return 'WORK'

    def mousePressEvent(self, event):
        """فتح كل الخلايا للتبديل إلى عطلة (H) بضغطة واحدة عند تفعيل خانة العطلات الرسمية."""
        if event.button() != Qt.LeftButton:
            return
        if not self.parent_window.holidays_chk.isChecked():
            return

        if self.day_type == 'HOLIDAY':
            self.day_type = self.default_type()
        else:
            self.day_type = 'HOLIDAY'

        self.apply_state_style()
        self.parent_window.update_statistics()


# ======================================================================
# الشاشة الرئيسية
# ======================================================================

class MonthPrepWindow(QMainWindow):
    """الشاشة الكاملة لتهيئة بداية الشهر (HR-03) — التقويم يميناً والتحكم يساراً."""
    def __init__(self, config_manager, db_connection, user_data, parent=None):
        super().__init__(parent)
        self.config = config_manager
        self.db = db_connection
        self.user_data = user_data or {}

        # إعدادات التاريخ الحالية
        now = datetime.now()
        self.current_year = now.year
        self.current_month = now.month

        # استرجاع المسارات بأمان من قسم DATABASE
        self.ts_path = self.config.config.get('DATABASE', 'timesheet', fallback='')
        self.main_path = self.config.config.get('DATABASE', 'main', fallback='')

        # تحويل المسارات إلى مسارات مطلقة نسبةً إلى BASE_DIR
        if self.ts_path and not os.path.isabs(self.ts_path):
            self.ts_path = os.path.join(BASE_DIR, self.ts_path).replace("\\", "/")
        if self.main_path and not os.path.isabs(self.main_path):
            self.main_path = os.path.join(BASE_DIR, self.main_path).replace("\\", "/")

        self.ts_pwd = self.config.get_password('timesheet')
        self.main_pwd = self.config.get_password('main')

        self.day_cells = {}
        self.day_types = {}
        self.coord_to_day = {}
        self.worker_thread = None
        self.pre_check_thread = None

        self.init_ui()
        self.refresh_connection_status()

    # ------------------------------------------------------------------
    # البناء البصري
    # ------------------------------------------------------------------
    def init_ui(self):
        self.setWindowTitle("تهيئة الشهر الجديد")
        self.resize(1200, 780)
        self.setLayoutDirection(Qt.RightToLeft)
        self.setStyleSheet("font-family: 'Segoe UI';")

        # أيقونة النافذة من مجلد الأصول (مع تحقق آمن من المسار)
        icon_path = os.path.join(BASE_DIR, "assests", "logo.png")
        if not os.path.exists(icon_path):
            icon_path = os.path.join(BASE_DIR, "assets", "logo.png")
        if os.path.exists(icon_path):
            self.setWindowIcon(QIcon(icon_path))

        if self.statusBar():
            self.statusBar().setSizeGripEnabled(False)

        self.central_widget = QWidget(self)
        self.central_widget.setStyleSheet("background-color: #FAFBFC;")
        self.setCentralWidget(self.central_widget)
        self.main_layout = QHBoxLayout(self.central_widget)
        self.main_layout.setContentsMargins(18, 18, 18, 18)
        self.main_layout.setSpacing(18)

        # ------------------------------------------
        # يميناً: لوحة التقويم (Calendar)
        # ------------------------------------------
        self.calendar_pane = QWidget(self)
        self.calendar_layout = QVBoxLayout(self.calendar_pane)
        self.calendar_layout.setContentsMargins(0, 0, 0, 0)
        self.calendar_layout.setSpacing(12)

        # شريط الشهر المستهدف: صندوق الشهر (MM-YYYY) + أزرار +/- + إحصائيات الشهر
        self.month_bar = QFrame(self)
        self.month_bar.setStyleSheet("""
            QFrame { background-color: #FFFFFF; border: 1px solid #DADCE0; border-radius: 8px; }
        """)
        self.month_bar_layout = QHBoxLayout(self.month_bar)
        self.month_bar_layout.setContentsMargins(12, 10, 12, 10)
        self.month_bar_layout.setSpacing(0)  # صفر مسافة: الأزرار ملاصقة تماماً لصندوق الشهر

        self.btn_dec_month = QPushButton("-", self)
        self.btn_dec_month.setFixedSize(34, 34)
        self.btn_dec_month.setFont(QFont("Segoe UI", 15, QFont.Bold))
        self.btn_dec_month.setStyleSheet("""
            QPushButton { background-color: #F8F9FA; border: 1px solid #DADCE0;
                          border-radius: 5px; color: #202124; }
            QPushButton:hover { background-color: #E8EAED; }
            QPushButton:pressed { background-color: #DADCE0; }
        """)
        self.btn_dec_month.clicked.connect(self.decrement_month)
        self.month_bar_layout.addWidget(self.btn_dec_month)

        self.month_input = QLineEdit(self)
        self.month_input.setReadOnly(True)
        self.month_input.setAlignment(Qt.AlignCenter)
        self.month_input.setFont(QFont("Segoe UI", 14, QFont.Bold))
        self.month_input.setFixedSize(140, 34)
        self.month_input.setStyleSheet(
            "border: 1px solid #DADCE0; border-radius: 5px;"
            "background-color: #FFFFFF; color: #111827;"
        )
        self.month_bar_layout.addWidget(self.month_input)

        self.btn_inc_month = QPushButton("+", self)
        self.btn_inc_month.setFixedSize(34, 34)
        self.btn_inc_month.setFont(QFont("Segoe UI", 15, QFont.Bold))
        self.btn_inc_month.setStyleSheet("""
            QPushButton { background-color: #F8F9FA; border: 1px solid #DADCE0;
                          border-radius: 5px; color: #202124; }
            QPushButton:hover { background-color: #E8EAED; }
            QPushButton:pressed { background-color: #DADCE0; }
        """)
        self.btn_inc_month.clicked.connect(self.increment_month)
        self.month_bar_layout.addWidget(self.btn_inc_month)

        # المساحة المتبقية: إحصائيات الشهر المستهدف
        self.month_bar_layout.addSpacing(18)
        self.stats_title = QLabel("إحصائيات الشهر المستهدف", self)
        self.stats_title.setFont(QFont("Segoe UI", 11, QFont.Bold))
        self.stats_title.setStyleSheet("color: #111827; border: none;")
        self.month_bar_layout.addWidget(self.stats_title)
        self.month_bar_layout.addSpacing(6)

        self.lbl_stat_work = QLabel("عمل: -", self)
        self.lbl_stat_work.setFont(QFont("Segoe UI", 10, QFont.Bold))
        self.lbl_stat_work.setStyleSheet("color: #1F2937; border: none; padding: 2px 8px;"
                                         "background-color: #F3F4F6; border-radius: 4px;")
        self.month_bar_layout.addWidget(self.lbl_stat_work)

        self.lbl_stat_rest = QLabel("راحة R: -", self)
        self.lbl_stat_rest.setFont(QFont("Segoe UI", 10, QFont.Bold))
        self.lbl_stat_rest.setStyleSheet("color: #991B1B; border: none; padding: 2px 8px;"
                                         "background-color: #FFEAEA; border-radius: 4px;")
        self.month_bar_layout.addWidget(self.lbl_stat_rest)

        self.lbl_stat_wh = QLabel("WH: -", self)
        self.lbl_stat_wh.setFont(QFont("Segoe UI", 10, QFont.Bold))
        self.lbl_stat_wh.setStyleSheet("color: #8E24AA; border: none; padding: 2px 8px;"
                                       "background-color: #F3E5F5; border-radius: 4px;")
        self.month_bar_layout.addWidget(self.lbl_stat_wh)

        self.lbl_stat_h = QLabel("عطلة H: -", self)
        self.lbl_stat_h.setFont(QFont("Segoe UI", 10, QFont.Bold))
        self.lbl_stat_h.setStyleSheet("color: #0369A1; border: none; padding: 2px 8px;"
                                      "background-color: #E0F2FE; border-radius: 4px;")
        self.month_bar_layout.addWidget(self.lbl_stat_h)

        self.month_bar_layout.addStretch(1)
        self.calendar_layout.addWidget(self.month_bar)

        # شريط خانات الاختيار
        self.control_bar = QFrame(self)
        self.control_bar.setStyleSheet(
            "QFrame { background-color: #FFFFFF; border: 1px solid #DADCE0; border-radius: 8px; }"
        )
        self.bar_layout = QHBoxLayout(self.control_bar)
        self.bar_layout.setContentsMargins(12, 8, 12, 8)
        self.bar_layout.setSpacing(24)

        check_wh_png = make_checkmark_png("#8E24AA")
        check_h_png = make_checkmark_png("#0369A1")

        self.wfh_chk = QCheckBox("العمل عن بعد", self)
        self.wfh_chk.setChecked(True)
        self.wfh_chk.setStyleSheet(checkbox_stylesheet("#8E24AA", check_wh_png))
        self.wfh_chk.stateChanged.connect(self.on_wfh_state_changed)
        self.bar_layout.addWidget(self.wfh_chk)

        self.holidays_chk = QCheckBox("العطلات الرسمية", self)
        self.holidays_chk.setChecked(False)
        self.holidays_chk.setStyleSheet(checkbox_stylesheet("#0369A1", check_h_png))
        self.bar_layout.addWidget(self.holidays_chk)

        self.bar_layout.addStretch(1)
        self.calendar_layout.addWidget(self.control_bar)

        # جدول التقويم Excel 7x7 (رؤوس مخفية — أسماء الأيام داخل الصف 0، بلا صناديق فرعية)
        self.calendar_table = QTableWidget(7, 7, self)
        self.calendar_table.setLayoutDirection(Qt.RightToLeft)
        self.calendar_table.horizontalHeader().setVisible(False)
        self.calendar_table.verticalHeader().setVisible(False)
        self.calendar_table.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        self.calendar_table.verticalHeader().setSectionResizeMode(QHeaderView.Stretch)
        self.calendar_table.setShowGrid(True)
        self.calendar_table.setStyleSheet("""
            QTableWidget {
                background-color: #FFFFFF; border: 1px solid #D1D5DB;
                gridline-color: #D1D5DB;
            }
        """)
        self.calendar_table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.calendar_table.setSelectionMode(QAbstractItemView.NoSelection)
        self.calendar_table.setFocusPolicy(Qt.NoFocus)
        self.calendar_table.setVerticalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.calendar_table.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.calendar_table.setFont(QFont("Segoe UI", 12, QFont.Bold))
        self.calendar_table.cellClicked.connect(self.on_cell_clicked)

        self.calendar_layout.addWidget(self.calendar_table, 1)

        # --------------------------------------------------
        # يساراً: سجل الإخراج + حالة الاتصال + الأزرار
        # --------------------------------------------------
        self.controls_pane = QWidget(self)
        self.controls_pane.setFixedWidth(360)
        self.controls_layout = QVBoxLayout(self.controls_pane)
        self.controls_layout.setContentsMargins(0, 0, 0, 0)
        self.controls_layout.setSpacing(14)

        # كارت حالة قاعدة البيانات
        self.status_card = QFrame(self)
        self.status_card.setStyleSheet(
            "QFrame { background-color: #E8F5E9; border: 1px solid #C8E6C9; border-radius: 8px; }"
        )
        self.status_layout = QVBoxLayout(self.status_card)
        self.status_layout.setContentsMargins(14, 12, 14, 12)
        self.status_layout.setSpacing(6)

        self.lbl_status_indicator = QLabel("حالة قاعدة البيانات: جارٍ التحقق...", self)
        self.lbl_status_indicator.setFont(QFont("Segoe UI", 11, QFont.Bold))
        self.lbl_status_indicator.setStyleSheet("color: #1B5E20; border: none;")
        self.status_layout.addWidget(self.lbl_status_indicator)

        self.lbl_db_details = QLabel(self)
        self.lbl_db_details.setFont(QFont("Segoe UI", 10))
        self.lbl_db_details.setStyleSheet("color: #2E7D32; line-height: 18px; border: none;")
        self.lbl_db_details.setWordWrap(True)
        db_file_name = os.path.basename(self.ts_path) if self.ts_path else "TIME SHEET.mdb"
        self.lbl_db_details.setText(
            f"<b>قاعدة البيانات:</b> {db_file_name}<br>"
            f"<b>المسار الفعلي:</b> {self.ts_path}<br>"
            f"<b>الجدول النشط:</b> DatePrep &amp; var_op"
        )
        self.status_layout.addWidget(self.lbl_db_details)
        self.controls_layout.addWidget(self.status_card)

        # سجل الإخراج
        log_title = QLabel("سجل الإخراج", self)
        log_title.setFont(QFont("Segoe UI", 11, QFont.Bold))
        log_title.setStyleSheet("color: #111827;")
        self.controls_layout.addWidget(log_title)

        self.output_log = QListWidget(self)
        self.output_log.setStyleSheet("""
            QListWidget {
                background-color: #FFFFFF; border: 1px solid #DADCE0; border-radius: 8px;
                color: #202124; font-size: 10pt; padding: 4px;
            }
            QListWidget::item { padding: 3px; border-bottom: 1px solid #F1F3F4; }
        """)
        self.controls_layout.addWidget(self.output_log, 1)

        # شريط التقدم وحالة الخيط
        self.progress_bar = QProgressBar(self)
        self.progress_bar.setVisible(False)
        self.progress_bar.setStyleSheet("""
            QProgressBar {
                border: 1px solid #DADCE0; border-radius: 6px; text-align: center;
                background-color: #FFFFFF; color: #202124;
            }
            QProgressBar::chunk { background-color: #34A853; border-radius: 5px; }
        """)
        self.controls_layout.addWidget(self.progress_bar)

        self.lbl_thread_status = QLabel("", self)
        self.lbl_thread_status.setFont(QFont("Segoe UI", 10))
        self.lbl_thread_status.setStyleSheet("color: #5F6368;")
        self.lbl_thread_status.setAlignment(Qt.AlignCenter)
        self.lbl_thread_status.setVisible(False)
        self.controls_layout.addWidget(self.lbl_thread_status)

        self.controls_layout.addStretch()

        # زر التهيئة (أخضر زمردي)
        self.btn_initialize = QPushButton("التهيئة", self)
        self.btn_initialize.setFont(QFont("Segoe UI", 11, QFont.Bold))
        self.btn_initialize.setFixedHeight(46)
        self.btn_initialize.setStyleSheet("""
            QPushButton {
                background-color: #059669; color: #FFFFFF; border: none; border-radius: 6px;
            }
            QPushButton:hover { background-color: #047857; }
            QPushButton:pressed { background-color: #065F46; }
            QPushButton:disabled { background-color: #A7F3D0; color: #ECFDF5; }
        """)
        self.btn_initialize.clicked.connect(self.trigger_initialization)
        self.controls_layout.addWidget(self.btn_initialize)

        # زر الرجوع (أحمر نابض)
        self.btn_back = QPushButton("الرجوع", self)
        self.btn_back.setFont(QFont("Segoe UI", 11, QFont.Bold))
        self.btn_back.setFixedHeight(46)
        self.btn_back.setStyleSheet("""
            QPushButton {
                background-color: #DC2626; color: #FFFFFF; border: none; border-radius: 6px;
            }
            QPushButton:hover { background-color: #B91C1C; }
            QPushButton:pressed { background-color: #991B1B; }
            QPushButton:disabled { background-color: #FCA5A5; color: #FEF2F2; }
        """)
        self.btn_back.clicked.connect(self.close)
        self.controls_layout.addWidget(self.btn_back)

        # ترتيب الألواح: التقويم يميناً (يُضاف أولاً في RTL) والتحكم يساراً
        self.main_layout.addWidget(self.calendar_pane, 3)
        self.main_layout.addWidget(self.controls_pane)

        self.update_month_display()

    # ------------------------------------------------------------------
    # حالة الاتصال
    # ------------------------------------------------------------------
    def refresh_connection_status(self):
        try:
            ok, msg = self.db.test_connection(self.ts_path, self.ts_pwd)
            if ok:
                self.lbl_status_indicator.setText("حالة قاعدة البيانات: متصلة ونشطة 🟢")
                self.lbl_status_indicator.setStyleSheet("color: #1B5E20; border: none;")
                self.status_card.setStyleSheet(
                    "QFrame { background-color: #E8F5E9; border: 1px solid #C8E6C9; border-radius: 8px; }"
                )
            else:
                self.lbl_status_indicator.setText("حالة قاعدة البيانات: غير متصلة 🔴")
                self.lbl_status_indicator.setStyleSheet("color: #B71C1C; border: none;")
                self.status_card.setStyleSheet(
                    "QFrame { background-color: #FDECEA; border: 1px solid #F5C6C0; border-radius: 8px; }"
                )
        except Exception as e:
            self.lbl_status_indicator.setText("حالة قاعدة البيانات: غير متصلة 🔴")
            self.lbl_status_indicator.setStyleSheet("color: #B71C1C; border: none;")
            self.status_card.setStyleSheet(
                "QFrame { background-color: #FDECEA; border: 1px solid #F5C6C0; border-radius: 8px; }"
            )
            self.append_log(f"فشل اختبار الاتصال: {e}")

    def append_log(self, text):
        item = QListWidgetItem(f"[{datetime.now().strftime('%H:%M:%S')}] {text}")
        self.output_log.addItem(item)
        self.output_log.scrollToBottom()

    # ------------------------------------------------------------------
    # التنقل بين الشهور
    # ------------------------------------------------------------------
    def update_month_display(self):
        self.issue = f"{self.current_year}{self.current_month:02d}"
        self.month_input.setText(f"{self.current_year}-{self.current_month:02d}")
        self.generate_calendar_grid()

    def decrement_month(self):
        if self.current_month == 1:
            self.current_month = 12
            self.current_year -= 1
        else:
            self.current_month -= 1
        self.update_month_display()

    def increment_month(self):
        if self.current_month == 12:
            self.current_month = 1
            self.current_year += 1
        else:
            self.current_month += 1
        self.update_month_display()

    def on_wfh_state_changed(self):
        """تظليل/إزالة عمود الأحد الكامل (رأسه وخلاياه) عند تغيير تفعيل العمل عن بعد."""
        for day_num in list(self.day_types.keys()):
            if datetime(self.current_year, self.current_month, day_num).weekday() == 6 \
                    and self.day_types[day_num] in ('WORK', 'WH'):
                self.day_types[day_num] = 'WH' if self.wfh_chk.isChecked() else 'WORK'
                self.apply_cell_style(day_num)

        # تلوين رأس عمود الأحد (الصف 0) تبعاً لحالة العمل عن بعد
        header_item = self.calendar_table.item(0, 0)
        if header_item is not None:
            if self.wfh_chk.isChecked():
                header_item.setForeground(QBrush(QColor("#8E24AA")))
                header_item.setBackground(QBrush(QColor("#F3E5F5")))
            else:
                header_item.setForeground(QBrush(QColor("#1F2937")))
                header_item.setBackground(QBrush(QColor("#F8FAFC")))

        self.update_statistics()

    # ------------------------------------------------------------------
    # شبكة التقويم
    # ------------------------------------------------------------------
    def generate_calendar_grid(self):
        """توليد جدول التقويم 7x7 RTL: الأحد أقصى اليمين (عمود 0) حتى السبت أقصى اليسار."""
        self.day_cells.clear()
        self.day_types.clear()
        self.coord_to_day.clear()

        first_day_weekday = date(self.current_year, self.current_month, 1).weekday()
        num_days = calendar.monthrange(self.current_year, self.current_month)[1]

        # خريطة weekday() إلى العمود: الأحد(6)->0 (يمين) ... السبت(5)->6 (يسار)
        mapping = {6: 0, 0: 1, 1: 2, 2: 3, 3: 4, 4: 5, 5: 6}
        col = mapping[first_day_weekday]
        row = 1

        for day_num in range(1, num_days + 1):
            dow = datetime(self.current_year, self.current_month, day_num).weekday()
            if dow in (4, 5):
                day_type = 'REST'
            elif dow == 6 and self.wfh_chk.isChecked():
                day_type = 'WH'
            else:
                day_type = 'WORK'

            self.day_cells[day_num] = (row, col)
            self.day_types[day_num] = day_type
            self.coord_to_day[(row, col)] = day_num

            col += 1
            if col > 6:
                col = 0
                row += 1

        self.render_calendar_table()

    def render_calendar_table(self):
        """رسم أسماء الأيام في الصف 0 وكافة خلايا الشهر (بدون رؤوس منفصلة)."""
        self.calendar_table.setRowCount(7)
        self.calendar_table.setColumnCount(7)

        weekdays = ["الأحد", "الإثنين", "الثلاثاء", "الأربعاء", "الخميس", "الجمعة", "السبت"]
        col_colors = {
            0: ("#F3E5F5", "#8E24AA"),  # الأحد — موف/بنفسجي
            5: ("#FFEAEA", "#991B1B"),  # الجمعة — أحمر
            6: ("#FFEAEA", "#991B1B"),  # السبت — أحمر
        }
        for col in range(7):
            if col == 0 and not self.wfh_chk.isChecked():
                bg, fg = "#F8FAFC", "#1F2937"
            else:
                bg, fg = col_colors.get(col, ("#F8FAFC", "#1F2937"))
            item = QTableWidgetItem(weekdays[col])
            item.setTextAlignment(Qt.AlignCenter)
            item.setForeground(QBrush(QColor(fg)))
            item.setBackground(QBrush(QColor(bg)))
            item.setFont(QFont("Segoe UI", 12, QFont.Bold))
            self.calendar_table.setItem(0, col, item)

        for day_num in self.day_cells:
            self.apply_cell_style(day_num)

    def apply_cell_style(self, day_num):
        """تلوين خلية اليوم حسب عمودها (مع خيار العطلة الأزرق) بنص عادي متعدد الأسطر."""
        row, col = self.day_cells[day_num]
        dt = self.day_types[day_num]

        if dt == 'HOLIDAY':
            bg, fg, code = "#E0F2FE", "#1F2937", "H"
        elif dt == 'REST':
            bg, fg, code = "#FFEAEA", "#1F2937", "R"
        elif dt == 'WH':
            bg, fg, code = "#F3E5F5", "#8E24AA", "WH"
        else:
            bg, fg, code = "#FFFFFF", "#1F2937", ""

        text = str(day_num) if not code else f"{day_num}\n{code}"
        item = QTableWidgetItem(text)
        item.setTextAlignment(Qt.AlignCenter)
        item.setForeground(QBrush(QColor(fg)))
        item.setBackground(QBrush(QColor(bg)))
        self.calendar_table.setItem(row, col, item)

    def on_cell_clicked(self, row, col):
        """تبديل أي يوم إلى عطلة (H) بضغطة واحدة عند تفعيل خانة العطلات الرسمية."""
        if row == 0 or not self.holidays_chk.isChecked():
            return
        day_num = self.coord_to_day.get((row, col))
        if day_num is None:
            return
        self.day_types[day_num] = 'HOLIDAY' if self.day_types[day_num] != 'HOLIDAY' else self.default_type(day_num)
        self.apply_cell_style(day_num)
        self.update_statistics()

    def default_type(self, day_num):
        """الحالة الافتراضية لليوم حسب يوم الأسبوع."""
        dow = datetime(self.current_year, self.current_month, day_num).weekday()
        if dow in (4, 5):
            return 'REST'
        if dow == 6:
            return 'WH' if self.wfh_chk.isChecked() else 'WORK'
        return 'WORK'

    def update_statistics(self):
        work = rest = wh = holiday = 0
        for dt in self.day_types.values():
            if dt == 'WORK':
                work += 1
            elif dt == 'REST':
                rest += 1
            elif dt == 'WH':
                wh += 1
            elif dt == 'HOLIDAY':
                holiday += 1

        self.lbl_stat_work.setText(f"عمل: {work}")
        self.lbl_stat_rest.setText(f"راحة R: {rest}")
        self.lbl_stat_wh.setText(f"WH: {wh}")
        self.lbl_stat_h.setText(f"عطلة H: {holiday}")

    def get_holidays_list(self):
        return [day_num for day_num, dt in self.day_types.items() if dt == 'HOLIDAY']

    # ------------------------------------------------------------------
    # دورة التهيئة الكاملة
    # ------------------------------------------------------------------
    def trigger_initialization(self):
        if self.worker_thread is not None and self.worker_thread.isRunning():
            return
        if self.pre_check_thread is not None and self.pre_check_thread.isRunning():
            return

        holidays = self.get_holidays_list()
        h_count = len(holidays)

        # رسالة التأكيد الأصلية للحفاظ على سلوك النظام (تأكيد العطلات)
        if h_count > 0:
            question_text = (f"لقد قمت بتحديد عدد {h_count} أيام كعطلات رسمية (H) لهذا الشهر. "
                             "هل أنت متأكد من صحة هذه العطلات وتريد الاستمرار في عملية التهيئة؟")
        else:
            question_text = ("تحذير: لم تقم بتحديد أي أيام كعطلات رسمية (H) لهذا الشهر. "
                             "هل أنت متأكد من الرغبة في تهيئة الشهر بالكامل كأيام عمل اعتيادية بدون أي عطلات رسمية؟")

        reply = QMessageBox.question(self, "تأكيد إطلاق التهيئة", question_text,
                                     QMessageBox.Yes | QMessageBox.No, QMessageBox.No)
        if reply == QMessageBox.No:
            return

        self.set_controls_enabled(False)
        self.progress_bar.setValue(0)
        self.progress_bar.setVisible(True)
        self.lbl_thread_status.setText("جارٍ التحقق المسبق من البيانات...")
        self.lbl_thread_status.setVisible(True)
        self.append_log(f"بدء الفحص المسبق للشهر {self.issue}...")

        # الفحص المسبق الصامت في خيط منفصل (لا تجميد)
        self.pre_check_thread = MonthPreCheckThread(
            db_helper=self.db, ts_path=self.ts_path, ts_pwd=self.ts_pwd, issue=self.issue
        )
        self.pre_check_thread.pre_check_result.connect(self.on_pre_check_result)
        self.pre_check_thread.finished.connect(self._clear_pre_check_thread)
        self.pre_check_thread.start()

    def _clear_pre_check_thread(self):
        self.pre_check_thread = None

    def on_pre_check_result(self, ok, has_records, count, present_days, error):
        if not ok:
            self.set_controls_enabled(True)
            self.progress_bar.setVisible(False)
            self.lbl_thread_status.setVisible(False)
            self.append_log(f"فشل الفحص المسبق: {error}")
            QMessageBox.critical(
                self, "فشل الاتصال / التهيئة 🔴",
                f"تعذر إتمام الفحص المسبق لقاعدة البيانات.\n\n{translate_odbc_error(error)}"
            )
            return

        num_days = calendar.monthrange(self.current_year, self.current_month)[1]

        # (أ) التحقق المسبق من اكتمال الأيام أولاً: أي يوم مفقود = إيقاف فوري برسالة عربية واضحة
        required_days = set(range(1, num_days + 1))
        missing = required_days - set(present_days)
        if missing:
            missing_text = ", ".join(str(d) for d in sorted(missing))
            self.set_controls_enabled(True)
            self.progress_bar.setVisible(False)
            self.lbl_thread_status.setVisible(False)
            self.append_log(f"إيقاف التهيئة: أيام مفقودة من var_op ({missing_text}).")
            QMessageBox.critical(
                self, "فشل الاتصال / التهيئة 🔴",
                f"توقفت عملية التهيئة: بعض أيام الشهر غير موجودة في جدول var_op.\n"
                f"الأيام المفقودة: {missing_text}\n"
                f"لا يمكن متابعة التهيئة قبل اكتمال أيام الشهر في قاعدة البيانات."
            )
            return

        # (ب) هل الشهر مُهيأ مسبقاً؟ -> رسالة تأكيد إعادة التهيئة
        if has_records:
            self.append_log(f"التحقق المسبق: الشهر مُهيأ مسبقاً ({count:,} سجل موجود).")
            confirm = QMessageBox.question(
                self, "تأكيد إعادة التهيئة",
                "هذا الشهر تمت تهيئته مسبقاً، هل تريد إعادة التهيئة ومسح الحركات الحالية؟",
                QMessageBox.Yes | QMessageBox.No, QMessageBox.No
            )
            if confirm == QMessageBox.No:
                self.set_controls_enabled(True)
                self.progress_bar.setVisible(False)
                self.lbl_thread_status.setVisible(False)
                self.append_log("تم إلغاء إعادة التهيئة بواسطة المستخدم.")
                return
        else:
            self.append_log(f"التحقق المسبق: الشهر غير مُهيأ مسبقاً ({count} سجل).")

        # 3) إطلاق خيط التهيئة
        self.append_log("بدء عملية التهيئة في الخلفية...")
        self.lbl_thread_status.setText("جارٍ تحضير خيط التهيئة...")

        self.worker_thread = MonthPrepThread(
            db_helper=DatabaseConnection(retry_attempts=3, retry_delay_ms=120, connect_timeout=8),
            main_path=self.main_path,
            ts_path=self.ts_path,
            main_pwd=self.main_pwd,
            ts_pwd=self.ts_pwd,
            year=self.current_year,
            month=self.current_month,
            issue=self.issue,
            num_days=num_days,
            wfh_active=self.wfh_chk.isChecked(),
            holidays_list=holidays,
        )
        self.worker_thread.progress_updated.connect(self.on_thread_progress)
        self.worker_thread.status_updated.connect(self.on_thread_status)
        self.worker_thread.initialization_completed.connect(self.on_thread_success)
        self.worker_thread.initialization_failed.connect(self.on_thread_failed)
        self.worker_thread.start()

    # ------------------------------------------------------------------
    # استدعاءات الخيط
    # ------------------------------------------------------------------
    def set_controls_enabled(self, enabled):
        self.btn_initialize.setEnabled(enabled)
        self.btn_back.setEnabled(enabled)
        self.btn_dec_month.setEnabled(enabled)
        self.btn_inc_month.setEnabled(enabled)
        self.wfh_chk.setEnabled(enabled)
        self.holidays_chk.setEnabled(enabled)

    def on_thread_progress(self, val):
        self.progress_bar.setValue(val)

    def on_thread_status(self, text):
        self.lbl_thread_status.setText(text)
        self.append_log(text)

    def on_thread_success(self, employees, records):
        self.progress_bar.setVisible(False)
        self.lbl_thread_status.setVisible(False)
        self.set_controls_enabled(True)
        self.worker_thread = None
        self.append_log(f"اكتملت التهيئة: {employees} موظف و {records:,} سجل.")

        QMessageBox.information(
            self, "تمت العملية بنجاح 🟢",
            f"تمت تهيئة الشهر {self.issue} بنجاح.\n"
            f"تمت معالجة {employees} موظف فاعل.\n"
            f"إجمالي السجلات التي تم إنشاؤها في var_op: {records:,} سجل."
        )

    def on_thread_failed(self, error_msg):
        self.progress_bar.setVisible(False)
        self.lbl_thread_status.setVisible(False)
        self.set_controls_enabled(True)
        self.worker_thread = None
        self.append_log(f"فشلت التهيئة: {error_msg}")

        arabic_msg = translate_odbc_error(error_msg)
        QMessageBox.critical(
            self, "فشل الاتصال / التهيئة 🔴",
            f"فشلت عملية تهيئة الشهر.\n\n{arabic_msg}\n\n(الخطأ التقني: {error_msg})"
        )

    def closeEvent(self, event):
        if self.worker_thread is not None and self.worker_thread.isRunning():
            self.worker_thread.requestInterruption()
            self.worker_thread.wait(3000)
        if self.pre_check_thread is not None and self.pre_check_thread.isRunning():
            self.pre_check_thread.wait(2000)
        super().closeEvent(event)
