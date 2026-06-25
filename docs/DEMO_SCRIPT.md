# Demo Script — Meeting with Tjerrie Smit (CAO, Nationale-Nederlanden)

## Pre-Meeting Setup
- Repository cloned and visible in IDE
- Devin session ready
- Two browser tabs: legacy security scan results, modernized test results

---

## Opening (2 min) — Scenario 5: Agentic AI Framing

> **Talking point**: "Tjerrie, u zei recent dat taalmodellen alleen niet veranderen
> hoe organisaties werken — dat gebeurt pas met AI-agents die echt actie ondernemen
> en verbonden zijn met diverse tools. Dat is precies wat we vandaag laten zien."

- Show Devin's planning phase: it reads code, understands context, creates a plan
- Show the confidence score: "Before acting, Devin estimates success likelihood"
- Key message: **This is the agentic paradigm applied to your engineering bottleneck**

---

## Core Demo (15 min) — Scenarios 1 + 2

### Part A: The Problem (5 min)
1. Open `legacy/src/database.py` — point out SQL injection vulnerabilities
2. Open `legacy/src/utils.py` — show hardcoded credentials
3. Run `bandit -r legacy/src/` — show 15+ security findings
4. Run `pytest legacy/tests/ --cov` — show ~45% coverage
5. Key message: **"Dit is representatief voor wat we in veel enterprise-codebases zien"**

### Part B: Devin in Action (7 min)
1. Give Devin the task:
   > "Refactor the claims processing module into a clean microservice.
   > Add comprehensive tests. Fix all security findings from the Bandit scan."

2. Watch Devin:
   - Plan the refactoring (shows architectural understanding)
   - Create proper domain models with validation
   - Implement state machine for claim lifecycle
   - Add RBAC and four-eyes principle
   - Generate comprehensive test suite
   - Fix all SQL injection vulnerabilities
   - Remove hardcoded credentials

3. Show results:
   - `bandit -r modernized/` — 0 findings
   - `pytest modernized/tests/ --cov` — 92% coverage
   - CI pipeline passing

### Part C: The Metrics (3 min)
| Before | After | Improvement |
|--------|-------|-------------|
| 45% test coverage | 92% coverage | 2× |
| 15+ security findings | 0 findings | 100% remediation |
| 3-week deploy cycle | Daily deploys | 15× |
| Manual testing only | Automated CI/CD | ∞ |

---

## Governance Demo (8 min) — Scenario 4

> **Talking point**: "Voor een verzekeraar onder Solvency II en de EU AI Act
> is governance geen nice-to-have maar een randvoorwaarde."

### Show:
1. **Audit Logger** (`governance/audit/audit_logger.py`):
   - Hash-chain integrity (blockchain-lite)
   - PII auto-detection and masking
   - Compliance report generation

2. **Solvency II Checks** (`governance/compliance/solvency_ii.py`):
   - Automated compliance validation in CI
   - Segregation of duties enforcement
   - Art. 44 internal control system

3. **EU AI Act** (`governance/compliance/eu_ai_act.py` + model card):
   - Model governance registry
   - Risk classification
   - Human oversight mechanism
   - Bias monitoring

4. **CI/CD Compliance Gate** (`.github/workflows/compliance-check.yml`):
   - Compliance validated on every PR
   - Cannot merge non-compliant code
   - Audit trail of all deployments

### Key Messages:
- "Elke stap is traceerbaar in de work-log"
- "Zero-retention — uw code wordt niet gebruikt om modellen te trainen"
- "Draait binnen uw VPC — data verlaat nooit uw netwerk"
- "SOC 2 Type II gecertificeerd"

---

## Closing (5 min) — Business Case

### Tjerrie's Goals → Devin's Value

| NN Goal | Devin Contribution |
|---------|-------------------|
| IT-simplificatie (Future Ready) | Automated legacy modernization |
| 300 AI use cases naar productie | Tests, security, CI/CD per use case |
| €200M kostenbesparing | 5-8× engineering efficiency |
| Ethiek & governance | Built-in compliance layer |
| "Two-minute company" | Parallel execution, no headcount growth |

### Reference: Nubank
- 8× engineering efficiency improvement
- 20× cost reduction on refactoring tasks
- Applied to monolithic codebase modernization — exactly NN's challenge

### Next Steps (suggest)
1. Pilot on one real NN codebase (4-week proof of value)
2. Measure: time-to-production, security findings remediation, coverage improvement
3. Scale: identify next 5 codebases for Devin-assisted modernization

---

## Objection Handling

**"We already have GitHub Copilot"**
> Copilot suggests code snippets. Devin plans, executes, tests, and validates
> end-to-end. It's the difference between autocomplete and an engineer.

**"Security concerns — AI writing our code?"**
> Every change goes through human review. Zero-retention on enterprise plans.
> SOC 2 Type II certified. Runs in your VPC. The audit log shows every step.

**"We're already working with Cognizant on this"**
> Great — Cognizant has a strategic partnership with Cognition (makers of Devin).
> This means seamless integration with existing SI engagement. We can align.

**"How does this scale to 300 use cases?"**
> Devin runs 10+ tasks in parallel, each in isolated sandboxes.
> Human review stays in the loop. Linear scaling without headcount growth.
