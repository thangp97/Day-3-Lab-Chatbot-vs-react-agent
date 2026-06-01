# Frontend (Vinmec Medchat UI)

React chat UI for the local Ollama-backed chatbot, powered by Vite.

## Cài đặt (Installation)

1. Đảm bảo bạn đã cài đặt Node.js (khuyến nghị phiên bản 16 trở lên).
2. Mở terminal và di chuyển vào thư mục `frontend`:
   ```bash
   cd frontend
   ```
3. Cài đặt các thư viện phụ thuộc (dependencies) thông qua npm:
   ```bash
   npm install
   ```

## Chạy ứng dụng (Running the Development Server)

Để khởi động giao diện trong môi trường phát triển:

```bash
npm run dev
```

Sau khi chạy lệnh, hãy mở trình duyệt và truy cập vào đường dẫn được hiển thị trên terminal (thường là `http://localhost:5173`).

## Build cho Production (Building for Production)

Để biên dịch và đóng gói ứng dụng cho môi trường production:

```bash
npm run build
```

Nếu bạn muốn chạy thử bản build trên local để kiểm tra:

```bash
npm run preview
```
