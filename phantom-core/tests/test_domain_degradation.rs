// phantom-core/tests/test_domain_degradation.rs

use phantom_core::plugin::DomainCapability;
use phantom_core::swarm::SwarmOrchestrator;

#[test]
fn test_orchestrator_domain_capabilities() {
    let orchestrator = SwarmOrchestrator::new_for_test();

    // Check that "legal" capability is Real
    let legal_cap = orchestrator.get_domain_capability("legal");
    assert_eq!(legal_cap, Some(DomainCapability::Real));

    // Check that prompt-only domains like "medical" or "sales" are PromptOnly
    let medical_cap = orchestrator.get_domain_capability("medical");
    assert_eq!(medical_cap, Some(DomainCapability::PromptOnly));

    let sales_cap = orchestrator.get_domain_capability("sales");
    assert_eq!(sales_cap, Some(DomainCapability::PromptOnly));

    let engineer_cap = orchestrator.get_domain_capability("engineer");
    assert_eq!(engineer_cap, Some(DomainCapability::PromptOnly));
}

#[tokio::test]
async fn test_pro_stubs_fail() {
    use phantom_core::pro::{
        AuditExport, KairoPro, TeamMemoryVault, AUDIT_EXPORT_ERR, TEAM_MEMORY_VAULT_ERR,
    };
    let pro = KairoPro::new();
    let res = TeamMemoryVault::sync_to_s3(&pro).await;
    assert!(res.is_err());
    let err_msg = res.unwrap_err().to_string();
    assert_eq!(err_msg, TEAM_MEMORY_VAULT_ERR);

    let res2 = AuditExport::export_csv(&pro, "user", "app", "agent", "hash", "outcome", 100);
    assert!(res2.is_err());
    let err_msg2 = res2.unwrap_err().to_string();
    assert_eq!(err_msg2, AUDIT_EXPORT_ERR);
}
