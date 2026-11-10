#!/data/data/com.termux/files/usr/bin/python3
"""
ARK Mobile Mod Extractor & Converter
Pipeline (sesuai target perbaikan):

1. Retoc membaca index .utoc.
2. Tool mengambil compressed chunk dari .ucas (via unpack-raw / get).
3. Unoodle mendekompresi blok Oodle yang sesuai (per-chunk, dengan --length / --header).
4. Retoc memproses kembali data package (to-legacy / unpack pada hasil dekompresi).

Catatan penting:
- Unoodle TIDAK otomatis bisa mendekompresi seluruh .ucas.
  Kita harus memastikan format chunk + header cocok terlebih dahulu.
- File original TIDAK pernah diubah. Semua kerja di direktori output/temp.
- Hasil adalah asset PC (WindowsServer). Belum otomatis jadi mod mobile.
"""

import argparse
import os
import sys
import subprocess
import shutil
import tempfile
from pathlib import Path
from datetime import datetime

# Paths (sesuaikan jika perlu)
RETOC = os.path.expanduser("~/retoc/target/release/retoc")
REPAK = os.path.expanduser("~/repak/target/release/repak")
UNOODLE = "unoodle"

SPYGLASS_DIR = os.path.expanduser("~/ark-mods/inspection/spyglass/AwesomeSpyglass/Content/Paks/WindowsServer")
FIELD_DIR = os.path.expanduser("~/ark-mods/inspection/field/FieldGenerators/Content/Paks/WindowsServer")

EXTRACTED_BASE = os.path.expanduser("~/ark-mods/extracted")

# Common Oodle / IoStore block sizes (bytes) untuk coba-coba
COMMON_UNCOMPRESSED = [65536, 131072, 262144, 524288, 1048576]


def log(msg, level="INFO"):
    ts = datetime.now().strftime("%H:%M:%S")
    print(f"[{ts}] [{level}] {msg}")


def run(cmd, cwd=None, timeout=3600):
    log(f"Menjalankan: {' '.join(cmd)}")
    try:
        result = subprocess.run(
            cmd, cwd=cwd, capture_output=True, text=True, timeout=timeout
        )
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
    # unoodle optional tapi disarankan
    if shutil.which(UNOODLE) is None and not os.path.exists(os.path.expanduser("~/bin/unoodle")):
        log("unoodle tidak ditemukan di PATH. Fallback Oodle akan terbatas.", "WARN")
    if missing:
        for m in missing:
            log(m, "ERROR")
        log("Pastikan retoc dan repak sudah di-build.", "ERROR")
        return False
    return True


def find_utoc(input_dir):
    for f in sorted(os.listdir(input_dir)):
        if f.endswith(".utoc"):
            return os.path.join(input_dir, f)
    return None


def find_ucas(utoc_path):
    base = utoc_path[:-5]  # strip .utoc
    for ext in (".ucas", ".UCAS"):
        p = base + ext
        if os.path.exists(p):
            return p
    return None


def retoc_read_index(utoc_path):
    """Langkah 1: Retoc membaca index .utoc."""
    log(f"Retoc membaca index: {os.path.basename(utoc_path)}")
    # info + list (directory index)
    ok_info, _ = run([RETOC, "info", utoc_path])
    ok_list, _ = run([RETOC, "list", utoc_path])
    return ok_info or ok_list


def extract_raw_chunks(utoc_path, raw_out_dir):
    """Langkah 2: Ambil compressed/raw chunks (unpack-raw)."""
    os.makedirs(raw_out_dir, exist_ok=True)
    log(f"Ambil raw chunks ke {raw_out_dir}")
    # Coba dengan override umum untuk header version mismatch
    for extra in [[], ["--override-container-header-version", "PreInitial"]]:
        cmd = [RETOC] + extra + ["unpack-raw", utoc_path, raw_out_dir]
        ok, _ = run(cmd)
        if ok:
            log("unpack-raw berhasil")
            return True
    log("unpack-raw gagal. Akan coba mode chunk manual nanti.", "WARN")
    return False


def try_unoodle_on_file(src_path, dst_path, uncompressed_len):
    """Coba dekompresi satu blok dengan unoodle."""
    if shutil.which(UNOODLE) is None:
        # coba path umum Termux
        cand = os.path.expanduser("~/bin/unoodle")
        if os.path.exists(cand):
            uno = cand
        else:
            return False
    else:
        uno = UNOODLE

    # --header 0 sering dipakai untuk raw block tanpa header panjang
    cmd = [
        uno,
        "--length", str(uncompressed_len),
        "--header", "0",
        src_path,
        "-o", dst_path,
        "-v",
    ]
    ok, _ = run(cmd, timeout=120)
    if ok and os.path.exists(dst_path) and os.path.getsize(dst_path) > 0:
        return True
    return False


def decompress_oodle_chunks(raw_dir, decompressed_dir):
    """
    Langkah 3: Unoodle pada chunk yang masih compressed.
    Catatan: Unoodle tidak otomatis proses seluruh .ucas.
    Kita coba per-file dengan length umum.
    """
    os.makedirs(decompressed_dir, exist_ok=True)
    raw_files = list(Path(raw_dir).rglob("*"))
    raw_files = [p for p in raw_files if p.is_file()]

    if not raw_files:
        log("Tidak ada raw chunk untuk didekompresi", "WARN")
        return False

    success_count = 0
    for rf in raw_files:
        rel = rf.relative_to(raw_dir)
        out_path = Path(decompressed_dir) / rel
        out_path.parent.mkdir(parents=True, exist_ok=True)

        # Coba length umum
        done = False
        for ulen in COMMON_UNCOMPRESSED:
            tmp = str(out_path) + ".tmp"
            if try_unoodle_on_file(str(rf), tmp, ulen):
                shutil.move(tmp, out_path)
                log(f"Unoodle OK: {rel} (length={ulen})")
                success_count += 1
                done = True
                break
            if os.path.exists(tmp):
                os.remove(tmp)
        if not done:
            # Kalau gagal, salin raw saja (mungkin sudah uncompressed)
            shutil.copy2(rf, out_path)
            log(f"Salin raw (mungkin sudah uncompressed): {rel}", "WARN")

    log(f"Unoodle selesai: {success_count}/{len(raw_files)} chunk didekompresi")
    return success_count > 0


def retoc_process_packages(input_for_retoc, final_out_dir):
    """Langkah 4: Retoc memproses kembali data package."""
    os.makedirs(final_out_dir, exist_ok=True)
    log(f"Retoc proses ulang → {final_out_dir}")

    # Coba to-legacy dulu (paling berguna untuk analisis)
    cmd = [RETOC, "to-legacy", input_for_retoc, final_out_dir, "--no-shaders"]
    ok, _ = run(cmd)
    if ok:
        log("to-legacy berhasil")
        return True

    # Fallback unpack
    cmd = [RETOC, "unpack", input_for_retoc, "--output", final_out_dir]
    ok, _ = run(cmd)
    if ok:
        log("unpack berhasil")
        return True

    log("Retoc gagal memproses ulang. Hasil raw/decompressed tetap disimpan.", "WARN")
    return False


def analyze_compatibility(extracted_dir):
    log("Analisis kompatibilitas (sederhana):")
    uassets = list(Path(extracted_dir).rglob("*.uasset"))
    log(f"  Jumlah .uasset: {len(uassets)}")
    log("  Catatan: Asset PC (WindowsServer) TIDAK otomatis kompatibel dengan ARK Ultimate Mobile.")
    log("  Perbedaan: UE version, platform, cooking, Blueprint, dependency, compression.")
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
        # fallback klasik pak
        paks = [f for f in os.listdir(input_dir) if f.endswith(".pak")]
        if not paks:
            log("Tidak ada .utoc maupun .pak", "ERROR")
            return False
        os.makedirs(final_out, exist_ok=True)
        ok, _ = run([REPAK, "unpack", os.path.join(input_dir, paks[0]), "--output", final_out])
        if ok:
            analyze_compatibility(final_out)
        return ok

    # === Pipeline utama ===
    # 1. Retoc baca index
    retoc_read_index(utoc)

    with tempfile.TemporaryDirectory(prefix="arkmod_") as tmp:
        raw_dir = os.path.join(tmp, "raw")
        decomp_dir = os.path.join(tmp, "decomp")

        # 2. Ambil compressed chunks
        got_raw = extract_raw_chunks(utoc, raw_dir)

        # 3. Unoodle dekompresi blok yang cocok
        if got_raw:
            decompress_oodle_chunks(raw_dir, decomp_dir)
            process_input = decomp_dir
        else:
            # Kalau unpack-raw gagal, coba langsung to-legacy pada folder original
            process_input = input_dir
            log("Lewati unoodle (tidak ada raw chunks). Langsung coba retoc pada original.", "WARN")

        # 4. Retoc proses ulang
        success = retoc_process_packages(process_input, final_out)

        # Selalu simpan juga raw/decompressed untuk analisis manual
        if got_raw:
            backup = os.path.join(final_out, "_raw_and_decompressed")
            os.makedirs(backup, exist_ok=True)
            if os.path.isdir(raw_dir):
                shutil.copytree(raw_dir, os.path.join(backup, "raw"), dirs_exist_ok=True)
            if os.path.isdir(decomp_dir):
                shutil.copytree(decomp_dir, os.path.join(backup, "decompressed"), dirs_exist_ok=True)
            log(f"Backup raw/decompressed disimpan di {backup}")

    if success or os.path.isdir(final_out):
        analyze_compatibility(final_out)
        return True
    return False


def main():
    parser = argparse.ArgumentParser(
        description="ARK Mobile Mod Extractor — Retoc + Unoodle pipeline"
    )
    parser.add_argument("command", choices=["extract", "list", "check"], help="Perintah")
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
