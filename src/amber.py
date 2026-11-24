#!/usr/bin/env python3
"""Янтарь (Amber AG) — русский Google Antigravity одной кнопкой.

Публичная версия: без аккаунтов, VPN и пользовательских данных.
При первом запуске скачивает официальный Antigravity с сайта Google,
включает русский интерфейс и (для РФ) локальный гейт-прокси.
"""
import os
import platform
import re
import shutil
import subprocess
import sys
import tarfile
import time
import urllib.request

WIN = platform.system() == "Windows"
APP_NAME = "AmberAG"
DOWNLOAD_PAGE = "https://antigravity.google/download"
WIN_URL = "https://storage.googleapis.com/antigravity-public/antigravity-hub/2.34.0-5887025308631040/windows-x64/Antigravity-x64.exe"
LIN_URL = "https://storage.googleapis.com/antigravity-public/antigravity-hub/2.34.0-5887025308631040/linux-x64/Antigravity.tar.gz"
PORT = 53190
DEBUG_PORT = 58321

HERE = os.path.dirname(os.path.abspath(__file__))
SRC = HERE if os.path.isdir(os.path.join(HERE, "assets")) else os.path.dirname(HERE)
DATA = os.path.join(os.environ.get("LOCALAPPDATA" if WIN else "HOME",
                                   os.path.expanduser("~")), APP_NAME)
APPDIR = os.path.join(DATA, "antigravity")
INSTALLED = os.path.join(DATA, "installed.marker")
PYBIN = sys.executable


def log(msg):
    print("[Amber] " + str(msg), flush=True)


def user_data():
    os.makedirs(DATA, exist_ok=True)
    os.makedirs(APPDIR, exist_ok=True)


def bootstrap():
    """Копируем себя в постоянную папку данных, чтобы не зависеть от temp SFX."""
    if os.path.isfile(os.path.join(DATA, "installed.marker")) and os.path.isfile(
            os.path.join(DATA, "src", "amber.py")):
        return DATA
    user_data()
    for name in ("src", "assets"):
        dst = os.path.join(DATA, name)
        if os.path.isdir(dst):
            shutil.rmtree(dst)
        shutil.copytree(os.path.join(SRC, name), dst)
    open(os.path.join(DATA, "installed.marker"), "w").close()
    return DATA


def find_urls():
    try:
        with urllib.request.urlopen(DOWNLOAD_PAGE, timeout=15) as r:
            html = r.read().decode("utf-8", "replace")
        w = re.search(r'https://[^" ]+/windows-x64/Antigravity-x64\.exe', html)
        l = re.search(r'https://[^" ]+/linux-x64/Antigravity\.tar\.gz', html)
        return (w.group(0) if w else WIN_URL, l.group(0) if l else LIN_URL)
    except Exception as exc:
        log(f"не удалось получить актуальные ссылки ({exc}), используем запасные")
        return WIN_URL, LIN_URL


def download(url, path):
    if os.path.isfile(path) and os.path.getsize(path) > 10_000_000:
        return path
    log(f"скачивание: {url}")
    with urllib.request.urlopen(url, timeout=90) as r, open(path + ".part", "wb") as f:
        while True:
            chunk = r.read(1024 * 1024)
            if not chunk:
                break
            f.write(chunk)
    os.replace(path + ".part", path)
    return path


def find_binary(root):
    names = ("antigravity", "Antigravity.exe", "antigravity.exe")
    for base, _dirs, files in os.walk(root):
        for name in files:
            if name in names:
                return os.path.join(base, name)
    return None


def install_app():
    exe = find_binary(APPDIR)
    if exe and os.path.isfile(exe):
        return exe
    wurl, lurl = find_urls()
    if WIN:
        installer = os.path.join(DATA, "Antigravity-x64.exe")
        download(wurl, installer)
        log("установка Antigravity (может занять пару минут)…")
        for args in (["/S"], ["/VERYSILENT", "/NORESTART"], []):
            try:
                subprocess.run([installer] + args, timeout=600, check=False)
                exe = find_binary(os.path.join(os.environ.get("LOCALAPPDATA", DATA), "Programs")) or find_binary(DATA)
                if exe:
                    return exe
            except Exception as exc:
                log(f"вариант установки {args} не сработал: {exc}")
        raise RuntimeError("не удалось установить Antigravity — запустите установщик вручную")
    archive = os.path.join(DATA, "Antigravity.tar.gz")
    download(lurl, archive)
    log("распаковка Antigravity…")
    with tarfile.open(archive, "r:gz") as tf:
        for member in tf.getmembers():
            target = os.path.join(APPDIR, member.name)
            if not os.path.abspath(target).startswith(os.path.abspath(APPDIR)):
                continue
            if member.isfile() or member.isdir():
                tf.extract(member, APPDIR)
    exe = find_binary(APPDIR)
    if not exe:
        raise RuntimeError("в архиве Antigravity не найден исполняемый файл")
    if not WIN:
        os.chmod(exe, 0o755)
    return exe


def patch_binary(exe):
    root = os.path.dirname(os.path.abspath(exe))
    count = 0
    for base, _dirs, files in os.walk(root):
        for name in files:
            if not name.startswith("language_server"):
                continue
            path = os.path.join(base, name)
            try:
                with open(path, "rb") as f:
                    data = f.read()
                if b"ineligible" not in data and b"https_proxy" not in data:
                    continue
                backup = path + ".amber_backup"
                if not os.path.isfile(backup):
                    shutil.copy2(path, backup)
                data = data.replace(b"ineligible", b"inexigible")
                data = data.replace(b"https_proxy", b"AG_UNL_PRXY")
                with open(path, "wb") as f:
                    f.write(data)
                count += 1
                log(f"патч применён: {name}")
            except OSError:
                pass
    if not count:
        log("патч не потребовался (уже применён или новая сборка)")


def spawn(script, env=None):
    e = dict(os.environ)
    e["AMBER_BASE"] = DATA
    if env:
        e.update(env)
    flags = subprocess.CREATE_NO_WINDOW if WIN else 0
    return subprocess.Popen([PYBIN, os.path.join(DATA, "src", script)], env=e,
                            creationflags=flags)


def main():
    user_data()
    root = bootstrap()
    os.environ["AMBER_BASE"] = root
    exe = install_app()
    patch_binary(exe)

    env = {
        "AG_UNL_PRXY": f"http://127.0.0.1:{PORT}",
        "SSL_CERT_FILE": os.path.join(root, "assets", "ca-bundle.pem"),
    }
    log("запуск локального гейт-прокси…")
    proxy = spawn("gate_proxy.py")
    time.sleep(2)

    log("запуск Antigravity…")
    e = dict(os.environ)
    e.update(env)
    e["AG_UNL_PRXY"] = env["AG_UNL_PRXY"]
    e["SSL_CERT_FILE"] = env["SSL_CERT_FILE"]
    flags = subprocess.CREATE_NO_WINDOW if WIN else 0
    app = subprocess.Popen([
        exe,
        f"--remote-debugging-port={DEBUG_PORT}",
        "--remote-debugging-address=127.0.0.1",
    ], env=e, creationflags=flags)

    log("включение русского интерфейса…")
    injector = spawn("inject.py")
    try:
        app.wait()
    except KeyboardInterrupt:
        pass
    finally:
        for p in (injector, proxy):
            try:
                p.terminate()
            except Exception:
                pass


if __name__ == "__main__":
    main()
