# ARK Mobile Mod Extractor & Converter

Tool orchestrator untuk mengekstrak mod ARK Survival Ascended (WindowsServer) di Termux Android ARM64.

## Pipeline (target perbaikan)

1. **Retoc membaca index `.utoc`** (`retoc info` / `retoc list`).
2. **Tool mengambil compressed chunk dari `.ucas`** (`retoc unpack-raw`).
3. **Unoodle mendekompresi blok Oodle yang sesuai** (per-chunk, dengan `--length` dan `--header 0`).
4. **Retoc memproses kembali data package** (`to-legacy` atau `unpack` pada hasil dekompresi).

Hasil Spyglass dan Field Generators disimpan **terpisah**.

### Catatan penting

- **Unoodle tidak otomatis bisa mendekompresi seluruh `.ucas`**. Kita harus memastikan format chunk dan header-nya cocok terlebih dahulu.
- **File original tidak pernah diubah**. Semua kerja di direktori output / temp.
- Hasil ekstraksi adalah asset PC. Belum otomatis menjadi mod mobile yang berfungsi.
- Membuat `.pak` mobile yang benar butuh cooking ulang di Unreal Engine Android, bukan hanya repack.

## Yang sudah tersedia

- `retoc` → `~/retoc/target/release/retoc` (IoStore)
- `repak` → `~/repak/target/release/repak` (classic `.pak`)
- `unoodle` (pure Rust Oodle) — akan diinstall otomatis jika belum ada

## Install

```bash
chmod +x install.sh
./install.sh
source ~/.bashrc
```

## Penggunaan

```bash
arkmod check
arkmod list
arkmod extract
arkmod extract --mod spyglass
arkmod extract --mod field
```

## Output

- `~/ark-mods/extracted/spyglass/`
- `~/ark-mods/extracted/field/`

Di dalam setiap output juga ada folder `_raw_and_decompressed/` untuk analisis manual.

## Batasan

1. Tidak memakai `libUE4.so` (menghindari segfault).
2. Unoodle hanya dipakai pada blok yang sudah diisolasi dengan panjang yang diketahui/dicoba.
3. Jika header version tidak cocok, script mencoba `--override-container-header-version PreInitial`.
4. Hasil belum dijamin bisa langsung jadi mod mobile.
