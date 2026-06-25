"""
Main application — the "god object" that ties everything together.
Flask web application serving HTML directly (no frontend framework).

ISSUES:
- 1500+ lines in production (truncated for demo)
- No API versioning
- Session management in-memory
- No CSRF protection
- No rate limiting
- Mixed HTML rendering with business logic
- No health check endpoint
- No graceful shutdown
"""
from datetime import datetime

from flask import Flask, jsonify, redirect, render_template_string, request, session

from .claims import ClaimsProcessor
from .database import Database
from .payments import PaymentProcessor, RefundProcessor
from .utils import hash_password, log_action, validate_bsn

app = Flask(__name__)
app.secret_key = "super-secret-key-dont-change"  # SECURITY: Hardcoded secret key

# Global state — not thread-safe
db = Database()
db.connect()
claims_processor = ClaimsProcessor(db)
payment_processor = PaymentProcessor(db)
refund_processor = RefundProcessor(db)


# ============================================================
# Authentication — no middleware, repeated in every route
# ============================================================

def require_login(f):
    """Decorator for login requirement.
    ISSUE: Checks session but no token refresh, no timeout.
    """
    def wrapper(*args, **kwargs):
        if "user" not in session:
            return redirect("/login")
        return f(*args, **kwargs)
    wrapper.__name__ = f.__name__
    return wrapper


@app.route("/login", methods=["GET", "POST"])
def login():
    """Login page.
    ISSUES:
    - No rate limiting (brute force possible)
    - No account lockout
    - Password in MD5
    - No CSRF token
    """
    if request.method == "POST":
        username = request.form.get("username", "")
        password = request.form.get("password", "")
        password_hash = hash_password(password)

        user = db.authenticate_user(username, password_hash)
        if user:
            session["user"] = {"id": user["id"], "username": user["username"], "role": user["role"]}
            log_action(username, "login", "success")
            return redirect("/dashboard")
        else:
            log_action(username, "login", "failed")  # Logs failed attempt but no lockout
            return render_template_string(LOGIN_HTML, error="Ongeldige inloggegevens")

    return render_template_string(LOGIN_HTML, error=None)


@app.route("/dashboard")
@require_login
def dashboard():
    """Main dashboard — loads all data on every request."""
    data = claims_processor.get_dashboard_data(session["user"]["username"])
    return render_template_string(DASHBOARD_HTML, data=data, user=session["user"])


# ============================================================
# Claims endpoints — business logic in route handlers
# ============================================================

@app.route("/claims/submit", methods=["POST"])
@require_login
def submit_claim():
    """Submit new claim.
    ISSUE: No input validation, no file upload scanning.
    """
    result = claims_processor.submit_claim(
        customer_id=request.form.get("customer_id"),
        policy_id=request.form.get("policy_id"),
        claim_type=request.form.get("claim_type"),
        description=request.form.get("description", ""),
        amount=float(request.form.get("amount", 0)),
    )
    if result["success"]:
        return redirect("/dashboard")
    return jsonify(result), 400


@app.route("/claims/<int:claim_id>/process", methods=["POST"])
@require_login
def process_claim(claim_id):
    """Process (approve/reject) a claim.
    ISSUE: No role-based access control — any logged-in user can approve.
    """
    decision = request.form.get("decision")
    approved_amount = request.form.get("approved_amount")
    notes = request.form.get("notes", "")

    if approved_amount:
        approved_amount = float(approved_amount)

    result = claims_processor.process_claim(
        claim_id=claim_id,
        processor_username=session["user"]["username"],
        decision=decision,
        approved_amount=approved_amount,
        notes=notes,
    )
    return jsonify(result)


@app.route("/claims/search")
@require_login
def search_claims():
    """Search claims — passes user input directly to SQL."""
    query = request.args.get("q", "")
    # VULNERABILITY: User input goes directly to SQL query
    results = db.search_customers(query)
    return jsonify([dict(r) for r in results])


# ============================================================
# Payment endpoints
# ============================================================

@app.route("/payments/batch", methods=["POST"])
@require_login
def batch_payments():
    """Trigger batch payment processing.
    ISSUE: No confirmation, no preview, just processes everything.
    """
    results = payment_processor.batch_process()
    return jsonify(results)


@app.route("/payments/<int:payment_id>/refund", methods=["POST"])
@require_login
def refund_payment(payment_id):
    """Process refund.
    ISSUE: No authorization check, no reason validation.
    """
    reason = request.form.get("reason", "No reason provided")
    result = refund_processor.process_refund(payment_id, reason)
    return jsonify(result)


# ============================================================
# Reports — blocking operations in web handlers
# ============================================================

@app.route("/reports/monthly")
@require_login
def monthly_report():
    """Generate monthly report.
    ISSUE: Synchronous, can timeout on large datasets.
    """
    year = int(request.args.get("year", datetime.now().year))
    month = int(request.args.get("month", datetime.now().month))
    report = claims_processor.generate_report(year, month)
    return jsonify(report)


# ============================================================
# HTML Templates — inline (no template engine separation)
# ============================================================

LOGIN_HTML = """
<!DOCTYPE html>
<html>
<head><title>NN Claims - Login</title></head>
<body>
    <h1>Nationale-Nederlanden Claims Portal</h1>
    {% if error %}<p style="color:red">{{ error }}</p>{% endif %}
    <form method="POST">
        <input name="username" placeholder="Gebruikersnaam" required>
        <input name="password" type="password" placeholder="Wachtwoord" required>
        <button type="submit">Inloggen</button>
    </form>
</body>
</html>
"""

DASHBOARD_HTML = """
<!DOCTYPE html>
<html>
<head><title>NN Claims - Dashboard</title></head>
<body>
    <h1>Claims Dashboard</h1>
    <p>Welkom, {{ user.username }}</p>
    <div>
        <h2>Overzicht</h2>
        <p>Openstaand: {{ data.pending_count }}</p>
        <p>Gemarkeerd: {{ data.flagged_count }}</p>
        <p>Vandaag goedgekeurd: {{ data.approved_today }}</p>
        <p>Totaal openstaand bedrag: €{{ "%.2f"|format(data.total_pending_amount) }}</p>
    </div>
</body>
</html>
"""


# ============================================================
# Application startup — no proper initialization
# ============================================================

def create_app(db_path=None):
    """Factory function (added later, not fully integrated)."""
    global db, claims_processor, payment_processor, refund_processor
    db = Database(db_path)
    db.connect()
    claims_processor = ClaimsProcessor(db)
    payment_processor = PaymentProcessor(db)
    refund_processor = RefundProcessor(db)
    return app


if __name__ == "__main__":
    # ISSUE: Debug mode in production, binds to all interfaces
    app.run(host="0.0.0.0", port=5000, debug=True)
