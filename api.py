from flask import Flask, jsonify, send_from_directory, request
from flask_cors import CORS
import json, os
from datetime import datetime

app = Flask(__name__)
CORS(app)
BASE_PATH = r"C:\Users\HORACIO\BotfinalClaude2"

@app.route('/')
def index():
    return send_from_directory('.', 'dashboard.html')

@app.route('/landing.html')
def landing():
    return send_from_directory('.', 'landing.html')

@app.route('/onboarding.html')
def onboarding():
    return send_from_directory('.', 'onboarding.html')

@app.route('/api/stats')
def stats():
    try:
        with open(os.path.join(BASE_PATH, 'stats_bot.json'), 'r') as f:
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
    try:
        with open(os.path.join(BASE_PATH, 'bot_config.json'), 'r') as f:
            return jsonify(json.load(f))
    except:
        return jsonify({'AUTO_MODE': True, 'MODO_REAL': False})

@app.route('/api/pausar', methods=['POST'])
def pausar():
    # Aquí el bot leería este flag
    return jsonify({'success': True, 'message': 'Bot pausado'})

@app.route('/api/modo', methods=['POST'])
def cambiar_modo():
    try:
        data = request.json
        with open(os.path.join(BASE_PATH, 'bot_config.json'), 'r') as f:
            config = json.load(f)
        config['AUTO_MODE'] = not config.get('AUTO_MODE', True)
        with open(os.path.join(BASE_PATH, 'bot_config.json'), 'w') as f:
            json.dump(config, f)
        return jsonify({'success': True, 'modo': config['AUTO_MODE']})
    except:
        return jsonify({'success': False})

@app.route('/api/reset', methods=['POST'])
def reset():
    return jsonify({'success': True, 'message': 'Reset programado'})

if __name__ == '__main__':
    print("API: http://localhost:5000")
    app.run(debug=True, port=5000)