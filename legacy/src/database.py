"""
Database layer — direct SQL queries with string formatting.
No ORM, no parameterized queries, no connection pooling.

SECURITY: Multiple SQL injection vulnerabilities (SonarQube Critical findings)
"""
import sqlite3
from datetime import datetime

from .utils import DB_HOST, DB_NAME, DB_PASSWORD, DB_PORT, DB_USER, log_action


class Database:
    """Monolithic database class handling ALL tables and queries."""

    def __init__(self, db_path=None):
        # In production this connects to PostgreSQL; using SQLite for demo
        self.db_path = db_path or ":memory:"
        self.connection = None

    def connect(self):
        """Connect to database — no connection pooling."""
        self.connection = sqlite3.connect(self.db_path)
        self.connection.row_factory = sqlite3.Row
        self._create_tables()

    def _create_tables(self):
        """Create all tables — everything in one database, no schema separation."""
        cursor = self.connection.cursor()
        cursor.executescript("""
            CREATE TABLE IF NOT EXISTS customers (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                bsn TEXT NOT NULL,
                first_name TEXT NOT NULL,
                last_name TEXT NOT NULL,
                email TEXT,
                phone TEXT,
                address TEXT,
                birth_date TEXT,
                created_at TEXT DEFAULT CURRENT_TIMESTAMP
            );

            CREATE TABLE IF NOT EXISTS policies (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                customer_id INTEGER,
                policy_number TEXT NOT NULL,
                policy_type TEXT NOT NULL,
                start_date TEXT,
                end_date TEXT,
                premium_amount REAL,
                coverage_amount REAL,
                status TEXT DEFAULT 'active'
            );

            CREATE TABLE IF NOT EXISTS claims (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                policy_id INTEGER,
                customer_id INTEGER,
                claim_number TEXT NOT NULL,
                claim_type TEXT,
                description TEXT,
                amount_claimed REAL,
                amount_approved REAL,
                status TEXT DEFAULT 'submitted',
                submitted_at TEXT DEFAULT CURRENT_TIMESTAMP,
                processed_at TEXT,
                processed_by TEXT,
                notes TEXT
            );

            CREATE TABLE IF NOT EXISTS payments (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                claim_id INTEGER,
                amount REAL,
                payment_method TEXT,
                iban TEXT,
                status TEXT DEFAULT 'pending',
                created_at TEXT DEFAULT CURRENT_TIMESTAMP,
                processed_at TEXT
            );

            CREATE TABLE IF NOT EXISTS users (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                username TEXT NOT NULL,
                password_hash TEXT NOT NULL,
                role TEXT DEFAULT 'agent',
                last_login TEXT
            );
        """)
        self.connection.commit()

    def get_customer(self, customer_id):
        """Get customer by ID — no input validation."""
        cursor = self.connection.cursor()
        # VULNERABILITY: SQL Injection via string formatting
        query = f"SELECT * FROM customers WHERE id = {customer_id}"
        cursor.execute(query)
        return cursor.fetchone()

    def search_customers(self, search_term):
        """Search customers — SQL injection vulnerability.
        SonarQube Finding: squid:S3649 - SQL Injection
        """
        cursor = self.connection.cursor()
        # VULNERABILITY: Direct string interpolation in SQL
        query = f"SELECT * FROM customers WHERE first_name LIKE '%{search_term}%' OR last_name LIKE '%{search_term}%' OR bsn = '{search_term}'"
        cursor.execute(query)
        return cursor.fetchall()

    def create_claim(self, policy_id, customer_id, claim_type, description, amount):
        """Create a new claim — no validation, no transaction safety."""
        cursor = self.connection.cursor()
        claim_number = f"CLM-{datetime.now().strftime('%Y%m%d%H%M%S')}"

        # VULNERABILITY: SQL Injection
        query = f"""
            INSERT INTO claims (policy_id, customer_id, claim_number, claim_type,
                              description, amount_claimed, status)
            VALUES ({policy_id}, {customer_id}, '{claim_number}', '{claim_type}',
                   '{description}', {amount}, 'submitted')
        """
        cursor.execute(query)
        self.connection.commit()
        return claim_number

    def update_claim_status(self, claim_id, status, processed_by, amount_approved=None):
        """Update claim status — no optimistic locking, no state machine."""
        cursor = self.connection.cursor()
        now = datetime.now().isoformat()

        if amount_approved:
            query = f"""
                UPDATE claims SET status = '{status}', processed_by = '{processed_by}',
                processed_at = '{now}', amount_approved = {amount_approved}
                WHERE id = {claim_id}
            """
        else:
            query = f"""
                UPDATE claims SET status = '{status}', processed_by = '{processed_by}',
                processed_at = '{now}' WHERE id = {claim_id}
            """
        cursor.execute(query)
        self.connection.commit()

    def get_claims_by_status(self, status):
        """Get claims filtered by status."""
        cursor = self.connection.cursor()
        # VULNERABILITY: SQL Injection
        query = f"SELECT * FROM claims WHERE status = '{status}'"
        cursor.execute(query)
        return cursor.fetchall()

    def get_claim_with_customer(self, claim_id):
        """Get claim with customer details — complex JOIN in application code."""
        cursor = self.connection.cursor()
        query = f"""
            SELECT c.*, cu.first_name, cu.last_name, cu.bsn, cu.email,
                   p.policy_number, p.policy_type, p.coverage_amount
            FROM claims c
            JOIN customers cu ON c.customer_id = cu.id
            JOIN policies p ON c.policy_id = p.id
            WHERE c.id = {claim_id}
        """
        cursor.execute(query)
        return cursor.fetchone()

    def authenticate_user(self, username, password_hash):
        """Authenticate user — timing attack vulnerable, no rate limiting."""
        cursor = self.connection.cursor()
        # VULNERABILITY: SQL Injection in authentication!
        query = f"SELECT * FROM users WHERE username = '{username}' AND password_hash = '{password_hash}'"
        cursor.execute(query)
        user = cursor.fetchone()
        if user:
            # Update last login — but no audit of failed attempts
            cursor.execute(f"UPDATE users SET last_login = '{datetime.now().isoformat()}' WHERE id = {user['id']}")
            self.connection.commit()
        return user

    def create_payment(self, claim_id, amount, iban, payment_method="bank_transfer"):
        """Create payment record.
        PCI-DSS ISSUE: IBAN stored in plain text, no encryption.
        """
        cursor = self.connection.cursor()
        query = f"""
            INSERT INTO payments (claim_id, amount, iban, payment_method, status)
            VALUES ({claim_id}, {amount}, '{iban}', '{payment_method}', 'pending')
        """
        cursor.execute(query)
        self.connection.commit()
        return cursor.lastrowid

    def get_monthly_report(self, year, month):
        """Generate monthly claims report — no caching, full table scan."""
        cursor = self.connection.cursor()
        query = f"""
            SELECT claim_type, COUNT(*) as count,
                   SUM(amount_claimed) as total_claimed,
                   SUM(amount_approved) as total_approved
            FROM claims
            WHERE strftime('%Y', submitted_at) = '{year}'
              AND strftime('%m', submitted_at) = '{month:02d}'
            GROUP BY claim_type
        """
        cursor.execute(query)
        return cursor.fetchall()

    def close(self):
        """Close connection."""
        if self.connection:
            self.connection.close()
