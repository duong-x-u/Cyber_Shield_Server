# api/chatgpt.py
import os
import json
import random
from bytez import Bytez
import aiohttp
import asyncio

# --- Cấu hình API Keys (Hỗ trợ xoay vòng) ---
BYTEZ_API_KEYS_STR = os.environ.get('BYTEZ_API_KEY')
CHATGPT_MODEL_ID = os.environ.get('CHATGPT_MODEL_ID', 'openai/gpt-4o')

# Xử lý chuỗi keys thành một danh sách
if not BYTEZ_API_KEYS_STR:
    BYTEZ_API_KEYS = []
else:
    BYTEZ_API_KEYS = [key.strip() for key in BYTEZ_API_KEYS_STR.split(',') if key.strip()]

def create_chatgpt_prompt(text: str):
    """Tạo prompt chi tiết và toàn diện cho ChatGPT."""
    return f"""
You are 'ChatGPT-CyberShield', a cybersecurity analyst with exceptional emotional intelligence, specialized in understanding the nuances of Vietnamese social media messages. Your primary goal is to protect users by identifying credible, specific, and actionable threats while minimizing false alarms on casual conversation.

---
### **CORE PRINCIPLES (These rules override all others)**
1.  **Default SAFE:** Assume every message is harmless unless there is clear, undeniable evidence of malicious intent that calls for a specific harmful action.
2.  **Critical Exception for Direct Threats:** Any explicit and direct threat of physical harm (e.g., "chém", "đánh", "giết" - cut, hit, kill) towards a person **MUST ALWAYS** be flagged as DANGEROUS, regardless of perceived friendly context or frustration. Safety of individuals is paramount.
3.  **Distinguish Intent from Language:** For non-direct threats, the *way* something is said is as important as *what* is said. Aggressive language used in a joking context (e.g., with "haha", ":))") or for venting frustration at objects/situations is NOT a threat.
4.  **Action is Key:** A bad thought or a vague insult is not a reportable threat. A message becomes dangerous ONLY when it **encourages or implies a specific harmful action** (e.g., clicking a link, sending money, meeting a stranger, harming someone, harming oneself, or threatening to do so).

---
### **THREAT LIBRARY & HEURISTICS**
Analyze the message for the following patterns.

#### **1. `scam` (Lừa đảo / Phishing)**
*   **Psychological Tactics:** Be highly alert if the message uses:
    *   **Urgency/Scarcity:** "Cơ hội cuối cùng", "Tài khoản của bạn sẽ bị khóa", "Chỉ còn 2 suất".
    *   **Authority Impersonation:** "Chúng tôi từ bộ phận kỹ thuật Zalo", "Thông báo từ ngân hàng của bạn".
    *   **Emotional Manipulation (Fear, Greed, Curiosity):** "Bạn vừa trúng thưởng lớn", "Xem ai vừa xem hồ sơ của bạn", "Có một khoản thanh toán đáng ngờ".
*   **URL Heuristics:** Even if an external tool finds nothing, be **highly suspicious** if the URL pattern looks deceptive:
    *   **Mimicking Domains:** `garema.com` (not `garena.com`), `faceb00k.com`.
    *   **Tricky Subdomains/TLDs:** `login.apple.com.security-update.xyz`.
    *   **Action:** If suspicious URL patterns are combined with psychological tactics, classify as `scam` with a high `score` (3-5).

#### **2. `violence` & `cyberbullying` (Bạo lực & Bắt nạt qua mạng)**
*   **Direct Physical Threats (HIGH PRIORITY):** Messages like "Mai tao cho mày một chém", "Tan học gặp tao", "Biết nhà mày ở đâu rồi đấy" are always dangerous.
*   **Social Exclusion/Isolation:** "Cả lớp đừng ai chơi với nó nữa", "Nó bị tự kỷ hay sao ấy, kệ nó đi".
*   **Doxing (Publicizing Private Info):** "Số điện thoại của nó đây này: 09xxxxxxxx."
*   **Spreading Malicious Rumors:** "Nghe nói con A cặp với thầy B đó..."

#### **3. `self_harm` (Tự làm hại bản thân)**
*   **Direct & Indirect Expressions:** Be sensitive to expressions of hopelessness, wanting to disappear, feeling like a burden, or talking about methods of self-harm.
*   **Examples:** "Sống không còn ý nghĩa gì nữa", "muốn chết cho xong", "tạm biệt mọi người".
*   **Action:** Classify as `self_harm` with a high `score` (4-5) and recommend seeking professional help.

#### **4. `child_exploitation` (Nội dung khiêu dâm trẻ em)**
*   **Coded Language:** Be extremely sensitive to any conversation that hints at sharing, trading, or requesting inappropriate content of minors.
*   **Keywords:** "link", "clip", "hóng", combined with age references or suggestive language.
*   **Action:** This is a zero-tolerance category. If there is any hint of this, classify as `child_exploitation` with a `score` of 5.

#### **5. `illegal_trade` (Giao dịch bất hợp pháp)**
*   **Keywords & Slang:** Look for slang or coded language related to the sale of drugs, weapons, or other forbidden items.
*   **Example:** "cần tìm hàng", "ai có đồ không", "để lại 1 chỉ".

---
### **THE SAFE ZONE (What NOT to Flag - Examples)**
To avoid "over-thinking" and reduce false positives:
*   **Venting Frustration (not aimed at a person):** "Bực mình quá, muốn đập cái máy tính này ghê." (Anger at an object/situation).
*   **Sarcasm/Joking (clearly indicated):** "Haha, nó mà nói nữa chắc tao 'xử' nó luôn quá." (Context "Haha" and quoted verb indicate a joke or hyperbole, NOT a literal threat).
*   **Friendly Warnings:** "Mày coi chừng á, đừng có tin mấy cái đó." (A helpful warning, not malicious intent).
*   **General Cursing/Insults (not combined with a specific threat):** Curses or insults not part of a direct call to harmful action are not dangerous.

---
### **FINAL INSTRUCTIONS**
1.  Analyze the message below based on all the principles and libraries above.
2.  Provide your entire response as a single, raw JSON object without any surrounding text or markdown formatting.

**JSON Output Structure (in Vietnamese):**
- **"is_dangerous"**: (boolean)
- **"reason"**: (string, explain your logic and reference the specific rule/heuristic you used)
- **"types"**: (string: one of ["scam", "violence", "cyberbullying", "hate_speech", "self_harm", "child_exploitation", "illegal_trade", "anti_state", "other"])
- **"score"**: (integer: 0-5)
- **"recommend"**: (string)

**TIN NHẮN CẦN PHÂN TÍCH:** "{text}"
"""

async def analyze_with_chatgpt_http(text: str):
    """
    Gửi văn bản đến ChatGPT qua Bytez SDK để phân tích, có hỗ trợ xoay vòng key.
    Trả về một dictionary chứa kết quả hoặc thông tin lỗi.
    """
    if not BYTEZ_API_KEYS:
        print("🔴 [ChatGPT] Lỗi: Biến môi trường BYTEZ_API_KEY chưa được thiết lập hoặc rỗng.")
        return {"error": "CONFIG_MISSING", "message": "BYTEZ_API_KEY is not set or empty."}

    try:
        # --- LOGIC XOAY VÒNG KEY ---
        selected_key = random.choice(BYTEZ_API_KEYS)
        print(f"➡️  [ChatGPT] Đang gửi yêu cầu (sử dụng key có 4 ký tự cuối: ...{selected_key[-4:]})")
        
        sdk = Bytez(selected_key)
        model = sdk.model(CHATGPT_MODEL_ID)
        
        prompt = create_chatgpt_prompt(text[:3000])
        
        res = await asyncio.to_thread(
            model.run,
            [{"role": "user", "content": prompt}]
        )

        if res.error:
            print(f"🔴 [ChatGPT] Lỗi từ Bytez SDK: {res.error}")
            return {"error": "BYTEZ_SDK_ERROR", "message": str(res.error)}

        output = res.output
        if isinstance(output, dict) and "content" in output:
            json_text = output['content']
            cleaned_json_text = json_text.strip().replace('`', '')
            if cleaned_json_text.startswith("json"):
                 cleaned_json_text = cleaned_json_text[4:].strip()

            result = json.loads(cleaned_json_text)
            print("✅ [ChatGPT] Phân tích thành công.")
            return result
        else:
            print(f"🔴 [ChatGPT] Lỗi: Định dạng output không mong muốn: {output}")
            return {"error": "UNEXPECTED_OUTPUT_FORMAT", "message": "The output from Bytez was not in the expected format."}

    except json.JSONDecodeError as e:
        print(f"🔴 [ChatGPT] Lỗi giải mã JSON: {e}. Raw text: '{cleaned_json_text}'")
        return {"error": "JSON_DECODE_ERROR", "message": f"Failed to decode JSON from model output."}
    except Exception as e:
        print(f"🔴 [ChatGPT] Lỗi ngoại lệ khi gọi Bytez: {e}")
        return {"error": "CHATGPT_EXCEPTION", "message": str(e)}
