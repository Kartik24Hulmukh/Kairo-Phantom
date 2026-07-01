use chrono::{DateTime, Utc};
use serde::Serialize;
use std::collections::HashMap;
use std::sync::Mutex;

#[derive(Debug, Default, Clone, Serialize)]
pub struct AgentMetrics {
    pub total_calls: u64,
    pub success_count: u64,
    pub failure_count: u64,
    pub average_latency_ms: f64,
    pub last_call: Option<DateTime<Utc>>,
}

pub struct PerformanceDashboard {
    metrics: Mutex<HashMap<String, AgentMetrics>>,
}

impl Default for PerformanceDashboard {
    fn default() -> Self {
        Self::new()
    }
}

impl PerformanceDashboard {
    pub fn new() -> Self {
        Self {
            metrics: Mutex::new(HashMap::new()),
        }
    }

    pub fn record_call(&self, agent_id: &str, latency_ms: u64, success: bool) {
        let mut lock = self.metrics.lock().unwrap();
        let stats = lock.entry(agent_id.to_string()).or_default();

        stats.total_calls += 1;
        if success {
            stats.success_count += 1;
        } else {
            stats.failure_count += 1;
        }

        // Rolling average for latency
        let n = stats.total_calls as f64;
        stats.average_latency_ms = (stats.average_latency_ms * (n - 1.0) + latency_ms as f64) / n;
        stats.last_call = Some(Utc::now());
    }

    pub fn get_report(&self) -> HashMap<String, AgentMetrics> {
        self.metrics.lock().unwrap().clone()
    }
}
