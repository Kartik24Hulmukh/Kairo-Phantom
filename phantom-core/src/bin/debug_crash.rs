fn main() {
    #[cfg(windows)]
    {
        let _ = uiautomation::UIAutomation::new();
        println!("Hello from debug_crash with uiautomation!");
    }
    #[cfg(not(windows))]
    {
        println!("debug_crash: uiautomation is Windows-only — not available on this platform");
    }
}
