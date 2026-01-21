from flask import Flask, jsonify, send_from_directory, request, session
from flask_cors import CORS
import json, os
from datetime import datetime
import database

app = Flask(__name__)
app.secret_key = 'tu_clave_secreta_super_segura_cambiar_en_produccion'
CORS(app, supports_credentials=True)

BASE_PATH = r"C:\Users\HORACIO\BotfinalClaude2"

@app.route('/')
def index():
    return send_from_directory('.', 'login.html')

@app.route('/dashboard.html')
def dashboard():
    return send_from_directory('.', 'dashboard.html')

@app.route('/landing.html')
def landing():
    return send_from_directory('.', 'landing.html')

@app.route('/onboarding.html')
def onboarding():
    return send_from_directory('.', 'onboarding.html')

@app.route('/api/register', methods=['POST'])
def register():
    data = request.json
    email = data.get('email')
    password = data.get('password')
    
    if not email or not password:
        return jsonify({'success': False, 'message': 'Faltan datos'})
    
    if database.crear_usuario(email, password):
        return jsonify({'success': True})
    else:
        return jsonify({'success': False, 'message': 'Email ya registrado'})

@app.route('/api/login', methods=['POST'])
def login():
    data = request.json
    email = data.get('email')
    password = data.get('password')
    
    user_id = database.verificar_login(email, password)
    
    if user_id:
        session['user_id'] = user_id
        return jsonify({'success': True, 'user_id': user_id})
    else:
        return jsonify({'success': False, 'message': 'Credenciales incorrectas'})

@app.route('/api/logout', methods=['POST'])
def logout():
    session.pop('user_id', None)
    return jsonify({'success': True})

@app.route('/api/save-keys', methods=['POST'])
def save_keys():
    if 'user_id' not in session:
        return jsonify({'success': False, 'message': 'No autenticado'}), 401
    
    data = request.json
    api_key = data.get('api_key')
    api_secret = data.get('api_secret')
    
    database.guardar_api_keys(session['user_id'], api_key, api_secret)
    return jsonify({'success': True})

@app.route('/api/stats')
def stats():
    
    user_id = 1
    stats_file = os.path.join(BASE_PATH, f'stats_user_{user_id}.json')
    
    try:
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
        return jsonify({'total_ops': 0, 'wins': 0, 'losses': 0, 'be': 0, 'win_rate': 0, 'total_pnl': 0.0})

@app.route('/api/config')
def get_config():
    if 'user_id' not in session:
        return jsonify({'error': 'No autenticado'}), 401
    
    user_id = session['user_id']
    config_file = os.path.join(BASE_PATH, f'bot_config_user_{user_id}.json')
    
    try:
        with open(config_file, 'r') as f:
            return jsonify(json.load(f))
    except:
        return jsonify({'AUTO_MODE': True, 'MODO_REAL': False})

@app.route('/api/pausar', methods=['POST'])
def pausar():
    if 'user_id' not in session:
        return jsonify({'success': False}), 401
    return jsonify({'success': True, 'message': 'Bot pausado'})

@app.route('/api/modo', methods=['POST'])
def cambiar_modo():
    if 'user_id' not in session:
        return jsonify({'success': False}), 401
    
    user_id = session['user_id']
    config_file = os.path.join(BASE_PATH, f'bot_config_user_{user_id}.json')
    
    try:
        with open(config_file, 'r') as f:
            config = json.load(f)
        config['AUTO_MODE'] = not config.get('AUTO_MODE', True)
        with open(config_file, 'w') as f:
            json.dump(config, f)
        return jsonify({'success': True, 'modo': config['AUTO_MODE']})
    except:
        return jsonify({'success': False})

@app.route('/api/reset', methods=['POST'])
def reset():
    if 'user_id' not in session:
        return jsonify({'success': False}), 401
    return jsonify({'success': True, 'message': 'Reset programado'})

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 10000))
    app.run(host="0.0.0.0", port=port)

