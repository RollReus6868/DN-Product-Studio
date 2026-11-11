# DN Product Studio 1.5.0

Tool đăng sản phẩm lên website Dark Network: **ebook** (PDF + ảnh bìa) và **POD qua Spring**. Chạy trên Windows và macOS, tự cập nhật.

## Tải về

Vào mục **Releases** của kho này, tải file theo bảng trong ghi chú phát hành. Người dùng thường không cần cài Python.

## Dùng thế nào

Cài đặt một lần (trang **Hướng dẫn** trong tool ghi lại từng bước):

1. **Cài đặt › Tạo mã** rồi dán mã vào Supabase › dự án của web › Edge Functions › **Secrets**, tên `TOOL_API_TOKEN`.
2. **Kiểm tra kết nối** phải báo xanh.

Mỗi lô sản phẩm:

| Bước | Ebook | POD |
|---|---|---|
| 1 | Chọn thư mục có `Ten.pdf` + `Ten.png` cùng tên › **Quét** | Dán link Spring › **Lấy thông tin** |
| 2 | **Viết mô tả** › Copy prompt › dán vào Claude/ChatGPT › dán câu trả lời lại | như ebook |
| 3 | **Đăng lên web (bản nháp)** | như ebook |

Sau đó vào trang Admin của web xem lại và chuyển sang Published. Tool không bao giờ tự xuất bản hay xoá; sản phẩm đã có trên web chỉ bị ghi đè khi bạn đồng ý.

## Thanh toán

Khách trả tiền bằng **PayPal** ngay trên web (từ 11/2026, thay Lemon Squeezy). Web lấy tên và giá từ chính sản phẩm, nên tool chỉ cần đăng sản phẩm với giá đúng; không có gì phải cài cho phần thanh toán.

## Nén file (Cài đặt › Nén file khi tải lên)

- **Ảnh bìa ebook** đổi sang WebP, tối đa 640×960; **ảnh POD** WebP tối đa 1000×1500. Nhẹ hơn JPG/PNG nhiều lần.
- **PDF**: *Giữ nguyên chất lượng* (mặc định) nén mà không đổi chữ hay ảnh; *Nén mạnh* lưu lại các ảnh lớn trong sách ở JPEG 80%, tối đa 1800 px; *Tắt* tải đúng file gốc. Bản nén chỉ được dùng khi nhẹ hơn ít nhất 3% và mở được đủ số trang; tên file giữ nguyên.
- **Nén lại ảnh đang có trên web**: đổi các ảnh JPG/PNG đã đăng trước đây (trong kho Supabase của web) sang WebP và gắn vào đúng sản phẩm (hành động `media_list` / `set_media` của `toolApi`). Ảnh trong thư mục `/img` của web và ảnh đã là WebP được bỏ qua.

## Chạy từ mã nguồn

- Windows: nhấp đúp `install.bat` (một lần), sau đó `run.bat`.
- macOS: nhấp đúp `run_mac.command`.

## Cấu trúc mã

```
launcher.py   điểm khởi động, ghi DNProductStudio_crash.log khi lỗi     app_info.py  APP_VERSION + GITHUB_REPO
main.py       mở cửa sổ (pywebview) trên máy chủ nội bộ                 server.py    API nội bộ 127.0.0.1 + phục vụ ui/
scan.py       ghép PDF với ảnh bìa cùng tên                             pdfread.py   số trang + chữ của PDF
prompts.py    soạn prompt, đọc và kiểm tra câu trả lời JSON             spring.py    đọc trang Spring (JSON-LD, Open Graph)
webstore.py   gọi hàm toolApi của web, tải file, đăng nháp              storage.py   cấu hình, danh sách, mã bí mật (keyring)
shrink.py     nén ảnh sang WebP, nén PDF
updater.py    tự cập nhật qua GitHub Releases                           selfcheck.py tự kiểm tra bản đã đóng gói
ui/           giao diện (HTML/CSS/JS, phong cách Youwee)                tools/fake_site.py  website giả lập để thử
```

Dữ liệu của tool: `%APPDATA%\DNProductStudio\` (Windows) hoặc `~/Library/Application Support/DNProductStudio/` (macOS). Mã bí mật nằm trong Windows Credential Manager / macOS Keychain, không ghi ra file.

## Kiểm thử

```
python -m unittest discover -s tests -v      # logic + luồng đầy đủ với website giả lập
python tests/smoke_ui.py shots               # chạy giao diện thật trong Chromium, chụp ảnh (cần playwright)
python tools/check_repo.py
```

## Phát hành bản mới

1. Tăng `APP_VERSION` trong `app_info.py`, cập nhật `RELEASE_NOTES.md` và `VERSION.txt`.
2. Đẩy lên `main`, chờ Actions xanh trên cả Windows và macOS.
3. Actions › **Build & Release** › Run workflow › tick **publish**. Máy đang cài bản cũ sẽ thấy nút cập nhật trong Cài đặt.

Kho phải để **Public** thì tool mới đọc được Releases.
