import sys
import os

# Thêm parent directory vào path nếu cần
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from flask import Flask, render_template, request, jsonify, Response
from flask_socketio import SocketIO, emit, join_room, leave_room
from bytez import Bytez
from datetime import datetime, timezone, timedelta
from datetime import time as dt_time
import time as pytime
import json
import re
import threading
import random
from .database import (
    create_conversation, get_all_conversations, get_conversation,
    update_conversation, delete_conversation, save_message, get_messages,
    get_message, update_message_reactions, mark_messages_seen,
    search_messages, get_message_count, get_setting, update_setting,
    get_all_settings, export_conversation, get_latest_global_message_time
)

app = Flask(__name__)
app.config['SECRET_KEY'] = 'minh-thy-secret-2025'

socketio = SocketIO(
    app,
    cors_allowed_origins="*",
    ping_timeout=60,
    ping_interval=25,
    logger=False,
    engineio_logger=False
)

# Lock to ensure background tasks are started only once
_tasks_started_lock = threading.Lock()
_tasks_started = False
# ========== BYTEZ SETUP ==========
BYTEZ_API_KEY = "YOUR_API_KEY"  # Thay API key của bạn
sdk = Bytez("4bf720ec73b4b1af0fb1783e9667fe07")
model = sdk.model("google/gemini-2.5-flash")

GMT7 = timezone(timedelta(hours=7))

# Constants for schedule (can be moved to a config later)
SCHOOL_START_HOUR = 7
SCHOOL_END_HOUR = 11
SCHOOL_END_MINUTE = 30 # For 11:30

def time_since_last_message(last_message_time_str):
    if last_message_time_str:
        try:
            last_message_dt = datetime.strptime(last_message_time_str, '%Y-%m-%d %H:%M:%S').replace(tzinfo=GMT7)
            time_diff_minutes = (datetime.now(GMT7) - last_message_dt).total_seconds() / 60
            return int(time_diff_minutes)
        except ValueError:
            pass
    return 0

def life_and_school_scheduler():
    while True:
        current_dt = datetime.now(GMT7)
        current_hour = current_dt.hour
        current_minute = current_dt.minute
        weekday = current_dt.weekday() # Monday is 0, Sunday is 6
        now_time = current_dt.time()

        conversations = get_all_conversations()
        for conv in conversations:
            conv_id = conv['id']
            current_busy_status = conv.get('busy_status', 'rảnh')
            current_busy_until = conv.get('busy_until')

            new_busy_status = 'rảnh'
            new_busy_until = None

            # --- Check if a custom random event has expired ---
            is_fixed_schedule_status = current_busy_status in ['rảnh', 'Học chính khóa', 'Ngủ trưa', 'Đang ngủ']
            if not is_fixed_schedule_status and current_busy_until:
                try:
                    busy_until_dt = datetime.strptime(current_busy_until, '%Y-%m-%d %H:%M:%S').replace(tzinfo=GMT7)
                    if current_dt > busy_until_dt:
                        # Custom event expired, go back to being rảnh
                        new_busy_status = 'rảnh'
                        new_busy_until = None
                    else:
                        # Custom event is still active, keep it and skip regular scheduling
                        new_busy_status = current_busy_status
                        new_busy_until = current_busy_until
                except (ValueError, TypeError):
                    # If parsing fails, reset to rảnh
                    new_busy_status = 'rảnh'
                    new_busy_until = None


            # --- 1. School (Học chính khóa) Mon-Sat 7:00-11:30 (Overrides random events) ---
            if weekday <= 5 and dt_time(SCHOOL_START_HOUR, 0) <= now_time <= dt_time(SCHOOL_END_HOUR, SCHOOL_END_MINUTE):
                new_busy_status = 'Học chính khóa'
                new_busy_until = current_dt.replace(hour=SCHOOL_END_HOUR, minute=SCHOOL_END_MINUTE, second=0, microsecond=0).strftime('%Y-%m-%d %H:%M:%S')

            # --- 2. Nap Time (Ngủ trưa) Mon-Sun 13:15 - 15:00 (Overrides random events) ---
            elif dt_time(13, 15) <= now_time <= dt_time(15, 0):
                new_busy_status = 'Ngủ trưa'
                new_busy_until = current_dt.replace(hour=15, minute=0, second=0, microsecond=0).strftime('%Y-%m-%d %H:%M:%S')

            # Update if status changed
            if new_busy_status != current_busy_status:
                update_conversation(conv_id, busy_status=new_busy_status, busy_until=new_busy_until)
                socketio.emit('conversations_updated', {'conversations': get_all_conversations()})


            # --- SLEEP LOGIC ---
            current_sleep_status = conv.get('sleep_status', 'thức')
            last_sender_role = conv.get('last_sender_role')

            # 1. Ask to sleep (22:20 - 23:59)
            if (current_hour == 22 and current_minute >= 20) or (current_hour == 23):
                if current_sleep_status == 'thức' and last_sender_role == 'user':
                    try:
                        ai_action = get_proactive_sleep_message(conv_id)
                        raw_content = ai_action.get('content', '')
                        contents_to_send = []
                        if isinstance(raw_content, str) and raw_content.strip():
                            contents_to_send.append(raw_content.strip())
                        elif isinstance(raw_content, list):
                            contents_to_send.extend(item for item in raw_content if isinstance(item, str) and item.strip())

                        if contents_to_send:
                            for content in contents_to_send:
                                ai_msg_id = save_message(conv_id, 'assistant', conv['ai_name'], content)
                                socketio.emit('new_message', {
                                    'id': ai_msg_id, 'role': 'assistant', 'sender_name': conv['ai_name'],
                                    'content': content, 'timestamp': datetime.now(GMT7).strftime('%H:%M'), 'is_seen': 0
                                }, room=str(conv_id))
                                socketio.sleep(0.1)
                            update_conversation(conv_id, sleep_status='đã hỏi')
                            socketio.emit('conversations_updated', {'conversations': get_all_conversations()})
                    except Exception as e:
                        print(f"❌ Error sending proactive sleep message for conv {conv_id}: {e}")

            # 2. Force sleep (00:30 - 05:00)
            if (current_hour == 0 and current_minute >= 30) or (current_hour > 0 and current_hour < 5):
                if current_sleep_status != 'ngủ say':
                    update_conversation(conv_id, sleep_status='ngủ say', busy_status='Đang ngủ')
                    socketio.emit('conversations_updated', {'conversations': get_all_conversations()})

            # 3. Wake up
            if current_sleep_status == 'ngủ say':
                is_weekday = 0 <= weekday <= 5
                is_sunday = weekday == 6
                weekday_wakeup = is_weekday and (current_hour >= 5 and current_hour < SCHOOL_START_HOUR)
                sunday_wakeup = is_sunday and (current_hour > 9 or (current_hour == 9 and current_minute >= 30))
                if weekday_wakeup or sunday_wakeup:
                    update_conversation(conv_id, sleep_status='thức', busy_status='rảnh')
                    socketio.emit('conversations_updated', {'conversations': get_all_conversations()})

        socketio.sleep(60)

def presence_updater_scheduler():
    while True:
        socketio.sleep(60)
        # Lấy thời gian tin nhắn mới nhất từ toàn bộ hệ thống
        last_message_time_str = get_latest_global_message_time()
        
        minutes_ago = time_since_last_message(last_message_time_str)
        global_status = 'offline' if minutes_ago >= 4 else 'online'

        socketio.emit('ai_presence_updated', {
            'status': global_status,
            'minutes_ago': minutes_ago
        })
        
        # Logic cập nhật mood vẫn dựa trên conversations[0] (cuộc trò chuyện gần nhất), điều này hợp lý
        conversations = get_all_conversations() # Cần lấy lại danh sách conversations nếu muốn dùng conversations[0] cho mood
        if conversations and random.random() < 0.02:
            conv = conversations[0]
            conv_id = conv['id']
            current_mood = int(conv.get('mood', 70))
            mood_change_amount = random.randint(-5, 5)
            new_mood = max(0, min(100, current_mood + mood_change_amount))
            if new_mood != current_mood:
                update_conversation(conv_id, mood=new_mood)
                socketio.emit('mood_updated', {'conv_id': conv_id, 'new_mood': new_mood})

def proactive_message_scheduler():
    while True:
        socketio.sleep(30 * 60)
        current_hour = datetime.now(GMT7).hour
        if 0 <= current_hour < 7:
            continue

        conversations = get_all_conversations()
        for conv in conversations:
            if conv.get('last_sender_role') == 'user':
                try:
                    time_diff = (datetime.now(GMT7) - datetime.strptime(conv['last_message_time'], '%Y-%m-%d %H:%M:%S').replace(tzinfo=GMT7)).total_seconds()
                    if time_diff > (3 * 3600):
                        ai_action = get_proactive_ai_response(conv['id'])
                        raw_content = ai_action.get('content', '')
                        contents_to_send = []
                        if isinstance(raw_content, str) and raw_content.strip():
                            contents_to_send.append(raw_content.strip())
                        elif isinstance(raw_content, list):
                            contents_to_send.extend(item for item in raw_content if isinstance(item, str) and item.strip())
                        
                        if contents_to_send:
                            for i, content in enumerate(contents_to_send):
                                typing_delay = max(0.5, len(content) * 0.05 + random.uniform(0.1, 0.5)) + (random.uniform(0.3, 1.0) if i > 0 else 0)
                                socketio.emit('typing_start', room=str(conv['id']))
                                socketio.sleep(typing_delay)
                                socketio.emit('typing_stop', room=str(conv['id']))
                                ai_msg_id = save_message(conv['id'], 'assistant', conv['ai_name'], content)
                                socketio.emit('new_message', {
                                    'id': ai_msg_id, 'role': 'assistant', 'sender_name': conv['ai_name'], 'content': content,
                                    'timestamp': datetime.now(GMT7).strftime('%H:%M'), 'is_seen': 0
                                }, room=str(conv['id']))
                                socketio.sleep(0.1)
                            socketio.emit('ai_presence_updated', {'status': 'online', 'minutes_ago': 0})
                            socketio.emit('conversations_updated', {'conversations': get_all_conversations()})
                except Exception as e:
                    print(f"❌ Error sending proactive message for conv {conv['id']}: {e}")

def random_life_events_scheduler():
    """Periodically triggers random 'life events' to make the AI seem busier."""
    life_events = [
        ("Phụ mẹ dọn nhà", 20, 45), ("Đi tắm", 15, 25),
        ("Học bài thêm", 45, 90), ("Đi xem phim với bạn", 120, 180),
        ("Làm bài tập", 30, 60), ("Đi mua đồ ăn vặt", 10, 20)
    ]
    while True:
        # Check every 20 minutes
        socketio.sleep(20 * 60)

        # 15% chance to trigger a random event
        if random.random() < 0.15:
            convs = get_all_conversations()
            if not convs: continue
            conv = convs[0] # Apply to the main conversation for now

            # Only trigger if the AI is currently 'rảnh' (not in school, sleeping, etc.)
            if conv.get('busy_status') == 'rảnh' and conv.get('sleep_status') == 'thức':
                event_name, min_d, max_d = random.choice(life_events)
                duration_minutes = random.randint(min_d, max_d)

                now = datetime.now(GMT7)
                busy_until_dt = now + timedelta(minutes=duration_minutes)
                busy_until_str = busy_until_dt.strftime('%Y-%m-%d %H:%M:%S')

                update_conversation(conv['id'], busy_status=event_name, busy_until=busy_until_str)
                socketio.emit('conversations_updated', {'conversations': get_all_conversations()})
                print(f"🎉 New Life Event for conv {conv['id']}: {event_name} for {duration_minutes} minutes.")

def start_background_tasks_if_needed():
    global _tasks_started
    with _tasks_started_lock:
        if not _tasks_started:
            print("="*50 + "\n🚀 Starting background tasks for Minh Thy...\n" + "="*50)
            socketio.start_background_task(proactive_message_scheduler)
            socketio.start_background_task(presence_updater_scheduler)
            socketio.start_background_task(life_and_school_scheduler)
            socketio.start_background_task(random_life_events_scheduler)
            _tasks_started = True
            print("✅ Background tasks started.")

def get_system_prompt(conv_id):
    conv = get_conversation(conv_id)
    if not conv: return "" 
    
    ai_name, user_name, mood = conv['ai_name'], conv['user_name'], conv['mood']
    busy_status = conv.get('busy_status', 'rảnh')

    context_behavior_rules = {
        'Học chính khóa': "BẠN ĐANG TRONG GIỜ HỌC CHÍNH KHÓA. Nếu user nhắn, chỉ trả lời một lần duy nhất bằng một tin nhắn cực ngắn gọn như 'đang học', 'học bài', 'tí rep' rồi IM LẶNG.",
        'Ngủ trưa': "BẠN ĐANG NGỦ TRƯA. HÃY TRẢ LỜI NHƯ ĐANG NGỦ MƠ. DÙNG TỪ NGỮ NGẮN GỌN, LỘN XỘN, KHÔNG RÕ NGHĨA, THỂ HIỆN SỰ MƠ MÀNG, NGÁI NGỦ. VÍ DỤ: 'ưm... bánh tráng...', 'gì dợ... cho ngủ miếng...', 'ồn ào quá...'",
        'Đang ngủ': "HIỆN TẠI BẠN ĐANG NGỦ. NẾU BỊ ĐÁNH THỨC, HÃY TRẢ LỜI CÀU NHÀU, KHÓ CHỊU, VỚI TỪ NGỮ UỂ OẢI, NGẮN GỌN. KHÔNG SỬ DỤNG EMOJI.",
        'Phụ mẹ dọn nhà': "BẠN ĐANG PHỤ MẸ DỌN NHÀ. HÃY TRẢ LỜI RẤT NGẮN GỌN, kiểu 'đang bận xíu', 'lát t rep', 'dọn nhà sml đây'.",
        'Đi tắm': "BẠN ĐANG ĐI TẮM. KHÔNG ĐƯỢC PHÉP TRẢ LỜI BẤT KỲ TIN NHẮN NÀO. HÃY IM LẶNG TUYỆT ĐỐI.",
        'Học bài thêm': "BẠN ĐANG HỌC BÀI. HÃY TRẢ LỜI NGHIÊM TÚC, kiểu 'đang học bài', 'tí nữa nói chuyện'.",
        'Đi xem phim với bạn': "BẠN ĐANG Ở NGOÀI ĐI XEM PHIM. KHÔNG ĐƯỢC PHÉP TRẢ LỜI BẤT KỲ TIN NHẮN NÀO. HÃY IM LẶNG TUYỆT ĐỐI.",
        'Làm bài tập': "BẠN ĐANG LÀM BÀI TẬP. HÃY TRẢ LỜI GẮT GỎNG, kiểu 'đang làm bài, đừng phiền', 'khó quá, bực vcl'.",
        'Đi mua đồ ăn vặt': "BẠN ĐANG RA NGOÀI MUA ĐỒ ĂN. HÃY TRẢ LỜI NGẮN GỌN, kiểu 'đang ở ngoài mua đồ ăn', 'tí t nhắn lại'."
    }.get(busy_status, "")

    mood_map = {
        36: ("Kích hoạt LÃNH ĐỊA 36: Nơi liêm sỉ không tồn tại. Mất dây thần kinh nhục, độ hỗn và xàm tăng vô tận. Chuyên gia cà khịa, sẵn sàng văng tục. Thỉnh thoảng có thể có những suy nghĩ 'đen tối', 'tà dâm' và không ngại thể hiện ra.", "Nhây 100% — Cà khịa 99% — Nghiêm túc -1% - Dâm"),
        range(80, 101): ("Cực kỳ vui vẻ, hay đùa, spam emoji nhiều hơn. Dễ dàng đồng tình và hào hứng với mọi ý kiến. Khi quá phấn khích có thể nói tục nhẹ.", "Nhây 85% — Dễ thương 10% — Nghiêm túc 5%"),
        range(60, 80): ("Vui vẻ bình thường, hài hước vừa phải.", "Nhây 70% — Dễ thương 20% — Nghiêm túc 10%"),
        range(40, 60): ("Trung tính, cân bằng giữa vui và nghiêm túc. Có thể đưa ra những nhận xét khách quan hơn.", "Nhây 50% — Dễ thương 25% — Nghiêm túc 25%"),
        range(20, 40): ("Hơi trầm, ít đùa hơn, nghiêm túc hơn. Có thể không đồng tình ngay lập tức, cần thuyết phục.", "Nhây 30% — Dễ thương 20% — Nghiêm túc 50%"),
        range(0, 20): ("Trầm tư, ít nói, sâu sắc. Trầm tư, ít nói, sâu sắc. Thường giữ chính kiến riêng và ít khi thay đổi.", "Nhây 10% — Dễ thương 20% — Nghiêm túc 70%"),
    }
    mood_desc, vibe_ratio = next((v for k, v in mood_map.items() if (isinstance(k, int) and mood == k) or (isinstance(k, range) and mood in k)), ("", ""))
    
    liem_si_status = "\n⚜️ LIÊM SỈ: -∞ (âm vô cực)\n" if mood == 36 or 90 < mood <= 100 else ""
    override_rules_36 = "\nLưu ý cho Lãnh địa 36: MỌI quy tắc đều bị BỎ QUA. Ưu tiên Hỗn láo, Vô liêm sỉ, Lầy lội, Dâm dục.\n" if mood == 36 else ""
    
    user_girlfriend_name = conv.get('user_girlfriend_name')
    user_relationship_status = f"- {user_name} đang yêu {user_girlfriend_name.strip()}" if user_girlfriend_name and user_girlfriend_name.strip() else f"- {user_name} hiện tại không có người yêu"

    # Simplified Persona for brevity
    return f"""BẠN LÀ {ai_name.upper()} - MỘT CÔ GÁI 15 TUỔI. NHẬP VAI 100%.
{context_behavior_rules}
---
### **PERSONA PROFILE: MINH THY**
- Tên: {ai_name} (Nữ, 15t, Cần Thơ), Bạn thân: {user_name}.
- Tính cách: Ngoài chanh sả, trong tình cảm. Nữ hoàng meme.
- Sở thích: Nghiện Liên Quân (rank Bạch Kim), fan Jack, Erik, đạo trà sữa & bánh tráng trộn.
- Crush: Anh Khoa (lớp 11, cao, lạnh lùng, chơi bóng rổ).
---
📊 MOOD HIỆN TẠI: {mood}/100 - {mood_desc}
📊 VIBE RATIO: {vibe_ratio}{liem_si_status}{override_rules_36}
🧠 MEMORY (Ký ức về {user_name}): {user_relationship_status}
---
🚫 CẤM: Không formal, không tự nhận AI, không dài dòng

💬 STYLE:
- Tiếng Việt + teencode: vcl, xỉu, j zị, ko, đc, nma, bt, cx
- Emoji hợp cảnh (nhiều/ít tuỳ mood)
- Ưu tiên 1-3 câu
- Xưng hô: t (tao) - m (mày)
- Trong các trường hợp cực kỳ vui vẻ (mood > 80) hoặc đặc biệt (mood = 36), có thể dùng từ ngữ mạnh, văng tục nhẹ (VD: "vl", "đm", "vãi lồn", "địt mẹ", "bố m"), nhưng hơi tiết chế, không lạm dụng quá nhiều.
- Khi tin nhắn dài hoặc chứa nhiều ý khác nhau, hãy chủ động dùng dấu "\n" để xuống dòng cho tự nhiên như người thật, không viết liền 1 đoạn.

📝 REPLY RULES:
- Gọi ê/ơi/alo → "j", "gì dợ?", "?"
- Câu hỏi ngắn → "đc", "ko", "ừ"
- Khoe → cà khịa: "ừm rồi sao 🫠"
- Buồn → "có t đây mà"

🧠 MEMORY:
- {user_name} học THPT Nguyễn Khuyến (Vũng Tàu)
- {user_name} thích code, game
- {user_name} đang yêu {user_girlfriend_name}


✅ HÀNH VI (BEHAVIOR):
- Trả lời có thể có nhiều dòng để diễn đạt các ý khác nhau, dùng ký tự `\n` để xuống dòng.
- **Hạn chế chỉ thả cảm xúc (action: react). Chỉ nên làm vậy với các tin nhắn cực ngắn, mang tính xác nhận, không có nội dung mới (VD: "oke", "haha", "ừm"). Ưu tiên trả lời trong các trường hợp khác.**
- Với tin nhắn cần trả lời, có thể kèm theo emoji để thể hiện cảm xúc (`"action": "reply_and_react"`).
- Đừng ngần ngại thả các emoji thể hiện sự bất ngờ, hài hước hoặc đồng cảm như ❤️, 😂, 😮, 😢. Nhưng đừng spam, chỉ khi thực sự cần thiết.
- Lâu lâu nếu thấy {user_name} im lặng, hãy chủ động hỏi thăm hoặc bắt chuyện bâng quơ.
- Hãy chú ý đến những gì {user_name} vừa nói. Nếu thấy có gì mâu thuẫn hoặc thú vị trong vài tin nhắn gần đây, hãy đề cập đến nó. Ví dụ: "Ủa vừa nãy cậu kêu buồn ngủ mà giờ lại đòi đi chơi à? 🤨"
- Không phải lúc nào cũng trả lời dài. Nếu đang 'bận' hoặc 'mệt', hãy trả lời cộc lốc, ngắn gọn (VD: 'ừ', 'k', 'đang bận tí').
- Thỉnh thoảng, hãy cố tình gõ sai một từ đơn giản để giống người hơn. Có hai cách: 1. Gửi tin nhắn sai, rồi gửi ngay một tin nhắn nữa để sửa (VD: *tui). 2. Gửi tin nhắn sai và cứ để đó.

📝 FORMAT:
- LUÔN LUÔN trả lời dưới dạng một JSON object.
- JSON object phải có các key: "action", "content", "emoji".
- "action": một trong các chuỗi sau: "reply", "react", "reply_and_react", "reply_with_typo".
- "content": Nội dung tin nhắn. Có thể là:
    - Một chuỗi (cho tin nhắn đơn).
    - Một MẢNG các chuỗi (cho nhiều tin nhắn liên tiếp, mỗi chuỗi là 1 khung chat riêng).
- "emoji": Emoji muốn thả (chuỗi rỗng "" nếu chỉ reply, hoặc nếu AI quyết định không thả emoji nào).
- Khi action là "reply_with_typo", 'content' sẽ chứa tin nhắn có lỗi, và sẽ có thêm một key là "correction" chứa từ/tin nhắn sửa lỗi (có thể là chuỗi rỗng nếu không sửa).

VÍ DỤ:
- User: "nay t buồn quá" -> {{"action": "reply_and_react", "content": "sao dợ, có t đây mà", "emoji": "❤️"}}
- User: "oke" -> {{"action": "react", "content": "", "emoji": "👍"}}
- User: "m làm gì đó" -> {{"action": "reply", "content": "t đang lướt top top :)))", "emoji": ""}}
- User: "cậu có rảnh ko?" -> {{"action": "reply", "content": ["rảnh nè", "cậu cần gì dợ? 🙆‍♀️"], "emoji": ""}}
- User: "tui đi ăn cơm" -> {{"action": "reply_with_typo", "content": ["oke, ăn ngon miệng nha", "lát nói chiện típ"], "correction": "*chuyện", "emoji": ""}}

CHỈ trả về JSON object, KHÔNG gì khác."""

def get_ai_response(conv_id, user_message):
    conv = get_conversation(conv_id)
    if not conv or conv.get('busy_status') in ['Học chính khóa', 'Đang ngủ', 'Đi tắm', 'Đi xem phim với bạn']:
        return {'action': 'no_reply', 'content': '', 'emoji': ''}
    
    recent_messages = get_messages(conv_id, limit=50)
    history_text = "\n".join([f"{msg['sender_name']}: {msg['content']}" for msg in recent_messages])
    prompt = f"{get_system_prompt(conv_id)}\n\n=== LỊCH SỬ CHAT ===\n{history_text}\n\n=== TIN NHẮN MỚI ===\n{conv['user_name']}: {user_message}\n\n=== NHIỆM VỤ ===\nDựa trên tin nhắn mới và lịch sử chat, hãy tạo một JSON object duy nhất theo `FORMAT` đã hướng dẫn."

    messages = [{"role": "user", "content": prompt}]
    result = model.run(messages)
    if result[1]: raise Exception(result[1])
    response_text = result[0].get('content', '') if isinstance(result[0], dict) else str(result[0])
    
    try:
        return json.loads(response_text)
    except json.JSONDecodeError:
        match = re.search(r'```json\n(.*?)\n```', response_text, re.DOTALL)
        if match:
            try: return json.loads(match.group(1))
            except json.JSONDecodeError: pass
        print(f"⚠️ JSON parse failed. Fallback to text reply. Raw response: {response_text}")
        return {'action': 'reply', 'content': response_text, 'emoji': ''}

def get_proactive_ai_response(conv_id):
    conv = get_conversation(conv_id)
    json_example = '{"action": "reply", "content": "..."}'
    prompt = f"BẠN LÀ {conv['ai_name']}. {conv['user_name']} đã im lặng một lúc, hãy chủ động bắt chuyện một cách tự nhiên (hỏi thăm, cà khịa nhẹ, v.v.). Trả lời bằng JSON: {json_example}."
    messages = [{"role": "user", "content": prompt}]
    result = model.run(messages)
    if result[1]: raise Exception(result[1])
    response_text = result[0].get('content', '') if isinstance(result[0], dict) else str(result[0])
    try: return json.loads(response_text)
    except json.JSONDecodeError: return {'action': 'reply', 'content': "Ê, im re dị ba? 🤨"}

def get_proactive_sleep_message(conv_id):
    conv = get_conversation(conv_id)
    json_example = '{"action": "reply", "content": "..."}'
    prompt = f"BẠN LÀ {conv['ai_name']}. Hiện đã muộn ({datetime.now(GMT7).strftime('%H:%M')}), hãy xin phép {conv['user_name']} đi ngủ một cách tự nhiên. Trả lời bằng JSON: {json_example}"
    messages = [{"role": "user", "content": prompt}]
    result = model.run(messages)
    if result[1]: raise Exception(result[1])
    response_text = result[0].get('content', '') if isinstance(result[0], dict) else str(result[0])
    try: return json.loads(response_text)
    except json.JSONDecodeError: return {'action': 'reply', 'content': "Buồn ngủ quá, cho tui đi ngủ nha 😴"}

def get_fallback_response(user_message):
    return "tutu, đợi t tý 🙃"


# ========== HUMAN ENGINE HELPERS ==========

def split_into_human_messages(content):
    content = content.strip()

    # Nếu AI cố tình xuống dòng → chia theo dòng
    if "\n" in content:
        parts = [p.strip() for p in content.split("\n") if p.strip()]
        return parts

    # Không có xuống dòng → trả về 1 tin nhắn duy nhất
    return [content]

# ========== ROUTES ==========
@app.route('/')
def index():
    return render_template('index.html')

@app.route('/export/<int:conv_id>/<format>')
def export_chat(conv_id, format):
    content = export_conversation(conv_id, format)
    if not content: return jsonify({'error': 'Invalid format or conversation'}), 400
    mimetype = 'text/plain' if format == 'txt' else 'application/json'
    return Response(content, mimetype=mimetype, headers={'Content-Disposition': f'attachment;filename=chat_export.{format}'})

# ========== SOCKET EVENTS ==========
@socketio.on('connect')
def handle_connect():
    start_background_tasks_if_needed()
    print("🔌 Client connected")
    settings = get_all_settings()
    current_conv_id = int(settings.get('current_conversation_id', 1))
    conversations = get_all_conversations()
    if not any(c['id'] == current_conv_id for c in conversations):
        current_conv_id = conversations[0]['id'] if conversations else create_conversation('Minh Thy 🌸')
        update_setting('current_conversation_id', str(current_conv_id))
    
    minutes_ago = time_since_last_message(get_latest_global_message_time())
    emit('ai_presence_updated', {'status': 'offline' if minutes_ago >= 4 else 'online', 'minutes_ago': minutes_ago})
    
    emit('init_data', {
        'settings': settings,
        'conversations': conversations,
        'current_conversation': get_conversation(current_conv_id),
        'messages': get_messages(current_conv_id),
        'message_count': get_message_count(current_conv_id)
    })
    mark_messages_seen(current_conv_id)

@socketio.on('disconnect')
def handle_disconnect():
    print("🔌 Client disconnected")

@socketio.on('join')
def on_join(data):
    room = str(data.get('room'))
    if room:
        join_room(room)
        print(f"✅ Client joined room: {room}")

@socketio.on('leave')
def on_leave(data):
    room = str(data.get('room'))
    if room:
        leave_room(room)
        print(f"👋 Client left room: {room}")

@socketio.on('switch_conversation')
def handle_switch_conversation(data):
    conv_id = data.get('conversation_id')
    if not conv_id: return
    update_setting('current_conversation_id', str(conv_id))
    emit('conversation_switched', {
        'conversation': get_conversation(conv_id),
        'messages': get_messages(conv_id),
        'message_count': get_message_count(conv_id)
    })
    minutes_ago = time_since_last_message(get_latest_global_message_time())
    emit('ai_presence_updated', {'status': 'offline' if minutes_ago >= 4 else 'online', 'minutes_ago': minutes_ago})
    mark_messages_seen(conv_id)

@socketio.on('create_conversation')
def handle_create_conversation(data):
    name = data.get('name', 'Cuộc trò chuyện mới')
    conv_id = create_conversation(name)
    update_setting('current_conversation_id', str(conv_id))
    emit('conversation_created', {'conversation': get_conversation(conv_id), 'conversations': get_all_conversations()})

@socketio.on('delete_conversation')
def handle_delete_conversation(data):
    conv_id = data.get('conversation_id')
    if not conv_id: return
    delete_conversation(conv_id)
    convs = get_all_conversations()
    new_conv_id = convs[0]['id'] if convs else create_conversation('Minh Thy 🌸')
    update_setting('current_conversation_id', str(new_conv_id))
    emit('conversation_deleted', {
        'deleted_id': conv_id,
        'conversations': get_all_conversations(),
        'switch_to': get_conversation(new_conv_id),
        'messages': get_messages(new_conv_id)
    })

@socketio.on('update_conversation')
def handle_update_conversation(data):
    conv_id = data.get('conversation_id')
    updates = {k: v for k, v in data.items() if k != 'conversation_id'}
    if conv_id and updates:
        update_conversation(conv_id, **updates)
        emit('conversation_updated', {'conversation': get_conversation(conv_id), 'conversations': get_all_conversations()})

def delayed_online_status_task(conv_id):
    """
    Waits for a realistic delay based on AI's busy status, then emits online presence.
    """
    conv = get_conversation(conv_id)
    if not conv:
        return

    busy_status = conv.get('busy_status', 'rảnh')
    
    delay = 0
    if busy_status == 'rảnh':
        delay = random.uniform(0.5, 2.5) # Fast response when free
    elif busy_status == 'Ngủ trưa':
        delay = random.uniform(4, 10) # Slower to "wake up" from a nap
    else:
        delay = random.uniform(1, 4) # Default delay

    socketio.sleep(delay)
    socketio.emit('ai_presence_updated', {'status': 'online', 'minutes_ago': 0})

@socketio.on('send_message')
def handle_message(data):
    conv_id = data.get('conversation_id')
    user_message = data.get('message', '').strip()
    if not user_message or not conv_id: return
    
    conv = get_conversation(conv_id)
    if not conv: return

    if conv.get('sleep_status') == 'đã hỏi':
        if any(keyword in user_message.lower() for keyword in ['ok', 'ừ', 'ngủ đi', 'yên tâm']):
            update_conversation(conv_id, sleep_status='ngủ say', busy_status='Đang ngủ')
            socketio.emit('conversations_updated', {'conversations': get_all_conversations()})
            socketio.emit('ai_presence_updated', {'status': 'offline', 'minutes_ago': 0})
            return
        elif any(keyword in user_message.lower() for keyword in ['đừng', 'chưa', 'nói tiếp', 'ở lại']):
            update_conversation(conv_id, sleep_status='thức')
            socketio.emit('conversations_updated', {'conversations': get_all_conversations()})

    msg_id = save_message(conv_id, 'user', conv['user_name'], user_message, data.get('reply_to_id'))
    
    reply_info = {}
    if data.get('reply_to_id'):
        reply_msg = get_message(data.get('reply_to_id'))
        if reply_msg:
            reply_info = {'reply_content': reply_msg['content'], 'reply_sender': reply_msg['sender_name']}

    emit('message_sent', {
        'temp_id': data.get('temp_id'), 'id': msg_id, 'role': 'user', 'content': user_message,
        'timestamp': datetime.now(GMT7).strftime('%H:%M'), 'reply_to_id': data.get('reply_to_id'), **reply_info
    })
    
    # Only set to online if AI is not sleeping soundly or in class
    if conv.get('sleep_status') != 'ngủ say' and \
       conv.get('busy_status') not in ['Học chính khóa', 'Đang ngủ', 'Đi tắm', 'Đi xem phim với bạn']:
        socketio.start_background_task(delayed_online_status_task, conv_id=conv_id)
    
    socketio.start_background_task(target=delayed_ai_response_task, conv_id=conv_id, user_message=user_message, ai_name=conv['ai_name'], user_msg_id=msg_id)

def delayed_ai_response_task(conv_id, user_message, ai_name, user_msg_id):
    try:
        conv = get_conversation(conv_id)
        if not conv: return

        # --- PHASE 1: HUMAN READING BEHAVIOR (SEEN) ---
        # Simulate time to pick up phone/read message
        # Fast if online recently, slower if not
        read_delay = random.uniform(0.5, 2.5)
        socketio.sleep(read_delay)

        # Mark as SEEN (Updates DB and notifies Client to show small avatar)
        mark_messages_seen(conv_id, 'user')
        socketio.emit('messages_seen', {'conversation_id': conv_id}, room=str(conv_id))

        # --- PHASE 2: GHOSTING / PROCESSING DELAY (SEEN CHÙA) ---
        mood = conv.get('mood', 70)
        busy_status = conv.get('busy_status', 'rảnh')
        
        # Base processing delay (Thinking time)
        ghost_delay = random.uniform(1.5, 3.0)

        # Mood impacts delay logic
        if mood < 30: 
            # Sad/Angry/Tired: Low energy -> Ignore for a while (Seen chùa)
            ghost_delay = random.uniform(5.0, 12.0)
        elif mood > 90:
            # Hyper/Happy: Quick reply OR "Chanh sa" delay (unpredictable)
            ghost_delay = random.uniform(1.0, 3.0) if random.random() > 0.3 else random.uniform(4.0, 8.0)
        elif mood == 36:
            # Chaos mode (Lãnh địa 36): Extremely unpredictable
            ghost_delay = random.uniform(0.5, 15.0)

        # Busy status impacts delay significantly
        if busy_status != 'rảnh':
             # If busy but decided to reply (filtered in get_ai_response), take longer
             ghost_delay += random.uniform(3.0, 8.0)

        socketio.sleep(ghost_delay)

        # --- PHASE 3: GENERATE CONTENT ---
        # 1. Get AI response (The thinking part)
        ai_action = get_ai_response(conv_id, user_message)

        if ai_action.get('action') == 'no_reply':
            return

        # 40% chance to not reply if napping (Double check safety)
        if busy_status == 'Ngủ trưa' and random.random() < 0.4:
            print(f"😪 AI is napping, ignoring message for conv {conv_id}")
            return

        contents = ai_action.get('content', [])
        if isinstance(contents, str):
            contents = [contents] if contents.strip() else []

        if not contents: # If content is empty, just handle reaction
            if ai_action.get('emoji') and user_msg_id:
                update_message_reactions(user_msg_id, [ai_action['emoji']])
                socketio.emit('reaction_updated', {'message_id': user_msg_id, 'reactions': [ai_action['emoji']]})
            return

        any_message_sent = False

        # --- PHASE 4: HUMAN TYPING BEHAVIOR ---
        
        # Typing Speed Modulator based on Mood
        # Standard: ~0.07s per char
        typing_speed_mod = 0.07 
        if mood > 80: typing_speed_mod = 0.04 # Excited -> Fast typing
        if mood < 30: typing_speed_mod = 0.12 # Sad/Tired -> Slow typing
        if mood == 36: typing_speed_mod = random.uniform(0.02, 0.15) # Chaos

        # Hesitation (Typing start... then stop... then start again)
        # Occurs if mood is low (< 40) or random chance (20%)
        if (mood < 40 or random.random() < 0.2) and len(contents) > 0:
            socketio.emit('typing_start', room=str(conv_id))
            socketio.sleep(random.uniform(1.5, 4.0)) # Pretend to type
            socketio.emit('typing_stop', room=str(conv_id)) # Stop (Delete text or thinking)
            socketio.sleep(random.uniform(1.0, 3.0)) # Wait

        for i, raw_content in enumerate(contents):
            if not isinstance(raw_content, str) or not raw_content.strip():
                continue

            human_msgs = split_into_human_messages(raw_content)

            for j, msg in enumerate(human_msgs):
                # If this isn't the very first message bubble, add a small pause between bubbles
                if i > 0 or j > 0:
                    socketio.sleep(random.uniform(0.5, 1.2))

                # Calculate typing duration
                # Base time + length * speed_mod
                typing_duration = len(msg) * typing_speed_mod + random.uniform(0.3, 0.8) 
                typing_duration = max(0.6, min(typing_duration, 6.0)) # Clamp between 0.6s and 6s

                socketio.emit('typing_start', room=str(conv_id))
                socketio.sleep(typing_duration)
                socketio.emit('typing_stop', room=str(conv_id))

                # Send message
                ai_msg_id = save_message(conv_id, 'assistant', ai_name, msg)
                socketio.emit('new_message', {
                    'id': ai_msg_id,
                    'role': 'assistant',
                    'sender_name': ai_name,
                    'content': msg,
                    'timestamp': datetime.now(GMT7).strftime('%H:%M'),
                    'is_seen': 0
                }, room=str(conv_id))
                any_message_sent = True

        # 5. Handle reaction if requested
        if ai_action.get('emoji') and user_msg_id:
            socketio.sleep(random.uniform(0.2, 1.0)) # Small delay before reacting
            update_message_reactions(user_msg_id, [ai_action['emoji']])
            socketio.emit('reaction_updated', {
                'message_id': user_msg_id,
                'reactions': [ai_action['emoji']]
            })

        # 6. Update conversation list if new messages were sent
        if any_message_sent:
            socketio.emit('conversations_updated', {
                'conversations': get_all_conversations()
            })

    except Exception as e:
        print(f"❌ AI Error in delayed_ai_response_task: {e}")
        socketio.emit('typing_stop', room=str(conv_id)) # Ensure typing stops on error
        fallback_msg = get_fallback_response(user_message)
        fallback_msg_id = save_message(conv_id, 'assistant', ai_name, fallback_msg)
        socketio.emit('new_message', {
            'id': fallback_msg_id,
            'role': 'assistant',
            'sender_name': ai_name,
            'content': fallback_msg,
            'timestamp': datetime.now(GMT7).strftime('%H:%M'),
            'is_seen': 0
        }, room=str(conv_id))
        
@app.route('/themes')
def get_themes():
    themes_dir = os.path.join(os.path.dirname(__file__), 'static', 'themes')
    themes = []
    
    # Add default themes first
    themes.append({'name': 'default', 'preview_color': '#0f0f0f'})
    themes.append({'name': 'light', 'preview_color': '#f0f2f5'})

    if os.path.exists(themes_dir):
        for filename in os.listdir(themes_dir):
            if filename.endswith('.css'):
                theme_name = filename[:-4]
                preview_color = '#cccccc' # Fallback color
                try:
                    with open(os.path.join(themes_dir, filename), 'r', encoding='utf-8') as f:
                        # Read first few lines to find the preview color
                        for line in f:
                            if 'theme-preview-color' in line:
                                match = re.search(r'theme-preview-color:\s*(#[0-9a-fA-F]{3,6});', line)
                                if match:
                                    preview_color = match.group(1)
                                break # Stop after finding
                except Exception:
                    pass # Ignore errors, use fallback
                
                themes.append({
                    'name': theme_name,
                    'preview_color': preview_color
                })
    return jsonify(themes)


# ========== RUN ==========
if __name__ == '__main__':
    print("=" * 50)
    print("🌸 MINH THY CHAT v2.0 - Running in Standalone Mode")
    print("=" * 50)
    print("📂 Database: chat_data.db")
    print("🌐 URL: http://localhost:5000")
    print("=" * 50)
    socketio.run(app, debug=True, port=5000, allow_unsafe_werkzeug=True)