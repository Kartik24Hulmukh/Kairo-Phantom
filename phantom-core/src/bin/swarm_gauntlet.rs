use anyhow::Result;
use serde::{Deserialize, Serialize};
use std::process::Command;
use tokio::task::JoinSet;
use tracing::{error, info};

#[derive(Debug, Serialize, Deserialize)]
struct TestManifest {
    win: Vec<TestCase>,
    linux: Vec<TestCase>,
}

#[derive(Debug, Serialize, Deserialize)]
struct TestCase {
    id: String,
    cmd: String,
    description: String,
}

#[derive(Debug, Serialize)]
struct TestResult {
    id: String,
    passed: bool,
    output: String,
    error: Option<String>,
}

#[tokio::main]
async fn main() -> Result<()> {
    tracing_subscriber::fmt::init();
    info!("🚀 Initializing Kairo Swarm Gauntlet (Phase 8)...");

    let manifest_content = std::fs::read_to_string("test_manifest.json")?;
    let manifest: TestManifest = serde_json::from_str(&manifest_content)?;

    let mut set = JoinSet::new();

    for test in manifest.win {
        set.spawn(async move {
            info!("Running test: {}", test.id);
            let output = Command::new("cmd").args(["/c", &test.cmd]).output();

            match output {
                Ok(out) => {
                    let passed = out.status.success();
                    let stdout = String::from_utf8_lossy(&out.stdout).to_string();
                    let stderr = String::from_utf8_lossy(&out.stderr).to_string();
                    TestResult {
                        id: test.id,
                        passed,
                        output: stdout,
                        error: if !passed { Some(stderr) } else { None },
                    }
                }
                Err(e) => TestResult {
                    id: test.id,
                    passed: false,
                    output: String::new(),
                    error: Some(e.to_string()),
                },
            }
        });
    }

    let mut results = Vec::new();
    while let Some(res) = set.join_next().await {
        match res {
            Ok(result) => {
                if result.passed {
                    info!("✅ Test {} PASSED", result.id);
                } else {
                    error!("❌ Test {} FAILED", result.id);
                }
                results.push(result);
            }
            Err(e) => error!("Thread join error: {}", e),
        }
    }

    let report_json = serde_json::to_string_pretty(&results)?;
    std::fs::write("gauntlet_report.json", report_json)?;
    info!("📊 Gauntlet complete. Report saved to gauntlet_report.json");

    Ok(())
}
