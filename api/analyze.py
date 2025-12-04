# api/analyze.py (Điều phối viên)

import json
import asyncio
import os
import gc
import re
import base64
from email.mime.text import MIMEText # <-- DÒNG NÀY ĐÃ ĐƯỢC THÊM
import random
from flask import Blueprint, request, jsonify
import aiohttp
from datetime import datetime, timezone, timedelta

# --- Google API imports (cho Email và Sheets) ---
from googleapiclient.discovery import build
from google.oauth2.credentials import Credentials

# --- Import các module phân tích ---
from api.chatgpt import analyze_with_chatgpt_http
from api.gemini import analyze_with_anna_ai_http
from api.pre_filter import is_trivial_message
from api.utils import get_dynamic_config # << IMPORT MỚI
from extensions import limiter

# --- Blueprint ---
analyze_endpoint = Blueprint('analyze_endpoint', __name__)

# --- Cấu hình (chỉ các secret và cấu hình tĩnh) ---
GMAIL_TOKEN_PATH = os.environ.get('GMAIL_TOKEN_PATH', 'secrets/token.json')
GOOGLE_SHEET_ID = os.environ.get('GOOGLE_SHEET_ID')

# VirusTotal API Keys (hỗ trợ xoay vòng)
VIRUSTOTAL_API_KEYS_STR = os.environ.get('VIRUSTOTAL_API_KEYS')
if not VIRUSTOTAL_API_KEYS_STR:
    VIRUSTOTAL_API_KEYS = []
else:
    VIRUSTOTAL_API_KEYS = [key.strip() for key in VIRUSTOTAL_API_KEYS_STR.split(',') if key.strip()]

# Cấu hình bật/tắt gửi email cảnh báo (Bây giờ đọc từ config.json)
# ENABLE_EMAIL_ALERTS = os.environ.get('ENABLE_EMAIL_ALERTS', 'True').lower() == 'true' # <-- DÒNG NÀY SẼ BỊ XÓA

# --- CÁC HÀM TIỆN ÍCH (GMAIL, SHEETS) ---
def get_google_credentials(scopes):
    if not os.path.exists(GMAIL_TOKEN_PATH):
        print(f"🔴 [Google API] Lỗi: Không tìm thấy tệp token tại '{GMAIL_TOKEN_PATH}'")
        return None
    try:
        return Credentials.from_authorized_user_file(GMAIL_TOKEN_PATH, scopes)
    except Exception as e:
        print(f"🔴 [Google API] Lỗi khi tải credentials: {e}")
        return None

async def send_email_gmail_api(to_email, subject, body):
    config = get_dynamic_config() # <-- Đọc cấu hình động
    enable_email_alerts = config.get('enable_email_alerts', True) # Mặc định là True
    
    if not enable_email_alerts:
        print("🟡 [Email] Gửi email cảnh báo bị tắt bởi cấu hình.")
        return
    creds = get_google_credentials(['https://www.googleapis.com/auth/gmail.send'])
    if not creds: return
    try:
        service = build('gmail', 'v1', credentials=creds)
        message = MIMEText(body, 'html')
        message['to'] = to_email
        message['subject'] = subject
        raw_message = base64.urlsafe_b64encode(message.as_bytes()).decode()
        await asyncio.to_thread(service.users().messages().send(userId='me', body={'raw': raw_message}).execute)
        print("✅ [Email] Gửi email cảnh báo thành công.")
    except Exception as e:
        print(f"🔴 [Email] Gửi email cảnh báo thất bại: {e}")

async def save_to_history_sheet_async(text: str, result: dict):
    if not GOOGLE_SHEET_ID: return
    creds = get_google_credentials(['https://www.googleapis.com/auth/spreadsheets'])
    if not creds: return
    try:
        service = build('sheets', 'v4', credentials=creds)
        vn_timezone = timezone(timedelta(hours=7))
        timestamp = datetime.now(vn_timezone).strftime('%Y-%m-%d %H:%M:%S')
        row_data = [
            timestamp, text, result.get('is_dangerous', False),
            result.get('types', 'N/A'), result.get('reason', 'N/A'),
            result.get('score', 0), result.get('recommend', 'N/A')
        ]
        body = {'values': [row_data]}
        await asyncio.to_thread(
            service.spreadsheets().values().append(
                spreadsheetId=GOOGLE_SHEET_ID, range='History!A2',
                valueInputOption='USER_ENTERED', insertDataOption='INSERT_ROWS', body=body
            ).execute
        )
        print("✅ [Sheet] Đã lưu thành công.")
    except Exception as e:
        print(f"🔴 [Sheet] Lỗi khi đang lưu: {e}")

# --- CÁC HÀM PHÂN TÍCH PHỤ (URL, PRE-FILTER) ---
def extract_urls_from_text(text: str) -> list:
    url_pattern = re.compile(
        r'\b((?:https?://|www\.|ftp://)[-A-Z0-9+&@#/%?=~_|$!:,.;]*[A-Z0-9+&@#/%=~_|$])|'
        r'([a-zA-Z0-9](?:[a-zA-Z0-9-]{0,61}[a-zA-Z0-9])?\.[a-zA-Z]{2,6})', re.IGNORECASE
    )
    urls = [match[0] or match[1] for match in url_pattern.findall(text)]
    valid_urls = []
    for url in urls:
        if not url.startswith(('http://', 'https://', 'ftp://')):
            valid_urls.append(f"http://{url}")
        else:
            valid_urls.append(url)
    return sorted(list(set(valid_urls)))

async def check_urls_with_virustotal(urls: list) -> list:
    if not VIRUSTOTAL_API_KEYS:
        print("🟡 [VirusTotal] Cảnh báo: VIRUSTOTAL_API_KEYS chưa được thiết lập.")
        return []
    malicious_urls = []
    async with aiohttp.ClientSession() as session:
        for url in urls:
            try:
                headers = {"x-apikey": random.choice(VIRUSTOTAL_API_KEYS)}
                vt_url_id = base64.urlsafe_b64encode(url.encode()).decode().strip("=")
                analysis_url = f"https://www.virustotal.com/api/v3/urls/{vt_url_id}"
                print(f"➡️  [VirusTotal] Đang kiểm tra URL: {url}")
                async with session.get(analysis_url, headers=headers, timeout=15) as resp:
                    if resp.status == 200:
                        report = await resp.json()
                        stats = report.get('data', {}).get('attributes', {}).get('last_analysis_stats', {})
                        if stats.get('malicious', 0) > 0 or stats.get('suspicious', 0) > 0:
                            malicious_urls.append(url)
                            print(f"⚠️ [VirusTotal] Phát hiện URL nguy hiểm: {url}")
                    elif resp.status == 429:
                        print("🔴 [VirusTotal] Hết hạn mức API. Tạm dừng kiểm tra URL.")
                        break
            except Exception as e:
                print(f"🔴 [VirusTotal] Lỗi ngoại lệ khi kiểm tra URL {url}: {e}")
    return malicious_urls

# --- HÀM ĐIỀU PHỐI PHÂN TÍCH CHÍNH ---
async def perform_full_analysis(text: str, urls_from_request: list):
    print(f"📜 [Bắt đầu] Phân tích tin nhắn: '{text[:400]}'")

    # --- TẦNG 0: BỘ LỌC NHANH (PRE-FILTER) ---
    if await is_trivial_message(text):
        print("✅ [Pre-filter] Tin nhắn đơn giản, bỏ qua phân tích sâu.")
        return {'is_dangerous': False, 'reason': 'Tin nhắn được xác định là vô hại bởi bộ lọc nhanh.', 'score': 0, 'types': 'Trivial'}

    config = get_dynamic_config()
    provider = config.get('analysis_provider', 'AUTO').upper()

    # --- TẦNG 1: CÔNG TẮC KHẨN CẤP (OFF SWITCH) ---
    if provider == 'OFF':
        print("⛔ [Hệ thống] Chế độ: OFF. Từ chối yêu cầu phân tích.")
        return {"error": "SERVICE_DISABLED", "message": "Dịch vụ phân tích hiện đang bị tắt.", "status_code": 503}

    # --- TẦNG 2: KIỂM TRA URL BẰNG VIRUSTOTAL ---
    all_potential_urls = sorted(list(set(urls_from_request + extract_urls_from_text(text))))
    if all_potential_urls:
        malicious_urls = await check_urls_with_virustotal(all_potential_urls)
        if malicious_urls:
            print(f"⚠️ [URL Check] Phát hiện URL nguy hiểm! Trả về kết quả ngay.")
            return {'is_dangerous': True, 'types': 'scam', 'score': 5, 'reason': f"Phát hiện URL không an toàn qua VirusTotal: {', '.join(malicious_urls)}", 'recommend': "Tuyệt đối không truy cập các liên kết này.", 'malicious_urls_found': malicious_urls}
        print("✅ [URL Check] Không tìm thấy URL nguy hiểm nào.")

    # --- TẦNG 3: PHÂN TÍCH SÂU BẰNG AI ---
    final_result = None
    ai_provider_map = {
        'GEMINI': ('GEMINI', analyze_with_anna_ai_http),
        'CHATGPT': ('CHATGPT', analyze_with_chatgpt_http)
    }
    primary_provider, primary_func = ai_provider_map.get(provider, ('GEMINI', analyze_with_anna_ai_http))
    secondary_provider, secondary_func = ai_provider_map.get('CHATGPT' if primary_provider == 'GEMINI' else 'GEMINI')

    print(f"🟡 [Luồng chính] Chế độ: {provider}. Ưu tiên gọi {primary_provider}...")
    final_result = await primary_func(text)
    
    if provider == 'AUTO' and (not final_result or 'error' in final_result):
        print(f"⚠️ [Chuyển đổi] {primary_provider} gặp lỗi. Tự động chuyển sang {secondary_provider}.")
        final_result = await secondary_func(text)

    print(f"📄 [Kết quả AI] Phân tích trả về: {json.dumps(final_result, ensure_ascii=False)}")
    if not final_result or 'error' in final_result:
        return final_result or {"error": "ANALYSIS_FAILED", "message": "All AI providers failed."}

    # --- GỬI CẢNH BÁO VÀ LƯU TRỮ ---
    if final_result.get("is_dangerous"):
        print("➡️ [Phản hồi] Phát hiện ca nguy hiểm mới. Lên lịch gửi email bằng Gmail API...")
        email_task = asyncio.create_task(send_email_gmail_api(
            "duongpham18210@gmail.com", 
            f"[CyberShield] Nguy hiểm: {final_result.get('types', 'N/A')}", 
            f"Tin nhắn:\n{text}\n\nPhân tích:\n{json.dumps(final_result, indent=2, ensure_ascii=False)}"
        ))
    
    gc.collect()
    print(f"🏁 [Kết thúc] Phân tích hoàn tất cho: '{text[:50]}...'")
    return final_result

# --- ENDPOINTS ---
@analyze_endpoint.route('/analyze', methods=['POST'])
@limiter.limit("15/minute;3/second")
async def analyze_text():
    try:
        data = request.get_json(silent=True)
        if not data or 'text' not in data: 
            return jsonify({'error': 'Yêu cầu không hợp lệ, thiếu "text"'}), 400
        
        text = data.get('text', '').strip()
        urls_from_request = data.get('urls', [])

        # --- VALIDATION: Kiểm tra độ dài của tin nhắn ---
        MAX_TEXT_LENGTH = 5000  # Đặt giới hạn 5000 ký tự
        if len(text) > MAX_TEXT_LENGTH:
            return jsonify({'error': f'Tin nhắn quá dài. Giới hạn là {MAX_TEXT_LENGTH} ký tự.'}), 413 # Payload Too Large

        if not text: 
            return jsonify({'error': 'Không có văn bản để phân tích'}), 400
        
        # Bỏ slicing text[:3000] vì đã validate ở trên
        result = await perform_full_analysis(text, urls_from_request)

        if 'error' in result:
            status_code = result.get('status_code', 500)
            return jsonify({'error': result.get('message', 'Lỗi không xác định')}), status_code
        
        response = jsonify({'result': result})
        asyncio.create_task(save_to_history_sheet_async(text, result))
        return response
    except Exception as e:
        print(f"🔴 [LỖI NGHIÊM TRỌNG] Lỗi server: {e}")
        gc.collect()
        return jsonify({'error': 'Lỗi nội bộ server'}), 500

@analyze_endpoint.route('/health', methods=['GET'])
async def health_check():
    config = get_dynamic_config()
    provider = config.get('analysis_provider', 'AUTO').upper()
    return jsonify({'status': 'Bình thường', 'architecture': 'Multi-layer', 'provider_mode': provider})