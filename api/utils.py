# api/utils.py
import json

def get_dynamic_config():
    """Đọc file config.json để lấy cấu hình động."""
    try:
        with open('config.json', 'r', encoding='utf-8') as f:
            return json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        # Fallback nếu file không tồn tại hoặc bị lỗi
                    return {
                        "analysis_provider": "AUTO",
                        "enable_email_alerts": True,
                        "pre_filter_model_id": "openai/gpt-3.5-turbo",
                        "chatgpt_model_id": "openai/gpt-4o",
                        "gemini_model_id": "gemini-2.5-flash-lite"
                    }
