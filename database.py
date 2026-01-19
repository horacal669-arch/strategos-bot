import sqlite3
import hashlib
import json
from datetime import datetime

DB_FILE = 'users.db'

def init_db():
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    c.execute('''CREATE TABLE IF NOT EXISTS users (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        email TEXT UNIQUE NOT NULL,
        password TEXT NOT NULL,
        api_key TEXT,
        api_secret TEXT,
        created_at TEXT
    )''')
    conn.commit()
    conn.close()

def hash_password(password):
    return hashlib.sha256(password.encode()).hexdigest()

def crear_usuario(email, password):
    try:
        conn = sqlite3.connect(DB_FILE)
        c = conn.cursor()
        c.execute('INSERT INTO users (email, password, created_at) VALUES (?, ?, ?)',
                  (email, hash_password(password), datetime.now().isoformat()))
        conn.commit()
        conn.close()
        return True
    except:
        return False

def verificar_login(email, password):
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    c.execute('SELECT id FROM users WHERE email=? AND password=?',
              (email, hash_password(password)))
    user = c.fetchone()
    conn.close()
    return user[0] if user else None

def guardar_api_keys(user_id, api_key, api_secret):
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    c.execute('UPDATE users SET api_key=?, api_secret=? WHERE id=?',
              (api_key, api_secret, user_id))
    conn.commit()
    conn.close()

def obtener_api_keys(user_id):
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    c.execute('SELECT api_key, api_secret FROM users WHERE id=?', (user_id,))
    keys = c.fetchone()
    conn.close()
    return keys if keys else (None, None)

init_db()