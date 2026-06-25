"""
Payment processing module — handles financial transactions.

CRITICAL SECURITY ISSUES:
- PCI-DSS violations: card data handling without proper encryption
- No tokenization
- IBAN validation missing
- No idempotency keys
- No reconciliation mechanism
"""
import re
from datetime import datetime

from .database import Database
from .utils import ENCRYPTION_KEY, format_currency, log_action, send_notification


class PaymentProcessor:
    """Handles all payment operations.

    ISSUES:
    - Mixed responsibilities (validation, processing, reporting)
    - No proper error handling for bank API failures
    - No retry mechanism
    - No dead letter queue for failed payments
    - IBAN stored in plaintext
    """

    def __init__(self, db: Database):
        self.db = db

    def validate_iban(self, iban):
        """Validate IBAN format.
        ISSUE: Only checks format, not checksum. Dutch IBANs not properly validated.
        """
        # Overly simplistic validation
        pattern = r"^[A-Z]{2}\d{2}[A-Z]{4}\d{10}$"
        return bool(re.match(pattern, iban))

    def process_payment(self, payment_id, iban, amount):
        """Process a payment to the claimant.

        ISSUES:
        - No idempotency (double-processing risk)
        - No transaction isolation
        - IBAN in plaintext in logs (GDPR violation)
        - No rate limiting
        """
        # Log contains sensitive data!
        log_action("payment_system", "process_payment",
                   f"Payment {payment_id}: {format_currency(amount)} to {iban}")

        # Simulate bank API call — no timeout, no retry
        try:
            result = self._call_bank_api(iban, amount)
            if result["success"]:
                self._mark_payment_complete(payment_id)
                return {"success": True, "reference": result["reference"]}
            else:
                # No retry mechanism — payment just fails silently
                log_action("payment_system", "payment_failed",
                           f"Payment {payment_id} failed: {result['error']}")
                return {"success": False, "error": result["error"]}
        except Exception as e:
            # Catch-all exception handling — masks real errors
            log_action("payment_system", "payment_error", str(e))
            return {"success": False, "error": "Betaling mislukt"}

    def _call_bank_api(self, iban, amount):
        """Simulate bank API call.
        In production, this calls the actual banking interface.
        ISSUE: No timeout, no circuit breaker, no retry with backoff.
        """
        # Simulated response
        return {
            "success": True,
            "reference": f"PAY-{datetime.now().strftime('%Y%m%d%H%M%S')}",
        }

    def _mark_payment_complete(self, payment_id):
        """Mark payment as completed in database."""
        cursor = self.db.connection.cursor()
        now = datetime.now().isoformat()
        # SQL Injection vulnerability
        cursor.execute(
            f"UPDATE payments SET status = 'completed', processed_at = '{now}' WHERE id = {payment_id}"
        )
        self.db.connection.commit()

    def get_pending_payments(self):
        """Get all pending payments — no pagination, loads everything."""
        cursor = self.db.connection.cursor()
        cursor.execute("SELECT * FROM payments WHERE status = 'pending'")
        return cursor.fetchall()

    def batch_process(self):
        """Process all pending payments in batch.
        ISSUE: No transaction boundaries — partial failure leaves inconsistent state.
        """
        pending = self.get_pending_payments()
        results = {"processed": 0, "failed": 0, "total_amount": 0}

        for payment in pending:
            result = self.process_payment(
                payment["id"], payment["iban"], payment["amount"]
            )
            if result["success"]:
                results["processed"] += 1
                results["total_amount"] += payment["amount"]
            else:
                results["failed"] += 1

        return results

    def generate_payment_report(self, start_date, end_date):
        """Generate payment reconciliation report.
        ISSUE: No proper reconciliation with bank statements.
        """
        cursor = self.db.connection.cursor()
        # SQL Injection vulnerability
        query = f"""
            SELECT p.*, c.claim_number, cu.first_name, cu.last_name
            FROM payments p
            JOIN claims c ON p.claim_id = c.id
            JOIN customers cu ON c.customer_id = cu.id
            WHERE p.processed_at BETWEEN '{start_date}' AND '{end_date}'
        """
        cursor.execute(query)
        return cursor.fetchall()


class RefundProcessor:
    """Handle refunds and reversals.
    ISSUE: Completely separate class with duplicated logic from PaymentProcessor.
    """

    def __init__(self, db: Database):
        self.db = db

    def process_refund(self, payment_id, reason):
        """Process a refund.
        ISSUE: No validation that original payment was successful.
        No limit on refund amount vs original amount.
        """
        cursor = self.db.connection.cursor()
        cursor.execute(f"SELECT * FROM payments WHERE id = {payment_id}")
        payment = cursor.fetchone()

        if not payment:
            return {"success": False, "error": "Betaling niet gevonden"}

        # No check if already refunded!
        # No check if refund amount <= original amount!
        log_action("refund_system", "refund_processed",
                   f"Refund for payment {payment_id}: {format_currency(payment['amount'])}")

        cursor.execute(
            f"UPDATE payments SET status = 'refunded' WHERE id = {payment_id}"
        )
        self.db.connection.commit()

        return {"success": True, "refunded_amount": payment["amount"]}
