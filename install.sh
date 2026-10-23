#!/bin/bash
# Memasang Catatan Cornell untuk pengguna saat ini (tanpa sudo).
set -e
DIR="$(cd "$(dirname "$0")" && pwd)"
DEST="$HOME/.local/share/cornell-app"
ID="id.mnawawii.cornell"

if ! python3 -c "import PySide6.QtWidgets" 2>/dev/null; then
  echo "Catatan: PySide6 belum terpasang. Pasang dengan: sudo dnf install python3-pyside6 qt6-qtwayland"
fi

mkdir -p "$DEST" "$HOME/.local/bin" "$HOME/.local/share/applications"
rm -rf "$DEST/icons"
cp "$DIR"/*.py "$DEST/"
cp -r "$DIR/icons" "$DEST/"

# ikon: tema ikon pengguna (SVG + PNG) agar tampil di dock dan menu GNOME
ICONROOT="$HOME/.local/share/icons/hicolor"
mkdir -p "$ICONROOT/scalable/apps"
cp "$DIR/icons/$ID.svg" "$ICONROOT/scalable/apps/"
for s in 48 64 128 256; do
  mkdir -p "$ICONROOT/${s}x${s}/apps"
  cp "$DIR/icons/$ID-$s.png" "$ICONROOT/${s}x${s}/apps/$ID.png"
done
gtk-update-icon-cache -f -t "$ICONROOT" 2>/dev/null || true

cat > "$HOME/.local/bin/cornell" << LAUNCH
#!/bin/bash
exec python3 "$DEST/main.py" "\$@"
LAUNCH
chmod +x "$HOME/.local/bin/cornell"

cat > "$HOME/.local/share/applications/$ID.desktop" << DESK
[Desktop Entry]
Type=Application
Name=Catatan Cornell
Comment=Pencatat materi metode Cornell dengan ekspor PDF dan Word
Exec=$HOME/.local/bin/cornell
Icon=$ICONROOT/scalable/apps/$ID.svg
Categories=Office;Education;
StartupWMClass=$ID
Terminal=false
DESK
update-desktop-database "$HOME/.local/share/applications" 2>/dev/null || true
echo "Selesai. Cari 'Catatan Cornell' di menu aplikasi, atau jalankan: cornell"
