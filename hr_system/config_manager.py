import configparser
import os


BASE_DIR = os.path.dirname(os.path.abspath(__file__))


class ConfigManager:
    def __init__(self, config_path=None, key_path=None):
        self.config_path = config_path or os.path.join(BASE_DIR, "config.ini")
        self.key_path = key_path or os.path.join(BASE_DIR, "key.key")
        self.config = configparser.ConfigParser()
        self.cipher = None
        self._init_cipher()
        self.load()

    def _init_cipher(self):
        """تهيئة او انشاء مفتاح التشفير"""
        try:
            from cryptography.fernet import Fernet
        except ImportError:
            raise ImportError("ثبت cryptography: pip install cryptography")

        if os.path.exists(self.key_path):
            with open(self.key_path, "rb") as f:
                key = f.read()
        else:
            key = Fernet.generate_key()
            with open(self.key_path, "wb") as f:
                f.write(key)
        self.cipher = Fernet(key)

    def load(self):
        if os.path.exists(self.config_path):
            self.config.read(self.config_path, encoding="utf-8")
        else:
            self.create_default()

    def create_default(self):
        self.config["DATABASE"] = {
            "main_db": "",
            "timesheet_db": "",
            "last_user_id": ""
        }
        self.config["SETTINGS"] = {
            "retry_attempts": "3",
            "retry_delay_ms": "100"
        }
        self.config["PASSWORDS"] = {}
        self.save()

    def save(self):
        with open(self.config_path, "w", encoding="utf-8") as f:
            self.config.write(f)

    def get(self, section, key, default=""):
        return self.config.get(section, key, fallback=default)

    def set(self, section, key, value):
        if section not in self.config:
            self.config[section] = {}
        self.config[section][key] = str(value)
        self.save()

    def get_main_db(self):
        return self.get("DATABASE", "main_db")

    def set_main_db(self, path):
        self.set("DATABASE", "main_db", path)

    def get_timesheet_db(self):
        return self.get("DATABASE", "timesheet_db")

    def set_timesheet_db(self, path):
        self.set("DATABASE", "timesheet_db", path)

    def get_last_user(self):
        return self.get("DATABASE", "last_user_id")

    def set_last_user(self, user_id):
        self.set("DATABASE", "last_user_id", user_id)

    def set_password(self, db_name, password):
        """تشفير وحفظ كلمة السر"""
        if not self.cipher:
            return
        if not password:
            if "PASSWORDS" in self.config and db_name + "_pwd" in self.config["PASSWORDS"]:
                del self.config["PASSWORDS"][db_name + "_pwd"]
                self.save()
            return
        encrypted = self.cipher.encrypt(password.encode()).decode()
        if "PASSWORDS" not in self.config:
            self.config["PASSWORDS"] = {}
        self.config["PASSWORDS"][db_name + "_pwd"] = encrypted
        self.save()

    def get_password(self, db_name):
        """جلب وفك تشفير كلمة السر"""
        if "PASSWORDS" not in self.config or not self.cipher:
            return ""
        encrypted = self.get("PASSWORDS", db_name + "_pwd", "")
        if not encrypted:
            return ""
        try:
            return self.cipher.decrypt(encrypted.encode()).decode()
        except Exception:
            return ""

    def has_password(self, db_name):
        """هل يوجد كلمة سر محفوظة"""
        return bool(self.get_password(db_name))
