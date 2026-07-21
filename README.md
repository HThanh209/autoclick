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

## Lưu nhiều bộ vị trí

Đặt tên rồi lưu, lần sau chọn tên là nạp lại toàn bộ vị trí + giãn cách, khỏi
chọn lại từ đầu:

1. Chọn xong các vị trí và giãn cách
2. Bấm **Lưu bộ này** → gõ tên (ví dụ *Trang chủ*)
3. Bộ khác: **Xóa hết** → chọn vị trí mới → lưu tên khác (*Menu sản phẩm*)
4. Về sau chọn tên ở ô **Bộ vị trí đã lưu** trên cùng là xong

Mỗi bộ nhớ luôn giãn cách riêng. Sửa vị trí trong một bộ thì phải bấm **Lưu bộ
này** lần nữa với đúng tên cũ mới ghi lại được. Đang chạy thì không đổi bộ được.

Tọa độ gắn với độ phân giải màn hình — đổi màn hình hoặc đổi mức phóng to thì bộ
cũ sẽ click trượt, phải chọn lại.

Lưu ở `profiles.json`:

| Hệ điều hành | Đường dẫn |
|---|---|
| Windows | `%APPDATA%\AutoClicker\profiles.json` |
| macOS | `~/Library/Application Support/AutoClicker/profiles.json` |

Ghi bằng cách viết file tạm rồi `os.replace` — tắt app giữa chừng không làm hỏng
file cũ. File hỏng thì app bỏ qua và khởi động với danh sách rỗng, không crash.

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

Mac chip Intel chưa có bản dựng sẵn — xem phần build tay bên dưới.

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

## Trang tải về

`web/index.html` là trang giới thiệu + link tải, `app.py` là web server tĩnh
phục vụ nó. Deploy lên host bất kỳ (vibehost, Render, Fly...):

```bash
python app.py          # mặc định cổng 8080, đọc biến môi trường PORT
```

Có sẵn `Dockerfile` nếu host dùng Docker. Không cần cài thư viện ngoài nào —
`app.py` dùng thuần stdlib. Health check: `GET /health` trả `{"status":"ok"}`.

> **Đừng deploy `autoclicker.py` lên server.** Nó là app desktop, cần màn hình
> và chuột thật. Container không có `libtk8.6.so`, và kể cả cài `tk-dev` + Xvfb
> thì nó vẫn không mở cổng HTTP nào nên health check luôn trượt — mà nếu có
> click thì cũng click lên màn hình ảo của server chứ không phải máy người
> dùng. Thứ đem deploy là `app.py`, không phải `autoclicker.py`.

## Lưu ý từng hệ điều hành

**Windows** — chạy được ngay, không cần cài gì. Hai lưu ý:

1. **Màn hình xanh "Windows protected your PC"** (Microsoft Defender SmartScreen)
   — không phải virus, chỉ là file chưa có điểm uy tín vì chưa ký số và còn ít
   lượt tải. Bấm **More info** → hiện nút **Run anyway** → bấm. Chỉ một lần duy
   nhất. Nút Run anyway bị giấu cho tới khi bấm More info.

2. **Click không ăn** vào một số game / phần mềm kế toán chạy quyền Admin → chạy
   AutoClicker bằng *Run as administrator*.

Muốn hết cảnh báo SmartScreen phải mua chứng chỉ ký số: OV ~200–400 USD/năm (uy
tín tích lũy dần), EV ~300–600 USD/năm (hết ngay). Chỉ đáng nếu phát hành ra
ngoài.

**macOS** — không cần cài thêm phần mềm nào, Python và thư viện đã nằm trong
`.app`. Nhưng có 3 bẫy:

1. **Gatekeeper chặn app chưa ký số.** Trên Sequoia (15) trở lên, cách chuột phải
   → Open đã bị Apple bỏ — phải mở app một lần cho nó bị chặn, rồi vào
   **System Settings → Privacy & Security → Open Anyway**. Sonoma (14) trở về
   trước thì chuột phải → Open → Open vẫn dùng được.

2. **Báo "app is damaged"** — không phải file hỏng, là cờ kiểm dịch gắn lên file
   tải từ mạng. Gỡ bằng:
   ```bash
   xattr -dr com.apple.quarantine /Applications/AutoClicker.app
   ```

3. **Quyền bắt buộc** trong **System Settings → Privacy & Security**:
   - **Accessibility** — không có thì tool mở được nhưng không click được gì.
   - **Input Monitoring** — để bắt hotkey F8/ESC. Không cấp thì chỉ mất hotkey.

   Cập nhật lên bản mới mà tool ngừng click: macOS giữ quyền gắn với file cũ →
   vào Accessibility xóa entry cũ (dấu `−`) rồi thêm lại app mới (dấu `+`).

Đây là cơ chế bảo mật của Apple, không có cách nào bỏ qua. Muốn hết hẳn cảnh báo
thì phải mua Apple Developer Program (99 USD/năm) để ký số và notarize.

## Vì sao không làm bản web?

Trình duyệt chạy trong sandbox: JavaScript chỉ thấy con trỏ khi nó nằm trong tab
web đó, và không có API nào cho phép trang web di chuyển hay click con chuột
thật của hệ điều hành. Nếu làm được thì mọi website đều chiếm quyền điều khiển
máy bạn. Vì vậy autoclick bắt buộc phải là app cài trên máy.
