//! LAN Memory Sync — P1.1
//! Enables teams sharing a local network to sync MemMachine brand-voice preferences.
//! Protocol: UDP broadcast for discovery, TCP for transfer.
//! Zero cloud dependency — all bytes stay on the LAN.

use anyhow::Result;
use serde::{Deserialize, Serialize};
use std::io::{Read, Write};
use std::net::{TcpListener, TcpStream, UdpSocket};
use std::path::{Path, PathBuf};
use std::time::Duration;

const DISCOVERY_PORT: u16 = 47381;
const SYNC_PORT: u16 = 47382;
const MAGIC: &[u8; 12] = b"KAIRO_LAN_v1";

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct LanPeer {
    pub addr: String,
    pub hostname: String,
    pub vault_entries: u64,
}

#[derive(Debug, Serialize, Deserialize)]
struct SyncPacket {
    magic: Vec<u8>,
    entries: Vec<SyncEntry>,
}

#[derive(Debug, Serialize, Deserialize, Clone)]
pub struct SyncEntry {
    pub id: String,
    pub content: String,
    pub app_context: String,
    pub context_key: String,
    pub tags: String,
    pub timestamp: i64,
    pub is_ground_truth: bool,
}

pub struct LanSync {
    db_path: PathBuf,
}

impl LanSync {
    pub fn new(vault_dir: &Path) -> Self {
        Self {
            db_path: vault_dir.join("mem_machine.db"),
        }
    }

    /// Broadcast presence and discover peers on the LAN.
    pub fn discover_peers(&self, timeout_ms: u64) -> Vec<LanPeer> {
        let mut peers = Vec::new();
        let sock = match UdpSocket::bind("0.0.0.0:0") {
            Ok(s) => s,
            Err(_) => return peers,
        };
        let _ = sock.set_broadcast(true);
        let _ = sock.set_read_timeout(Some(Duration::from_millis(timeout_ms)));

        // Announce ourselves
        let hostname = std::env::var("COMPUTERNAME")
            .or_else(|_| std::env::var("HOSTNAME"))
            .unwrap_or_else(|_| "kairo-node".into());
        let announce = format!("KAIRO_DISCOVER:{hostname}");
        let _ = sock.send_to(
            announce.as_bytes(),
            format!("255.255.255.255:{DISCOVERY_PORT}"),
        );

        // Listen for responses
        let mut buf = [0u8; 512];
        let deadline = std::time::Instant::now() + Duration::from_millis(timeout_ms);
        while std::time::Instant::now() < deadline {
            if let Ok((n, src)) = sock.recv_from(&mut buf) {
                let msg = String::from_utf8_lossy(&buf[..n]);
                if let Some(rest) = msg.strip_prefix("KAIRO_PEER:") {
                    let parts: Vec<&str> = rest.splitn(2, ':').collect();
                    peers.push(LanPeer {
                        addr: format!("{}:{}", src.ip(), SYNC_PORT),
                        hostname: parts.first().unwrap_or(&"unknown").to_string(),
                        vault_entries: parts.get(1).and_then(|s| s.parse().ok()).unwrap_or(0),
                    });
                }
            }
        }
        peers
    }

    /// Start a listener that responds to discovery and serves sync requests.
    pub fn start_server(&self) -> Result<()> {
        let hostname = std::env::var("COMPUTERNAME")
            .or_else(|_| std::env::var("HOSTNAME"))
            .unwrap_or_else(|_| "kairo-node".into());
        let entry_count = self.count_entries().unwrap_or(0);
        let db_path = self.db_path.clone();

        // UDP discovery responder
        let hn = hostname.clone();
        std::thread::spawn(move || {
            if let Ok(sock) = UdpSocket::bind(format!("0.0.0.0:{DISCOVERY_PORT}")) {
                let mut buf = [0u8; 512];
                loop {
                    if let Ok((n, src)) = sock.recv_from(&mut buf) {
                        let msg = String::from_utf8_lossy(&buf[..n]);
                        if msg.starts_with("KAIRO_DISCOVER:") {
                            let resp = format!("KAIRO_PEER:{hn}:{entry_count}");
                            let _ = sock.send_to(resp.as_bytes(), src);
                        }
                    }
                }
            }
        });

        // TCP sync server
        let listener = TcpListener::bind(format!("0.0.0.0:{SYNC_PORT}"))?;
        tracing::info!("🌐 LAN sync server listening on :{}", SYNC_PORT);
        for stream in listener.incoming().flatten() {
            let db = db_path.clone();
            std::thread::spawn(move || {
                let _ = handle_sync_client(stream, &db);
            });
        }
        Ok(())
    }

    /// Pull shared entries from a remote peer and merge into local DB.
    pub fn pull_from_peer(&self, peer_addr: &str) -> Result<usize> {
        let mut stream = TcpStream::connect(peer_addr)?;
        stream.set_read_timeout(Some(Duration::from_secs(30)))?;

        // Request sync
        stream.write_all(b"PULL\n")?;

        let mut data = Vec::new();
        stream.read_to_end(&mut data)?;

        if data.len() < 12 {
            return Ok(0);
        }
        let packet: SyncPacket = bincode::deserialize(&data)
            .map_err(|e| anyhow::anyhow!("Deserialization failed: {e}"))?;

        if packet.magic != MAGIC {
            return Ok(0);
        }

        let merged = self.merge_entries(&packet.entries)?;
        tracing::info!(
            "🌐 LAN sync: merged {} new entries from {}",
            merged,
            peer_addr
        );
        Ok(merged)
    }

    fn count_entries(&self) -> Result<u64> {
        if !self.db_path.exists() {
            return Ok(0);
        }
        let conn = rusqlite::Connection::open(&self.db_path)?;
        let n = conn
            .query_row("SELECT COUNT(*) FROM semantic_memory", [], |r| {
                r.get::<_, i64>(0)
            })
            .unwrap_or(0);
        Ok(n as u64)
    }

    fn export_entries(&self) -> Result<Vec<SyncEntry>> {
        if !self.db_path.exists() {
            return Ok(vec![]);
        }
        let conn = rusqlite::Connection::open(&self.db_path)?;
        let ok: bool = conn
            .query_row(
                "SELECT COUNT(*) FROM sqlite_master WHERE type='table' AND name='semantic_memory'",
                [],
                |row| row.get::<_, i64>(0),
            )
            .unwrap_or(0)
            > 0;
        if !ok {
            return Ok(vec![]);
        }
        let mut stmt = conn.prepare(
            "SELECT id, content, app_context, context_key, tags, timestamp, is_ground_truth \
             FROM semantic_memory WHERE is_ground_truth = 1 ORDER BY timestamp DESC LIMIT 500",
        )?;
        let rows = stmt.query_map([], |row| {
            Ok(SyncEntry {
                id: row.get(0)?,
                content: row.get(1)?,
                app_context: row.get(2)?,
                context_key: row.get(3)?,
                tags: row.get(4)?,
                timestamp: row.get(5)?,
                is_ground_truth: row.get::<_, i64>(6)? != 0,
            })
        })?;
        Ok(rows.filter_map(|r| r.ok()).collect())
    }

    fn merge_entries(&self, entries: &[SyncEntry]) -> Result<usize> {
        if entries.is_empty() {
            return Ok(0);
        }
        std::fs::create_dir_all(self.db_path.parent().unwrap_or(std::path::Path::new(".")))?;
        let conn = rusqlite::Connection::open(&self.db_path)?;
        conn.execute_batch(
            "CREATE TABLE IF NOT EXISTS semantic_memory (
               id TEXT PRIMARY KEY, timestamp INTEGER, content TEXT, full_episode TEXT,
               embedding BLOB, app_context TEXT, context_key TEXT,
               is_ground_truth INTEGER DEFAULT 0,
               storage_strength REAL DEFAULT 1.0, retrieval_strength REAL DEFAULT 1.0,
               tags TEXT)",
        )?;
        let mut merged = 0;
        for e in entries {
            let affected = conn.execute(
                "INSERT OR IGNORE INTO semantic_memory \
                 (id, timestamp, content, full_episode, app_context, context_key, is_ground_truth, tags) \
                 VALUES (?1, ?2, ?3, '', ?4, ?5, ?6, ?7)",
                rusqlite::params![e.id, e.timestamp, e.content, e.app_context,
                    e.context_key, if e.is_ground_truth { 1 } else { 0 }, e.tags])?;
            merged += affected;
        }
        Ok(merged)
    }
}

fn handle_sync_client(mut stream: TcpStream, db_path: &Path) -> Result<()> {
    let mut req = [0u8; 8];
    let _ = stream.read(&mut req);
    let syncer = LanSync {
        db_path: db_path.to_path_buf(),
    };
    let entries = syncer.export_entries()?;
    let packet = SyncPacket {
        magic: MAGIC.to_vec(),
        entries,
    };
    let data = bincode::serialize(&packet)?;
    stream.write_all(&data)?;
    Ok(())
}

pub async fn run_lan_sync_command(args: &[String]) -> Result<()> {
    let vault = dirs::home_dir().unwrap_or_default().join(".kairo-phantom");
    let sync = LanSync::new(&vault);

    let subcmd = args.first().map(|s| s.as_str()).unwrap_or("discover");
    match subcmd {
        "discover" => {
            println!("🔍 Discovering Kairo peers on LAN (3s)...");
            let peers = sync.discover_peers(3000);
            if peers.is_empty() {
                println!("  No peers found.");
            }
            for p in &peers {
                println!(
                    "  ✅ {} — {} ({} entries)",
                    p.hostname, p.addr, p.vault_entries
                );
            }
        }
        "pull" => {
            let peer = args.get(1).map(String::as_str).unwrap_or("");
            if peer.is_empty() {
                println!("Usage: kairo memory sync pull <ip:port>");
                return Ok(());
            }
            let n = sync.pull_from_peer(peer)?;
            println!("✅ Merged {n} new preference entries from {peer}");
        }
        "serve" => {
            println!("🌐 Starting LAN sync server on port {SYNC_PORT}...");
            sync.start_server()?;
        }
        _ => println!("Usage: kairo memory sync <discover|pull <peer>|serve>"),
    }
    Ok(())
}

#[cfg(test)]
mod tests {
    use super::*;
    use tempfile::tempdir;

    #[test]
    fn test_new_empty_vault() {
        let d = tempdir().unwrap();
        let sync = LanSync::new(d.path());
        assert_eq!(sync.count_entries().unwrap(), 0);
    }

    #[test]
    fn test_merge_empty() {
        let d = tempdir().unwrap();
        let sync = LanSync {
            db_path: d.path().join("mem_machine.db"),
        };
        let merged = sync.merge_entries(&[]).unwrap();
        assert_eq!(merged, 0);
    }

    #[test]
    fn test_merge_entries() {
        let d = tempdir().unwrap();
        let sync = LanSync {
            db_path: d.path().join("mem_machine.db"),
        };
        let entries = vec![SyncEntry {
            id: "test-id-001".into(),
            content: "Prefer bullets".into(),
            app_context: "Word".into(),
            context_key: "format".into(),
            tags: "lan,test".into(),
            timestamp: 1700000000,
            is_ground_truth: true,
        }];
        let merged = sync.merge_entries(&entries).unwrap();
        assert_eq!(merged, 1, "Should merge 1 entry");
        // Merge again — no duplicate
        let merged2 = sync.merge_entries(&entries).unwrap();
        assert_eq!(merged2, 0, "Duplicate should be ignored");
    }
}
