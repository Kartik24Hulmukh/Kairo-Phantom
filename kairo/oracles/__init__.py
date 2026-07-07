# PROVENANCE: original | clean-room oracle package for specs/VERIFICATION_ORACLES.md
"""kairo.oracles — deterministic, kill-proven verification oracles.

Each oracle asserts a REAL system outcome and ships with a kill-proof (a known-bad
input it must reject). See specs/VERIFICATION_ORACLES.md and prompts/02.
"""

from kairo.oracles.docx_tracked_changes import (
    Revision,
    extract_revisions,
    reconstruct_original_and_final,
    verify_docx_tracked_changes,
)
from kairo.oracles.clause_coverage import verify_clause_coverage
from kairo.oracles.no_hallucinated_citation import verify_no_hallucinated_citation
from kairo.oracles.legal_redline_pipeline import (
    AppliedEdit,
    FlaggedClause,
    RedlineResult,
    redline_contract,
)
from kairo.oracles.ed25519_audit_log import (
    AuditEntry,
    Ed25519AuditLog,
)
from kairo.oracles.zero_egress_report import (
    ZeroEgressReport,
    generate_zero_egress_report,
    verify_zero_egress_report,
    report_from_json,
)
from kairo.oracles.airgap_egress import (
    AirgapEgressReport,
    EgressAttempt,
    SocketEgressInterceptor,
    run_airgap_egress_oracle,
    verify_airgap_egress,
    run_kill_proof,
    sealed_binary_scan,
)
from kairo.oracles.production_ops import (  # noqa: F401
    AirgapTelemetryReport,
    UpdateSignatureReport,
    SupplyChainReport,
    run_airgap_telemetry_oracle,
    verify_airgap_telemetry,
    run_airgap_telemetry_kill_proof,
    run_update_signature_oracle,
    verify_update_signature,
    run_update_signature_kill_proof,
    run_supply_chain_oracle,
    verify_supply_chain,
    run_supply_chain_kill_proof,
    scan_for_secrets,
    generate_cyclonedx_sbom,
    validate_sbom,
)

__all__ = [
    "Revision",
    "extract_revisions",
    "reconstruct_original_and_final",
    "verify_docx_tracked_changes",
    "verify_clause_coverage",
    "verify_no_hallucinated_citation",
    "AppliedEdit",
    "FlaggedClause",
    "RedlineResult",
    "redline_contract",
    "AuditEntry",
    "Ed25519AuditLog",
    "ZeroEgressReport",
    "generate_zero_egress_report",
    "verify_zero_egress_report",
    "report_from_json",
    "AirgapEgressReport",
    "EgressAttempt",
    "SocketEgressInterceptor",
    "run_airgap_egress_oracle",
    "verify_airgap_egress",
    "run_kill_proof",
    "sealed_binary_scan",
    "AirgapTelemetryReport",
    "UpdateSignatureReport",
    "SupplyChainReport",
    "run_airgap_telemetry_oracle",
    "verify_airgap_telemetry",
    "run_airgap_telemetry_kill_proof",
    "run_update_signature_oracle",
    "verify_update_signature",
    "run_update_signature_kill_proof",
    "run_supply_chain_oracle",
    "verify_supply_chain",
    "run_supply_chain_kill_proof",
    "scan_for_secrets",
    "generate_cyclonedx_sbom",
    "validate_sbom",
]
