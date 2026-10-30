use cellular_bridge::apdu_codec::{ApduCommand, ApduResponse};
use cellular_bridge::mod_b_pcsc::PcscSimTunnel;

#[test]
fn test_apdu_milenage_auth_roundtrip() {
    let tunnel = PcscSimTunnel::new("sysmoSIMBANK-Slot03".to_string());
    
    // ISO 7816-4 INTERNAL AUTHENTICATE command with RAND (16 bytes) + AUTN (16 bytes)
    let mut auth_cmd = vec![0x00, 0x88, 0x00, 0x81, 0x22, 0x10];
    let rand = [0x11u8; 16];
    auth_cmd.extend_from_slice(&rand);
    auth_cmd.push(0x10); // AUTN length
    let autn = [0x22u8; 16];
    auth_cmd.extend_from_slice(&autn);

    let resp = tunnel.transmit_apdu(&auth_cmd).expect("APDU transmission should succeed");
    assert_eq!(resp.sw1, 0x90);
    assert_eq!(resp.sw2, 0x00);
    assert!(resp.is_success());
    assert!(!resp.data.is_empty(), "Milenage crypto payload must be returned");
}

#[test]
fn test_apdu_select_usim_application() {
    let tunnel = PcscSimTunnel::new("test-card".to_string());
    // SELECT USIM AID: 00 A4 04 00 10 A0 00 00 00 87 10 02 FF 86 FF 03 89 FF FF FF FF
    let select_aid = [
        0x00, 0xA4, 0x04, 0x00, 0x10,
        0xA0, 0x00, 0x00, 0x00, 0x87, 0x10, 0x02, 0xFF, 0x86, 0xFF, 0x03, 0x89, 0xFF, 0xFF, 0xFF, 0xFF
    ];
    let resp = tunnel.transmit_apdu(&select_aid).expect("SELECT AID should succeed");
    assert_eq!(resp.sw1, 0x90);
    assert_eq!(resp.sw2, 0x00);
}
