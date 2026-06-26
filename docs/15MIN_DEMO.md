# 15-Minuten Live Demo Script — Devin × Nationale-Nederlanden

**Meeting met Tjerrie Smit (Chief Analytics Officer)**

Repo: https://github.com/jelteeshuis-glitch/nn-insurance-platform-demo

---

## Doel

Toon Tjerrie de agentic loop (plan → uitvoeren → testen → valideren) op een legacy codebase die lijkt op die van NN, en raak zijn drie kernthema's: **IT-simplificatie**, **pilot-naar-productie**, en **governance**.

## Eenmalige voorbereiding (voor de meeting)

- `git clone https://github.com/jelteeshuis-glitch/nn-insurance-platform-demo.git`
- Open het project in je IDE en zet een Devin-sessie klaar in een ander tabblad.
- Voor een **echte live build**: laat Devin de modernized code zelf maken. Demo op een branch waar de map `modernized/` is verwijderd (de `demo-live` branch). Houd de echte `modernized/` achter de hand als Devin uitloopt.
- Draai 's ochtends elke command één keer, zodat dependencies gecached zijn en output direct verschijnt.

---

## ⏱️ 0:00 – 2:00 | Opener: spreek zijn taal (Scenario 5)

Zeg:

> "Tjerrie, je zei: taalmodellen veranderen niets, AI-agents die actie ondernemen wél. Dat is precies wat Devin doet voor software-engineering. Laat me het je tonen op een codebase die lijkt op wat we bij verzekeraars zien."

Toon de repo-structuur. Wijs naar `legacy/` versus `governance/`. Leg nog geen code uit — frame alleen: "before, after, en de governance-laag die een gereguleerde verzekeraar nodig heeft."

## ⏱️ 2:00 – 5:00 | Het probleem is echt en meetbaar (Scenario 1)

Draai live in de terminal (print snel):

```bash
cd legacy
pip install -r requirements.txt
bandit -r src/                 # -> SQL-injectie, hardcoded 'Welkom2019!', MD5
pytest tests/ --cov=src        # -> ~45% dekking
```

Zeg:

> "Hardcoded wachtwoorden, SQL-injectie, 45% testdekking. Dit is de verouderde IT-laag waar je 300 use-cases op vastlopen. Nubank loste exact dit op met Devin: 8× efficiency, 20× kostenbesparing."

## ⏱️ 5:00 – 11:00 | Devin in actie (Scenario 2) — het kernmoment

Plak in de Devin-sessie deze prompt letterlijk:

> "Refactor the claims processing in `legacy/src/claims.py` into a clean service under `modernized/services/claims/`. Use Pydantic models with validation, enforce a claim-status state machine, add four-eyes approval for claims over €50.000, and fix every Bandit finding (no SQL injection, no hardcoded secrets). Add a pytest suite with >85% coverage. Run the tests and Bandit to prove it's clean."

Vertel mee terwijl Devin werkt — dit zijn de verkooppunten:

- **Het beslist vóóraf of doorgaan zinvol is.** Plan + confidence score verschijnt eerst.
- **Het neemt actie en valideert zichzelf — dat is de agent.** Het bewerkt meerdere bestanden, draait tests, leest fouten, fixt ze.

Als alles groen is, toon het contrast:

```bash
cd ..
bandit -r modernized/ --exclude '*/tests/*' --skip B101   # -> 0 findings
pytest modernized/tests/ -q                               # -> alles slaagt
```

Zeg:

> "Van 45% naar 90%+ dekking en 0 security findings — in minuten, niet weken. Dít is pilot-naar-productie."

## ⏱️ 11:00 – 14:00 | Governance: de doorslaggevende laag (Scenario 4)

Draai:

```bash
python -c "from governance.compliance.solvency_ii import SolvencyIIValidator; from governance.audit import AuditLogger; print(SolvencyIIValidator(audit_logger=AuditLogger(), config={'dual_approval_enabled':True}).generate_report()['compliance_score'])"   # -> 1.0
```

Open `governance/models/fraud_detection_card.yaml` en `governance/audit/audit_logger.py`. Zeg:

> "Solvency II: onveranderlijke audit-trail met hash-chain. EU AI Act: elk model heeft een governance-card, risico-classificatie en human-override. PII wordt automatisch gemaskeerd. Elke Devin-stap staat in de work-log. Zero-retention, draait in jullie VPC."

## ⏱️ 14:00 – 15:00 | Afsluiting

> "Drie dingen: je legacy-laag versnelt, je pilots halen productie, en governance is ingebouwd — niet achteraf. Voorstel: 4-weken proof-of-value op één echte NN-codebase. En handig: Cognizant heeft net een partnerschap met Cognition, dus dit sluit aan op je bestaande SI-traject."

---

## Vangnetten (belangrijk)

- **Als Devin uitloopt:** stop met wachten — schakel over naar de vooraf gebouwde `modernized/` map en loop het resultaat door. Het verhaal is identiek; je toont in plaats van genereert.
- **Als er geen internet/Devin-toegang is op locatie:** sla 5:00–11:00 live build over; toon `git log` / de `modernized/` diff en `docs/DEMO_SCRIPT.md`.
- **Pre-run elke command één keer** de ochtend zelf, zodat dependencies gecached zijn en output direct is.

---

## Snelle command-cheatsheet

```bash
# 1. Probleem tonen
cd legacy && pip install -r requirements.txt
bandit -r src/
pytest tests/ --cov=src

# 2. Devin-prompt (zie 5:00-11:00)

# 3. Resultaat tonen
cd ..
bandit -r modernized/ --exclude '*/tests/*' --skip B101
pytest modernized/tests/ -q

# 4. Governance
python -c "from governance.compliance.solvency_ii import SolvencyIIValidator; from governance.audit import AuditLogger; print(SolvencyIIValidator(audit_logger=AuditLogger(), config={'dual_approval_enabled':True}).generate_report()['compliance_score'])"
```
