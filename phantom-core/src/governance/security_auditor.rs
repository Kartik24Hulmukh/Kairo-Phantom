use crate::governance::{AuditEvent, AuditLogger, AuditOutcome};
use crate::pii_guard::PiiGuard;
use anyhow::Result;
use tracing::{info, warn};

/// SecurityAuditor handles high-level security verification and compliance auditing.
pub struct SecurityAuditor {
    pii_guard: PiiGuard,
    audit_logger: AuditLogger,
    pub strict: bool,
}

impl SecurityAuditor {
    pub fn new(audit_logger: AuditLogger) -> Self {
        Self {
            pii_guard: PiiGuard::new(),
            audit_logger,
            strict: true,
        }
    }

    /// Performs a pre-flight security check on the context before sending it to an LLM.
    pub fn pre_flight_check(&self, text: &str, app_name: &str) -> Result<String> {
        info!(
            "🔒 SecurityAuditor: Running pre-flight check for {}",
            app_name
        );

        // 1. Redact PII
        let (redacted_text, was_redacted) = self.pii_guard.redact(text);
        if was_redacted {
            warn!("⚠️ PII detected and redacted in session for {}", app_name);
        }

        // 2. Check for sensitive keywords (Enterprise Policy)
        let sensitive_keywords = [
            "confidential",
            "trade secret",
            "internal use only",
            "proprietary",
        ];
        for keyword in sensitive_keywords {
            if redacted_text.to_lowercase().contains(keyword) {
                warn!(
                    "⚠️ Sensitive keyword '{}' detected in {}",
                    keyword, app_name
                );
                self.audit_logger.log_ghost_session(
                    AuditEvent::GhostSessionBlocked,
                    AuditOutcome::Blocked,
                    app_name,
                    "security_auditor",
                    "n/a",
                    redacted_text.len(),
                );
                if self.strict {
                    return Err(anyhow::anyhow!(
                        "Sensitive keyword '{keyword}' detected in {app_name} (Strict Block Mode)"
                    ));
                }
            }
        }

        Ok(redacted_text)
    }

    /// Final audit of the generated output before injection.
    pub fn post_flight_audit(&self, output: &str, app_name: &str) -> Result<()> {
        let findings = self.pii_guard.scan_output(output);
        if !findings.is_empty() {
            warn!(
                "⚠️ SecurityAuditor: Potential sensitive data leak in AI output for {}: {:?}",
                app_name, findings
            );
            // Log as a security warning
            self.audit_logger.log_ghost_session(
                AuditEvent::GhostSessionCompleted,
                AuditOutcome::Error {
                    message: format!("Leak detected: {findings:?}"),
                },
                app_name,
                "security_auditor",
                "n/a",
                output.len(),
            );
        }
        Ok(())
    }
}
