# DN Product Studio 1.1.0

Tool chuyển sang làm việc với **website mới (Supabase)** thay cho Base44.

- File (ảnh bìa, PDF) tải thẳng vào kho của website, không còn giới hạn theo function; mỗi file tối đa 50 MB.
- **Gắn lại PDF cho sách cũ**: sau khi quét thư mục, tool báo sách nào trên web còn thiếu PDF và tải lên các file trùng tên có trong thư mục.
- Mã bí mật giờ đặt ở Supabase › Edge Functions › Secrets (`TOOL_API_TOKEN`).

Các tính năng từ bản 1.0.0:

- **Ebook**: quét thư mục PDF + ảnh bìa cùng tên, soạn prompt để Claude/ChatGPT viết mô tả, đặt giá, nén ảnh bìa, tải PDF lên kho riêng tư và tạo sản phẩm **bản nháp** trên web.
- **POD (Spring)**: dán link Spring, tool lấy tên, giá, ảnh rồi đăng bản nháp lên web.
- **Lemon Squeezy**: mọi ebook dùng chung một Variant ID; web tự đặt tên và giá từng cuốn lúc thanh toán.
- Tự cập nhật qua GitHub Releases, giao diện sáng/tối, 7 bộ màu.

## Tải bản nào?

| Máy của bạn | File |
|---|---|
| Windows (khuyên dùng) | `DNProductStudio-1.1.0-windows-setup.exe` |
| Windows, không muốn cài | `DNProductStudio-1.1.0-windows-portable.exe` |
| Mac chip Apple (M1 trở lên) | `DNProductStudio-1.1.0-mac-arm64.zip` |
| Mac chip Intel | `DNProductStudio-1.1.0-mac-x64.zip` |

Windows có thể hiện “Windows protected your PC”: bấm **More info › Run anyway** (app chưa mua chữ ký số).
Mac: giải nén, kéo vào Applications, lần đầu bấm chuột phải › **Open**.
