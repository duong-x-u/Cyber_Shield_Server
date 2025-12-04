from flask import Flask, jsonify, request, render_template, send_from_directory
from flask_cors import CORS
from flask_socketio import SocketIO, emit
import json
import os
from datetime import datetime
from werkzeug.utils import secure_filename
import uuid

app = Flask(__name__)
CORS(app)
app.config['UPLOAD_FOLDER'] = 'uploads'
app.config['MAX_CONTENT_LENGTH'] = 25 * 1024 * 1024  # 25 MB max size
socketio = SocketIO(app, cors_allowed_origins="*") # Allow all origins for development


MESSAGES_FILE = 'messages.txt'

def load_messages():
    """Đọc tin nhắn từ file"""
    if not os.path.exists(MESSAGES_FILE):
        return []
    
    try:
        with open(MESSAGES_FILE, 'r', encoding='utf-8') as f:
            lines = f.readlines()
            messages = []
            for line in lines:
                if line.strip():
                    try:
                        msg = json.loads(line.strip())
                        messages.append(msg)
                    except json.JSONDecodeError:
                        continue
            return messages
    except Exception as e:
        print(f"Lỗi khi đọc file: {e}")
        return []

def save_message(message):
    """Lưu tin nhắn vào file"""
    try:
        with open(MESSAGES_FILE, 'a', encoding='utf-8') as f:
            f.write(json.dumps(message, ensure_ascii=False) + '\n')
        return True
    except Exception as e:
        print(f"Lỗi khi lưu tin nhắn: {e}")
        return False

@app.route('/api/messages', methods=['GET'])
def get_messages():
    """Lấy tất cả tin nhắn"""
    messages = load_messages()
    return jsonify({'messages': messages})

@app.route('/')
def index():
    """Phục vụ trang HTML chính từ template"""
    return render_template('index.html')

@socketio.on('connect')
def handle_connect():
    print('Client connected:', request.sid)

@socketio.on('disconnect')
def handle_disconnect():
    print('Client disconnected:', request.sid)

@socketio.on('send_message')

def handle_send_message(data):

    """Xử lý tin nhắn mới từ client qua SocketIO"""

    if not data or not data.get('content'):

        return



    message = {

        'id': str(uuid.uuid4()),

        'sessionId': data.get('sessionId'),

        'username': data.get('username', 'Anonymous'),

        'content': data.get('content'),

        'timestamp': datetime.now().isoformat()

    }

    

    if save_message(message):

        emit('new_message', message, broadcast=True)



@socketio.on('revoke_message')

def handle_revoke_message(data):

    """Xử lý yêu cầu thu hồi tin nhắn"""

    message_id = data.get('id')

    session_id = data.get('sessionId')



    if not message_id or not session_id:

        return



    messages = load_messages()

    message_found = False

    

    for msg in messages:

        if msg.get('id') == message_id:

            if msg.get('sessionId') == session_id:

                msg['content'] = 'Tin nhắn đã được thu hồi'

                msg['revoked'] = True

                msg.pop('fileUrl', None)

                msg.pop('filename', None)

                message_found = True

                break

            else:

                return

    

    if message_found:

        try:

            with open(MESSAGES_FILE, 'w', encoding='utf-8') as f:

                for msg in messages:

                    f.write(json.dumps(msg, ensure_ascii=False) + '\n')

            emit('message_revoked', {'id': message_id}, broadcast=True)

        except Exception as e:

            print(f"Lỗi khi ghi lại file sau khi thu hồi: {e}")



@app.route('/upload', methods=['POST'])

def upload_file():

    if 'file' not in request.files:

        return jsonify({'error': 'No file part'}), 400

    file = request.files['file']

    if file.filename == '':

        return jsonify({'error': 'No selected file'}), 400

    if file:

        filename = secure_filename(file.filename)

        unique_filename = datetime.now().strftime("%Y%m%d%H%M%S") + "_" + filename

        file.save(os.path.join(app.config['UPLOAD_FOLDER'], unique_filename))

        

        message = {

            'id': str(uuid.uuid4()),

            'sessionId': request.form.get('sessionId'),

            'username': request.form.get('username', 'Anonymous'),

            'content': f'Đã gửi một file: {filename}',

            'fileUrl': f'/uploads/{unique_filename}',

            'filename': filename,

            'timestamp': datetime.now().isoformat()

        }

        if save_message(message):

            socketio.emit('new_message', message, broadcast=True)

        return jsonify({'success': True}), 200

    return jsonify({'error': 'File không hợp lệ'}), 400



@app.route('/uploads/<filename>')

def uploaded_file(filename):

    return send_from_directory(app.config['UPLOAD_FOLDER'], filename)



if __name__ == '__main__':

    socketio.run(app, debug=True, host='0.0.0.0', port=5000)