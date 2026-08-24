from PySide6.QtWidgets import (
    QMainWindow, QWidget, QVBoxLayout, QHBoxLayout, QGridLayout,
    QLabel, QPushButton, QLineEdit, QComboBox, QCompleter,
    QTableWidget, QTableWidgetItem, QMessageBox,
    QFrame, QDateEdit, QHeaderView, QRadioButton, QButtonGroup,
    QAbstractItemView, QListWidget
)
from PySide6.QtCore import Qt, QDate, QEvent
from PySide6.QtGui import QFont
import datetime


class _SelectableDateEdit(QDateEdit):
    def __init__(self, parent=None):
        super().__init__(parent)
        self._manually_edited = False
        self._source = None
        self.dateChanged.connect(self._on_date_changed)

    def set_source(self, widget):
        self._source = widget
        if self._source is not None:
            self._source.dateChanged.connect(self._on_source_date_changed)

    def _on_source_date_changed(self, date):
        if not self._manually_edited:
            self.blockSignals(True)
            self.setDate(date)
            self.blockSignals(False)

    def _on_date_changed(self, date):
        self._manually_edited = True

    def focusInEvent(self, event):
        self.selectAll()
        super().focusInEvent(event)


class VariablesWindow(QMainWindow):
    PERMISSION_CODES = ("1", "x", "X")
    MAX_PERMISSIONS_PER_TYPE = 2

    def __init__(self, config_manager, db_connection, user_data, parent=None):
        super().__init__(parent)
        self.config = config_manager
        self.db = db_connection
        self.user_data = user_data

        self.variables_data = []
        self.workplaces_data = []
        self.current_issue = ""
        self.current_emp_id = None

        self.setWindowTitle("ادخال المتغيرات")
        self.setMinimumSize(1000, 650)
        self.setLayoutDirection(Qt.RightToLeft)
        self.setup_ui()
        self._load_static_data()

        today = QDate.currentDate()
        self.month_input.setText(today.toString("yyyyMM"))
        self.date_from.setDate(today)
        self.date_to.setDate(today)

        # Action buttons initially disabled until valid employee is loaded
        self.transfer_var_btn.setEnabled(False)
        self.transfer_perm_btn.setEnabled(False)
        self.cancel_perm_btn.setEnabled(False)

        # 1. Auto Focus on init
        self.id_input.setFocus()

        # 2. Intelligent tab order sequence
        QWidget.setTabOrder(self.id_input, self.date_from)
        QWidget.setTabOrder(self.date_from, self.date_to)
        QWidget.setTabOrder(self.date_to, self.var_combo)
        QWidget.setTabOrder(self.var_combo, self.wp_combo)

        # 3. Install event filter for keyboard-driven focus navigation
        self.id_input.installEventFilter(self)
        self.date_from.installEventFilter(self)
        self.date_to.installEventFilter(self)
        self.var_combo.installEventFilter(self)
        if self.var_combo.lineEdit():
            self.var_combo.lineEdit().installEventFilter(self)
        self.wp_combo.installEventFilter(self)
        if self.wp_combo.lineEdit():
            self.wp_combo.lineEdit().installEventFilter(self)

    def eventFilter(self, watched, event):
        if event.type() == QEvent.KeyPress:
            key = event.key()
            nav_widgets = [self.id_input, self.date_from, self.date_to, self.var_combo, self.wp_combo]
            var_lineEdit = self.var_combo.lineEdit()
            wp_lineEdit = self.wp_combo.lineEdit()

            target = None
            if watched in nav_widgets:
                target = watched
            elif watched == var_lineEdit:
                target = self.var_combo
            elif watched == wp_lineEdit:
                target = self.wp_combo

            if target is not None:
                # 1. Forward Navigation (Enter, Return, Down Arrow)
                if key in (Qt.Key_Return, Qt.Key_Enter, Qt.Key_Down):
                    # Check if combo box completer popup dropdown is visible
                    if isinstance(target, QComboBox):
                        c = target.completer()
                        if c and c.popup() and c.popup().isVisible():
                            return super().eventFilter(watched, event)

                    # For Financial Number, pressing Enter triggers loading of employee data first
                    if target == self.id_input and key in (Qt.Key_Return, Qt.Key_Enter):
                        self._load_employee()
                        return True

                    self.focusNextChild()
                    return True

                # 2. Backward Navigation (Up Arrow)
                elif key == Qt.Key_Up:
                    if isinstance(target, QComboBox):
                        c = target.completer()
                        if c and c.popup() and c.popup().isVisible():
                            return super().eventFilter(watched, event)

                    self.focusPreviousChild()
                    return True

        return super().eventFilter(watched, event)

    def setup_ui(self):
        central = QWidget()
        central.setStyleSheet("background-color: #fafbfc;")
        self.setCentralWidget(central)

        main_layout = QVBoxLayout(central)
        main_layout.setContentsMargins(12, 10, 12, 10)
        main_layout.setSpacing(8)

        # Body Area (3 Columns in RTL: Right = Variables, Center = Inputs/Info/Report, Left = 31-Day Movements)
        body = QHBoxLayout()
        body.setSpacing(8)

        # Column 1 (Right in RTL): Variables Panel (قائمة المتغيرات)
        body.addWidget(self._build_variables_panel(), 2)

        # Column 2 (Center in RTL): Inputs + Employee Info + Report Panel
        body.addLayout(self._build_center_area(), 5)

        # Column 3 (Left in RTL): 31-Day Movements Table (تحركات الشهر)
        body.addWidget(self._build_movements_panel(), 5)

        main_layout.addLayout(body, 1)

        # Bottom Bar with Back button
        main_layout.addWidget(self._build_bottom_bar())

    def _build_variables_panel(self):
        panel = QFrame()
        panel.setStyleSheet(
            "QFrame { background-color: #ffffff; border: 1px solid #dadce0; border-radius: 8px; }"
        )
        layout = QVBoxLayout(panel)
        layout.setContentsMargins(6, 6, 6, 6)
        layout.setSpacing(4)

        header = QLabel("قائمة المتغيرات")
        header.setFont(QFont("Segoe UI", 10, QFont.Bold))
        header.setStyleSheet("color: #1a73e8; border: none; padding: 2px 4px;")
        layout.addWidget(header)

        self.variables_list = QListWidget()
        self.variables_list.setFont(QFont("Segoe UI", 9))
        self.variables_list.setSelectionMode(QListWidget.SingleSelection)
        self.variables_list.setStyleSheet(
            "QListWidget { background-color: #ffffff; border: 1px solid #e8eaed; border-radius: 6px; padding: 2px; }"
            "QListWidget::item { padding: 3px 6px; border-bottom: 1px solid #f1f3f4; color: #202124; }"
            "QListWidget::item:selected { background-color: #e8f0fe; color: #1a73e8; font-weight: bold; border-radius: 4px; }"
            "QListWidget::item:hover { background-color: #f8f9fa; }"
        )
        self.variables_list.currentRowChanged.connect(self._on_list_selected)
        layout.addWidget(self.variables_list, 1)
        return panel

    def _build_center_area(self):
        center = QVBoxLayout()
        center.setSpacing(6)
        center.addWidget(self._build_inputs_panel(), 0)
        center.addWidget(self._build_info_panel(), 0)
        center.addWidget(self._build_report_panel(), 1)
        return center

    def _build_inputs_panel(self):
        panel = QFrame()
        panel.setStyleSheet(
            "QFrame { background-color: #ffffff; border: 1px solid #dadce0; border-radius: 8px; }"
            "QLineEdit, QDateEdit { "
            "background-color: #ffffff; border: 1px solid #dadce0; "
            "border-radius: 6px; padding: 0 8px; font-size: 13px; color: #202124; min-height: 30px; max-height: 30px; }"
            "QLineEdit:focus, QDateEdit:focus { "
            "border: 2px solid #1a73e8; padding: 0 7px; }"
            "QRadioButton { font-size: 13px; font-weight: bold; color: #202124; spacing: 6px; }"
            "QRadioButton::indicator { width: 16px; height: 16px; }"
        )
        layout = QVBoxLayout(panel)
        layout.setContentsMargins(10, 8, 10, 8)
        layout.setSpacing(6)

        grid = QGridLayout()
        grid.setHorizontalSpacing(8)
        grid.setVerticalSpacing(5)

        # Row 0: الشهر (col 0, 1) | الرقم المالي (col 2, 3)
        month_label = QLabel("الشهر:")
        month_label.setFont(QFont("Segoe UI", 9, QFont.Bold))
        month_label.setStyleSheet("color: #5f6368; border: none;")
        grid.addWidget(month_label, 0, 0)

        month_row = QHBoxLayout()
        month_row.setSpacing(3)
        self.month_minus_btn = self._month_button("-")
        self.month_minus_btn.clicked.connect(lambda: self._shift_month(-1))
        self.month_input = QLineEdit()
        self.month_input.setMaxLength(6)
        self.month_input.setAlignment(Qt.AlignCenter)
        self.month_input.setFont(QFont("Segoe UI", 9, QFont.Bold))
        self.month_plus_btn = self._month_button("+")
        self.month_plus_btn.clicked.connect(lambda: self._shift_month(1))
        month_row.addWidget(self.month_minus_btn)
        month_row.addWidget(self.month_input, 1)
        month_row.addWidget(self.month_plus_btn)
        grid.addLayout(month_row, 0, 1)

        id_label = QLabel("الرقم المالي:")
        id_label.setFont(QFont("Segoe UI", 9, QFont.Bold))
        id_label.setStyleSheet("color: #5f6368; border: none;")
        grid.addWidget(id_label, 0, 2)

        self.id_input = QLineEdit()
        self.id_input.setPlaceholderText("اكتب الرقم ثم Enter")
        self.id_input.setFont(QFont("Segoe UI", 9))
        self.id_input.returnPressed.connect(self._load_employee)
        grid.addWidget(self.id_input, 0, 3)

        # Row 1: تاريخ من (col 0, 1) | تاريخ إلى (col 2, 3)
        date_from_label = QLabel("تاريخ من:")
        date_from_label.setFont(QFont("Segoe UI", 9, QFont.Bold))
        date_from_label.setStyleSheet("color: #5f6368; border: none;")
        grid.addWidget(date_from_label, 1, 0)

        self.date_from = QDateEdit()
        self.date_from.setCalendarPopup(True)
        self.date_from.setDisplayFormat("dd/MM/yyyy")
        self.date_from.setFont(QFont("Segoe UI", 9))
        grid.addWidget(self.date_from, 1, 1)

        date_to_label = QLabel("تاريخ إلى:")
        date_to_label.setFont(QFont("Segoe UI", 9, QFont.Bold))
        date_to_label.setStyleSheet("color: #5f6368; border: none;")
        grid.addWidget(date_to_label, 1, 2)

        self.date_to = _SelectableDateEdit()
        self.date_to.set_source(self.date_from)
        self.date_to.setCalendarPopup(True)
        self.date_to.setDisplayFormat("dd/MM/yyyy")
        self.date_to.setFont(QFont("Segoe UI", 9))
        grid.addWidget(self.date_to, 1, 3)

        # Apply Calendar Widget styling (Directive 2)
        calendar_style = """
        QCalendarWidget QWidget {
            alternate-background-color: #f8f9fa;
        }
        QCalendarWidget QAbstractItemView:enabled {
            color: #202124;
            background-color: #ffffff;
            selection-background-color: #1a73e8;
            selection-color: #ffffff;
        }
        QCalendarWidget QNavigationButton {
            color: #ffffff;
            background-color: #1a73e8;
        }
        QCalendarWidget QMenu {
            background-color: #ffffff;
            color: #202124;
        }
        """
        self.date_from.calendarWidget().setStyleSheet(calendar_style)
        self.date_to.calendarWidget().setStyleSheet(calendar_style)

        # Row 2: المتغير (col 0, 1) | الموقع (col 2, 3)
        var_label = QLabel("المتغير:")
        var_label.setFont(QFont("Segoe UI", 9, QFont.Bold))
        var_label.setStyleSheet("color: #5f6368; border: none;")
        grid.addWidget(var_label, 2, 0)

        self.var_combo = self._autocomplete_combo()
        self.var_combo.setFont(QFont("Segoe UI", 9))
        self.var_combo.editTextChanged.connect(self._on_var_combo_changed)
        grid.addWidget(self.var_combo, 2, 1)

        wp_label = QLabel("الموقع:")
        wp_label.setFont(QFont("Segoe UI", 9, QFont.Bold))
        wp_label.setStyleSheet("color: #5f6368; border: none;")
        grid.addWidget(wp_label, 2, 2)

        self.wp_combo = self._autocomplete_combo()
        self.wp_combo.setFont(QFont("Segoe UI", 9))
        grid.addWidget(self.wp_combo, 2, 3)

        combobox_style = """
        QComboBox {
            border: 1px solid #dadce0;
            border-radius: 4px;
            padding: 4px;
            background-color: #ffffff;
            color: #202124;
        }
        QComboBox::drop-down {
            subcontrol-origin: padding;
            subcontrol-position: top left; /* Left side for RTL */
            width: 25px;
            border-right: 1px solid #dadce0;
            border-top-left-radius: 4px;
            border-bottom-left-radius: 4px;
        }
        QComboBox::down-arrow {
            image: none;
            border: none;
            width: 0;
            height: 0;
            border-left: 5px solid transparent;
            border-right: 5px solid transparent;
            border-top: 5px solid #202124;
            margin-left: 5px;
        }
        QComboBox QAbstractItemView {
            background-color: #ffffff;
            color: #202124;
            selection-background-color: #1a73e8;
            selection-color: #ffffff;
            border: 1px solid #dadce0;
        }
        """
        self.var_combo.setStyleSheet(combobox_style)
        self.wp_combo.setStyleSheet(combobox_style)

        # Row 3: "ترحيل متغير" Button placed directly below Variable and Location comboboxes (Directive 5)
        self.transfer_var_btn = self._action_button("ترحيل متغير", "#1a73e8", "#1557b0")
        self.transfer_var_btn.clicked.connect(self._transfer_variable)
        grid.addWidget(self.transfer_var_btn, 3, 0, 1, 4)

        # Separator line
        sep = QFrame()
        sep.setFrameShape(QFrame.HLine)
        sep.setFrameShadow(QFrame.Sunken)
        sep.setStyleSheet("color: #e8eaed;")
        grid.addWidget(sep, 4, 0, 1, 4)

        # Row 5: Permission Radio Buttons (Directive 4)
        perm_label = QLabel("نوع الإذن:")
        perm_label.setFont(QFont("Segoe UI", 9, QFont.Bold))
        perm_label.setStyleSheet("color: #5f6368; border: none;")
        grid.addWidget(perm_label, 5, 0)

        radio_layout = QHBoxLayout()
        radio_layout.setSpacing(20)
        self.radio_perm_1 = QRadioButton("إذن (1)")
        self.radio_perm_x = QRadioButton("إذن (x)")
        self.radio_perm_1.setChecked(True)
        self.perm_btn_group = QButtonGroup(self)
        self.perm_btn_group.addButton(self.radio_perm_1)
        self.perm_btn_group.addButton(self.radio_perm_x)
        radio_layout.addWidget(self.radio_perm_1)
        radio_layout.addWidget(self.radio_perm_x)
        radio_layout.addStretch()
        grid.addLayout(radio_layout, 5, 1, 1, 3)

        # Row 6: Permission Action Buttons directly below radio buttons (Directive 4)
        perm_btn_row = QHBoxLayout()
        perm_btn_row.setSpacing(6)
        self.transfer_perm_btn = self._action_button("ترحيل إذن", "#34a853", "#2d9249")
        self.transfer_perm_btn.clicked.connect(self._transfer_permission)
        perm_btn_row.addWidget(self.transfer_perm_btn, 1)

        self.cancel_perm_btn = self._action_button("إلغاء إذن", "#f9ab00", "#e09b00")
        self.cancel_perm_btn.clicked.connect(self._cancel_permission)
        perm_btn_row.addWidget(self.cancel_perm_btn, 1)

        grid.addLayout(perm_btn_row, 6, 0, 1, 4)

        layout.addLayout(grid)
        return panel

    def _build_info_panel(self):
        panel = QFrame()
        panel.setStyleSheet(
            "QFrame { background-color: #ffffff; border: 1px solid #dadce0; border-radius: 8px; }"
        )
        layout = QVBoxLayout(panel)
        layout.setContentsMargins(8, 5, 8, 5)
        layout.setSpacing(3)

        header = QLabel("بيان العامل")
        header.setFont(QFont("Segoe UI", 10, QFont.Bold))
        header.setStyleSheet("color: #1a73e8; border: none;")
        layout.addWidget(header)

        grid = QGridLayout()
        grid.setHorizontalSpacing(8)
        grid.setVerticalSpacing(4)

        self.info_labels = {}
        fields = [
            ("name", "الاسم:", 0, 0),
            ("job", "الوظيفة:", 0, 1),
            ("work_place", "القوة:", 1, 0),
            ("t3akod", "نوع التعاقد:", 1, 1),
        ]

        for key, text, row, col in fields:
            card = QFrame()
            card.setStyleSheet(
                "QFrame { background-color: #f8f9fa; border: 1px solid #e8eaed; border-radius: 6px; }"
            )
            card_layout = QHBoxLayout(card)
            card_layout.setContentsMargins(6, 2, 6, 2)
            card_layout.setSpacing(6)

            k_label = QLabel(text)
            k_label.setFont(QFont("Segoe UI", 9, QFont.Bold))
            k_label.setStyleSheet("color: #5f6368; border: none;")
            k_label.setFixedWidth(65)
            card_layout.addWidget(k_label)

            v_label = QLabel("-")
            v_label.setFont(QFont("Segoe UI", 9, QFont.Bold))
            v_label.setStyleSheet("color: #202124; border: none;")
            v_label.setWordWrap(True)
            card_layout.addWidget(v_label, 1)

            grid.addWidget(card, row, col)
            self.info_labels[key] = v_label

        layout.addLayout(grid)
        return panel

    def _build_report_panel(self):
        panel = QFrame()
        panel.setStyleSheet(
            "QFrame { background-color: #ffffff; border: 1px solid #dadce0; border-radius: 8px; }"
        )
        layout = QVBoxLayout(panel)
        layout.setContentsMargins(6, 6, 6, 6)
        layout.setSpacing(4)

        header_layout = QHBoxLayout()
        self.lbl_report_title = QLabel("تقرير الشهور السابقة")
        self.lbl_report_title.setFont(QFont("Segoe UI", 10, QFont.Bold))
        self.lbl_report_title.setStyleSheet("color: #1a73e8; border: none;")
        header_layout.addWidget(self.lbl_report_title)
        header_layout.addStretch()
        layout.addLayout(header_layout)

        self.report_table = QTableWidget()
        self.report_table.setColumnCount(7)
        self.report_table.setHorizontalHeaderLabels([
            "الشهر", "x", "DX", "DI", "T", "WH", "الاجمالي"
        ])
        self.report_table.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        self.report_table.verticalHeader().setVisible(False)
        self.report_table.setAlternatingRowColors(True)
        self.report_table.setEditTriggers(QTableWidget.NoEditTriggers)
        self.report_table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.report_table.setSelectionMode(QAbstractItemView.SingleSelection)
        self.report_table.setStyleSheet("""
            QTableWidget {
                background-color: #ffffff;
                alternate-background-color: #f8f9fa;
                gridline-color: #e8eaed;
                color: #202124;
                border: 1px solid #dadce0;
                border-radius: 4px;
            }
            QHeaderView::section {
                background-color: #f1f3f4;
                color: #202124;
                padding: 6px;
                border: 1px solid #e8eaed;
                font-weight: bold;
            }
        """)
        layout.addWidget(self.report_table, 1)
        return panel

    def _build_movements_panel(self):
        panel = QFrame()
        panel.setStyleSheet(
            "QFrame { background-color: #ffffff; border: 1px solid #dadce0; border-radius: 8px; }"
        )
        layout = QVBoxLayout(panel)
        layout.setContentsMargins(6, 6, 6, 6)
        layout.setSpacing(4)

        label = QLabel("تحركات الشهر")
        label.setFont(QFont("Segoe UI", 10, QFont.Bold))
        label.setStyleSheet("color: #1a73e8; border: none; padding: 2px 4px;")
        layout.addWidget(label)

        self.table_days = QTableWidget(0, 4)
        self.movements_table = self.table_days  # Backward-compatible alias
        self.table_days.setHorizontalHeaderLabels(
            ["الاذن / الملاحظات", "تاريخ اليوم", "المتغير", "الموقع"]
        )
        self.table_days.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.table_days.setSelectionMode(QAbstractItemView.SingleSelection)
        self.table_days.setEditTriggers(QTableWidget.NoEditTriggers)
        self.table_days.setVerticalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.table_days.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.table_days.setFont(QFont("Segoe UI", 8, QFont.Bold))
        self.table_days.setAlternatingRowColors(True)
        self.table_days.setStyleSheet(
            "QTableWidget { background-color: #ffffff; alternate-background-color: #f8f9fa; "
            "border: 1px solid #e8eaed; border-radius: 6px; gridline-color: #e8eaed; color: #202124; }"
            "QHeaderView::section { background-color: #f1f3f4; color: #3c4043; font-weight: bold; "
            "padding: 1px 3px; border: 1px solid #e8eaed; font-size: 11px; }"
            "QTableWidget::item { padding: 0px 2px; color: #202124; }"
            "QTableWidget::item:selected { background-color: #e8f0fe; color: #1a73e8; font-weight: bold; }"
        )

        header = self.table_days.horizontalHeader()
        header.setSectionResizeMode(0, QHeaderView.Stretch)
        header.setSectionResizeMode(1, QHeaderView.ResizeToContents)
        header.setSectionResizeMode(2, QHeaderView.Stretch)
        header.setSectionResizeMode(3, QHeaderView.Stretch)
        header.setDefaultAlignment(Qt.AlignCenter)
        header.setFixedHeight(24)

        vheader = self.table_days.verticalHeader()
        vheader.setSectionResizeMode(QHeaderView.Stretch)
        vheader.setMinimumSectionSize(10)
        vheader.setDefaultSectionSize(16)
        vheader.setStyleSheet(
            "QHeaderView::section { background-color: #f8f9fa; color: #5f6368; "
            "font-size: 10px; font-weight: bold; border: none; border-bottom: 1px solid #e8eaed; padding: 0 1px; }"
        )

        self.table_days.cellClicked.connect(self._on_movement_clicked)
        layout.addWidget(self.table_days, 1)
        return panel

    def _build_bottom_bar(self):
        bar = QFrame()
        bar.setStyleSheet(
            "QFrame { background-color: #ffffff; border: 1px solid #dadce0; border-radius: 8px; }"
        )
        bar.setFixedHeight(44)
        layout = QHBoxLayout(bar)
        layout.setContentsMargins(12, 0, 12, 0)
        layout.addStretch()

        back_btn = QPushButton("رجوع")
        back_btn.setMinimumHeight(32)
        back_btn.setMinimumWidth(100)
        back_btn.setCursor(Qt.PointingHandCursor)
        back_btn.setStyleSheet(
            "QPushButton { background-color: #f8f9fa; color: #3c4043; "
            "border: 1px solid #dadce0; border-radius: 6px; font-size: 13px; font-weight: bold; padding: 0 14px; }"
            "QPushButton:hover { background-color: #e8eaed; }"
        )
        back_btn.clicked.connect(self.close)
        layout.addWidget(back_btn)
        return bar

    def _month_button(self, text):
        btn = QPushButton(text)
        btn.setFixedSize(28, 30)
        btn.setCursor(Qt.PointingHandCursor)
        btn.setStyleSheet(
            "QPushButton { background-color: #f1f3f4; color: #1a73e8; "
            "border: 1px solid #dadce0; border-radius: 6px; font-size: 14px; font-weight: bold; }"
            "QPushButton:hover { background-color: #e8eaed; }"
        )
        return btn

    def _autocomplete_combo(self):
        combo = QComboBox()
        combo.setEditable(True)
        combo.setInsertPolicy(QComboBox.NoInsert)
        completer = QCompleter([], combo)
        completer.setFilterMode(Qt.MatchContains)
        completer.setCompletionMode(QCompleter.PopupCompletion)
        combo.setCompleter(completer)
        return combo

    def _action_button(self, text, color, hover_color=None):
        btn = QPushButton(text)
        btn.setMinimumHeight(32)
        btn.setCursor(Qt.PointingHandCursor)
        hover = hover_color or color
        btn.setStyleSheet(
            f"QPushButton {{ background-color: {color}; color: white; "
            f"border: none; border-radius: 6px; font-size: 13px; font-weight: bold; padding: 0 8px; }}"
            f"QPushButton:hover {{ background-color: {hover}; }}"
        )
        return btn

    # === تحميل البيانات الثابتة ===

    def _load_static_data(self):
        try:
            self.variables_data = self.db.get_variables(
                self.config.get_timesheet_db(),
                self.config.get_password("timesheet"),
            )
        except Exception:
            self.variables_data = []
        try:
            self.workplaces_data = self.db.get_workplaces(
                self.config.get_timesheet_db(),
                self.config.get_password("timesheet"),
            )
        except Exception:
            self.workplaces_data = []

        names = [v["var_name"] for v in self.variables_data]
        self.var_combo.clear()
        self.var_combo.addItems(names)
        self.var_combo.setCurrentText("")
        self.var_combo.completer().setModel(self.var_combo.model())

        wp_names = [w["workplace"] for w in self.workplaces_data]
        self.wp_combo.clear()
        self.wp_combo.addItems(wp_names)
        self.wp_combo.setCurrentText("")
        self.wp_combo.completer().setModel(self.wp_combo.model())

        self.variables_list.blockSignals(True)
        self.variables_list.clear()
        for v in self.variables_data:
            self.variables_list.addItem(v["var_name"])
        self.variables_list.blockSignals(False)

    # === الربط الثنائي ===

    def _on_list_selected(self, row):
        if row < 0 or row >= len(self.variables_data):
            return
        name = self.variables_data[row]["var_name"]
        self.var_combo.blockSignals(True)
        self.var_combo.setCurrentText(name)
        self.var_combo.blockSignals(False)

    def _on_var_combo_changed(self, text):
        text = text.strip()
        if not text:
            return
        for idx, v in enumerate(self.variables_data):
            if v["var_name"] == text:
                self.variables_list.blockSignals(True)
                self.variables_list.setCurrentRow(idx)
                self.variables_list.blockSignals(False)
                return

    # === تحميل بيانات العامل ===

    def _load_employee(self):
        raw = self.id_input.text().strip()
        if not raw:
            return
        try:
            emp_id = float(raw)
        except ValueError:
            QMessageBox.warning(self, "تنبيه", "الرقم المالي غير صحيح")
            self.id_input.selectAll()
            self.id_input.setFocus()
            self.info_labels["name"].setText("-")
            self.info_labels["job"].setText("-")
            self.info_labels["work_place"].setText("-")
            self.info_labels["t3akod"].setText("-")
            self.current_emp_id = None
            self.table_days.setRowCount(0)
            self.report_table.setRowCount(0)
            self.transfer_var_btn.setEnabled(False)
            self.transfer_perm_btn.setEnabled(False)
            self.cancel_perm_btn.setEnabled(False)
            return

        main_pwd = self.config.get_password("main")
        info = None
        try:
            info = self.db.get_employee_full_info(
                self.config.get_main_db(), emp_id, main_pwd
            )
        except Exception as e:
            QMessageBox.critical(self, "خطأ", "تعذر الاتصال بقاعدة البيانات:\n" + str(e))
            return

        if not info:
            QMessageBox.warning(self, "تنبيه", "الرقم المالي غير موجود ببيانات العاملين!")
            self.id_input.selectAll()
            self.id_input.setFocus()
            self.info_labels["name"].setText("-")
            self.info_labels["job"].setText("-")
            self.info_labels["work_place"].setText("-")
            self.info_labels["t3akod"].setText("-")
            self.current_emp_id = None
            self.table_days.setRowCount(0)
            self.report_table.setRowCount(0)
            self.transfer_var_btn.setEnabled(False)
            self.transfer_perm_btn.setEnabled(False)
            self.cancel_perm_btn.setEnabled(False)
            return

        self.current_emp_id = emp_id
        self.info_labels["name"].setText(info["name"])
        self.info_labels["job"].setText(info["job"])
        self.info_labels["work_place"].setText(info["work_place"])
        self.info_labels["t3akod"].setText(info["t3akod"])

        self.transfer_var_btn.setEnabled(True)
        self.transfer_perm_btn.setEnabled(True)
        self.cancel_perm_btn.setEnabled(True)

        self._validate_month_input()
        self._load_movements()
        self._load_report()
        
        # Upon successfully loading the employee, advance focus to Date From
        self.date_from.setFocus()

    def _validate_month_input(self):
        raw = self.month_input.text().strip()
        if len(raw) == 6 and raw.isdigit():
            self.current_issue = raw
        else:
            self.current_issue = QDate.currentDate().toString("yyyyMM")
            self.month_input.setText(self.current_issue)

    def _load_movements(self):
        if self.current_emp_id is None or not self.current_issue:
            return
        try:
            movements = self.db.get_month_movements(
                self.config.get_timesheet_db(),
                self.current_issue,
                self.current_emp_id,
                self.config.get_password("timesheet"),
            )
        except Exception as e:
            QMessageBox.critical(self, "خطأ", "تعذر قراءة حركات الشهر:\n" + str(e))
            return

        var_abbr_map = {v["code"]: (v.get("var") or v["var_name"]) for v in self.variables_data}
        wp_name_map = {w["code"]: w["workplace"] for w in self.workplaces_data}

        self.table_days.setRowCount(len(movements))
        for row, m in enumerate(movements):
            date_item = QTableWidgetItem(self._fmt_date(m["date"]))
            var_text = var_abbr_map.get(m["var"], str(m["var"]) if m["var"] else "")
            var_item = QTableWidgetItem(var_text)
            wp_text = wp_name_map.get(m["wp"], str(m["wp"]) if m["wp"] else "")
            wp_item = QTableWidgetItem(wp_text)
            notes_item = QTableWidgetItem(m["notes"])

            for item, col in [
                (notes_item, 0), (date_item, 1), (var_item, 2), (wp_item, 3)
            ]:
                item.setTextAlignment(Qt.AlignCenter)
                self.table_days.setItem(row, col, item)

    def _load_report(self):
        if self.current_emp_id is None:
            return
        self._validate_month_input()
        end_year = int(self.current_issue[:4])
        end_month = int(self.current_issue[4:])
        end_issue = end_year * 100 + end_month
        start_issue = self._add_months(end_issue, -23)  # Exactly last 24 calendar months

        try:
            report = self.db.get_attendance_report(
                self.config.get_timesheet_db(),
                self.current_emp_id,
                start_issue,
                end_issue,
                self.config.get_password("timesheet"),
            )
        except Exception as e:
            QMessageBox.critical(self, "خطأ", "تعذر قراءة التقرير:\n" + str(e))
            return

        self.report_table.setRowCount(24)
        for offset in range(24):
            issue = self._add_months(start_issue, offset)
            year = issue // 100
            month = issue % 100
            label = self._month_name(month, year)
            counts = report.get(str(issue), {})
            
            c_x = counts.get(1, 0)
            c_dx = counts.get(2, 0)
            c_di = counts.get(3, 0)
            c_t = counts.get(4, 0)
            c_wh = counts.get(35, 0)
            total = c_x + c_dx + c_di + c_t + c_wh

            row_values = [
                label,
                str(c_x),
                str(c_dx),
                str(c_di),
                str(c_t),
                str(c_wh),
                str(total)
            ]

            for col_idx, val in enumerate(row_values):
                item = QTableWidgetItem(val)
                item.setTextAlignment(Qt.AlignCenter)
                item.setFlags(Qt.ItemIsEnabled | Qt.ItemIsSelectable)
                self.report_table.setItem(offset, col_idx, item)

    def _add_months(self, base_issue, offset):
        total = (base_issue // 100) * 12 + (base_issue % 100) - 1 + offset
        year, month = divmod(total, 12)
        return year * 100 + month + 1

    def _months_between(self, start_issue, end_issue):
        return (end_issue // 100 * 12 + end_issue % 100) - (start_issue // 100 * 12 + start_issue % 100)

    def _month_name(self, month, year):
        names = ["يناير", "فبراير", "مارس", "ابريل", "مايو", "يونيو",
                 "يوليو", "اغسطس", "سبتمبر", "اكتوبر", "نوفمبر", "ديسمبر"]
        return names[month - 1] + " " + str(year)

    # === تفريغ/تعبئة الحقول ===

    def _fmt_date(self, value):
        if isinstance(value, datetime.datetime) or isinstance(value, datetime.date):
            return value.strftime("%d/%m/%Y")
        return str(value)

    def _to_date(self, qdate):
        return datetime.date(qdate.year(), qdate.month(), qdate.day())

    def _resolve_var(self):
        text = self.var_combo.currentText().strip()
        if not text:
            return None, None
        for v in self.variables_data:
            if v["var_name"] == text or v.get("var") == text:
                return v["code"], v["var_name"]
        if text.isdigit():
            for v in self.variables_data:
                if v["code"] == int(text):
                    return v["code"], v["var_name"]
        return None, None

    def _resolve_wp(self):
        text = self.wp_combo.currentText().strip()
        if not text:
            return None, None
        for w in self.workplaces_data:
            if w["workplace"] == text or w.get("wp") == text:
                return w["code"], w["workplace"]
        if text.isdigit():
            for w in self.workplaces_data:
                if w["code"] == int(text):
                    return w["code"], w["workplace"]
        return None, None

    def _get_range_dates(self):
        start = self._to_date(self.date_from.date())
        end = self._to_date(self.date_to.date())
        if end < start:
            start, end = end, start
        dates = []
        d = start
        while d <= end:
            dates.append(d)
            d += datetime.timedelta(days=1)
        return dates

    def _check_ready(self):
        if self.current_emp_id is None:
            QMessageBox.warning(self, "تنبيه", "برجاء ادخال الرقم المالي اولا")
            return False
        self._validate_month_input()
        return True

    def _count_permission_in_month(self, code):
        count = 0
        target = code.strip().lower()
        for row in range(self.table_days.rowCount()):
            item = self.table_days.item(row, 0)
            if item and item.text().strip().lower() == target:
                count += 1
        return count

    # === أزرار التنفيذ ===

    def _transfer_variable(self):
        if not self._check_ready():
            return
        var_code, var_name = self._resolve_var()
        wp_code, wp_name = self._resolve_wp()

        if var_code is None:
            QMessageBox.warning(self, "تنبيه", "برجاء اختيار المتغير")
            self.var_combo.setFocus()
            return

        dates = self._get_range_dates()
        missing = []
        for d in dates:
            try:
                exists = self.db.movement_exists(
                    self.config.get_timesheet_db(),
                    self.current_issue,
                    self.current_emp_id,
                    d,
                    self.config.get_password("timesheet"),
                )
            except Exception as e:
                QMessageBox.critical(self, "خطأ", str(e))
                return
            if not exists:
                missing.append(d)

        if missing:
            QMessageBox.warning(
                self, "تنبيه",
                "لا يوجد سجل - يجب ادراج شهر جديد في جدول الحضور"
            )
            return

        # Instant local memory UI update (Directive 7)
        var_abbr = next((v.get("var") or v["var_name"] for v in self.variables_data if v["code"] == var_code), str(var_code))
        date_strs = {d.strftime("%d/%m/%Y") for d in dates}
        for row in range(self.table_days.rowCount()):
            d_item = self.table_days.item(row, 1)
            if d_item and d_item.text() in date_strs:
                v_item = self.table_days.item(row, 2)
                w_item = self.table_days.item(row, 3)
                if v_item:
                    v_item.setText(var_abbr)
                if w_item:
                    w_item.setText(wp_name or "")

        for d in dates:
            try:
                self.db.update_movement_var(
                    self.config.get_timesheet_db(),
                    self.current_issue,
                    self.current_emp_id,
                    d,
                    var_code,
                    wp_code,
                    self.config.get_password("timesheet"),
                )
            except Exception as e:
                QMessageBox.critical(self, "خطأ", str(e))
                return

        self._load_report()
        QMessageBox.information(self, "تم", "تم ترحيل المتغير بنجاح")

    def _transfer_permission(self):
        if not self._check_ready():
            return
        perm_code = "1" if self.radio_perm_1.isChecked() else "x"

        current = self._count_permission_in_month(perm_code)
        if current + len(self._get_range_dates()) > self.MAX_PERMISSIONS_PER_TYPE:
            QMessageBox.warning(
                self, "رفض",
                "تم تجاوز الحد المسموح من هذا النوع لهذا الشهر - الغاء العملية"
            )
            return

        dates = self._get_range_dates()
        missing = []
        for d in dates:
            try:
                exists = self.db.movement_exists(
                    self.config.get_timesheet_db(),
                    self.current_issue,
                    self.current_emp_id,
                    d,
                    self.config.get_password("timesheet"),
                )
            except Exception as e:
                QMessageBox.critical(self, "خطأ", str(e))
                return
            if not exists:
                missing.append(d)

        if missing:
            QMessageBox.warning(
                self, "تنبيه",
                "لا يوجد سجل - يجب ادراج شهر جديد في جدول الحضور"
            )
            return

        # Instant local memory UI update (Directive 7)
        date_strs = {d.strftime("%d/%m/%Y") for d in dates}
        for row in range(self.table_days.rowCount()):
            d_item = self.table_days.item(row, 1)
            if d_item and d_item.text() in date_strs:
                n_item = self.table_days.item(row, 0)
                if n_item:
                    n_item.setText(perm_code)

        for d in dates:
            try:
                self.db.update_movement_notes(
                    self.config.get_timesheet_db(),
                    self.current_issue,
                    self.current_emp_id,
                    d,
                    perm_code,
                    self.config.get_password("timesheet"),
                )
            except Exception as e:
                QMessageBox.critical(self, "خطأ", str(e))
                return

        QMessageBox.information(self, "تم", "تم ترحيل الاذن بنجاح")

    def _cancel_permission(self):
        if not self._check_ready():
            return
        date = self._to_date(self.date_from.date())
        if date.strftime("%Y%m") != self.current_issue:
            QMessageBox.warning(self, "تنبيه", "برجاء اختيار التاريخ")
            return
        try:
            exists = self.db.movement_exists(
                self.config.get_timesheet_db(),
                self.current_issue,
                self.current_emp_id,
                date,
                self.config.get_password("timesheet"),
            )
        except Exception as e:
            QMessageBox.critical(self, "خطأ", str(e))
            return
        if not exists:
            QMessageBox.warning(
                self, "تنبيه",
                "لا يوجد سجل - يجب ادراج شهر جديد في جدول الحضور"
            )
            return

        # Instant local memory UI update (Directive 7)
        d_str = date.strftime("%d/%m/%Y")
        for row in range(self.table_days.rowCount()):
            d_item = self.table_days.item(row, 1)
            if d_item and d_item.text() == d_str:
                n_item = self.table_days.item(row, 0)
                if n_item:
                    n_item.setText("")
                break

        try:
            # Directive 6: Notes set to NULL only, variables/workplaces remain untouched
            self.db.update_movement_notes(
                self.config.get_timesheet_db(),
                self.current_issue,
                self.current_emp_id,
                date,
                None,
                self.config.get_password("timesheet"),
            )
        except Exception as e:
            QMessageBox.critical(self, "خطأ", str(e))
            return

        QMessageBox.information(self, "تم", "تم الغاء الاذن")

    def _parse_date(self, text):
        try:
            parts = text.split("/")
            day, month, year = int(parts[0]), int(parts[1]), int(parts[2])
            return datetime.date(year, month, day)
        except (ValueError, IndexError):
            return None

    def _shift_month(self, delta):
        raw = self.month_input.text().strip()
        if len(raw) != 6 or not raw.isdigit():
            raw = QDate.currentDate().toString("yyyyMM")
        year = int(raw[:4])
        month = int(raw[4:])
        prev_year = year
        month += delta
        if month < 1:
            month = 12
            year -= 1
        elif month > 12:
            month = 1
            year += 1
        self.month_input.setText(f"{year:04d}{month:02d}")
        if self.current_emp_id is not None:
            self.current_issue = self.month_input.text()
            self._load_movements()
            if year != prev_year:
                self._load_report()

    # === استرجاع صف عند النقر ===

    def _on_movement_clicked(self, row, col):
        date_item = self.table_days.item(row, 1)
        var_item = self.table_days.item(row, 2)
        wp_item = self.table_days.item(row, 3)
        notes_item = self.table_days.item(row, 0)

        if date_item:
            date = self._parse_date(date_item.text())
            if date:
                qdate = QDate(date.year, date.month, date.day)
                self.date_from.setDate(qdate)
                self.date_to.setDate(qdate)

        if var_item and var_item.text().strip():
            abbr = var_item.text().strip()
            matching_var = None
            for idx, v in enumerate(self.variables_data):
                if v.get("var") == abbr or v["var_name"] == abbr or str(v["code"]) == abbr:
                    matching_var = (idx, v)
                    break
            if matching_var:
                idx, v = matching_var
                self.var_combo.blockSignals(True)
                self.var_combo.setCurrentText(v["var_name"])
                self.var_combo.blockSignals(False)
                self.variables_list.blockSignals(True)
                self.variables_list.setCurrentRow(idx)
                self.variables_list.blockSignals(False)

        if wp_item and wp_item.text().strip():
            wp_text = wp_item.text().strip()
            self.wp_combo.blockSignals(True)
            self.wp_combo.setCurrentText(wp_text)
            self.wp_combo.blockSignals(False)

        if notes_item:
            notes_text = notes_item.text().strip()
            if notes_text == "1":
                self.radio_perm_1.setChecked(True)
            elif notes_text.lower() == "x":
                self.radio_perm_x.setChecked(True)