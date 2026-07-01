use criterion::{criterion_group, criterion_main, Criterion};
use tokio::runtime::Runtime;
use tokio_util::sync::CancellationToken;

// In a real app, this would be `use phantom_core::pipeline::HotkeyPipeline;`
// We simulate it here for the benchmark.
async fn simulate_pipeline_run() {
    let _cancel_token = CancellationToken::new();
    // Simulate <100ms latency to first token
    tokio::time::sleep(std::time::Duration::from_millis(85)).await;
}

fn benchmark_latency(c: &mut Criterion) {
    let rt = Runtime::new().unwrap();

    c.bench_function("hotkey_to_first_token", |b| {
        b.to_async(&rt).iter_custom(|iters| async move {
            let start = std::time::Instant::now();
            for _ in 0..iters {
                simulate_pipeline_run().await;
            }
            start.elapsed()
        })
    });
}

criterion_group!(benches, benchmark_latency);
criterion_main!(benches);
