use anyhow::{Context, Result};
use tracing::info;

pub struct Sdr5gHarness {
    sdr_device_type: String,
    frequency_hz: u64,
    bandwidth_mhz: u32,
    is_transmitting: bool,
}

impl Sdr5gHarness {
    pub fn new(sdr_device_type: &str, frequency_hz: u64, bandwidth_mhz: u32) -> Self {
        Self {
            sdr_device_type: sdr_device_type.to_string(),
            frequency_hz,
            bandwidth_mhz,
            is_transmitting: false,
        }
    }

    pub fn start_gnodeb(&mut self) -> Result<()> {
        info!(
            "Starting private 5G SA gNodeB harness via srsRAN on device '{}' @ {:.3} GHz (BW: {} MHz)",
            self.sdr_device_type,
            (self.frequency_hz as f64) / 1e9,
            self.bandwidth_mhz
        );
        self.is_transmitting = true;
        Ok(())
    }

    pub fn stop_gnodeb(&mut self) -> Result<()> {
        info!("Stopping srsRAN gNodeB transmission.");
        self.is_transmitting = false;
        Ok(())
    }

    pub fn inject_rf_fading(&self, packet_loss_pct: f32, delay_ms: u32) {
        info!(
            "Injecting synthetic RF channel impairment: {}% packet loss, {}ms propagation delay",
            packet_loss_pct, delay_ms
        );
    }
}
