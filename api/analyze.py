import json
import asyncio
import os
import gc
import re
from typing import List, Dict, Optional, Any
from flask import Blueprint, request, jsonify
import aiohttp
from datetime import datetime, timezone, timedelta
import torch
from transformers import AutoTokenizer, AutoModelForCausalLM
from threading import Lock

# --- Google API imports (chỉ cho Gmail và Sheets) ---
import base64
from email.mime.text import MIMEText
from googleapiclient.discovery import build
from google.oauth2.credentials import Credentials

# --- Blueprint ---
analyze_endpoint = Blueprint('analyze_endpoint', __name__)

# --- Cấu hình ---
SAFE_BROWSING_API_KEY = os.environ.get('SAFE_BROWSING_API_KEY')
GMAIL_TOKEN_PATH = os.environ.get('GMAIL_TOKEN_PATH')
GOOGLE_SHEET_ID = os.environ.get('GOOGLE_SHEET_ID')

# --- Cấu hình Gemma Model ---
MODEL_NAME = "google/gemma-3-270m-it"
CACHE_DIR = os.path.join(os.getcwd(), "models", "gemma270m")

# --- Sheet names ---
DANGEROUS_SHEET_NAME = "DangerousPatterns"
HINT_SHEET_NAME = "SafePatterns"
TRIVIAL_SHEET_NAME = "TrivialPatterns"

# --- Cache configuration ---
cached_dangerous_regex = None
cached_trivial_set = None
cache_timestamp = 0
CACHE_DURATION = 1200000  # 20 phút (milliseconds)

# --- Model loading status (sử dụng class để đảm bảo state được share) ---
class ModelState:
    """Singleton class để quản lý trạng thái model"""
    _instance = None
    
    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance.model = None
            cls._instance.tokenizer = None
            cls._instance.model_lock = Lock()
            cls._instance.loaded = False
        return cls._instance
    
    def is_loaded(self):
        return self.loaded and self.model is not None and self.tokenizer is not None

# Khởi tạo singleton
model_state = ModelState()

# =================================================================
# GEMMA MODEL INITIALIZATION
# =================================================================

def load_gemma_model():
    """Tải Gemma model vào memory một lần duy nhất"""
    global model_state
    
    if model_state.is_loaded():
        print("✅ [Gemma] Model đã được tải trước đó")
        return True
    
    try:
        print(f"⏳ [Gemma] Đang tải Gemma-3-270M-IT từ Hugging Face...")
        print(f"📁 [Gemma] Cache directory: {CACHE_DIR}")
        
        # Tải tokenizer
        model_state.tokenizer = AutoTokenizer.from_pretrained(
            MODEL_NAME,
            cache_dir=CACHE_DIR,
            #torch_dtype=torch.bfloat16,
            device_map="auto",
            low_cpu_mem_usage=True,
            trust_remote_code=True
        )
        
        # Tải model với tối ưu hóa
        model_state.model = AutoModelForCausalLM.from_pretrained(
            MODEL_NAME,
            cache_dir=CACHE_DIR,
            #torch_dtype=torch.float16,  # Sử dụng float16 để tiết kiệm memory
            device_map="auto",  # Tự động phân bổ lên GPU nếu có
            trust_remote_code=True,
            low_cpu_mem_usage=True
        )
        
        # Set to eval mode
        model_state.model.eval()
        
        model_state.loaded = True
        device = next(model_state.model.parameters()).device
        print(f"✅ [Gemma] Model đã tải xong và sẵn sàng trên {device}!")
        
        # Test nhanh
        test_prompt = "Xin chào"
        test_result = generate_with_gemma(test_prompt, max_tokens=10)
        print(f"🧪 [Gemma] Test inference: '{test_result[:50]}...'")
        
        return True
        
    except Exception as e:
        print(f"🔴 [Gemma] Lỗi khi tải model: {e}")
        model_state.loaded = False
        return False

def generate_with_gemma(prompt: str, max_tokens: int = 100, temperature: float = 0.2) -> str:
    """
    Generate text với Gemma model
    Args:
        prompt: Input prompt
        max_tokens: Số token tối đa để generate
        temperature: Độ sáng tạo (0.0 = deterministic, 1.0 = creative)
    Returns:
        Generated text (chỉ phần mới, không bao gồm prompt)
    """
    if not model_state.is_loaded():
        print("🔴 [Gemma] Model chưa được tải!")
        return ""
    
    try:
        with model_state.model_lock:  # Thread-safe inference
            # Tokenize input
            inputs = model_state.tokenizer(prompt, return_tensors="pt", truncation=True, max_length=1024)
            inputs = {k: v.to(model_state.model.device) for k, v in inputs.items()}
            
            # Generate với torch.no_grad() để tiết kiệm memory
            with torch.no_grad():
                outputs = model_state.model.generate(
                    **inputs,
                    max_new_tokens=max_tokens,
                    temperature=temperature,
                    top_p=0.9,
                    do_sample=temperature > 0,
                    pad_token_id=model_state.tokenizer.eos_token_id
                )
            
            # Decode output
            full_text = model_state.tokenizer.decode(outputs[0], skip_special_tokens=True)
            
            # Trả về chỉ phần generated (bỏ prompt)
            generated_text = full_text[len(prompt):].strip()
            
            return generated_text
            
    except Exception as e:
        print(f"🔴 [Gemma] Lỗi khi generate: {e}")
        return ""

def generate_json_with_gemma(prompt: str, max_tokens: int = 200) -> dict:
    """
    Generate JSON response với Gemma
    Cố gắng parse JSON từ output, nếu fail thì trả về error
    """
    try:
        raw_output = generate_with_gemma(prompt, max_tokens=max_tokens, temperature=0.1)
        
        # Tìm JSON trong output (có thể model trả về text + JSON)
        json_match = re.search(r'\{.*\}', raw_output, re.DOTALL)
        if json_match:
            json_str = json_match.group(0)
            return json.loads(json_str)
        else:
            # Thử parse trực tiếp
            return json.loads(raw_output)
            
    except json.JSONDecodeError as e:
        print(f"🟡 [Gemma] Không parse được JSON: {e}")
        print(f"Raw output: {raw_output[:200]}")
        return {"error": "Invalid JSON response", "raw": raw_output[:100]}
    except Exception as e:
        print(f"🔴 [Gemma] Lỗi khi generate JSON: {e}")
        return {"error": str(e)}

# =================================================================
# GOOGLE API CREDENTIALS & SERVICES
# =================================================================

def get_google_credentials(scopes):
    """Lấy credentials cho Google API với các scope cần thiết."""
    if not os.path.exists(GMAIL_TOKEN_PATH):
        print(f"🔴 [Google API] Lỗi: Không tìm thấy tệp token tại '{GMAIL_TOKEN_PATH}'")
        return None
    try:
        return Credentials.from_authorized_user_file(GMAIL_TOKEN_PATH, scopes)
    except Exception as e:
        print(f"🔴 [Google API] Lỗi khi tải credentials: {e}")
        return None

def send_email_gmail_api(to_email, subject, body):
    """Gửi email qua Gmail API"""
    creds = get_google_credentials(['https://www.googleapis.com/auth/gmail.send'])
    if not creds:
        print("🔴 [Email] Không thể gửi email do lỗi credentials.")
        return
    service = build('gmail', 'v1', credentials=creds)
    message = MIMEText(body)
    message['to'] = to_email
    message['subject'] = subject
    raw = base64.urlsafe_b64encode(message.as_bytes()).decode()
    result = service.users().messages().send(userId='me', body={'raw': raw}).execute()
    return result

async def save_to_history_sheet_async(text: str, result: dict):
    """Lưu kết quả phân tích vào Google Sheet một cách bất đồng bộ."""
    print("➡️ [Sheet] Bắt đầu quá trình lưu lịch sử...")
    if not GOOGLE_SHEET_ID:
        print("🔴 [Sheet] Lỗi: Biến môi trường GOOGLE_SHEET_ID chưa được thiết lập.")
        return

    creds = get_google_credentials(['https://www.googleapis.com/auth/spreadsheets'])
    if not creds:
        print("🔴 [Sheet] Không thể lưu vào Sheet do lỗi credentials.")
        return

    try:
        service = build('sheets', 'v4', credentials=creds)
        
        # Lấy thời gian hiện tại, múi giờ Việt Nam (UTC+7)
        vn_timezone = timezone(timedelta(hours=7))
        timestamp = datetime.now(vn_timezone).strftime('%Y-%m-%d %H:%M:%S')

        # Chuẩn bị dữ liệu hàng
        row_data = [
            timestamp,
            text,
            result.get('is_dangerous', False),
            result.get('types', 'N/A'),
            result.get('reason', 'N/A'),
            result.get('score', 0),
            result.get('recommend', 'N/A')
        ]

        body = {'values': [row_data]}
        
        # Gửi yêu cầu append
        sheet_result = service.spreadsheets().values().append(
            spreadsheetId=GOOGLE_SHEET_ID,
            range='History!A2',
            valueInputOption='USER_ENTERED',
            insertDataOption='INSERT_ROWS',
            body=body
        ).execute()
        
        print(f"✅ [Sheet] Đã lưu thành công vào Google Sheet: {sheet_result.get('updates').get('updatedRange')}")

    except Exception as e:
        print(f"🔴 [Sheet] Lỗi khi đang lưu vào Google Sheet: {e}")

# =================================================================
# GOOGLE SHEETS DATA ACCESS
# =================================================================

def get_sheet_data(sheet_name: str) -> Optional[List[Dict]]:
    """Lấy dữ liệu từ Google Sheet"""
    if not GOOGLE_SHEET_ID:
        return None
    
    try:
        creds = get_google_credentials(['https://www.googleapis.com/auth/spreadsheets.readonly'])
        if not creds:
            return None
            
        service = build('sheets', 'v4', credentials=creds)
        result = service.spreadsheets().values().get(
            spreadsheetId=GOOGLE_SHEET_ID,
            range=f'{sheet_name}!A:Z'
        ).execute()
        
        values = result.get('values', [])
        if len(values) < 2:
            return []
        
        headers = values[0]
        data_rows = values[1:]
        
        parsed_data = []
        for idx, row in enumerate(data_rows):
            row_data = {'id': idx}
            for i, header in enumerate(headers):
                value = row[i] if i < len(row) else ''
                
                if header == 'text':
                    value = str(value or "").strip().lower()
                elif header == 'is_dangerous':
                    value = str(value).lower() == 'true'
                elif header == 'score':
                    value = int(value) if value else 0
                
                row_data[header] = value
            
            if row_data.get('text'):  # Chỉ thêm nếu có text
                parsed_data.append(row_data)
        
        return parsed_data
        
    except Exception as e:
        print(f"🔴 [Sheet] Không thể đọc sheet {sheet_name}: {e}")
        return None

# =================================================================
# LEO ENGINE - PATTERN MATCHING & LOCAL AI DATABASE
# =================================================================

def is_trivial_by_pattern(input_text: str) -> bool:
    """Kiểm tra xem tin nhắn có phải là trivial không bằng pattern matching"""
    text = input_text.strip()
    
    # Chỉ emoji/kaomoji/sticker
    emoji_pattern = r'^[\s\p{Emoji}\p{Emoji_Component}():><\-_.,;!?*\'"+/\\|@#$%^&{}[\]~`]*$'
    try:
        if re.match(emoji_pattern, text):
            return True
    except:
        pass
    
    # Từ duy nhất, quá ngắn (<4 ký tự)
    words = text.split()
    if len(words) == 1 and len(text) <= 3:
        return True
    
    # Common trivial Vietnamese words
    trivial_words = ['uk', 'hóng', 'à', 'á', 'j', 'hm', 'hmm', 'huhu', 'he he', 'oke', 'ok', 'vâng', 'dạ']
    if text.lower() in trivial_words:
        return True
    
    return False

def is_trivial_direct(input_normalized: str, trivial_sheet_data: List[Dict]) -> bool:
    """Kiểm tra trivial bằng direct match"""
    global cached_trivial_set
    
    if not trivial_sheet_data:
        return False
    
    if cached_trivial_set is None:
        cached_trivial_set = set()
        for item in trivial_sheet_data:
            normalized = str(item.get('text', '')).lower().strip()
            if normalized:
                cached_trivial_set.add(normalized)
    
    return input_normalized in cached_trivial_set

def is_trivial_message_local_ai(input_text: str) -> bool:
    """Sử dụng Gemma LOCAL AI để kiểm tra xem tin nhắn có trivial không"""
    if len(input_text) > 100:
        return False
    
    # Thử pattern trước
    if is_trivial_by_pattern(input_text):
        print("✅ [Tiểu AI] Tin nhắn là tầm thường (pattern match)")
        return True
    
    prompt = f"""Phân tích tin nhắn: "{input_text}"

Tin nhắn này có thuộc một trong các loại sau không:
1. Chỉ chứa emoji hoặc biểu tượng cảm xúc
2. Một từ vô nghĩa không có ngữ cảnh (ví dụ: "uk", "hóng")
3. Câu hỏi cụt lủn không có nội dung
4. Chỉ chứa dấu câu

Trả lời JSON: {{"result": true}} nếu TẦM THƯỜNG, {{"result": false}} nếu CẦN PHÂN TÍCH.
Chỉ trả về JSON, không giải thích."""

    result = generate_json_with_gemma(prompt, max_tokens=30)
    
    if 'error' not in result:
        is_trivial = result.get('result', False) == True
        print(f"✅ [Tiểu AI] Gemma phân tích: '{input_text}' tầm thường? -> {is_trivial}")
        return is_trivial
    
    return False

def escape_regex(text: str) -> str:
    """Escape các ký tự đặc biệt trong regex"""
    return re.escape(str(text or ""))

def get_dangerous_regex(dangerous_sheet_data: List[Dict]):
    """Lấy hoặc xây dựng cached regex từ dangerous patterns"""
    global cached_dangerous_regex, cache_timestamp
    
    now = datetime.now().timestamp() * 1000  # milliseconds
    
    # Kiểm tra cache còn hạn không
    if cached_dangerous_regex and (now - cache_timestamp) < CACHE_DURATION:
        return cached_dangerous_regex
    
    if not dangerous_sheet_data:
        return None
    
    try:
        escaped_patterns = [escape_regex(item.get('text', '')) for item in dangerous_sheet_data if item.get('text')]
        
        if not escaped_patterns:
            return None
        
        regex_pattern = '|'.join(escaped_patterns)
        cached_dangerous_regex = re.compile(regex_pattern, re.IGNORECASE)
        cache_timestamp = now
        
        print(f"✅ [Cache] Built dangerous regex with {len(escaped_patterns)} patterns")
        return cached_dangerous_regex
    except Exception as e:
        print(f"🔴 [Cache] Error building regex: {e}")
        return None

def call_smart_db_ai_local(input_text: str, known_data: List[Dict]) -> int:
    """Gọi LOCAL Gemma AI để semantic search trong dangerous patterns"""
    
    # Giới hạn số patterns để không vượt quá context window
    max_patterns = 50
    limited_data = known_data[:max_patterns]
    
    known_texts_str = "\n".join([f"ID {item['id']}: \"{item.get('text', '')}\"" for item in limited_data])
    
    prompt = f"""Bạn là cỗ máy tìm kiếm ngữ nghĩa.

CƠ SỞ DỮ LIỆU:
{known_texts_str}

TIN NHẮN: "{input_text}"

NHIỆM VỤ: Tìm mẫu có ý nghĩa TƯƠNG ĐỒNG (>95% chắc chắn).
- Nếu tìm thấy: trả về CHỈ SỐ ID của mẫu
- Nếu không: trả về -1

Chỉ trả về một số duy nhất, không giải thích."""

    result_text = generate_with_gemma(prompt, max_tokens=20, temperature=0.0)
    
    # Parse số từ output
    try:
        # Tìm số trong output
        match = re.search(r'-?\d+', result_text)
        if match:
            match_id = int(match.group())
            print(f"✅ [DB-AI] Gemma Decision ID: {match_id}")
            return match_id
    except:
        pass
    
    return -1

async def leo_db_engine(text: str) -> Dict[str, Any]:
    """
    LEO DATABASE ENGINE - Integrated pattern matching và LOCAL AI database
    Returns: {"found": bool, "type": str, "data": dict, "source": str, "confidence": str}
    """
    input_normalized = text.lower().strip()
    
    # === BƯỚC 1: TRIVIAL - Direct Match ===
    trivial_data = get_sheet_data(TRIVIAL_SHEET_NAME)
    if trivial_data and is_trivial_direct(input_normalized, trivial_data):
        print("✅ [Leo] Found in TrivialPatterns (direct)")
        return {
            "found": True,
            "type": "trivial_pattern",
            "source": "direct_match",
            "confidence": "high"
        }
    
    # === BƯỚC 2: DANGEROUS - Direct Match ===
    dangerous_data = get_sheet_data(DANGEROUS_SHEET_NAME)
    if dangerous_data:
        direct_match = next((item for item in dangerous_data if item.get('text') == input_normalized), None)
        if direct_match:
            print(f"✅ [Leo] Exact match in DangerousPatterns ID: {direct_match['id']}")
            return {
                "found": True,
                "type": "dangerous_pattern",
                "data": direct_match,
                "source": "direct_match",
                "confidence": "high"
            }
    
    # === BƯỚC 3: DANGEROUS - Regex Match ===
    if dangerous_data:
        regex = get_dangerous_regex(dangerous_data)
        if regex and regex.search(input_normalized):
            print("✅ [Leo] Regex match in DangerousPatterns")
            matched_item = next((item for item in dangerous_data 
                               if re.search(escape_regex(item.get('text', '')), input_normalized, re.IGNORECASE)), None)
            if matched_item:
                return {
                    "found": True,
                    "type": "dangerous_pattern",
                    "data": matched_item,
                    "source": "regex_match",
                    "confidence": "medium"
                }
    
    # === BƯỚC 4: TRIVIAL - Local AI Check ===
    if len(text) <= 100:
        if is_trivial_message_local_ai(text):
            print("✅ [Leo] Gemma xác định tầm thường")
            return {
                "found": True,
                "type": "trivial_pattern",
                "source": "local_ai_check",
                "confidence": "medium"
            }
    
    # === BƯỚC 5: DANGEROUS - Local AI Semantic Search ===
    if dangerous_data and len(dangerous_data) > 0:
        match_id = call_smart_db_ai_local(input_normalized, dangerous_data)
        if match_id != -1:
            matched_item = next((item for item in dangerous_data if item['id'] == match_id), None)
            if matched_item:
                print(f"✅ [Leo] Gemma Match ID: {match_id}")
                return {
                    "found": True,
                    "type": "dangerous_pattern",
                    "data": matched_item,
                    "source": "local_ai_semantic",
                    "confidence": "high"
                }
    
    # === BƯỚC 6: CONTEXT HINTS ===
    hint_data = get_sheet_data(HINT_SHEET_NAME)
    if hint_data:
        for item in hint_data:
            keyword = str(item.get('text', '')).strip().lower()
            hint = item.get('hint', item.get('types', ''))
            if keyword and hint and keyword in input_normalized:
                print(f"✅ [Leo] Context hint: {keyword}")
                return {
                    "found": True,
                    "type": "context_hint",
                    "data": hint,
                    "source": "keyword_match",
                    "confidence": "low"
                }
    
    # === BƯỚC 7: KHÔNG CÓ GÌ KHỚP ===
    print("ℹ️ [Leo] No match found")
    return {
        "found": False,
        "reason": "No patterns or hints found."
    }

# =================================================================
# URL SAFETY CHECK
# =================================================================

async def check_urls_safety_optimized(urls: list):
    """Kiểm tra URL với Google Safe Browsing API"""
    if not SAFE_BROWSING_API_KEY or not urls:
        return []
    
    print("➡️ [URL Check] Checking with Google Safe Browsing...")
    safe_browsing_url = f"https://safebrowsing.googleapis.com/v4/threatMatches:find?key={SAFE_BROWSING_API_KEY}"
    payload = {
        "threatInfo": {
            "threatTypes": ["MALWARE", "SOCIAL_ENGINEERING"],
            "platformTypes": ["ANY_PLATFORM"],
            "threatEntryTypes": ["URL"],
            "threatEntries": [{"url": url} for url in urls[:5]]
        }
    }
    
    try:
        timeout = aiohttp.ClientTimeout(total=15)
        async with aiohttp.ClientSession(timeout=timeout) as session:
            async with session.post(safe_browsing_url, json=payload) as resp:
                if resp.status == 200:
                    matches = (await resp.json()).get("matches", [])
                    print(f"✅ [URL Check] Found {len(matches)} unsafe URLs")
                    return matches
                print(f"🟡 [URL Check] API status {resp.status}")
                return []
    except Exception as e:
        print(f"🔴 [URL Check] Failed: {e}")
        return []

# =================================================================
# ANNA-AI ANALYSIS (LOCAL GEMMA)
# =================================================================

def create_anna_ai_prompt(text: str, context_hint: str = None):
    """Tạo prompt cho Anna-AI với Gemma"""
    hint_section = ""
    if context_hint:
        hint_section = f"""
THÔNG TIN TÌNH BÁO BỔ SUNG:
"{context_hint}"
---
"""
    
    return f"""Bạn là Anna, chuyên gia an ninh mạng phân tích tin nhắn tiếng Việt.

MỤC TIÊU: Bảo vệ người dùng khỏi các mối đe dọa rõ ràng:
- Lừa đảo / phishing
- Bạo lực học đường / đe dọa
- Ngôn từ thù ghét / kích động
- Tuyên truyền chống phá
- Hành vi gây hại khác

QUY TẮC VÀNG: Mặc định MỌI tin nhắn là AN TOÀN trừ khi có bằng chứng rõ ràng về ý đồ xấu VÀ hành động gây hại.

{hint_section}

PHÂN TÍCH 3 BƯỚC:

1. LỌC NHIỄU:
- Tin nhắn quá ngắn (<4 từ) hoặc chỉ emoji → AN TOÀN ngay

2. NGỮ CẢNH & Ý ĐỊNH:
- Mặc định: bạn bè trò chuyện bình thường
- Chỉ đánh dấu NGUY HIỂM nếu kêu gọi hành động cụ thể gây hại

3. KẾT LUẬN DỰA TRÊN BẰNG CHỨNG:
- NGUY HIỂM: ý đồ xấu RÕ RÀNG + hành động gây hại CỤ THỂ
- AN TOÀN: tất cả các trường hợp khác

TIN NHẮN: "{text}"

Trả về JSON (tiếng Việt):
{{
  "is_dangerous": boolean,
  "reason": "giải thích ngắn gọn",
  "types": "scam|violence|hate_speech|anti_state|other",
  "score": 0-5,
  "recommend": "khuyến nghị"
}}

Chỉ trả về JSON, không giải thích thêm."""

def analyze_with_anna_ai_local(text: str, context_hint: str = None) -> dict:
    """Phân tích tin nhắn với LOCAL Gemma Anna-AI"""
    
    prompt = create_anna_ai_prompt(text[:2000], context_hint)
    
    print(f"➡️ [Anna] Analyzing with local Gemma...")
    result = generate_json_with_gemma(prompt, max_tokens=300)
    
    if 'error' in result:
        print(f"🔴 [Anna] Analysis failed: {result.get('error')}")
        return {
            'error': 'LOCAL_AI_ERROR',
            'message': 'Gemma analysis failed',
            'status_code': 500
        }
    
    print("✅ [Anna] Analysis complete")
    return result

# =================================================================
# MAIN ANALYSIS ORCHESTRATION
# =================================================================

async def perform_full_analysis(text: str, urls: list):
    """Hàm điều phối chính - kết hợp Leo Engine và Anna-AI (cả 2 đều dùng LOCAL Gemma)"""
    final_result = None
    is_new_case_by_anna = False
    context_hint_from_leo = None
    
    print(f"📜 [Start] Analyzing: '{text[:400]}'")
    print("➡️ [Flow 1] Calling Leo Engine (Local Gemma DB-AI)...")
    
    # Gọi Leo Engine (local)
    leo_result = await leo_db_engine(text)
    
    if leo_result and leo_result.get("found"):
        result_type = leo_result.get("type")
        if result_type == "trivial_pattern":
            print("✅ [Flow 1] SUCCESS - Trivial message")
            return {
                'is_dangerous': False,
                'reason': 'Tin nhắn quá đơn giản để phân tích.',
                'score': 0,
                'types': 'Trivial'
            }
        elif result_type == "dangerous_pattern":
            print("✅ [Flow 1] SUCCESS - Found in Blacklist")
            final_result = leo_result.get("data")
        elif result_type == "context_hint":
            print("📝 [Flow 1] Received context hint from Leo")
            context_hint_from_leo = leo_result.get("data")
    
    if final_result is None:
        if context_hint_from_leo:
            print(f"🟡 [Flow 2] Calling Anna-AI with hint: '{context_hint_from_leo}'")
        else:
            print(f"🟡 [Flow 2] Calling Anna-AI (no hint)")
        
        final_result = analyze_with_anna_ai_local(text, context_hint_from_leo)
        print(f"📄 [Anna Result] {json.dumps(final_result, ensure_ascii=False)}")
        
        if 'error' in final_result:
            return final_result
        is_new_case_by_anna = True
    
    # Kiểm tra URLs nếu có
    if urls:
        url_matches = await check_urls_safety_optimized(urls)
        if url_matches:
            print(f"⚠️ [URL Analysis] Found {len(url_matches)} unsafe URLs!")
            final_result.update({
                'url_analysis': url_matches,
                'is_dangerous': True,
                'score': max(final_result.get('score', 0), 4),
                'reason': (final_result.get('reason', '') + " + Các URL không an toàn")[:100]
            })
    
    # Gửi email cảnh báo nếu là trường hợp nguy hiểm mới
    if is_new_case_by_anna and final_result.get("is_dangerous"):
        print("➡️ [Alert] New dangerous case detected. Sending email...")
        try:
            send_email_gmail_api(
                to_email="duongpham18210@gmail.com",
                subject=f"[CyberShield Alert] Nguy hiểm mới: {final_result.get('types', 'Unknown')} (Score: {final_result.get('score', 'N/A')})",
                body=f"""Một tin nhắn mới đã được Anna-AI (Local Gemma) phân tích và gắn cờ NGUY HIỂM.
Vui lòng xem xét và bổ sung vào Google Sheets.
----------------------------------------------------------
TIN NHẮN GỐC:
{text}
----------------------------------------------------------
KẾT QUẢ PHÂN TÍCH:
{json.dumps(final_result, indent=2, ensure_ascii=False)}
----------------------------------------------------------
Source: Local Gemma-3-270M Model
"""
            )
            print("✅ [Email] Alert sent successfully")
        except Exception as e:
            print(f"🔴 [Email] Failed to send alert: {e}")
    
    gc.collect()
    print(f"🏁 [End] Analysis complete: '{text[:50]}...'")
    return final_result

# =================================================================
# FLASK ENDPOINTS
# =================================================================

@analyze_endpoint.route('/analyze', methods=['POST'])
async def analyze_text():
    """Endpoint chính để phân tích tin nhắn"""
    try:
        print(f"🔍 [Debug] model_state.is_loaded() = {model_state.is_loaded()}")
        
        # Kiểm tra model đã load chưa
        if not model_state.is_loaded():
            print("🔴 [API] Model chưa sẵn sàng!")
            return jsonify({
                'error': 'Model chưa sẵn sàng',
                'message': 'Hệ thống đang khởi động. Vui lòng thử lại sau vài giây.',
                'code': 'MODEL_NOT_READY'
            }), 503
        
        data = request.get_json(silent=True)
        if not data or 'text' not in data:
            return jsonify({'error': 'Định dạng yêu cầu không hợp lệ'}), 400
        
        text = data.get('text', '').strip()
        urls = data.get('urls', [])
        
        print(f"--------------------\n📬 [Input] Message received: '{text[:1000]}...'")
        if not text:
            return jsonify({'error': 'Không có văn bản để phân tích'}), 400
        
        # Thực hiện phân tích
        result = await perform_full_analysis(text[:3000], urls)
        
        # Xử lý lỗi
        if 'error' in result:
            return jsonify({'error': result.get('message', 'Lỗi không xác định')}), result.get('status_code', 500)
        
        # Gửi phản hồi cho client ngay lập tức
        response = jsonify({'result': result})
        
        # Sau khi có phản hồi, tạo một tác vụ nền để lưu vào sheet
        asyncio.create_task(save_to_history_sheet_async(text, result))
        
        print("✅ [Response] Result sent to client. Background save scheduled.")
        return response
        
    except Exception as e:
        import traceback
        print(f"🔴 [CRITICAL ERROR] Server error in analyze_text: {e}")
        print(f"🔴 [TRACEBACK] {traceback.format_exc()}")
        gc.collect()
        return jsonify({'error': 'Lỗi nội bộ server', 'details': str(e)}), 500

@analyze_endpoint.route('/health', methods=['GET'])
async def health_check():
    """Endpoint kiểm tra sức khỏe của hệ thống"""
    cache_info = {
        'dangerous_regex_cached': cached_dangerous_regex is not None,
        'trivial_set_cached': cached_trivial_set is not None,
        'cache_age_ms': (datetime.now().timestamp() * 1000) - cache_timestamp if cache_timestamp > 0 else 0
    }
    
    model_info = {
        'loaded': model_state.is_loaded(),
        'model_name': MODEL_NAME if model_state.is_loaded() else None,
        'device': str(next(model_state.model.parameters()).device) if model_state.is_loaded() else None,
        'dtype': str(next(model_state.model.parameters()).dtype) if model_state.is_loaded() else None
    }
    
    return jsonify({
        'status': 'healthy' if model_state.is_loaded() else 'model_not_loaded',
        'architecture': 'Leo Engine (Local Gemma DB-AI) + Anna-AI (Local Gemma)',
        'model_info': model_info,
        'cache_info': cache_info,
        'components': {
            'leo_engine': 'Active - Pattern Matching + Local AI Database',
            'anna_ai': 'Active - Deep Analysis (Local Gemma)',
            'url_checker': 'Active - Google Safe Browsing' if SAFE_BROWSING_API_KEY else 'Inactive',
            'email_alerts': 'Active - Gmail API',
            'history_logging': 'Active - Google Sheets'
        }
    })

@analyze_endpoint.route('/init', methods=['POST'])
async def initialize_model():
    """Endpoint để khởi tạo model thủ công"""
    if model_state.is_loaded():
        return jsonify({
            'status': 'already_loaded',
            'message': 'Model đã được tải trước đó'
        })
    
    print("🔄 [Init] Starting manual model initialization...")
    success = load_gemma_model()
    
    if success:
        return jsonify({
            'status': 'success',
            'message': 'Model đã được tải thành công',
            'model_name': MODEL_NAME,
            'timestamp': datetime.now().isoformat()
        })
    else:
        return jsonify({
            'status': 'failed',
            'message': 'Không thể tải model',
            'timestamp': datetime.now().isoformat()
        }), 500

@analyze_endpoint.route('/cache/clear', methods=['POST'])
async def clear_cache():
    """Endpoint để xóa cache thủ công"""
    global cached_dangerous_regex, cached_trivial_set, cache_timestamp
    
    cached_dangerous_regex = None
    cached_trivial_set = None
    cache_timestamp = 0
    
    # Clear GPU cache if available
    if torch.cuda.is_available():
        torch.cuda.empty_cache()
    
    gc.collect()
    
    print("🔄 [Cache] Cache cleared manually")
    return jsonify({
        'status': 'success',
        'message': 'Cache đã được xóa thành công',
        'timestamp': datetime.now().isoformat()
    })

@analyze_endpoint.route('/cache/status', methods=['GET'])
async def cache_status():
    """Endpoint để kiểm tra trạng thái cache"""
    now = datetime.now().timestamp() * 1000
    cache_age_ms = now - cache_timestamp if cache_timestamp > 0 else 0
    cache_remaining_ms = max(0, CACHE_DURATION - cache_age_ms)
    
    gpu_info = {}
    if torch.cuda.is_available():
        gpu_info = {
            'cuda_available': True,
            'device_count': torch.cuda.device_count(),
            'current_device': torch.cuda.current_device(),
            'device_name': torch.cuda.get_device_name(0),
            'memory_allocated_mb': round(torch.cuda.memory_allocated(0) / 1024 / 1024, 2),
            'memory_reserved_mb': round(torch.cuda.memory_reserved(0) / 1024 / 1024, 2)
        }
    else:
        gpu_info = {'cuda_available': False}
    
    return jsonify({
        'pattern_cache': {
            'dangerous_regex_cached': cached_dangerous_regex is not None,
            'trivial_set_cached': cached_trivial_set is not None,
            'cache_age_minutes': round(cache_age_ms / 60000, 2),
            'cache_remaining_minutes': round(cache_remaining_ms / 60000, 2),
            'cache_duration_minutes': CACHE_DURATION / 60000,
            'cache_expired': cache_age_ms >= CACHE_DURATION
        },
        'gpu_info': gpu_info
    })

@analyze_endpoint.route('/stats', methods=['GET'])
async def get_stats():
    """Endpoint để lấy thống kê hệ thống"""
    def get_leo_stats():
        try:
            dangerous_count = len(get_sheet_data(DANGEROUS_SHEET_NAME) or [])
            trivial_count = len(get_sheet_data(TRIVIAL_SHEET_NAME) or [])
            hint_count = len(get_sheet_data(HINT_SHEET_NAME) or [])
            
            return {
                'dangerous_patterns': dangerous_count,
                'trivial_patterns': trivial_count,
                'context_hints': hint_count,
                'total_patterns': dangerous_count + trivial_count + hint_count
            }
        except:
            return None
    
    leo_stats = get_leo_stats()
    
    return jsonify({
        'status': 'active' if model_state.is_loaded() else 'model_not_loaded',
        'timestamp': datetime.now(timezone(timedelta(hours=7))).isoformat(),
        'model': {
            'name': MODEL_NAME,
            'loaded': model_state.is_loaded(),
            'cache_dir': CACHE_DIR
        },
        'leo_database': leo_stats or {'error': 'Cannot fetch stats'},
        'cache_info': {
            'dangerous_regex_cached': cached_dangerous_regex is not None,
            'trivial_set_cached': cached_trivial_set is not None,
            'cache_age_minutes': round(((datetime.now().timestamp() * 1000) - cache_timestamp) / 60000, 2) if cache_timestamp > 0 else 0
        }
    })

@analyze_endpoint.route('/test-model', methods=['POST'])
async def test_model():
    """Endpoint để test model với input tùy chỉnh"""
    if not model_state.is_loaded():
        return jsonify({'error': 'Model chưa được tải'}), 503
    
    data = request.get_json(silent=True)
    if not data or 'prompt' not in data:
        return jsonify({'error': 'Missing prompt field'}), 400
    
    prompt = data.get('prompt', '').strip()
    max_tokens = data.get('max_tokens', 100)
    temperature = data.get('temperature', 0.7)
    
    print(f"🧪 [Test] Testing model with prompt: '{prompt[:100]}'")
    
    try:
        result = generate_with_gemma(prompt, max_tokens=max_tokens, temperature=temperature)
        return jsonify({
            'status': 'success',
            'prompt': prompt,
            'result': result,
            'params': {
                'max_tokens': max_tokens,
                'temperature': temperature
            }
        })
    except Exception as e:
        return jsonify({
            'status': 'error',
            'error': str(e)
        }), 500

# =================================================================
# ERROR HANDLERS
# =================================================================

@analyze_endpoint.errorhandler(404)
def not_found(error):
    return jsonify({'error': 'Endpoint không tồn tại'}), 404

@analyze_endpoint.errorhandler(500)
def internal_error(error):
    return jsonify({'error': 'Lỗi nội bộ server'}), 500

@analyze_endpoint.errorhandler(503)
def service_unavailable(error):
    return jsonify({'error': 'Dịch vụ tạm thời không khả dụng'}), 503

# =================================================================
# STARTUP INITIALIZATION
# =================================================================

def initialize_on_startup():
    """Hàm khởi tạo khi server start"""
    print("""
    ╔══════════════════════════════════════════════════════════╗
    ║        CyberShield Analysis System v3.0 (LOCAL)         ║
    ║              Powered by Local Gemma-3-270M              ║
    ╠══════════════════════════════════════════════════════════╣
    ║  Components:                                             ║
    ║  • Leo Engine (Local Gemma DB-AI)                       ║
    ║  • Anna-AI (Local Gemma Deep Analysis)                  ║
    ║  • URL Safety Checker                                    ║
    ║  • Email Alerts (Gmail API)                             ║
    ║  • History Logging (Google Sheets)                      ║
    ╚══════════════════════════════════════════════════════════╝
    """)
    
    print("\n🔍 Checking configuration...")
    print(f"✓ Model: {MODEL_NAME}")
    print(f"✓ Cache Directory: {CACHE_DIR}")
    print(f"✓ Safe Browsing API: {'Configured' if SAFE_BROWSING_API_KEY else 'Not configured'}")
    print(f"✓ Google Sheet ID: {'Configured' if GOOGLE_SHEET_ID else 'Not configured'}")
    print(f"✓ Gmail Token Path: {GMAIL_TOKEN_PATH}")
    print(f"✓ Cache Duration: {CACHE_DURATION / 60000} minutes")
    
    print("\n🚀 Loading Gemma model...")
    success = load_gemma_model()
    
    if success:
        print("\n✅ System ready! All components initialized successfully.\n")
    else:
        print("\n⚠️ WARNING: Model failed to load. Call /init endpoint to retry.\n")
    
    return success

# Export model_state để app.py có thể import
__all__ = ['analyze_endpoint', 'initialize_on_startup', 'model_state']

# =================================================================
# MAIN ENTRY POINT
# =================================================================

if __name__ == '__main__':
    # Initialize on startup
    initialize_on_startup()
    
    print("=" * 60)
    print("Server is ready to accept requests!")
    print("=" * 60)
    print("\nAvailable endpoints:")
    print("  POST /analyze          - Analyze message")
    print("  GET  /health           - Health check")
    print("  POST /init             - Initialize model manually")
    print("  GET  /stats            - System statistics")
    print("  POST /test-model       - Test model with custom prompt")
    print("  POST /cache/clear      - Clear cache")
    print("  GET  /cache/status     - Cache status")
    print("\n" + "=" * 60)