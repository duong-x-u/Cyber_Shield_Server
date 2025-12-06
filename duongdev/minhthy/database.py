import sqlite3
from datetime import datetime, timezone, timedelta
import json

DB_FILE = "chat_data.db"
GMT7 = timezone(timedelta(hours=7))

def get_db():
    conn = sqlite3.connect(DB_FILE)
    conn.row_factory = sqlite3.Row
    return conn

def get_gmt7_now():
    """Lấy thời gian hiện tại GMT+7 dạng ISO"""
    return datetime.now(GMT7).strftime('%Y-%m-%d %H:%M:%S')

def init_db():
    conn = get_db()
    cursor = conn.cursor()
    
    cursor.execute("PRAGMA foreign_keys = ON")

    # Table conversations
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS conversations (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL DEFAULT 'Cuộc trò chuyện mới',
            ai_name TEXT DEFAULT 'Minh Thy',
            user_name TEXT DEFAULT 'Dương',
            mood INTEGER DEFAULT 70,
            created_at TEXT,
            updated_at TEXT
        )
    ''')
    
    # Add columns if they don't exist
    cursor.execute("PRAGMA table_info(conversations)")
    columns = [col[1] for col in cursor.fetchall()]
    if 'sleep_status' not in columns:
        cursor.execute("ALTER TABLE conversations ADD COLUMN sleep_status TEXT DEFAULT 'thức'")
    if 'busy_status' not in columns:
        cursor.execute("ALTER TABLE conversations ADD COLUMN busy_status TEXT DEFAULT 'rảnh'")
    if 'busy_until' not in columns:
        cursor.execute("ALTER TABLE conversations ADD COLUMN busy_until TEXT DEFAULT NULL")
    if 'user_girlfriend_name' not in columns:
        cursor.execute("ALTER TABLE conversations ADD COLUMN user_girlfriend_name TEXT DEFAULT ''")
    if 'last_busy_reason' not in columns:
        cursor.execute("ALTER TABLE conversations ADD COLUMN last_busy_reason TEXT DEFAULT NULL")
    
    
    # Table messages
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS messages (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            conversation_id INTEGER NOT NULL,
            role TEXT NOT NULL,
            sender_name TEXT NOT NULL,
            content TEXT NOT NULL,
            image TEXT DEFAULT NULL,
            reply_to_id INTEGER DEFAULT NULL,
            reactions TEXT DEFAULT '[]',
            is_seen INTEGER DEFAULT 0,
            timestamp TEXT,
            FOREIGN KEY (conversation_id) REFERENCES conversations(id) ON DELETE CASCADE,
            FOREIGN KEY (reply_to_id) REFERENCES messages(id) ON DELETE SET NULL
        )
    ''')
    
    # Add image column if not exists (migration)
    cursor.execute("PRAGMA table_info(messages)")
    msg_columns = [col[1] for col in cursor.fetchall()]
    if 'image' not in msg_columns:
        cursor.execute("ALTER TABLE messages ADD COLUMN image TEXT DEFAULT NULL")
    if 'is_retracted' not in msg_columns:
        cursor.execute("ALTER TABLE messages ADD COLUMN is_retracted INTEGER DEFAULT 0")
    if 'is_edited' not in msg_columns:
        cursor.execute("ALTER TABLE messages ADD COLUMN is_edited INTEGER DEFAULT 0")

    # Table settings
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS settings (
            key TEXT PRIMARY KEY,
            value TEXT NOT NULL
        )
    ''')

    # Table daily_summaries
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS daily_summaries (
            date TEXT PRIMARY KEY,
            summary TEXT NOT NULL,
            created_at TEXT
        )
    ''')
    
    # Default settings
    cursor.execute("INSERT OR IGNORE INTO settings (key, value) VALUES ('current_conversation_id', '1')")
    
    # Create default conversation if none exists
    cursor.execute('SELECT COUNT(*) as count FROM conversations')
    if cursor.fetchone()['count'] == 0:
        now = get_gmt7_now()
        cursor.execute("INSERT INTO conversations (name, created_at, updated_at) VALUES (?, ?, ?)", ('Minh Thy 🌸', now, now))

    conn.commit()
    conn.close()

# ========== CONVERSATIONS ========== 
def create_conversation(name="Cuộc trò chuyện mới"):
    conn = get_db()
    cursor = conn.cursor()
    now = get_gmt7_now()
    cursor.execute("INSERT INTO conversations (name, created_at, updated_at) VALUES (?, ?, ?)", (name, now, now))
    conn.commit()
    conv_id = cursor.lastrowid
    conn.close()
    return conv_id

def get_all_conversations():
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute('''
        SELECT c.*, 
               (SELECT content FROM messages WHERE conversation_id = c.id ORDER BY timestamp DESC LIMIT 1) as last_message,
               (SELECT timestamp FROM messages WHERE conversation_id = c.id ORDER BY timestamp DESC LIMIT 1) as last_message_time,
               (SELECT role FROM messages WHERE conversation_id = c.id ORDER BY timestamp DESC LIMIT 1) as last_sender_role,
               (SELECT COUNT(*) FROM messages WHERE conversation_id = c.id AND is_seen = 0 AND role = 'assistant') as unread_count
        FROM conversations c 
        ORDER BY c.updated_at DESC
    ''')
    convs = [dict(row) for row in cursor.fetchall()]
    conn.close()
    return convs

def get_conversation(conv_id):
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute('SELECT * FROM conversations WHERE id = ?', (conv_id,))
    row = cursor.fetchone()
    conn.close()
    return dict(row) if row else None

def update_conversation(conv_id, **kwargs):
    conn = get_db()
    cursor = conn.cursor()
    
    allowed_fields = ['name', 'ai_name', 'user_name', 'mood', 'sleep_status', 'busy_status', 'busy_until', 'user_girlfriend_name', 'last_busy_reason']
    updates = {k: v for k, v in kwargs.items() if k in allowed_fields}
    
    if updates:
        set_clause = ", ".join([f"{key} = ?" for key in updates.keys()])
        values = list(updates.values())
        values.extend([get_gmt7_now(), conv_id])
        cursor.execute(f'UPDATE conversations SET {set_clause}, updated_at = ? WHERE id = ?', values)
        conn.commit()
    conn.close()

def delete_conversation(conv_id):
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute('DELETE FROM conversations WHERE id = ?', (conv_id,))
    conn.commit()
    conn.close()

# ========== MESSAGES ========== 
def save_message(conversation_id, role, sender_name, content, reply_to_id=None, image=None):
    conn = get_db()
    cursor = conn.cursor()
    now = get_gmt7_now()
    cursor.execute('UPDATE conversations SET updated_at = ? WHERE id = ?', (now, conversation_id))
    cursor.execute(
        'INSERT INTO messages (conversation_id, role, sender_name, content, reply_to_id, timestamp, image) VALUES (?, ?, ?, ?, ?, ?, ?)',
        (conversation_id, role, sender_name, content, reply_to_id, now, image)
    )
    conn.commit()
    msg_id = cursor.lastrowid
    conn.close()
    return msg_id

def get_messages(conversation_id, limit=None, start_date=None, end_date=None):
    conn = get_db()
    cursor = conn.cursor()
    
    base_query = '''
        SELECT m.*, r.content as reply_content, r.sender_name as reply_sender
        FROM messages m
        LEFT JOIN messages r ON m.reply_to_id = r.id
        WHERE m.conversation_id = ?
    '''
    params = [conversation_id]
    
    if start_date:
        base_query += ' AND m.timestamp >= ?'
        params.append(start_date)
    if end_date:
        base_query += ' AND m.timestamp <= ?'
        params.append(end_date)
        
    if limit:
        # This logic is a bit tricky with date filters. A simpler approach is taken for now.
        # A more robust solution might use window functions if complexity increases.
        sub_query = base_query + " ORDER BY m.timestamp DESC LIMIT ?"
        params.append(limit)
        query = f"SELECT * FROM ({sub_query}) sub ORDER BY sub.timestamp ASC"

    else:
        query = base_query + " ORDER BY m.timestamp ASC"

    cursor.execute(query, tuple(params))
    messages = [dict(row) for row in cursor.fetchall()]
    conn.close()
    return messages


def get_message(msg_id):
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute('SELECT * FROM messages WHERE id = ?', (msg_id,))
    row = cursor.fetchone()
    conn.close()
    return dict(row) if row else None

def update_message_reactions(msg_id, reactions):
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute('UPDATE messages SET reactions = ? WHERE id = ?', (json.dumps(reactions), msg_id))
    conn.commit()
    conn.close()

def retract_message(msg_id):
    conn = get_db()
    cursor = conn.cursor()
    now = get_gmt7_now()
    # Update the conversation's updated_at to bring it to the top
    cursor.execute('''
        UPDATE conversations SET updated_at = ? 
        WHERE id = (SELECT conversation_id FROM messages WHERE id = ?)
    ''', (now, msg_id))
    # Retract the message
    cursor.execute(
        "UPDATE messages SET is_retracted = 1, content = '[Tin nhắn đã được thu hồi]' WHERE id = ?",
        (msg_id,)
    )
    conn.commit()
    conn.close()

def edit_message(msg_id, new_content):
    conn = get_db()
    cursor = conn.cursor()
    now = get_gmt7_now()
    # Update the conversation's updated_at to bring it to the top
    cursor.execute('''
        UPDATE conversations SET updated_at = ? 
        WHERE id = (SELECT conversation_id FROM messages WHERE id = ?)
    ''', (now, msg_id))
    # Update the message content and mark as edited
    cursor.execute(
        "UPDATE messages SET content = ?, is_edited = 1 WHERE id = ?",
        (new_content, msg_id)
    )
    conn.commit()
    conn.close()

def mark_messages_seen(conversation_id, role='assistant'):
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute('UPDATE messages SET is_seen = 1 WHERE conversation_id = ? AND role = ?', (conversation_id, role))
    conn.commit()
    conn.close()

def search_messages(conversation_id, query, start_date=None, end_date=None):
    conn = get_db()
    cursor = conn.cursor()
    
    params = [conversation_id, f'%{query}%']
    sql = "SELECT * FROM messages WHERE conversation_id = ? AND content LIKE ?"
    
    if start_date:
        sql += " AND timestamp >= ?"
        params.append(start_date)
    
    if end_date:
        sql += " AND timestamp <= ?"
        params.append(end_date)
        
    sql += " ORDER BY timestamp DESC LIMIT 50"
    
    cursor.execute(sql, tuple(params))
    messages = [dict(row) for row in cursor.fetchall()]
    conn.close()
    return messages

def get_message_count(conversation_id=None):
    conn = get_db()
    cursor = conn.cursor()
    if conversation_id:
        cursor.execute('SELECT COUNT(*) as count FROM messages WHERE conversation_id = ?', (conversation_id,))
    else:
        cursor.execute('SELECT COUNT(*) as count FROM messages')
    count = cursor.fetchone()['count']
    conn.close()
    return count

# ========== SETTINGS ========== 
def get_setting(key):
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute('SELECT value FROM settings WHERE key = ?', (key,))
    row = cursor.fetchone()
    conn.close()
    return row['value'] if row else None

def update_setting(key, value):
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute('INSERT OR REPLACE INTO settings (key, value) VALUES (?, ?)', (key, value))
    conn.commit()
    conn.close()

def get_all_settings():
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute('SELECT * FROM settings')
    settings = {row['key']: row['value'] for row in cursor.fetchall()}
    conn.close()
    return settings

# ========== DAILY SUMMARIES (MEMORY) ==========
def save_daily_summary(date, summary):
    conn = get_db()
    cursor = conn.cursor()
    now = get_gmt7_now()
    cursor.execute('INSERT OR REPLACE INTO daily_summaries (date, summary, created_at) VALUES (?, ?, ?)', (date, summary, now))
    conn.commit()
    conn.close()

def get_summary_for_date(date):
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute('SELECT summary FROM daily_summaries WHERE date = ?', (date,))
    row = cursor.fetchone()
    conn.close()
    return row['summary'] if row else None


# ========== EXPORT ========== 
def export_conversation(conversation_id, format='txt'):
    conv = get_conversation(conversation_id)
    messages = get_messages(conversation_id)
    if not conv: return None
    
    if format == 'txt':
        lines = [f"=== {conv['name']} ===\n", f"AI: {conv['ai_name']} | User: {conv['user_name']}\n", "="*40 + "\n\n"]
        for msg in messages:
            lines.append(f"[{msg['timestamp'] or ''}] {msg['sender_name']}:\n{msg['content']}\n\n")
        return ''.join(lines)
    
    if format == 'json':
        return json.dumps({'conversation': conv, 'messages': messages}, ensure_ascii=False, indent=2)
    
    return None

def get_latest_global_message_time():
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute('SELECT MAX(timestamp) as last_time FROM messages')
    row = cursor.fetchone()
    conn.close()
    return row['last_time'] if row and row['last_time'] else None

# Initialize
init_db()
