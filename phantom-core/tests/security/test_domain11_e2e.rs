#[cfg(feature = "cua")]
mod tests {
    use serde_json::json;
    use std::time::Duration;
    use tokio::time::sleep;

    use phantom_core::cua::cua_planner::CuaPlanner;
    use phantom_core::cua::vlm_bridge::VlmBridge;
    use phantom_core::cua::world_model;
    use phantom_core::cua::CuaContext;

    #[cfg(target_os = "windows")]
    async fn start_mock_sidecar(pipe_name: String) -> tokio::task::JoinHandle<()> {
        tokio::spawn(async move {
            use tokio::io::{AsyncReadExt, AsyncWriteExt};
            use tokio::net::windows::named_pipe::ServerOptions;

            if let Ok(mut server) = ServerOptions::new()
                .first_pipe_instance(true)
                .create(&pipe_name)
            {
                // Accept client
                if server.connect().await.is_ok() {
                    let mut buf = vec![0u8; 65536];
                    if let Ok(n) = server.read(&mut buf).await {
                        let req_str = String::from_utf8_lossy(&buf[..n]);
                        if req_str.contains("vlm_ground") {
                            let resp = json!({
                                "ok": true,
                                "data": {
                                    "found": true,
                                    "x": 840,
                                    "y": 450,
                                    "confidence": 0.97,
                                    "description": "Mocked Submit button found",
                                    "latency_ms": 120.0
                                }
                            });
                            let resp_str = format!("{resp}\n");
                            let _ = server.write_all(resp_str.as_bytes()).await;
                        }
                    }
                }
            }
        })
    }

    #[cfg(not(target_os = "windows"))]
    async fn start_mock_sidecar(socket_path: String) -> tokio::task::JoinHandle<()> {
        tokio::spawn(async move {
            use std::fs;
            use tokio::io::{AsyncReadExt, AsyncWriteExt};
            use tokio::net::UnixListener;

            let _ = fs::remove_file(&socket_path);
            if let Ok(listener) = UnixListener::bind(&socket_path) {
                if let Ok((mut stream, _)) = listener.accept().await {
                    let mut buf = vec![0u8; 65536];
                    if let Ok(n) = stream.read(&mut buf).await {
                        let req_str = String::from_utf8_lossy(&buf[..n]);
                        if req_str.contains("vlm_ground") {
                            let resp = json!({
                                "ok": true,
                                "data": {
                                    "found": true,
                                    "x": 840,
                                    "y": 450,
                                    "confidence": 0.97,
                                    "description": "Mocked Submit button found",
                                    "latency_ms": 120.0
                                }
                            });
                            let resp_str = format!("{resp}\n");
                            let _ = stream.write_all(resp_str.as_bytes()).await;
                        }
                    }
                }
                let _ = fs::remove_file(&socket_path);
            }
        })
    }

    #[tokio::test]
    async fn test_vlm_bridge_integration_and_grounding() {
        #[cfg(target_os = "windows")]
        let pipe_name = r"\\.\pipe\kairo_sidecar_test_domain11".to_string();
        #[cfg(not(target_os = "windows"))]
        let pipe_name = "/tmp/kairo.sock".to_string();

        // Start background mock sidecar listener
        let sidecar_handle = start_mock_sidecar(pipe_name.clone()).await;

        // Give the listener a brief moment to bind/create
        sleep(Duration::from_millis(100)).await;

        // Instantiate VlmBridge pointing to our mock pipe/socket
        let bridge = VlmBridge::with_config(pipe_name, Duration::from_secs(5));

        // Exercise element grounding
        let res = bridge
            .ground_element("dummy_screenshot.png", "Submit button")
            .await;

        assert!(
            res.is_ok(),
            "Failed to call ground_element on VlmBridge: {:?}",
            res.err()
        );
        let resp = res.unwrap();
        assert!(resp.found, "Expected element to be found");
        assert_eq!(resp.x, 840);
        assert_eq!(resp.y, 450);
        assert!((resp.confidence - 0.97).abs() < 0.001);

        // Wait for server task to finish cleanly
        let _ = sidecar_handle.await;
    }

    #[tokio::test]
    async fn test_domain11_mock_gauntlet_run() {
        // Instantiate a mock gauntlet run representing a CUA Execution flow
        let planner = CuaPlanner::new();
        let ctx = CuaContext {
            app_name: "GenericApp".to_string(),
            window_title: "Generic Document Window".to_string(),
            ..Default::default()
        };

        // Asserting that planning for a known shortcut is mapped successfully
        let plan_res = planner.plan("undo", &ctx).await;
        assert!(plan_res.is_ok(), "Planner failed: {:?}", plan_res.err());
        let plan = plan_res.unwrap();
        assert_eq!(plan.source, phantom_core::cua::PlanSource::Template);
        assert!(!plan.actions.is_empty());

        // Asserting world model tracking registers correctly
        let total_actions = world_model::TOTAL_ACTIONS.load(std::sync::atomic::Ordering::SeqCst);
        assert!(
            total_actions > 0,
            "CUA Planner did not increment world model action counters"
        );
    }
}

#[cfg(not(feature = "cua"))]
#[test]
fn test_domain11_e2e_cua_not_enabled() {
    println!("CUA feature not enabled; skipping Domain 11 E2E tests");
}
