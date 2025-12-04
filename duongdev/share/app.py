# duongdev/share/app.py
import os
from flask import (
    Flask, render_template, request, redirect, url_for, send_from_directory, flash
)
from flask_sqlalchemy import SQLAlchemy
from datetime import datetime
from werkzeug.utils import secure_filename
from flask_socketio import SocketIO, emit # Import SocketIO and emit

# --- App Initialization ---
app = Flask(__name__)

# --- Configuration ---
basedir = os.path.abspath(os.path.dirname(__file__))
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///' + os.path.join(basedir, 'file_blog.db')
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
app.config['UPLOAD_FOLDER'] = os.path.join(basedir, 'uploads/')
app.config['SECRET_KEY'] = 'a-random-secret-key-for-the-share-app' 
app.config['MAX_CONTENT_LENGTH'] = 100 * 1024 * 1024  # 100MB

# --- SocketIO Initialization ---
socketio = SocketIO(app, cors_allowed_origins="*", path='/duongdev/share/socket.io')

# --- Database Setup ---
db = SQLAlchemy(app)

# --- Database Model ---
class FilePost(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    title = db.Column(db.String(150), nullable=False)
    description = db.Column(db.Text, nullable=True)
    filename = db.Column(db.String(255), nullable=False, unique=True)
    file_size = db.Column(db.Integer, nullable=False) # in bytes
    upload_date = db.Column(db.DateTime, nullable=False, default=datetime.utcnow)

    def __repr__(self):
        return f'<FilePost {self.title}>'

    def formatted_size(self):
        if self.file_size is None:
            return "0 B"
        size_bytes = self.file_size
        if size_bytes < 1024:
            return f"{size_bytes} B"
        elif size_bytes < 1024**2:
            return f"{size_bytes/1024:.2f} KB"
        elif size_bytes < 1024**3:
            return f"{size_bytes/1024**2:.2f} MB"
        else:
            return f"{size_bytes/1024**3:.2f} GB"

@app.context_processor
def inject_now():
    return {'now': datetime.utcnow()}
    
# --- Routes ---

@app.route('/')
def index():
    posts = FilePost.query.order_by(FilePost.upload_date.desc()).all()
    return render_template('index.html', posts=posts)

@app.route('/upload', methods=['POST'])
def upload():
    if 'file' not in request.files:
        flash('No file part')
        return redirect(url_for('index'))
    
    file = request.files['file']
    if file.filename == '':
        flash('No selected file')
        return redirect(url_for('index'))

    if file:
        original_filename = secure_filename(file.filename)
        # Create a unique filename to prevent overwrites
        timestamp = datetime.utcnow().strftime('%Y%m%d%H%M%S')
        unique_filename = f"{timestamp}_{original_filename}"
        
        filepath = os.path.join(app.config['UPLOAD_FOLDER'], unique_filename)
        file.seek(0, os.SEEK_END)
        file_size = file.tell()
        file.seek(0) # Reset pointer
        file.save(filepath)

        new_post = FilePost(
            title=request.form.get('title', 'Untitled'),
            description=request.form.get('description', ''),
            filename=unique_filename,
            file_size=file_size
        )
        db.session.add(new_post)
        db.session.commit()
        
        # Emit SocketIO event for new file upload
        socketio.emit('file_uploaded', {
            'id': new_post.id,
            'title': new_post.title,
            'description': new_post.description, # Include description
            'filename': new_post.filename,
            'size': new_post.formatted_size(),
            'date': new_post.upload_date.strftime('%Y-%m-%d %H:%M')
        })
        
    return redirect(url_for('index'))

@app.route('/download/<filename>')
def download(filename):
    return send_from_directory(app.config['UPLOAD_FOLDER'], filename, as_attachment=True)

@app.route('/edit/<int:post_id>', methods=['GET', 'POST'])
def edit_post(post_id):
    post = FilePost.query.get_or_404(post_id)
    if request.method == 'POST':
        post.title = request.form['title']
        post.description = request.form['description']
        db.session.commit()
        
        # Emit SocketIO event for file edited
        socketio.emit('file_edited', {
            'id': post.id,
            'title': post.title,
            'description': post.description,
            'date': post.upload_date.strftime('%Y-%m-%d %H:%M')
        })

        return redirect(url_for('index'))
    return render_template('edit_post.html', post=post)

@app.route('/delete/<int:post_id>', methods=['POST'])
def delete_post(post_id):
    post = FilePost.query.get_or_404(post_id)
    
    # Delete the physical file
    try:
        filepath = os.path.join(app.config['UPLOAD_FOLDER'], post.filename)
        if os.path.exists(filepath):
            os.remove(filepath)
    except OSError as e:
        flash(f"Error deleting file: {e}")

    db.session.delete(post)
    db.session.commit()
    
    # Emit SocketIO event for file deleted
    socketio.emit('file_deleted', {'id': post_id})
    
    return redirect(url_for('index'))

# --- Main Execution ---
# This runs when the app is initialized, ensuring tables exist.
with app.app_context():
    db.create_all()
    # Ensure the upload folder exists
    os.makedirs(app.config['UPLOAD_FOLDER'], exist_ok=True)

if __name__ == '__main__':
    # This allows running the app standalone for testing
    socketio.run(app, debug=True, port=5001)
