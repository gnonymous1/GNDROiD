#![allow(unused_mut, dead_code, unused_variables, unused_imports)]

pub mod crash_analyzer;
pub mod ebpf_tracer;
pub mod mcp_server;
pub mod shm_framebuffer;
pub mod vlm_agent;

use anyhow::Result;
use clap::Parser;
use mcp_server::EmulatorMcpServer;
use std::path::PathBuf;
use std::time::Duration;
use tracing::info;

#[derive(Parser, Debug)]
#[command(name = "ai-control-plane", about = "AI-Native Emulator Control Plane & MCP Server")]
struct Args {
    #[arg(long, default_value = "50052")]
    grpc_port: u16,

    #[arg(long, default_value = "/dev/shm/crosvm_gpu_prime_buf")]
    shm_path: PathBuf,

    #[arg(long, default_value = "gemini-2.5-flash")]
    vlm_model: String,
}

#[tokio::main]
async fn main() -> Result<()> {
    tracing_subscriber::fmt()
        .with_env_filter(tracing_subscriber::EnvFilter::from_default_env())
        .init();

    let args = Args::parse();
    info!("Starting IndusBridge AI Control Plane on port {}", args.grpc_port);

    let mcp = EmulatorMcpServer::new();
    let tools = mcp.list_tools();
    info!("Initialized Model Context Protocol (MCP) server with tools:");
    if let Some(arr) = tools["tools"].as_array() {
        for t in arr {
            info!("  - {} : {}", t["name"].as_str().unwrap_or(""), t["description"].as_str().unwrap_or(""));
        }
    }

    let fb = shm_framebuffer::ShmFramebufferReader::new(args.shm_path, 1080, 2400);
    info!(
        "Configured Zero-Copy Framebuffer Reader: {}x{} stride={}",
        fb.get_dimensions().width,
        fb.get_dimensions().height,
        fb.get_dimensions().stride
    );

    let vlm = vlm_agent::VlmSelfHealingLocator::new(&args.vlm_model);
    let resolved = vlm.resolve_locator("Click on WhatsApp Continue button", &[], None).await?;
    info!(
        "VLM locator test: Target='{}' at ({}, {}) [Confidence: {:.2}]",
        resolved.target_label, resolved.center_x, resolved.center_y, resolved.confidence
    );

    let report = ebpf_tracer::EbpfCausalityTracer::profile_session(Duration::from_millis(50)).await?;
    info!("Causality tracer report: {}", report.root_cause_diagnosis);

    info!("AI Control Plane ready. Awaiting gRPC & MCP agent connections.");
    Ok(())
}
