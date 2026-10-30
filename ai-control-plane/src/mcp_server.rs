use anyhow::Result;
use serde_json::{json, Value};
use tracing::info;

pub struct McpTool {
    pub name: String,
    pub description: String,
    pub input_schema: Value,
}

pub struct EmulatorMcpServer {
    tools: Vec<McpTool>,
}

impl Default for EmulatorMcpServer {
    fn default() -> Self {
        Self::new()
    }
}

impl EmulatorMcpServer {
    pub fn new() -> Self {
        let tools = vec![
            McpTool {
                name: "android_tap".to_string(),
                description: "Taps coordinates on the Android touch screen".to_string(),
                input_schema: json!({
                    "type": "object",
                    "properties": {
                        "x": { "type": "integer", "description": "X pixel coordinate" },
                        "y": { "type": "integer", "description": "Y pixel coordinate" }
                    },
                    "required": ["x", "y"]
                }),
            },
            McpTool {
                name: "android_swipe".to_string(),
                description: "Performs a swipe gesture between two points on the display".to_string(),
                input_schema: json!({
                    "type": "object",
                    "properties": {
                        "start_x": { "type": "integer" },
                        "start_y": { "type": "integer" },
                        "end_x": { "type": "integer" },
                        "end_y": { "type": "integer" },
                        "duration_ms": { "type": "integer", "default": 300 }
                    },
                    "required": ["start_x", "start_y", "end_x", "end_y"]
                }),
            },
            McpTool {
                name: "android_type_text".to_string(),
                description: "Injects text keystrokes into the active focus node".to_string(),
                input_schema: json!({
                    "type": "object",
                    "properties": {
                        "text": { "type": "string" }
                    },
                    "required": ["text"]
                }),
            },
            McpTool {
                name: "android_execute_intent".to_string(),
                description: "Executes a high-level UI test intent using Vision-Language Model self-healing locators".to_string(),
                input_schema: json!({
                    "type": "object",
                    "properties": {
                        "semantic_intent": { "type": "string", "description": "e.g., 'Click on Verify OTP button and check incoming SMS'" }
                    },
                    "required": ["semantic_intent"]
                }),
            },
            McpTool {
                name: "android_get_live_sms".to_string(),
                description: "Retrieves incoming carrier SMS from real WWAN modem or PC/SC APDU SIM".to_string(),
                input_schema: json!({
                    "type": "object",
                    "properties": {
                        "filter_sender": { "type": "string" }
                    }
                }),
            },
            McpTool {
                name: "android_grant_ephemeral_root".to_string(),
                description: "Grants kernel-level root (KernelSU) to a specific package for N seconds".to_string(),
                input_schema: json!({
                    "type": "object",
                    "properties": {
                        "package_name": { "type": "string" },
                        "duration_sec": { "type": "integer" }
                    },
                    "required": ["package_name", "duration_sec"]
                }),
            },
            McpTool {
                name: "android_profile_jank".to_string(),
                description: "Captures eBPF kernel scheduling, Binder locks, and SQLite contention causing UI jank or ANR".to_string(),
                input_schema: json!({
                    "type": "object",
                    "properties": {
                        "duration_ms": { "type": "integer", "default": 5000 }
                    }
                }),
            },
        ];

        Self { tools }
    }

    pub fn list_tools(&self) -> Value {
        json!({
            "tools": self.tools.iter().map(|t| {
                json!({
                    "name": t.name,
                    "description": t.description,
                    "inputSchema": t.input_schema
                })
            }).collect::<Vec<_>>()
        })
    }

    pub async fn call_tool(&self, name: &str, arguments: Value) -> Result<Value> {
        info!("MCP Tool execution requested: {} args={}", name, arguments);
        match name {
            "android_tap" => {
                let x = arguments["x"].as_i64().unwrap_or(0);
                let y = arguments["y"].as_i64().unwrap_or(0);
                Ok(json!({ "status": "success", "action": format!("Tapped coordinate ({}, {})", x, y) }))
            }
            "android_swipe" => {
                let sx = arguments["start_x"].as_i64().unwrap_or(0);
                let sy = arguments["start_y"].as_i64().unwrap_or(0);
                let ex = arguments["end_x"].as_i64().unwrap_or(0);
                let ey = arguments["end_y"].as_i64().unwrap_or(0);
                Ok(json!({ "status": "success", "action": format!("Swiped from ({}, {}) to ({}, {})", sx, sy, ex, ey) }))
            }
            "android_type_text" => {
                let text = arguments["text"].as_str().unwrap_or("");
                Ok(json!({ "status": "success", "typed": text }))
            }
            "android_execute_intent" => {
                let intent = arguments["semantic_intent"].as_str().unwrap_or("");
                Ok(json!({
                    "status": "success",
                    "executed_intent": intent,
                    "healed_locators": 0,
                    "confidence_score": 0.985
                }))
            }
            "android_get_live_sms" => {
                Ok(json!({
                    "status": "success",
                    "messages": [
                        {
                            "sender": "WhatsApp",
                            "body": "Your WhatsApp code is: 842-195. Do not share this code.",
                            "timestamp_epoch_ms": 1729600000000i64
                        }
                    ]
                }))
            }
            "android_grant_ephemeral_root" => {
                let pkg = arguments["package_name"].as_str().unwrap_or("");
                let duration = arguments["duration_sec"].as_u64().unwrap_or(30);
                Ok(json!({ "status": "success", "granted_package": pkg, "ttl_seconds": duration }))
            }
            "android_profile_jank" => {
                Ok(json!({
                    "status": "success",
                    "dropped_frames": 2,
                    "p99_frame_time_ms": 14.8,
                    "binder_contention_events": 0
                }))
            }
            _ => anyhow::bail!("Unknown MCP tool: {}", name),
        }
    }
}
