import psycopg2
import hashlib
import os
from datetime import datetime, timedelta

# PostgreSQL connection
DATABASE_URL = os.getenv("DATABASE_URL", "postgresql://localhost/strategos")

def get_conn():
    return psycopg2.connect(DATABASE_URL)

def init_db():
    """Crear tablas si no existen"""
    conn = get_conn()
    c = conn.cursor()
    
    # Tabla usuarios
    c.execute('''CREATE TABLE IF NOT EXISTS users (
        id SERIAL PRIMARY KEY,
        email TEXT UNIQUE NOT NULL,
        password TEXT NOT NULL,
        plan TEXT DEFAULT 'free',
        plan_expiry TIMESTAMP,
        whatsapp TEXT,
        api_key TEXT,
        api_secret TEXT,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        last_login TIMESTAMP,
        is_active BOOLEAN DEFAULT TRUE
    )''')
    
    # Tabla pagos
    c.execute('''CREATE TABLE IF NOT EXISTS payments (
        id SERIAL PRIMARY KEY,
        user_id INTEGER REFERENCES users(id),
        plan TEXT NOT NULL,
        amount DECIMAL(10,2),
        payment_method TEXT,
        status TEXT DEFAULT 'pending',
        transaction_id TEXT,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    )''')
    
    # Tabla configuración bot por usuario
    c.execute('''CREATE TABLE IF NOT EXISTS bot_configs (
        user_id INTEGER PRIMARY KEY REFERENCES users(id),
        auto_mode BOOLEAN DEFAULT FALSE,
        modo_real BOOLEAN DEFAULT FALSE,
        capital INTEGER DEFAULT 100,
        leverage INTEGER DEFAULT 10,
        max_ops INTEGER DEFAULT 2,
        pares_permitidos TEXT DEFAULT '["BTC/USDT"]'
    )''')
    
    conn.commit()
    conn.close()
    print("✅ Base de datos inicializada")

def hash_password(password):
    return hashlib.sha256(password.encode()).hexdigest()

def crear_usuario(email, password, plan='free', whatsapp=None):
    """Crear nuevo usuario con plan"""
    try:
        conn = get_conn()
        c = conn.cursor()
        
        # Calcular fecha de expiración
        if plan == 'free':
            expiry = datetime.now() + timedelta(days=7)
        else:
            expiry = datetime.now() + timedelta(days=30)
        
        c.execute(
            'INSERT INTO users (email, password, plan, plan_expiry, whatsapp) VALUES (%s, %s, %s, %s, %s) RETURNING id',
            (email, hash_password(password), plan, expiry, whatsapp)
        )
        user_id = c.fetchone()[0]
        
        # Crear configuración por defecto
        max_ops_map = {'free': 2, 'basic': 3, 'premium': 5, 'vip': 999}
        pares = '["BTC/USDT"]' if plan == 'free' else '[]'
        
        c.execute(
            'INSERT INTO bot_configs (user_id, max_ops, pares_permitidos) VALUES (%s, %s, %s)',
            (user_id, max_ops_map.get(plan, 2), pares)
        )
        
        conn.commit()
        conn.close()
        return user_id
    except Exception as e:
        print(f"Error crear usuario: {e}")
        return None

def verificar_login(email, password):
    """Verificar credenciales y devolver user_id"""
    conn = get_conn()
    c = conn.cursor()
    c.execute(
        'SELECT id, plan, plan_expiry, is_active FROM users WHERE email=%s AND password=%s',
        (email, hash_password(password))
    )
    user = c.fetchone()
    
    if user:
        user_id, plan, expiry, is_active = user
        
        # Verificar si el plan expiró
        if expiry and datetime.now() > expiry:
            c.execute('UPDATE users SET is_active=FALSE WHERE id=%s', (user_id,))
            conn.commit()
            conn.close()
            return None  # Plan expirado
        
        if not is_active:
            conn.close()
            return None
        
        # Actualizar last_login
        c.execute('UPDATE users SET last_login=CURRENT_TIMESTAMP WHERE id=%s', (user_id,))
        conn.commit()
        conn.close()
        return user_id
    
    conn.close()
    return None

def obtener_usuario(user_id):
    """Obtener datos completos del usuario"""
    conn = get_conn()
    c = conn.cursor()
    c.execute('SELECT * FROM users WHERE id=%s', (user_id,))
    user = c.fetchone()
    conn.close()
    
    if user:
        return {
            'id': user[0],
            'email': user[1],
            'plan': user[3],
            'plan_expiry': user[4],
            'whatsapp': user[5],
            'api_key': user[6],
            'api_secret': user[7]
        }
    return None

def obtener_bot_config(user_id):
    """Obtener configuración del bot para usuario"""
    conn = get_conn()
    c = conn.cursor()
    c.execute('SELECT * FROM bot_configs WHERE user_id=%s', (user_id,))
    config = c.fetchone()
    conn.close()
    
    if config:
        return {
            'auto_mode': config[1],
            'modo_real': config[2],
            'capital': config[3],
            'leverage': config[4],
            'max_ops': config[5],
            'pares_permitidos': config[6]
        }
    return None

def guardar_api_keys(user_id, api_key, api_secret):
    """Guardar API keys de Binance"""
    conn = get_conn()
    c = conn.cursor()
    c.execute(
        'UPDATE users SET api_key=%s, api_secret=%s WHERE id=%s',
        (api_key, api_secret, user_id)
    )
    conn.commit()
    conn.close()

def renovar_plan(user_id, plan, payment_id=None):
    """Renovar plan de usuario"""
    conn = get_conn()
    c = conn.cursor()
    
    expiry = datetime.now() + timedelta(days=30)
    
    c.execute(
        'UPDATE users SET plan=%s, plan_expiry=%s, is_active=TRUE WHERE id=%s',
        (plan, expiry, user_id)
    )
    
    # Actualizar max_ops según plan
    max_ops_map = {'free': 2, 'basic': 3, 'premium': 5, 'vip': 999}
    c.execute(
        'UPDATE bot_configs SET max_ops=%s WHERE user_id=%s',
        (max_ops_map.get(plan, 2), user_id)
    )
    
    conn.commit()
    conn.close()

def registrar_pago(user_id, plan, amount, payment_method, transaction_id=None):
    """Registrar pago"""
    conn = get_conn()
    c = conn.cursor()
    c.execute(
        'INSERT INTO payments (user_id, plan, amount, payment_method, transaction_id) VALUES (%s, %s, %s, %s, %s) RETURNING id',
        (user_id, plan, amount, payment_method, transaction_id)
    )
    payment_id = c.fetchone()[0]
    conn.commit()
    conn.close()
    return payment_id

def verificar_plan_activo(user_id):
    """Verificar si el plan del usuario está activo"""
    conn = get_conn()
    c = conn.cursor()
    c.execute('SELECT plan, plan_expiry, is_active FROM users WHERE id=%s', (user_id,))
    user = c.fetchone()
    conn.close()
    
    if not user:
        return False
    
    plan, expiry, is_active = user
    
    if not is_active:
        return False
    
    if expiry and datetime.now() > expiry:
        return False
    
    return True

# Inicializar al importar
if __name__ == '__main__':
    init_db()
