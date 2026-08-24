# تعليمات المهمة — شاشة إدخال المتغيرات (شاشة التحركات)

> هذا الملف يخص **مهمة واحدة فقط**: إكمال ومراجعة `ui/variables_window.py` وربطها بالنظام. اقرأ أولًا `02-general-project-instructions.md` لأنه يحوي القواعد الثابتة (تصميم، أمان، طبقة قاعدة بيانات) التي تنطبق هنا أيضًا ولن تتكرر بالكامل في هذا الملف.

---

## 1. الحالة الحالية — مهم جدًا

**لا تبدأ من الصفر.** يوجد ملف `ui/variables_window.py` مبني فعليًا (946 سطرًا) يطبّق أغلب ما هو مطلوب أدناه. مهمتك الأساسية: **المراجعة، الإصلاح، الإكمال، والتأكد من التشغيل الفعلي**، وليس إعادة الكتابة. اقرأ الملف الموجود بالكامل أولًا قبل أي تعديل.

الملف يعتمد على دوال في `db_connection.py` (النسخة الكاملة الموحّدة بعد حسم التكرار — راجع `04-files-to-upload-list.md`): `get_employee_full_info`, `get_variables`, `get_workplaces`, `get_month_movements`, `movement_exists`, `update_movement_var`, `update_movement_notes`, `get_attendance_report`. تأكد من وجودها جميعًا قبل تشغيل الشاشة.

الشاشة مربوطة فعليًا من الشاشة الرئيسية عبر:
```python
def _open_variables(self):
    from ui.variables_window import VariablesWindow
    if self.variables_window is None or not self.variables_window.isVisible():
        self.variables_window = VariablesWindow(self.config, self.db, self.user_data, self)
    self.variables_window.showMaximized()
    self.variables_window.raise_()
    self.variables_window.activateWindow()
```
تأكد أن هذا الربط موجود فعليًا في `ui/main_window.py` المُستخدَم (وليس في نسخة مهملة منه).

---

## 2. مرجع التصميم البصري — تنبيه

المستخدم أرسل صورة كروكي (`كروكي شاشة الادخال.bmp`) يُفترض أنها المرجع النهائي للتخطيط، **لكن الملف المرفوع حاليًا فارغ (0 بايت)**. لذلك:
- إذا لم تتوفر لك نسخة صالحة من هذه الصورة عند بدء المهمة: **اطلبها من المستخدم صراحة قبل ضبط التخطيط النهائي**، ولا تخمّن التفاصيل البصرية الدقيقة.
- إلى حين توفرها، استخدم التخطيط النصي المؤكَّد في القسم 3 أدناه (وهو نفسه ما طُبِّق فعليًا في `variables_window.py` الحالي).

## 3. التخطيط العام المؤكَّد (نصيًا، بانتظار تأكيد الصورة)

```
┌──────────────────────────────┬────────────────────────────────┐
│ (أ) منطقة المدخلات           │ (ب) مخرجات بيان العامل          │
│  - الشهر (YYYYMM) + [-][+]   │  - الاسم / الوظيفة / القوة      │
│  - الرقم المالي              │  - نوع التعاقد                  │
│  - تاريخ من / تاريخ إلى      │                                 │
│  - المتغير (كومبوبوكس)       │                                 │
│  - الموقع (كومبوبوكس)        │                                 │
│  - ملاحظات (تكست بوكس)       │                                 │
│  [ترحيل متغير] [ترحيل إذن] [إلغاء إذن]                          │
├──────────────────────────────┴────────────────────────────────┤
│ (هـ) تحركات الشهر (4 أعمدة)   │ (و) تقرير سنتين  │ (ج) ليست بوكس │
│ الإذن/الملاحظات، التاريخ،    │ (12–24 صف)       │ المتغيرات فقط │
│ المتغير، الموقع              │                  │ (يمين الشاشة) │
├───────────────────────────────────────────────────────────────┤
│  [حذف]                                              [خروج]    │
└───────────────────────────────────────────────────────────────┘
```
- في RTL: ليست بوكس المتغيرات يظهر في أقصى اليمين، وباقي العناصر إلى يساره — هذا مطبَّق في الكود الحالي عبر `body.addWidget(variables_panel, 1)` كأول عنصر في `QHBoxLayout` مع `setLayoutDirection(Qt.RightToLeft)`.
- **حل مشكلة الشاشات الصغيرة (مؤكَّد)**: نسب تمدد مرنة (المدخلات ~20% / الجداول ~50% / التقرير ~30%)، فتح النافذة بـ `showMaximized()`، تفعيل `Qt.AA_EnableHighDpiScaling` في `main.py`. **لا تستخدم `QSplitter`** — البيانات ثابتة الحجم نسبيًا (37 متغيرًا كحد أقصى، 31 يومًا، 24 صفًا) ولا تبرر هذا التعقيد.

## 4. المدخلات (الجزء أ) — تفصيل دقيق

| الحقل | السلوك المطلوب |
|---|---|
| الشهر | نص `YYYYMM`، افتراضي = الشهر الحالي، زران [-][+] لزيادة/تقليل الشهر (تعامل صحيح مع حدود السنة، مثال: 202512 + 1 → 202601) |
| الرقم المالي | إدخال يدوي (Enter لتحميل بيانات الموظف). إن لم يوجد في `basic` → رسالة تنبيه + **تظليل النص فقط دون مسحه** |
| تاريخ من | إجباري |
| تاريخ إلى | اختياري، عند أول تركيز عليه يُملأ تلقائيًا بقيمة "من" مع تظليل كامل (منطق `_SelectableDateEdit` الموجود بالفعل) |
| المتغير | كومبوبوكس بإكمال تلقائي، يقبل رقم أو اسم، **مرتبط ثنائيًا** بليست بوكس المتغيرات (اختيار من أحدهما يحدّث الآخر) |
| الموقع | كومبوبوكس بإكمال تلقائي فقط (لا ليست بوكس مقابل له) |
| ملاحظات | تكست بوكس لرمز الإذن أو ملاحظة حرة |
| التنقّل | الشهر → الرقم المالي → تاريخ من → تاريخ إلى (Tab order منطقي) |

## 5. بيان العامل (الجزء ب)

يُجلب فور إدخال رقم مالي صحيح عبر `get_employee_full_info`: الاسم، الوظيفة (`jobs`)، القوة/الموقع الأساسي (`work_place`)، نوع التعاقد (`t3akod`).

## 6. ليست بوكس المتغيرات (الجزء ج)

- مصدرها جدول `variables` (37 صفًا كحد أقصى).
- ربط ثنائي كامل مع كومبوبوكس المتغير في الجزء (أ) — هذا موجود في الكود عبر `_on_list_selected` و `_on_var_combo_changed`.
- الموقع ليس له ليست بوكس مقابل — كومبوبوكس فقط.

## 7. تحركات الشهر (الجزء هـ)

جدول 4 أعمدة (الإذن/الملاحظات، التاريخ، المتغير، الموقع) من `var_op`، مُقيَّد بـ `Issue` + `EmpId` الحاليين. **عند النقر على صف**: تُنسخ القيم لحقول الإدخال — التاريخ يذهب لـ"من" **و"إلى" معًا** (مؤكَّد من المستخدم صراحة)، المتغير للكومبوبوكس/الليست بوكس، الموقع لكومبوبوكس الموقع، الملاحظات لحقل الملاحظات.

## 8. تقرير العام الحالي والسابق (الجزء و)

- نطاق: **السنة الحالية + السابقة** (وليس 6 أشهر). حد أدنى **12 صفًا**، حد أقصى **24 صفًا**.
- خمسة أنواع تُحسب: المتغيرات 1، 2، 3، 4، بالإضافة إلى متغير جديد بكود **35 (اسمه `WH`)**.
- عرض: ليست بوكس بارتفاع 12 صفًا مرئيًا + سكرول للباقي.
- الحساب يجب أن يتم عبر `GROUP BY` في SQL (`get_attendance_report`) — **ليس بجلب كل صفوف `var_op` وعدّها في بايثون**.
- **تنبيه حسابي مهم لأي تعديل مستقبلي**: حساب الشهر التالي/السابق عبر حدود السنة (`202512 → 202601`) يجب أن يمر دائمًا عبر دالة مساعدة موحّدة (مثل `_add_months` الموجودة في الكود الحالي)، ولا يُكتب كجمع بسيط `issue + 1` لأنه يكسر عند حدود السنة.

## 9. قواعد العمل الصارمة (مؤكَّدة من المستخدم)

1. **حد الأذونات الشهري**: كل رمز إذن (`"2"` أو `"x"`) له **مرتان كحد أقصى شهريًا لكل رمز** (وليس لكل نطاق تاريخ). عند تجاوز الحد → رسالة رفض صريحة وإلغاء العملية بالكامل، مع إعادة التركيز لحقل الملاحظات.
2. **نطاق التواريخ (من → إلى)**: يُطبَّق على **كل الأيام في النطاق** دفعة واحدة (مثال: من 1 إلى 5 = 5 أيام بنفس القيمة).
3. **التحديث لا الإدراج**: `var_op` يجب أن يحتوي مسبقًا سجلًا فارغًا لكل يوم (نتيجة عملية "تهيئة بداية الشهر" المنفصلة). إن لم يوجد السجل → **رسالة**: "لا يوجد سجل — يجب إدراج شهر جديد في جدول الحضور"، ولا يُنشأ سجل جديد من هذه الشاشة.
4. **الحذف**: يحذف حركة المتغير أو الإذن من نفس اليوم؛ **إن وُجد الاثنان معًا** يُخيَّر المستخدم أيهما يُحذف (Yes/No/Cancel)، وليس حذفًا تلقائيًا للاثنين.
5. **قيمة فارغة عند الترحيل**: الضغط على زر الترحيل بقيمة فارغة يُفرِّغ الخلية في النطاق كله مع رسالة تنبيه، لا يُعامَل كخطأ صامت.
6. عمود `lock` في `var_op` **متروك دون استخدام حاليًا** — لا تبني عليه منطقًا جديدًا دون تأكيد من المستخدم.

## 10. الأزرار (الأسماء والسلوك المؤكَّد)

| الزر | السلوك |
|---|---|
| **ترحيل متغير** | يرحّل حركة اليوم/النطاق (تاريخ – متغير – موقع) إلى `var_op` |
| **ترحيل إذن** | يرحّل نص حقل الملاحظات إلى عمود `Notes` مع تطبيق قاعدة حد الأذونات |
| **إلغاء إذن** | يمسح الإذن من `Notes` في التاريخ المحدد فقط؛ بلا تاريخ محدد → "برجاء اختيار التاريخ" |
| **حذف** | حذف حركة/إذن من الصف المحدد في جدول التحركات، مع التخيير إن وُجد الاثنان |
| **خروج** | إغلاق الشاشة فقط |

⚠️ **لا يوجد زر "ترحيل" كبير مُدمج واحد** — هذا أُلغي صراحة. كل عملية بزرها المستقل.

## 11. ما يجب التحقق منه/إكماله الآن (Checklist)

- [ ] تشغيل التطبيق كاملًا (بعد حسم تكرار الملفات — راجع `04-files-to-upload-list.md`) والتأكد أن زر "ادخال المتغيرات" يفتح الشاشة فعليًا بلا أخطاء.
- [ ] التحقق من كل دالة في `db_connection.py` المطلوبة موجودة وتُستدعى بالأسماء والمعاملات الصحيحة من `variables_window.py`.
- [ ] اختبار السيناريوهات الحرجة: رقم مالي غير موجود، تجاوز حد الأذونات، الترحيل ليوم بلا سجل مُهيَّأ، الحذف عند وجود متغير وإذن معًا، حساب الشهر عند حدود السنة (ديسمبر↔يناير).
- [ ] طلب صورة الكروكي الحقيقية من المستخدم إن لم تكن مرفقة صالحة، ومطابقة التخطيط النهائي معها قبل اعتباره منتهيًا.
- [ ] تحديث `capture_screens.py` ليشمل التقاط صورة لـ `VariablesWindow` (اختياري لكن مفيد للمراجعة البصرية عن بُعد).
- [ ] عدم لمس منطق شاشات الدخول/الإعدادات إلا لإصلاح الأخطاء الموثّقة في `05-known-issues-and-fixes.md` التي تمنع تشغيل هذه الشاشة أصلًا.

## 12. نقاط مفتوحة — لا تفترض إجابتها، اسأل المستخدم

- زر "تهيئة بداية الشهر" (DatePrep + تعبئة السجلات الفارغة) **ليس جزءًا من هذه المهمة** — هو للشاشة الرئيسية في مهمة لاحقة منفصلة. لا تبنِه ضمن شاشة المتغيرات.
- أي تفصيل تخطيطي (نِسَب أعمدة، ترتيب دقيق) غير مطابق للصورة الحقيقية بمجرد توفرها يجب تعديله وفقها، لا وفق افتراضك.

## 13. Focus & Intelligent Navigation Policy

### 1. Initial Focus Window Policy
- When the Variables Input Screen (`VariablesWindow`) opens, the active cursor focus must be automatically set onto the Financial Number input field (مربع ادخال الرقم المالي).

### 2. Intelligent Navigation Sequence
- The navigation sequence must advance sequentially through this exact order:
  `Financial Number (الرقم المالي) -> Date From (تاريخ من) -> Date To (تاريخ إلى) -> Variable (المتغير) -> Location (الموقع)`.
- **Keyboard Navigation Shortcuts**:
  - **Tab Key**: Move to the next widget.
  - **Enter / Return Key (Main & Numpad)**: Move to the next widget (for the Financial Number field, trigger loading employee data first).
  - **Down Arrow Key**: Move to the next widget.
  - **Up Arrow Key**: Move to the previous widget.
  - *Exception*: While auto-complete popup lists (e.g. Variable or Location combo box completer dropdowns) are visible, Up/Down Arrow keys retain their standard behaviors to navigate the dropdown options.

### 3. Dynamic Default Date Logic
- **Date From (تاريخ من)**: Initialize to the current system date (Today's Date) as default.
- **Date To (تاريخ إلى)**: Dynamically inherit the value of "Date From" as its initial default value, while keeping it fully editable for manual adjustments.

## Focus & Intelligent Navigation Policy

### 1. Automatic Initial Focus
- Upon opening the Variables Input Window, the system automatically assigns the active cursor focus to the **Financial Number** field (مربع إدخال الرقم المالي). This eliminates the need for initial mouse clicks and streamlines the data entry process.

### 2. Intelligent Field Transition
- The system overrides standard key events (`keyPressEvent` via `eventFilter`) to support a comprehensive and fluid navigation experience.
- The focus transitions seamlessly across input fields using any of the following methods:
  - **Tab Key**: Standard sequential forward navigation.
  - **Enter / Return Keys**: Both the primary Enter key and the Numpad Enter key instantly validate input (e.g., loading employee data) and push focus to the next logical field.
  - **Arrow Keys**: The **Down Arrow** key moves the focus forward, while the **Up Arrow** key moves the focus backward through the sequence.
- **ComboBox Exception Logic**: Custom handling prevents navigation events from overriding or closing autocomplete dropdown (`QCompleter`) popup menus when they are actively displayed.

### 3. Navigation Path Order
- To maintain optimal ergonomic flow during data entry, the explicit focus path strictly follows:
  1. `Financial Number` (الرقم المالي)
  2. `Date From` (تاريخ من)
  3. `Date To` (تاريخ إلى)
  4. `Variable` (المتغير)
  5. `Location` (الموقع)

### 4. Auto-Date Dynamic Logic
- **Initialization**: The "Date From" field defaults to the current system date upon launch.
- **Inheritance**: The "Date To" field utilizes a custom `_SelectableDateEdit` widget to intelligently inherit and continuously mirror the value of "Date From" as its dynamic default.
- **Flexibility**: Once the user manually interacts with or edits the "Date To" field, the inheritance binding is gracefully broken for that session, prioritizing the user's explicit input while remaining fully editable.