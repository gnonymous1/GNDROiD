fn main() -> Result<(), Box<dyn std::error::Error>> {
    println!("cargo:rerun-if-changed=proto/cellular_bridge.proto");
    
    // Attempt protobuf compilation if protoc is found
    if std::process::Command::new("protoc").arg("--version").output().is_ok() {
        tonic_build::compile_protos("proto/cellular_bridge.proto")?;
    } else {
        println!("cargo:warning=protoc not found in PATH; skipping tonic code generation during offline host check");
    }
    Ok(())
}
