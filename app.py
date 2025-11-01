from dotenv import load_dotenv
load_dotenv()

from flask import Flask, request, jsonify, render_template
from flask_cors import CORS
import os
import logging
from werkzeug.exceptions import NotFound

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# Initialize Flask app
app = Flask(__name__)
CORS(app)

# =================================================================
# INITIALIZE GEMMA MODEL ON STARTUP (CRITICAL!)
# =================================================================
print("\n" + "="*60)
print("🚀 INITIALIZING CYBERSHIELD BACKEND WITH LOCAL GEMMA")
print("="*60 + "\n")

# Import analyze_endpoint AFTER loading env (để đọc được env vars)
from api.analyze import analyze_endpoint, initialize_on_startup, model_state

# Khởi tạo Gemma model ngay khi app start
logger.info("🔄 Starting Gemma model initialization...")
model_init_success = initialize_on_startup()

if model_init_success:
    logger.info("✅ Gemma model loaded successfully!")
else:
    logger.warning("⚠️ Gemma model failed to load. API will return 503 until initialized.")
    logger.warning("   You can manually initialize by calling POST /api/init")

# Import webhook blueprint (nếu có)
try:
    from webhook import webhook_blueprint
    app.register_blueprint(webhook_blueprint, url_prefix='/messenger')
    logger.info("✅ Webhook blueprint registered")
except ImportError:
    logger.warning("⚠️ Webhook module not found, skipping")

# Register analyze blueprint
app.register_blueprint(analyze_endpoint, url_prefix='/api')
logger.info("✅ Analyze endpoint registered at /api/*")

# =================================================================
# ROUTES
# =================================================================

@app.route('/')
def home():
    """Landing page"""
    try:
        return render_template('index.html')
    except:
        # Fallback nếu không có template
        return jsonify({
            'service': 'CyberShield Backend v3.0',
            'status': 'online',
            'architecture': 'Local Gemma-3-270M',
            'endpoints': {
                'health': 'GET /',
                'analyze': 'POST /api/analyze',
                'model_health': 'GET /api/health',
                'init_model': 'POST /api/init',
                'test_model': 'POST /api/test-model',
                'stats': 'GET /api/stats',
                'cache_clear': 'POST /api/cache/clear',
                'cache_status': 'GET /api/cache/status'
            }
        })

@app.route('/health')
def health_check():
    """Quick health check endpoint"""
    
    return jsonify({
        'status': '🟢 Systems Nominal' if model_state.is_loaded() else '🟡 Model Not Loaded',
        'hp': '100/100' if model_state.is_loaded() else '50/100',
        'mana': '∞',
        'latency_ms': 5,
        'service': 'cybershield-backend-v3-local-gemma',
        'model_status': 'loaded' if model_state.is_loaded() else 'not_loaded',
        'note': 'Tế đàn còn ổn' if model_state.is_loaded() else 'Đang nạp đạn...'
    })

@app.route('/ping')
def ping():
    """Simple ping endpoint for uptime monitoring"""
    return jsonify({'pong': True, 'timestamp': os.environ.get('RENDER_GIT_COMMIT', 'local')})

@app.route('/debug/model-state')
def debug_model_state():
    """Debug endpoint để kiểm tra trạng thái model"""
    import sys
    
    debug_info = {
        'model_state_id': id(model_state),
        'is_loaded': model_state.is_loaded(),
        'model_is_none': model_state.model is None,
        'tokenizer_is_none': model_state.tokenizer is None,
        'loaded_flag': model_state.loaded,
        'python_version': sys.version,
        'imports': {
            'analyze_module': 'api.analyze' in sys.modules,
            'torch_available': 'torch' in sys.modules
        }
    }
    
    if model_state.model is not None:
        try:
            debug_info['model_device'] = str(next(model_state.model.parameters()).device)
            debug_info['model_dtype'] = str(next(model_state.model.parameters()).dtype)
        except:
            debug_info['model_device'] = 'error_getting_device'
    
    return jsonify(debug_info)

# =================================================================
# ERROR HANDLERS
# =================================================================

@app.errorhandler(404)
def not_found(error):
    return jsonify({
        'error': '❌ 404: Endpoint Not Found',
        'message': 'The requested endpoint does not exist',
        'available_endpoints': [
            'GET /',
            'GET /health',
            'GET /ping',
            'POST /api/analyze',
            'GET /api/health',
            'POST /api/init'
        ]
    }), 404

@app.errorhandler(500)
def internal_error(error):
    logger.error(f"Internal error: {str(error)}")
    return jsonify({
        'error': '💥 500: Internal Server Error',
        'message': 'Quay về phòng thủ. Tế đàn bị tấn công',
        'details': str(error) if app.debug else 'Enable debug mode for details'
    }), 500

@app.errorhandler(503)
def service_unavailable(error):
    return jsonify({
        'error': '⚠️ 503: Service Temporarily Unavailable',
        'message': 'Model is not loaded yet. Please wait or call POST /api/init',
        'retry_after': 10
    }), 503

# =================================================================
# GRACEFUL SHUTDOWN
# =================================================================

import signal
import sys

def graceful_shutdown(signum, frame):
    """Handle graceful shutdown"""
    logger.info("🛑 Received shutdown signal. Cleaning up...")
    
    # Clear GPU cache if available
    try:
        import torch
        if torch.cuda.is_available():
            torch.cuda.empty_cache()
            logger.info("✅ GPU cache cleared")
    except:
        pass
    
    logger.info("✅ Shutdown complete. Goodbye!")
    sys.exit(0)

# Register signal handlers
signal.signal(signal.SIGTERM, graceful_shutdown)
signal.signal(signal.SIGINT, graceful_shutdown)

# =================================================================
# MAIN ENTRY POINT
# =================================================================

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 10000))
    debug_mode = os.environ.get('FLASK_DEBUG', 'False').lower() == 'true'
    
    print("\n" + "="*60)
    print(f"🌐 Starting Flask server on 0.0.0.0:{port}")
    print(f"🐛 Debug mode: {debug_mode}")
    print(f"🤖 Model status: {'Loaded ✅' if model_init_success else 'Not loaded ⚠️'}")
    print("="*60 + "\n")
    
    # Log all registered routes
    logger.info("📋 Registered routes:")
    for rule in app.url_map.iter_rules():
        methods = ','.join(sorted(rule.methods - {'HEAD', 'OPTIONS'}))
        logger.info(f"   {methods:10s} {rule.rule}")
    
    print("\n🚀 Server is ready to accept connections!\n")
    
    app.run(
        host='0.0.0.0',
        port=port,
        debug=debug_mode,
        threaded=True  # Important for handling concurrent requests
    )