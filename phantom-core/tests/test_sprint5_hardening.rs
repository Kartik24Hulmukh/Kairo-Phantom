/// Sprint 5 — Hardening & Release Readiness Tests
/// Item 24: pro.rs stub removal (TolariaBridge, TeamMemoryVault, AuditExport, unlock_advanced_agents)
/// Item 30: Thin domain capability stripping (AgentRegistry::public_agents, capability_map)

#[cfg(test)]
mod test_sprint5_hardening {
    use phantom_core::document_context::DocumentContext;
    use phantom_core::plugin::{AgentRegistry, DomainCapability};
    use phantom_core::pro::{
        unlock_advanced_agents, AuditExport, KairoPro, TeamMemoryVault, TolariaBridge,
        AUDIT_EXPORT_ERR, TEAM_MEMORY_VAULT_ERR,
    };
    use std::sync::Arc;

    fn make_doc_ctx() -> DocumentContext {
        DocumentContext::from_plain_text("test", "", "")
    }

    // ── Item 24: pro.rs stub removal ──────────────────────────────

    #[test]
    fn test_inject_guidelines_returns_err_when_not_pro() {
        // KairoPro without a license file = not pro
        let pro = KairoPro::new();
        let mut prompt = "Hello".to_string();
        let result = TolariaBridge::inject_guidelines(&pro, &mut prompt);
        assert!(result.is_err(), "inject_guidelines must Err when not Pro");
        let msg = result.unwrap_err();
        assert!(
            msg.contains("unavailable") || msg.contains("Kairo Pro"),
            "Error must mention unavailability: got '{msg}'"
        );
        // Prompt must remain unmodified
        assert_eq!(prompt, "Hello");
    }

    #[test]
    fn test_unlock_advanced_agents_returns_err_when_not_pro() {
        let pro = KairoPro::new();
        let result = unlock_advanced_agents(&pro);
        assert!(
            result.is_err(),
            "unlock_advanced_agents must Err when not Pro"
        );
        let msg = result.unwrap_err();
        assert!(
            msg.contains("unavailable") || msg.contains("Kairo Pro"),
            "Error must mention unavailability: got '{msg}'"
        );
    }

    #[tokio::test]
    async fn test_team_memory_vault_sync_error_message_is_descriptive() {
        let pro = KairoPro::new();
        let result = TeamMemoryVault::sync_to_s3(&pro).await;
        assert!(result.is_err(), "sync_to_s3 must Err when not Pro");
        let msg = result.unwrap_err().to_string();
        assert_eq!(msg, TEAM_MEMORY_VAULT_ERR);
    }

    #[test]
    fn test_audit_export_error_message_is_descriptive() {
        let result = AuditExport::export_csv(
            &KairoPro::new(),
            "user",
            "app",
            "agent",
            "hash",
            "outcome",
            100,
        );
        assert!(result.is_err());
        let msg = result.unwrap_err().to_string();
        assert_eq!(msg, AUDIT_EXPORT_ERR);
    }

    // ── Item 30: Thin domain capability stripping ──────────────────

    fn make_real_agent(id: &str) -> Arc<dyn phantom_core::plugin::SwarmAgent> {
        // DynamicAgent defaults to PromptOnly in capability() trait default.
        // We wrap in a custom struct instead.
        struct RealAgent {
            id_str: String,
        }
        impl phantom_core::plugin::SwarmAgent for RealAgent {
            fn id(&self) -> &str {
                &self.id_str
            }
            fn name(&self) -> &str {
                "Real Agent"
            }
            fn build_system_prompt(&self, _: &DocumentContext) -> String {
                String::new()
            }
            fn match_score(&self, _: &DocumentContext) -> u8 {
                50
            }
            fn capability(&self) -> DomainCapability {
                DomainCapability::Real
            }
        }
        Arc::new(RealAgent {
            id_str: id.to_string(),
        })
    }

    fn make_prompt_only_agent(id: &str) -> Arc<dyn phantom_core::plugin::SwarmAgent> {
        struct ThinAgent {
            id_str: String,
        }
        impl phantom_core::plugin::SwarmAgent for ThinAgent {
            fn id(&self) -> &str {
                &self.id_str
            }
            fn name(&self) -> &str {
                "Thin Agent"
            }
            fn build_system_prompt(&self, _: &DocumentContext) -> String {
                String::new()
            }
            fn match_score(&self, _: &DocumentContext) -> u8 {
                10
            }
            fn capability(&self) -> DomainCapability {
                DomainCapability::PromptOnly
            }
        }
        Arc::new(ThinAgent {
            id_str: id.to_string(),
        })
    }

    #[test]
    fn test_public_agents_strips_prompt_only() {
        let mut registry = AgentRegistry::new();
        registry.register(make_real_agent("word-agent"));
        registry.register(make_real_agent("excel-agent"));
        registry.register(make_prompt_only_agent("medical-thin"));
        registry.register(make_prompt_only_agent("sales-thin"));

        let all = registry.list_agents();
        let public = registry.public_agents();

        assert_eq!(all.len(), 4, "All 4 agents should be registered");
        assert_eq!(
            public.len(),
            2,
            "Only 2 Real agents should appear in public list"
        );
        for agent in &public {
            assert_eq!(
                agent.capability(),
                DomainCapability::Real,
                "public_agents() must only return Real capability agents"
            );
        }
    }

    #[test]
    fn test_capability_map_includes_all_with_correct_capabilities() {
        let mut registry = AgentRegistry::new();
        registry.register(make_real_agent("word-agent"));
        registry.register(make_prompt_only_agent("medical-thin"));

        let cap_map = registry.capability_map();
        assert_eq!(cap_map.len(), 2);

        let word_cap = cap_map
            .iter()
            .find(|(id, _)| id == "word-agent")
            .map(|(_, c)| c);
        let med_cap = cap_map
            .iter()
            .find(|(id, _)| id == "medical-thin")
            .map(|(_, c)| c);

        assert_eq!(*word_cap.unwrap(), DomainCapability::Real);
        assert_eq!(*med_cap.unwrap(), DomainCapability::PromptOnly);
    }

    #[test]
    fn test_empty_registry_returns_empty_public_agents() {
        let registry = AgentRegistry::new();
        assert!(registry.public_agents().is_empty());
        assert!(registry.capability_map().is_empty());
    }

    #[tokio::test]
    async fn test_api_get_capabilities() {
        use axum::extract::State;
        use phantom_core::api::{get_capabilities, ApiState};
        use phantom_core::context::ContextEngine;
        use phantom_core::crdt::CrdtSession;
        use phantom_core::document_context::ExtractorRegistry;
        use phantom_core::injector::HumanizedInjector;
        use phantom_core::swarm::{SwarmOrchestrator, TestFallbackBackend};
        use phantom_core::uia::UiaReader;

        let swarm_engine = Arc::new(SwarmOrchestrator::new_for_test());
        let state = ApiState {
            crdt: Arc::new(CrdtSession::new(999)),
            uia: Arc::new(UiaReader::new()),
            injector: Arc::new(HumanizedInjector::new(0)),
            ai: Arc::new(TestFallbackBackend),
            context_engine: Arc::new(ContextEngine::new()),
            extractor_registry: Arc::new(ExtractorRegistry::with_defaults()),
            swarm_engine,
            mcp_agent_override: Arc::new(std::sync::Mutex::new(None)),
        };

        let result = get_capabilities(State(state)).await;
        let list = result.0;

        // Assert that the public agents are returned.
        assert!(!list.is_empty(), "Capabilities list should not be empty");
        for cap in list {
            assert_eq!(
                cap.capability,
                phantom_core::plugin::DomainCapability::Real,
                "Should only return Real capability agents"
            );
        }
    }
}
