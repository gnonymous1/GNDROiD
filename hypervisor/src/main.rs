#![allow(unused_mut, dead_code, unused_variables, unused_imports)]

mod snapshot;
mod vmm;
mod vsock_router;

use anyhow::Result;
use clap::Parser;
use std::path::PathBuf;
use tracing::info;
use vmm::{CrosvmManager, VmmConfig};
use vsock_router::VsockRouter;

#[derive(Parser, Debug)]
#[command(name = "emulator-hypervisor", about = "Enterprise Android crosvm micro-VM Hypervisor Orchestrator")]
struct Args {
    #[arg(short, long, default_value = "4")]
    cpus: usize,

    #[arg(short, long, default_value = "8192")]
    memory_mb: usize,

    #[arg(long, default_value = "3")]
    vsock_cid: u32,

    #[arg(long, default_value = "/tmp/crosvm_vsock.sock")]
    vsock_socket: PathBuf,

    #[arg(long, default_value = "8443")]
    webrtc_port: u16,

    #[arg(long, default_value = "false")]
    dry_run: bool,
}

#[tokio::main]
async fn main() -> Result<()> {
    tracing_subscriber::fmt()
        .with_env_filter(tracing_subscriber::EnvFilter::from_default_env())
        .init();

    let args = Args::parse();
    info!("Starting IndusBridge Enterprise Android Hypervisor Service");

    let router = VsockRouter::new(args.vsock_socket.clone());
    let active_routes = router.list_routes().await;
    info!("Initialized Vsock Router with {} high-throughput endpoints:", active_routes.len());
    for route in active_routes {
        info!("  [Port {}] {} -> {}", route.port, route.description, route.target_endpoint);
    }

    let mut config = VmmConfig::default();
    config.cpus = args.cpus;
    config.memory_mb = args.memory_mb;
    config.vsock_cid = args.vsock_cid;
    config.vsock_path = args.vsock_socket;
    config.webrtc_port = args.webrtc_port;

    let manager = CrosvmManager::new(config);

    if args.dry_run {
        let launch_cmd = manager.build_launch_command();
        info!("Dry-run mode: Crosvm command prepared: {:?}", launch_cmd);
        return Ok(());
    }

    info!("Hypervisor orchestrator ready. Awaiting CVD control plane signals.");
    Ok(())
}
