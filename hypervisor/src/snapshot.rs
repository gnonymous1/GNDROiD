use anyhow::{Context, Result};
use std::path::PathBuf;
use std::process::Command;
use std::time::Instant;
use tracing::info;

pub struct SnapshotEngine {
    crosvm_socket: PathBuf,
    snapshot_dir: PathBuf,
}

impl SnapshotEngine {
    pub fn new(crosvm_socket: PathBuf, snapshot_dir: PathBuf) -> Self {
        Self {
            crosvm_socket,
            snapshot_dir,
        }
    }

    /// Takes a sub-500ms CoW memory & device state snapshot of the active micro-VM
    pub fn create_snapshot(&self, snapshot_name: &str) -> Result<PathBuf> {
        let start_time = Instant::now();
        std::fs::create_dir_all(&self.snapshot_dir)
            .context("Failed to create snapshot directory")?;

        let target_path = self.snapshot_dir.join(format!("{}.snap", snapshot_name));
        info!("Executing crosvm snapshot to: {}", target_path.display());

        let status = Command::new("crosvm")
            .arg("snapshot")
            .arg("take")
            .arg(&target_path)
            .arg(&self.crosvm_socket)
            .status();

        match status {
            Ok(s) if s.success() => {
                let duration = start_time.elapsed();
                info!(
                    "Snapshot '{}' completed successfully in {:.2}ms",
                    snapshot_name,
                    duration.as_secs_f64() * 1000.0
                );
                Ok(target_path)
            }
            Ok(s) => {
                anyhow::bail!("crosvm snapshot returned non-zero status: {:?}", s.code());
            }
            Err(e) => {
                Err(e).context("Failed to execute crosvm snapshot command")
            }
        }
    }

    /// Restores micro-VM execution state instantly from a previously captured snapshot
    pub fn restore_snapshot(&self, snapshot_name: &str) -> Result<()> {
        let start_time = Instant::now();
        let snap_path = self.snapshot_dir.join(format!("{}.snap", snapshot_name));
        info!("Restoring micro-VM state from: {}", snap_path.display());

        let status = Command::new("crosvm")
            .arg("snapshot")
            .arg("restore")
            .arg(&snap_path)
            .arg(&self.crosvm_socket)
            .status();

        match status {
            Ok(s) if s.success() => {
                let duration = start_time.elapsed();
                info!(
                    "Snapshot '{}' restored in {:.2}ms",
                    snapshot_name,
                    duration.as_secs_f64() * 1000.0
                );
                Ok(())
            }
            Ok(s) => {
                anyhow::bail!("crosvm snapshot restore failed: {:?}", s.code());
            }
            Err(e) => {
                Err(e).context("Failed to execute crosvm snapshot restore command")
            }
        }
    }
}
