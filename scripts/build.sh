#!/usr/bin/env bash
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
BUILD="$ROOT/build"
PKG="$ROOT/packages"
mkdir -p "$BUILD" "$PKG"

echo "==> Скачивание компонентов"
curl -fLs -o "$BUILD/py-win.tar.gz" "https://github.com/astral-sh/python-build-standalone/releases/download/20261123/cpython-3.11.18%2B20261123-x86_64-pc-windows-msvc-install_only.tar.gz"
curl -fLs -o "$BUILD/py-linux.tar.gz" "https://github.com/astral-sh/python-build-standalone/releases/download/20261123/cpython-3.11.18%2B20261123-x86_64-unknown-linux-gnu-install_only.tar.gz"
curl -fLs -o "$BUILD/7zinstall.exe" "https://www.7-zip.org/a/7z2501-x64.exe"
curl -fLs -o "$BUILD/appimagetool.AppImage" "https://github.com/AppImage/appimagetool/releases/download/continuous/appimagetool-x86_64.AppImage"
curl -fLs -o "$BUILD/cacert.pem" "https://curl.se/ca/cacert.pem"
chmod +x "$BUILD/appimagetool.AppImage"

echo "==> Подготовка公共安全ных ассетов"
cp "$BUILD/cacert.pem" "$ROOT/assets/ca-bundle.pem"
cat "$ROOT/assets/certs/ca.crt" >> "$ROOT/assets/ca-bundle.pem"

echo "==> Windows: распаковка Python и SFX"
rm -rf "$BUILD/stage-win" "$BUILD/7z-sfx"
mkdir -p "$BUILD/stage-win" "$BUILD/7z-sfx"
tar -xzf "$BUILD/py-win.tar.gz" -C "$BUILD/stage-win"
7z x -y -o"$BUILD/7z-sfx" "$BUILD/7zinstall.exe" 7zCon.sfx >/dev/null
cp -r "$ROOT/src" "$ROOT/assets" "$BUILD/stage-win/"
cp "$ROOT/src/run.cmd" "$BUILD/stage-win/"
cat > "$BUILD/sfx-config.txt" <<'EOF'
;!@Install@!UTF-8!
Title="Amber AG - Russian Antigravity"
BeginPrompt="Amber AG: install and run Russian Antigravity? "
RunProgram="python\\pythonw.exe src\\amber.py"
;!@InstallEnd@!
EOF
rm -f "$BUILD/amber-win.7z"
(cd "$BUILD/stage-win" && 7z a -y -r "$BUILD/amber-win.7z" python src assets run.cmd >/dev/null)
cat "$BUILD/7z-sfx/7zCon.sfx" "$BUILD/sfx-config.txt" "$BUILD/amber-win.7z" > "$PKG/AmberAG.exe"
chmod +x "$PKG/AmberAG.exe"

echo "==> Linux: сборка AppImage"
APPDIR="$BUILD/AmberAG.AppDir"
rm -rf "$APPDIR"
mkdir -p "$APPDIR/usr/share/amber-ag" "$APPDIR/usr/share/icons/hicolor/256x256/apps"
tar -xzf "$BUILD/py-linux.tar.gz" -C "$BUILD"
rm -rf "$APPDIR/usr/python"
mv "$BUILD/python" "$APPDIR/usr/python"
cp -r "$ROOT/src" "$ROOT/assets" "$APPDIR/usr/share/amber-ag/"
cp "$ROOT/assets/icon.png" "$APPDIR/usr/share/icons/hicolor/256x256/apps/amber-ag.png"
cp "$ROOT/assets/icon.png" "$APPDIR/amber-ag.png"
cp "$ROOT/src/AppRun" "$APPDIR/AppRun"
chmod +x "$APPDIR/AppRun"
cat > "$APPDIR/amber-ag.desktop" <<'EOF'
[Desktop Entry]
Type=Application
Name=Amber AG
GenericName=Russian Antigravity
Comment=Russian Google Antigravity launcher
Exec=AppRun
Icon=amber-ag
Terminal=false
Categories=Development;IDE;
EOF
cp "$APPDIR/amber-ag.desktop" "$APPDIR/usr/share/applications/" 2>/dev/null || { mkdir -p "$APPDIR/usr/share/applications"; cp "$APPDIR/amber-ag.desktop" "$APPDIR/usr/share/applications/"; }
chmod -R a+rX "$APPDIR"
"$BUILD/appimagetool.AppImage" --appimage-extract-and-run "$APPDIR" "$PKG/AmberAG-x86_64.AppImage"

echo "==> Готово"
ls -lh "$PKG"
