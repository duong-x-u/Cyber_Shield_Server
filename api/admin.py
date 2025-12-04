# api/admin.py
import functools
import json
import os
import psutil # << IMPORT MỚI
from flask import (
    Blueprint, request, render_template, redirect, url_for, session, flash, jsonify
)
from api.utils import get_dynamic_config # Import hàm đọc config dùng chung

admin_endpoint = Blueprint('admin', __name__, url_prefix='/admin')

# Lấy đường dẫn gốc của dự án
PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))


# --- HÀM BẢO MẬT ---
def is_safe_path(path_to_check):
    """
    Kiểm tra để đảm bảo đường dẫn file là an toàn và nằm trong thư mục dự án.
    Ngăn chặn các cuộc tấn công Path Traversal (ví dụ: ../../etc/passwd).
    """
    requested_path = os.path.abspath(os.path.join(PROJECT_ROOT, path_to_check))
    return requested_path.startswith(PROJECT_ROOT)

# --- DECORATOR ĐỂ BẢO VỆ ---
def login_required(view):
    @functools.wraps(view)
    def wrapped_view(**kwargs):
        if 'admin_logged_in' not in session:
            if request.path.startswith('/api/'):
                return jsonify(error="Authentication required"), 401
            return redirect(url_for('admin.login'))
        return view(**kwargs)
    return wrapped_view

# --- ROUTE GIAO DIỆN (UI) ---
@admin_endpoint.route('/login', methods=['GET', 'POST'])
def login():
    # ... (giữ nguyên)
    if 'admin_logged_in' in session:
        return redirect(url_for('admin.dashboard'))
    if request.method == 'POST':
        submitted_token = request.form.get('token')
        # Lấy token từ biến môi trường thay vì config file
        correct_token = os.environ.get('ADMIN_SECRET_TOKEN')
        if submitted_token and correct_token and submitted_token == correct_token:
            session['admin_logged_in'] = True
            session.permanent = True
            return redirect(url_for('admin.dashboard'))
        else:
            flash('Admin Secret Token không chính xác!')
    return render_template('admin_login.html')

@admin_endpoint.route('/')
@login_required
def dashboard():
    return render_template('admin_dashboard.html')

@admin_endpoint.route('/logout')
def logout():
    session.clear()
    return redirect(url_for('admin.login'))

# --- API ENDPOINTS CHO ADMIN ---

# API cho Config Editor
@admin_endpoint.route('/api/config', methods=['GET', 'POST'])
@login_required
def config_api():
    if request.method == 'GET':
        try:
            with open('config.json', 'r', encoding='utf-8') as f:
                return jsonify(json.load(f))
        except Exception as e:
            return jsonify(error=f"Lỗi khi đọc file: {str(e)}"), 500
    
    if request.method == 'POST':
        if not request.is_json:
            return jsonify(error="Yêu cầu phải là dạng JSON."), 400
        try:
            with open('config.json', 'w', encoding='utf-8') as f:
                json.dump(request.get_json(), f, indent=2, ensure_ascii=False)
            return jsonify(success=True, message="Cập nhật config.json thành công!")
        except Exception as e:
            return jsonify(error=f"Lỗi khi ghi file: {str(e)}"), 500

# === API MỚI CHO FILE EDITOR ===

@admin_endpoint.route('/api/files', methods=['GET'])
@login_required
def list_files_api():
    """API để liệt kê các file và thư mục."""
    try:
        path = request.args.get('path', '.') # Lấy path từ query param, mặc định là thư mục gốc
        if not is_safe_path(path):
            return jsonify(error="Truy cập bị từ chối."), 403

        abs_path = os.path.join(PROJECT_ROOT, path)
        items = []
        for item in sorted(os.listdir(abs_path)):
            item_path = os.path.join(abs_path, item)
            if os.path.isdir(item_path):
                items.append({'name': item, 'type': 'directory'})
            else:
                items.append({'name': item, 'type': 'file'})
        return jsonify(items)
    except Exception as e:
        return jsonify(error=f"Lỗi khi liệt kê file: {str(e)}"), 500

@admin_endpoint.route('/api/file-content', methods=['GET'])
@login_required
def get_file_content_api():
    """API để đọc nội dung file."""
    filepath = request.args.get('filepath')
    if not filepath:
        return jsonify(error="Thiếu tham số 'filepath'"), 400
    if not is_safe_path(filepath):
        return jsonify(error="Truy cập bị từ chối."), 403
    
    try:
        abs_path = os.path.join(PROJECT_ROOT, filepath)
        with open(abs_path, 'r', encoding='utf-8') as f:
            content = f.read()
        return jsonify(content=content, filepath=filepath)
    except Exception as e:
        return jsonify(error=f"Không thể đọc file: {str(e)}"), 500

@admin_endpoint.route('/api/file-content', methods=['POST'])
@login_required
def update_file_content_api():
    """API để ghi nội dung vào file."""
    data = request.get_json()
    filepath = data.get('filepath')
    content = data.get('content')

    if not filepath or content is None:
        return jsonify(error="Thiếu 'filepath' hoặc 'content'."), 400
    if not is_safe_path(filepath):
        return jsonify(error="Truy cập bị từ chối."), 403

    try:
        abs_path = os.path.join(PROJECT_ROOT, filepath)
        with open(abs_path, 'w', encoding='utf-8') as f:
            f.write(content)
        return jsonify(success=True, message=f"Đã lưu file '{filepath}' thành công!")
    except Exception as e:
        return jsonify(error=f"Không thể ghi file: {str(e)}"), 500

# === API MỚI CHO SYSTEM STATUS ===
@admin_endpoint.route('/api/system-metrics', methods=['GET'])
@login_required
def get_system_metrics_api():
    """API để lấy thông số hệ thống (CPU, RAM, Disk)."""
    try:
        cpu_usage = psutil.cpu_percent(interval=1)
        ram_usage = psutil.virtual_memory().percent
        disk_usage = psutil.disk_usage('/').percent
        return jsonify({
            'cpu': cpu_usage,
            'ram': ram_usage,
            'disk': disk_usage
        })
    except Exception as e:
        return jsonify(error=f"Lỗi khi lấy thông số hệ thống: {str(e)}"), 500
