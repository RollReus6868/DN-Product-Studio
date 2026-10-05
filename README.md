# DN Product Studio 1.1.1

Tool đăng sản phẩm lên website Dark Network: **ebook** (PDF + ảnh bìa) và **POD qua Spring**. Chạy trên Windows và macOS, tự cập nhật.

## Tải về

Vào mục **Releases** của kho này, tải file theo bảng trong ghi chú phát hành. Người dùng thường không cần cài Python.

## Dùng thế nào

Cài đặt một lần (trang **Hướng dẫn** trong tool ghi lại từng bước):

1. **Cài đặt › Tạo mã** rồi dán mã vào Supabase › dự án của web › Edge Functions › **Secrets**, tên `TOOL_API_TOKEN`.
2. Trên Lemon Squeezy tạo **một** sản phẩm “Ebook” chung, dán Variant ID của nó vào **Cài đặt**.
3. **Kiểm tra kết nối** phải báo xanh.

Mỗi lô sản phẩm:

| Bước | Ebook | POD |
|---|---|---|
| 1 | Chọn thư mục có `Ten.pdf` + `Ten.png` cùng tên › **Quét** | Dán link Spring › **Lấy thông tin** |
| 2 | **Viết mô tả** › Copy prompt › dán vào Claude/ChatGPT › dán câu trả lời lại | như ebook |
| 3 | **Đăng lên web (bản nháp)** | như ebook |

Sau đó vào trang Admin của web xem lại và chuyển sang Published. Tool không bao giờ tự xuất bản hay xoá; sản phẩm đã có trên web chỉ bị ghi đè khi bạn đồng ý.

## Tool làm gì với Lemon Squeezy

API của Lemon Squeezy không cho tạo sản phẩm. Vì vậy mọi ebook dùng chung một Variant ID; lúc khách bấm Buy Now, website tạo phiên thanh toán với **tên và giá của đúng cuốn đó** (hàm `createEbookCheckout` của web).

## Chạy từ mã nguồn

- Windows: nhấp đúp `install.bat` (một lần), sau đó `run.bat`.
- macOS: nhấp đúp `run_mac.command`.

## Cấu trúc mã

```
launcher.py   điểm khởi động, ghi DNProductStudio_crash.log khi lỗi     app_info.py  APP_VERSION + GITHUB_REPO
main.py       mở cửa sổ (pywebview) trên máy chủ nội bộ                 server.py    API nội bộ 127.0.0.1 + phục vụ ui/
scan.py       ghép PDF với ảnh bìa cùng tên                             pdfread.py   số trang + chữ của PDF
prompts.py    soạn prompt, đọc và kiểm tra câu trả lời JSON             spring.py    đọc trang Spring (JSON-LD, Open Graph)
webstore.py   gọi hàm toolApi của web, nén ảnh, tải file, đăng nháp     storage.py   cấu hình, danh sách, mã bí mật (keyring)
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
