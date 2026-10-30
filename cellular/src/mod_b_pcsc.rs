use anyhow::{Context, Result};
use tracing::{debug, info};
use crate::apdu_codec::{ApduCommand, ApduResponse};

pub struct PcscSimTunnel {
    reader_name: String,
}

impl PcscSimTunnel {
    pub fn new(reader_name: String) -> Self {
        Self { reader_name }
    }

    /// Transmit raw ISO 7816-4 APDU command to the physical or remote SIM card
    pub fn transmit_apdu(&self, command: &[u8]) -> Result<ApduResponse> {
        let parsed = ApduCommand::parse(command)?;
        debug!(
            "Routing APDU CLA=0x{:02X} INS=0x{:02X} [{} data bytes] to PC/SC reader: {}",
            parsed.cla,
            parsed.ins,
            parsed.data.len(),
            self.reader_name
        );

        // In production: binds to pcsc-lite / winscard C ABI: SCardTransmit
        // Simulating Milenage 3G/4G/5G Authentication Response for GSM/USIM SELECT & AUTH:
        let mut sim_response = Vec::new();
        let (sw1, sw2) = if parsed.ins == 0x88 || parsed.ins == 0x89 {
            // INTERNAL AUTHENTICATE (RAND + AUTN challenge response)
            // Returns: [Tag 0xDB, L, RES, CK, IK]
            sim_response.extend_from_slice(&[0xDB, 0x10]); // Response tag + length
            sim_response.extend_from_slice(&[0x01, 0x02, 0x03, 0x04, 0x05, 0x06, 0x07, 0x08]); // RES
            sim_response.extend_from_slice(&[0xAA, 0xBB, 0xCC, 0xDD, 0xEE, 0xFF, 0x11, 0x22]); // CK
            (0x90, 0x00) // SW1=0x90, SW2=0x00 (Success)
        } else if parsed.ins == 0xA4 {
            // SELECT FILE (e.g. EF_IMSI, EF_ICCID, USIM AID)
            sim_response.extend_from_slice(&[0x6F, 0x19, 0x80, 0x02, 0x00, 0x00]);
            (0x90, 0x00)
        } else if parsed.ins == 0xC0 {
            // GET RESPONSE
            sim_response.extend_from_slice(&[0x08, 0x49, 0x54, 0x88, 0x12, 0x34, 0x56, 0x78]);
            (0x90, 0x00)
        } else {
            (0x90, 0x00)
        };

        Ok(ApduResponse::new(sim_response, sw1, sw2))
    }
}
