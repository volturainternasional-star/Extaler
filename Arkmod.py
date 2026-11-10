cd ~/Extaler

cp Arkmod.py Arkmod.py.backup

cat > Arkmod.py <<'PY'
#!/data/data/com.termux/files/usr/bin/python3

import argparse
import os
import sys
import shutil
import subprocess
from pathlib import Path
from datetime import datetime

HOME = Path.home()

RETOC = HOME / "retoc/target/release/retoc"
REPAK = HOME / "repak/target/release/repak"

UNOODLE_CANDIDATES = [
    shutil.which("unoodle"),
    str(HOME / ".cargo/bin/unoodle"),
    str(HOME / "bin/unoodle"),
]

SPYGLASS_DIR = (
    HOME / "ark-mods/inspection/spyglass/AwesomeSpyglass/Content/Paks/WindowsServer"
)

FIELD_DIR = (
    HOME / "ark-mods/inspection/field/FieldGenerators/Content/Paks/WindowsServer"
)

OUTPUT_BASE = HOME / "ark-mods/extracted"
LOG_DIR = HOME / "ark-mods/logs"


def log(message, level="INFO"):
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    print(f"[{now}] [{level}] {message}", flush=True)


def find_unoodle():
    for candidate in UNOODLE_CANDIDATES:
        if candidate and Path(candidate).is_file():
            return candidate
    return None


def run_command(command, logfile, timeout=3600):
    log("$ " + " ".join(map(str, command)))

    try:
        result = subprocess.run(
            list(map(str, command)),
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            errors="replace",
            timeout=timeout,
        )

        output = result.stdout or ""

        Path(logfile).parent.mkdir(parents=True, exist_ok=True)
        with open(logfile, "a", encoding="utf-8") as f:
            f.write("\n\n$ " + " ".join(map(str, command)) + "\n")
            f.write(output)

        if output:
            print(output[-6000:], flush=True)

        if result.returncode != 0:
            log(f"Command gagal: exit code {result.returncode}", "ERROR")
            return False, output

        return True, output

    except subprocess.TimeoutExpired:
        log("Command timeout", "ERROR")
        return False, "TIMEOUT"

    except Exception as error:
        log(f"Kesalahan menjalankan command: {error}", "ERROR")
        return False, str(error)


def check_tools():
    missing = []

    if not RETOC.is_file():
        missing.append(f"Retoc tidak ditemukan: {RETOC}")

    if not REPAK.is_file():
        missing.append(f"Repak tidak ditemukan: {REPAK}")

    uno = find_unoodle()

    if not uno:
        log("Unoodle tidak ditemukan.", "WARN")
    else:
        log(f"Unoodle: {uno}")

    if missing:
        for item in missing:
            log(item, "ERROR")
        return False

    return True


def find_utoc(folder):
    if not folder.is_dir():
        return None

    files = sorted(folder.glob("*.utoc"))
    return files[0] if files else None


def find_ucas(utoc):
    candidate = utoc.with_suffix(".ucas")
    return candidate if candidate.is_file() else None


def count_files(folder):
    if not folder.exists():
        return 0
    return sum(1 for item in folder.rglob("*") if item.is_file())


def inspect_container(utoc, logfile):
    log("Memeriksa index IoStore...")

    run_command(
        [RETOC, "info", utoc],
        logfile,
        timeout=300,
    )

    run_command(
        [RETOC, "list", utoc],
        logfile,
        timeout=300,
    )


def extract_iostore(name, input_dir, output_dir):
    log("=" * 55)
    log(f"MOD: {name}")
    log(f"INPUT : {input_dir}")
    log(f"OUTPUT: {output_dir}")

    if not input_dir.is_dir():
        log("Folder input tidak ditemukan.", "ERROR")
        return False

    utoc = find_utoc(input_dir)

    if not utoc:
        log("File .utoc tidak ditemukan.", "ERROR")
        return False

    ucas = find_ucas(utoc)

    if not ucas:
        log("Pasangan file .ucas tidak ditemukan.", "ERROR")
        return False

    if ucas.stat().st_size == 0 or utoc.stat().st_size == 0:
        log("File IoStore kosong.", "ERROR")
        return False

    log(f"UTOC: {utoc.name} ({utoc.stat().st_size} bytes)")
    log(f"UCAS: {ucas.name} ({ucas.stat().st_size} bytes)")

    output_dir.mkdir(parents=True, exist_ok=True)

    logfile = LOG_DIR / f"{name.lower().replace(' ', '_')}.log"
    logfile.parent.mkdir(parents=True, exist_ok=True)

    inspect_container(utoc, logfile)

    # Retoc unpack menggunakan format:
    # retoc unpack <UTOC> <OUTPUT>
    log("Memulai ekstraksi IoStore menggunakan Retoc...")

    success, output = run_command(
        [RETOC, "unpack", utoc, output_dir],
        logfile,
        timeout=3600,
    )

    extracted = count_files(output_dir)

    if success and extracted > 0:
        log(f"Ekstraksi berhasil: {extracted} file.")
        return True

    log("Retoc belum berhasil mengekstrak container.", "ERROR")

    error_text = output.lower()

    if "oodle" in error_text:
        log(
            "Retoc gagal pada dekompresi Oodle. "
            "Build Retoc ini belum memiliki decoder Oodle yang berfungsi.",
            "ERROR",
        )

    log(f"Jumlah file output saat ini: {extracted}")
    log(f"Log lengkap: {logfile}")

    return False


def extract_legacy_pak(pak, output_dir):
    logfile = LOG_DIR / "legacy_pak.log"

    output_dir.mkdir(parents=True, exist_ok=True)

    log("Mencoba ekstraksi PAK legacy menggunakan Repak...")

    success, _ = run_command(
        [REPAK, "unpack", pak, "--output", output_dir],
        logfile,
        timeout=3600,
    )

    extracted = count_files(output_dir)

    if success and extracted > 0:
        log(f"PAK berhasil diekstrak: {extracted} file.")
        return True

    log("Ekstraksi PAK gagal. Periksa log Repak.", "ERROR")
    return False


def process_mod(name, input_dir, output_name):
    output_dir = OUTPUT_BASE / output_name

    if output_dir.exists():
        log(f"Folder output sudah ada: {output_dir}", "WARN")
        log("File lama tidak dihapus atau ditimpa otomatis.", "WARN")
        output_dir = OUTPUT_BASE / (
            output_name + "_" + datetime.now().strftime("%Y%m%d_%H%M%S")
        )

    utoc = find_utoc(input_dir)

    if utoc:
        return extract_iostore(name, input_dir, output_dir)

    if not input_dir.is_dir():
        log(f"Folder tidak ditemukan: {input_dir}", "ERROR")
        return False

    pak_files = sorted(input_dir.glob("*.pak"))

    if not pak_files:
        log(f"Tidak ditemukan .utoc maupun .pak di {input_dir}", "ERROR")
        return False

    return extract_legacy_pak(pak_files[0], output_dir)


def main():
    parser = argparse.ArgumentParser(
        description="ARK IoStore extractor for Termux"
    )

    parser.add_argument(
        "command",
        choices=["check", "list", "extract"],
    )

    parser.add_argument(
        "--mod",
        choices=["spyglass", "field", "both"],
        default="both",
    )

    args = parser.parse_args()

    LOG_DIR.mkdir(parents=True, exist_ok=True)
    OUTPUT_BASE.mkdir(parents=True, exist_ok=True)

    if not check_tools():
        sys.exit(1)

    if args.command == "check":
        log(f"Retoc : {RETOC}")
        log(f"Repak : {REPAK}")
        log(f"Unoodle: {find_unoodle() or 'tidak ditemukan'}")

        run_command(
            [RETOC, "--version"],
            LOG_DIR / "check.log",
            timeout=60,
        )

        run_command(
            [REPAK, "--version"],
            LOG_DIR / "check.log",
            timeout=60,
        )

        sys.exit(0)

    if args.command == "list":
        for name, folder in [
            ("Awesome Spyglass", SPYGLASS_DIR),
            ("Field Generators", FIELD_DIR),
        ]:
            log(name)

            if not folder.is_dir():
                log(f"Folder tidak ditemukan: {folder}", "WARN")
                continue

            for item in sorted(folder.iterdir()):
                print(f"  {item.name}")

        sys.exit(0)

    results = []

    if args.mod in ("spyglass", "both"):
        results.append(
            process_mod(
                "Awesome Spyglass",
                SPYGLASS_DIR,
                "spyglass",
            )
        )

    if args.mod in ("field", "both"):
        results.append(
            process_mod(
                "Field Generators",
                FIELD_DIR,
                "field",
            )
        )

    print()
    log("========== HASIL ==========")

    if results and all(results):
        log("Ekstraksi selesai dan file output ditemukan.")
    else:
        log("Ada proses ekstraksi yang gagal.", "ERROR")
        log("Jangan anggap file output parsial sebagai hasil berhasil.")

    log(f"Folder output: {OUTPUT_BASE}")
    log(f"Folder log   : {LOG_DIR}")
    log("File sumber asli tidak diubah.")
    log("Asset WindowsServer belum otomatis kompatibel dengan ARK Mobile.")


if __name__ == "__main__":
    main()
PY

python -m py_compile Arkmod.py  blocks = parse_toc_compression_blocks(utoc)

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
