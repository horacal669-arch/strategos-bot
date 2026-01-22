from flask import Flask, jsonify, send_from_directory, request, session
from flask_cors import CORS
import json, os
from datetime import datetime, timedelta
import database
import jwt

app = Flask(__name__)
app.secret_key = os.getenv('SECRET_KEY', 'cambiar_en_produccion_12345')
CORS(app, supports_credentials=True, origins=['*'])

JWT_SECRET = os.getenv('JWT_SECRET', 'jwt_secret_cambiar_12345')

# ==========================================
# HELPER - JWT
# ==========================================
def generate_token(user_id):
    """Generar JWT token"""
    payload = {
        'user_id': user_id,
        'exp': datetime.utcnow() + timedelta(days=7)
    }
    return jwt.encode(payload, JWT_SECRET, algorithm='HS256')

def verify_token(token):
    """Verificar JWT token"""
    try:
        payload = jwt.decode(token, JWT_SECRET, algorithms=['HS256'])
        return payload['user_id']
    except:
        return None

def get_user_from_request():
    """Obtener user_id desde token o sesión"""
    # Intentar desde header Authorization
    auth_header = request.headers.get('Authorization')
    if auth_header and auth_header.startswith('Bearer '):
        token = auth_header.split(' ')[1]
        user_id = verify_token(token)
        if user_id:
            return user_id
    
    # Intentar desde sesión
    if 'user_id' in session:
        return session['user_id']
    
    return None

# ==========================================
# RUTAS HTML
# ==========================================
@app.route('/')
def index():
    return send_from_directory('.', 'landing_comercial.html')

@app.route('/pricing.html')
def pricing():
    return send_from_directory('.', 'pricing.html')

@app.route('/dashboard.html')
def dashboard():
    return send_from_directory('.', 'dashboard.html')

@app.route('/login.html')
def login_page():
    return send_from_directory('.', 'login.html')

@app.route('/onboarding.html')
def onboarding():
    return send_from_directory('.', 'onboarding.html')

@app.route('/terms.html')
def terms():
    return send_from_directory('.', 'terms.html')

@app.route('/privacy.html')
def privacy():
    return send_from_directory('.', 'privacy.html')

# ==========================================
# API - AUTENTICACIÓN
# ==========================================
@app.route('/api/register', methods=['POST'])
def register():
    data = request.json
    email = data.get('email')
    password = data.get('password')
    plan = data.get('plan', 'free')
    whatsapp = data.get('whatsapp')
    
    if not email or not password:
        return jsonify({'success': False, 'message': 'Faltan datos'}), 400
    
    user_id = database.crear_usuario(email, password, plan, whatsapp)
    
    if user_id:
        token = generate_token(user_id)
        session['user_id'] = user_id
        return jsonify({
            'success': True,
            'user_id': user_id,
            'token': token
        })
    else:
        return jsonify({'success': False, 'message': 'Email ya registrado'}), 400

@app.route('/api/login', methods=['POST'])
def login():
    data = request.json
    email = data.get('email')
    password = data.get('password')
    
    user_id = database.verificar_login(email, password)
    
    if user_id:
        # Verificar plan activo
        if not database.verificar_plan_activo(user_id):
            return jsonify({
                'success': False,
                'message': 'Plan expirado. Por favor renueva tu suscripción.'
            }), 403
        
        token = generate_token(user_id)
        session['user_id'] = user_id
        
        user_data = database.obtener_usuario(user_id)
        
        return jsonify({
            'success': True,
            'user_id': user_id,
            'token': token,
            'plan': user_data['plan'],
            'plan_expiry': user_data['plan_expiry'].isoformat() if user_data['plan_expiry'] else None
        })
    else:
        return jsonify({'success': False, 'message': 'Credenciales incorrectas'}), 401

@app.route('/api/logout', methods=['POST'])
def logout():
    session.pop('user_id', None)
    return jsonify({'success': True})

# ==========================================
# API - USUARIO
# ==========================================
@app.route('/api/user', methods=['GET'])
def get_user():
    user_id = get_user_from_request()
    if not user_id:
        return jsonify({'error': 'No autenticado'}), 401
    
    user_data = database.obtener_usuario(user_id)
    if not user_data:
        return jsonify({'error': 'Usuario no encontrado'}), 404
    
    return jsonify({
        'email': user_data['email'],
        'plan': user_data['plan'],
        'plan_expiry': user_data['plan_expiry'].isoformat() if user_data['plan_expiry'] else None,
        'whatsapp': user_data['whatsapp']
    })

@app.route('/api/save-keys', methods=['POST'])
def save_keys():
    user_id = get_user_from_request()
    if not user_id:
        return jsonify({'success': False, 'message': 'No autenticado'}), 401
    
    data = request.json
    api_key = data.get('api_key')
    api_secret = data.get('api_secret')
    
    database.guardar_api_keys(user_id, api_key, api_secret)
    return jsonify({'success': True})

# ==========================================
# API - STATS
# ==========================================
@app.route('/api/stats')
def stats():
    user_id = get_user_from_request()
    if not user_id:
        return jsonify({'error': 'No autenticado'}), 401
    
    # Aquí deberías cargar las stats desde un archivo por usuario
    # Por ahora retorno datos de ejemplo
    stats_file = f'stats_user_{user_id}.json'
    
    try:
        if os.path.exists(stats_file):
            with open(stats_file, 'r') as f:
                data = json.load(f)
                s = data.get('stats', {})
                total = s.get('wins', 0) + s.get('losses', 0) + s.get('be', 0)
                wr = (s['wins']/total*100) if total > 0 else 0
                return jsonify({
                    'total_ops': total,
                    'wins': s.get('wins', 0),
                    'losses': s.get('losses', 0),
                    'be': s.get('be', 0),
                    'win_rate': round(wr, 1),
                    'total_pnl': s.get('total_pnl', 0.0)
                })
    except:
        pass
    
    return jsonify({
        'total_ops': 0,
        'wins': 0,
        'losses': 0,
        'be': 0,
        'win_rate': 0,
        'total_pnl': 0.0
    })

@app.route('/api/operations')
def operations():
    user_id = get_user_from_request()
    if not user_id:
        return jsonify({'error': 'No autenticado'}), 401
    
    ops_file = f'operations_user_{user_id}.json'
    
    try:
        if os.path.exists(ops_file):
            with open(ops_file, 'r') as f:
                ops = json.load(f)
                return jsonify({'operations': ops})
    except:
        pass
    
    return jsonify({'operations': []})

# ==========================================
# API - CONFIG
# ==========================================
@app.route('/api/config')
def get_config():
    user_id = get_user_from_request()
    if not user_id:
        return jsonify({'error': 'No autenticado'}), 401
    
    config = database.obtener_bot_config(user_id)
    if config:
        return jsonify(config)
    
    return jsonify({'error': 'Config no encontrada'}), 404

# ==========================================
# API - PAGOS
# ==========================================
@app.route('/api/create-subscription', methods=['POST'])
def create_subscription():
    data = request.json
    plan = data.get('plan')
    email = data.get('email')
    whatsapp = data.get('whatsapp')
    payment_method = data.get('payment_method')
    
    # Crear usuario pendiente de pago
    # En producción aquí irían las integraciones de pago reales
    
    return jsonify({
        'success': True,
        'message': 'Suscripción creada. Completa el pago.'
    })

@app.route('/api/webhook/payment', methods=['POST'])
def payment_webhook():
    """Webhook para confirmar pagos (PayPal, Crypto, etc)"""
    # Aquí procesarías webhooks de PayPal, Coinbase, etc.
    data = request.json
    
    # Ejemplo: activar plan después de pago confirmado
    user_id = data.get('user_id')
    plan = data.get('plan')
    
    if user_id and plan:
        database.renovar_plan(user_id, plan)
        return jsonify({'success': True})
    
    return jsonify({'success': False}), 400

# ==========================================
# API - ADMIN (solo para ti)
# ==========================================
@app.route('/api/admin/users', methods=['GET'])
def admin_users():
    # Aquí deberías validar que sea admin
    # Por ahora retorna lista básica
    # En producción: agregar autenticación admin
    
    return jsonify({
        'message': 'Admin endpoint - implementar autenticación'
    })

# ==========================================
# HEALTH CHECK
# ==========================================
@app.route('/health')
def health():
    return jsonify({
        'status': 'ok',
        'timestamp': datetime.now().isoformat()
    })

# ==========================================
# INICIO
# ==========================================
if __name__ == '__main__':
    print("="*60)
    print("  🚀 STRATEGOS.HC API - COMERCIAL")
    print("  Puerto: 5000")
    print("="*60)
    
    # Inicializar DB
    database.init_db()
    
    app.run(debug=False, host='0.0.0.0', port=5000)
