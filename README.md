# Cyber Shield API - Phân Tích An Ninh Mạng

## 1. Giới thiệu

**Cyber Shield API** là một dịch vụ web được xây dựng bằng Python (Flask) với mục tiêu phân tích và phát hiện các mối đe dọa tiềm ẩn trong các đoạn văn bản tiếng Việt. Dự án sử dụng sức mạnh của mô hình ngôn ngữ lớn (LLM) từ Google (Gemini) để đánh giá nội dung, xác định các rủi ro như lừa đảo, bạo lực, ngôn từ kích động thù địch, và các nội dung nguy hiểm khác.

Giao diện người dùng đơn giản được cung cấp để dễ dàng kiểm tra và tương tác với API.

## 2. Chức năng chính

- **Phân tích nội dung văn bản:**
  - Tiếp nhận văn bản qua API endpoint `/api/analyze`.
  - Sử dụng một AI phân tích (tên là "Anna") được huấn luyện đặc biệt để hiểu ngữ cảnh và ý định trong tin nhắn tiếng Việt, giảm thiểu việc báo động nhầm với các cuộc trò chuyện thông thường hoặc đùa giỡn.
- **Kiểm tra URL:**
  - Tự động trích xuất và kiểm tra các URL có trong văn bản bằng **Google Safe Browsing API** để phát hiện các liên kết độc hại.
- **Phân loại mối đe dọa:**
  - Phân loại các nội dung nguy hiểm vào các nhóm cụ thể: `scam` (lừa đảo), `violence` (bạo lực), `hate_speech` (ngôn từ thù địch), `anti_state` (chống phá nhà nước), `other` (khác).
- **Cảnh báo và Ghi nhận:**
  - Khi phát hiện một mối đe dọa nghiêm trọng, hệ thống có khả năng tự động gửi email cảnh báo đến quản trị viên.
  - Lưu lại lịch sử các lần phân tích vào Google Sheets để theo dõi và cải thiện mô hình.

## 3. Công nghệ sử dụng

- **Backend:** Python, Flask
- **AI Model:** Google Gemini Pro
- **APIs:** Google Safe Browsing, Gmail API, Google Sheets API
- **Frontend:** HTML, CSS, JavaScript (cho trang demo)
- **Deployment:** Cấu hình cho Gunicorn, sẵn sàng để triển khai trên các nền tảng như Render, Heroku.

## 4. Cách hoạt động

1.  **Client** gửi một yêu cầu `POST` đến `/api/analyze` với nội dung văn bản cần kiểm tra.
2.  **Flask App** nhận yêu cầu.
3.  **Anna-AI (Gemini)** phân tích văn bản và trả về một cấu trúc JSON chứa kết quả:
    - `is_dangerous`: `true` hoặc `false`.
    - `reason`: Giải thích ngắn gọn cho kết quả.
    - `types`: Loại mối đe dọa.
    - `score`: Điểm nguy hiểm (từ 0 đến 5).
    - `recommend`: Khuyến nghị hành động.
4.  Nếu có **URL**, hệ thống sẽ gọi Google Safe Browsing API để kiểm tra.
5.  Nếu kết quả là nguy hiểm, một tác vụ nền sẽ được kích hoạt để **gửi email cảnh báo**.
6.  Một tác vụ nền khác sẽ **lưu kết quả** vào Google Sheets.
7.  **Flask App** trả kết quả phân tích về cho client.

## 5. Hướng dẫn cài đặt và chạy dự án

### Yêu cầu

- Python 3.9+
- `pip`

### Các bước cài đặt

1.  **Clone repository:**
    ```bash
    git clone <your-repo-url>
    cd Cyber-Shield-API-Ver-main
    ```

2.  **Tạo môi trường ảo:**
    ```bash
    python -m venv venv
    source venv/bin/activate  # Trên Windows: venv\Scripts\activate
    ```

3.  **Cài đặt các thư viện cần thiết:**
    ```bash
    pip install -r requirements.txt
    ```

4.  **Cấu hình biến môi trường:**
    Tạo một file `.env` ở thư mục gốc và thêm các biến môi trường cần thiết. Đây là những thông tin nhạy cảm và không nên được đưa vào code.
    ```
    # Google API Keys (lấy từ Google AI Studio hoặc Google Cloud Console)
    # Có thể là một hoặc nhiều key, cách nhau bởi dấu phẩy
    GOOGLE_API_KEYS=your_google_api_key_1,your_google_api_key_2

    # Google Safe Browsing API Key
    SAFE_BROWSING_API_KEY=your_safe_browsing_api_key

    # Đường dẫn đến file token của Gmail API (để gửi email)
    # Ví dụ: /etc/secrets/token.json hoặc secrets/token.json
    GMAIL_TOKEN_PATH=secrets/token.json

    # ID của Google Sheet để lưu lịch sử
    GOOGLE_SHEET_ID=your_google_sheet_id
    ```
    *Lưu ý:* Bạn cần phải có file `secrets/google_credentials.json` và `secrets/token.json` để các chức năng liên quan đến Google API (Gmail, Sheets) hoạt động.

5.  **Chạy ứng dụng:**
    - **Để phát triển (development):**
      ```bash
      flask run
      ```
    - **Để triển khai (production):**
      Sử dụng Gunicorn:
      ```bash
      gunicorn --bind 0.0.0.0:10000 app:app
      ```

## 6. Cách kiểm tra (Test)

Bạn có thể sử dụng file `Cach_test.txt` để xem hướng dẫn chi tiết cách gửi yêu cầu đến API từ trình duyệt.
