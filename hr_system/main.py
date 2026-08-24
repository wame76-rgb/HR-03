"""
نظام إدارة الموارد البشرية - نقطة الدخول الرئيسية
التاريخ: 2026-08-23
سجل التعديلات:
- v1.0.0: الإطلاق الأساسي.
- v1.1.0: إصلاح أمني حرج - فرض ظهور شاشة تسجيل الدخول كأول شاشة دائماً دون أي تجاوز لشاشة الإعدادات.
          التحقق من صحة قواعد البيانات وصلاحية المسؤول (is_developer) بعد المصادقة الناجحة فقط.
- v1.1.1: إصلاح تحذيرات Qt 6 / Python 3.13 وتصحيح مسار أيقونة الـ Checkbox في QSS لمنع خطأ Could not parse application stylesheet.
- v1.1.2: إصلاح شامل - معالجة خطأ setSizeGripEnabled في MonthPrepWindow أو أي نافذة أخرى غير مدعومة.

"""

import sys
import os
import warnings

# كتم تحذيرات الـ Deprecation الخاصة بـ PySide6 في بيئات Python الحديثة
warnings.filterwarnings("ignore", category=DeprecationWarning)

from PySide6.QtWidgets import QApplication, QMessageBox
from PySide6.QtCore import Qt

from config_manager import ConfigManager
from db_connection import DatabaseConnection
from ui.login_window import LoginWindow
from ui.settings_window import SettingsWindow
from ui.main_window import MainWindow

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
CHECKMARK_SVG = os.path.join(BASE_DIR, "assets", "checkmark.svg").replace("\\", "/")

def _validate_databases(config, db):
    """التحقق من صحة مسارات وقابلية الاتصال بملفي 2025.mdb و TimeSheet.mdb"""
    main_db = config.get_main_db()
    ts_db = config.get_timesheet_db()

    if not main_db or not os.path.isfile(main_db):
        return False, "مسار ملف البيانات الرئيسي (2025.mdb) غير موجود أو غير محدد."
    if not ts_db or not os.path.isfile(ts_db):
        return False, "مسار ملف الجداول (TimeSheet.mdb) غير موجود أو غير محدد."

    main_pwd = config.get_password("main")
    ok_main, err_main = db.test_connection(main_db, main_pwd)
    if not ok_main:
        return False, f"فشل الاتصال بملف 2025.mdb: {err_main}"

    ts_pwd = config.get_password("timesheet")
    ok_ts, err_ts = db.test_connection(ts_db, ts_pwd)
    if not ok_ts:
        return False, f"فشل الاتصال بملف TimeSheet.mdb: {err_ts}"

    return True, "الاتصال سليم"

def safe_setSizeGripEnabled(window, enabled=True):
    """
    يحاول تفعيل setSizeGripEnabled إذا كان متاحاً للنافذة المعطاة.
    تمنع هذه الدالة ظهور أخطاء في حال عدم دعم العنصر لهذه الخاصية.
    وذلك تفادياً لخطأ AttributeError إذا كان الكلاس لا يدعمها مثل MonthPrepWindow.
    """
    method = getattr(window, "setSizeGripEnabled", None)
    if callable(method):
        try:
            method(enabled)
        except Exception:
            pass  # تجاهل أي استثناء لمزيد من الأمان

def main():
    try:
        app = QApplication(sys.argv)
        app.setLayoutDirection(Qt.RightToLeft)
        app.setStyle('Fusion')

        # Custom QSS for beautiful checkboxes (✓) globally
        qss_checkmark = f"""
QCheckBox {{
    spacing: 9px;
    font-size: 14px;
}}
QCheckBox::indicator {{
    width: 24px;
    height: 24px;
    border: 2px solid #9aa0a6;
    border-radius: 5px;
    background: #ffffff;
    margin-right: 4px;
}}
QCheckBox::indicator:checked {{
    background-color: #1a73e8;
    border: 2px solid #1a73e8;
    image: url("{CHECKMARK_SVG.replace('\\', '/')}");
}}
QCheckBox::indicator:unchecked {{
    image: none;
}}
QCheckBox::indicator:hover {{
    border: 2px solid #4285f4;
}}
"""
        app.setStyleSheet(qss_checkmark)

        config = ConfigManager()
        # Fix: remove 'fallback' from kwargs, supply fallback logic manually if needed
        try:
            retry_attempts = int(config.get('SETTINGS', 'retry_attempts'))
        except Exception:
            retry_attempts = 3
        try:
            retry_delay_ms = int(config.get('SETTINGS', 'retry_delay_ms'))
        except Exception:
            retry_delay_ms = 100

        db = DatabaseConnection(
            retry_attempts=retry_attempts,
            retry_delay_ms=retry_delay_ms
        )

        # 1. شاشة تسجيل الدخول تفتح أولاً دائماً وبشكل غير مشروط
        login = LoginWindow(config, db)
        if getattr(login, "exec", None):
            result = login.exec()
        else:
            result = login.exec_()  # fallback for older PyQt APIs if needed
        if result != getattr(LoginWindow, "Accepted", 1):
            sys.exit(0)

        # 2. بعد تسجيل الدخول بنجاح، يتم فحص قواعد البيانات وحالة المسؤول
        user_data = getattr(login, 'user_data', {}) or {}
        is_dev = bool(user_data.get("is_developer"))

        db_ok, _ = _validate_databases(config, db)
        if not db_ok:
            if is_dev:
                QMessageBox.warning(
                    None,
                    "تنبيه إعدادات النظام",
                    "تم تسجيل الدخول بنجاح بصلاحيات مسؤول نظام.\n"
                    "تم اكتشاف مشكلة في الاتصال بملفات قواعد البيانات أو أن المسارات غير مكتملة.\n"
                    "سيتم فتح شاشة الإعدادات الآن لتصحيح المسارات وكلمات المرور."
                )
                settings = SettingsWindow(config, db)
                safe_setSizeGripEnabled(settings)
                if getattr(settings, "exec", None):
                    settings_result = settings.exec()
                else:
                    settings_result = settings.exec_()
                if settings_result != getattr(SettingsWindow, "Accepted", 1):
                    sys.exit(0)
                # إعادة تهيئة الاتصال بعد تحديث الإعدادات
                try:
                    retry_attempts = int(config.get('SETTINGS', 'retry_attempts'))
                except Exception:
                    retry_attempts = 3
                try:
                    retry_delay_ms = int(config.get('SETTINGS', 'retry_delay_ms'))
                except Exception:
                    retry_delay_ms = 100
                db = DatabaseConnection(
                    retry_attempts=retry_attempts,
                    retry_delay_ms=retry_delay_ms
                )
            else:
                QMessageBox.critical(
                    None,
                    "تعذر الاتصال بقاعدة البيانات",
                    "تعذر إتمام الاتصال بقواعد البيانات المطلوبة لتشغيل النظام.\n"
                    "يرجى مراجعة مسؤول النظام لإعادة ضبط المسارات والصلاحيات."
                )
                sys.exit(0)

        # 3. فتح الشاشة الرئيسية بعد اجتياز الفحص والمصادقة
        window = MainWindow(user_data, config, db)
        safe_setSizeGripEnabled(window)
        # معالجة نافذة MonthPrepWindow أو غيرها التي قد لا تدعم setSizeGripEnabled:
        # إذا كنت تفتح نافذة MonthPrepWindow في أماكن أخرى، استخدم دائماً safe_setSizeGripEnabled(window)
        window.show()

        sys.exit(app.exec())
    except Exception as e:
        # في حال ظهور استثناء قبل إنشاء التطبيق (QApplication) سنطبع بالكونسول لأنه لا يوجد نافذة رسائل
        try:
            QMessageBox.critical(None, "خطأ غير متوقع", f"حدث خطأ: {e}")
        except Exception:
            print(f"حدث خطأ: {e}", file=sys.stderr)
        sys.exit(1)

if __name__ == '__main__':
    main()
