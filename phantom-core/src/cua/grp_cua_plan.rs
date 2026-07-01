//! GRP CUA Plan — displays the CUA action plan in the Ghost Review Panel
//!
//! Before ANY CUA action executes, the GRP shows:
//! "Kairo will:
//!  [1] Select all text in element
//!  [2] Type replacement text  
//!  [3] Verify change
//! [Tab: Execute] [Esc: Cancel]"
//!
//! NEVER auto-executes. User MUST press Tab to approve.

use super::{CuaAction, CuaPlan, TargetingSource};

/// Formats a CuaPlan for display in the GRP overlay
pub struct GrpCuaPlanDisplay;

impl GrpCuaPlanDisplay {
    /// Generate the GRP mini-plan text from a CuaPlan
    pub fn format_plan(plan: &CuaPlan) -> String {
        let mut lines = vec!["Kairo will:".to_string()];
        let mut has_low_confidence = false;
        let mut has_coordinate = false;

        for (i, step_desc) in plan.step_descriptions.iter().enumerate() {
            let confidence = plan.step_confidences.get(i).cloned().unwrap_or(1.0);
            let source = plan
                .step_sources
                .get(i)
                .cloned()
                .unwrap_or(TargetingSource::UIA);

            let icon = if confidence < 0.60 || source == TargetingSource::Coordinate {
                "[⚠]"
            } else {
                "[✓]"
            };

            if confidence < 0.60 {
                has_low_confidence = true;
            }
            if source == TargetingSource::Coordinate {
                has_coordinate = true;
            }

            lines.push(format!(
                "  {} [{}] {} ({:.0}% via {:?})",
                icon,
                i + 1,
                step_desc,
                confidence * 100.0,
                source
            ));
        }

        if has_low_confidence {
            lines.push(
                "WARNING: Plan contains low-confidence steps (<60%). Proceed with caution!"
                    .to_string(),
            );
        }
        if has_coordinate {
            lines.push(
                "WARNING: Plan contains coordinate-based targeting (accuracy <43%).".to_string(),
            );
        }

        lines.push(String::new());
        lines.push(format!(
            "Source: {:?} | Risk: {:?}",
            plan.source, plan.estimated_risk
        ));
        lines.push("[Tab: Execute] [Esc: Cancel]".to_string());

        lines.join("\n")
    }

    /// Generate a blocked action message (for forbidden windows, rate limits, etc.)
    pub fn format_blocked(reason: &str) -> String {
        format!("CUA blocked: {reason}\n[Esc: Dismiss]")
    }

    /// Check if user pressed Tab (approve) vs Esc (cancel)
    pub fn parse_user_response(key: &str) -> CuaUserResponse {
        match key {
            "Tab" | "tab" | "\t" => CuaUserResponse::Approve,
            "Escape" | "Esc" | "esc" | "\x1b" => CuaUserResponse::Cancel,
            _ => CuaUserResponse::Waiting,
        }
    }
}

/// User's response to the CUA plan display.
/// `Serialize`/`Deserialize` are needed for IPC payloads (overlay events,
/// audit log JSON, sidecar notifications).
#[derive(Debug, Clone, PartialEq, serde::Serialize, serde::Deserialize)]
pub enum CuaUserResponse {
    /// User pressed Tab — execute the plan
    Approve,
    /// User pressed Esc — cancel everything
    Cancel,
    /// Waiting for response
    Waiting,
}

#[cfg(test)]
mod tests {
    use super::*;
    use crate::cua::{CuaPlan, PlanSource, Risk};

    fn make_plan(steps: Vec<&str>) -> CuaPlan {
        CuaPlan {
            actions: vec![],
            source: PlanSource::Template,
            estimated_risk: Risk::Low,
            description: "Test plan".to_string(),
            step_descriptions: steps.into_iter().map(|s| s.to_string()).collect(),
            step_confidences: vec![],
            step_sources: vec![],
        }
    }

    #[test]
    fn test_format_plan_contains_steps() {
        let plan = make_plan(vec!["Select all text", "Type replacement"]);
        let output = GrpCuaPlanDisplay::format_plan(&plan);
        assert!(output.contains("Kairo will:"));
        assert!(output.contains("[1] Select all text"));
        assert!(output.contains("[2] Type replacement"));
        assert!(output.contains("[Tab: Execute] [Esc: Cancel]"));
    }

    #[test]
    fn test_format_plan_empty_steps() {
        let plan = make_plan(vec![]);
        let output = GrpCuaPlanDisplay::format_plan(&plan);
        assert!(output.contains("Kairo will:"));
        assert!(output.contains("[Tab: Execute] [Esc: Cancel]"));
    }

    #[test]
    fn test_format_blocked() {
        let msg = GrpCuaPlanDisplay::format_blocked("forbidden window");
        assert!(msg.contains("CUA blocked: forbidden window"));
        assert!(msg.contains("[Esc: Dismiss]"));
    }

    #[test]
    fn test_parse_user_response_approve() {
        assert_eq!(
            GrpCuaPlanDisplay::parse_user_response("Tab"),
            CuaUserResponse::Approve
        );
        assert_eq!(
            GrpCuaPlanDisplay::parse_user_response("tab"),
            CuaUserResponse::Approve
        );
        assert_eq!(
            GrpCuaPlanDisplay::parse_user_response("\t"),
            CuaUserResponse::Approve
        );
    }

    #[test]
    fn test_parse_user_response_cancel() {
        assert_eq!(
            GrpCuaPlanDisplay::parse_user_response("Escape"),
            CuaUserResponse::Cancel
        );
        assert_eq!(
            GrpCuaPlanDisplay::parse_user_response("Esc"),
            CuaUserResponse::Cancel
        );
        assert_eq!(
            GrpCuaPlanDisplay::parse_user_response("esc"),
            CuaUserResponse::Cancel
        );
        assert_eq!(
            GrpCuaPlanDisplay::parse_user_response("\x1b"),
            CuaUserResponse::Cancel
        );
    }

    #[test]
    fn test_parse_user_response_waiting() {
        assert_eq!(
            GrpCuaPlanDisplay::parse_user_response("Enter"),
            CuaUserResponse::Waiting
        );
        assert_eq!(
            GrpCuaPlanDisplay::parse_user_response("Space"),
            CuaUserResponse::Waiting
        );
        assert_eq!(
            GrpCuaPlanDisplay::parse_user_response(""),
            CuaUserResponse::Waiting
        );
    }
}
