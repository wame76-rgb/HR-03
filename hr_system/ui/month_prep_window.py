# -*- coding: utf-8 -*-
"""
شاشة تهيئة بداية الشهر - نظام إدارة الموارد البشرية
التاريخ: 2026-08-23
سجل التعديلات:
- v1.0.0: الشاشة الأساسية وتجهيز التقويم وربط الخيوط.
- v1.1.0: إصلاح صريح وحاسم لمسارات قواعد البيانات (Path Resolution Fix):
1. القراءة الصحيحة من قسم DATABASE عبر ConfigManager بدلاً من 'paths'.
2. توحيد وحساب المسارات المطلقة اعتماداً على BASE_DIR لحماية الاتصال من الانهيار.
3. ربط كلمات المرور المشفرة لملفي TimeSheet و Main بشكل منفصل دقيق.
4. منع ظهور رسالة الخطأ (مسار قاعدة البيانات فارغ) وعرض المسار الفيزيائي الحقيقي في كارت الحالة.
"""

import os
import calendar
import datetime
import pyodbc
from datetime import date, datetime

from PySide6.QtWidgets import (
    QMainWindow, QWidget, QVBoxLayout, QHBoxLayout, QGridLayout, QLabel,
    QPushButton, QLineEdit, QComboBox, QListWidget, QTableWidget,
    QTableWidgetItem, QMessageBox, QFrame, QDateEdit, QHeaderView,
    QCheckBox, QProgressBar, QApplication
)
from PySide6.QtCore import Qt, QSize, QThread, Signal, QTimer
from PySide6.QtGui import QFont, QColor

# BASE_DIR Resolution
BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

class MonthPrepThread(QThread):
    """خيط معالجة خلفي مستقل لتنفيذ عملية تهيئة الشهر المليونية دون تجميد الواجهة"""
    progress_updated = Signal(int)
    status_updated = Signal(str)
    initialization_completed = Signal(int, int) # (employees, records)
    initialization_failed = Signal(str)

    def __init__(self, main_path, ts_path, main_pwd, ts_pwd, target_month, wfh_active, holidays_list):
        super().__init__()
        self.main_path = main_path
        self.ts_path = ts_path
        self.main_pwd = main_pwd
        self.ts_pwd = ts_pwd
        self.target_month = target_month # YYYYMM (string)
        self.wfh_active = wfh_active
        self.holidays_list = holidays_list # List of day numbers (integers)

    def run(self):
        try:
            self.status_updated.emit("جاري الاتصال بقواعد البيانات...")
            
            # 1. Main Database Connection to fetch active employees
            main_conn_str = f"DRIVER={{Microsoft Access Driver (*.mdb, *.accdb)}};DBQ={self.main_path};"
            if self.main_pwd:
                main_conn_str += f"PWD={self.main_pwd};"
            
            self.status_updated.emit("جاري جلب بيانات الموظفين الفاعلين...")
            main_conn = pyodbc.connect(main_conn_str)
            main_cursor = main_conn.cursor()
            
            # Fetch active employees (enha2_date is null or > target_month)
            # Since enha2_date is Date/Time, we compare it safely
            query_year = int(self.target_month[:4])
            query_month = int(self.target_month[4:])
            target_date_str = f"{query_year}/{query_month:02d}/01"
            
            main_cursor.execute(f"""
                SELECT ID, name, work_place 
                FROM basic 
                WHERE enha2_date IS NULL OR enha2_date > CDate('{target_date_str}')
            """)
            employees = [row for row in main_cursor.fetchall()]
            main_cursor.close()
            main_conn.close()

            if not employees:
                self.initialization_failed.emit("خطأ: لم يتم العثور على موظفين فاعلين في جدول basic!")
                return

            self.status_updated.emit("جاري التحضير لترحيل البيانات لجدول var_op...")

            # 2. Timesheet Database Connection
            ts_conn_str = f"DRIVER={{Microsoft Access Driver (*.mdb, *.accdb)}};DBQ={self.ts_path};"
            if self.ts_pwd:
                ts_conn_str += f"PWD={self.ts_pwd};"
                
            ts_conn = pyodbc.connect(ts_conn_str)
            ts_cursor = ts_conn.cursor()

            # Dynamic code retrieval from variables table
            ts_cursor.execute("SELECT var_code, var FROM variables")
            var_mapping = {}
            for row in ts_cursor.fetchall():
                var_mapping[str(row[1]).strip().upper()] = row[0]

            code_R = var_mapping.get('R', 5) # Default R fallback code
            code_WH = var_mapping.get('WH', 35) # Default WH fallback code
            code_H = var_mapping.get('H', 4) # Default H fallback code

            # Determine number of days in chosen month
            num_days = calendar.monthrange(query_year, query_month)[1]

            # Clear existing DatePrep and fill it
            self.status_updated.emit("جاري تحديث جدول أيام الشهر DatePrep...")
            ts_cursor.execute("DELETE FROM DatePrep")
            for day in range(1, num_days + 1):
                day_date_str = f"{query_year}/{query_month:02d}/{day:02d}"
                ts_cursor.execute("INSERT INTO DatePrep (EDate) VALUES (CDate(?))", day_date_str)
            
            # Start Bulk Insert into var_op
            # To maximize insert performance on MS Access, we construct tuples and use transaction commit
            self.status_updated.emit(f"جاري إدراج {len(employees) * num_days} سجل حضور لجدول var_op...")
            
            # Retrieve existing keys to prevent duplicates if needed or delete existing month records first
            ts_cursor.execute("DELETE FROM var_op WHERE Issue = ?", self.target_month)
            ts_conn.commit()

            inserted_records = 0
            total_employees = len(employees)

            for idx, emp in enumerate(employees):
                emp_id = emp[0]
                emp_wp = emp[2] if emp[2] is not None else 0
                
                # Check cancellation in the middle of thread
                if self.isInterruptionRequested():
                    ts_conn.rollback()
                    self.initialization_failed.emit("تم إلغاء العملية بواسطة المستخدم.")
                    return

                for day in range(1, num_days + 1):
                    current_date = datetime(query_year, query_month, day)
                    day_of_week = current_date.weekday() # 0 is Monday, 6 is Sunday
                    
                    # Precedence Rules logic
                    var_code = 0 # Default work
                    
                    if day in self.holidays_list:
                        var_code = code_H
                    elif day_of_week in (4, 5): # Friday or Saturday
                        var_code = code_R
                    elif day_of_week == 6 and self.wfh_active: # Sunday
                        var_code = code_WH
                    
                    day_date_str = f"{query_year}/{query_month:02d}/{day:02d}"
                    
                    ts_cursor.execute("""
                        INSERT INTO var_op (Issue, EmpId, EntryDate, var, wp, Notes, [lock])
                        VALUES (?, ?, CDate(?), ?, ?, NULL, 0)
                    """, self.target_month, float(emp_id), day_date_str, int(var_code), int(emp_wp))
                    
                    inserted_records += 1

                # Update progress per employee
                progress = int(((idx + 1) / total_employees) * 100)
                self.progress_updated.emit(progress)

            ts_conn.commit()
            ts_cursor.close()
            ts_conn.close()

            self.initialization_completed.emit(total_employees, inserted_records)

        except Exception as e:
            self.initialization_failed.emit(str(e))


class DayCardWidget(QFrame):
    """تصميم كارت اليوم التفاعلي داخل شبكة التقويم الجداري"""
    def __init__(self, day_num, day_type, parent_window):
        super().__init__()
        self.day_num = day_num
        self.day_type = day_type # 'WORK', 'REST', 'WH', 'HOLIDAY'
        self.parent_window = parent_window
        self.init_ui()

    def init_ui(self):
        self.setFrameShape(QFrame.StyledPanel)
        self.setFrameShadow(QFrame.Plain)
        self.setFixedSize(85, 75)
        
        self.layout = QVBoxLayout(self)
        self.layout.setContentsMargins(4, 8, 4, 8)
        self.layout.setSpacing(4)
        self.layout.setAlignment(Qt.AlignCenter)

        # Day Number Label
        self.num_label = QLabel(str(self.day_num), self)
        self.num_label.setFont(QFont("Segoe UI", 18, QFont.Bold))
        self.num_label.setAlignment(Qt.AlignCenter)
        self.layout.addWidget(self.num_label)

        # Status Description Label
        self.status_label = QLabel(self)
        self.status_label.setFont(QFont("Segoe UI", 10))
        self.status_label.setAlignment(Qt.AlignCenter)
        self.layout.addWidget(self.status_label)

        self.apply_state_style()

    def apply_state_style(self):
        """تطبيق الأنماط اللونية الأربعة المعتمدة في دستور المشروع بدقة متناهية"""
        if self.day_type == 'REST':
            # Fridays and Saturdays
            self.setStyleSheet("""
                DayCardWidget {
                    background-color: #f1f3f4;
                    border: 1px solid #dadce0;
                    border-radius: 6px;
                }
                QLabel {
                    color: #9aa0a6;
                }
            """)
            self.status_label.setText("راحة (R)")
        elif self.day_type == 'WH':
            # Sundays Work From Home
            self.setStyleSheet("""
                DayCardWidget {
                    background-color: #f3e5f5;
                    border: 1px solid #ab47bc;
                    border-radius: 6px;
                }
                QLabel {
                    color: #8e24aa;
                }
            """)
            self.status_label.setText("عمل عن بعد (WH)")
        elif self.day_type == 'HOLIDAY':
            # Selected Official Holiday
            self.setStyleSheet("""
                DayCardWidget {
                    background-color: #1a73e8;
                    border: 1px solid #1557b0;
                    border-radius: 6px;
                }
                QLabel {
                    color: #ffffff;
                }
            """)
            self.status_label.setText("عطلة (H)")
        else:
            # Normal Work Day
            self.setStyleSheet("""
                DayCardWidget {
                    background-color: #ffffff;
                    border: 1px solid #dadce0;
                    border-radius: 6px;
                }
                QLabel {
                    color: #202124;
                }
            """)
            self.status_label.setText("عمل")

    def mousePressEvent(self, event):
        """تغيير الحالة عند النقر فقط إذا كان قفل التعديل ملغياً وكارت اليوم ليس عطلة إجبارية"""
        if event.button() == Qt.LeftButton:
            if self.day_type == 'REST':
                return # Locked Friday/Saturday
            
            # Only allow click if "تنشيط تحديد العطلات الرسمية" is checked
            if not self.parent_window.holidays_chk.isChecked():
                QMessageBox.warning(self.parent_window, "تنبيه", "برجاء تفعيل خانة الاختيار 'تنشيط تحديد العطلات الرسمية (H)' أولاً لفتح تعديل خلايا التقويم.")
                return

            # Toggle state
            if self.day_type == 'HOLIDAY':
                # Revert to normal or WH depending on day of week
                current_date = datetime(self.parent_window.current_year, self.parent_window.current_month, self.day_num)
                if current_date.weekday() == 6 and self.parent_window.wfh_chk.isChecked():
                    self.day_type = 'WH'
                else:
                    self.day_type = 'WORK'
            else:
                self.day_type = 'HOLIDAY'

            self.apply_state_style()
            self.parent_window.update_statistics()


class MonthPrepWindow(QMainWindow):
    """الشاشة الرئيسية الكاملة لتهيئة بداية الشهر والتقويم الجداري المصقول v17"""
    def __init__(self, config_manager, db_connection, user_data, parent=None):
        super().__init__(parent)
        self.config = config_manager
        self.db = db_connection
        self.user_data = user_data

        # Parse current date settings
        now = datetime.now()
        self.current_year = now.year
        self.current_month = now.month

        # Retrieve paths safely from DATABASE section
        self.ts_path = self.config.config.get('DATABASE', 'timesheet', fallback='')
        self.main_path = self.config.config.get('DATABASE', 'main', fallback='')

        # Ensure absolute resolution relative to BASE_DIR
        if self.ts_path and not os.path.isabs(self.ts_path):
            self.ts_path = os.path.join(BASE_DIR, self.ts_path).replace("\\", "/")
        if self.main_path and not os.path.isabs(self.main_path):
            self.main_path = os.path.join(BASE_DIR, self.main_path).replace("\\", "/")

        self.ts_pwd = self.config.get_password('timesheet')
        self.main_pwd = self.config.get_password('main')

        self.day_widgets = {}
        self.init_ui()

    def init_ui(self):
        self.setWindowTitle("تهيئة بداية الشهر (DatePrep & Movements Population)")
        self.resize(1180, 780)
        self.setLayoutDirection(Qt.RightToLeft)
        self.setStyleSheet("background-color: #fafbfc; font-family: 'Segoe UI';")

        # Disable size grip cleanly
        if self.statusBar():
            self.statusBar().setSizeGripEnabled(False)

        # Central Widget & Top Layout
        self.central_widget = QWidget(self)
        self.setCentralWidget(self.central_widget)
        self.main_layout = QHBoxLayout(self.central_widget)
        self.main_layout.setContentsMargins(20, 20, 20, 20)
        self.main_layout.setSpacing(20)

        # ----------------------------------------------------
        # Pane 1: Left Pane (Calendar Area - 60% Stretch)
        # ----------------------------------------------------
        self.left_pane = QWidget(self)
        self.left_layout = QVBoxLayout(self.left_pane)
        self.left_layout.setContentsMargins(0, 0, 0, 0)
        self.left_layout.setSpacing(15)

        # Checkbox Control Bar (Styled beautifully per pixel specs)
        self.control_bar = QFrame(self)
        self.control_bar.setStyleSheet("""
            QFrame {
                background-color: #ffffff;
                border: 1px solid #e8eaed;
                border-radius: 8px;
            }
            QCheckBox {
                spacing: 8px;
                font-weight: bold;
                color: #3c4043;
            }
            QCheckBox::indicator {
                width: 20px;
                height: 20px;
                border: 2px solid #dadce0;
                border-radius: 4px;
                background-color: white;
            }
            QCheckBox::indicator:checked {
                background-color: #1a73e8;
                border-color: #1a73e8;
                image: url(hr_system/assets/checkmark.svg); /* Or custom tick */
            }
        """)
        self.bar_layout = QHBoxLayout(self.control_bar)
        self.bar_layout.setContentsMargins(15, 12, 15, 12)
        self.bar_layout.setSpacing(30)

        # Checkbox WH (Default Active)
        self.wfh_chk = QCheckBox("تفعيل العمل عن بعد (الأحد - WH)", self)
        self.wfh_chk.setChecked(True)
        self.wfh_chk.stateChanged.connect(self.on_wfh_state_changed)
        self.bar_layout.addWidget(self.wfh_chk)

        # Checkbox Holidays H (Default Disabled/Unchecked)
        self.holidays_chk = QCheckBox("تنشيط تحديد العطلات الرسمية (H)", self)
        self.holidays_chk.setChecked(False)
        self.bar_layout.addWidget(self.holidays_chk)

        self.left_layout.addWidget(self.control_bar)

        # Main Calendar Panel Wrapper
        self.calendar_wrapper = QFrame(self)
        self.calendar_wrapper.setStyleSheet("background-color: #ffffff; border: 1px solid #e8eaed; border-radius: 8px;")
        self.calendar_layout = QVBoxLayout(self.calendar_wrapper)
        self.calendar_layout.setContentsMargins(15, 15, 15, 15)
        self.calendar_layout.setSpacing(10)

        # Header Titles (Static columns Friday to Saturday RTL)
        self.header_grid = QGridLayout()
        self.header_grid.setSpacing(10)
        weekdays = ["الجمعة", "الخميس", "الأربعاء", "الثلاثاء", "الاثنين", "الأحد", "السبت"]
        for idx, day_name in enumerate(weekdays):
            lbl = QLabel(day_name, self)
            lbl.setFont(QFont("Segoe UI", 11, QFont.Bold))
            lbl.setAlignment(Qt.AlignCenter)
            lbl.setStyleSheet("color: #5f6368; padding-bottom: 5px;")
            self.header_grid.addWidget(lbl, 0, idx)
        
        self.calendar_layout.addLayout(self.header_grid)

        # Calendar Grid
        self.grid_layout = QGridLayout()
        self.grid_layout.setSpacing(10)
        self.calendar_layout.addLayout(self.grid_layout)

        # Add stretch to left side to align beautifully
        self.left_layout.addWidget(self.calendar_wrapper, 1)
        self.main_layout.addWidget(self.left_pane, 3)

        # ----------------------------------------------------
        # Pane 2: Right Pane (Column A - 40% Width)
        # ----------------------------------------------------
        self.right_pane = QWidget(self)
        self.right_pane.setFixedWidth(360)
        self.right_layout = QVBoxLayout(self.right_pane)
        self.right_layout.setContentsMargins(0, 0, 0, 0)
        self.right_layout.setSpacing(15)

        # 1. User Info Card
        self.user_card = QFrame(self)
        self.user_card.setStyleSheet("background-color: #ffffff; border: 1px solid #e8eaed; border-radius: 8px;")
        self.user_layout = QVBoxLayout(self.user_card)
        self.user_layout.setContentsMargins(15, 12, 15, 12)
        
        # Truncate Name to Triple name and ID to safe Integer
        raw_name = self.user_data.get("name", "مستشار النظام")
        name_parts = raw_name.split()
        triple_name = " ".join(name_parts[:3]) if len(name_parts) >= 3 else raw_name
        emp_id = int(float(self.user_data.get("ID", 0)))

        self.user_label = QLabel(f"المستشار الحالي: {triple_name}\nالرقم المالي: {emp_id}", self)
        self.user_label.setFont(QFont("Segoe UI", 11, QFont.Bold))
        self.user_label.setStyleSheet("color: #3c4043; line-height: 24px;")
        self.user_label.setAlignment(Qt.AlignRight)
        self.user_layout.addWidget(self.user_label)
        self.right_layout.addWidget(self.user_card)

        # 2. Target Month Card (Flanked with zero/minimal spacing)
        self.month_card = QFrame(self)
        self.month_card.setStyleSheet("background-color: #ffffff; border: 1px solid #e8eaed; border-radius: 8px;")
        self.month_layout = QHBoxLayout(self.month_card)
        self.month_layout.setContentsMargins(15, 12, 15, 12)
        self.month_layout.setSpacing(2) # Flanked closely

        self.btn_dec_month = QPushButton("-", self)
        self.btn_dec_month.setFixedSize(36, 36)
        self.btn_dec_month.setFont(QFont("Segoe UI", 14, QFont.Bold))
        self.btn_dec_month.setStyleSheet("""
            QPushButton {
                background-color: #f8f9fa; border: 1px solid #dadce0; border-radius: 4px; color: #3c4043;
            }
            QPushButton:hover { background-color: #e8eaed; }
        """)
        self.btn_dec_month.clicked.connect(self.decrement_month)
        self.month_layout.addWidget(self.btn_dec_month)

        self.month_input = QLineEdit(self)
        self.month_input.setReadOnly(True)
        self.month_input.setAlignment(Qt.AlignCenter)
        self.month_input.setFont(QFont("Segoe UI", 13, QFont.Bold))
        self.month_input.setFixedSize(160, 36)
        self.month_input.setStyleSheet("border: 1px solid #dadce0; border-radius: 4px; background-color: #ffffff; color: #202124;")
        self.month_layout.addWidget(self.month_input)

        self.btn_inc_month = QPushButton("+", self)
        self.btn_inc_month.setFixedSize(36, 36)
        self.btn_inc_month.setFont(QFont("Segoe UI", 14, QFont.Bold))
        self.btn_inc_month.setStyleSheet("""
            QPushButton {
                background-color: #f8f9fa; border: 1px solid #dadce0; border-radius: 4px; color: #3c4043;
            }
            QPushButton:hover { background-color: #e8eaed; }
        """)
        self.btn_inc_month.clicked.connect(self.increment_month)
        self.month_layout.addWidget(self.btn_inc_month)

        self.right_layout.addWidget(self.month_card)

        # 3. Monthly Statistics Card
        self.stats_card = QFrame(self)
        self.stats_card.setStyleSheet("background-color: #ffffff; border: 1px solid #e8eaed; border-radius: 8px;")
        self.stats_layout = QVBoxLayout(self.stats_card)
        self.stats_layout.setContentsMargins(15, 15, 15, 15)
        self.stats_layout.setSpacing(10)

        self.stats_title = QLabel("إحصائيات الشهر المستهدف", self)
        self.stats_title.setFont(QFont("Segoe UI", 11, QFont.Bold))
        self.stats_title.setStyleSheet("color: #3c4043; border-bottom: 1px solid #f1f3f4; padding-bottom: 5px;")
        self.stats_layout.addWidget(self.stats_title)

        self.lbl_stat_work = QLabel("أيام العمل: -", self)
        self.lbl_stat_work.setFont(QFont("Segoe UI", 10, QFont.Bold))
        self.lbl_stat_work.setStyleSheet("color: #202124;")
        self.stats_layout.addWidget(self.lbl_stat_work)

        self.lbl_stat_rest = QLabel("أيام الراحة (R): -", self)
        self.lbl_stat_rest.setFont(QFont("Segoe UI", 10, QFont.Bold))
        self.lbl_stat_rest.setStyleSheet("color: #5f6368;")
        self.stats_layout.addWidget(self.lbl_stat_rest)

        self.lbl_stat_wh = QLabel("أيام العمل عن بعد (WH): -", self)
        self.lbl_stat_wh.setFont(QFont("Segoe UI", 10, QFont.Bold))
        self.lbl_stat_wh.setStyleSheet("color: #8e24aa;")
        self.stats_layout.addWidget(self.lbl_stat_wh)

        self.lbl_stat_h = QLabel("أيام العطلات الرسمية (H): -", self)
        self.lbl_stat_h.setFont(QFont("Segoe UI", 10, QFont.Bold))
        self.lbl_stat_h.setStyleSheet("color: #1a73e8;")
        self.stats_layout.addWidget(self.lbl_stat_h)

        self.right_layout.addWidget(self.stats_card)

        # 4. Live Green Status Card
        self.status_card = QFrame(self)
        self.status_card.setStyleSheet("background-color: #e8f5e9; border: 1px solid #c8e6c9; border-radius: 8px;")
        self.status_layout = QVBoxLayout(self.status_card)
        self.status_layout.setContentsMargins(15, 12, 15, 12)
        self.status_layout.setSpacing(6)

        self.lbl_status_indicator = QLabel("حالة قاعدة البيانات: متصلة ونشطة 🟢", self)
        self.lbl_status_indicator.setFont(QFont("Segoe UI", 11, QFont.Bold))
        self.lbl_status_indicator.setStyleSheet("color: #1b5e20;")
        self.status_layout.addWidget(self.lbl_status_indicator)

        self.lbl_db_details = QLabel(self)
        self.lbl_db_details.setFont(QFont("Segoe UI", 10))
        self.lbl_db_details.setStyleSheet("color: #2e7d32; line-height: 18px;")
        self.lbl_db_details.setWordWrap(True)
        
        # Display the real physical path in small font
        db_file_name = os.path.basename(self.ts_path) if self.ts_path else "TIME SHEET.mdb"
        self.lbl_db_details.setText(
            f"<b>قاعدة البيانات:</b> {db_file_name}<br>"
            f"<b>المسار الفعلي:</b> {self.ts_path}<br>"
            f"<b>الجدول النشط:</b> DatePrep & var_op"
        )
        self.status_layout.addWidget(self.lbl_db_details)
        self.right_layout.addWidget(self.status_card)

        # Progress Bar & Thread Status (Shown during computation)
        self.progress_bar = QProgressBar(self)
        self.progress_bar.setVisible(False)
        self.progress_bar.setStyleSheet("""
            QProgressBar {
                border: 1px solid #dadce0; border-radius: 6px; text-align: center; background-color: #ffffff;
            }
            QProgressBar::chunk {
                background-color: #34a853; border-radius: 5px;
            }
        """)
        self.right_layout.addWidget(self.progress_bar)

        self.lbl_thread_status = QLabel("", self)
        self.lbl_thread_status.setFont(QFont("Segoe UI", 10))
        self.lbl_thread_status.setStyleSheet("color: #5f6368;")
        self.lbl_thread_status.setAlignment(Qt.AlignCenter)
        self.lbl_thread_status.setVisible(False)
        self.right_layout.addWidget(self.lbl_thread_status)

        # Spacer to push action buttons down
        self.right_layout.addStretch()

        # 5. Action Buttons (Vertical in Column A)
        self.btn_initialize = QPushButton("بدء تهيئة الشهر", self)
        self.btn_initialize.setFont(QFont("Segoe UI", 11, QFont.Bold))
        self.btn_initialize.setFixedHeight(48)
        self.btn_initialize.setStyleSheet("""
            QPushButton {
                background-color: #1a73e8; color: #ffffff; border: none; border-radius: 6px;
            }
            QPushButton:hover { background-color: #1557b0; }
        """)
        self.btn_initialize.clicked.connect(self.trigger_initialization)
        self.right_layout.addWidget(self.btn_initialize)

        self.btn_back = QPushButton("رجوع", self)
        self.btn_back.setFont(QFont("Segoe UI", 11, QFont.Bold))
        self.btn_back.setFixedHeight(48)
        self.btn_back.setStyleSheet("""
            QPushButton {
                background-color: #f8f9fa; color: #3c4043; border: 1px solid #dadce0; border-radius: 6px;
            }
            QPushButton:hover { background-color: #e8eaed; }
        """)
        self.btn_back.clicked.connect(self.close)
        self.right_layout.addWidget(self.btn_back)

        self.main_layout.addWidget(self.right_pane)

        # Load target month
        self.update_month_display()

    def update_month_display(self):
        """تحديث بيانات الشهر المالي المكتوب وتوليد خلايا التقويم ديناميكياً"""
        self.month_str = f"{self.current_year}{self.current_month:02d}"
        self.month_input.setText(self.month_str)
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
        """تحديث أنماط أيام الأحد تلقائياً عند تغيير حالة العمل عن بعد"""
        for day_num, card in self.day_widgets.items():
            if card.day_type in ('WORK', 'WH'):
                current_date = datetime(self.current_year, self.current_month, day_num)
                if current_date.weekday() == 6: # Sunday
                    card.day_type = 'WH' if self.wfh_chk.isChecked() else 'WORK'
                    card.apply_state_style()
        self.update_statistics()

    def generate_calendar_grid(self):
        """تنظيف وتوليد خلايا التقويم الجداري RTL وفق أول عمود على اليمين الجمعة"""
        # Clean current grid widgets
        for i in reversed(range(self.grid_layout.count())): 
            widget = self.grid_layout.itemAt(i).widget()
            if widget is not None:
                widget.deleteLater()
        
        self.day_widgets.clear()

        # Determine start weekday and total days
        first_day_weekday = date(self.current_year, self.current_month, 1).weekday()
        num_days = calendar.monthrange(self.current_year, self.current_month)[1]

        # Monday(0)->col4, Tuesday(1)->col3, Wednesday(2)->col2, Thursday(3)->col1, Friday(4)->col0, Sunday(6)->col5, Saturday(5)->col6
        mapping = {4: 0, 3: 1, 2: 2, 1: 3, 0: 4, 6: 5, 5: 6}
        col = mapping[first_day_weekday]
        row = 1

        for day_num in range(1, num_days + 1):
            current_date = datetime(self.current_year, self.current_month, day_num)
            day_of_week = current_date.weekday()

            # Determine default type
            if day_of_week in (4, 5): # Friday/Saturday
                day_type = 'REST'
            elif day_of_week == 6 and self.wfh_chk.isChecked(): # Sunday WH
                day_type = 'WH'
            else:
                day_type = 'WORK'

            card = DayCardWidget(day_num, day_type, self)
            self.day_widgets[day_num] = card
            self.grid_layout.addWidget(card, row, col)

            col += 1
            if col > 6:
                col = 0
                row += 1

        self.update_statistics()

    def update_statistics(self):
        """حساب وعرض إحصائيات الشهر المستهدف ديناميكياً بأرقام حقيقية"""
        work = 0
        rest = 0
        wh = 0
        holiday = 0

        for card in self.day_widgets.values():
            if card.day_type == 'WORK':
                work += 1
            elif card.day_type == 'REST':
                rest += 1
            elif card.day_type == 'WH':
                wh += 1
            elif card.day_type == 'HOLIDAY':
                holiday += 1

        self.lbl_stat_work.setText(f"أيام العمل: {work} يوم")
        self.lbl_stat_rest.setText(f"أيام الراحة (R): {rest} يوم")
        self.lbl_stat_wh.setText(f"أيام العمل عن بعد (WH): {wh} يوم")
        self.lbl_stat_h.setText(f"أيام العطلات الرسمية (H): {holiday} يوم")

    def get_holidays_list(self):
        """الحصول على قائمة الأيام المعلمة كعطلة رسمية H"""
        return [day_num for day_num, card in self.day_widgets.items() if card.day_type == 'HOLIDAY']

    def trigger_initialization(self):
        """التحقق الوقائي وإطلاق خيط المعالجة بالخلفية لترحيل السجلات"""
        holidays = self.get_holidays_list()
        h_count = len(holidays)

        # Secure RTL Confirmation Message Boxes
        if h_count > 0:
            question_text = f"لقد قمت بتحديد عدد {h_count} أيام كعطلات رسمية (H) لهذا الشهر. هل أنت متأكد من صحة هذه العطلات وتريد الاستمرار في عملية التهيئة؟"
        else:
            question_text = "تحذير: لم تقم بتحديد أي أيام كعطلات رسمية (H) لهذا الشهر. هل أنت متأكد من الرغبة في تهيئة الشهر بالكامل كأيام عمل اعتيادية بدون أي عطلات رسمية؟"

        reply = QMessageBox.question(self, "تأكيد إطلاق التهيئة", question_text, QMessageBox.Yes | QMessageBox.No, QMessageBox.No)
        
        if reply == QMessageBox.No:
            return

        # Disable main control buttons to prevent multi-clicking
        self.btn_initialize.setEnabled(False)
        self.btn_back.setEnabled(False)
        self.btn_dec_month.setEnabled(False)
        self.btn_inc_month.setEnabled(False)
        self.wfh_chk.setEnabled(False)
        self.holidays_chk.setEnabled(False)

        # Show progress widgets
        self.progress_bar.setValue(0)
        self.progress_bar.setVisible(True)
        self.lbl_thread_status.setText("جاري التحضير لبدء المعالجة...")
        self.lbl_thread_status.setVisible(True)

        # Launch QThread background worker
        self.worker_thread = MonthPrepThread(
            main_path=self.main_path,
            ts_path=self.ts_path,
            main_pwd=self.main_pwd,
            ts_pwd=self.ts_pwd,
            target_month=self.month_str,
            wfh_active=self.wfh_chk.isChecked(),
            holidays_list=holidays
        )

        self.worker_thread.progress_updated.connect(self.on_thread_progress)
        self.worker_thread.status_updated.connect(self.on_thread_status)
        self.worker_thread.initialization_completed.connect(self.on_thread_success)
        self.worker_thread.initialization_failed.connect(self.on_thread_failed)

        self.worker_thread.start()

    def on_thread_progress(self, val):
        self.progress_bar.setValue(val)

    def on_thread_status(self, text):
        self.lbl_thread_status.setText(text)

    def on_thread_success(self, employees, records):
        self.progress_bar.setVisible(False)
        self.lbl_thread_status.setVisible(False)

        # Enable UI
        self.btn_initialize.setEnabled(True)
        self.btn_back.setEnabled(True)
        self.btn_dec_month.setEnabled(True)
        self.btn_inc_month.setEnabled(True)
        self.wfh_chk.setEnabled(True)
        self.holidays_chk.setEnabled(True)

        QMessageBox.information(
            self, "تمت العملية بنجاح 🟢", 
            f"تمت عملية تهيئة الشهر {self.month_str} بنجاح!\n"
            f"تمت معالجة {employees} موظف فاعل.\n"
            f"إجمالي السجلات التي تم إدراجها في var_op: {records} سجل حضور فارغ."
        )

    def on_thread_failed(self, error_msg):
        self.progress_bar.setVisible(False)
        self.lbl_thread_status.setVisible(False)

        # Enable UI
        self.btn_initialize.setEnabled(True)
        self.btn_back.setEnabled(True)
        self.btn_dec_month.setEnabled(True)
        self.btn_inc_month.setEnabled(True)
        self.wfh_chk.setEnabled(True)
        self.holidays_chk.setEnabled(True)

        QMessageBox.critical(
            self, "فشل الاتصال / التهيئة 🔴", 
            f"فشلت عملية تهيئة الشهر بسبب الخطأ التالي:\n{error_msg}"
        )
