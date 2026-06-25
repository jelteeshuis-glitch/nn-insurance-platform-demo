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
