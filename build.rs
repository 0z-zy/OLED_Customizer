fn main() {
    println!("cargo:rerun-if-changed=assets/app_icon.ico");
    println!("cargo:rerun-if-changed=assets/app_icon.png");

    let target_os = std::env::var("CARGO_CFG_TARGET_OS").unwrap_or_default();
    if target_os == "windows" {
        let icon_path = std::path::Path::new("assets/app_icon.ico");
        if icon_path.exists() {
            let mut res = winresource::WindowsResource::new();
            res.set_icon("assets/app_icon.ico");
            res.set("ProductName", "OLED Customizer");
            res.set("FileDescription", "OLED Customizer");
            res.set("FileVersion", "2.0.1.0");
            res.set("ProductVersion", "2.0.1");
            if let Err(e) = res.compile() {
                println!("cargo:warning=Could not embed Windows icon resource (rc.exe?): {e}");
            }
        }
    }
}
