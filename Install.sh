#!/data/data/com.termux/files/usr/bin/bash
# install.sh - ARK Mobile Mod Extractor installer for Termux
set -e

echo "=== ARK Mobile Mod Extractor Installer ==="

# Dependencies
pkg update -y
pkg install -y python rust git

# Install unoodle (pure Rust Oodle decoder)
if ! command -v unoodle >/dev/null 2>&1; then
    echo "[+] Installing unoodle (oozextract)..."
    cargo install oozextract --features cli || {
        echo "[!] cargo install failed, trying from source..."
        git clone --depth 1 https://github.com/lvlvllvlvllvlvl/oozextract.git /tmp/oozextract
        cd /tmp/oozextract
        cargo build --release --features cli
        mkdir -p ~/bin
        cp target/release/unoodle ~/bin/
        cd -
    }
fi

# Create command
mkdir -p ~/bin
cp arkmod.py ~/bin/arkmod
chmod +x ~/bin/arkmod

# Add to PATH if needed
if ! echo "$PATH" | grep -q "$HOME/bin"; then
    echo 'export PATH="$HOME/bin:$PATH"' >> ~/.bashrc
    echo "[+] Added ~/bin to PATH. Run: source ~/.bashrc"
fi

echo ""
echo "[OK] Install selesai."
echo "Gunakan: arkmod --help"
echo ""
echo "Catatan:"
echo "- Tool ini memakai retoc dan repak yang sudah kamu punya."
echo "- unoodle dipakai sebagai fallback Oodle murni."
echo "- Hasil ekstraksi belum dijamin bisa langsung jadi mod mobile."
