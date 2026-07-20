# Auto Clicker

Tool click chuột tự động theo danh sách vị trí, chạy tuần tự và lặp vòng.
Chạy trên Windows và macOS.

## Dùng thế nào

1. Bấm **+ Chọn vị trí** → cửa sổ tool thu nhỏ xuống → click chuột trái vào chỗ
   cần click trên màn hình → tọa độ được lưu vào danh sách.
2. Lặp lại để thêm nhiều điểm. Tool sẽ click lần lượt điểm 1 → 2 → 3 → rồi quay
   lại điểm 1.
3. Đặt **giãn cách mỗi click** (ms). 1000 = 1 giây.
4. Bấm **BẮT ĐẦU**, hoặc phím **F8**.

| Phím | Tác dụng |
|---|---|
| `F8` | Bật / tắt, bấm được từ bất kỳ đâu |
| `ESC` | Dừng khẩn cấp |

## Chạy từ mã nguồn

```bash
pip install -r requirements.txt
python autoclicker.py
```

## Tải bản dựng sẵn

Vào tab [Releases](../../releases) tải file tương ứng, giải nén rồi mở lên chạy.
Không cần cài Python.

| Máy của bạn | File |
|---|---|
| Windows | `AutoClicker-Windows.zip` |
| Mac chip M1/M2/M3/M4 | `AutoClicker-macOS-AppleSilicon.zip` |
| Mac chip Intel | `AutoClicker-macOS-Intel.zip` |

## Tự build

Người dùng cuối không cần cài Python.

**Tự động (khuyên dùng)** — GitHub Actions dựng cả 3 bản trên máy thật của
GitHub rồi tự tạo Release:

```bash
git tag v1.0.0
git push origin v1.0.0
```

Muốn build thử mà chưa phát hành thì vào tab **Actions** → **Build** → **Run
workflow**, file nằm ở mục Artifacts.

**Thủ công trên Windows** → ra `dist/AutoClicker.exe`:

```bash
pip install -r requirements.txt
python -m PyInstaller --onefile --windowed --name AutoClicker --clean --noconfirm autoclicker.py
```

**Thủ công trên macOS** → ra `dist/AutoClicker.app`:

```bash
bash build_mac.sh
```

> Không build chéo được: `.exe` phải build trên máy Windows, `.app` phải build
> trên máy Mac. Đó là lý do dùng GitHub Actions — runner `macos-latest` và
> `macos-13` là máy Mac thật, miễn phí cho repo public.

## Lưu ý từng hệ điều hành

**Windows** — chạy được ngay. Nếu app đích chạy quyền Admin (một số game, phần
mềm kế toán) thì phải chạy AutoClicker bằng *Run as administrator*, nếu không
click sẽ không ăn. Windows Defender đôi khi cảnh báo file `.exe` chưa ký số —
chọn *More info* → *Run anyway*.

**macOS** — bắt buộc cấp quyền trong **System Settings → Privacy & Security**:

- **Accessibility** — để tool điều khiển được chuột.
- **Input Monitoring** — để bắt phím tắt F8 / ESC toàn cục. Không cấp thì tool
  vẫn chạy, chỉ mất hotkey, phải bấm nút trên cửa sổ.

Đây là cơ chế bảo mật của Apple, không có cách nào bỏ qua.

## Vì sao không làm bản web?

Trình duyệt chạy trong sandbox: JavaScript chỉ thấy con trỏ khi nó nằm trong tab
web đó, và không có API nào cho phép trang web di chuyển hay click con chuột
thật của hệ điều hành. Nếu làm được thì mọi website đều chiếm quyền điều khiển
máy bạn. Vì vậy autoclick bắt buộc phải là app cài trên máy.
