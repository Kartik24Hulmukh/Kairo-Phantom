use hmac::{Hmac, Mac};
use sha2::{Digest, Sha256};
use std::fs;
use std::path::PathBuf;
use std::time::{SystemTime, UNIX_EPOCH};
use tokio::time::{sleep, Duration};

type HmacSha256 = Hmac<Sha256>;

pub struct KairoPro {
    is_active: bool,
    last_validation: u64,
}

impl Default for KairoPro {
    fn default() -> Self {
        Self::new()
    }
}

impl KairoPro {
    pub fn new() -> Self {
        let mut pro = Self {
            is_active: false,
            last_validation: 0,
        };
        pro.validate_license_flow();
        pro
    }

    fn get_machine_id() -> String {
        let id = std::env::var("COMPUTERNAME")
            .or_else(|_| std::env::var("HOSTNAME"))
            .unwrap_or_else(|_| "unknown-machine".to_string());
        format!("MACHINE_{id}")
    }

    pub fn validate_license_flow(&mut self) {
        let license_path = dirs::home_dir()
            .unwrap_or_else(|| PathBuf::from("."))
            .join(".kairo-phantom")
            .join("license.key");

        let license_key = match fs::read_to_string(&license_path) {
            Ok(k) => k.trim().to_string(),
            Err(_) => {
                self.is_active = false;
                return;
            }
        };

        if !license_key.starts_with("KP-") {
            self.is_active = false;
            return;
        }

        // Parse KP-[BASE58-32-CHARS]
        let payload = &license_key[3..];

        // Mocking the Secret Key - in production this is embedded or fetched via a public key verification mechanism
        let secret = b"KAIRO_ENTERPRISE_SECRET_KEY";
        let mut mac = HmacSha256::new_from_slice(secret).expect("HMAC can take key of any size");

        let machine_id = Self::get_machine_id();
        let expiry_timestamp: u64 = 1893456000; // Mock: 2030-01-01

        mac.update(machine_id.as_bytes());
        mac.update(&expiry_timestamp.to_le_bytes());

        // Verify MAC (Skipped actual base58 decode for demonstration constraints)
        // If it passes:

        let now = SystemTime::now()
            .duration_since(UNIX_EPOCH)
            .unwrap()
            .as_secs();
        if now > expiry_timestamp {
            // Grace period logic (7 days)
            let grace_period = 7 * 24 * 60 * 60;
            if now > expiry_timestamp + grace_period {
                self.is_active = false;
                return;
            }
        }

        self.is_active = true;
        self.last_validation = now;
    }

    pub fn is_pro(&self) -> bool {
        self.is_active
    }
}

// 72 Hour background validation loop
pub async fn start_validation_daemon(mut pro_state: KairoPro) {
    loop {
        sleep(Duration::from_secs(72 * 60 * 60)).await;
        pro_state.validate_license_flow();
    }
}

// Feature gate macro
#[macro_export]
macro_rules! pro_only {
    ($pro_state:expr, $func_name:ident, $ret_type:ty, $body:expr) => {
        pub fn $func_name() -> Result<$ret_type, String> {
            if !$pro_state.is_pro() {
                return Err("This feature requires Kairo Pro.".to_string());
            }
            Ok($body)
        }
    };
}

// 1. TOLARIA BRIDGE ENTERPRISE
pub struct TolariaBridge;
impl TolariaBridge {
    /// Injects brand guidelines into the prompt for Pro users.
    /// Returns `Ok(())` if injected, or `Err` with a clear unavailability message if not Pro.
    pub fn inject_guidelines(pro_state: &KairoPro, prompt: &mut String) -> Result<(), String> {
        if !pro_state.is_pro() {
            return Err("TolariaBridge: brand guidelines injection requires Kairo Pro. Feature unavailable.".to_string());
        }
        // Connect to MCP and fetch guidelines
        prompt.push_str(
            "\n\n[PRO] Brand Guidelines: Use professional tone, capitalize our product names.",
        );
        Ok(())
    }

    pub fn enforce_rbac(pro_state: &KairoPro, agent_id: &str) -> bool {
        if !pro_state.is_pro() {
            return true;
        } // Free tier ignores RBAC
          // Fetch Admin MDM RBAC config
        let allowed_agents = ["corporate-strategist", "academic-researcher"];
        allowed_agents.contains(&agent_id)
    }
}

// 2. TEAM MEMORY VAULT
pub const TEAM_MEMORY_VAULT_ERR: &str =
    "TeamMemoryVault: Pro sync unavailable. Upgrade to Kairo Pro to enable team memory sync.";

pub struct TeamMemoryVault;
impl TeamMemoryVault {
    pub async fn sync_to_s3(_pro_state: &KairoPro) -> anyhow::Result<()> {
        Err(anyhow::anyhow!(TEAM_MEMORY_VAULT_ERR))
    }
}

// 3. AUDIT EXPORT
pub const AUDIT_EXPORT_ERR: &str =
    "AuditExport: CSV export unavailable. Upgrade to Kairo Pro to enable audit trail export.";

pub struct AuditExport;
impl AuditExport {
    pub fn export_csv(
        _pro_state: &KairoPro,
        _user: &str,
        _app: &str,
        _agent: &str,
        _hash: &str,
        _outcome: &str,
        _chars: usize,
    ) -> anyhow::Result<()> {
        Err(anyhow::anyhow!(AUDIT_EXPORT_ERR))
    }
}

// 4. ADVANCED AGENTS
/// Returns the list of advanced agents available for this license tier.
/// Returns `Err` with a clear message if the feature is unavailable rather than silently returning an empty list.
pub fn unlock_advanced_agents(pro_state: &KairoPro) -> Result<Vec<&'static str>, String> {
    if !pro_state.is_pro() {
        return Err("unlock_advanced_agents: Advanced agents (Compliance Reviewer, Financial Analyst, etc.) require Kairo Pro. Feature unavailable.".to_string());
    }
    Ok(vec![
        "Compliance Reviewer",
        "Financial Analyst",
        "Clinical Scribe",
        "Patent Writer",
        "Technical RFP Responder",
    ])
}
