import os
import shutil
import subprocess
import sys

def main():
    print("====================================================")
    print("         RTK Installation Helper Script")
    print("====================================================")
    
    # 1. Check if rtk is already installed
    rtk_path = shutil.which("rtk") or shutil.which("rtk.exe")
    if rtk_path:
        print(f"rtk is already installed at: {rtk_path}")
        return

    # 2. Check for Cargo
    cargo_path = shutil.which("cargo")
    if cargo_path:
        print("Rust Cargo detected. Attempting to build and install rtk...")
        try:
            # Run cargo install rtk
            res = subprocess.run(["cargo", "install", "rtk"], capture_output=True, text=True)
            if res.returncode == 0:
                print("[SUCCESS] rtk successfully installed via Cargo!")
                return
            else:
                print(f"[WARNING] cargo install failed: {res.stderr}")
        except Exception as e:
            print(f"[WARNING] Failed to run cargo command: {e}")
            
    # 3. Fallback instructions
    print("\nCould not automatically install rtk.")
    print("To install rtk manually, please:")
    print("1. Ensure Rust & Cargo is installed (https://rustup.rs/)")
    print("2. Run the command: cargo install rtk")
    print("3. Ensure the cargo bin folder (usually ~/.cargo/bin or %USERPROFILE%\\.cargo\\bin) is in your system PATH.")
    print("====================================================")

if __name__ == "__main__":
    main()
