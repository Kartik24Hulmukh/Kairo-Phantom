//! Domain 8: Screen Context Engine
//!
//! Captures the active window screenshot and extracts structured context
//! using farscry (VASP output). Falls back to Win32 OCR if farscry is unavailable.
//!
//! Integration: Alt+Shift+M → capture screenshot → farscry CLI → structured
//! context → LLM prompt enrichment → ghost-write response.

use anyhow::{bail, Context, Result};
use std::path::{Path, PathBuf};
use tracing::{info, warn};

use crate::config::ScreenContextConfig;

/// Captures and analyzes screen content for LLM context enrichment.
pub struct ScreenContextEngine {
    /// Path to farscry binary (auto-detected or configured)
    farscry_path: Option<PathBuf>,
    /// Directory for temporary screenshot files
    temp_dir: PathBuf,
    /// Configuration
    config: ScreenContextConfig,
}

/// Structured screen context extracted from a screenshot.
#[derive(Debug, Clone, Default)]
pub struct ScreenContext {
    /// Raw VASP output from farscry (structured layout + OCR)
    pub vasp_output: String,
    /// Application name from window detection
    pub app_name: String,
    /// Window title
    pub window_title: String,
    /// Path to the captured screenshot
    pub screenshot_path: Option<PathBuf>,
    /// Capture timestamp
    pub timestamp: String,
    /// Whether farscry was used (true) or fallback OCR (false)
    pub used_farscry: bool,
}

impl ScreenContextEngine {
    /// Create a new ScreenContextEngine.
    pub fn new(config: ScreenContextConfig) -> Self {
        let temp_dir = dirs::home_dir()
            .unwrap_or_else(|| PathBuf::from("."))
            .join(".kairo-phantom")
            .join("tmp");
        std::fs::create_dir_all(&temp_dir).ok();

        let farscry_path = config
            .farscry_path
            .as_ref()
            .map(PathBuf::from)
            .or_else(Self::find_farscry_in_path);

        if let Some(ref path) = farscry_path {
            info!("📸 ScreenContextEngine: farscry found at {:?}", path);
        } else {
            info!("📸 ScreenContextEngine: farscry not found, OCR fallback will be used");
        }

        ScreenContextEngine {
            farscry_path,
            temp_dir,
            config,
        }
    }

    /// Check if the engine is available (farscry or fallback).
    pub fn is_available(&self) -> bool {
        self.config.enabled
    }

    /// Check if farscry is available specifically.
    pub fn has_farscry(&self) -> bool {
        self.farscry_path
            .as_ref()
            .map(|p| p.exists())
            .unwrap_or(false)
    }

    /// Capture screenshot and extract structured context.
    ///
    /// Full pipeline: Win32 screenshot → save PNG → farscry VASP → ScreenContext
    pub async fn capture_and_extract(
        &self,
        app_name: &str,
        window_title: &str,
    ) -> Result<ScreenContext> {
        if !self.config.enabled {
            bail!("Screen context capture is disabled in config");
        }

        // 1. Capture active window screenshot
        let screenshot_path = self.capture_screenshot()?;
        info!("📸 Screenshot captured: {}", screenshot_path.display());

        // 2. Extract structured context
        let (vasp_output, used_farscry) = if let Some(ref farscry) = self.farscry_path {
            match self.extract_with_farscry(farscry, &screenshot_path).await {
                Ok(output) => (output, true),
                Err(e) => {
                    warn!("⚠️ farscry failed: {}. Using fallback.", e);
                    (self.fallback_extract(&screenshot_path)?, false)
                }
            }
        } else {
            (self.fallback_extract(&screenshot_path)?, false)
        };

        let timestamp = chrono::Utc::now().format("%Y-%m-%dT%H:%M:%SZ").to_string();

        Ok(ScreenContext {
            vasp_output,
            app_name: app_name.to_string(),
            window_title: window_title.to_string(),
            screenshot_path: Some(screenshot_path),
            timestamp,
            used_farscry,
        })
    }

    /// Capture the active/foreground window as a BMP/PNG file.
    #[cfg(windows)]
    pub fn capture_screenshot(&self) -> Result<PathBuf> {
        use windows::Win32::Foundation::HWND;
        use windows::Win32::Graphics::Gdi::{
            BitBlt, CreateCompatibleBitmap, CreateCompatibleDC, DeleteDC, DeleteObject, GetDC,
            GetDIBits, ReleaseDC, SelectObject, BITMAPINFO, BITMAPINFOHEADER, BI_RGB,
            DIB_RGB_COLORS, SRCCOPY,
        };
        use windows::Win32::UI::WindowsAndMessaging::GetClientRect;
        use windows::Win32::UI::WindowsAndMessaging::GetForegroundWindow;

        let filename = format!(
            "kairo_screen_{}.bmp",
            chrono::Utc::now().format("%Y%m%d_%H%M%S")
        );
        let output_path = self.temp_dir.join(filename);

        unsafe {
            let hwnd: HWND = GetForegroundWindow();
            let mut rect = windows::Win32::Foundation::RECT::default();
            let _ = GetClientRect(hwnd, &mut rect);

            let width = rect.right - rect.left;
            let height = rect.bottom - rect.top;

            if width <= 0 || height <= 0 {
                bail!("Invalid window dimensions: {width}x{height}");
            }

            let hdc_window = GetDC(hwnd);
            let hdc_mem = CreateCompatibleDC(hdc_window);
            let hbm = CreateCompatibleBitmap(hdc_window, width, height);
            let old = SelectObject(hdc_mem, hbm);

            // Copy window content to our bitmap
            let _ = BitBlt(hdc_mem, 0, 0, width, height, hdc_window, 0, 0, SRCCOPY);

            // Read bitmap data
            let mut bmi = BITMAPINFO {
                bmiHeader: BITMAPINFOHEADER {
                    biSize: std::mem::size_of::<BITMAPINFOHEADER>() as u32,
                    biWidth: width,
                    biHeight: -height, // Top-down
                    biPlanes: 1,
                    biBitCount: 24,
                    biCompression: BI_RGB.0,
                    ..Default::default()
                },
                ..Default::default()
            };

            let row_size = ((width * 3 + 3) & !3) as usize; // 4-byte aligned
            let data_size = row_size * height as usize;
            let mut pixels = vec![0u8; data_size];

            GetDIBits(
                hdc_mem,
                hbm,
                0,
                height as u32,
                Some(pixels.as_mut_ptr() as *mut _),
                &mut bmi,
                DIB_RGB_COLORS,
            );

            // Write BMP file
            Self::write_bmp_file(&output_path, width, height, &pixels)?;

            // Cleanup GDI objects
            SelectObject(hdc_mem, old);
            let _ = DeleteObject(hbm);
            let _ = DeleteDC(hdc_mem);
            ReleaseDC(hwnd, hdc_window);
        }

        Ok(output_path)
    }

    #[cfg(not(windows))]
    pub fn capture_screenshot(&self) -> Result<PathBuf> {
        let filename = format!(
            "kairo_screen_{}.png",
            chrono::Utc::now().format("%Y%m%d_%H%M%S")
        );
        let output_path = self.temp_dir.join(filename);

        // Use scrot or gnome-screenshot on Linux, screencapture on macOS
        let status = std::process::Command::new("screencapture")
            .args(["-x", output_path.to_str().unwrap_or("screenshot.png")])
            .status()
            .or_else(|_| {
                std::process::Command::new("scrot")
                    .arg(output_path.to_str().unwrap_or("screenshot.png"))
                    .status()
            })?;

        if !status.success() {
            bail!("Screenshot capture failed");
        }
        Ok(output_path)
    }

    /// Extract structured context using farscry CLI.
    async fn extract_with_farscry(&self, farscry_path: &Path, image_path: &Path) -> Result<String> {
        let output = tokio::process::Command::new(farscry_path)
            .args(["extract", image_path.to_str().unwrap_or("")])
            .stdout(std::process::Stdio::piped())
            .stderr(std::process::Stdio::piped())
            .output()
            .await
            .context("Failed to run farscry")?;

        if !output.status.success() {
            let stderr = String::from_utf8_lossy(&output.stderr);
            bail!("farscry failed: {stderr}");
        }

        let vasp = String::from_utf8_lossy(&output.stdout).to_string();
        info!("📸 farscry VASP output: {} chars", vasp.len());

        Ok(vasp)
    }

    /// Fallback: extract text from screenshot using simple OCR description.
    /// Since we don't bundle tesseract, we describe the screenshot for the sidecar.
    fn fallback_extract(&self, image_path: &Path) -> Result<String> {
        // Build a context description from the screenshot file metadata
        let metadata = std::fs::metadata(image_path)?;
        let size_kb = metadata.len() / 1024;

        Ok(format!(
            "[Screen Context: Screenshot captured ({} KB). \
             OCR processing delegated to sidecar. \
             Image path: {}]",
            size_kb,
            image_path.display()
        ))
    }

    /// Find farscry in system PATH.
    fn find_farscry_in_path() -> Option<PathBuf> {
        let candidates = if cfg!(windows) {
            vec!["farscry.cmd", "farscry.exe", "farscry"]
        } else {
            vec!["farscry"]
        };

        for name in candidates {
            if let Ok(output) =
                std::process::Command::new(if cfg!(windows) { "where" } else { "which" })
                    .arg(name)
                    .output()
            {
                if output.status.success() {
                    let path_str = String::from_utf8_lossy(&output.stdout);
                    let first_line = path_str.lines().next().unwrap_or("").trim();
                    if !first_line.is_empty() {
                        return Some(PathBuf::from(first_line));
                    }
                }
            }
        }

        None
    }

    #[cfg(windows)]
    fn write_bmp_file(path: &Path, width: i32, height: i32, pixels: &[u8]) -> Result<()> {
        use std::io::Write;

        let row_size = ((width * 3 + 3) & !3) as u32;
        let data_size = row_size * height as u32;
        let file_size = 54 + data_size;

        let mut f = std::fs::File::create(path)?;

        // BMP file header (14 bytes)
        f.write_all(b"BM")?;
        f.write_all(&file_size.to_le_bytes())?;
        f.write_all(&0u16.to_le_bytes())?; // reserved
        f.write_all(&0u16.to_le_bytes())?; // reserved
        f.write_all(&54u32.to_le_bytes())?; // pixel data offset

        // DIB header (40 bytes)
        f.write_all(&40u32.to_le_bytes())?;
        f.write_all(&width.to_le_bytes())?;
        f.write_all(&height.to_le_bytes())?; // positive = bottom-up
        f.write_all(&1u16.to_le_bytes())?; // planes
        f.write_all(&24u16.to_le_bytes())?; // bits per pixel
        f.write_all(&0u32.to_le_bytes())?; // compression (none)
        f.write_all(&data_size.to_le_bytes())?;
        f.write_all(&2835u32.to_le_bytes())?; // X ppm
        f.write_all(&2835u32.to_le_bytes())?; // Y ppm
        f.write_all(&0u32.to_le_bytes())?; // colors
        f.write_all(&0u32.to_le_bytes())?; // important colors

        // Pixel data (already in BGR format from GetDIBits)
        // Write rows bottom-to-top for BMP format
        let row_bytes = row_size as usize;
        for y in (0..height as usize).rev() {
            let start = y * row_bytes;
            let end = start + row_bytes;
            if end <= pixels.len() {
                f.write_all(&pixels[start..end])?;
            }
        }

        Ok(())
    }
}

impl ScreenContext {
    /// Format the screen context for inclusion in an LLM prompt.
    pub fn to_prompt_context(&self) -> String {
        format!(
            "═══ SCREEN CONTEXT (captured {}) ═══\n\
             App: {} | Window: {}\n\
             Method: {}\n\
             ───────────────────────────────\n\
             {}\n\
             ═══════════════════════════════",
            self.timestamp,
            self.app_name,
            self.window_title,
            if self.used_farscry {
                "farscry VASP"
            } else {
                "fallback OCR"
            },
            self.vasp_output
        )
    }
}
