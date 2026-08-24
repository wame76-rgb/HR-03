import pyodbc
import time
import calendar
from datetime import date, datetime


class DatabaseConnection:
    def __init__(self, retry_attempts=3, retry_delay_ms=100):
        self.retry_attempts = retry_attempts
        self.retry_delay_ms = retry_delay_ms / 1000.0
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
        conn = pyodbc.connect(conn_str, timeout=5)
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
        holidays_set=None,
        holiday_var_code=None,
        progress_callback=None,
        db_password=""
    ):
        """
        تنفيذ عملية التهيئة الشاملة:
        1. تفريغ وتعبئة جدول DatePrep.
        2. جلب الموظفين الفعالين من basic (enha2_date IS NULL).
        3. إدراج مجمع لسجلات var_op لكل موظف ولكل يوم من أيام الشهر.
        """
        issue_val = int(issue)
        holidays_set = holidays_set or set()

        # الخطوة 1: تعبئة جدول DatePrep
        self.populate_date_prep(ts_db_path, dates_list, db_password)
        if progress_callback:
            progress_callback(10, "تم تجهيز جدول التواريخ DatePrep بنجاح...")

        # الخطوة 2: جلب أرقام العاملين النشطين
        active_emp_ids = self.get_active_employee_ids(main_db_path, db_password)
        total_emps = len(active_emp_ids)
        if total_emps == 0:
            raise ValueError("لم يتم العثور على أي موظفين فعالين في جدول basic (حقل enha2_date فارغ).")

        if progress_callback:
            progress_callback(25, f"تم حصر {total_emps} موظف فعال...")

        # الخطوة 3: تجهيز وإدراج سجلات var_op مجمعة
        def op(conn):
            cursor = conn.cursor()
            insert_query = (
                "INSERT INTO var_op (Issue, EmpId, EntryDate, var, wp, Notes) "
                "VALUES (?, ?, ?, ?, NULL, NULL)"
            )

            # إعداد الحزم للإدراج المجمع (Chunked Batch Insert)
            batch = []
            batch_size = 2000
            total_records = total_emps * len(dates_list)
            inserted_count = 0

            for emp_idx, emp_id in enumerate(active_emp_ids, start=1):
                for dt in dates_list:
                    # تحديد ما إذا كان اليوم عطلة رسمية محددة
                    is_holiday = dt in holidays_set or dt.strftime("%Y-%m-%d") in holidays_set
                    var_val = holiday_var_code if (is_holiday and holiday_var_code is not None) else None
                    batch.append((issue_val, emp_id, dt, var_val))

                if len(batch) >= batch_size:
                    cursor.executemany(insert_query, batch)
                    inserted_count += len(batch)
                    batch.clear()

                    if progress_callback:
                        pct = 25 + int((inserted_count / total_records) * 70)
                        progress_callback(pct, f"تم إنشاء {inserted_count:,} من أصل {total_records:,} سجل...")

            if batch:
                cursor.executemany(insert_query, batch)
                inserted_count += len(batch)
                batch.clear()

            return inserted_count

        records_count = self.execute_with_retry(ts_db_path, op, db_password)

        if progress_callback:
            progress_callback(100, f"اكتملت التهيئة بنجاح بإجمالي {records_count:,} سجل.")

        return {
            "total_employees": total_emps,
            "total_days": len(dates_list),
            "total_records": records_count,
            "issue": issue_val
        }