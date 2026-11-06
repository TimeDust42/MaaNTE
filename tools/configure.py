from pathlib import Path
import shutil

assets_dir = Path(__file__).parent.parent.resolve() / "assets"


def configure_ocr_model():
    assets_ocr_dir = assets_dir / "MaaCommonAssets" / "OCR"
    if not assets_ocr_dir.exists():
        print(f"❌ Папка не найдена: {assets_ocr_dir}")
        print("💡 Подсказка: инициализируйте сабмодули командой 'git submodule update --init --recursive'")
        exit(1)

    ocr_dir = assets_dir / "resource" / "model" / "ocr"
    if not ocr_dir.exists():
        print("📥 Копирование стандартной модели OCR (ppocr_v6/small)...")
        shutil.copytree(
            assets_dir / "MaaCommonAssets" / "OCR" / "ppocr_v6" / "small",
            ocr_dir,
            dirs_exist_ok=True,
        )
        print("✅ Модель OCR успешно скопирована.")
    else:
        print("ℹ️  Папка OCR уже существует, импорт стандартной модели пропущен.")


if __name__ == "__main__":
    configure_ocr_model()

    print("🎉 Настройка модели OCR завершена.")