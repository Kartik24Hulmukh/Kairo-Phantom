use phantom_core::injector::{HumanizedInjector, CLIPBOARD_MUTEX};
use std::sync::atomic::{AtomicBool, Ordering};
use std::sync::Arc;
use std::thread;
use std::time::Duration;

#[test]
fn test_concurrent_clipboard_mutex_safety() {
    let injector = Arc::new(HumanizedInjector::new(0));

    // Acquire the clipboard lock in the main thread
    let guard = CLIPBOARD_MUTEX.lock().unwrap();

    let finished = Arc::new(AtomicBool::new(false));
    let finished_clone = finished.clone();
    let injector_clone = injector.clone();

    // Spawn a background thread that tries to inject
    let handle = thread::spawn(move || {
        injector_clone.inject_via_clipboard("Concurrency Test");
        finished_clone.store(true, Ordering::SeqCst);
    });

    // Sleep to give the background thread time to start and execute if not blocked
    thread::sleep(Duration::from_millis(1000));

    // Since the main thread holds the lock, the background thread must be blocked
    assert!(
        !finished.load(Ordering::SeqCst),
        "Background thread should be blocked by CLIPBOARD_MUTEX"
    );

    // Release the lock
    drop(guard);

    // Wait for the background thread to finish
    handle.join().unwrap();

    // Now it should be finished
    assert!(
        finished.load(Ordering::SeqCst),
        "Background thread should have finished after lock release"
    );
}
