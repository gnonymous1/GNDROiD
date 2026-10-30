use std::collections::HashMap;
use std::path::{Path, PathBuf};
use std::sync::Arc;
use tokio::sync::RwLock;
use tracing::info;

pub const VSOCK_PORT_CELLULAR_RIL: u32 = 5000;
pub const VSOCK_PORT_AI_CONTROL: u32 = 5001;
pub const VSOCK_PORT_EBPF_TELEMETRY: u32 = 5002;
pub const VSOCK_PORT_ROOT_ORCHESTRATOR: u32 = 5003;

#[derive(Debug, Clone)]
pub struct VsockRouteConfig {
    pub port: u32,
    pub description: String,
    pub target_endpoint: String,
}

pub struct VsockRouter {
    socket_path: PathBuf,
    routes: Arc<RwLock<HashMap<u32, VsockRouteConfig>>>,
}

impl VsockRouter {
    pub fn new(socket_path: PathBuf) -> Self {
        let mut default_routes = HashMap::new();
        default_routes.insert(
            VSOCK_PORT_CELLULAR_RIL,
            VsockRouteConfig {
                port: VSOCK_PORT_CELLULAR_RIL,
                description: "AIDL IRadio 2.1+ Telephony & APDU Tunnel".to_string(),
                target_endpoint: "127.0.0.1:50051".to_string(),
            },
        );
        default_routes.insert(
            VSOCK_PORT_AI_CONTROL,
            VsockRouteConfig {
                port: VSOCK_PORT_AI_CONTROL,
                description: "AI Control Plane & Framebuffer DMA-BUF Sync".to_string(),
                target_endpoint: "127.0.0.1:50052".to_string(),
            },
        );
        default_routes.insert(
            VSOCK_PORT_EBPF_TELEMETRY,
            VsockRouteConfig {
                port: VSOCK_PORT_EBPF_TELEMETRY,
                description: "eBPF Jank & Causality Stream".to_string(),
                target_endpoint: "127.0.0.1:50053".to_string(),
            },
        );
        default_routes.insert(
            VSOCK_PORT_ROOT_ORCHESTRATOR,
            VsockRouteConfig {
                port: VSOCK_PORT_ROOT_ORCHESTRATOR,
                description: "KernelSU Dynamic UID Whitelister".to_string(),
                target_endpoint: "127.0.0.1:50054".to_string(),
            },
        );

        Self {
            socket_path,
            routes: Arc::new(RwLock::new(default_routes)),
        }
    }

    pub async fn register_route(&self, port: u32, description: &str, target: &str) {
        let mut routes = self.routes.write().await;
        routes.insert(
            port,
            VsockRouteConfig {
                port,
                description: description.to_string(),
                target_endpoint: target.to_string(),
            },
        );
        info!("Registered Vsock route on port {}: {} -> {}", port, description, target);
    }

    pub async fn list_routes(&self) -> Vec<VsockRouteConfig> {
        let routes = self.routes.read().await;
        routes.values().cloned().collect()
    }

    pub fn get_socket_path(&self) -> &Path {
        &self.socket_path
    }
}
