# Minh Thy Chatbot - Your Customizable AI Companion
# Minh Thy Chatbot - Người bạn AI tùy chỉnh của bạn

Minh Thy is an interactive, highly customizable AI chatbot designed to provide a uniquely human-like conversational experience. Built with Flask and Socket.IO, Minh Thy adapts her personality and communication style based on your preferences, making every chat session engaging and personalized.

Minh Thy là một chatbot AI tương tác, có khả năng tùy chỉnh cao, được thiết kế để mang lại trải nghiệm trò chuyện độc đáo và giống con người. Được xây dựng với Flask và Socket.IO, Minh Thy điều chỉnh tính cách và phong cách giao tiếp của mình dựa trên sở thích của bạn, khiến mỗi phiên trò chuyện trở nên hấp dẫn và cá nhân hóa.

## Features / Tính năng

-   **Real-time Chat / Chat thời gian thực:** Engage in dynamic, real-time conversations. / Tham gia vào các cuộc trò chuyện năng động, thời gian thực.
-   **Customizable Personality / Cá tính có thể tùy chỉnh:** Adjust Minh Thy's "mood" (0-100) to influence her responses, tone, and overall persona. / Điều chỉnh "tâm trạng" của Minh Thy (0-100) để ảnh hưởng đến phản hồi, giọng điệu và tính cách tổng thể của cô ấy.
-   **Human-like Interactions / Tương tác giống con người:**
    -   Proactive messaging when you're inactive (within set hours). / Nhắn tin chủ động khi bạn không hoạt động (trong khung giờ nhất định).
    -   Simulated online/offline status and varied response delays. / Mô phỏng trạng thái online/offline và độ trễ phản hồi đa dạng.
    -   Human-like typing speed, pauses, and even occasional typos with corrections. / Tốc độ gõ giống người, có các khoảng dừng và thậm chí thỉnh thoảng có lỗi chính tả kèm sửa lỗi.
    -   Ability to use text formatting (bold, italics, strikethrough) and emojis for emphasis. / Khả năng sử dụng định dạng văn bản (in đậm, in nghiêng, gạch ngang) và biểu tượng cảm xúc để nhấn mạnh.
    -   Context-aware responses, remembering recent conversation points. / Phản hồi theo ngữ cảnh, ghi nhớ các điểm trò chuyện gần đây.
-   **Multi-part Messaging / Nhắn tin đa phần:** Minh Thy can send multiple short messages in sequence, mimicking natural human chat. / Minh Thy có thể gửi nhiều tin nhắn ngắn liên tiếp, mô phỏng cách trò chuyện tự nhiên của con người.
-   **Persistent Conversations / Cuộc trò chuyện bền vững:** All chat history, settings, and memories are saved locally in `chat_data.db`. / Toàn bộ lịch sử trò chuyện, cài đặt và ký ức được lưu trữ cục bộ trong `chat_data.db`.

## Installation / Cài đặt

### Prerequisites / Yêu cầu tiên quyết

-   Python 3.8+
-   `pip` (Python package installer)

### Steps / Các bước

1.  **Clone the repository / Tải repository về:**
    ```bash
    git clone https://github.com/duong-x-u/MinhThy_AIChat.git
    cd MinhThy_AIChat
    ```
2.  **Create a virtual environment (recommended) / Tạo môi trường ảo (khuyến nghị):**
    ```bash
    python -m venv venv
    source venv/bin/activate  # On Windows: .\venv\Scripts\activate
    ```
3.  **Install dependencies / Cài đặt các thư viện phụ thuộc:**
    ```bash
    pip install -r requirements.txt
    ```

## Configuration / Cấu hình

1.  **API Key:**
    Minh Thy uses the Bytez SDK to connect to Google's Gemini models. You need to provide your Bytez API key.
    Open `app.py` in the project directory and replace the placeholder API key with your actual Bytez API key:
    ```python
    sdk = Bytez("YOUR_BYTEZ_API_KEY_HERE") # Replace "YOUR_BYTEZ_API_KEY_HERE"
    ```
2.  **Adjust Socket.IO Path (if running standalone) / Điều chỉnh đường dẫn Socket.IO (nếu chạy độc lập):**
    If you are running this project as a standalone application (not as a sub-app of `Server_NEW`), you should adjust the Socket.IO connection path in `static/script.js`.
    Open `static/script.js` and change the line:
    `const socket = io({ path: '/duongdev/minhthy/socket.io' });`
    to:
    `const socket = io();`
    *(Nếu bạn chạy dự án này như một ứng dụng độc lập (không phải là một ứng dụng con của `Server_NEW`), bạn nên điều chỉnh đường dẫn kết nối Socket.IO trong `static/script.js`. Mở `static/script.js` và thay đổi dòng `const socket = io({ path: '/duongdev/minhthy/socket.io' });` thành `const socket = io();`)*

3.  **In-App Settings / Cài đặt trong ứng dụng:**
    You can customize Minh Thy's name, your name, and her "mood" (0-100) directly from the chatbot's web interface. These settings are saved per conversation.
    Bạn có thể tùy chỉnh tên của Minh Thy, tên của bạn và "tâm trạng" (mood) của cô ấy (0-100) trực tiếp từ giao diện web của chatbot. Các cài đặt này được lưu trữ cho mỗi cuộc trò chuyện.

## Usage / Cách sử dụng

1.  **Start the server / Khởi động máy chủ:**
    ```bash
    python app.py
    ```
    For background execution (recommended for production):
    Để chạy nền (khuyến nghị cho môi trường production):
    ```bash
    nohup python app.py &
    ```
2.  **Access the Chatbot / Truy cập Chatbot:**
    Open your web browser and navigate to `http://localhost:5000` (default port when running standalone).
    Mở trình duyệt web của bạn và điều hướng đến `http://localhost:5000` (cổng mặc định khi chạy độc lập).

## Contributing / Đóng góp

Contributions are welcome! If you have suggestions or improvements, please feel free to open an issue or submit a pull request.
Mọi đóng góp đều được chào đón! Nếu bạn có gợi ý hoặc cải tiến, xin vui lòng mở một issue hoặc gửi pull request.

## License / Giấy phép

This project is licensed under the MIT License - see the [LICENSE](LICENSE) file for details.
Dự án này được cấp phép theo Giấy phép MIT - xem file [LICENSE](LICENSE) để biết chi tiết.