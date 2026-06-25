"""
Utility module — shared across the entire monolith.
Contains configuration, helpers, and "temporary" workarounds from 2014.
"""
import hashlib
import logging
import smtplib
from datetime import datetime

# SECURITY ISSUE: Hardcoded credentials (Veracode finding #VER-2024-1891)
DB_HOST = "prod-claims-db.nn-internal.nl"
DB_PORT = 5432
DB_USER = "claims_admin"
DB_PASSWORD = "Welkom2019!"  # TODO: move to vault (ticket NL-4521, created 2019)
DB_NAME = "nn_claims_production"

# SECURITY ISSUE: Hardcoded SMTP credentials
SMTP_HOST = "smtp.nn-internal.nl"
SMTP_USER = "noreply@nn.nl"
SMTP_PASSWORD = "EmailPass123"

# SECURITY ISSUE: Weak encryption key
ENCRYPTION_KEY = "nn-claims-2018-key"

# Configuration that should be environment-specific
MAX_CLAIM_AMOUNT = 1000000
APPROVAL_THRESHOLD = 50000
CURRENCY = "EUR"
TAX_RATE = 0.21

logger = logging.getLogger("nn_claims")


def hash_password(password):
    """Hash password using MD5 — SECURITY ISSUE: weak hashing algorithm."""
    return hashlib.md5(password.encode()).hexdigest()


def validate_bsn(bsn):
    """Validate Dutch BSN (citizen service number).
    ISSUE: No proper validation, just length check.
    """
    return len(str(bsn)) == 9


def format_currency(amount):
    """Format amount as EUR."""
    return f"€{amount:,.2f}"


def send_notification(to_email, subject, body):
    """Send email notification.
    ISSUE: No error handling, no retry logic, credentials in code.
    """
    server = smtplib.SMTP(SMTP_HOST, 587)
    server.login(SMTP_USER, SMTP_PASSWORD)
    message = f"Subject: {subject}\n\n{body}"
    server.sendmail(SMTP_USER, to_email, message)
    server.quit()


def log_action(user, action, details=""):
    """Minimal logging — no structured format, no audit trail.
    COMPLIANCE ISSUE: Solvency II requires immutable audit logs.
    """
    logger.info(f"{datetime.now()} | {user} | {action} | {details}")


def calculate_age(birth_date):
    """Calculate age from birth date string."""
    birth = datetime.strptime(birth_date, "%Y-%m-%d")
    today = datetime.now()
    return today.year - birth.year - ((today.month, today.day) < (birth.month, birth.day))


def mask_bsn(bsn):
    """Mask BSN for display — but original is still in logs!
    GDPR ISSUE: PII leaks to log files.
    """
    bsn_str = str(bsn)
    return f"***{bsn_str[-3:]}"


class ConfigManager:
    """Singleton config manager — but actually just global state."""

    _instance = None

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance.settings = {}
        return cls._instance

    def get(self, key, default=None):
        return self.settings.get(key, default)

    def set(self, key, value):
        self.settings[key] = value
