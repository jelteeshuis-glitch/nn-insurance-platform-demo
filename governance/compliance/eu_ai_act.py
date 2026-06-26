"""
EU AI Act Compliance Module

Implements requirements from the EU AI Act (Regulation 2024/1689) for
high-risk AI systems in the insurance domain.

Key requirements addressed:
- Article 9: Risk management system
- Article 10: Data governance
- Article 11: Technical documentation
- Article 13: Transparency and provision of information
- Article 14: Human oversight
- Article 15: Accuracy, robustness, and cybersecurity
"""
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Optional


class AIRiskCategory(str, Enum):
    """EU AI Act risk classification (Article 6)."""
    UNACCEPTABLE = "unacceptable"  # Banned
    HIGH = "high"  # Insurance pricing, claims assessment
    LIMITED = "limited"  # Chatbots, customer service
    MINIMAL = "minimal"  # Spam filters, search


class TransparencyLevel(str, Enum):
    """Required transparency level per risk category."""
    FULL = "full"  # Complete explainability required
    SUMMARY = "summary"  # Key factors must be disclosed
    NOTICE = "notice"  # User must know they interact with AI
    NONE = "none"  # No special requirements


@dataclass
class ModelCard:
    """AI Model Governance Card — Article 11 Technical Documentation.

    Every AI model deployed in production must have a complete model card
    documenting its purpose, limitations, and governance status.
    """
    model_id: str
    model_name: str
    version: str
    risk_category: AIRiskCategory
    transparency_level: TransparencyLevel

    # Purpose and scope
    intended_use: str
    out_of_scope_uses: list[str] = field(default_factory=list)
    target_population: str = ""

    # Technical details
    model_type: str = ""  # e.g., "gradient_boosting", "neural_network"
    input_features: list[str] = field(default_factory=list)
    output_description: str = ""
    performance_metrics: dict[str, float] = field(default_factory=dict)

    # Fairness and bias
    protected_attributes_tested: list[str] = field(default_factory=list)
    bias_metrics: dict[str, float] = field(default_factory=dict)
    fairness_constraints: list[str] = field(default_factory=list)

    # Governance
    owner: str = ""
    approved_by: str = ""
    approval_date: Optional[str] = None
    next_review_date: Optional[str] = None
    human_oversight_required: bool = True
    override_mechanism: str = ""

    # Lifecycle
    training_date: Optional[str] = None
    deployment_date: Optional[str] = None
    retirement_date: Optional[str] = None
    status: str = "development"  # development | staging | production | retired


@dataclass
class InferenceRecord:
    """Record of a single AI inference — for audit and explainability."""
    inference_id: str
    model_id: str
    timestamp: str
    input_data: dict[str, Any]  # Masked PII
    output: Any
    confidence: float
    explanation: dict[str, Any]  # Feature importance, decision path
    human_override: Optional[str] = None
    override_reason: Optional[str] = None


class AIGovernanceRegistry:
    """Central registry for AI model governance.

    Maintains inventory of all AI models and their compliance status.
    Required under EU AI Act Article 51 (registration).
    """

    def __init__(self):
        self._models: dict[str, ModelCard] = {}
        self._inferences: list[InferenceRecord] = []

    def register_model(self, model_card: ModelCard) -> None:
        """Register a model in the governance registry."""
        if model_card.risk_category == AIRiskCategory.UNACCEPTABLE:
            raise ValueError(
                f"Model {model_card.model_id} classified as UNACCEPTABLE risk — "
                "deployment is prohibited under EU AI Act Article 5"
            )
        self._models[model_card.model_id] = model_card

    def get_model(self, model_id: str) -> Optional[ModelCard]:
        """Retrieve model governance card."""
        return self._models.get(model_id)

    def validate_deployment_readiness(self, model_id: str) -> dict:
        """Check if a model is ready for production deployment.

        Validates all EU AI Act requirements are met before allowing deployment.
        """
        model = self._models.get(model_id)
        if not model:
            return {"ready": False, "errors": ["Model not found in registry"]}

        errors = []
        warnings = []

        # Article 9: Risk management
        if model.risk_category == AIRiskCategory.HIGH:
            if not model.performance_metrics:
                errors.append("High-risk model missing performance metrics")
            if not model.bias_metrics:
                errors.append("High-risk model missing bias assessment")
            if not model.human_oversight_required:
                errors.append("High-risk model must require human oversight")

        # Article 11: Technical documentation
        if not model.intended_use:
            errors.append("Missing intended use documentation")
        if not model.input_features:
            errors.append("Missing input feature documentation")
        if not model.owner:
            errors.append("Missing model owner")

        # Article 14: Human oversight
        if model.risk_category in (AIRiskCategory.HIGH, AIRiskCategory.LIMITED):
            if not model.override_mechanism:
                errors.append("Missing human override mechanism")

        # Governance approval
        if not model.approved_by:
            warnings.append("Model not yet approved by governance board")
        if not model.next_review_date:
            warnings.append("No review date scheduled")

        return {
            "ready": len(errors) == 0,
            "model_id": model_id,
            "risk_category": model.risk_category.value,
            "errors": errors,
            "warnings": warnings,
        }

    def record_inference(self, record: InferenceRecord) -> None:
        """Record an AI inference for auditability (Article 12: Record-keeping)."""
        self._inferences.append(record)

    def record_human_override(
        self, inference_id: str, override_decision: str, reason: str
    ) -> None:
        """Record when a human overrides an AI decision (Article 14)."""
        for record in self._inferences:
            if record.inference_id == inference_id:
                record.human_override = override_decision
                record.override_reason = reason
                break

    def get_model_performance_report(self, model_id: str) -> dict:
        """Generate performance and fairness report for a model."""
        model = self._models.get(model_id)
        if not model:
            return {"error": "Model not found"}

        model_inferences = [
            r for r in self._inferences if r.model_id == model_id
        ]
        overrides = [r for r in model_inferences if r.human_override]

        return {
            "model_id": model_id,
            "model_name": model.model_name,
            "version": model.version,
            "risk_category": model.risk_category.value,
            "total_inferences": len(model_inferences),
            "human_overrides": len(overrides),
            "override_rate": len(overrides) / len(model_inferences)
            if model_inferences
            else 0,
            "performance_metrics": model.performance_metrics,
            "bias_metrics": model.bias_metrics,
            "status": model.status,
        }

    def list_models(self, risk_category: Optional[AIRiskCategory] = None) -> list[dict]:
        """List all registered models, optionally filtered by risk category."""
        models = self._models.values()
        if risk_category:
            models = [m for m in models if m.risk_category == risk_category]

        return [
            {
                "model_id": m.model_id,
                "model_name": m.model_name,
                "version": m.version,
                "risk_category": m.risk_category.value,
                "status": m.status,
                "owner": m.owner,
                "human_oversight": m.human_oversight_required,
            }
            for m in models
        ]
