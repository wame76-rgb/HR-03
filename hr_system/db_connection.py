import pyodbc
import time
import calendar
from datetime import date, datetime


class DatabaseConnection:
    def __init__(self, retry_attempts=3, retry_delay_ms=100, connect_timeout=8):
        self.retry_attempts = retry_attempts
        self.retry_delay_ms = retry_delay_ms / 1000.0
        self.connect_timeout = connect_timeout
        self._connections = {}

    def get_connection(self, db_path, password=""):
        if not db_path:
            raise ValueError("مسار قاعدة البيانات فارغ")
        key = (db_path, password)
        conn = self._connections.get(key)
        if conn is not None:
            try:
                # التحقق من أن الاتصال لا يزال نشطاً
                cursor = conn.cursor()
                cursor.execute("SELECT 1")
                cursor.fetchone()
                return conn
            except Exception:
                try:
                    conn.close()
                except Exception:
                    pass
                self._connections.pop(key, None)

        conn_str = f"DRIVER={{Microsoft Access Driver (*.mdb, *.accdb)}};DBQ={db_path};"
        if password:
            conn_str += f"PWD={password};"
        # timeout محدد يمنع تعليق الاتصال عند انقطاع الشبكة أو قفل الملف
        conn = pyodbc.connect(conn_str, timeout=self.connect_timeout)
        self._connections[key] = conn
        return conn

    def connect(self, db_path, password=""):
        return self.get_connection(db_path, password)

    def close_all(self):
        for key, conn in list(self._connections.items()):
            try:
                conn.close()
            except Exception:
                pass
        self._connections.clear()

    def execute_with_retry(self, db_path, operation, password=""):
        last_error = None
        for attempt in range(self.retry_attempts):
            try:
                conn = self.get_connection(db_path, password)
                result = operation(conn)
                conn.commit()
                return result
            except InterruptedError as e:
                # إلغاء المستخدم: لا يُعاد التنفيذ إطلاقاً
                raise e
            except (pyodbc.Error, Exception) as e:
                last_error = e
                key = (db_path, password)
                if key in self._connections:
                    try:
                        self._connections[key].close()
                    except Exception:
                        pass
                    self._connections.pop(key, None)
                if attempt < self.retry_attempts - 1:
                    time.sleep(self.retry_delay_ms * (attempt + 1))
                continue
        raise last_error

    def test_connection(self, db_path, password=""):
        try:
            conn = self.get_connection(db_path, password)
            cursor = conn.cursor()
            cursor.execute("SELECT 1")
            cursor.fetchone()
            return True, "تم الاتصال بنجاح"
        except Exception as e:
            return False, "فشل الاتصال: " + str(e)

    def authenticate(self, main_db_path, user_id, password, db_password=""):
        def op(conn):
            cursor = conn.cursor()
            query = (
                "SELECT e.ID, e.agor, e.IsDeveloper, b.name "
                "FROM edary e "
                "LEFT JOIN basic b ON e.ID = b.ID "
                "WHERE e.ID = ? AND e.passowrd = ?"
            )
            cursor.execute(query, (user_id, password))
            row = cursor.fetchone()
            if row:
                return {
                    "id": row[0],
                    "agor": row[1],
                    "is_developer": row[2],
                    "name": row[3] or "مستخدم"
                }
            return None
        return self.execute_with_retry(main_db_path, op, db_password)

    def get_employee_name(self, main_db_path, user_id, db_password=""):
        def op(conn):
            cursor = conn.cursor()
            cursor.execute("SELECT name FROM basic WHERE ID = ?", (user_id,))
            row = cursor.fetchone()
            return row[0] if row else None
        return self.execute_with_retry(main_db_path, op, db_password)

    def get_employee_full_info(self, main_db_path, user_id, db_password=""):
        """بيان العامل الكامل: الاسم، الوظيفة، القوة، نوع التعاقد"""
        def op(conn):
            cursor = conn.cursor()
            query = (
                "SELECT b.name, j.jobs, wp.workplace, t.t3akod "
                "FROM (((basic b "
                "LEFT JOIN jobs j ON b.job = j.jobs_code) "
                "LEFT JOIN work_place wp ON b.work_place = wp.workplacecode) "
                "LEFT JOIN t3akod t ON b.t3akod = t.t3akod_code) "
                "WHERE b.ID = ?"
            )
            cursor.execute(query, (user_id,))
            row = cursor.fetchone()
            if row:
                return {
                    "name": row[0] or "مستخدم",
                    "job": row[1] or "",
                    "work_place": row[2] or "",
                    "t3akod": row[3] or "",
                }
            return None
        return self.execute_with_retry(main_db_path, op, db_password)

    def get_variables(self, ts_db_path, db_password=""):
        """قائمة المتغيرات من جدول variables"""
        def op(conn):
            cursor = conn.cursor()
            cursor.execute("SELECT var_code, var_name, var FROM variables ORDER BY var_code")
            rows = cursor.fetchall()
            return [{"code": int(r[0]), "var_name": r[1] or "", "var": r[2] or ""} for r in rows]
        return self.execute_with_retry(ts_db_path, op, db_password)

    def get_workplaces(self, ts_db_path, db_password=""):
        """قائمة المواقع من جدول work_place"""
        def op(conn):
            cursor = conn.cursor()
            cursor.execute("SELECT workplacecode, workplace, wp FROM work_place ORDER BY workplacecode")
            rows = cursor.fetchall()
            return [{"code": int(r[0]), "workplace": r[1] or "", "wp": r[2] or ""} for r in rows]
        return self.execute_with_retry(ts_db_path, op, db_password)

    def get_month_movements(self, ts_db_path, issue, emp_id, db_password=""):
        """حركات العامل في شهر محدد (Issue بصيغة YYYYMM)"""
        def op(conn):
            cursor = conn.cursor()
            query = (
                "SELECT EntryDate, var, wp, Notes FROM var_op "
                "WHERE Issue = ? AND EmpId = ? ORDER BY EntryDate"
            )
            cursor.execute(query, (issue, emp_id))
            rows = cursor.fetchall()
            return [
                {"date": r[0], "var": r[1], "wp": r[2], "notes": r[3] or ""}
                for r in rows
            ]
        return self.execute_with_retry(ts_db_path, op, db_password)

    def movement_exists(self, ts_db_path, issue, emp_id, entry_date, db_password=""):
        """هل يوجد سجل لهذا العامل في هذا اليوم؟"""
        def op(conn):
            cursor = conn.cursor()
            cursor.execute(
                "SELECT COUNT(*) FROM var_op WHERE Issue = ? AND EmpId = ? AND EntryDate = ?",
                (issue, emp_id, entry_date),
            )
            res = cursor.fetchone()
            return bool(res and res[0] > 0)
        return self.execute_with_retry(ts_db_path, op, db_password)

    def update_movement_var(self, ts_db_path, issue, emp_id, entry_date, var, wp, db_password=""):
        """تحديث المتغير والموقع لسجل موجود دون لمس الملاحظات"""
        def op(conn):
            cursor = conn.cursor()
            var_val = None if (var is None or var == "") else var
            wp_val = None if (wp is None or wp == "") else wp
            cursor.execute(
                "UPDATE var_op SET var = ?, wp = ? WHERE Issue = ? AND EmpId = ? AND EntryDate = ?",
                (var_val, wp_val, issue, emp_id, entry_date),
            )
            return cursor.rowcount
        return self.execute_with_retry(ts_db_path, op, db_password)

    def update_movement_notes(self, ts_db_path, issue, emp_id, entry_date, notes, db_password=""):
        """تحديث الملاحظات/الإذن لسجل موجود مع تحويل النص الفارغ إلى NULL لتوافق MS Access دون لمس المتغير أو الموقع"""
        def op(conn):
            cursor = conn.cursor()
            val = None if (notes is None or notes == "") else notes
            cursor.execute(
                "UPDATE var_op SET Notes = ? WHERE Issue = ? AND EmpId = ? AND EntryDate = ?",
                (val, issue, emp_id, entry_date),
            )
            return cursor.rowcount
        return self.execute_with_retry(ts_db_path, op, db_password)

    def get_attendance_report(self, ts_db_path, emp_id, start_issue, end_issue, db_password=""):
        """تقرير الحضور: عدد أيام كل نوع متغير (1,2,3,4,35) لكل شهر في النطاق"""
        def op(conn):
            cursor = conn.cursor()
            query = (
                "SELECT Issue, var, COUNT(*) FROM var_op "
                "WHERE EmpId = ? AND Issue BETWEEN ? AND ? AND var IN (1,2,3,4,35) "
                "GROUP BY Issue, var ORDER BY Issue, var"
            )
            cursor.execute(query, (emp_id, start_issue, end_issue))
            rows = cursor.fetchall()
            report = {}
            for issue, var, cnt in rows:
                report.setdefault(str(issue), {})[int(var)] = cnt
            return report
        return self.execute_with_retry(ts_db_path, op, db_password)

    # ==========================================
    # عمليات المحطة الخامسة: تهيئة بداية الشهر
    # ==========================================

    def is_month_initialized(self, ts_db_path, issue, db_password=""):
        """فحص عدد السجلات الموجودة مسبقاً لشهر محدد في جدول var_op"""
        def op(conn):
            cursor = conn.cursor()
            cursor.execute("SELECT COUNT(*) FROM var_op WHERE Issue = ?", (int(issue),))
            row = cursor.fetchone()
            count = row[0] if row else 0
            return (count > 0), count
        return self.execute_with_retry(ts_db_path, op, db_password)

    def get_month_present_days(self, ts_db_path, issue, db_password=""):
        """مجموعة أيام الشهر الموجودة فعلياً في var_op للشهر المستهدف (من 1 إلى آخر يوم)"""
        def op(conn):
            cursor = conn.cursor()
            cursor.execute(
                "SELECT DISTINCT DatePart('d', EntryDate) FROM var_op WHERE Issue = ?",
                (int(issue),),
            )
            return {int(r[0]) for r in cursor.fetchall() if r[0] is not None}
        return self.execute_with_retry(ts_db_path, op, db_password)

    def pre_check_month(self, ts_db_path, issue, db_password=""):
        """الفحص الصامت المسبق الموحد:
        يرجع (count, present_days) حيث count عدد سجلات الشهر الموجود،
        و present_days مجموعة أيام الشهر المتواجدة فعلياً.
        يعتمد على عمود Issue المفهرس لتجنب أي مسح شامل غير مقيد."""
        def op(conn):
            cursor = conn.cursor()
            cursor.execute("SELECT COUNT(*) FROM var_op WHERE Issue = ?", (int(issue),))
            row = cursor.fetchone()
            count = int(row[0]) if row else 0
            cursor.execute(
                "SELECT DISTINCT DatePart('d', EntryDate) FROM var_op WHERE Issue = ?",
                (int(issue),),
            )
            days = {int(r[0]) for r in cursor.fetchall() if r[0] is not None}
            return count, days
        return self.execute_with_retry(ts_db_path, op, db_password)

    def delete_month_records(self, ts_db_path, issue, db_password=""):
        """حذف آمن وغير معرقل لسجلات شهر محدد من var_op قبل إعادة التهيئة"""
        def op(conn):
            cursor = conn.cursor()
            cursor.execute("DELETE FROM var_op WHERE Issue = ?", (int(issue),))
            return cursor.rowcount
        return self.execute_with_retry(ts_db_path, op, db_password)

    def get_active_employees_count(self, main_db_path, db_password=""):
        """عدد الموظفين الفعالين (الذين لم تنته خدمتهم: enha2_date فارغ)"""
        def op(conn):
            cursor = conn.cursor()
            cursor.execute("SELECT COUNT(*) FROM basic WHERE enha2_date IS NULL")
            row = cursor.fetchone()
            return row[0] if row else 0
        return self.execute_with_retry(main_db_path, op, db_password)

    def get_active_employee_ids(self, main_db_path, db_password=""):
        """جلب قائمة معرفات (ID) الموظفين الفعالين المستمرين بالخدمة"""
        def op(conn):
            cursor = conn.cursor()
            cursor.execute("SELECT ID FROM basic WHERE enha2_date IS NULL ORDER BY ID")
            rows = cursor.fetchall()
            return [r[0] for r in rows if r[0] is not None]
        return self.execute_with_retry(main_db_path, op, db_password)

    def populate_date_prep(self, ts_db_path, dates_list, db_password=""):
        """تفريغ جدول DatePrep وإدخال تواريخ أيام الشهر المستهدف"""
        def op(conn):
            cursor = conn.cursor()
            cursor.execute("DELETE FROM DatePrep")
            insert_sql = "INSERT INTO DatePrep (EDate) VALUES (?)"
            params = [(d,) for d in dates_list]
            cursor.executemany(insert_sql, params)
            return len(dates_list)
        return self.execute_with_retry(ts_db_path, op, db_password)

    def initialize_month_records(
        self,
        ts_db_path,
        main_db_path,
        issue,
        dates_list,
        code_map,
        holidays_set=None,
        wfh_active=True,
        preserve_weekend_overrides=True,
        batch_size=200,
        main_db_password="",
        ts_db_password="",
        interrupt_check=None,
        progress_callback=None,
    ):
        """
        التهيئة الآمنة لشهر كامل (إعادة البناء المتسامحة مع الخطأ):

        خوارزمية مقاومة لانهيار HY000 والقيود الافتراضية:
        1. تعبئة جدول DatePrep بأيام الشهر المستهدف.
        2. جلب الموظفين الفعالين من basic (enha2_date IS NULL).
        3. حارس الجمعة/السبت/الأحد: جلب أي تعديلات يدوية سابقة (قيمة غير صفرية)
           وحفظها قبل أي حذف لعدم الكتابة فوقها لاحقاً.
        4. حذف سجلات الشهر الحالي من var_op إن وُجدت (بعد موافقة المستخدم).
        5. إدراج مجزأ بدفعات صغيرة (batch_size = 200 صفاً افتراضياً) مع
           conn.commit() بعد كل دفعة لمنع انسداد الشبكة وقفل السائق
           وتفادي تجاوز حدود معاملات الاستعلام الواحد.
        6. النقل الانتقائي: فقط الحالات الثلاث (H / R / WH) تُعبأ برموزها،
           أما أيام العمل العادية فتُترك بقيمتها الافتراضية (0).
        """
        issue_val = int(issue)
        holidays_set = holidays_set or set()
        code_map = code_map or {}

        # الخطوة 1: تعبئة جدول DatePrep
        self.populate_date_prep(ts_db_path, dates_list, ts_db_password)
        if progress_callback:
            progress_callback(5, "تم تجهيز جدول التواريخ DatePrep")

        # الخطوة 2: جلب أرقام العاملين النشطين
        active_emp_ids = self.get_active_employee_ids(main_db_path, main_db_password)
        total_emps = len(active_emp_ids)
        if total_emps == 0:
            raise ValueError("لم يتم العثور على أي موظفين فعالين في جدول basic (حقل enha2_date فارغ).")

        if progress_callback:
            progress_callback(10, f"تم حصر {total_emps} موظف فعال")

        # خريطة التاريخ -> رمز المتغير (0 لأيام العمل العادية)
        day_var_map = {}
        for dt in dates_list:
            dow = dt.weekday()  # Monday=0 ... Sunday=6
            if dt in holidays_set or dt.strftime("%Y-%m-%d") in holidays_set:
                day_var_map[dt] = int(code_map.get('H') or 0)
            elif dow in (4, 5):  # الجمعة والسبت
                day_var_map[dt] = int(code_map.get('R') or 0)
            elif dow == 6 and wfh_active:  # الأحد مع تفعيل العمل عن بعد
                day_var_map[dt] = int(code_map.get('WH') or 0)
            else:
                day_var_map[dt] = 0

        def op(conn):
            cursor = conn.cursor()

            # الخطوة 3: حارس الجمعة/السبت/الأحد — حفظ التعديلات اليدوية السابقة
            preserved = {}
            if preserve_weekend_overrides:
                weekend_days = [dt for dt in dates_list if dt.weekday() in (4, 5, 6)]
                if weekend_days:
                    day_nums = sorted({dt.day for dt in weekend_days})
                    placeholders = ",".join("?" * len(day_nums))
                    try:
                        cursor.execute(
                            "SELECT EmpId, DatePart('d', EntryDate), var FROM var_op "
                            "WHERE Issue = ? AND var IS NOT NULL AND var <> 0 "
                            f"AND DatePart('d', EntryDate) IN ({placeholders})",
                            [issue_val] + day_nums,
                        )
                        for emp_id, day_num, var in cursor.fetchall():
                            preserved[(emp_id, day_num)] = var
                    except Exception:
                        preserved = {}

            # الخطوة 4: حذف سجلات الشهر إن وُجدت (مسح الحركات الحالية بموافقة المستخدم)
            cursor.execute("DELETE FROM var_op WHERE Issue = ?", (issue_val,))

            insert_query = (
                "INSERT INTO var_op (Issue, EmpId, EntryDate, var, wp, Notes) "
                "VALUES (?, ?, ?, ?, NULL, NULL)"
            )
            total_records = total_emps * len(dates_list)
            inserted_count = 0
            batch = []

            for emp_idx, emp_id in enumerate(active_emp_ids, start=1):
                if interrupt_check and interrupt_check():
                    conn.rollback()
                    raise InterruptedError("تم إلغاء العملية بواسطة المستخدم.")

                for dt in dates_list:
                    var_val = day_var_map[dt]
                    # حارس الأمان: أي قيمة سابقة غير صفرية في الجمعة/السبت/الأحد تُحفظ كما هي
                    if preserve_weekend_overrides and dt.weekday() in (4, 5, 6):
                        saved = preserved.get((emp_id, dt.day))
                        if saved is not None:
                            var_val = int(saved)
                    batch.append((issue_val, emp_id, dt, var_val))

                if len(batch) >= batch_size:
                    cursor.executemany(insert_query, batch)
                    conn.commit()
                    inserted_count += len(batch)
                    batch.clear()
                    if progress_callback:
                        pct = 10 + int((inserted_count / total_records) * 85)
                        progress_callback(pct, f"تم إنشاء {inserted_count:,} من أصل {total_records:,} سجل")

            if batch:
                cursor.executemany(insert_query, batch)
                conn.commit()
                inserted_count += len(batch)

            if progress_callback:
                progress_callback(95, "جارٍ تثبيت النتائج النهائية...")

            return inserted_count

        records_count = self.execute_with_retry(ts_db_path, op, ts_db_password)

        if progress_callback:
            progress_callback(100, f"اكتملت التهيئة بنجاح بإجمالي {records_count:,} سجل.")

        return {
            "total_employees": total_emps,
            "total_days": len(dates_list),
            "total_records": records_count,
            "issue": issue_val
        }