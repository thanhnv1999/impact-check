## Quy tắc bảo mật
- Không bao giờ đọc, hiển thị, hoặc log nội dung file .env
- Không hardcode API key, password, token vào code
- Khi cần dùng biến môi trường, chỉ gọi tên biến (VD: process.env.API_KEY)
  không được in giá trị thật ra
- Nếu thấy thông tin nhạy cảm trong code, cảnh báo ngay cho người dùng