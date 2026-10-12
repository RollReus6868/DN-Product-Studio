# DN Product Studio 1.3.2

- **Huy hiệu đỏ trên icon** như thông báo trên điện thoại: icon **Tin nhắn** hiện số khách đang chờ trả lời, icon **Đơn hàng** hiện số đơn mới. Thu gọn thanh bên vẫn thấy.
- Tool tự kiểm tra đơn mới mỗi phút, kể cả khi bạn đang ở mục khác, và hiện thông báo ở góc trên khi có đơn mới.
- Mở mục Đơn hàng là số đơn mới tự về 0. Lần đầu mở bản này, các đơn cũ không tính là mới.

Từ bản 1.3.1:
- **Ảnh bìa ebook nhẹ hơn**: tool nén bìa còn khoảng 150 KB (trước là khoảng 350 KB) trước khi tải lên, vẫn nét trên web.
- Ảnh tải lên được trình duyệt của khách lưu lại 1 năm, khách quay lại không phải tải lại. Hai thay đổi này giúp website tốn ít băng thông Supabase hơn.
- Ảnh sản phẩm POD giữ kích thước như cũ.

Từ bản 1.3.0:
- **Tin nhắn** (mục mới): khách nhắn ở khung chat trên web sẽ hiện trong tool. Bấm vào tên khách để đọc, gõ câu trả lời rồi Enter để gửi; khách thấy ngay trong khung chat của họ.
- Thanh bên trái hiện **số khách đang chờ trả lời**. Khi có tin mới lúc bạn đang ở mục khác, tool hiện thông báo ở góc trên.
- Đây cùng là hộp thư với Admin › Tin nhắn trên web: trả lời ở đâu cũng được.

Từ bản 1.2.0:

- **Đơn hàng** (mục mới): xem các đơn khách đã mua trên web: email, thời gian mua, số cuốn và tên từng cuốn, số tiền, trạng thái (đã thanh toán / đã hoàn tiền), khách có tài khoản hay khách vãng lai. Phía trên có tổng số đơn, doanh thu, số sách đã bán.
- **Lượt truy cập** (mục mới): số khách và lượt xem trang hôm nay, 7 ngày, 30 ngày; biểu đồ khách mỗi ngày; các trang được xem nhiều nhất. Số liệu do website tự đếm, không tính lượt của bạn khi đang đăng nhập admin.
- Hai mục Đơn hàng và Lượt truy cập chỉ đọc, không sửa hay xoá gì trên web.

Từ bản 1.1.1: file PDF tải lên giữ nguyên tên gốc.

Từ bản 1.1.0: làm việc với website mới (Supabase), tải file thẳng vào kho (tối đa 50 MB mỗi file), gắn lại PDF cho sách cũ.

Các tính năng từ bản 1.0.0:

- **Ebook**: quét thư mục PDF + ảnh bìa cùng tên, soạn prompt để Claude/ChatGPT viết mô tả, đặt giá, nén ảnh bìa, tải PDF lên kho riêng tư và tạo sản phẩm **bản nháp** trên web.
- **POD (Spring)**: dán link Spring, tool lấy tên, giá, ảnh rồi đăng bản nháp lên web.
- **Lemon Squeezy**: mọi ebook dùng chung một Variant ID; web tự đặt tên và giá từng cuốn lúc thanh toán.
- Tự cập nhật qua GitHub Releases, giao diện sáng/tối, 7 bộ màu.

## Tải bản nào?

| Máy của bạn | File |
|---|---|
| Windows (khuyên dùng) | `DNProductStudio-1.3.0-windows-setup.exe` |
| Windows, không muốn cài | `DNProductStudio-1.3.0-windows-portable.exe` |
| Mac chip Apple (M1 trở lên) | `DNProductStudio-1.3.0-mac-arm64.zip` |
| Mac chip Intel | `DNProductStudio-1.3.0-mac-x64.zip` |

Windows có thể hiện “Windows protected your PC”: bấm **More info › Run anyway** (app chưa mua chữ ký số).
Mac: giải nén, kéo vào Applications, lần đầu bấm chuột phải › **Open**.
