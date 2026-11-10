# ARK Mobile Mod Extractor & Converter

Tool orchestrator untuk mengekstrak mod ARK Survival Ascended (WindowsServer) di Termux Android ARM64.

## Yang sudah tersedia
- `retoc` → `~/retoc/target/release/retoc` (IoStore)
- `repak` → `~/repak/target/release/repak` (classic .pak)
- `unoodle` akan diinstall otomatis (pure Rust Oodle)

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

## Batasan (penting)
1. **Tidak memakai `libUE4.so`** (menghindari segfault).
2. Mengandalkan `retoc` untuk IoStore dan `repak` untuk .pak.
3. Jika Oodle gagal di retoc/repak, `unoodle` tersedia sebagai fallback manual.
4. **Hasil ekstraksi adalah asset PC**. Belum otomatis menjadi mod mobile yang berfungsi.
5. Membuat `.pak` mobile yang benar butuh cooking ulang di Unreal Engine Android, bukan hanya repack.

## Langkah selanjutnya (manual)
Setelah extract berhasil:
1. Analisis `.uasset` dengan tool yang kompatibel.
2. Periksa dependency dan Blueprint.
3. Cook ulang di UE untuk platform Android.
4. Baru kemudian pack menjadi `.pak` mobile.
5. 
