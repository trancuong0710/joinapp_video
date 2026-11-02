# Video Toolkit Pro - Nối Video • Cắt Video • Tải YouTube Tốc Độ Cao

Ứng dụng desktop hiện đại chạy trên Windows kết hợp 3 tính năng mạnh mẽ: **Ghép nối video chuyên nghiệp**, **Cắt video siêu tốc** và **Tải video/âm thanh YouTube chất lượng cao**.

---

## 🌟 3 Chức Năng Chính

### 1. 🎬 Ghép Nối Video MP4 Chuyên Nghiệp (Offline)
- **Ghép Siêu Tốc (Stream Copy - Khuyên dùng):** Nối xong trong vài giây mà không làm giảm 1% chất lượng nào (100x - 300x).
- **Mã Hóa Chuẩn Hóa (Tăng tốc phần cứng GPU):** Tận dụng GPU NVIDIA NVENC, AMD AMF, Intel QSV hoặc CPU đa luồng để chuẩn hóa độ phân giải (1080p, 720p, 4K) và FPS.
- **Chọn Audio Track theo từng file:** Hỗ trợ phim/clip có nhiều luồng tiếng (Tiếng Việt, Tiếng Anh, thuyết minh, 5.1ch) hoặc tắt tiếng.
- **Kéo & Thả (Drag and Drop):** Kéo thả video hoặc cả thư mục từ máy tính vào giao diện.
- **Xem trước Thumbnail & Thông số:** Thời lượng, độ phân giải, FPS, dung lượng file, codec.
- **Nút "✂️ Cắt" trên từng video:** Bấm là chuyển ngay sang tab Cắt Video với file đó được nạp sẵn.

### 2. ✂️ Cắt & Rút Gọn Video (Luôn Xuất Định Dạng MP4)
- **Luôn xuất file MP4:** Bất kể file đầu vào là định dạng gì (MKV, AVI, MOV, WEBM, FLV, TS,...), file kết quả sau khi cắt **luôn luôn ở định dạng MP4 chuẩn**, xem mượt mà trên mọi thiết bị và nền tảng.
- **2 chế độ cắt thông minh:**
  - **⚡ Cắt Siêu Tốc (Stream Copy):** Xử lý chỉ trong 1 - 2 giây, giữ nguyên 100% độ sắc nét gốc không nén lại.
  - **🎯 Mã Hóa Chuẩn Hóa (Frame-Accurate):** Cắt chuẩn xác từng khung hình millisecond, chuẩn hóa codec H.264 + AAC.
- **Điều khiển thời gian linh hoạt:**
  - Kéo thanh trượt (slider) trực quan cho mốc Bắt đầu & Kết thúc.
  - Ô nhập thời gian chính xác `HH:MM:SS` hoặc có số lẻ giây `HH:MM:SS.s`.
  - Các nút tinh chỉnh nhanh: `[ 00:00:00 ]`, `[ Cuối Video ]`, `[ -5s ]`, `[ -1s ]`, `[ +1s ]`, `[ +5s ]`.
- **Hỗ trợ chọn Audio Track:** Giữ lại track âm thanh mong muốn hoặc tắt tiếng khi cắt.
- **Tích hợp tiện lợi:** Sau khi cắt, có thể bấm **▶ Xem File Vừa Cắt**, **📂 Mở Thư Mục** hoặc **➕ Đưa Vào Ghép Video** để nối tiếp đoạn clip vừa cắt!

### 3. 📥 Tải Video & Âm Thanh Từ YouTube
- **Nhập link YouTube:** Hỗ trợ link video thường, shorts, youtu.be. Có nút dán nhanh từ clipboard và xóa link.
- **Hiển thị đầy đủ danh sách link tải:**
  - **Video MP4 chuẩn:** 4K Ultra HD, 2K, 1080p Full HD, 720p HD, 480p, 360p (tự động ghép video + âm thanh chất lượng tốt nhất).
  - **Chỉ Âm thanh:** Tách riêng âm thanh M4A / AAC / MP3 gốc chất lượng cao cho nhạc, podcast.
  - **Luồng trực tiếp (Direct Streams):** Hiển thị chi tiết từng luồng video/audio cùng link download trực tiếp (hỗ trợ copy link dán vào IDM hoặc trình duyệt).
- **Tải về máy chỉ với 1 click:** Nhấn nút **⬇️ Tải Về Máy**, chọn thư mục lưu và ứng dụng sẽ tự động tải về.
- **Theo dõi tiến trình trực quan:** Xem % tiến trình, dung lượng đã tải, tốc độ tải (MB/s), thời gian còn lại (ETA).
- **Tích hợp sau khi tải:** Mở xem video, mở thư mục, bấm **✂️ Cắt Video Này** để rút gọn ngay, hoặc **➕ Đưa Vào Ghép Video**!

---

## 🚀 Cách khởi chạy ứng dụng

### Cài đặt thư viện phụ thuộc:
```bash
pip install -r requirements.txt
```

### Cách 1: Chạy file `.bat` (Khuyên dùng)
- Nhấp đúp chuột vào file **`run.bat`**.

### Cách 2: Chạy bằng dòng lệnh Python
```bash
python main.py
# hoặc
py main.py
```

### Phím tắt nhanh trong ứng dụng:
- `Ctrl + 1`: Chuyển sang màn hình **🎬 Ghép Video**
- `Ctrl + 2` hoặc `Ctrl + X`: Chuyển sang màn hình **✂️ Cắt Video**
- `Ctrl + 3` hoặc `Ctrl + D`: Chuyển sang màn hình **📥 Tải Video YouTube**
- `Enter` trong ô nhập link YouTube: Bắt đầu phân tích & lấy link tải ngay
