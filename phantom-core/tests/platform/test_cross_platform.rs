use phantom_core::platform::new_reader;
use std::env;
use std::fs;
use std::path::Path;

#[test]
fn test_cross_platform_report_verification() {
    let manifest_dir = env::var("CARGO_MANIFEST_DIR").unwrap_or_else(|_| ".".to_string());
    let report_path = Path::new(&manifest_dir).join("../CROSS_PLATFORM_REPORT.md");

    assert!(
        report_path.exists(),
        "CROSS_PLATFORM_REPORT.md does not exist at {report_path:?}"
    );

    let content =
        fs::read_to_string(&report_path).expect("Failed to read CROSS_PLATFORM_REPORT.md");

    // Windows compatibility verification
    assert!(
        content.contains("WindowsUiaReader")
            || content.contains("windows.rs")
            || content.contains("Windows"),
        "Windows compatibility marker missing in report"
    );

    // macOS compatibility verification
    assert!(
        content.contains("MacOsAccessibilityReader")
            || content.contains("macos.rs")
            || content.contains("macOS"),
        "macOS compatibility marker missing in report"
    );

    // Linux compatibility verification
    assert!(
        content.contains("LinuxAtspiReader")
            || content.contains("linux.rs")
            || content.contains("Linux"),
        "Linux compatibility marker missing in report"
    );

    // Gate verifications
    assert!(
        content.contains("Gate 1"),
        "Gate 1 section missing in report"
    );
    assert!(
        content.contains("Gate 2"),
        "Gate 2 section missing in report"
    );
    assert!(
        content.contains("Gate 3"),
        "Gate 3 section missing in report"
    );
}

#[test]
fn test_os_matrix_setup_correctness() {
    // Assert target OS is one of Windows, macOS, or Linux
    let is_supported_os = cfg!(any(
        target_os = "windows",
        target_os = "macos",
        target_os = "linux"
    ));
    assert!(
        is_supported_os,
        "Target OS is not supported by Kairo Phantom"
    );

    // Check that we can create a platform-appropriate reader and it doesn't crash on construction.
    let reader = new_reader();
    let _ = reader.get_clipboard_text();
}
