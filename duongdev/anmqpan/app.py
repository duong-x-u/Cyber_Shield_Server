from flask import Flask, jsonify, request, render_template, send_from_directory
from flask_cors import CORS
from flask_socketio import SocketIO, emit
from datetime import datetime

app = Flask(__name__)
CORS(app)

socketio = SocketIO(app, cors_allowed_origins="*")

@app.route('/')
def index():
    """Phục vụ trang HTML chính từ template"""
    return render_template('index.html')

@app.route('/duongdev/anmqpan/music/<path:filename>')
def serve_music(filename):
    """Phục vụ các file nhạc"""
    return send_from_directory('music', filename)



if __name__ == '__main__':
    socketio.run(app, debug=True, host='0.0.0.0', port=8386)