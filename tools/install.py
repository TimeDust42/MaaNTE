from pathlib import Path
import argparse
import shutil
import sys
import tarfile
import urllib.request
import zipfile
import time
import subprocess

try:
    import jsonc # type: ignore[import-untyped]
except ModuleNotFoundError as e:
    raise ImportError(
        "Missing dependency 'json-with-comments' (imported as 'jsonc').\n"
        f"Install it with:\n  {sys.executable} -m pip install json-with-comments\n"
        "Or add it to your project's requirements."
    ) from e

from configure import configure_ocr_model

# ================= НАСТРОЙКИ =================
PROJECT_NAME = "MaaNTE"
PROJECT_VERSION = "v1.0.0"

MAA_REPO = "MaaXYZ/MaaFramework"
MAA_VERSION = "v5.14.3"

MXU_REPO = "misteo/mxu"
MXU_VERSION = "v2.8.0"
# ============================================

working_dir = Path(__file__).parent.parent.resolve()
install_path = working_dir / "install"
deps_dir = working_dir / "deps"

maa_deps_dir = deps_dir / "maaframework"
mxu_deps_dir = deps_dir / "mxu"


def parse_args():
    parser = argparse.ArgumentParser(description="Сборщик проекта MaaNTE и установка зависимостей")
    parser.add_argument("version", nargs="?", default=PROJECT_VERSION, help="Версия проекта (например, v1.0.0)")
    parser.add_argument("os", nargs="?", default="win", choices=["win", "macos", "linux", "android"], help="Целевая ОС")
    parser.add_argument("arch", nargs="?", default="x86_64", choices=["x86_64", "aarch64"], help="Архитектура")
    parser.add_argument(
        "--reinstall-deps", "-f",
        action="store_true",
        help="Принудительно удалить и заново скачать зависимости (MaaFramework, MXU)"
    )
    return parser.parse_args()


args = parse_args()
project_version = args.version
os_name = args.os
arch = args.arch
force_reinstall = args.reinstall_deps


def clean_previous_build():
    """Полная очистка предыдущей сборки"""
    if install_path.exists():
        print(f"--> 🧹 Очистка старой папки {install_path.name}...")
        shutil.rmtree(install_path)
    install_path.mkdir(parents=True, exist_ok=True)


def get_dotnet_platform_tag():
    mapping = {
        ("win", "x86_64"): "win-x64",
        ("win", "aarch64"): "win-arm64",
        ("macos", "x86_64"): "osx-x64",
        ("macos", "aarch64"): "osx-arm64",
        ("linux", "x86_64"): "linux-x64",
        ("linux", "aarch64"): "linux-arm64",
    }
    tag = mapping.get((os_name, arch))
    if not tag:
        print(f"Unsupported OS/arch: {os_name} {arch}")
        sys.exit(1)
    return tag


def is_archive_valid(archive_path: Path) -> bool:
    """Проверяет валидность и целостность архива"""
    if not archive_path.exists() or archive_path.stat().st_size == 0:
        return False
    try:
        if archive_path.name.endswith(".zip"):
            with zipfile.ZipFile(archive_path, "r") as zf:
                return zf.testzip() is None
        elif archive_path.name.endswith(".tar.gz"):
            with tarfile.open(archive_path, "r:gz") as tf:
                for _ in tf:
                    pass
            return True
    except Exception:
        return False
    return False

def format_size(bytes_count: int) -> str:
    """Форматирует байты в читаемый формат (KB, MB, GB, TB)"""
    size = float(bytes_count)
    for unit in ['B', 'KB', 'MB', 'GB']:
        if size < 1024.0:
            return f"{size:.1f} {unit}"
        size /= 1024.0
    return f"{size:.1f} TB"

def download_safe(url: str, dest_path: Path):
    dest_path.parent.mkdir(parents=True, exist_ok=True)
    temp_path = dest_path.with_suffix(dest_path.suffix + ".tmp")

    if temp_path.exists():
        temp_path.unlink()

    print(f"--> 🌐 Скачивание: {dest_path.name}")
    headers = {"User-Agent": "Mozilla/5.0"}
    req = urllib.request.Request(url, headers=headers)

    try:
        with urllib.request.urlopen(req) as response, open(temp_path, "wb") as out_file:
            total_size = int(response.headers.get("content-length", 0))
            downloaded = 0
            chunk_size = 1024 * 64
            
            start_time = time.time()
            last_update_time = start_time

            while True:
                chunk = response.read(chunk_size)
                if not chunk:
                    break
                
                out_file.write(chunk)
                downloaded += len(chunk)
                current_time = time.time()

                if current_time - last_update_time > 0.1 or downloaded == total_size:
                    elapsed = current_time - start_time
                    speed = downloaded / elapsed if elapsed > 0 else 0
                    
                    if total_size > 0:
                        percent = (downloaded / total_size) * 100
                        bar_len = 30
                        filled = int(bar_len * downloaded // total_size)
                        bar = "=" * filled + "-" * (bar_len - filled)
                        status = (
                            f"\r[{bar}] {percent:5.1f}% "
                            f"({format_size(downloaded)}/{format_size(total_size)}) "
                            f"[{format_size(int(speed))}/s]"
                        )
                    else:
                        status = f"\rСкачано: {format_size(downloaded)} [{format_size(int(speed))}/s]"
                    
                    sys.stdout.write(status)
                    sys.stdout.flush()
                    last_update_time = current_time

            sys.stdout.write("\n")
            sys.stdout.flush()

        temp_path.replace(dest_path)
        print(f"--> 💾 Сохранено: {dest_path.name}")

    except Exception as e:
        sys.stdout.write("\n")
        if temp_path.exists():
            temp_path.unlink()
        raise e


def extract_archive(archive_path: Path, extract_to: Path):
    print(f"--> 📦 Распаковка {archive_path.name} в {extract_to.relative_to(working_dir)}/...")
    extract_to.mkdir(parents=True, exist_ok=True)
    if archive_path.name.endswith(".zip"):
        with zipfile.ZipFile(archive_path, "r") as zip_ref:
            zip_ref.extractall(extract_to)
    elif archive_path.name.endswith(".tar.gz"):
        with tarfile.open(archive_path, "r:gz") as tar_ref:
            tar_ref.extractall(extract_to)


def ensure_maaframework():
    if force_reinstall and maa_deps_dir.exists():
        print("--> Флаг --reinstall-deps: 🔄 удаление старого MaaFramework...")
        shutil.rmtree(maa_deps_dir)

    bin_dir = maa_deps_dir / "bin"
    zip_name = f"MAA-{os_name}-{arch}-{MAA_VERSION}.zip"
    zip_path = maa_deps_dir / zip_name

    if bin_dir.exists() and is_archive_valid(zip_path):
        return

    maa_deps_dir.mkdir(parents=True, exist_ok=True)

    if zip_path.exists() and not is_archive_valid(zip_path):
        print(f"⚠️ [Предупреждение] Архив {zip_name} поврежден! Удаление и повторное скачивание...")
        zip_path.unlink()

    if not zip_path.exists():
        url = f"https://github.com/{MAA_REPO}/releases/download/{MAA_VERSION}/{zip_name}"
        try:
            download_safe(url, zip_path)
        except Exception as e:
            print(f"❌ Ошибка загрузки MaaFramework: {e}")
            sys.exit(1)

    extract_archive(zip_path, maa_deps_dir)


def patch_exe_icon_and_rename():
    """Переименовывает mxu.exe в имя проекта и заменяет его системную иконку"""
    if os_name != "win":
        return

    orig_exe = install_path / "mxu.exe"
    target_exe = install_path / f"{PROJECT_NAME}.exe"

    if not orig_exe.exists():
        return

    # 1. Переименовываем mxu.exe -> MaaNTE.exe
    orig_exe.rename(target_exe)
    print(f"🏷️ Исполняемый файл переименован в: {target_exe.name}")

    # 2. Проверяем наличие .ico файла
    ico_path = working_dir / "assets" / "resource" / "icon.ico"
    if not ico_path.exists():
        print("ℹ️ Файл icon.ico не найден, смена вшитой иконки .exe пропущена.")
        return

    # 3. Скачиваем rcedit-x64.exe в deps/tools/, если его еще нет
    rcedit_path = deps_dir / "tools" / "rcedit-x64.exe"
    if not rcedit_path.exists():
        rcedit_url = "https://github.com/electron/rcedit/releases/download/v2.0.0/rcedit-x64.exe"
        download_safe(rcedit_url, rcedit_path)

    # 4. Вшиваем иконку и название продукта в .exe
    print(f"🎨 Вшивание иконки в {target_exe.name}...")
    subprocess.run([
        str(rcedit_path),
        str(target_exe),
        "--set-icon", str(ico_path),
        "--set-version-string", "ProductName", PROJECT_NAME,
        "--set-version-string", "FileDescription", f"{PROJECT_NAME} Assistant"
    ], check=True)
    print("✅ Иконка и метаданные .exe успешно обновлены!")


def install_mxu():
    if force_reinstall and mxu_deps_dir.exists():
        print("--> Флаг --reinstall-deps: 🔄 удаление старого MXU...")
        shutil.rmtree(mxu_deps_dir)

    mxu_deps_dir.mkdir(parents=True, exist_ok=True)

    ext = "zip" if os_name == "win" else "tar.gz"
    archive_name = f"MXU-{os_name}-{arch}-{MXU_VERSION}.{ext}"
    archive_path = mxu_deps_dir / archive_name

    if archive_path.exists() and not is_archive_valid(archive_path):
        print(f"⚠️ [Предупреждение] Архив {archive_name} поврежден! Удаление и повторное скачивание...")
        archive_path.unlink()

    if not archive_path.exists():
        url = f"https://github.com/{MXU_REPO}/releases/download/{MXU_VERSION}/{archive_name}"
        try:
            download_safe(url, archive_path)
        except Exception as e:
            print(f"⚠️ Предупреждение: не удалось автоматически скачать MXU: {e}")
            print(f"Положите валидный архив MXU вручную в: {archive_path}")
            return

    extracted_marker = mxu_deps_dir / ("mxu.exe" if os_name == "win" else "mxu")
    if not extracted_marker.exists():
        extract_archive(archive_path, mxu_deps_dir)

    print("--> 🚀 Установка MXU в install/...")
    for item in mxu_deps_dir.iterdir():
        if item.name.endswith(".zip") or item.name.endswith(".tar.gz") or item.name == "mxu.pdb":
            continue
        if item.is_dir():
            shutil.copytree(item, install_path / item.name, dirs_exist_ok=True)
        else:
            shutil.copy2(item, install_path / item.name)

    patch_exe_icon_and_rename()


def install_deps():
    ensure_maaframework()

    maafw_target_dir = install_path / "maafw"
    maafw_target_dir.mkdir(parents=True, exist_ok=True)

    if (maa_deps_dir / "bin").exists():
        shutil.copytree(
            maa_deps_dir / "bin",
            maafw_target_dir,
            dirs_exist_ok=True,
        )

    if (maa_deps_dir / "share" / "MaaAgentBinary").exists():
        shutil.copytree(
            maa_deps_dir / "share" / "MaaAgentBinary",
            maafw_target_dir / "MaaAgentBinary",
            dirs_exist_ok=True,
        )


def install_resource():
    configure_ocr_model()

    shutil.copytree(working_dir / "assets" / "resource", install_path / "resource", dirs_exist_ok=True)
    shutil.copy2(working_dir / "assets" / "interface.json", install_path)

    with open(install_path / "interface.json", "r", encoding="utf-8") as f:
        interface = jsonc.load(f)

    interface["version"] = project_version

    with open(install_path / "interface.json", "w", encoding="utf-8") as f:
        jsonc.dump(interface, f, ensure_ascii=False, indent=4)


def install_chores():
    for filename in ["README.md", "LICENSE"]:
        file_path = working_dir / filename
        if file_path.exists():
            shutil.copy2(file_path, install_path)


def install_agent():
    if (working_dir / "agent").exists():
        shutil.copytree(working_dir / "agent", install_path / "agent", dirs_exist_ok=True)


def create_release_archive():
    archive_name = f"{PROJECT_NAME}-{project_version}-{os_name}-{arch}.zip"
    archive_path = working_dir / archive_name

    if archive_path.exists():
        archive_path.unlink()

    print(f"--> 🗜️  Упаковка в архив {archive_name}...")
    with zipfile.ZipFile(archive_path, "w", zipfile.ZIP_DEFLATED) as zip_out:
        for file in install_path.rglob("*"):
            if file.is_file():
                arcname = file.relative_to(install_path)
                zip_out.write(file, arcname)

    print(f"--> 🎁 Готовый архив создан: {archive_path}")


if __name__ == "__main__":
    clean_previous_build()
    install_deps()
    install_resource()
    install_chores()
    install_agent()
    install_mxu()
    create_release_archive()

    print(f"\n🎉 Чистый билд сформирован в: {install_path}")