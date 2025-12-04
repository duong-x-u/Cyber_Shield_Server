# app.py
import os
import logging
from dotenv import load_dotenv
load_dotenv()

# Import các thư viện cần thiết
import eventlet
from eventlet import wsgi
from flask import Flask, jsonify, render_template, request, abort
import re
from flask_cors import CORS
from werkzeug.middleware.dispatcher import DispatcherMiddleware
from socketio import WSGIApp

from extensions import limiter

# Import các ứng dụng con và các instance socketio của chúng
from api.analyze import analyze_endpoint
from api.admin import admin_endpoint
from duongdev.TO1_Chat.app import app as to1_chat_app, socketio as to1_chat_socketio
from duongdev.anmqpan.app import app as qpan_app, socketio as qpan_socketio
from duongdev.minhthy.app import app as minhthy_app, socketio as minhthy_socketio
from duongdev.love.app import app as love_app, socketio as love_socketio # Commented out
from duongdev.share.app import app as share_app, socketio as share_socketio


# Cấu hình logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# --- Middleware tùy chỉnh để thêm Flask app context ---
class FlaskAppMiddleware:
    """
    Middleware này sẽ "tiêm" instance của Flask app vào môi trường WSGI.
    Điều này cần thiết để Flask-SocketIO có thể tạo app context khi xử lý event.
    """
    def __init__(self, wsgi_app, flask_app):
        self.wsgi_app = wsgi_app
        self.flask_app = flask_app

    def __call__(self, environ, start_response):
        environ['flask.app'] = self.flask_app
        return self.wsgi_app(environ, start_response)

# --- Ứng dụng Flask gốc (chỉ xử lý các route không thuộc ứng dụng con) ---
app = Flask(__name__)
CORS(app)

limiter.init_app(app)

app.secret_key = os.environ.get('SECRET_KEY', 'default-secret-key-for-dev-only')
if app.secret_key == 'default-secret-key-for-dev-only':
    logger.warning("Sử dụng SECRET_KEY mặc định. Hãy thay đổi nó trong môi trường production!")

# Đăng ký blueprint cho ứng dụng gốc

@app.before_request
def firewall():
    """Một tường lửa ứng dụng web đơn giản để chặn các yêu cầu quét lỗ hổng phổ biến."""
    path = request.path
    
    # Danh sách các mẫu regex để chặn.
    # Bao gồm các mẫu quét CMS, truy cập tệp ẩn, và path traversal.
    blocked_patterns = [
        r'\/wp-admin',
        r'\/wp-login\.php',
        r'\/xmlrpc\.php',
        r'\/\.git',
        r'\/\.env',
        r'\/\.\.', # Path traversal
        r'\/phpmyadmin',
        r'\/pma'
    ]
    
    for pattern in blocked_patterns:
        if re.search(pattern, path, re.IGNORECASE):
            # Ghi log lại hành vi đáng ngờ
            logger.warning(
                f"[FIREWALL] Blocked malicious path pattern '{pattern}' from IP {request.remote_addr} on path {path}"
            )
            # Trả về lỗi 403 Forbidden
            abort(403)

app.register_blueprint(analyze_endpoint, url_prefix='/api')
app.register_blueprint(admin_endpoint)

@app.route('/')
def home():
    return render_template('index.html')

@app.route('/health')
def health_check():
    return jsonify({
        'status': '🟢 Systems Nominal',
        'hp': '100/100',
        'mana': '∞',
        'latency_ms': 5,
        'service': 'cybershield-backend',
        'note': 'Tế đàn còn ổn'
    })

@app.route('/duongdev')
def duongdev_home():
    return render_template('duongdev.html')

# --- Security Headers Middleware ---
@app.after_request
def add_security_headers(response):
    """Thêm các header bảo mật vào mỗi response."""
    # Ngăn trình duyệt tự ý thay đổi content-type (MIME-sniffing).
    response.headers['X-Content-Type-Options'] = 'nosniff'
    # Ngăn trang web bị nhúng vào iframe trên domain khác (chống clickjacking).
    response.headers['X-Frame-Options'] = 'SAMEORIGIN'
    
    # Chính sách An toàn Nội dung (Content Security Policy) chi tiết hơn
    # Cho phép các nguồn cần thiết, giải quyết các lỗi "Refused to load/apply"
    csp_policy = "default-src 'self';" \
                 "script-src 'self' 'unsafe-inline' https://static.cloudflareinsights.com https://cdnjs.cloudflare.com https://cdn.socket.io;" \
                 "style-src 'self' 'unsafe-inline' https://fonts.googleapis.com https://cdnjs.cloudflare.com;" \
                 "img-src 'self' data:;" \
                 "font-src 'self' https://fonts.gstatic.com;" \
                 "connect-src 'self' ws: wss:;" # Cho phép kết nối WebSocket (SocketIO)

    response.headers['Content-Security-Policy'] = csp_policy
    return response

# --- Bọc mỗi ứng dụng con thành một WSGI app hoàn chỉnh (Flask + SocketIO) ---
to1_chat_wsgi_raw = WSGIApp(to1_chat_socketio.server, to1_chat_app)
qpan_wsgi_raw = WSGIApp(qpan_socketio.server, qpan_app)
minhthy_wsgi_raw = WSGIApp(minhthy_socketio.server, minhthy_app)
love_wsgi_raw = WSGIApp(love_socketio.server, love_app) # Commented out
share_wsgi_raw = WSGIApp(share_socketio.server, share_app) # NEW

# --- Sử dụng middleware tùy chỉnh để thêm app context ---
to1_chat_wsgi = FlaskAppMiddleware(to1_chat_wsgi_raw, to1_chat_app)
qpan_wsgi = FlaskAppMiddleware(qpan_wsgi_raw, qpan_app)
minhthy_wsgi = FlaskAppMiddleware(minhthy_wsgi_raw, minhthy_app)
love_wsgi = FlaskAppMiddleware(love_wsgi_raw, love_app) # Commented out
share_wsgi = FlaskAppMiddleware(share_wsgi_raw, share_app) # NEW


# --- Tạo bộ điều phối (Dispatcher) để kết hợp tất cả các ứng dụng ---
application = DispatcherMiddleware(app, {
    '/duongdev/to1-chat': to1_chat_wsgi,
    '/duongdev/qpan': qpan_wsgi,
    '/duongdev/minhthy': minhthy_wsgi,
    '/duongdev/love': love_wsgi, # Commented out
    '/duongdev/share': share_wsgi, # Changed from share_app to share_wsgi
})

# --- Error Handlers (chỉ hoạt động cho ứng dụng gốc) ---
@app.errorhandler(404)
def not_found(error):
    return render_template('404.html'), 404

@app.errorhandler(500)
def internal_error(error):
    logger.error(f"Internal error: {str(error)}")
    return jsonify({'error': '💥 500: Quay về phòng thủ. Tế đàn bị tấn công'}), 500


# --- Khởi chạy Server ---
if __name__ == '__main__':
    port = int(os.environ.get('PORT', 10000))
    logger.info(f"🚀 Starting combined server on http://localhost:{port}")
    logger.info(f"Truy cập vào Minh Thy qua: http://localhost:{port}/duongdev/minhthy")
    # Sử dụng server của eventlet để chạy bộ điều phối 'application'
    # Điều này đảm bảo các kết nối WebSocket được xử lý đúng cách
    wsgi.server(eventlet.listen(('', port)), application)