use clap::{Parser, Subcommand};
use colored::*;
use std::env;
use std::path::{Path, PathBuf};
use std::process::Command;

#[cfg(windows)]
use std::os::windows::process::CommandExt;

const CREATE_NO_WINDOW: u32 = 0x08000000;
const DETACHED_PROCESS: u32 = 0x00000008;

#[derive(Parser)]
#[command(
    name = "gndroid",
    author = "Ghulam Nabi Kalhoro",
    version = "2.2.2",
    about = "GNDROiD — High-Performance Android Virtual Machine & Physical Phone Suite CLI",
    long_about = "Unified native CLI and process runner for GNDROiD. Replaces legacy batch scripts with zero-flash process launching, multi-device radar, and quick action subcommands."
)]
struct Cli {
    #[command(subcommand)]
    command: Option<Commands>,
}

#[derive(Subcommand)]
enum Commands {
    /// Launch the main Fluent Light GUI Controller (default when double-clicked)
    Gui,

    /// Launch a virtual machine instance or the main controller
    Launch {
        /// Optional AVD name to launch directly
        #[arg(short, long)]
        avd: Option<String>,
    },

    /// Start phone mirroring with docked companion sidebar
    Mirror {
        /// Optional target serial (USB or IP:Port)
        #[arg(short, long)]
        serial: Option<String>,
    },

    /// Open the Multi-Instance Manager for parallel clones and batch management
    Multi,

    /// Open ADB Doctor & Troubleshooting Suite
    Fix,

    /// Open Wireless LAN & Wi-Fi Mode directly (1-Click TCP/IP 5555 setup & Subnet Radar)
    #[command(alias = "wireless")]
    Lan,

    /// Open 1-Click Android OS System Image Downloader
    Download,

    /// Query and list connected physical phones, Wi-Fi devices, and running VMs
    Devices,

    /// Terminate zombie port 5037 blockers and restart ADB server
    Clean,

    /// Re-generate Windows desktop shortcuts pointing directly to gndroid.exe
    Shortcuts,
}

fn find_workspace_root() -> PathBuf {
    // 1. Try current executable's directory
    if let Ok(exe_path) = env::current_exe() {
        if let Some(dir) = exe_path.parent() {
            if dir.join("gndroid.pyw").exists() {
                return dir.to_path_buf();
            }
            if let Some(parent) = dir.parent() {
                if parent.join("gndroid.pyw").exists() {
                    return parent.to_path_buf();
                }
                if let Some(grandparent) = parent.parent() {
                    if grandparent.join("gndroid.pyw").exists() {
                        return grandparent.to_path_buf();
                    }
                }
            }
        }
    }

    // 2. Try current working directory
    if let Ok(cwd) = env::current_dir() {
        if cwd.join("gndroid.pyw").exists() {
            return cwd;
        }
    }

    // Fallback to default installation path
    PathBuf::from(r"c:\Users\Reader-Branch\Desktop\Android Emulator")
}

fn find_python_executable(gui: bool) -> String {
    let name = if gui { "pythonw.exe" } else { "python.exe" };

    let user_profile = env::var("USERPROFILE").unwrap_or_default();
    let candidates = [
        format!(r"{}\AppData\Local\Programs\Python\Python312\{}", user_profile, name),
        format!(r"{}\AppData\Local\Programs\Python\Python311\{}", user_profile, name),
        format!(r"{}\AppData\Local\Programs\Python\Python310\{}", user_profile, name),
        format!(r"{}\AppData\Local\Programs\Python\Python313\{}", user_profile, name),
        format!(r"C:\Program Files\Python312\{}", name),
        format!(r"C:\Program Files\Python311\{}", name),
        format!(r"C:\Program Files\Python310\{}", name),
        format!(r"C:\Program Files\Python313\{}", name),
    ];

    // Priority 1: Pick an installation that verified has PyQt6 installed
    for cand in &candidates {
        let p = Path::new(cand);
        if p.exists() {
            if let Some(parent) = p.parent() {
                if parent.join("Lib").join("site-packages").join("PyQt6").exists() {
                    return cand.clone();
                }
            }
        }
    }

    // Priority 2: Check active system PATH
    if let Ok(path_var) = env::var("PATH") {
        for dir in env::split_paths(&path_var) {
            let full = dir.join(name);
            if full.exists() {
                return full.to_string_lossy().to_string();
            }
        }
    }

    // Priority 3: Fallback to first existing candidate
    for cand in &candidates {
        if Path::new(cand).exists() {
            return cand.clone();
        }
    }

    name.to_string()
}

fn find_adb() -> String {
    let root = find_workspace_root();
    let candidates = [
        root.join("adb.exe"),
        root.join("dist").join("gndroid").join("adb.exe"),
        PathBuf::from(format!(
            r"{}\Android\Sdk\platform-tools\adb.exe",
            env::var("LOCALAPPDATA").unwrap_or_default()
        )),
    ];

    for cand in candidates {
        if cand.exists() {
            return cand.to_string_lossy().to_string();
        }
    }

    "adb".to_string()
}

fn launch_python_script(script_args: &[&str], silent: bool) -> anyhow::Result<()> {
    let root = find_workspace_root();
    let script_path = root.join("gndroid.pyw");

    if !script_path.exists() {
        anyhow::bail!("GNDROiD core script not found at {:?}", script_path);
    }

    let python = find_python_executable(true);
    let mut cmd = Command::new(&python);
    cmd.arg(&script_path);

    for arg in script_args {
        cmd.arg(arg);
    }

    cmd.current_dir(&root);

    #[cfg(windows)]
    {
        // DETACHED_PROCESS allows the child GUI process to detach and continue running
        // without flashing a console and without conflicting with CREATE_NO_WINDOW.
        cmd.creation_flags(DETACHED_PROCESS);
    }

    cmd.spawn()?;

    if !silent {
        println!("{}", "⚡ GNDROiD process spawned successfully in background.".green().bold());
    }

    Ok(())
}

fn ensure_adb_server() -> anyhow::Result<()> {
    if std::net::TcpStream::connect("127.0.0.1:5037").is_ok() {
        return Ok(());
    }

    let adb = find_adb();
    #[cfg(windows)]
    {
        let cmd_str = format!("Start-Process -FilePath '{}' -ArgumentList 'start-server' -WindowStyle Hidden", adb);
        let _ = Command::new("powershell")
            .args(["-NoProfile", "-WindowStyle", "Hidden", "-Command", &cmd_str])
            .creation_flags(CREATE_NO_WINDOW)
            .output();
    }
    #[cfg(not(windows))]
    {
        let _ = Command::new(&adb).arg("start-server").output();
    }

    // Wait up to 1.5 seconds for ADB server to respond on port 5037
    for _ in 0..15 {
        std::thread::sleep(std::time::Duration::from_millis(100));
        if std::net::TcpStream::connect("127.0.0.1:5037").is_ok() {
            break;
        }
    }
    Ok(())
}

fn cmd_devices() -> anyhow::Result<()> {
    let _ = ensure_adb_server();
    let adb = find_adb();
    println!("{}", "============================================================".cyan());
    println!("{}", "  GNDROiD — Connected Android Devices & Virtual Machines     ".bold().cyan());
    println!("{}", "============================================================".cyan());

    let output = Command::new(&adb)
        .arg("devices")
        .arg("-l")
        .output();

    match output {
        Ok(out) => {
            let stdout = String::from_utf8_lossy(&out.stdout);
            let lines: Vec<&str> = stdout.lines().collect();

            let mut count = 0;
            for line in lines.iter().skip(1) {
                let trimmed = line.trim();
                if trimmed.is_empty() {
                    continue;
                }

                let parts: Vec<&str> = trimmed.split_whitespace().collect();
                if parts.len() >= 2 {
                    let serial = parts[0];
                    let state = parts[1];
                    let extra = parts[2..].join(" ");

                    let dev_type = if serial.starts_with("emulator-") {
                        "🖥 Virtual Machine".magenta()
                    } else if serial.contains(':') {
                        "📶 Wireless Wi-Fi".blue()
                    } else {
                        "📱 Physical USB".green()
                    };

                    let status_badge = if state == "device" {
                        "🟢 ONLINE".green().bold()
                    } else if state == "unauthorized" {
                        "🟡 UNAUTHORIZED".yellow().bold()
                    } else {
                        "🔴 OFFLINE".red().bold()
                    };

                    println!("  {} | {:<22} | {:<16} | {}", status_badge, serial.bold(), dev_type, extra.dimmed());
                    count += 1;
                }
            }

            if count == 0 {
                println!("{}", "  No active Android devices or emulators detected.".yellow());
                println!("{}", "\n  Quick Actions:".bold());
                println!("    • Connect phone via USB cable and allow USB debugging");
                println!("    • Run '{}' to configure wireless Wi-Fi streaming", "gndroid fix".cyan());
                println!("    • Run '{}' to start a virtual machine clone", "gndroid multi".cyan());
            } else {
                println!("\n  Total active targets: {}", count.to_string().green().bold());
            }
        }
        Err(e) => {
            println!("{} Failed to query ADB: {}", "[-]".red(), e);
        }
    }

    println!("{}", "============================================================".cyan());
    Ok(())
}

fn cmd_clean() -> anyhow::Result<()> {
    let adb = find_adb();
    println!("{}", "Cleaning zombie ADB server processes and port 5037 conflicts...".yellow());

    // 1. Kill ADB server
    let _ = Command::new(&adb).arg("kill-server").output();

    #[cfg(windows)]
    {
        // 2. Kill tasklist conflicts on Windows
        let _ = Command::new("taskkill")
            .args(["/F", "/IM", "scrcpy.exe"])
            .creation_flags(CREATE_NO_WINDOW)
            .output();
    }

    // 3. Start fresh ADB server without handle inheritance hang
    let _ = ensure_adb_server();

    println!("{}", "✓ ADB server restarted cleanly on port 5037. All zombie blockers cleared.".green().bold());
    Ok(())
}

fn cmd_shortcuts() -> anyhow::Result<()> {
    println!("{}", "Refreshing GNDROiD desktop shortcuts...".cyan());
    let root = find_workspace_root();
    let script = root.join("gndroid.pyw");
    let python = find_python_executable(false);

    let status = Command::new(&python)
        .arg(&script)
        .arg("--install-shortcuts")
        .status()?;

    if status.success() {
        println!("{}", "✓ Desktop shortcuts (GNDROiD, GNDROiD Mirror, GNDROiD Multi-Instance) updated.".green().bold());
    } else {
        println!("{}", "[-] Shortcut generation completed.".yellow());
    }
    Ok(())
}

fn main() -> anyhow::Result<()> {
    let cli = Cli::parse();

    match cli.command {
        None => {
            // Default action (double click or bare 'gndroid'): Launch full GUI silently
            launch_python_script(&[], true)?;
        }
        Some(Commands::Gui) => {
            launch_python_script(&[], false)?;
        }
        Some(Commands::Launch { avd }) => {
            if let Some(name) = avd {
                launch_python_script(&["--avd", &name], false)?;
            } else {
                launch_python_script(&[], false)?;
            }
        }
        Some(Commands::Mirror { serial }) => {
            if let Some(s) = serial {
                launch_python_script(&["--mirror", &s], false)?;
            } else {
                launch_python_script(&["--mirror"], false)?;
            }
        }
        Some(Commands::Multi) => {
            launch_python_script(&["--multi"], false)?;
        }
        Some(Commands::Fix) => {
            launch_python_script(&["--adb-fixer"], false)?;
        }
        Some(Commands::Lan) => {
            launch_python_script(&["--lan"], false)?;
        }
        Some(Commands::Download) => {
            launch_python_script(&["--download-image"], false)?;
        }
        Some(Commands::Devices) => {
            cmd_devices()?;
        }
        Some(Commands::Clean) => {
            cmd_clean()?;
        }
        Some(Commands::Shortcuts) => {
            cmd_shortcuts()?;
        }
    }

    Ok(())
}
