"""
Governance tests — audit hash-chain, Solvency II checks, EU AI Act registry.
"""
import pytest

from governance.audit import AuditEntry, AuditEventType, AuditLogger
from governance.audit.audit_logger import PIIDetector
from governance.compliance.eu_ai_act import (
    AIGovernanceRegistry,
    AIRiskCategory,
    InferenceRecord,
    ModelCard,
    TransparencyLevel,
)
from governance.compliance.solvency_ii import ComplianceStatus, SolvencyIIValidator


def _entry(action="test") -> AuditEntry:
    return AuditEntry(
        event_type=AuditEventType.DATA_WRITE,
        actor="a", actor_role="agent", resource="r",
        action=action, outcome="success",
    )


# ============================================================
# Audit hash-chain + PII
# ============================================================

class TestAuditLogger:
    def test_chain_intact(self):
        log = AuditLogger()
        for i in range(3):
            log.log(_entry(f"action-{i}"))
        ok, bad = log.verify_integrity()
        assert ok and bad is None

    def test_tamper_detected(self):
        log = AuditLogger()
        log.log(_entry())
        log.log(_entry())
        log._entries[0].action = "tampered"
        ok, bad = log.verify_integrity()
        assert not ok
        assert bad is not None

    def test_query_filters(self):
        log = AuditLogger()
        log.log(_entry())
        log.log(AuditEntry(
            event_type=AuditEventType.DATA_READ, actor="b",
            actor_role="agent", resource="r", action="read", outcome="success",
        ))
        assert len(log.query(event_type=AuditEventType.DATA_READ)) == 1
        assert len(log.query(actor="b")) == 1

    def test_pii_masking_in_details(self):
        log = AuditLogger()
        log.log(AuditEntry(
            event_type=AuditEventType.DATA_WRITE, actor="a", actor_role="agent",
            resource="r", action="x", outcome="success",
            details={"note": "email jan@example.nl bsn 111222333"},
        ))
        stored = log._entries[0].details["note"]
        assert "jan@example.nl" not in stored
        assert "111222333" not in stored

    def test_pii_detector_scan_nested(self):
        masked = PIIDetector.scan_dict({
            "a": "NL91ABNA0417164300",
            "b": {"c": "0612345678"},
            "d": ["jan@example.nl", 5],
        })
        assert "NL91ABNA0417164300" not in masked["a"]
        assert "0612345678" not in masked["b"]["c"]
        assert "jan@example.nl" not in masked["d"][0]
        assert masked["d"][1] == 5


# ============================================================
# Solvency II
# ============================================================

class TestSolvencyII:
    def test_all_pass_by_default(self):
        validator = SolvencyIIValidator(audit_logger=AuditLogger())
        checks = validator.run_all_checks()
        assert all(c.status == ComplianceStatus.PASS for c in checks)

    def test_report_structure(self):
        report = SolvencyIIValidator(audit_logger=AuditLogger()).generate_report()
        assert report["framework"] == "Solvency II"
        assert report["failed"] == 0
        assert report["compliance_score"] == 1.0

    def test_dual_approval_disabled_fails(self):
        validator = SolvencyIIValidator(config={"dual_approval_enabled": False})
        report = validator.generate_report()
        assert report["failed"] >= 1

    def test_tampered_audit_fails_check(self):
        log = AuditLogger()
        log.log(_entry())
        log._entries[0].action = "tampered"
        validator = SolvencyIIValidator(audit_logger=log)
        checks = validator.run_all_checks()
        audit_check = next(c for c in checks if c.id == "SII-AUD-001")
        assert audit_check.status == ComplianceStatus.FAIL


# ============================================================
# EU AI Act
# ============================================================

def _high_risk_card(ready=True) -> ModelCard:
    card = ModelCard(
        model_id="fraud_v1",
        model_name="Fraud Detector",
        version="1.0",
        risk_category=AIRiskCategory.HIGH,
        transparency_level=TransparencyLevel.FULL,
        intended_use="Detect fraudulent claims",
    )
    if ready:
        card.performance_metrics = {"auc": 0.9}
        card.bias_metrics = {"demographic_parity": 0.02}
        card.input_features = ["amount", "keywords"]
        card.owner = "risk-team"
        card.override_mechanism = "manual review"
        card.approved_by = "board"
        card.next_review_date = "2027-01-01"
    return card


class TestEuAiAct:
    def test_register_and_get(self):
        reg = AIGovernanceRegistry()
        reg.register_model(_high_risk_card())
        assert reg.get_model("fraud_v1") is not None

    def test_unacceptable_risk_rejected(self):
        reg = AIGovernanceRegistry()
        card = _high_risk_card()
        card.risk_category = AIRiskCategory.UNACCEPTABLE
        with pytest.raises(ValueError, match="UNACCEPTABLE"):
            reg.register_model(card)

    def test_deployment_ready(self):
        reg = AIGovernanceRegistry()
        reg.register_model(_high_risk_card(ready=True))
        result = reg.validate_deployment_readiness("fraud_v1")
        assert result["ready"] is True
        assert result["errors"] == []

    def test_deployment_not_ready_lists_errors(self):
        reg = AIGovernanceRegistry()
        reg.register_model(_high_risk_card(ready=False))
        result = reg.validate_deployment_readiness("fraud_v1")
        assert result["ready"] is False
        assert any("performance" in e for e in result["errors"])

    def test_deployment_unknown_model(self):
        reg = AIGovernanceRegistry()
        result = reg.validate_deployment_readiness("nope")
        assert result["ready"] is False

    def test_inference_and_override_report(self):
        reg = AIGovernanceRegistry()
        reg.register_model(_high_risk_card())
        reg.record_inference(InferenceRecord(
            inference_id="i1", model_id="fraud_v1", timestamp="now",
            input_data={}, output="flagged", confidence=0.8, explanation={},
        ))
        reg.record_human_override("i1", "cleared", "false positive")
        report = reg.get_model_performance_report("fraud_v1")
        assert report["total_inferences"] == 1
        assert report["human_overrides"] == 1
        assert report["override_rate"] == 1.0

    def test_performance_report_unknown(self):
        assert "error" in AIGovernanceRegistry().get_model_performance_report("x")

    def test_list_models_filter(self):
        reg = AIGovernanceRegistry()
        reg.register_model(_high_risk_card())
        assert len(reg.list_models()) == 1
        assert len(reg.list_models(AIRiskCategory.HIGH)) == 1
        assert len(reg.list_models(AIRiskCategory.MINIMAL)) == 0
