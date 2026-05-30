# BÁO CÁO TIẾN ĐỘ DỰ ÁN PTS2GG (HANDOFF)

**Ngày cập nhật cuối:** 30/05/2026
**Trạng thái hiện tại:** 🟢 **Hoạt động ổn định (Bản Rút Gọn)**

## 1. Thành quả đã đạt được (Tính năng lõi)
Dự án hiện tại đã hoạt động cực kỳ mượt mà với luồng xử lý chính:
- **Inpaint 1-Click:** Khoanh vùng chọn trong Photoshop -> Điền Prompt -> Chờ -> Tự động dán đè ảnh mới lên đúng tọa độ vùng chọn cũ.
- **Xử lý ảnh tự động:** Đã tối ưu hóa luồng chờ trên giao diện Google Gemini để **tự động bóc tách được link ảnh gốc 4K** (URL `https://*.googleusercontent.com/` có đuôi `=s0`).
- **Cơ chế tải ngầm (Background Fetch):** Không còn tình trạng giật lag hay ép mở giao diện Lightbox trên trình duyệt. Code tự động chờ ảnh nâng cấp lên HD trong nền.
- **Bộ lọc bảo vệ:** Đã thêm cơ chế kiểm tra kích thước khắt khe. Nếu ảnh tải về từ Gemini <= 1024px, hệ thống sẽ tự động vứt bỏ và "đứng rình" cho đến khi lấy được bản to mới thôi.
- **Server trung gian (Bridge):** Chạy ổn định qua cổng `8765`, không bị kẹt port, có tính năng tự động tắt/bật từ trong PTS.

## 2. Các tính năng đã gỡ bỏ & Lý do
- 🔴 **Chế độ Biến thể (3 Variants / Retry):** ĐÃ BỊ XÓA BỎ.
  - *Lý do:* Nút bấm này trước đây ép Photoshop tạo 1 vòng lặp gửi 3 lệnh liên tiếp. Tuy nhiên, việc nhận diện lại một thành phần (DOM element) cũ trên web Gemini và bắt nó nhả ra tấm hình nâng cấp chất lượng cao cực kỳ khó khăn và rủi ro. Tính năng Retry này gây nhiễu loạn luồng tải ảnh gốc, khiến ảnh tải về bị tụt độ phân giải xuống còn 1024x1024.
  - *Kết quả:* Đã cắt bỏ sạch sẽ trên giao diện UXP, trả lại 1 nút `GENERATE` duy nhất, hoạt động trơn tru 1 lệnh/lần.

## 3. Kế hoạch khi làm lại dự án (Next Steps)
Khi bạn hoặc người khác tiếp quản lại dự án này, vui lòng đọc các bước sau:

1. **Đóng gói dự án (Packaging):**
   - Đóng gói Extension: Bật Developer mode trong `chrome://extensions/` và Pack folder `extension` thành file `.crx`.
   - Đóng gói Plugin Photoshop: Dùng Adobe UXP Developer Tool để Pack thành file `.ccx`.
   - Đóng gói Server Node.js: Cài thư viện `pkg` (lệnh: `npm i -g pkg`), sau đó vào thư mục `bridge` gõ `pkg server.js --targets node18-win-x64 --output DB9_Server.exe` để tạo 1 file chạy độc lập cho khách không cần rườm rà.

2. **Phát triển lại tính năng Biến thể (Nếu cần):**
   - Đừng tái sử dụng vòng lặp `for` 3 lần ngây ngô trong `uxp-plugin/index.js` như cũ.
   - Hãy thiết kế để Gemini Gen 1 lúc ra luôn 3 tấm ảnh, sau đó Extension Chrome sẽ bóc tách cả 3 tấm này gởi về 1 lượt cho Photoshop cho người dùng chọn, chứ không nên chia thành 3 lệnh tuần tự làm kẹt hàng chờ của Gemini.

## 4. Các file quan trọng nhất cần nắm
- `uxp-plugin/index.js`: File điều khiển giao diện PTS. Cứ mò vào hàm `runGenerate` là hiểu luồng gọi.
- `extension/content/provider-gemini.js`: Trái tim của toàn bộ Extension. Chịu trách nhiệm tương tác DOM với Gemini. Chú ý 2 hàm quan trọng nhất:
  - `waitForOutput()`: Nằm vùng chờ ảnh xuất hiện và nâng cấp lên HTTPS.
  - `downloadHD()`: Thợ săn link `=s0`, kiểm tra kích thước > 1024px và kéo ảnh về qua CDP.

---
*Chúc dự án thương mại hóa thành công!*
