# NN Insurance Claims Platform — Legacy Modernization Demo

> **Demo repository** showcasing how AI-powered software engineering (Devin) accelerates
> legacy modernization, pilot-to-production maturity, and governance compliance for
> regulated financial institutions.

---

## 🎯 Business Context

Nationale Nederlanden's **Future Ready** strategy targets:
- **IT simplification** — reducing complexity in legacy systems
- **€200M cost savings** — through engineering efficiency
- **300+ AI use cases** — scaling from pilot to production
- **Regulatory compliance** — Solvency II, EU AI Act, GDPR

This repository demonstrates the **before** (legacy monolith) and **after** (modernized,
production-ready microservices) of an insurance claims processing platform — the exact
transformation Devin accelerates.

---

## 📁 Repository Structure

```
├── legacy/                    # ⚠️  The "before" — monolithic claims system
│   ├── src/                   #     Single codebase, tightly coupled
│   │   ├── app.py            #     Main application (1500+ lines, god object)
│   │   ├── database.py       #     Raw SQL, no ORM, injection vulnerabilities
│   │   ├── claims.py         #     Claims processing (business logic + DB + UI)
│   │   ├── payments.py       #     Payment handling (PCI-DSS violations)
│   │   └── utils.py          #     Shared utilities (hardcoded config)
│   └── tests/                 #     ~45% coverage, no integration tests
│
├── modernized/                # ✅  The "after" — refactored microservices
│   ├── services/
│   │   ├── claims/           #     Claims service (bounded context)
│   │   ├── policy/           #     Policy administration service
│   │   ├── payments/         #     PCI-DSS compliant payment service
│   │   └── customer/         #     Customer data service (GDPR-ready)
│   ├── shared/               #     Shared libraries (auth, logging, events)
│   └── tests/                #     90%+ coverage, integration + contract tests
│
├── governance/                # 🔒  Governance & compliance layer
│   ├── audit/                #     Immutable audit logging
│   ├── compliance/           #     Solvency II & EU AI Act checks
│   └── models/               #     AI model governance registry
│
├── .github/workflows/         # 🚀  CI/CD pipeline
│   ├── security-scan.yml     #     SAST + dependency scanning
│   ├── test-coverage.yml     #     Coverage gates (minimum 80%)
│   └── compliance-check.yml  #     Automated compliance validation
│
└── docs/                      #     Architecture decision records
```

---

## 🔴 Legacy System — Key Problems Demonstrated

| Problem | Impact | File |
|---------|--------|------|
| Monolithic god object (1500+ LOC) | Impossible to scale teams | `legacy/src/app.py` |
| SQL injection vulnerabilities | Critical security risk | `legacy/src/database.py` |
| Hardcoded credentials | Compliance violation | `legacy/src/utils.py` |
| No input validation | Data integrity issues | `legacy/src/claims.py` |
| ~45% test coverage | Cannot safely refactor | `legacy/tests/` |
| No audit trail | Solvency II non-compliance | — |
| PCI-DSS violations | Regulatory risk | `legacy/src/payments.py` |
| Tight coupling | 3-week deploy cycles | All files |

---

## ✅ Modernized System — Devin's Contribution

| Improvement | Metric | How Devin Helps |
|-------------|--------|-----------------|
| Microservices decomposition | 5 bounded contexts | Automated refactoring at scale |
| Test coverage | 45% → 92% | Generates tests + edge cases |
| Security remediation | 23 CVEs → 0 | Fixes SonarQube/Veracode findings |
| CI/CD pipeline | Manual → Automated | Full pipeline generation |
| Audit logging | None → Complete | Compliance-aware code generation |
| Documentation | Outdated → Current | ADRs + API docs from code |
| Deploy frequency | 3 weeks → Daily | Confidence through test coverage |

---

## 🏛️ Governance & Compliance (Scenario 4)

This demo specifically addresses regulated-sector requirements:

### Solvency II
- Immutable audit trail for all data mutations
- Segregation of duties in approval workflows
- Complete traceability from business event to system action

### EU AI Act
- Model governance registry with risk classification
- Explainability logging for AI-driven decisions
- Human-in-the-loop enforcement for high-risk classifications

### GDPR
- PII detection and masking in logs
- Right-to-erasure support in data layer
- Consent management integration points

---

## 🚀 Running the Demo

### Legacy system (showing the problems)
```bash
cd legacy
pip install -r requirements.txt
python src/app.py
# Run security scan to see vulnerabilities:
bandit -r src/
# Run tests to see low coverage:
pytest tests/ --cov=src --cov-report=term-missing
```

### Modernized system (showing the solution)
```bash
cd modernized
pip install -r requirements.txt
pytest tests/ --cov --cov-report=term-missing
# Coverage: 92%
```

---

## 💡 Demo Narrative for Tjerrie Smit

### Opening (Scenario 5 — Agentic AI framing)
> "Taalmodellen alleen veranderen niet hoe organisaties werken — dat gebeurt
> pas met AI-agents die echt actie ondernemen."
>
> Devin **is** die definitie: het plant, voert uit, en valideert — end-to-end.

### Core Demo (Scenarios 1 + 2)
1. Show the legacy codebase — recognizable technical debt
2. Give Devin a task: "Refactor claims processing into a microservice, add tests, fix security findings"
3. Watch Devin execute: plan → implement → test → validate
4. Result: production-ready code with 90%+ coverage in hours, not weeks

### Closer (Scenario 4 — Governance)
> "Elke stap is traceerbaar in de work-log. Zero-retention op enterprise-plannen.
> Uw code verlaat nooit uw VPC."

---

## 📊 Expected Impact (Based on Reference Cases)

| Metric | Industry Benchmark | NN Potential |
|--------|-------------------|--------------|
| Engineering efficiency | 8× (Nubank) | 5-8× on legacy modernization |
| Cost per refactoring task | 20× reduction | €200M target acceleration |
| Security fix turnaround | 5-10% dev time saved | Faster Veracode remediation |
| Test coverage improvement | 50% → 90% in days | De-risk production deployments |
| Pilot → Production time | Weeks → Days | 300 use cases faster to market |

---

## 🔐 Enterprise Security Features Demonstrated

- **Audit log**: Every Devin action is logged and traceable
- **Zero retention**: Code is not used to train models
- **VPC deployment**: Runs within NN's network boundary
- **SOC 2 Type II**: Enterprise compliance certified
- **SSO/SAML**: Integration with NN's identity provider

---

*This repository is a synthetic demonstration. No real customer data or proprietary
NN systems are represented.*
