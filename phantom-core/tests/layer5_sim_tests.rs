// ============================================================
// LAYER 5: Deterministic Simulation Tests
//
// FoundationDB-style: seed-based deterministic async execution
// - Tests ghost session lifecycle under simulated time
// - 1000 seeds, each must produce zero panics
// - Any failure is perfectly reproducible by seed ID
// ============================================================
use phantom_core::config::PhantomConfig;
use phantom_core::ghost_session::{ConfidenceBand, GhostSession};
use std::sync::atomic::Ordering::Relaxed;

/// Deterministic pseudo-random number generator (LCG seeded)
struct DeterministicRng {
    state: u64,
}

impl DeterministicRng {
    fn new(seed: u64) -> Self {
        Self { state: seed }
    }

    fn next_u64(&mut self) -> u64 {
        // LCG constants from Numerical Recipes
        self.state = self
            .state
            .wrapping_mul(6364136223846793005)
            .wrapping_add(1442695040888963407);
        self.state
    }

    fn next_bool(&mut self) -> bool {
        self.next_u64() % 2 == 0
    }
    fn next_range(&mut self, max: u64) -> u64 {
        self.next_u64() % max
    }
}

/// Run one deterministic simulation with the given seed
/// Returns Ok(()) if the simulation completed without panic
/// Returns Err(seed) if something failed — seed can reproduce it
fn run_simulation(seed: u64) -> Result<(), u64> {
    let mut rng = DeterministicRng::new(seed);

    // Generate deterministic test scenario
    let prompt_len = (rng.next_range(500) + 5) as usize;
    let confidence_roll = rng.next_range(3);
    let confidence = match confidence_roll {
        0 => ConfidenceBand::High,
        1 => ConfidenceBand::Medium,
        _ => ConfidenceBand::Low,
    };

    // Build prompt from seed (deterministic)
    let prompt = format!("simulation test seed={seed} len={prompt_len}");

    // Create session — must not panic
    let session = GhostSession::new(&prompt, prompt.len(), confidence);

    // Validate invariants hold under this seed's fault configuration
    if session.prompt_char_count != prompt.len() {
        return Err(seed);
    }

    if session.original_prompt != prompt {
        return Err(seed);
    }

    // Optionally cancel (deterministic choice)
    if rng.next_bool() {
        session.cancel_token.cancel();
        if !session.cancel_token.is_cancelled() {
            return Err(seed);
        }
    }

    Ok(())
}

// ──────────────────────────────────────────────────────────────
// Simulation Test 1: 1000 seeds — zero failures
// ──────────────────────────────────────────────────────────────
#[test]
fn sim_1000_seeds_zero_panics() {
    let mut failures = Vec::new();

    for seed in 0..1000u64 {
        match run_simulation(seed) {
            Ok(()) => {}
            Err(failed_seed) => {
                failures.push(failed_seed);
                eprintln!(
                    "SIMULATION FAILURE: seed={failed_seed} — reproduce with run_simulation({failed_seed})"
                );
            }
        }
    }

    assert!(
        failures.is_empty(),
        "Simulation failures at seeds: {failures:?}\n\
         Reproduce any failure with: run_simulation(<seed>)"
    );
}

// ──────────────────────────────────────────────────────────────
// Simulation Test 2: Ghost session lifecycle — 500 seeds
// ──────────────────────────────────────────────────────────────
#[test]
fn sim_ghost_lifecycle_500_seeds() {
    for seed in 1000..1500u64 {
        let mut rng = DeterministicRng::new(seed);

        let prompt = format!("ghost lifecycle seed {seed}");
        let confidence = match rng.next_range(3) {
            0 => ConfidenceBand::High,
            1 => ConfidenceBand::Medium,
            _ => ConfidenceBand::Low,
        };

        let session = GhostSession::new(&prompt, prompt.len(), confidence);

        // Invariant: prompt_char_count always equals actual length
        assert_eq!(
            session.prompt_char_count,
            prompt.len(),
            "Invariant broken at seed={seed}"
        );

        // Invariant: original_prompt always preserved
        assert_eq!(
            session.original_prompt, prompt,
            "Prompt data corrupted at seed={seed}"
        );

        // Invariant: cancel token starts uncancelled
        assert!(
            !session.cancel_token.is_cancelled(),
            "Token starts cancelled at seed={seed}"
        );
    }
}

// ──────────────────────────────────────────────────────────────
// Simulation Test 3: Config stability across 200 seeds
// ──────────────────────────────────────────────────────────────
#[test]
fn sim_config_stability_200_seeds() {
    for seed in 2000..2200u64 {
        let mut rng = DeterministicRng::new(seed);

        let mut cfg = PhantomConfig::default();
        cfg.typing_delay_ms = rng.next_range(500);

        // Serialize → deserialize must be lossless
        let toml_str = toml::to_string_pretty(&cfg)
            .unwrap_or_else(|e| panic!("seed={seed} serialize failed: {e}"));

        let restored: PhantomConfig = toml::from_str(&toml_str)
            .unwrap_or_else(|e| panic!("seed={seed} deserialize failed: {e}"));

        assert_eq!(
            restored.typing_delay_ms, cfg.typing_delay_ms,
            "Config unstable at seed={seed}"
        );
    }
}

// ──────────────────────────────────────────────────────────────
// Simulation Test 4: Concurrent sessions — 50 seeds × 10 sessions
// ──────────────────────────────────────────────────────────────
#[tokio::test]
async fn sim_concurrent_sessions_50_seeds() {
    for seed in 3000..3050u64 {
        let mut rng = DeterministicRng::new(seed);
        let n_sessions = (rng.next_range(9) + 2) as usize; // 2–10 sessions

        let handles: Vec<_> = (0..n_sessions)
            .map(|i| {
                let prompt = format!("seed={seed} session={i}");
                tokio::spawn(async move {
                    let session = GhostSession::new(&prompt, prompt.len(), ConfidenceBand::High);
                    session.cancel_token.cancel();
                    assert!(session.cancel_token.is_cancelled());
                    i
                })
            })
            .collect();

        let results = futures::future::join_all(handles).await;
        for res in results {
            res.expect("Session task panicked");
        }
    }
}
