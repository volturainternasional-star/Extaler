#!/data/data/com.termux/files/usr/bin/python3
"""
ARK Mobile Mod Extractor & Converter
Orchestrator untuk ekstrak mod ARK Survival Ascended di Termux.

Menggunakan:
- retoc  (sudah ada di ~/retoc/target/release/retoc)
- repak  (sudah ada di ~/repak/target/release/repak)
- unoodle (oozextract, pure Rust Oodle)

Tidak memakai dlopen(libUE4.so).
"""

import argparse
import os
import sys
import subprocess
import shutil
from pathlib import Path
from datetime import datetime

# Paths
RETOC = os.path.expanduser("~/retoc/target/release/retoc")
REPAK = os.path.expanduser("~/repak/target/release/repak")
UNOODLE = "unoodle"

SPYGLASS_DIR = os.path.expanduser("~/ark-mods/inspection/spyglass/AwesomeSpyglass/Content/Paks/WindowsServer")
FIELD_DIR = os.path.expanduser("~/ark-mods/inspection/field/FieldGenerators/Content/Paks/WindowsServer")

EXTRACTED_BASE = os.path.expanduser("~/ark-mods/extracted")

def log(msg, level="INFO"):
    ts = datetime.now().strftime("%H:%M:%S")
    print(f"[{ts}] [{level}] {msg}")

def run(cmd, cwd=None):
    log(f"Menjalankan: {' '.join(cmd)}")
    try:
        result = subprocess.run(cmd, cwd=cwd, capture_output=True, text=True, timeout=3600)
        if result.returncode != 0:
            log(f"Error: {result.stderr.strip()}", "ERROR")
            return False, result.stderr
        if result.stdout:
            print(result.stdout)
        return True, result.stdout
    except Exception as e:
        log(f"Exception: {e}", "ERROR")
        return False, str(e)

def check_tools():
    missing = []
    if not os.path.exists(RETOC):
        missing.append(f"retoc tidak ditemukan di {RETOC}")
    if not os.path.exists(REPAK):
        missing.append(f"repak tidak ditemukan di {REPAK}")
    if missing:
        for m in missing:
            log(m, "ERROR")
        log("Pastikan retoc dan repak sudah di-build.", "ERROR")
        return False
    return True

def extract_iostore(input_dir, output_dir, name):
    """Extract IoStore (.utoc/.ucas) using retoc to-legacy."""
    log(f"Ekstrak IoStore: {name}")
    os.makedirs(output_dir, exist_ok=True)
    
    # Coba to-legacy
    cmd = [RETOC, "to-legacy", input_dir, output_dir, "--no-shaders"]
    ok, out = run(cmd)
    if ok:
        log(f"Berhasil extract {name} ke {output_dir}")
        return True
    
    log(f"to-legacy gagal untuk {name}. Coba unpack biasa...", "WARN")
    cmd = [RETOC, "unpack", input_dir, "--output", output_dir]
    ok, out = run(cmd)
    if ok:
        log(f"Unpack berhasil untuk {name}")
        return True
    
    log(f"Gagal extract {name}. Cek log di atas.", "ERROR")
    return False

def extract_pak(pak_file, output_dir, name):
    """Extract classic .pak using repak."""
    log(f"Ekstrak PAK: {name}")
    os.makedirs(output_dir, exist_ok=True)
    cmd = [REPAK, "unpack", pak_file, "--output", output_dir]
    ok, out = run(cmd)
    if ok:
        log(f"repak unpack berhasil untuk {name}")
        return True
    log(f"repak unpack gagal (kemungkinan Oodle). {name} mungkin butuh unoodle manual.", "WARN")
    return False

def analyze_compatibility(extracted_dir):
    """Analisis sederhana kompatibilitas dengan ARK Mobile."""
    log("Analisis kompatibilitas (sederhana):")
    uassets = list(Path(extracted_dir).rglob("*.uasset"))
    log(f"  Jumlah .uasset: {len(uassets)}")
    log("  Catatan: Asset PC (WindowsServer) TIDAK otomatis kompatibel dengan ARK Ultimate Mobile.")
    log("  Perbedaan: UE version, platform, cooking, Blueprint, dependency, compression.")
    log("  Jangan anggap hasil ini sebagai mod mobile yang siap pakai.")

def process_mod(name, input_dir, output_subdir):
    output_dir = os.path.join(EXTRACTED_BASE, output_subdir)
    log(f"=== Memproses {name} ===")
    log(f"Input : {input_dir}")
    log(f"Output: {output_dir}")
    
    if not os.path.isdir(input_dir):
        log(f"Direktori tidak ditemukan: {input_dir}", "ERROR")
        return False
    
    # Deteksi format
    files = os.listdir(input_dir)
    has_utoc = any(f.endswith(".utoc") for f in files)
    has_pak = any(f.endswith(".pak") for f in files)
    
    success = False
    if has_utoc:
        success = extract_iostore(input_dir, output_dir, name)
    elif has_pak:
        # Ambil pak pertama
        pak = next(f for f in files if f.endswith(".pak"))
        success = extract_pak(os.path.join(input_dir, pak), output_dir, name)
    else:
        log("Tidak ditemukan .utoc atau .pak", "ERROR")
        return False
    
    if success:
        analyze_compatibility(output_dir)
    return success

def main():
    parser = argparse.ArgumentParser(description="ARK Mobile Mod Extractor & Converter")
    parser.add_argument("command", choices=["extract", "list", "check"], help="Perintah")
    parser.add_argument("--mod", choices=["spyglass", "field", "both"], default="both")
    args = parser.parse_args()
    
    if not check_tools():
        sys.exit(1)
    
    if args.command == "check":
        log("Tool check OK")
        log(f"retoc : {RETOC}")
        log(f"repak : {REPAK}")
        sys.exit(0)
    
    if args.command == "list":
        for name, path in [("Spyglass", SPYGLASS_DIR), ("Field", FIELD_DIR)]:
            if os.path.isdir(path):
                log(f"{name}:")
                for f in sorted(os.listdir(path)):
                    print(f"  {f}")
            else:
                log(f"{name}: direktori tidak ada", "WARN")
        sys.exit(0)
    
    # extract
    results = []
    if args.mod in ("spyglass", "both"):
        results.append(process_mod("Awesome Spyglass", SPYGLASS_DIR, "spyglass"))
    if args.mod in ("field", "both"):
        results.append(process_mod("Field Generators", FIELD_DIR, "field"))
    
    log("=== Selesai ===")
    if all(results):
        log("Semua mod berhasil diekstrak.")
    else:
        log("Ada yang gagal. Cek log di atas.", "WARN")
    
    log("Hasil ada di:")
    log(f"  {EXTRACTED_BASE}/spyglass/")
    log(f"  {EXTRACTED_BASE}/field/")
    log("")
    log("PENTING: Hasil ekstraksi adalah asset PC. Belum siap jadi mod mobile.")
    log("Langkah selanjutnya butuh analisis manual + cooking ulang di UE Android.")

if __name__ == "__main__":
    main()
