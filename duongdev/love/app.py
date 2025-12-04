#MÁY CHỦ CON CỦA /LOVE

import os
from flask import Flask, render_template, request, redirect, url_for, jsonify, flash
from flask_sqlalchemy import SQLAlchemy
from flask_socketio import SocketIO, emit
from datetime import datetime, timedelta
from werkzeug.utils import secure_filename

# Set the base directory for the app
basedir = os.path.abspath(os.path.dirname(__file__))

app = Flask(__name__)
app.config['SECRET_KEY'] = 'your-secret-key-here'
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///database.db'
app.config['UPLOAD_FOLDER'] = os.path.join(basedir, 'static', 'uploads')
app.config['MAX_CONTENT_LENGTH'] = 16 * 1024 * 1024  # 16MB max

socketio = SocketIO(app, cors_allowed_origins="*")

db = SQLAlchemy(app)

# Ngày bắt đầu yêu
START_DATE = datetime(2025, 11, 28, 15, 51, 0)

# Models
class DiaryEntry(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    title = db.Column(db.String(200), nullable=False)
    content = db.Column(db.Text, nullable=False)
    mood = db.Column(db.String(50))  # happy, love, sad, excited...
    date = db.Column(db.DateTime, default=datetime.now)
    created_at = db.Column(db.DateTime, default=datetime.now)

class Photo(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    filename = db.Column(db.String(300), nullable=False)
    caption = db.Column(db.String(500))
    date_taken = db.Column(db.DateTime)
    created_at = db.Column(db.DateTime, default=datetime.now)

class Milestone(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    title = db.Column(db.String(200), nullable=False)
    description = db.Column(db.Text)
    date = db.Column(db.DateTime, nullable=False)
    icon = db.Column(db.String(50), default='heart')
    is_recurring = db.Column(db.Boolean, default=False)  # Lặp lại hàng năm
    created_at = db.Column(db.DateTime, default=datetime.now)

class Memory(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    title = db.Column(db.String(200), nullable=False)
    description = db.Column(db.Text)
    date = db.Column(db.DateTime)
    photo_id = db.Column(db.Integer, db.ForeignKey('photo.id'))
    created_at = db.Column(db.DateTime, default=datetime.now)

# Helper functions
def get_love_duration():
    now = datetime.now()
    delta = now - START_DATE
    
    total_seconds = int(delta.total_seconds())
    days = delta.days
    years = days // 365
    months = (days % 365) // 30
    remaining_days = (days % 365) % 30
    hours = (total_seconds % 86400) // 3600
    minutes = (total_seconds % 3600) // 60
    seconds = total_seconds % 60
    
    return {
        'total_days': days,
        'years': years,
        'months': months,
        'days': remaining_days,
        'hours': hours,
        'minutes': minutes,
        'seconds': seconds,
        'total_seconds': total_seconds
    }

def get_upcoming_milestones():
    now = datetime.now()
    upcoming = []
    
    # Kỷ niệm tháng tiếp theo
    months_together = (now.year - START_DATE.year) * 12 + (now.month - START_DATE.month)
    next_month_anniversary = START_DATE.replace(
        year=START_DATE.year + (START_DATE.month + months_together) // 12,
        month=(START_DATE.month + months_together) % 12 + 1
    )
    if next_month_anniversary <= now:
        next_month_anniversary = START_DATE.replace(
            year=START_DATE.year + (START_DATE.month + months_together + 1) // 12,
            month=(START_DATE.month + months_together + 1 - 1) % 12 + 1
        )
    
    upcoming.append({
        'title': f'Kỷ niệm {months_together + 1} tháng',
        'date': next_month_anniversary,
        'days_left': (next_month_anniversary - now).days
    })
    
    # Custom milestones
    milestones = Milestone.query.filter(Milestone.date >= now).order_by(Milestone.date).limit(5).all()
    for m in milestones:
        upcoming.append({
            'title': m.title,
            'date': m.date,
            'days_left': (m.date - now).days,
            'icon': m.icon
        })
    
    return sorted(upcoming, key=lambda x: x['date'])[:5]

# Routes
@app.route('/')
def index():
    duration = get_love_duration()
    upcoming = get_upcoming_milestones()
    recent_photos = Photo.query.order_by(Photo.created_at.desc()).limit(6).all()
    recent_diary = DiaryEntry.query.order_by(DiaryEntry.date.desc()).limit(3).all()
    
    return render_template('index.html', 
                         duration=duration,
                         upcoming=upcoming,
                         recent_photos=recent_photos,
                         recent_diary=recent_diary,
                         start_date=START_DATE)

@app.route('/api/duration')
def api_duration():
    return jsonify(get_love_duration())

# Diary routes
@app.route('/diary')
def diary():
    entries = DiaryEntry.query.order_by(DiaryEntry.date.desc()).all()
    return render_template('diary.html', entries=entries)

@app.route('/diary/add', methods=['POST'])
def add_diary():
    title = request.form.get('title')
    content = request.form.get('content')
    mood = request.form.get('mood', 'love')
    date_str = request.form.get('date')
    
    if date_str:
        date = datetime.strptime(date_str, '%Y-%m-%d')
    else:
        date = datetime.now()
    
    entry = DiaryEntry(title=title, content=content, mood=mood, date=date)
    db.session.add(entry)
    db.session.commit()
    
    return redirect(url_for('diary'))

@app.route('/diary/delete/<int:id>')
def delete_diary(id):
    entry = DiaryEntry.query.get_or_404(id)
    db.session.delete(entry)
    db.session.commit()
    return redirect(url_for('diary'))

# Gallery routes
@app.route('/gallery')
def gallery():
    photos = Photo.query.order_by(Photo.created_at.desc()).all()
    return render_template('gallery.html', photos=photos)

@app.route('/gallery/upload', methods=['POST'])
def upload_photo():
    if 'photo' not in request.files:
        return redirect(url_for('gallery'))
    
    file = request.files['photo']
    if file.filename == '':
        return redirect(url_for('gallery'))
    
    if file:
        filename = secure_filename(f"{datetime.now().strftime('%Y%m%d%H%M%S')}_{file.filename}")
        filepath = os.path.join(app.config['UPLOAD_FOLDER'], filename)
        file.save(filepath)
        
        caption = request.form.get('caption', '')
        date_str = request.form.get('date_taken')
        date_taken = datetime.strptime(date_str, '%Y-%m-%d') if date_str else datetime.now()
        
        photo = Photo(filename=filename, caption=caption, date_taken=date_taken)
        db.session.add(photo)
        db.session.commit()
    
    return redirect(url_for('gallery'))

@app.route('/gallery/delete/<int:id>')
def delete_photo(id):
    photo = Photo.query.get_or_404(id)
    
    # Xóa file vật lý (nếu tồn tại)
    try:
        filepath = os.path.join(app.config['UPLOAD_FOLDER'], photo.filename)
        if os.path.exists(filepath):
            os.remove(filepath)
            flash(f'Đã xóa file vật lý "{photo.filename}".', 'success')
        else:
            flash(f'File vật lý "{photo.filename}" không tồn tại trên server.', 'warning')
    except OSError as e:
        flash(f'Lỗi khi xóa file vật lý "{photo.filename}": {e}.', 'error')

    # Luôn xóa bản ghi trong database
    db.session.delete(photo)
    db.session.commit()
    flash('Đã xóa bản ghi ảnh khỏi database.', 'success')
    
    return redirect(url_for('gallery'))

# Milestones routes
@app.route('/milestones')
def milestones():
    all_milestones = Milestone.query.order_by(Milestone.date).all()
    upcoming = get_upcoming_milestones()
    return render_template('milestones.html', milestones=all_milestones, upcoming=upcoming)

@app.route('/milestones/add', methods=['POST'])
def add_milestone():
    title = request.form.get('title')
    description = request.form.get('description', '')
    date_str = request.form.get('date')
    icon = request.form.get('icon', 'heart')
    is_recurring = request.form.get('is_recurring') == 'on'
    
    date = datetime.strptime(date_str, '%Y-%m-%d')
    
    milestone = Milestone(
        title=title,
        description=description,
        date=date,
        icon=icon,
        is_recurring=is_recurring
    )
    db.session.add(milestone)
    db.session.commit()
    
    return redirect(url_for('milestones'))

@app.route('/milestones/delete/<int:id>')
def delete_milestone(id):
    milestone = Milestone.query.get_or_404(id)
    db.session.delete(milestone)
    db.session.commit()
    return redirect(url_for('milestones'))

# Thêm route edit diary
@app.route('/diary/edit/<int:id>', methods=['GET', 'POST'])
def edit_diary(id):
    entry = DiaryEntry.query.get_or_404(id)
    
    if request.method == 'POST':
        entry.title = request.form.get('title')
        entry.content = request.form.get('content')
        entry.mood = request.form.get('mood', 'love')
        date_str = request.form.get('date')
        
        if date_str:
            entry.date = datetime.strptime(date_str, '%Y-%m-%d')
        
        db.session.commit()
        return redirect(url_for('diary'))
    
    return render_template('edit_diary.html', entry=entry)

# Khởi tạo database và tạo folder uploads khi ứng dụng được tạo (luôn chạy)
with app.app_context():
    db.create_all()
    # Tạo folder uploads nếu chưa có
    os.makedirs(app.config['UPLOAD_FOLDER'], exist_ok=True)

if __name__ == '__main__':
    socketio.run(app, debug=True, port=6000, allow_unsafe_werkzeug=True)