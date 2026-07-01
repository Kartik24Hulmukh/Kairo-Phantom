//! Multi-monitor coordinate mapping — verifies the pure layout math against
//! synthetic monitor configurations (no real displays; runs headless).

use phantom_core::monitor::{MonitorInfo, MonitorLayout};

fn mon(id: &str, x: i32, y: i32, w: i32, h: i32, scale: f64, primary: bool) -> MonitorInfo {
    MonitorInfo {
        id: id.to_string(),
        x,
        y,
        width: w,
        height: h,
        scale,
        primary,
    }
}

fn dual_1080p() -> MonitorLayout {
    MonitorLayout::new(vec![
        mon("left", 0, 0, 1920, 1080, 1.0, true),
        mon("right", 1920, 0, 1920, 1080, 1.0, false),
    ])
}

fn mixed_dpi() -> MonitorLayout {
    MonitorLayout::new(vec![
        mon("secondary", -1920, 0, 1920, 1080, 1.0, false),
        mon("primary", 0, 0, 3840, 2160, 1.5, true),
    ])
}

#[test]
fn hit_testing_selects_correct_monitor() {
    let l = dual_1080p();
    assert_eq!(l.monitor_at(10, 10).unwrap().id, "left");
    assert_eq!(l.monitor_at(2000, 500).unwrap().id, "right");
    assert!(l.monitor_at(3840, 0).is_none()); // right edge exclusive
}

#[test]
fn logical_to_physical_on_secondary_monitor() {
    let l = dual_1080p();
    let (px, py) = l.logical_to_physical("right", 100.0, 100.0).unwrap();
    assert_eq!((px, py), (2020, 100));
}

#[test]
fn logical_to_physical_applies_per_monitor_scale() {
    let l = mixed_dpi();
    assert_eq!(
        l.logical_to_physical("primary", 200.0, 200.0).unwrap(),
        (300, 300)
    );
    assert_eq!(
        l.logical_to_physical("secondary", 200.0, 200.0).unwrap(),
        (-1720, 200)
    );
}

#[test]
fn physical_to_logical_round_trip() {
    let l = mixed_dpi();
    let (id, lx, ly) = l.physical_to_logical(300, 300).unwrap();
    assert_eq!(id, "primary");
    assert!((lx - 200.0).abs() < 1e-9 && (ly - 200.0).abs() < 1e-9);
    assert_eq!(l.logical_to_physical(&id, lx, ly).unwrap(), (300, 300));
}

#[test]
fn physical_to_logical_in_void_returns_none() {
    let l = MonitorLayout::new(vec![
        mon("a", 0, 0, 1000, 1000, 1.0, true),
        mon("b", 2000, 0, 1000, 1000, 1.0, false),
    ]);
    assert!(l.physical_to_logical(1500, 500).is_none());
}

#[test]
fn clamp_brings_void_point_onto_nearest_monitor() {
    let l = MonitorLayout::new(vec![
        mon("a", 0, 0, 1000, 1000, 1.0, true),
        mon("b", 2000, 0, 1000, 1000, 1.0, false),
    ]);
    let (cx, cy) = l.clamp_to_nearest(1200, 500);
    assert_eq!(l.monitor_at(cx, cy).unwrap().id, "a");
    assert_eq!(l.clamp_to_nearest(2500, 500), (2500, 500)); // already on b
}

#[test]
fn clamp_handles_out_of_bounds_point() {
    let l = MonitorLayout::new(vec![
        mon("primary", 0, 0, 2560, 1440, 1.0, true),
        mon("small", 0, 1440, 1280, 720, 1.0, false),
    ]);
    let (cx, cy) = l.clamp_to_nearest(5000, 5000);
    let m = l
        .monitor_at(cx, cy)
        .expect("clamped point must be on a monitor");
    assert!(cx >= m.x && cx < m.right() && cy >= m.y && cy < m.bottom());
}

#[test]
fn virtual_bounds_spans_negative_origin() {
    assert_eq!(mixed_dpi().virtual_bounds(), (-1920, 0, 3840, 2160));
}

#[test]
fn primary_detection_and_fallback() {
    assert_eq!(dual_1080p().primary().id, "left");
    let l2 = MonitorLayout::new(vec![
        mon("x", 0, 0, 800, 600, 1.0, false),
        mon("y", 800, 0, 800, 600, 1.0, false),
    ]);
    assert_eq!(l2.primary().id, "x");
}

#[test]
fn empty_layout_falls_back_to_single_primary() {
    let l = MonitorLayout::new(vec![]);
    assert_eq!(l.len(), 1);
    assert!(l.primary().primary);
    assert_eq!(l.primary().width, 1920);
}

#[test]
fn non_positive_scale_is_guarded() {
    let l = MonitorLayout::new(vec![mon("z", 0, 0, 1920, 1080, 0.0, true)]);
    let (id, lx, ly) = l.physical_to_logical(100, 200).unwrap();
    assert_eq!(id, "z");
    assert_eq!((lx, ly), (100.0, 200.0));
}

#[test]
fn resolve_click_uses_active_monitor_origin_and_scale() {
    use phantom_core::monitor::resolve_click;
    let l = MonitorLayout::new(vec![
        mon("primary", 0, 0, 1920, 1080, 1.0, true),
        mon("right", 1920, 0, 3840, 2160, 1.5, false), // 4K @150% to the right
    ]);
    let window_center = (1920 + 1000, 500); // active window on the right monitor
                                            // logical (100,100) -> origin 1920 + 100*1.5 = 2070 ; 0 + 150 = 150
    assert_eq!(resolve_click(&l, window_center, 1.0, 100, 100), (2070, 150));
}

#[test]
fn resolve_click_falls_back_to_dpi_when_center_in_void() {
    use phantom_core::monitor::resolve_click;
    let l = MonitorLayout::new(vec![
        mon("a", 0, 0, 1000, 1000, 1.0, true),
        mon("b", 2000, 0, 1000, 1000, 1.0, false),
    ]);
    // window center in the gap -> legacy dpi 2.0: (100,100)->(200,200), which lands on "a"
    let (px, py) = resolve_click(&l, (1500, 500), 2.0, 100, 100);
    assert_eq!((px, py), (200, 200));
    assert_eq!(l.monitor_at(px, py).unwrap().id, "a");
}
