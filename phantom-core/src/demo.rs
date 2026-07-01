use std::process::Command;
use std::time::Duration;
use tokio::time::sleep;
use rand::Rng;

pub async fn run_demo_mode(app_handle: &tauri::AppHandle) {
    println!("Starting Kairo Phantom Demo Mode...");

    // 1. Open fake document window
    let window = tauri::WebviewWindowBuilder::new(
        app_handle,
        "demo_window",
        tauri::WebviewUrl::App("demo.html".into())
    )
    .inner_size(800.0, 600.0)
    .title("Document1 — Kairo Phantom Demo")
    .build()
    .unwrap();

    // Give window time to render
    sleep(Duration::from_secs(2)).await;

    // 2. Start ffmpeg recording
    // FFMPEG COMMAND: capture only the Kairo window (not full screen) at 1920x1080 equivalent, 30fps, H.264, optimized for Twitter/X upload (max 512MB, < 140 seconds).
    let output_path = dirs::desktop_dir().unwrap().join("kairo-demo.mp4");
    
    #[cfg(target_os = "windows")]
    let mut ffmpeg = Command::new("ffmpeg")
        .args(&[
            "-y", 
            "-f", "gdigrab", 
            "-framerate", "30",
            "-i", "title=Document1 — Kairo Phantom Demo", 
            "-c:v", "libx264",
            "-preset", "fast",
            "-crf", "23",
            "-pix_fmt", "yuv420p",
            "-s", "1920x1080", // force 1080p scale equivalent
            output_path.to_str().unwrap()
        ])
        .spawn()
        .expect("Failed to start ffmpeg");

    #[cfg(target_os = "macos")]
    let mut ffmpeg = Command::new("ffmpeg")
        .args(&[
            "-y",
            "-f", "avfoundation",
            "-framerate", "30",
            "-i", "1", 
            "-c:v", "libx264",
            "-preset", "fast",
            "-crf", "23",
            "-pix_fmt", "yuv420p",
            "-s", "1920x1080",
            output_path.to_str().unwrap()
        ])
        .spawn()
        .expect("Failed to start ffmpeg");

    // 3. Simulate user typing prompt
    let prompt = "Write a persuasive executive summary for our Q3 product migration.\n\n";
    for c in prompt.chars() {
        let js = format!("window.typeCharacter(`{}`);", if c == '\n' { "\\n" } else { &c.to_string() });
        let _ = window.eval(&js);
        sleep(Duration::from_millis(80)).await;
    }

    sleep(Duration::from_secs(1)).await;

    // Show confidence band
    let _ = window.eval("window.showConfidenceBand();");
    
    sleep(Duration::from_millis(1500)).await;

    // 4. Ghost-type the hardcoded response
    let response = "EXECUTIVE SUMMARY\n\nOur Q3 product migration represents a critical inflection point for enterprise scaling. By transitioning to the new infrastructure, we will reduce latency by 40% and unlock $2M in annualized operational savings.\n\nKey Objectives:\n- Seamless transition with zero downtime\n- Security compliance audit completion\n- Enterprise customer onboarding\n\nThe strategic ROI of this migration is positive within 4 months.";
    
    let mut rng = rand::thread_rng();
    
    for c in response.chars() {
        let js = format!("window.typeCharacter(`{}`);", if c == '\n' { "\\n" } else { &c.to_string() });
        let _ = window.eval(&js);
        
        // Natural speed (60-120ms/char)
        let delay = rng.gen_range(60..=120);
        sleep(Duration::from_millis(delay)).await;
    }

    // 5. Stop recording after a short pause
    sleep(Duration::from_secs(2)).await;
    
    #[cfg(any(target_os = "windows", target_os = "macos"))]
    {
        // Gracefully kill ffmpeg
        let _ = ffmpeg.kill();
    }

    // 6. Open the file
    let _ = open::that(output_path);
}
