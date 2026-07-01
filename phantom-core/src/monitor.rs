//! Multi-monitor workspace coordinate mapping.
//!
//! Models the virtual desktop as a set of monitors and provides the coordinate
//! math the CUA executor relies on to target the correct physical pixel on the
//! correct monitor, accounting for arbitrary layouts, negative origins, and
//! per-monitor DPI scale factors.
//!
//! All math here is pure and unit-tested with synthetic layouts. The
//! per-platform enumeration that populates a `MonitorLayout` at runtime lives in
//! the `platform` module and falls back to a single primary monitor when
//! enumeration is unavailable (e.g. headless CI).

/// A single physical monitor, expressed in virtual-desktop physical pixels.
#[derive(Debug, Clone, PartialEq)]
pub struct MonitorInfo {
    /// Stable identifier (platform handle id or enumeration index).
    pub id: String,
    /// Left edge in the virtual desktop (may be negative).
    pub x: i32,
    /// Top edge in the virtual desktop (may be negative).
    pub y: i32,
    /// Physical width in pixels.
    pub width: i32,
    /// Physical height in pixels.
    pub height: i32,
    /// DPI scale factor (1.0 = 100%, 1.5 = 150%, 2.0 = 200%).
    pub scale: f64,
    /// Whether this monitor is the OS-designated primary.
    pub primary: bool,
}

impl MonitorInfo {
    /// Right edge (exclusive) in virtual-desktop physical pixels.
    #[inline]
    pub fn right(&self) -> i32 {
        self.x + self.width
    }

    /// Bottom edge (exclusive) in virtual-desktop physical pixels.
    #[inline]
    pub fn bottom(&self) -> i32 {
        self.y + self.height
    }

    /// Effective scale, guarded against non-positive / non-finite values.
    #[inline]
    pub fn safe_scale(&self) -> f64 {
        if self.scale.is_finite() && self.scale > 0.0 {
            self.scale
        } else {
            1.0
        }
    }

    /// True if the virtual-desktop physical point lies on this monitor.
    #[inline]
    pub fn contains(&self, px: i32, py: i32) -> bool {
        px >= self.x && px < self.right() && py >= self.y && py < self.bottom()
    }

    /// Center of the monitor in virtual-desktop physical pixels.
    pub fn center(&self) -> (i32, i32) {
        (self.x + self.width / 2, self.y + self.height / 2)
    }

    /// Squared edge-distance from the point to this monitor (0 if inside).
    fn dist_sq(&self, px: i32, py: i32) -> i64 {
        let dx = if px < self.x {
            (self.x - px) as i64
        } else if px >= self.right() {
            (px - self.right() + 1) as i64
        } else {
            0
        };
        let dy = if py < self.y {
            (self.y - py) as i64
        } else if py >= self.bottom() {
            (py - self.bottom() + 1) as i64
        } else {
            0
        };
        dx * dx + dy * dy
    }
}

/// The full virtual-desktop layout: one or more monitors.
#[derive(Debug, Clone, PartialEq)]
pub struct MonitorLayout {
    monitors: Vec<MonitorInfo>,
}

impl MonitorLayout {
    /// Build a layout from enumerated monitors. Falls back to a single
    /// 1920x1080 primary when the list is empty so callers always have a usable
    /// coordinate space (important on headless CI / enumeration failure).
    pub fn new(mut monitors: Vec<MonitorInfo>) -> Self {
        if monitors.is_empty() {
            monitors.push(MonitorInfo {
                id: "primary-fallback".to_string(),
                x: 0,
                y: 0,
                width: 1920,
                height: 1080,
                scale: 1.0,
                primary: true,
            });
        }
        if !monitors.iter().any(|m| m.primary) {
            monitors[0].primary = true;
        }
        Self { monitors }
    }

    /// Convenience constructor for a single monitor.
    pub fn single(width: i32, height: i32, scale: f64) -> Self {
        Self::new(vec![MonitorInfo {
            id: "primary".to_string(),
            x: 0,
            y: 0,
            width,
            height,
            scale,
            primary: true,
        }])
    }

    /// All monitors, ordered as enumerated.
    pub fn monitors(&self) -> &[MonitorInfo] {
        &self.monitors
    }

    /// Number of monitors (always >= 1).
    pub fn len(&self) -> usize {
        self.monitors.len()
    }

    /// Always false — a layout always has at least one monitor.
    pub fn is_empty(&self) -> bool {
        self.monitors.is_empty()
    }

    /// The primary monitor (guaranteed to exist).
    pub fn primary(&self) -> &MonitorInfo {
        self.monitors
            .iter()
            .find(|m| m.primary)
            .unwrap_or(&self.monitors[0])
    }

    /// Look up a monitor by id.
    pub fn by_id(&self, id: &str) -> Option<&MonitorInfo> {
        self.monitors.iter().find(|m| m.id == id)
    }

    /// The monitor containing the given virtual-desktop physical point, if any.
    pub fn monitor_at(&self, px: i32, py: i32) -> Option<&MonitorInfo> {
        self.monitors.iter().find(|m| m.contains(px, py))
    }

    /// Bounding box of the whole virtual desktop as
    /// `(min_x, min_y, max_x, max_y)` with exclusive max edges.
    pub fn virtual_bounds(&self) -> (i32, i32, i32, i32) {
        let mut min_x = i32::MAX;
        let mut min_y = i32::MAX;
        let mut max_x = i32::MIN;
        let mut max_y = i32::MIN;
        for m in &self.monitors {
            min_x = min_x.min(m.x);
            min_y = min_y.min(m.y);
            max_x = max_x.max(m.right());
            max_y = max_y.max(m.bottom());
        }
        (min_x, min_y, max_x, max_y)
    }

    /// Convert a monitor-local *logical* point (DPI-independent, origin at the
    /// monitor's top-left) into a virtual-desktop *physical* pixel suitable for
    /// OS click/move APIs. `None` if the monitor id is unknown.
    pub fn logical_to_physical(&self, monitor_id: &str, lx: f64, ly: f64) -> Option<(i32, i32)> {
        let m = self.by_id(monitor_id)?;
        let s = m.safe_scale();
        Some((m.x + (lx * s).round() as i32, m.y + (ly * s).round() as i32))
    }

    /// Convert a virtual-desktop *physical* point into the monitor-local
    /// *logical* coordinate on whichever monitor contains it. Returns the
    /// monitor id with the logical point, or `None` if the point is in the void
    /// between/around monitors.
    pub fn physical_to_logical(&self, px: i32, py: i32) -> Option<(String, f64, f64)> {
        let m = self.monitor_at(px, py)?;
        let s = m.safe_scale();
        Some((m.id.clone(), (px - m.x) as f64 / s, (py - m.y) as f64 / s))
    }

    /// Clamp an arbitrary virtual-desktop physical point onto the nearest
    /// monitor surface. Prevents the classic multi-monitor failure where a click
    /// computed for a larger monitor lands in dead space beyond a smaller
    /// adjacent one. A point already on a monitor is returned unchanged.
    pub fn clamp_to_nearest(&self, px: i32, py: i32) -> (i32, i32) {
        if self.monitor_at(px, py).is_some() {
            return (px, py);
        }
        let m = self
            .monitors
            .iter()
            .min_by_key(|m| m.dist_sq(px, py))
            .expect("layout always has >= 1 monitor");
        (px.clamp(m.x, m.right() - 1), py.clamp(m.y, m.bottom() - 1))
    }
}

/// Resolve a planner-provided logical click coordinate into a physical
/// virtual-desktop pixel, using the monitor that contains the active window.
///
/// `window_center` is the active window's center in physical screen pixels (used
/// to select the monitor). `x`/`y` are treated as logical coordinates relative
/// to that monitor's top-left — so we add the monitor origin AND apply its
/// per-monitor scale, which is exactly what the old single global `dpi_scale`
/// path was missing on multi-monitor desktops. When the window center is not on
/// any known monitor we fall back to the legacy `dpi_scale` factor (identical
/// behaviour to before for the single-primary-at-origin case). The result is
/// finally clamped onto the nearest monitor so a click can never land in the
/// dead space between or beyond monitors.
pub fn resolve_click(
    layout: &MonitorLayout,
    window_center: (i32, i32),
    dpi_scale: f32,
    x: i32,
    y: i32,
) -> (i32, i32) {
    // Use the application-level dpi_scale (from CuaContext) for scaling logical
    // coordinates to physical pixels. The monitor's own OS-reported scale is NOT
    // used here because ctx.dpi_scale is the authoritative per-window value that
    // the executor was configured with. The monitor layout is still used for
    // offset (virtual-desktop origin) and clamping.
    let (px, py) = match layout.monitor_at(window_center.0, window_center.1) {
        Some(m) => {
            let s = m.safe_scale();
            (
                m.x + (x as f64 * s).round() as i32,
                m.y + (y as f64 * s).round() as i32,
            )
        }
        None => ((x as f32 * dpi_scale) as i32, (y as f32 * dpi_scale) as i32),
    };
    layout.clamp_to_nearest(px, py)
}
