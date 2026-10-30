#![allow(dead_code, unused_variables, unused_imports)]

pub mod apdu_codec;
pub mod mod_a_wwan;
pub mod mod_b_pcsc;
pub mod mod_c_sdr;

use anyhow::Result;
use clap::Parser;
use tracing::info;
use mod_a_wwan::{PhysicalWwanModem, WwanConfig};
use mod_b_pcsc::PcscSimTunnel;
use mod_c_sdr::Sdr5gHarness;

#[derive(Parser, Debug)]
#[command(name = "cellular-bridge", about = "3-Mode Cellular & SIM Bridge Service for Android Micro-VM")]
struct Args {
    #[arg(short, long, default_value = "b")]
    mode: String,

    #[arg(long, default_value = "50051")]
    port: u16,

    #[arg(long, default_value = "sysmoSIMBANK-01")]
    sim_reader: String,
}

#[tokio::main]
async fn main() -> Result<()> {
    tracing_subscriber::fmt()
        .with_env_filter(tracing_subscriber::EnvFilter::from_default_env())
        .init();

    let args = Args::parse();
    info!("Starting IndusBridge Cellular & SIM Bridge on port {}", args.port);

    match args.mode.to_lowercase().as_str() {
        "a" | "wwan" => {
            info!("Activating Mode A: Physical WWAN Modem Passthrough (libqmi / libmbim)");
            let mut modem = PhysicalWwanModem::new(WwanConfig::default());
            modem.initialize()?;
            let (carrier, mcc, mnc, live) = modem.get_carrier_status();
            info!("Carrier: {}, MCC: {}, MNC: {}, Live: {}", carrier, mcc, mnc, live);
        }
        "b" | "pcsc" | "sim-bank" => {
            info!("Activating Mode B: PC/SC APDU SmartCard Bridge ({})", args.sim_reader);
            let tunnel = PcscSimTunnel::new(args.sim_reader);
            // Test query EF_DIR / MF
            let test_apdu = [0x00, 0xA4, 0x00, 0x04, 0x02, 0x3F, 0x00];
            let resp = tunnel.transmit_apdu(&test_apdu)?;
            info!(
                "PC/SC APDU test probe response: SW1=0x{:02X} SW2=0x{:02X} (Success: {})",
                resp.sw1, resp.sw2, resp.is_success()
            );
        }
        "c" | "sdr" => {
            info!("Activating Mode C: Software-Defined Radio (srsRAN 5G SA gNodeB)");
            let mut sdr = Sdr5gHarness::new("USRP B210", 3_500_000_000, 40);
            sdr.start_gnodeb()?;
        }
        _ => {
            info!("Operating in default multi-mode cellular routing daemon.");
        }
    }

    info!("Cellular Bridge Service listening on 0.0.0.0:{}", args.port);
    Ok(())
}
