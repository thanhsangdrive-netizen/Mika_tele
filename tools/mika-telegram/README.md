# Mika Telegram Connector

Kết nối điều khiển trợ lý điện thoại Mika qua tin nhắn Telegram.

## 1. Giới thiệu

`mika-telegram` là một dịch vụ connector chạy trên máy tính, VPS hoặc Termux (trực tiếp trên Android). Nó nhận tin nhắn từ bạn trên Telegram và gửi yêu cầu tới Mika trên điện thoại qua REST API `/api/v1`.

- **Bảo mật tuyệt đối**: Chỉ người dùng đã xác thực (qua mã `/pair <code>` lần đầu) mới có quyền ra lệnh cho điện thoại.
- **Không phụ thuộc thư viện ngoài**: Viết hoàn toàn bằng Python standard library (chạy được ngay trên Python 3.10+ mà không cần `pip install` nặng nề).
- **Hoạt động 2 chiều**: Nhận lệnh từ Telegram, cập nhật trạng thái, hỏi người dùng khi cần thông tin và thông báo kết quả kèm ảnh chụp.

---

## 2. Cài đặt & Sử dụng

### Bước 1: Chuẩn bị
1. **Lấy Telegram Bot Token**: Chat với [@BotFather](https://t.me/BotFather) trên Telegram để tạo một Bot mới và lấy token (dạng `123456789:ABCdefGHI...`).
2. **Bật Task API trên Mika Phone**: Trong Mika trên điện thoại, vào **Cài đặt > Truy cập từ máy tính (Computer Access)**, bật Task API và lấy mã Token cùng địa chỉ IP (hoặc dùng cổng mặc định qua ADB `adb forward tcp:8080 tcp:8080`).

### Bước 2: Cài đặt connector
```bash
# Cài đặt từ thư mục repository:
pip install -e ./tools/mika-telegram
```
*(Hoặc chạy trực tiếp không cần install:* `python -m tools.mika-telegram.src.mika_telegram`*)*

### Bước 3: Cấu hình và chạy
```bash
# 1. Cấu hình (nhập bot token, URL điện thoại và token)
mika-telegram setup

# 2. Kiểm tra kết nối tới Telegram và Điện thoại
mika-telegram doctor

# 3. Khởi chạy
mika-telegram run
```

### Bước 4: Ghép nối (Pairing) lần đầu
Khi chạy `mika-telegram run` lần đầu tiên, màn hình terminal sẽ in ra mã ghép nối 10 phút, ví dụ:
```
[IMPORTANT] First pairing required:
Send this command to your Telegram bot within 10 minutes:
  /pair abcXYZ123
```
Bạn chỉ cần mở Telegram, vào bot vừa tạo và gửi tin nhắn `/pair abcXYZ123`. Kể từ lúc này, chỉ tài khoản Telegram của bạn mới có quyền điều khiển bot.

---

## 3. Các lệnh điều khiển trên Telegram

| Lệnh | Mô tả |
|---|---|
| `Nội dung bất kỳ` | Bắt đầu giao việc cho Mika (ví dụ: *"Mở YouTube bật nhạc Lofi"*, *"Đặt hẹn giờ 15 phút"*). |
| `/status` | Xem chi tiết tiến độ công việc đang chạy. |
| `/answer <câu trả lời>` | Trả lời câu hỏi khi Mika cần hỏi thêm thông tin (hoặc có thể reply trực tiếp tin nhắn của bot). |
| `/steer <hướng dẫn thêm>` | Thêm chỉ dẫn cho tác vụ đang chạy. |
| `/cancel` | Yêu cầu hủy bỏ tác vụ hiện tại. |
| `/new` | Xóa ngữ cảnh phiên chat cũ để bắt đầu cuộc trò chuyện mới. |
| `/help` | Xem danh sách các lệnh hỗ trợ. |
