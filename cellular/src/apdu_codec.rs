use anyhow::{bail, Result};

#[derive(Debug, Clone, PartialEq, Eq)]
pub enum ApduCase {
    Case1, // CLA INS P1 P2 (4 bytes)
    Case2Short(u8), // CLA INS P1 P2 Le (5 bytes)
    Case3Short(Vec<u8>), // CLA INS P1 P2 Lc Data
    Case4Short(Vec<u8>, u8), // CLA INS P1 P2 Lc Data Le
}

#[derive(Debug, Clone, PartialEq, Eq)]
pub struct ApduCommand {
    pub cla: u8,
    pub ins: u8,
    pub p1: u8,
    pub p2: u8,
    pub data: Vec<u8>,
    pub le: Option<u16>,
}

#[derive(Debug, Clone, PartialEq, Eq)]
pub struct ApduResponse {
    pub data: Vec<u8>,
    pub sw1: u8,
    pub sw2: u8,
}

impl ApduCommand {
    pub fn parse(raw: &[u8]) -> Result<Self> {
        if raw.len() < 4 {
            bail!("APDU raw length must be at least 4 bytes, got {}", raw.len());
        }

        let cla = raw[0];
        let ins = raw[1];
        let p1 = raw[2];
        let p2 = raw[3];

        if raw.len() == 4 {
            return Ok(Self {
                cla,
                ins,
                p1,
                p2,
                data: Vec::new(),
                le: None,
            });
        }

        let b4 = raw[4];
        if raw.len() == 5 {
            // Case 2: Le only
            let le = if b4 == 0 { 256 } else { b4 as u16 };
            return Ok(Self {
                cla,
                ins,
                p1,
                p2,
                data: Vec::new(),
                le: Some(le),
            });
        }

        // Case 3 or 4: b4 is Lc
        let lc = b4 as usize;
        if raw.len() < 5 + lc {
            bail!("APDU data underflow: expected {} data bytes, got {}", lc, raw.len() - 5);
        }

        let data = raw[5..5 + lc].to_vec();
        let remaining = &raw[5 + lc..];

        let le = if remaining.is_empty() {
            None
        } else if remaining.len() == 1 {
            let val = remaining[0];
            Some(if val == 0 { 256 } else { val as u16 })
        } else {
            None
        };

        Ok(Self {
            cla,
            ins,
            p1,
            p2,
            data,
            le,
        })
    }

    pub fn to_bytes(&self) -> Vec<u8> {
        let mut out = vec![self.cla, self.ins, self.p1, self.p2];
        if !self.data.is_empty() {
            out.push(self.data.len() as u8);
            out.extend_from_slice(&self.data);
        }
        if let Some(le) = self.le {
            out.push((le & 0xFF) as u8);
        }
        out
    }
}

impl ApduResponse {
    pub fn new(data: Vec<u8>, sw1: u8, sw2: u8) -> Self {
        Self { data, sw1, sw2 }
    }

    pub fn is_success(&self) -> bool {
        self.sw1 == 0x90 && self.sw2 == 0x00
    }

    pub fn to_bytes(&self) -> Vec<u8> {
        let mut out = self.data.clone();
        out.push(self.sw1);
        out.push(self.sw2);
        out
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn test_parse_select_master_file() {
        // SELECT MF: 00 A4 00 0C 02 3F 00
        let raw = [0x00, 0xA4, 0x00, 0x0C, 0x02, 0x3F, 0x00];
        let cmd = ApduCommand::parse(&raw).unwrap();
        assert_eq!(cmd.cla, 0x00);
        assert_eq!(cmd.ins, 0xA4);
        assert_eq!(cmd.p1, 0x00);
        assert_eq!(cmd.p2, 0x0C);
        assert_eq!(cmd.data, vec![0x3F, 0x00]);
        assert_eq!(cmd.le, None);
    }

    #[test]
    fn test_parse_get_response() {
        // GET RESPONSE: 00 C0 00 00 19
        let raw = [0x00, 0xC0, 0x00, 0x00, 0x19];
        let cmd = ApduCommand::parse(&raw).unwrap();
        assert_eq!(cmd.cla, 0x00);
        assert_eq!(cmd.ins, 0xC0);
        assert_eq!(cmd.le, Some(0x19));
    }
}
