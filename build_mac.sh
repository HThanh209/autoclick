#!/bin/bash
# Build AutoClicker.app trên macOS. PHẢI chạy trên chính máy Mac —
# không build được file .app từ Windows.
set -e

python3 -m pip install -r requirements.txt

python3 -m PyInstaller \
  --onefile \
  --windowed \
  --name AutoClicker \
  --osx-bundle-identifier com.hthanh.autoclicker \
  --clean --noconfirm \
  autoclicker.py

echo ""
echo "Xong: dist/AutoClicker.app"
echo "Lần đầu mở sẽ bị macOS chặn (app chưa ký) -> chuột phải vào app > Open > Open."
echo "Rồi vào System Settings > Privacy & Security, cấp 2 quyền cho AutoClicker:"
echo "  - Accessibility   (để điều khiển chuột)"
echo "  - Input Monitoring (để bắt phím tắt F8 / ESC)"
