#!/data/data/com.termux/files/usr/bin/python3
"""
ARK Mobile Mod Extractor & Converter
Pipeline:
1. Retoc membaca index .utoc.
2. Tool mengambil compressed chunk dari .ucas (via unpack-raw + parse TOC).
3. Unoodle mendekompresi blok Oodle dengan ukuran exact dari TOC.
4. Retoc memproses kembali data package (to-legacy / unpack).

Catatan:
- Unoodle tidak otomatis dekompresi seluruh .ucas.
- File original tidak pernah diubah.
- Hasil adalah asset PC (WindowsServer).
"""

import argparse
import os
import sys
import subprocess
import shutil
import tempfile
import struct
from pathlib import Path
from datetime import datetime

RETOC = os.path.expanduser("\~/retoc/target/release/retoc")
REPAK = os.path.expanduser("\~/repak/target/release/repak")
UNOODLE = "unoodle"

SPYGLASS_DIR = os.path.expanduser("\~/ark-mods/inspection/spyglass/AwesomeSpyglass/Content/Paks/WindowsServer")
FIELD_DIR = os.path.expanduser("\~/ark-mods/inspection/field/FieldGenerators/Content/Paks/WindowsServer")
EXTRACTED_BASE = os.path.expanduser("\~/ark-mods/extracted")

def log(msg, level="INFO"):
    ts = datetime.now().strftime("%H:%M:%S")
    print(f"[{ts}] [{level}] {msg}")

def run(cmd, cwd=None, timeout=3600):
    log(f"Menjalankan: {' '.join(cmd)}")
    try:
        result = subprocess.run(cmd, cwd=cwd, capture_output=True, text=True, timeout=timeout)
        if result.returncode != 0:
            err = (result.stderr or result.stdout or "").strip()
            log(f"Error (code {result.returncode}): {err[:800]}", "ERROR")
            return False, err
        if result.stdout:
            print(result.stdout)
        return True, result.stdout
    except subprocess.TimeoutExpired:
        log("Timeout", "ERROR")
        return False, "timeout"
    except Exception as e:
        log(f"Exception: {e}", "ERROR")
        return False, str(e)

def check_tools():
    missing = []
    if not os.path.exists(RETOC):
        missing.append(f"retoc tidak ditemukan di {RETOC}")
    if not os.path.exists(REPAK):
        missing.append(f"repak tidak ditemukan di {REPAK}")
    if shutil.which(UNOODLE) is None and not os.path.exists(os.path.expanduser("\~/bin/unoodle")):
        log("unoodle tidak ditemukan di PATH. Fallback Oodle akan terbatas.", "WARN")
    if missing:
        for m in missing:
            log(m, "ERROR")
        return False
    return True

def find_utoc(input_dir):
    for f in sorted(os.listdir(input_dir)):
        if f.endswith(".utoc"):
            return os.path.join(input_dir, f)
    return None

def find_ucas(utoc_path):
    base = utoc_path[:-5]
    for ext in (".ucas", ".UCAS"):
        p = base + ext
        if os.path.exists(p):
            return p
    return None

def parse_toc_compression_blocks(utoc_path):
    """Baca FIoStoreTocCompressedBlockEntry dari .utoc."""
    try:
        with open(utoc_path, "rb") as f:
            data = f.read()
    except Exception as e:
        log(f"Gagal baca .utoc: {e}", "ERROR")
        return None

    if len(data) < 144 or data[:16] != b"-==--==--==--==-":
        log("Magic .utoc tidak cocok atau file terlalu kecil", "WARN")
        return None

    version = data[16]
    toc_header_size = struct.unpack_from("<I", data, 20)[0]
    entry_count = struct.unpack_from("<I", data, 24)[0]
    compressed_block_count = struct.unpack_from("<I", data, 28)[0]
    compressed_block_entry_size = struct.unpack_from("<I", data, 32)[0]

    log(f"TOC: version={version}, entries={entry_count}, "
        f"comp_blocks={compressed_block_count}, block_entry_size={compressed_block_entry_size}")

    if compressed_block_entry_size != 12 or compressed_block_count == 0:
        log("Tidak ada compression block yang bisa diparse", "WARN")
        return []

    base = toc_header_size
    base += 12 * entry_count   # FIoChunkId
    base += 10 * entry_count   # FIoOffsetAndLength

    blocks = []
    if base + 12 * compressed_block_count <= len(data):
        for i in range(compressed_block_count):
            off = base + i * 12
            raw = data[off:off+12]
            if len(raw) < 12:
                break
            offset_comp = struct.unpack_from("<Q", raw, 0)[0]
            uncomp_method = struct.unpack_from("<I", raw, 8)[0]

            offset = offset_comp & ((1 << 40) - 1)
            compressed_size = (offset_comp >> 40) & ((1 << 24) - 1)
            uncompressed_size = uncomp_method & ((1 << 24) - 1)
            method = (uncomp_method >> 24) & 0xFF

            blocks.append({
                "offset": offset,
                "compressed_size": compressed_size,
                "uncompressed_size": uncompressed_size,
                "method": method,
            })

    if blocks:
        log(f"Berhasil parse {len(blocks)} compression blocks dari TOC")
        for b in blocks[:3]:
            log(f"  sample: off={b['offset']} csize={b['compressed_size']} "
                f"usize={b['uncompressed_size']} method={b['method']}")
        return blocks

    log("Gagal parse compression blocks dari TOC", "WARN")
    return None

def extract_and_decompress_blocks(ucas_path, output_dir, blocks):
    """Ambil blok tepat dari .ucas sesuai TOC, dekompresi dengan unoodle exact size."""
    if not blocks or not ucas_path or not os.path.exists(ucas_path):
        return False

    os.makedirs(output_dir, exist_ok=True)
    uno = shutil.which(UNOODLE) or os.path.expanduser("\~/bin/unoodle")
    if not os.path.exists(uno):
        log("unoodle tidak tersedia", "WARN")
        return False
    if shutil.which(UNOODLE):
        uno = UNOODLE

    success = 0
    with open(ucas_path, "rb") as ucas:
        for i, b in enumerate(blocks):
            if b["compressed_size"] == 0 or b["uncompressed_size"] == 0 or b["method"] == 0:
                continue

            try:
                ucas.seek(b["offset"])
                compressed = ucas.read(b["compressed_size"])
            except Exception as e:
                log(f"Gagal baca blok {i}: {e}", "WARN")
                continue

            if len(compressed) != b["compressed_size"]:
                continue

            tmp_in = os.path.join(output_dir, f"block_{i:06d}.comp")
            tmp_out = os.path.join(output_dir, f"block_{i:06d}.bin")
            with open(tmp_in, "wb") as f:
                f.write(compressed)

            cmd = [
                uno,
                "--length", str(b["uncompressed_size"]),
                "--header", "0",
                tmp_in,
                "-o", tmp_out,
                "-v",
            ]
            ok, _ = run(cmd, timeout=60)
            if ok and os.path.exists(tmp_out) and os.path.getsize(tmp_out) > 0:
                actual = os.path.getsize(tmp_out)
                if actual == b["uncompressed_size"]:
                    log(f"Blok {i}: Unoodle OK (exact size match {actual})")
                    success += 1
                else:
                    log(f"Blok {i}: Unoodle OK tapi ukuran tidak cocok "
                        f"(dapat {actual}, diharapkan {b['uncompressed_size']}) — TIDAK divalidasi", "WARN")
            else:
                log(f"Blok {i}: Unoodle gagal (method={b['method']}, usize={b['uncompressed_size']})", "WARN")

            if os.path.exists(tmp_in):
                os.remove(tmp_in)

    log(f"Dekompresi blok akurat selesai: {success}/{len(blocks)}")
    return success > 0

def retoc_read_index(utoc_path):
    log(f"Retoc membaca index: {os.path.basename(utoc_path)}")
    ok_info, _ = run([RETOC, "info", utoc_path])
    ok_list, _ = run([RETOC, "list", utoc_path])
    return ok_info or ok_list

def extract_raw_chunks(utoc_path, raw_out_dir):
    os.makedirs(raw_out_dir, exist_ok=True)
    log(f"Ambil raw chunks ke {raw_out_dir}")
    for extra in [[], ["--override-container-header-version", "PreInitial"]]:
        cmd = [RETOC] + extra + ["unpack-raw", utoc_path, raw_out_dir]
        ok, _ = run(cmd)
        if ok:
            log("unpack-raw berhasil")
            return True
    log("unpack-raw gagal", "WARN")
    return False

def retoc_process_packages(input_for_retoc, final_out_dir):
    os.makedirs(final_out_dir, exist_ok=True)
    log(f"Retoc proses ulang → {final_out_dir}")

    # to-legacy: retoc to-legacy <INPUT> <OUTPUT>
    cmd = [RETOC, "to-legacy", input_for_retoc, final_out_dir, "--no-shaders"]
    ok, _ = run(cmd)
    if ok:
        log("to-legacy berhasil")
        return True

    # unpack: retoc unpack <UTOC> <OUTPUT>  (positional, bukan --output)
    cmd = [RETOC, "unpack", input_for_retoc, final_out_dir]
    ok, _ = run(cmd)
    if ok:
        log("unpack berhasil")
        return True

    log("Retoc gagal memproses ulang", "WARN")
    return False

def analyze_compatibility(extracted_dir):
    log("Analisis kompatibilitas (sederhana):")
    uassets = list(Path(extracted_dir).rglob("*.uasset"))
    log(f"  Jumlah .uasset: {len(uassets)}")
    log("  Catatan: Asset PC (WindowsServer) TIDAK otomatis kompatibel dengan ARK Mobile.")
    log("  Perbedaan: UE version, platform, cooking, Blueprint, dependency.")
    log("  Jangan anggap hasil ini sebagai mod mobile yang siap pakai.")

def process_mod(name, input_dir, output_subdir):
    final_out = os.path.join(EXTRACTED_BASE, output_subdir)
    log(f"=== Memproses {name} ===")
    log(f"Input : {input_dir}")
    log(f"Output: {final_out}")

    if not os.path.isdir(input_dir):
        log(f"Direktori tidak ditemukan: {input_dir}", "ERROR")
        return False

    utoc = find_utoc(input_dir)
    if not utoc:
        log("Tidak ditemukan .utoc. Coba mode .pak...", "WARN")
        paks = [f for f in os.listdir(input_dir) if f.endswith(".pak")]
        if not paks:
            log("Tidak ada .utoc maupun .pak", "ERROR")
            return False
        os.makedirs(final_out, exist_ok=True)
        ok, _ = run([REPAK, "unpack", os.path.join(input_dir, paks[0]), final_out])
        if ok:
            analyze_compatibility(final_out)
        return ok

    retoc_read_index(utoc)
    ucas = find_ucas(utoc)
    blocks = parse_toc_compression_blocks(utoc)

    with tempfile.TemporaryDirectory(prefix="arkmod_") as tmp:
        raw_dir = os.path.join(tmp, "raw")
        decomp_dir = os.path.join(tmp, "decomp")
        blocks_dir = os.path.join(tmp, "blocks")

        got_raw = extract_raw_chunks(utoc, raw_dir)

        if blocks and ucas:
            extract_and_decompress_blocks(ucas, blocks_dir, blocks)

        process_input = input_dir
        if got_raw and os.path.isdir(raw_dir) and any(Path(raw_dir).iterdir()):
            process_input = raw_dir

        success = retoc_process_packages(process_input, final_out)

        backup = os.path.join(final_out, "_raw_and_blocks")
        os.makedirs(backup, exist_ok=True)
        if os.path.isdir(raw_dir):
            shutil.copytree(raw_dir, os.path.join(backup, "raw"), dirs_exist_ok=True)
        if os.path.isdir(blocks_dir):
            shutil.copytree(blocks_dir, os.path.join(backup, "blocks"), dirs_exist_ok=True)
        log(f"Backup disimpan di {backup}")

    if success or os.path.isdir(final_out):
        analyze_compatibility(final_out)
        return True
    return False

def main():
    parser = argparse.ArgumentParser(description="ARK Mobile Mod Extractor — Retoc + Unoodle")
    parser.add_argument("command", choices=["extract", "list", "check"])
    parser.add_argument("--mod", choices=["spyglass", "field", "both"], default="both")
    args = parser.parse_args()

    if not check_tools():
        sys.exit(1)

    if args.command == "check":
        log("Tool check OK")
        log(f"retoc : {RETOC}")
        log(f"repak : {REPAK}")
        log(f"unoodle: {shutil.which(UNOODLE) or 'tidak di PATH'}")
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

    results = []
    if args.mod in ("spyglass", "both"):
        results.append(process_mod("Awesome Spyglass", SPYGLASS_DIR, "spyglass"))
    if args.mod in ("field", "both"):
        results.append(process_mod("Field Generators", FIELD_DIR, "field"))

    log("=== Selesai ===")
    if all(results):
        log("Semua mod berhasil diproses.")
    else:
        log("Ada yang gagal. Cek log di atas.", "WARN")

    log(f"Hasil: {EXTRACTED_BASE}/spyglass/ dan {EXTRACTED_BASE}/field/")
    log("PENTING: File original tidak diubah. Hasil adalah asset PC, belum siap jadi mod mobile.")

if __name__ == "__main__":
    main()nt("command", choices=["extract", "list", "check"], help="Perintah")
    parser.add_argument("--mod", choices=["spyglass", "field", "both"], default="both")
    args = parser.parse_args()

    if not check_tools():
        sys.exit(1)

    if args.command == "check":
        log("Tool check OK")
        log(f"retoc : {RETOC}")
        log(f"repak : {REPAK}")
        log(f"unoodle: {shutil.which(UNOODLE) or 'tidak di PATH'}")
        log("")
        log("Pipeline:")
        log("  1. Retoc baca index .utoc")
        log("  2. Ambil compressed chunk dari .ucas (unpack-raw)")
        log("  3. Unoodle dekompresi blok Oodle (per-chunk, --length/--header)")
        log("  4. Retoc proses ulang data package")
        log("")
        log("Catatan: Unoodle tidak otomatis dekompresi seluruh .ucas.")
        log("File original tidak pernah diubah.")
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
        log("Semua mod berhasil diproses.")
    else:
        log("Ada yang gagal. Cek log di atas.", "WARN")

    log("Hasil ada di:")
    log(f"  {EXTRACTED_BASE}/spyglass/")
    log(f"  {EXTRACTED_BASE}/field/")
    log("")
    log("PENTING:")
    log("- File original tidak diubah.")
    log("- Unoodle butuh chunk + header yang cocok (tidak otomatis seluruh .ucas).")
    log("- Hasil adalah asset PC. Belum siap jadi mod mobile.")
    log("- Langkah selanjutnya butuh analisis manual + cooking ulang di UE Android.")


if __name__ == "__main__":
    main()
