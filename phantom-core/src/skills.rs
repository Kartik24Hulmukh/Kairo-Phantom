// phantom-core/src/skills.rs
// Waza-inspired Skill Architecture — per kairo-intel.md §3.1
// All 8 skills are loaded at compile time via include_str!

use crate::command_protocol::CommandMode;
use std::collections::HashMap;

pub struct SkillManager {
    skills: HashMap<CommandMode, String>,
}

impl SkillManager {
    pub fn new() -> Self {
        let mut skills = HashMap::new();

        // All 8 Waza-inspired skills — per kairo-intel.md §3.2
        skills.insert(
            CommandMode::Think,
            include_str!("./skills/think/SKILL.md").to_string(),
        );
        skills.insert(
            CommandMode::Design,
            include_str!("./skills/design/SKILL.md").to_string(),
        );
        skills.insert(
            CommandMode::Check,
            include_str!("./skills/check/SKILL.md").to_string(),
        );
        skills.insert(
            CommandMode::Write,
            include_str!("./skills/write/SKILL.md").to_string(),
        );
        skills.insert(
            CommandMode::Learn,
            include_str!("./skills/learn/SKILL.md").to_string(),
        );
        skills.insert(
            CommandMode::Read,
            include_str!("./skills/read/SKILL.md").to_string(),
        );
        skills.insert(
            CommandMode::Health,
            include_str!("./skills/health/SKILL.md").to_string(),
        );
        skills.insert(
            CommandMode::Kami,
            include_str!("./skills/kami/SKILL.md").to_string(),
        );

        Self { skills }
    }

    /// Get the Waza skill directive for a given command mode.
    /// Returns None for modes without a skill file (e.g. GhostWrite, Urgent, Query).
    pub fn get_skill_directive(&self, mode: &CommandMode) -> Option<String> {
        self.skills.get(mode).cloned()
    }

    /// Return a summary of all loaded skills for health reporting.
    pub fn skill_summary(&self) -> Vec<String> {
        self.skills
            .keys()
            .map(|mode| format!("  · {mode:?} — SKILL.md loaded"))
            .collect()
    }

    /// Return count of loaded skills.
    pub fn count(&self) -> usize {
        self.skills.len()
    }
}

impl Default for SkillManager {
    fn default() -> Self {
        Self::new()
    }
}
pub mod design_agent;
pub mod ppt_agent;
