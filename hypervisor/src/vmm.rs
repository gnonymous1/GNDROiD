use anyhow::{Context, Result};
use std::path::PathBuf;
use std::process::{Child, Command, Stdio};
use tracing::{info, warn};

#[derive(Debug, Clone)]
pub struct VmmConfig {
    pub kernel_path: PathBuf,
    pub initrd_path: PathBuf,
    pub disk_path: PathBuf,
    pub cpus: usize,
    pub memory_mb: usize,
    pub vsock_cid: u32,
    pub vsock_path: PathBuf,
    pub shared_dir: PathBuf,
    pub gpu_enabled: bool,
    pub webrtc_port: u16,
    pub adb_port: u16,
}

impl Default for VmmConfig {
    fn default() -> Self {
        Self {
            kernel_path: PathBuf::from("artifacts/kernel/bzImage"),
            initrd_path: PathBuf::from("artifacts/initramfs.img"),
            disk_path: PathBuf::from("artifacts/system.raw"),
            cpus: 4,
            memory_mb: 8192,
            vsock_cid: 3,
            vsock_path: PathBuf::from("/tmp/crosvm_vsock.sock"),
            shared_dir: PathBuf::from("./shared_workspace"),
            gpu_enabled: true,
            webrtc_port: 8443,
            adb_port: 5555,
        }
    }
}

pub struct CrosvmManager {
    config: VmmConfig,
    child_process: Option<Child>,
}

impl CrosvmManager {
    pub fn new(config: VmmConfig) -> Self {
        Self {
            config,
            child_process: None,
        }
    }

    pub fn build_launch_command(&self) -> Command {
        let mut cmd = Command::new("crosvm");
        cmd.arg("run");

        // CPU & Memory Allocation
        cmd.arg("--cpus").arg(self.config.cpus.to_string());
        cmd.arg("--mem").arg(self.config.memory_mb.to_string());

        // Kernel & Root Filesystem
        cmd.arg("--kernel").arg(&self.config.kernel_path);
        cmd.arg("--initrd").arg(&self.config.initrd_path);
        cmd.arg("--rwdisk").arg(&self.config.disk_path);

        // High-Throughput VirtIO Vsock for IPC & Cellular APDU Tunneling
        cmd.arg("--vsock").arg(format!(
            "vhost={},path={}",
            self.config.vsock_cid,
            self.config.vsock_path.display()
        ));

        // virtio-fs Shared Filesystem for Real-Time Artifacts & Sync
        cmd.arg("--shared-dir").arg(format!(
            "{}:shared_workspace:type=fs:cache=always",
            self.config.shared_dir.display()
        ));

        // GPU Acceleration: Rutabaga / gfxstream forwarding Vulkan & GLES to Host
        if self.config.gpu_enabled {
            cmd.arg("--gpu").arg("backend=gfxstream,vulkan=true,gles=true");
            cmd.arg("--gpu-display").arg(format!("mode=webrtc,port={}", self.config.webrtc_port));
        }

        // VirtIO Multi-Touch Screen & Foldable Hinge Physics
        cmd.arg("--multi-touch").arg("width=1080,height=2400");
        cmd.arg("--serial").arg("type=stdout,hardware=virtio-console,console=true");

        // Synthetic net interface / TAP bridge
        cmd.arg("--net").arg("tap-name=crosvm_tap0");

        cmd.stdout(Stdio::piped()).stderr(Stdio::piped());
        cmd
    }

    pub fn start(&mut self) -> Result<()> {
        let mut cmd = self.build_launch_command();
        info!(
            "Launching crosvm micro-VM with CID {}, cpus={}, mem={}MB",
            self.config.vsock_cid, self.config.cpus, self.config.memory_mb
        );
        let child = cmd.spawn().context("Failed to spawn crosvm child process")?;
        self.child_process = Some(child);
        Ok(())
    }

    pub fn is_running(&mut self) -> bool {
        if let Some(child) = &mut self.child_process {
            match child.try_wait() {
                Ok(None) => true,
                Ok(Some(status)) => {
                    info!("crosvm process exited with status: {}", status);
                    false
                }
                Err(e) => {
                    warn!("Error checking crosvm status: {}", e);
                    false
                }
            }
        } else {
            false
        }
    }

    pub fn stop(&mut self) -> Result<()> {
        if let Some(mut child) = self.child_process.take() {
            info!("Sending termination signal to crosvm micro-VM...");
            let _ = child.kill();
            let _ = child.wait();
        }
        Ok(())
    }

    pub fn get_config(&self) -> &VmmConfig {
        &self.config
    }
}
