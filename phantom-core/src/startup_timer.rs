//! Startup Timer — P0-A1
//! Added to perf_engine.rs — tracks milliseconds elapsed at each startup checkpoint.

pub struct StartupTimer {
    start: std::time::Instant,
}

impl StartupTimer {
    pub fn new() -> Self {
        Self {
            start: std::time::Instant::now(),
        }
    }

    /// Log a named checkpoint with elapsed milliseconds since construction.
    pub fn checkpoint(&self, label: &str) {
        let ms = self.start.elapsed().as_millis();
        tracing::info!("⚡ Startup [{:>5}ms] {}", ms, label);
        if ms > 200 {
            tracing::warn!("🐢 Startup exceeded 200ms target at: {} ({}ms)", label, ms);
        }
    }

    /// Return elapsed ms since construction.
    pub fn elapsed_ms(&self) -> u128 {
        self.start.elapsed().as_millis()
    }
}

impl Default for StartupTimer {
    fn default() -> Self {
        Self::new()
    }
}
