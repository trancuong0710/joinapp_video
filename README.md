# Video Toolkit Pro - Ghép Nối Video & Tải YouTube Tốc Độ Cao

Ứng dụng desktop hiện đại chạy trên Windows kết hợp 2 tính năng mạnh mẽ: **Ghép nối video chuyên nghiệp** và **Tải video/âm thanh YouTube chất lượng cao**.

---

## 🌟 2 Chức Năng Chính

### 1. 🎬 Ghép Nối Video MP4 Chuyên Nghiệp (Offline)
- **Ghép Siêu Tốc (Stream Copy - Khuyên dùng):** Nối xong trong vài giây mà không làm giảm 1% chất lượng nào (100x - 300x).
- **Mã Hóa Chuẩn Hóa (Tăng tốc phần cứng GPU):** Tận dụng GPU NVIDIA NVENC, AMD AMF, Intel QSV hoặc CPU đa luồng để chuẩn hóa độ phân giải (1080p, 720p, 4K) và FPS.
- **Chọn Audio Track theo từng file:** Hỗ trợ phim/clip có nhiều luồng tiếng (Tiếng Việt, Tiếng Anh, thuyết minh, 5.1ch) hoặc tắt tiếng.
- **Kéo & Thả (Drag and Drop):** Kéo thả video hoặc cả thư mục từ máy tính vào giao diện.
- **Xem trước Thumbnail & Thông số:** Thời lượng, độ phân giải, FPS, dung lượng file, codec.

### 2. 📥 Tải Video & Âm Thanh Từ YouTube
- **Nhập link YouTube:** Hỗ trợ link video thường, shorts, youtu.be. Có nút dán nhanh từ clipboard và xóa link.
- **Hiển thị đầy đủ danh sách link tải:**
  - **Video MP4 chuẩn:** 4K Ultra HD, 2K, 1080p Full HD, 720p HD, 480p, 360p (tự động ghép video + âm thanh chất lượng tốt nhất).
  - **Chỉ Âm thanh:** Tách riêng âm thanh M4A / AAC / MP3 gốc chất lượng cao cho nhạc, podcast.
  - **Luồng trực tiếp (Direct Streams):** Hiển thị chi tiết từng luồng video/audio cùng link download trực tiếp (hỗ trợ copy link dán vào IDM hoặc trình duyệt).
- **Tải về máy chỉ với 1 click:** Nhấn nút **⬇️ Tải Về Máy**, chọn thư mục lưu và ứng dụng sẽ tự động tải về.
- **Theo dõi tiến trình trực quan:** Xem % tiến trình, dung lượng đã tải, tốc độ tải (MB/s), thời gian còn lại (ETA).
- **Tích hợp tiện lợi sau khi tải:** Mở video xem ngay, mở thư mục chứa file, hoặc bấm **➕ Đưa Vào Ghép Video** để tự động thêm vào danh sách nối video!

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
- `Ctrl + 1`: Chuyển sang màn hình **Ghép Video**
- `Ctrl + 2` hoặc `Ctrl + D`: Chuyển sang màn hình **Tải Video YouTube**
- `Enter` trong ô nhập link YouTube: Bắt đầu phân tích & lấy link tải ngay
