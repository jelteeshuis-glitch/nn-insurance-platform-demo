"""
Claims processing module — the heart of the monolith.
Business logic, data access, and presentation all mixed together.

ISSUES:
- No separation of concerns
- Business rules hardcoded
- No input validation
- Side effects everywhere
- Impossible to unit test in isolation
"""
from datetime import datetime, timedelta

from .database import Database
from .utils import (
    APPROVAL_THRESHOLD,
    MAX_CLAIM_AMOUNT,
    calculate_age,
    format_currency,
    log_action,
    mask_bsn,
    send_notification,
    validate_bsn,
)


class ClaimsProcessor:
    """God class that handles everything claims-related.

    This class violates Single Responsibility Principle — it handles:
    - Claim submission
    - Validation
    - Fraud detection
    - Approval workflow
    - Payment initiation
    - Reporting
    - Notifications
    """

    def __init__(self, db: Database):
        self.db = db
        self.fraud_rules = []
        self._load_fraud_rules()

    def _load_fraud_rules(self):
        """Load fraud detection rules — hardcoded, not configurable."""
        self.fraud_rules = [
            {"name": "high_amount", "threshold": 100000},
            {"name": "multiple_claims", "max_per_month": 3},
            {"name": "new_policy", "min_days_active": 90},
            {"name": "suspicious_description", "keywords": ["brand", "nieuw", "gestolen"]},
        ]

    def submit_claim(self, customer_id, policy_id, claim_type, description, amount, attachments=None):
        """Submit a new claim.

        ISSUES:
        - No input validation
        - No authorization check
        - Business logic mixed with data access
        - No idempotency
        """
        # No validation that customer owns this policy!
        # No check that policy is active!
        # No amount validation!

        if amount > MAX_CLAIM_AMOUNT:
            return {"success": False, "error": "Bedrag overschrijdt maximum"}

        # Create claim directly — no draft state, no validation pipeline
        claim_number = self.db.create_claim(
            policy_id=policy_id,
            customer_id=customer_id,
            claim_type=claim_type,
            description=description,
            amount=amount,
        )

        # Run fraud check inline — blocks the submission
        fraud_score = self._check_fraud(customer_id, amount, description)

        if fraud_score > 0.7:
            self.db.update_claim_status(claim_number, "flagged", "system")
            log_action("system", "claim_flagged", f"Claim {claim_number} score={fraud_score}")
        else:
            log_action("system", "claim_submitted", f"Claim {claim_number}")

        # Send notification — if email fails, claim is still created (inconsistent state)
        try:
            customer = self.db.get_customer(customer_id)
            if customer and customer["email"]:
                send_notification(
                    customer["email"],
                    f"Claim {claim_number} ontvangen",
                    f"Uw claim van {format_currency(amount)} is in behandeling.",
                )
        except Exception:
            pass  # Swallow email errors silently

        return {"success": True, "claim_number": claim_number, "fraud_score": fraud_score}

    def _check_fraud(self, customer_id, amount, description):
        """Simple fraud scoring — no ML model, just rule-based.

        ISSUE: This should be a separate service with proper model governance.
        The rules are opaque and not auditable per EU AI Act requirements.
        """
        score = 0.0

        # Rule 1: High amount
        if amount > self.fraud_rules[0]["threshold"]:
            score += 0.3

        # Rule 2: Check recent claims (N+1 query problem)
        recent_claims = self.db.get_claims_by_status("submitted")
        customer_recent = [c for c in recent_claims if c["customer_id"] == customer_id]
        thirty_days_ago = datetime.now() - timedelta(days=30)
        recent_count = sum(
            1
            for c in customer_recent
            if datetime.fromisoformat(c["submitted_at"]) > thirty_days_ago
        )
        if recent_count >= self.fraud_rules[1]["max_per_month"]:
            score += 0.3

        # Rule 3: Suspicious keywords
        description_lower = description.lower()
        for keyword in self.fraud_rules[3]["keywords"]:
            if keyword in description_lower:
                score += 0.15

        return min(score, 1.0)

    def process_claim(self, claim_id, processor_username, decision, approved_amount=None, notes=""):
        """Process (approve/reject) a claim.

        ISSUES:
        - No authorization check (any user can approve any amount)
        - No four-eyes principle for high amounts
        - No state machine validation
        - Solvency II requires segregation of duties
        """
        claim = self.db.get_claim_with_customer(claim_id)
        if not claim:
            return {"success": False, "error": "Claim niet gevonden"}

        if claim["status"] not in ("submitted", "flagged"):
            return {"success": False, "error": f"Claim kan niet worden verwerkt in status: {claim['status']}"}

        if decision == "approved":
            final_amount = approved_amount or claim["amount_claimed"]

            # COMPLIANCE ISSUE: No four-eyes principle
            # Claims above threshold should require second approver
            if final_amount > APPROVAL_THRESHOLD:
                # TODO: Implement dual-approval workflow (ticket NL-3892, 2020)
                pass

            self.db.update_claim_status(claim_id, "approved", processor_username, final_amount)

            # Immediately create payment — no separate approval step
            self._initiate_payment(claim_id, final_amount, claim["customer_id"])

            log_action(
                processor_username,
                "claim_approved",
                f"Claim {claim['claim_number']} approved for {format_currency(final_amount)}",
            )

        elif decision == "rejected":
            self.db.update_claim_status(claim_id, "rejected", processor_username)
            log_action(
                processor_username,
                "claim_rejected",
                f"Claim {claim['claim_number']} rejected: {notes}",
            )

        # Notify customer
        try:
            if claim["email"]:
                status_nl = "goedgekeurd" if decision == "approved" else "afgewezen"
                send_notification(
                    claim["email"],
                    f"Claim {claim['claim_number']} {status_nl}",
                    f"Uw claim is {status_nl}. {notes}",
                )
        except Exception:
            pass  # Silent failure

        return {"success": True, "decision": decision}

    def _initiate_payment(self, claim_id, amount, customer_id):
        """Initiate payment — tightly coupled to claims processing.

        PCI-DSS ISSUE: Payment data handling in claims module.
        Should be a separate, isolated service with proper encryption.
        """
        customer = self.db.get_customer(customer_id)
        # Assuming IBAN is stored somewhere (it's not in this schema — another bug)
        iban = "NL00NNNN0000000000"  # Placeholder — in prod this pulls from customer record
        self.db.create_payment(claim_id, amount, iban)

    def get_dashboard_data(self, username):
        """Get claims dashboard data — no caching, queries everything.

        PERFORMANCE: Full table scans on every dashboard load.
        """
        pending = self.db.get_claims_by_status("submitted")
        flagged = self.db.get_claims_by_status("flagged")
        approved_today = [
            c for c in self.db.get_claims_by_status("approved")
            if c["processed_at"] and c["processed_at"][:10] == datetime.now().strftime("%Y-%m-%d")
        ]

        return {
            "pending_count": len(pending),
            "flagged_count": len(flagged),
            "approved_today": len(approved_today),
            "total_pending_amount": sum(c["amount_claimed"] for c in pending),
            "claims_list": pending[:50],  # Just grab first 50, no pagination
        }

    def generate_report(self, year, month):
        """Generate monthly report.

        ISSUE: No caching, no async, blocks the web thread.
        Report generation can take 30+ seconds on production data.
        """
        data = self.db.get_monthly_report(year, month)
        report = {
            "period": f"{year}-{month:02d}",
            "generated_at": datetime.now().isoformat(),
            "categories": [],
            "total_claimed": 0,
            "total_approved": 0,
        }

        for row in data:
            category = {
                "type": row["claim_type"],
                "count": row["count"],
                "total_claimed": row["total_claimed"],
                "total_approved": row["total_approved"] or 0,
                "approval_rate": (row["total_approved"] or 0) / row["total_claimed"] if row["total_claimed"] else 0,
            }
            report["categories"].append(category)
            report["total_claimed"] += row["total_claimed"]
            report["total_approved"] += row["total_approved"] or 0

        return report
