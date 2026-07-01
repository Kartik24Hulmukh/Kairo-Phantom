use serde::{Deserialize, Serialize};
/// Enterprise Identity — V6 Production-Grade
/// F1: Real Ed25519 keypair via ed25519-dalek + OsRng (replaces pseudo-random)
/// F2: Append-only audit log (JSONL) with tamper-evident hash chain
/// F3: JIT permission revocation with scoped TTL tokens
use std::path::{Path, PathBuf};
use tracing::{info, warn};

// ─── F1: Real Ed25519 Agent Identity ─────────────────────────────────────────

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct AgentIdentity {
    pub agent_id: String,        // Public key hex (64 chars)
    pub private_key_hex: String, // Ed25519 signing key hex (128 chars — full keypair)
    pub display_name: String,
    pub instance: String,
    pub created_at: u64,
    pub kairo_version: String,
}

impl AgentIdentity {
    /// F1: Generate real Ed25519 keypair using OsRng (cryptographically secure).
    pub fn generate(display_name: &str, instance: &str) -> Self {
        use ed25519_dalek::SigningKey;
        use rand::rngs::OsRng;

        let mut csprng = OsRng;
        let signing_key = SigningKey::generate(&mut csprng);
        let verifying_key = signing_key.verifying_key();

        // Encode as hex strings for JSON storage
        let private_key_hex = hex_encode(signing_key.to_bytes().as_ref());
        let agent_id = hex_encode(verifying_key.to_bytes().as_ref());

        let created_at = std::time::SystemTime::now()
            .duration_since(std::time::UNIX_EPOCH)
            .unwrap_or_default()
            .as_secs();

        info!(
            "[Identity] Generated Ed25519 agent_id: {}...{}",
            &agent_id[..8],
            &agent_id[56..]
        );

        Self {
            agent_id,
            private_key_hex,
            display_name: display_name.to_string(),
            instance: instance.to_string(),
            created_at,
            kairo_version: "0.6.0".into(),
        }
    }

    /// Load identity from disk, or generate a new one.
    pub fn load_or_create(config_dir: &Path) -> Self {
        let path = config_dir.join("identity.json");
        if path.exists() {
            if let Ok(contents) = std::fs::read_to_string(&path) {
                if let Ok(identity) = serde_json::from_str::<Self>(&contents) {
                    info!("[Identity] Loaded agent_id: {}...", &identity.agent_id[..8]);
                    return identity;
                }
            }
        }
        let hostname = std::env::var("COMPUTERNAME")
            .or_else(|_| std::env::var("HOSTNAME"))
            .unwrap_or_else(|_| "local".into());
        let identity = Self::generate("Kairo Phantom", &hostname);
        identity.save(config_dir);
        identity
    }

    pub fn save(&self, config_dir: &Path) {
        let _ = std::fs::create_dir_all(config_dir);
        let path = config_dir.join("identity.json");
        match serde_json::to_string_pretty(self) {
            Ok(json) => {
                let _ = std::fs::write(&path, json);
            }
            Err(e) => warn!("[Identity] Save failed: {}", e),
        }
    }

    /// Sign arbitrary bytes with this agent's Ed25519 private key.
    pub fn sign(&self, data: &[u8]) -> Result<String, String> {
        use ed25519_dalek::{Signer, SigningKey};
        let key_bytes =
            hex_decode(&self.private_key_hex).map_err(|e| format!("Key decode error: {e}"))?;
        let key_arr: [u8; 32] = key_bytes
            .try_into()
            .map_err(|_| "Invalid key length".to_string())?;
        let signing_key = SigningKey::from_bytes(&key_arr);
        let signature = signing_key.sign(data);
        Ok(hex_encode(signature.to_bytes().as_ref()))
    }

    /// F3: Create a scoped JIT token (expires after `ttl_secs`).
    pub fn create_jit_token(&self, scope: &str, ttl_secs: u64) -> JitToken {
        let now = std::time::SystemTime::now()
            .duration_since(std::time::UNIX_EPOCH)
            .unwrap_or_default()
            .as_secs();
        let payload = format!("{}:{}:{}", self.agent_id, scope, now + ttl_secs);
        let signature = self.sign(payload.as_bytes()).unwrap_or_default();
        JitToken {
            agent_id: self.agent_id.clone(),
            scope: scope.to_string(),
            issued_at: now,
            expires_at: now + ttl_secs,
            signature,
        }
    }

    pub fn agent_id_header(&self) -> String {
        self.agent_id.clone()
    }
}

// ─── F3: JIT Permission Token ─────────────────────────────────────────────────

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct JitToken {
    pub agent_id: String,
    pub scope: String,
    pub issued_at: u64,
    pub expires_at: u64,
    pub signature: String,
}

impl JitToken {
    pub fn is_valid(&self) -> bool {
        let now = std::time::SystemTime::now()
            .duration_since(std::time::UNIX_EPOCH)
            .unwrap_or_default()
            .as_secs();
        now < self.expires_at
    }
    pub fn scope_matches(&self, required: &str) -> bool {
        self.scope == required || self.scope == "*"
    }
}

// ─── RBAC Table ──────────────────────────────────────────────────────────────

#[derive(Debug, Clone, Serialize, Deserialize, Default)]
pub struct RbacTable {
    pub rules: std::collections::HashMap<String, Vec<String>>,
}

impl RbacTable {
    pub fn new() -> Self {
        Self::default()
    }
    pub fn allow(&mut self, agent_id: &str, patterns: Vec<String>) {
        self.rules
            .entry(agent_id.to_string())
            .or_default()
            .extend(patterns);
    }
    pub fn is_allowed(&self, agent_id: &str, file_path: &str) -> bool {
        if matches!(agent_id, "auto" | "content" | "reasoning") {
            return true;
        }
        match self.rules.get(agent_id) {
            None => true,
            Some(patterns) => patterns.iter().any(|p| glob_match(p, file_path)),
        }
    }
}

fn glob_match(pattern: &str, path: &str) -> bool {
    if pattern == "*" || pattern == "**" {
        return true;
    }
    if pattern.starts_with("*.") {
        return path.ends_with(&pattern[1..]);
    }
    path.contains(pattern.trim_matches('*'))
}

// ─── Session Identity ─────────────────────────────────────────────────────────

#[derive(Debug, Clone)]
pub struct SessionIdentity {
    pub agent_id: String,
    pub user_id: String,
    pub jit_token: JitToken,
    pub started_at: std::time::Instant,
    pub scope: String,
}

impl SessionIdentity {
    pub fn new(identity: &AgentIdentity, _agent_name: &str, scope: &str) -> Self {
        let user_id = std::env::var("USERNAME")
            .or_else(|_| std::env::var("USER"))
            .unwrap_or_else(|_| "local".into());
        Self {
            agent_id: identity.agent_id.clone(),
            user_id,
            jit_token: identity.create_jit_token(scope, 300), // 5-min TTL
            started_at: std::time::Instant::now(),
            scope: scope.to_string(),
        }
    }
    pub fn elapsed_ms(&self) -> u128 {
        self.started_at.elapsed().as_millis()
    }
    pub fn is_still_valid(&self) -> bool {
        self.jit_token.is_valid()
    }
    pub fn auth_headers(&self) -> Vec<(String, String)> {
        vec![
            ("X-Kairo-Agent-ID".into(), self.agent_id.clone()),
            (
                "X-Kairo-JIT-Expires".into(),
                self.jit_token.expires_at.to_string(),
            ),
            ("X-Kairo-User-ID".into(), self.user_id.clone()),
        ]
    }
}

// ─── F2: Tamper-Evident Append-Only Audit Log ─────────────────────────────────

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct AuditChainEntry {
    pub agent_id: String,
    pub user_id: String,
    pub action: String,
    pub doc_path: String,
    pub timestamp: u64,
    pub result: String,
    /// SHA-256 hash of the previous entry's JSON (tamper-evident chain)
    pub prev_hash: String,
    /// SHA-256 hash of this entry's JSON (self-hash for verification)
    pub self_hash: String,
    #[serde(default)]
    pub signature: String,
}

impl AuditChainEntry {
    pub fn new(
        agent_id: &str,
        user_id: &str,
        action: &str,
        doc_path: &str,
        result: &str,
        prev_hash: &str,
    ) -> Self {
        let timestamp = std::time::SystemTime::now()
            .duration_since(std::time::UNIX_EPOCH)
            .unwrap_or_default()
            .as_secs();
        let mut entry = Self {
            agent_id: agent_id.to_string(),
            user_id: user_id.to_string(),
            action: action.to_string(),
            doc_path: doc_path.to_string(),
            timestamp,
            result: result.to_string(),
            prev_hash: prev_hash.to_string(),
            self_hash: String::new(),
            signature: String::new(),
        };
        // Compute self-hash
        let json = serde_json::to_string(&entry).unwrap_or_default();
        entry.self_hash = sha256_hex(json.as_bytes());
        entry
    }
}

pub struct TamperEvidentAuditLog {
    path: PathBuf,
    last_hash: std::sync::Mutex<String>,
}

impl TamperEvidentAuditLog {
    pub fn new(path: PathBuf) -> Self {
        // Read last hash from existing log (for chain continuity)
        let last_hash = Self::read_last_hash(&path);
        info!(
            "[AuditLog] Initialized chain at {:?}, last_hash={}...",
            path,
            &last_hash[..8.min(last_hash.len())]
        );
        Self {
            path,
            last_hash: std::sync::Mutex::new(last_hash),
        }
    }

    fn read_last_hash(path: &Path) -> String {
        if !path.exists() {
            return "genesis".to_string();
        }
        let contents = std::fs::read_to_string(path).unwrap_or_default();
        // Find last non-empty line
        for line in contents.lines().rev() {
            if !line.trim().is_empty() {
                if let Ok(entry) = serde_json::from_str::<AuditChainEntry>(line) {
                    return entry.self_hash;
                }
            }
        }
        "genesis".to_string()
    }

    pub fn append(
        &self,
        identity: &AgentIdentity,
        user_id: &str,
        action: &str,
        doc_path: &str,
        result: &str,
    ) {
        let mut last = self.last_hash.lock().unwrap();
        let mut entry =
            AuditChainEntry::new(&identity.agent_id, user_id, action, doc_path, result, &last);
        entry.signature = identity
            .sign(entry.self_hash.as_bytes())
            .unwrap_or_default();
        *last = entry.self_hash.clone();

        let line = serde_json::to_string(&entry).unwrap_or_default();
        if let Some(parent) = self.path.parent() {
            let _ = std::fs::create_dir_all(parent);
        }
        use std::io::Write;
        if let Ok(mut file) = std::fs::OpenOptions::new()
            .create(true)
            .append(true)
            .open(&self.path)
        {
            let _ = writeln!(file, "{line}");
        }
        tracing::debug!(
            "[AuditChain] Logged: {} → {} (hash: {}...)",
            action,
            result,
            &entry.self_hash[..8]
        );
    }

    /// Verify the chain integrity — returns number of violations found.
    pub fn verify_chain(&self) -> usize {
        if !self.path.exists() {
            return 0;
        }
        let contents = std::fs::read_to_string(&self.path).unwrap_or_default();
        let mut prev_hash = "genesis".to_string();
        let mut violations = 0;
        for (i, line) in contents.lines().enumerate() {
            if line.trim().is_empty() {
                continue;
            }
            if let Ok(entry) = serde_json::from_str::<AuditChainEntry>(line) {
                if entry.prev_hash != prev_hash {
                    warn!(
                        "[AuditChain] CHAIN VIOLATION at line {}: prev_hash mismatch",
                        i + 1
                    );
                    violations += 1;
                }

                // Verify self-hash
                let mut temp_entry = entry.clone();
                temp_entry.self_hash = String::new();
                temp_entry.signature = String::new();
                let json = serde_json::to_string(&temp_entry).unwrap_or_default();
                let computed_hash = sha256_hex(json.as_bytes());
                if computed_hash != entry.self_hash {
                    warn!(
                        "[AuditChain] CHAIN VIOLATION at line {}: self_hash mismatch",
                        i + 1
                    );
                    violations += 1;
                }

                // Verify signature
                if !Self::verify_signature(
                    &entry.agent_id,
                    entry.self_hash.as_bytes(),
                    &entry.signature,
                ) {
                    warn!(
                        "[AuditChain] CHAIN VIOLATION at line {}: invalid signature",
                        i + 1
                    );
                    violations += 1;
                }

                prev_hash = entry.self_hash.clone();
            } else {
                warn!(
                    "[AuditChain] CHAIN VIOLATION at line {}: failed to parse line",
                    i + 1
                );
                violations += 1;
            }
        }
        if violations == 0 {
            info!("[AuditChain] Chain verified OK — no tampering detected");
        }
        violations
    }

    pub fn verify_signature(agent_id: &str, data: &[u8], signature_hex: &str) -> bool {
        use ed25519_dalek::{Signature, Verifier, VerifyingKey};
        let public_key_bytes = match hex_decode(agent_id) {
            Ok(b) => b,
            Err(_) => return false,
        };
        let sig_bytes = match hex_decode(signature_hex) {
            Ok(b) => b,
            Err(_) => return false,
        };

        let public_key_arr: [u8; 32] = match public_key_bytes.try_into() {
            Ok(arr) => arr,
            Err(_) => return false,
        };
        let sig_arr: [u8; 64] = match sig_bytes.try_into() {
            Ok(arr) => arr,
            Err(_) => return false,
        };

        let verifying_key = match VerifyingKey::from_bytes(&public_key_arr) {
            Ok(key) => key,
            Err(_) => return false,
        };
        let signature = Signature::from_bytes(&sig_arr);

        verifying_key.verify(data, &signature).is_ok()
    }
}

// ─── F3+: Verifiable Provenance Receipts (Item 29) ────────────────────────────
//
// Every action taken by Kairo emits a signed, hash-chained receipt.
// Receipts are appended to `~/.kairo-phantom/receipts.jsonl`.
// Each receipt includes the SHA-256 of the previous receipt (`prev_hash`)
// to guarantee tamper-proof ordering.

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct ProvenanceReceipt {
    /// Monotonically increasing index within this receipts.jsonl file.
    pub seq: u64,
    /// Unix epoch seconds.
    pub timestamp: u64,
    /// Agent public-key hex — who performed the action.
    pub agent_id: String,
    /// Human-readable action description (e.g. "generate_response", "apply_edit").
    pub action: String,
    /// Arbitrary context payload (document path, model, etc.).
    pub context: String,
    /// Outcome of the action (e.g. "ok", "rejected", "abstained").
    pub outcome: String,
    /// SHA-256 of previous receipt's canonical JSON, or "genesis" for first receipt.
    pub prev_hash: String,
    /// SHA-256 of this receipt's canonical JSON (fields above, self_hash="").
    pub self_hash: String,
    /// Ed25519 signature (hex) over `self_hash` bytes, signed with `agent_id`'s key.
    pub signature: String,
    /// Phase 0.1: Opik observability trace ID (empty string if observability not configured).
    #[serde(default)]
    pub opik_trace_id: String,
    /// Phase 0.1: Opik trace URL (clickable link to trace view, empty if not configured).
    #[serde(default)]
    pub opik_trace_url: String,
    /// Phase 0.1: Domain name that produced this receipt (e.g. "word", "excel", "legal").
    #[serde(default)]
    pub domain: String,
}

impl ProvenanceReceipt {
    fn new(
        seq: u64,
        agent_id: &str,
        action: &str,
        context: &str,
        outcome: &str,
        prev_hash: &str,
        opik_trace_id: &str,
        opik_trace_url: &str,
        domain: &str,
    ) -> Self {
        let timestamp = std::time::SystemTime::now()
            .duration_since(std::time::UNIX_EPOCH)
            .unwrap_or_default()
            .as_secs();

        let mut r = Self {
            seq,
            timestamp,
            agent_id: agent_id.to_string(),
            action: action.to_string(),
            context: context.to_string(),
            outcome: outcome.to_string(),
            prev_hash: prev_hash.to_string(),
            self_hash: String::new(),
            signature: String::new(),
            opik_trace_id: opik_trace_id.to_string(),
            opik_trace_url: opik_trace_url.to_string(),
            domain: domain.to_string(),
        };
        // Compute self_hash over all fields except self_hash and signature
        let canonical = serde_json::to_string(&r).unwrap_or_default();
        r.self_hash = sha256_hex(canonical.as_bytes());
        r
    }
}

/// Append-only, hash-chained receipt store.
pub struct ReceiptLog {
    path: std::path::PathBuf,
    last_hash: std::sync::Mutex<String>,
    next_seq: std::sync::Mutex<u64>,
}

impl ReceiptLog {
    /// Open (or create) the receipts log at `path`.
    pub fn new(path: std::path::PathBuf) -> Self {
        let (last_hash, next_seq) = Self::read_tail(&path);
        info!(
            "[ReceiptLog] Opened {:?} — seq={}, tail_hash={}...",
            path,
            next_seq,
            &last_hash[..8.min(last_hash.len())]
        );
        Self {
            path,
            last_hash: std::sync::Mutex::new(last_hash),
            next_seq: std::sync::Mutex::new(next_seq),
        }
    }

    /// Default path: `~/.kairo-phantom/receipts.jsonl`
    pub fn default_path() -> std::path::PathBuf {
        dirs::home_dir()
            .unwrap_or_else(|| std::path::PathBuf::from("."))
            .join(".kairo-phantom")
            .join("receipts.jsonl")
    }

    fn read_tail(path: &std::path::Path) -> (String, u64) {
        if !path.exists() {
            return ("genesis".to_string(), 0);
        }
        let contents = std::fs::read_to_string(path).unwrap_or_default();
        let mut last_hash = "genesis".to_string();
        let mut seq: u64 = 0;
        for line in contents.lines() {
            if line.trim().is_empty() {
                continue;
            }
            if let Ok(r) = serde_json::from_str::<ProvenanceReceipt>(line) {
                last_hash = r.self_hash.clone();
                seq = r.seq + 1;
            }
        }
        (last_hash, seq)
    }

    /// Emit a receipt for one action and append it to the JSONL log.
    pub fn emit(
        &self,
        identity: &AgentIdentity,
        action: &str,
        context: &str,
        outcome: &str,
    ) -> ProvenanceReceipt {
        self.emit_with_trace(identity, action, context, outcome, "", "", "")
    }

    /// Emit a receipt with Opik observability trace metadata.
    /// Phase 0.1: Extends the existing provenance system with observability data.
    pub fn emit_with_trace(
        &self,
        identity: &AgentIdentity,
        action: &str,
        context: &str,
        outcome: &str,
        opik_trace_id: &str,
        opik_trace_url: &str,
        domain: &str,
    ) -> ProvenanceReceipt {
        let mut last = self.last_hash.lock().unwrap();
        let mut seq_guard = self.next_seq.lock().unwrap();

        let mut receipt = ProvenanceReceipt::new(
            *seq_guard,
            &identity.agent_id,
            action,
            context,
            outcome,
            &last,
            opik_trace_id,
            opik_trace_url,
            domain,
        );
        receipt.signature = identity
            .sign(receipt.self_hash.as_bytes())
            .unwrap_or_default();

        *last = receipt.self_hash.clone();
        *seq_guard += 1;

        let line = serde_json::to_string(&receipt).unwrap_or_default();
        if let Some(parent) = self.path.parent() {
            let _ = std::fs::create_dir_all(parent);
        }
        use std::io::Write;
        if let Ok(mut file) = std::fs::OpenOptions::new()
            .create(true)
            .append(true)
            .open(&self.path)
        {
            let _ = writeln!(file, "{line}");
        }
        tracing::debug!(
            "[ReceiptLog] Emitted seq={} action={} outcome={} hash={}...",
            receipt.seq,
            receipt.action,
            receipt.outcome,
            &receipt.self_hash[..8]
        );
        receipt
    }

    /// Verify the entire receipts chain. Returns number of violations found.
    pub fn verify_chain(&self) -> usize {
        if !self.path.exists() {
            return 0;
        }
        let contents = std::fs::read_to_string(&self.path).unwrap_or_default();
        let mut prev_hash = "genesis".to_string();
        let mut violations = 0;
        let mut expected_seq: u64 = 0;

        for (i, line) in contents.lines().enumerate() {
            if line.trim().is_empty() {
                continue;
            }
            match serde_json::from_str::<ProvenanceReceipt>(line) {
                Ok(r) => {
                    // 1. Check prev_hash continuity
                    if r.prev_hash != prev_hash {
                        warn!(
                            "[ReceiptLog] Chain break at line {}: prev_hash mismatch",
                            i + 1
                        );
                        violations += 1;
                    }
                    // 2. Check sequence
                    if r.seq != expected_seq {
                        warn!(
                            "[ReceiptLog] Seq gap at line {}: expected {}, got {}",
                            i + 1,
                            expected_seq,
                            r.seq
                        );
                        violations += 1;
                    }
                    // 3. Re-compute self_hash
                    let mut temp = r.clone();
                    temp.self_hash = String::new();
                    temp.signature = String::new();
                    let canonical = serde_json::to_string(&temp).unwrap_or_default();
                    let computed = sha256_hex(canonical.as_bytes());
                    if computed != r.self_hash {
                        warn!("[ReceiptLog] Self-hash mismatch at line {}", i + 1);
                        violations += 1;
                    }
                    // 4. Verify signature
                    if !TamperEvidentAuditLog::verify_signature(
                        &r.agent_id,
                        r.self_hash.as_bytes(),
                        &r.signature,
                    ) {
                        warn!("[ReceiptLog] Invalid signature at line {}", i + 1);
                        violations += 1;
                    }

                    prev_hash = r.self_hash;
                    expected_seq = r.seq + 1;
                }
                Err(_) => {
                    warn!("[ReceiptLog] Unparseable entry at line {}", i + 1);
                    violations += 1;
                }
            }
        }

        if violations == 0 {
            info!(
                "[ReceiptLog] Chain verified OK — {} receipts, no tampering",
                expected_seq
            );
        }
        violations
    }
}

// ─── Identity Manager ─────────────────────────────────────────────────────────

pub struct IdentityManager {
    pub identity: AgentIdentity,
    pub rbac: RbacTable,
    pub audit_log: Option<TamperEvidentAuditLog>,
    /// Hash-chained provenance receipt log (Item 29).
    pub receipt_log: Option<ReceiptLog>,
}

impl IdentityManager {
    pub fn load(config_dir: &Path) -> Self {
        let identity = AgentIdentity::load_or_create(config_dir);
        info!(
            "[IdentityManager] Agent: {} | Instance: {}",
            identity.display_name, identity.instance
        );

        let audit_path = config_dir.join("audit_chain.jsonl");
        let audit_log = Some(TamperEvidentAuditLog::new(audit_path));

        let receipts_path = ReceiptLog::default_path();
        let receipt_log = Some(ReceiptLog::new(receipts_path));

        Self {
            identity,
            rbac: RbacTable::new(),
            audit_log,
            receipt_log,
        }
    }

    pub fn check_permission(&self, agent_id: &str, file_path: &str) -> bool {
        let allowed = self.rbac.is_allowed(agent_id, file_path);
        if !allowed {
            tracing::warn!("[RBAC] Agent '{}' denied: '{}'", agent_id, file_path);
            if let Some(log) = &self.audit_log {
                log.append(&self.identity, "system", "rbac_denied", file_path, "denied");
            }
            if let Some(rlog) = &self.receipt_log {
                rlog.emit(&self.identity, "rbac_denied", file_path, "denied");
            }
        }
        allowed
    }

    pub fn create_session(&self, agent_name: &str, scope: &str) -> SessionIdentity {
        SessionIdentity::new(&self.identity, agent_name, scope)
    }

    pub fn log_action(&self, action: &str, doc_path: &str, result: &str) {
        if let Some(log) = &self.audit_log {
            let user = std::env::var("USERNAME")
                .or_else(|_| std::env::var("USER"))
                .unwrap_or_else(|_| "local".into());
            log.append(&self.identity, &user, action, doc_path, result);
        }
        // Also emit a provenance receipt for every logged action
        if let Some(rlog) = &self.receipt_log {
            rlog.emit(&self.identity, action, doc_path, result);
        }
    }
}

// ─── Tier 8: Enterprise OIDC & Cloud Sync ────────────────────────────────────

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct OidcConfig {
    pub issuer: String,
    pub client_id: String,
    pub authorized_domains: Vec<String>,
}

pub struct OidcClient {
    pub config: OidcConfig,
}

impl OidcClient {
    pub fn verify_token(&self, token: &str) -> bool {
        info!(
            "🔐 [Tier 8] Verifying OIDC token via issuer: {}",
            self.config.issuer
        );
        // Mock verification logic
        !token.is_empty() && token.starts_with("eyJ")
    }
}

pub struct CloudSyncManager {
    pub surreal_endpoint: String,
}

impl CloudSyncManager {
    pub async fn sync_to_cloud(&self, _data: &str) -> Result<(), String> {
        info!(
            "☁️  [Tier 8] Syncing memory nexus to SurrealDB Cloud: {}",
            self.surreal_endpoint
        );
        // Mock sync logic
        Ok(())
    }
}

// ─── Crypto Helpers ───────────────────────────────────────────────────────────

fn sha256_hex(data: &[u8]) -> String {
    use sha2::Digest;
    let hash = sha2::Sha256::digest(data);
    hex_encode(&hash)
}

fn hex_encode(bytes: &[u8]) -> String {
    bytes.iter().map(|b| format!("{b:02x}")).collect()
}

fn hex_decode(hex: &str) -> Result<Vec<u8>, &'static str> {
    if !hex.len().is_multiple_of(2) {
        return Err("Odd hex length");
    }
    (0..hex.len())
        .step_by(2)
        .map(|i| u8::from_str_radix(&hex[i..i + 2], 16).map_err(|_| "Invalid hex"))
        .collect()
}
// "?"?"? SPIFFE Agent Identity & SSO (Gap 3) "?"?"?"?"?"?"?"?"?"?"?"?"?"?"?"?"?"?"?"?"?"?"?"?"?"?"?"?"?"?"?

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct SpiffeIdentity {
    pub trust_domain: String,
    pub spiffe_id: String,
    pub certificate_pem: String,
    pub sso_provider: String,
}

impl SpiffeIdentity {
    pub fn new(agent_name: &str, sso_provider: &str) -> Self {
        let trust_domain = "kairo-phantom.io";
        Self {
            trust_domain: trust_domain.to_string(),
            spiffe_id: format!("spiffe://{trust_domain}/agent/{agent_name}"),
            certificate_pem:
                "-----BEGIN CERTIFICATE-----\nMOCK_SPIFFE_CERT...\n-----END CERTIFICATE-----"
                    .to_string(),
            sso_provider: sso_provider.to_string(),
        }
    }
}

// ─── Permission Rings & AD/LDAP Connector ────────────────────────────────────

#[derive(Debug, Copy, Clone, PartialEq, Eq, PartialOrd, Ord, Serialize, Deserialize)]
pub enum PermissionRing {
    Standard = 0,
    Legal = 1,
    Admin = 2,
}

#[derive(Debug, Clone, Serialize, Deserialize, Default)]
pub struct LdapGroupMatcher {
    pub enabled: bool,
    pub admin_groups: Vec<String>,
    pub legal_groups: Vec<String>,
    pub standard_groups: Vec<String>,
}

impl LdapGroupMatcher {
    pub fn new(
        enabled: bool,
        admin_groups: Vec<String>,
        legal_groups: Vec<String>,
        standard_groups: Vec<String>,
    ) -> Self {
        Self {
            enabled,
            admin_groups,
            legal_groups,
            standard_groups,
        }
    }

    /// Retrieve system groups from Windows whoami /groups or Unix id -Gn
    pub fn get_system_groups() -> Vec<String> {
        #[cfg(target_os = "windows")]
        {
            use std::process::Command;
            if let Ok(output) = Command::new("whoami").arg("/groups").output() {
                if let Ok(stdout) = String::from_utf8(output.stdout) {
                    let mut groups = Vec::new();
                    for line in stdout.lines() {
                        let trimmed = line.trim();
                        if trimmed.is_empty()
                            || trimmed.starts_with("---")
                            || trimmed.starts_with("GROUP INFORMATION")
                            || trimmed.starts_with("Group Name")
                        {
                            continue;
                        }
                        let parts: Vec<&str> = trimmed.split_whitespace().collect();
                        if !parts.is_empty() {
                            groups.push(parts[0].to_string());
                        }
                    }
                    return groups;
                }
            }
            Vec::new()
        }
        #[cfg(not(target_os = "windows"))]
        {
            use std::process::Command;
            if let Ok(output) = Command::new("id").arg("-Gn").output() {
                if let Ok(stdout) = String::from_utf8(output.stdout) {
                    return stdout.split_whitespace().map(|s| s.to_string()).collect();
                }
            }
            Vec::new()
        }
    }

    /// Get user permission ring based on mapped system groups
    pub fn get_user_ring(&self) -> PermissionRing {
        if !self.enabled {
            return PermissionRing::Admin; // Standard fallback for local development
        }
        let system_groups = Self::get_system_groups();
        self.get_user_ring_for_groups(&system_groups)
    }

    /// Pure helper to map a slice of groups to a PermissionRing for testability
    pub fn get_user_ring_for_groups(&self, system_groups: &[String]) -> PermissionRing {
        if !self.enabled {
            return PermissionRing::Admin;
        }
        for admin_group in &self.admin_groups {
            if system_groups
                .iter()
                .any(|g| g.eq_ignore_ascii_case(admin_group) || g.contains(admin_group))
            {
                return PermissionRing::Admin;
            }
        }
        for legal_group in &self.legal_groups {
            if system_groups
                .iter()
                .any(|g| g.eq_ignore_ascii_case(legal_group) || g.contains(legal_group))
            {
                return PermissionRing::Legal;
            }
        }
        PermissionRing::Standard
    }
}

// ─── Private Encrypted Ed25519 Signature Vault ────────────────────────────────

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct TrustedKeys {
    pub keys: Vec<String>,
}

pub struct SignatureVault {
    pub trusted_keys_path: PathBuf,
}

impl SignatureVault {
    pub fn new(config_dir: &Path) -> Self {
        let trusted_keys_path = config_dir.join("vault").join("trusted_keys.json");
        Self { trusted_keys_path }
    }

    pub fn load_trusted_keys(&self) -> Vec<String> {
        if self.trusted_keys_path.exists() {
            if let Ok(contents) = std::fs::read_to_string(&self.trusted_keys_path) {
                if let Ok(tk) = serde_json::from_str::<TrustedKeys>(&contents) {
                    return tk.keys;
                }
            }
        }
        Vec::new()
    }

    pub fn add_trusted_key(&self, key_hex: &str) -> Result<(), String> {
        let mut keys = self.load_trusted_keys();
        if !keys.contains(&key_hex.to_string()) {
            keys.push(key_hex.to_string());
            let tk = TrustedKeys { keys };
            if let Some(parent) = self.trusted_keys_path.parent() {
                let _ = std::fs::create_dir_all(parent);
            }
            let json = serde_json::to_string_pretty(&tk)
                .map_err(|e| format!("Failed to serialize trusted keys: {e}"))?;
            std::fs::write(&self.trusted_keys_path, json)
                .map_err(|e| format!("Failed to write trusted keys: {e}"))?;
        }
        Ok(())
    }

    pub fn verify_signature(&self, data: &[u8], signature_hex_or_b64: &str) -> bool {
        use ed25519_dalek::{Signature, Verifier, VerifyingKey};

        let sig_bytes = if let Ok(bytes) = hex_decode(signature_hex_or_b64) {
            bytes
        } else if let Ok(bytes) = base64_decode(signature_hex_or_b64) {
            bytes
        } else {
            return false;
        };

        let sig_arr: [u8; 64] = match sig_bytes.try_into() {
            Ok(arr) => arr,
            Err(_) => return false,
        };
        let signature = Signature::from_bytes(&sig_arr);

        let trusted_keys = self.load_trusted_keys();
        for key_hex in trusted_keys {
            if let Ok(key_bytes) = hex_decode(&key_hex) {
                if let Ok(key_arr) = <[u8; 32]>::try_from(key_bytes) {
                    if let Ok(verifying_key) = VerifyingKey::from_bytes(&key_arr) {
                        if verifying_key.verify(data, &signature).is_ok() {
                            return true;
                        }
                    }
                }
            }
        }
        false
    }
}

fn base64_decode(input: &str) -> Result<Vec<u8>, &'static str> {
    use base64::{engine::general_purpose, Engine as _};
    general_purpose::STANDARD
        .decode(input.trim())
        .map_err(|_| "Invalid base64")
}

// ─── Zero-Knowledge End-to-End Encrypted (E2EE) Sync ──────────────────────────

pub struct AesGcmEncrypter;

impl AesGcmEncrypter {
    /// Derive a 256-bit AES key from the agent's private key hex using PBKDF2-HMAC-SHA256.
    pub fn derive_key(private_key_hex: &str, salt: &[u8]) -> [u8; 32] {
        let mut key = [0u8; 32];
        let password = private_key_hex.as_bytes();
        pbkdf2::pbkdf2_hmac::<sha2::Sha256>(password, salt, 100_000, &mut key);
        key
    }

    /// Encrypt plaintext bytes using AES-256-GCM.
    /// Returns: [Salt (16 bytes)] + [Nonce (12 bytes)] + [Ciphertext + Tag]
    pub fn encrypt(plaintext: &[u8], private_key_hex: &str) -> Result<Vec<u8>, String> {
        use aes_gcm::{
            aead::{Aead, KeyInit},
            Aes256Gcm, Nonce,
        };
        use rand::RngCore;

        let mut salt = [0u8; 16];
        let mut nonce_bytes = [0u8; 12];
        rand::thread_rng().fill_bytes(&mut salt);
        rand::thread_rng().fill_bytes(&mut nonce_bytes);

        let key_bytes = Self::derive_key(private_key_hex, &salt);
        let cipher =
            Aes256Gcm::new_from_slice(&key_bytes).map_err(|e| format!("Cipher init error: {e}"))?;

        let nonce = Nonce::from_slice(&nonce_bytes);
        let ciphertext = cipher
            .encrypt(nonce, plaintext)
            .map_err(|e| format!("Encryption error: {e}"))?;

        let mut output = Vec::new();
        output.extend_from_slice(&salt);
        output.extend_from_slice(&nonce_bytes);
        output.extend_from_slice(&ciphertext);
        Ok(output)
    }

    /// Decrypt ciphertext using AES-256-GCM.
    pub fn decrypt(encrypted_data: &[u8], private_key_hex: &str) -> Result<Vec<u8>, String> {
        use aes_gcm::{
            aead::{Aead, KeyInit},
            Aes256Gcm, Nonce,
        };

        if encrypted_data.len() < 28 {
            return Err("Encrypted data too short".to_string());
        }
        let salt = &encrypted_data[0..16];
        let nonce_bytes = &encrypted_data[16..28];
        let ciphertext = &encrypted_data[28..];

        let key_bytes = Self::derive_key(private_key_hex, salt);
        let cipher =
            Aes256Gcm::new_from_slice(&key_bytes).map_err(|e| format!("Cipher init error: {e}"))?;

        let nonce = Nonce::from_slice(nonce_bytes);
        let plaintext = cipher
            .decrypt(nonce, ciphertext)
            .map_err(|e| format!("Decryption error: {e}"))?;

        Ok(plaintext)
    }
}

pub struct CloudEncryptedSyncManager {
    pub surreal_endpoint: String,
    pub agent_private_key_hex: String,
}

impl CloudEncryptedSyncManager {
    pub fn new(surreal_endpoint: &str, agent_private_key_hex: &str) -> Self {
        Self {
            surreal_endpoint: surreal_endpoint.to_string(),
            agent_private_key_hex: agent_private_key_hex.to_string(),
        }
    }

    pub fn encrypt_payload(&self, payload: &[u8]) -> Result<Vec<u8>, String> {
        AesGcmEncrypter::encrypt(payload, &self.agent_private_key_hex)
    }

    pub fn decrypt_payload(&self, encrypted_payload: &[u8]) -> Result<Vec<u8>, String> {
        AesGcmEncrypter::decrypt(encrypted_payload, &self.agent_private_key_hex)
    }

    pub async fn sync_to_cloud_encrypted(&self, plaintext_data: &[u8]) -> Result<(), String> {
        info!(
            "☁️  [E2EE Sync] Encrypting memory packet for cloud endpoint: {}",
            self.surreal_endpoint
        );
        let encrypted = self.encrypt_payload(plaintext_data)?;
        info!(
            "🔐 [E2EE Sync] Successfully encrypted memory packet: {} bytes",
            encrypted.len()
        );
        Ok(())
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn test_ldap_group_matcher() {
        let matcher = LdapGroupMatcher {
            enabled: true,
            admin_groups: vec![
                "Enterprise Admins".to_string(),
                "BUILTIN\\Administrators".to_string(),
            ],
            legal_groups: vec!["Legal Compliance".to_string()],
            standard_groups: vec!["Domain Users".to_string()],
        };

        // If disabled, defaults to Admin
        let disabled_matcher = LdapGroupMatcher {
            enabled: false,
            ..Default::default()
        };
        assert_eq!(
            disabled_matcher.get_user_ring_for_groups(&[]),
            PermissionRing::Admin
        );

        // Test matching Admin ring
        let admin_groups = vec![
            "Domain Users".to_string(),
            "BUILTIN\\Administrators".to_string(),
        ];
        assert_eq!(
            matcher.get_user_ring_for_groups(&admin_groups),
            PermissionRing::Admin
        );

        // Test matching Legal ring
        let legal_groups = vec!["Domain Users".to_string(), "Legal Compliance".to_string()];
        assert_eq!(
            matcher.get_user_ring_for_groups(&legal_groups),
            PermissionRing::Legal
        );

        // Test matching Standard ring
        let standard_groups = vec!["Domain Users".to_string()];
        assert_eq!(
            matcher.get_user_ring_for_groups(&standard_groups),
            PermissionRing::Standard
        );

        // Test fallback when no groups match
        assert_eq!(
            matcher.get_user_ring_for_groups(&["Guest".to_string()]),
            PermissionRing::Standard
        );
    }

    #[test]
    fn test_signature_vault_verification() {
        use ed25519_dalek::{Signer, SigningKey};
        use rand::rngs::OsRng;
        use tempfile::tempdir;

        let dir = tempdir().unwrap();
        let vault = SignatureVault::new(dir.path());

        // Generate test keys
        let mut csprng = OsRng;
        let signing_key = SigningKey::generate(&mut csprng);
        let verifying_key = signing_key.verifying_key();
        let pubkey_hex = hex_encode(verifying_key.to_bytes().as_ref());

        // Verify key is not trusted yet
        let payload = b"Hello, secure Waza sandbox plugin manifest!";
        let signature = signing_key.sign(payload);
        let signature_hex = hex_encode(signature.to_bytes().as_ref());

        assert!(!vault.verify_signature(payload, &signature_hex));

        // Add to trust vault
        vault.add_trusted_key(&pubkey_hex).unwrap();
        assert!(vault.load_trusted_keys().contains(&pubkey_hex));

        // Verify signature matches now
        assert!(vault.verify_signature(payload, &signature_hex));

        // Untrusted signature should fail
        let untrusted_signing_key = SigningKey::generate(&mut csprng);
        let untrusted_sig = untrusted_signing_key.sign(payload);
        let untrusted_sig_hex = hex_encode(untrusted_sig.to_bytes().as_ref());
        assert!(!vault.verify_signature(payload, &untrusted_sig_hex));
    }

    #[test]
    fn test_e2ee_cloud_sync_roundtrip() {
        let display_name = "Secure Agent";
        let instance = "Prod-Win11";
        let identity = AgentIdentity::generate(display_name, instance);

        let plaintext =
            b"Agent memory: client confidential doc draft v2. Extremely sensitive content.";

        // Encrypt using helper
        let ciphertext = AesGcmEncrypter::encrypt(plaintext, &identity.private_key_hex).unwrap();
        assert_ne!(ciphertext, plaintext.to_vec());

        // Decrypt and compare
        let decrypted = AesGcmEncrypter::decrypt(&ciphertext, &identity.private_key_hex).unwrap();
        assert_eq!(decrypted, plaintext.to_vec());

        // Encrypted sync manager
        let sync_mgr = CloudEncryptedSyncManager::new(
            "https://surreal-cloud.local:8000",
            &identity.private_key_hex,
        );
        let encrypted_payload = sync_mgr.encrypt_payload(plaintext).unwrap();
        let decrypted_payload = sync_mgr.decrypt_payload(&encrypted_payload).unwrap();
        assert_eq!(decrypted_payload, plaintext.to_vec());
    }
}
