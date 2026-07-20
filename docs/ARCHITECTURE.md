# Architecture Decision Records

## ADR-001: Microservices Decomposition

**Status**: Accepted  
**Date**: 2024-11-01  
**Context**: The legacy monolith has become unmaintainable with 3-week deploy cycles.

### Decision
Decompose into 5 bounded contexts:
1. **Claims Service** — Claim lifecycle management
2. **Policy Service** — Policy administration
3. **Payment Service** — Financial transactions (PCI-DSS isolated)
4. **Customer Service** — Customer data (GDPR isolated)
5. **Governance Service** — Audit, compliance, AI model governance

### Consequences
- Teams can deploy independently
- Failure isolation (payment failure doesn't block claims)
- Technology heterogeneity possible per service
- Increased operational complexity (mitigated by CI/CD automation)

---

## ADR-002: Event-Driven Architecture

**Status**: Accepted  
**Date**: 2024-11-01  
**Context**: Legacy system has tight coupling between all modules.

### Decision
Adopt event-driven architecture with Azure Service Bus for inter-service communication.

### Key Events
| Event | Publisher | Consumers |
|-------|-----------|-----------|
| `claim.submitted` | Claims | Fraud Detection, Notifications |
| `claim.approved` | Claims | Payments, Notifications |
| `claim.rejected` | Claims | Notifications |
| `payment.completed` | Payments | Claims, Notifications |
| `fraud.flagged` | Fraud Detection | Claims |

### Consequences
- Services are decoupled (can evolve independently)
- Natural audit trail from event log
- Supports event sourcing for compliance
- Eventually consistent (acceptable for this domain)

---

## ADR-003: Immutable Audit Trail

**Status**: Accepted  
**Date**: 2024-11-01  
**Context**: Solvency II requires complete, tamper-evident audit trail.

### Decision
Implement hash-chain audit logging with:
- SHA-256 chain linking (each entry includes previous hash)
- Append-only storage (no update/delete operations)
- Automatic PII detection and masking
- 7-year retention for financial records
- Real-time streaming for monitoring

### Consequences
- Full traceability for regulator audits
- Tamper detection via chain verification
- GDPR compliance through PII masking
- Storage costs managed via tiered archival

---

## ADR-004: AI Model Governance

**Status**: Accepted  
**Date**: 2024-11-01  
**Context**: EU AI Act classifies insurance claims assessment as high-risk AI.

### Decision
Implement model governance registry with:
- Mandatory model cards for all deployed models
- Risk classification per EU AI Act Annex III
- Human-in-the-loop enforcement for high-risk decisions
- Bias monitoring and fairness constraints
- Override mechanism with audit trail

### Consequences
- EU AI Act compliance from day one
- Explainability built into the system
- Slower model deployment (governance gate) but lower risk
- Clear accountability chain

---

## ADR-005: Security-First Design

**Status**: Accepted  
**Date**: 2024-11-01  
**Context**: Legacy system has 23 critical security findings.

### Decision
- All SQL via parameterized queries (SQLAlchemy ORM)
- Secrets from Azure Key Vault (no hardcoded credentials)
- RBAC with least-privilege principle
- Rate limiting and account lockout
- IBAN tokenization (PCI-DSS)
- Encryption at rest for all PII
- SAST/DAST in CI/CD pipeline

### Consequences
- Zero critical findings in modernized codebase
- Veracode/SonarQube clean reports
- Slightly more complex deployment (vault integration)
- Security as enabler, not blocker

---

## ADR-006: Repository Pattern with Pluggable Persistence

**Status**: Accepted
**Date**: 2026-07-20
**Context**: Services referenced an abstract `repository` that was never defined.
The demo needs runnable persistence without provisioning a database, while
production must satisfy ADR-005 (parameterized access via SQLAlchemy).

### Decision
- Define an abstract async `Repository[T]` interface in `modernized/shared/repository.py`
  (`save`, `get`, `list_all`, `delete`, `exists`, `find`).
- Provide an `InMemoryRepository[T]` concrete adapter for the demo and tests.
- Services depend only on the interface, so a SQLAlchemy-backed adapter can be
  dropped in per service with no changes to business logic.
- Payments adds a `PaymentRepository` with a secondary idempotency-key index.

### Consequences
- Services are testable and runnable with zero infrastructure.
- Swapping to a real DB (Postgres per service) is a localized change.
- The in-memory adapter is **not** durable and is for the demo only.

---

## ADR-007: FastAPI Entry Points per Service

**Status**: Accepted
**Date**: 2026-07-20
**Context**: The monolithic Flask routes in `legacy/src/app.py` must be replaced
with per-service HTTP APIs consistent with the microservices decomposition.

### Decision
- Each bounded context exposes a thin FastAPI app (`services/<svc>/api.py`) via a
  `create_app(service)` factory plus a module-level `app` for `uvicorn`.
- Routes only translate HTTP ↔ domain calls; all rules live in the service layer.
- Caller identity/role arrive via `X-Actor` / `X-Actor-Role` headers (a real
  deployment resolves these from a validated JWT — see ADR-005).
- Domain exceptions map to HTTP status codes centrally
  (`PermissionError` → 403, `ValueError` → 400) in `shared/http.py`.

### Consequences
- Independent deployability (ADR-001) with per-service OpenAPI docs.
- Consistent validation via the shared Pydantic domain models.
- Header-based auth is a demo shim; production terminates real JWTs at the edge.

---

## ADR-008: In-Process Event Bus as Local Adapter

**Status**: Accepted
**Date**: 2026-07-20
**Context**: ADR-002 targets Azure Service Bus, which is unavailable in the demo.

### Decision
- Use the existing in-process async `EventBus` as the local adapter and wire all
  ADR-002 subscriptions in a single composition root (`modernized/platform.py`):
  `claim.submitted` → fraud + notifications, `claim.approved` → payments +
  notifications, `fraud.flagged` → claims, `payment.completed` → claims +
  notifications.
- Failed handlers are isolated to the bus dead-letter list rather than failing
  the originating transaction.

### Consequences
- The full event-driven flow is exercised end-to-end in tests.
- The bus is the seam for a Service Bus adapter later (same publish/subscribe API).
- Handlers must be idempotent (payment processing keys on the claim id).

---

## ADR-009: Encryption & Tokenization Boundaries

**Status**: Accepted
**Date**: 2026-07-20
**Context**: The legacy system stored BSN/email in cleartext and logged raw IBANs,
violating GDPR (ADR-003) and PCI-DSS (ADR-005).

### Decision
- Introduce a `shared/encryption.py` abstraction with a `FernetEncryptionService`;
  the key is sourced from `ENCRYPTION_KEY` (Key Vault / secret store in prod) and
  generated ephemerally only for the demo.
- Customer PII (BSN, email, phone, address) is encrypted at rest on the entity;
  plaintext PII never persists.
- Payment IBANs are tokenized (SHA-256 → `tok_…`) at the API boundary; the
  `Payment` entity stores only the token and passes mod-97 validation first.
- The audit logger continues to mask any residual PII in log details (ADR-003).

### Consequences
- PII/PCI data is protected at rest and absent from logs.
- Right-to-erasure anonymizes contact data while retaining legally-required records.
- Tokenization is one-way for the demo; production would use a reversible vault
  token if de-tokenization for payout is required.
