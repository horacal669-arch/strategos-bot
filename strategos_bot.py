# STRATEGOS.HC - BOT COMERCIAL V1.0
import time, requests, ccxt, pandas as pd, json, os, threading
from datetime import datetime
import database

# ==========================================
# CONFIGURACIÓN
# ==========================================
TG_TOKEN = os.getenv("TG_TOKEN", "")
TG_CHAT = os.getenv("TG_CHAT", "")

USER_ID = int(os.getenv("USER_ID", "1"))  # Se pasa desde Render por usuario

BASE_PATH = os.path.dirname(os.path.abspath(__file__))

PAIRS_ALL = [
    "BTC/USDT", "ETH/USDT", "BNB/USDT", "SOL/USDT", "XRP/USDT", "DOGE/USDT",
    "LTC/USDT", "AVAX/USDT", "LINK/USDT", "MATIC/USDT", "UNI/USDT"
]

COMISION_BINANCE = 0.0004
FILTRO_TP1_MIN = 7.0

# ==========================================
# VARIABLES GLOBALES
# ==========================================
ops = []
op_id = 0
stats = {'wins': 0, 'losses': 0, 'be': 0, 'total_pnl': 0.0}
bot_pausado = False
señales_pendientes = {}
last_update_id = 0
exchange = None

# Configuración del usuario
user_config = {}
user_data = {}

# ==========================================
# INICIALIZACIÓN
# ==========================================
def init_user():
    """Cargar datos del usuario desde DB"""
    global user_config, user_data, exchange
    
    user_data = database.obtener_usuario(USER_ID)
    if not user_data:
        print(f"❌ Usuario {USER_ID} no encontrado")
        return False
    
    user_config = database.obtener_bot_config(USER_ID)
    if not user_config:
        print(f"❌ Config no encontrada para usuario {USER_ID}")
        return False
    
    # Verificar plan activo
    if not database.verificar_plan_activo(USER_ID):
        print(f"⚠️ Plan expirado para usuario {USER_ID}")
        tg(f"⚠️ <b>PLAN EXPIRADO</b>\n\nRenueva tu suscripción en:\nhttps://strategos.hc/pricing")
        return False
    
    # Inicializar Binance
    if user_data['api_key'] and user_data['api_secret']:
        try:
            exchange = ccxt.binance({
                'apiKey': user_data['api_key'],
                'secret': user_data['api_secret'],
                'enableRateLimit': True,
                'options': {'defaultType': 'future'}
            })
            # Test
            exchange.fetch_balance()
            print(f"✅ Binance conectado para user {USER_ID}")
        except Exception as e:
            print(f"❌ Error Binance: {e}")
            return False
    else:
        print(f"⚠️ Sin API keys configuradas para user {USER_ID}")
        return False
    
    print(f"✅ Usuario cargado: {user_data['email']}")
    print(f"   Plan: {user_data['plan'].upper()}")
    print(f"   Max ops: {user_config['max_ops']}")
    print(f"   Modo: {'REAL' if user_config['modo_real'] else 'DEMO'}")
    
    return True

# ==========================================
# TELEGRAM
# ==========================================
def tg(txt, keyboard=None):
    try:
        data = {"chat_id": TG_CHAT, "text": txt, "parse_mode": "HTML"}
        if keyboard:
            data["reply_markup"] = json.dumps(keyboard)
        
        res = requests.post(
            f"https://api.telegram.org/bot{TG_TOKEN}/sendMessage",
            json=data,
            timeout=10
        )
        
        if res.status_code == 200:
            print(f"📡 TG: {txt[:40]}...")
            return True
    except Exception as e:
        print(f"❌ TG Error: {e}")
    return False

def crear_menu_principal():
    return {
        "inline_keyboard": [
            [{"text": "📊 Stats", "callback_data": "menu_stats"}],
            [{"text": "📈 Activas", "callback_data": "menu_activas"}],
            [{"text": "💰 Saldo", "callback_data": "menu_saldo"}],
            [{"text": "⏸️ Pausar", "callback_data": "menu_pausar"}]
        ]
    }

def crear_teclado_capital():
    return {
        "inline_keyboard": [
            [{"text": "$50", "callback_data": "cap_50"}, {"text": "$80", "callback_data": "cap_80"}],
            [{"text": "$100", "callback_data": "cap_100"}, {"text": "$150", "callback_data": "cap_150"}]
        ]
    }

def crear_teclado_leverage():
    return {
        "inline_keyboard": [
            [{"text": "5x", "callback_data": "lev_5"}, {"text": "8x", "callback_data": "lev_8"}],
            [{"text": "10x", "callback_data": "lev_10"}, {"text": "15x", "callback_data": "lev_15"}]
        ]
    }

def crear_teclado_confirmar(op_id):
    return {
        "inline_keyboard": [
            [{"text": "✅ ABRIR", "callback_data": f"confirmar_{op_id}"}],
            [{"text": "❌ CANCELAR", "callback_data": f"cancelar_{op_id}"}]
        ]
    }

# ==========================================
# CONSULTAR SALDO BINANCE
# ==========================================
def obtener_saldo_futures():
    """Consultar saldo disponible en Binance Futures"""
    try:
        balance = exchange.fetch_balance({'type': 'future'})
        usdt_free = balance.get('USDT', {}).get('free', 0.0)
        usdt_used = balance.get('USDT', {}).get('used', 0.0)
        usdt_total = balance.get('USDT', {}).get('total', 0.0)
        
        return {
            'disponible': usdt_free,
            'en_uso': usdt_used,
            'total': usdt_total
        }
    except Exception as e:
        print(f"❌ Error consultando saldo: {e}")
        return {'disponible': 0, 'en_uso': 0, 'total': 0}

# ==========================================
# ANÁLISIS TÉCNICO (SIMPLIFICADO)
# ==========================================
def analizar(par):
    """Análisis técnico - Solo RSI para esta versión"""
    try:
        ohlcv = exchange.fetch_ohlcv(par, '15m', limit=200)
        df = pd.DataFrame(ohlcv, columns=['t','o','high','low','close','volume'])
        c = df['close']
        p = c.iloc[-1]
        
        # RSI
        d = c.diff()
        g = d.clip(lower=0)
        l = -d.clip(upper=0)
        rsi_val = 100-(100/(1+g.ewm(com=13,min_periods=14).mean()/l.ewm(com=13,min_periods=14).mean())).iloc[-1]
        
        # ATR
        hl = df['high']-df['low']
        hc = (df['high']-df['close'].shift()).abs()
        lc = (df['low']-df['close'].shift()).abs()
        atr_val = pd.concat([hl,hc,lc],axis=1).max(axis=1).ewm(span=14,adjust=False).mean().iloc[-1]
        
        print(f"  {par}: RSI={rsi_val:.1f}")
        
        # SEÑAL LONG
        if 25 < rsi_val < 35:
            return {
                'par': par,
                'side': 'LONG',
                'entry': p,
                'tp1': p + (atr_val * 2.0),
                'tp2': p + (atr_val * 3.5),
                'tp3': p + (atr_val * 5.0),
                'sl': p - (atr_val * 1.2),
                'tipo': 'RSI Sobreventa',
                'lev_sug': 8
            }
        
        # SEÑAL SHORT
        if 65 < rsi_val < 75:
            return {
                'par': par,
                'side': 'SHORT',
                'entry': p,
                'tp1': p - (atr_val * 2.0),
                'tp2': p - (atr_val * 3.5),
                'tp3': p - (atr_val * 5.0),
                'sl': p + (atr_val * 1.2),
                'tipo': 'RSI Sobrecompra',
                'lev_sug': 8
            }
        
        return None
    except Exception as e:
        print(f"❌ Error {par}: {e}")
        return None

# ==========================================
# PROCESAMIENTO SEÑALES
# ==========================================
def procesar_señal(s):
    """Procesar nueva señal - SIEMPRE pregunta en Telegram"""
    global op_id
    op_id += 1
    tag = f"#{op_id:03d}"
    
    # Validar TP1
    tp1_real = abs(s['tp1']-s['entry']) / s['entry'] * user_config['capital'] * user_config['leverage']
    
    if tp1_real < FILTRO_TP1_MIN:
        print(f"⚠️ {tag} descartada (TP1: ${tp1_real:.2f})")
        return
    
    # Verificar max ops
    activas = len([o for o in ops if o['activa']])
    if activas >= user_config['max_ops']:
        print(f"⏸️ Max ops ({activas}/{user_config['max_ops']})")
        return
    
    # Verificar saldo disponible
    saldo = obtener_saldo_futures()
    capital_necesario = user_config['capital'] * 1.5  # 50% margen
    
    if saldo['disponible'] < capital_necesario:
        tg(f"⚠️ <b>SALDO INSUFICIENTE</b>\n\nDisponible: ${saldo['disponible']:.2f}\nNecesario: ${capital_necesario:.2f}")
        return
    
    # PREGUNTAR EN TELEGRAM
    nueva_señal_telegram(s, tag)

def nueva_señal_telegram(s, tag):
    """Enviar señal a Telegram para confirmación"""
    tp1_real = abs(s['tp1']-s['entry']) / s['entry'] * user_config['capital'] * user_config['leverage']
    tp2_real = abs(s['tp2']-s['entry']) / s['entry'] * user_config['capital'] * user_config['leverage']
    tp3_real = abs(s['tp3']-s['entry']) / s['entry'] * user_config['capital'] * user_config['leverage']
    sl_real = abs(s['sl']-s['entry']) / s['entry'] * user_config['capital'] * user_config['leverage']
    
    saldo = obtener_saldo_futures()
    
    emoji = "📈" if s['side']=="LONG" else "📉"
    
    msg = (
        f"🚨 <b>SEÑAL {tag} {emoji}</b>\n\n"
        f"<b>{s['par']} {s['side']}</b>\n"
        f"{s['tipo']}\n\n"
        f"Entry: {s['entry']:.4f}\n"
        f"🎯 TP1: {s['tp1']:.4f} (~${tp1_real:.1f})\n"
        f"TP2: {s['tp2']:.4f} (~${tp2_real:.1f})\n"
        f"TP3: {s['tp3']:.4f} (~${tp3_real:.1f})\n"
        f"🛡️ SL: {s['sl']:.4f} (-${sl_real:.1f})\n\n"
        f"Lev sugerido: {s['lev_sug']}x\n"
        f"💰 Saldo disponible: ${saldo['disponible']:.2f}\n\n"
        f"<b>¿Capital a usar?</b>"
    )
    
    señales_pendientes[op_id] = {
        'señal': s,
        'tag': tag,
        'esperando': 'capital',
        'capital': None,
        'leverage': None
    }
    
    tg(msg, crear_teclado_capital())
    print(f"📢 {tag} {s['par']} → Telegram")

def abrir_operacion(s, tag, capital, leverage):
    """Abrir operación (DEMO o REAL)"""
    hora = datetime.now().strftime('%H:%M')
    
    tp1_real = abs(s['tp1']-s['entry']) / s['entry'] * capital * leverage
    tp2_real = abs(s['tp2']-s['entry']) / s['entry'] * capital * leverage
    tp3_real = abs(s['tp3']-s['entry']) / s['entry'] * capital * leverage
    
    # MODO REAL
    if user_config['modo_real']:
        try:
            exchange.set_leverage(leverage, s['par'])
            cantidad = capital * leverage / s['entry']
            binance_side = "buy" if s['side'] == "LONG" else "sell"
            order = exchange.create_market_order(s['par'], binance_side, cantidad)
            print(f"✅ Orden ejecutada: {order['id']}")
        except Exception as e:
            tg(f"❌ Error abriendo {tag}: {e}")
            return
    
    # Guardar operación
    ops.append({
        'tag': tag,
        'par': s['par'],
        'side': s['side'],
        'entry': s['entry'],
        'tp1': s['tp1'],
        'tp2': s['tp2'],
        'tp3': s['tp3'],
        'sl': s['sl'],
        'tps': [],
        'activa': True,
        'be': False,
        'tipo': s['tipo'],
        'capital': capital,
        'leverage': leverage,
        'timestamp': datetime.now().isoformat(),
        'tp1_usd': tp1_real,
        'tp2_usd': tp2_real,
        'tp3_usd': tp3_real,
        'pnl_final': 0,
        'user_id': USER_ID
    })
    
    modo_txt = "🔴 REAL" if user_config['modo_real'] else "🟢 DEMO"
    
    msg = (
        f"✅ <b>ABIERTA {tag}</b>\n\n"
        f"{s['par']} {s['side']}\n"
        f"{hora}hs\n\n"
        f"{s['tipo']}\n\n"
        f"💰 ${capital} | {leverage}x\n\n"
        f"🎯 TP1: ${tp1_real:.2f}\n"
        f"TP2: ${tp2_real:.2f}\n"
        f"TP3: ${tp3_real:.2f}\n\n"
        f"{modo_txt}"
    )
    
    tg(msg, crear_menu_principal())
    print(f"✅ {tag} ABIERTA")

# ==========================================
# MONITOREO
# ==========================================
def monitorear():
    """Monitorear operaciones activas"""
    for op in ops[:]:
        if not op['activa']:
            continue
        
        try:
            ticker = exchange.fetch_ticker(op['par'])
            p = ticker['last']
            
            # SL
            if (op['side']=="LONG" and p<=op['sl']) or (op['side']=="SHORT" and p>=op['sl']):
                if op['be']:
                    tg(f"🔒 BE {op['tag']} - $0.00")
                    stats['be'] += 1
                else:
                    perdida = abs(op['sl']-op['entry'])/op['entry']*op['capital']*op['leverage']
                    tg(f"❌ SL {op['tag']} -${perdida:.2f}")
                    stats['losses'] += 1
                    stats['total_pnl'] -= perdida
                
                op['activa'] = False
                continue
            
            # TPs
            for i, tp in enumerate([op['tp1'], op['tp2'], op['tp3']]):
                if i not in op['tps']:
                    if (op['side']=="LONG" and p>=tp) or (op['side']=="SHORT" and p<=tp):
                        usdt = [op['tp1_usd'], op['tp2_usd']-op['tp1_usd'], op['tp3_usd']-op['tp2_usd']][i]
                        
                        tg(f"✅ TP{i+1} {op['tag']} +${usdt:.2f}")
                        op['tps'].append(i)
                        
                        # BE Progresivo
                        if i == 0:
                            op['sl'] = op['entry']
                            op['be'] = True
                            tg(f"🔒 BE ACTIVADO {op['tag']}")
                        elif i == 1:
                            op['sl'] = op['tp1']
                            tg(f"🔒 BE → TP1 {op['tag']}")
            
            # WIN
            if len(op['tps']) == 3:
                total = op['tp3_usd']
                tg(f"🏆 WIN {op['tag']} +${total:.2f}")
                stats['wins'] += 1
                stats['total_pnl'] += total
                op['activa'] = False
        
        except Exception as e:
            print(f"❌ Error monitoreo {op['tag']}: {e}")

# ==========================================
# LISTENER TELEGRAM
# ==========================================
def tg_listener():
    global last_update_id, bot_pausado
    
    while True:
        try:
            res = requests.get(
                f"https://api.telegram.org/bot{TG_TOKEN}/getUpdates?offset={last_update_id+1}&timeout=10",
                timeout=15
            ).json()
            
            if not res.get("ok"):
                continue
            
            for u in res.get("result", []):
                last_update_id = u['update_id']
                
                if "callback_query" in u:
                    data = u["callback_query"]["data"]
                    
                    # Capital
                    if data.startswith("cap_"):
                        cap = int(data.replace("cap_", ""))
                        for oid, d in señales_pendientes.items():
                            if d['esperando'] == 'capital':
                                d['capital'] = cap
                                d['esperando'] = 'leverage'
                                tg(f"Capital: ${cap}\n\n¿Apalancamiento?", crear_teclado_leverage())
                                break
                    
                    # Leverage
                    elif data.startswith("lev_"):
                        lev = int(data.replace("lev_", ""))
                        for oid, d in señales_pendientes.items():
                            if d['esperando'] == 'leverage':
                                d['leverage'] = lev
                                d['esperando'] = 'confirmar'
                                s = d['señal']
                                
                                tp1 = abs(s['tp1']-s['entry'])/s['entry']*d['capital']*lev
                                tp3 = abs(s['tp3']-s['entry'])/s['entry']*d['capital']*lev
                                sl = abs(s['sl']-s['entry'])/s['entry']*d['capital']*lev
                                
                                msg = f"<b>CONFIRMAR {d['tag']}</b>\n\n{s['par']} {s['side']}\n${d['capital']} {lev}x\n\nMax: +${tp3:.2f}\nSL: -${sl:.2f}"
                                tg(msg, crear_teclado_confirmar(oid))
                                break
                    
                    # Confirmar
                    elif data.startswith("confirmar_"):
                        oid = int(data.replace("confirmar_", ""))
                        if oid in señales_pendientes:
                            d = señales_pendientes[oid]
                            abrir_operacion(d['señal'], d['tag'], d['capital'], d['leverage'])
                            del señales_pendientes[oid]
                    
                    # Cancelar
                    elif data.startswith("cancelar_"):
                        oid = int(data.replace("cancelar_", ""))
                        if oid in señales_pendientes:
                            tg(f"❌ {señales_pendientes[oid]['tag']} cancelada")
                            del señales_pendientes[oid]
                    
                    # Menú
                    elif data == "menu_stats":
                        total = stats['wins']+stats['losses']+stats['be']
                        wr = (stats['wins']/total*100) if total > 0 else 0
                        msg = f"📊 <b>STATS</b>\n\nOps: {total}\nWins: {stats['wins']}\nWR: {wr:.1f}%\nP&L: ${stats['total_pnl']:+.2f}"
                        tg(msg, crear_menu_principal())
                    
                    elif data == "menu_activas":
                        activas = [o for o in ops if o['activa']]
                        if activas:
                            msg = "📈 <b>ACTIVAS</b>\n\n"
                            for o in activas:
                                msg += f"{o['tag']} {o['par']} {o['side']}\n"
                            tg(msg, crear_menu_principal())
                        else:
                            tg("Sin ops activas", crear_menu_principal())
                    
                    elif data == "menu_saldo":
                        saldo = obtener_saldo_futures()
                        msg = f"💰 <b>BINANCE FUTURES</b>\n\nDisponible: ${saldo['disponible']:.2f}\nEn uso: ${saldo['en_uso']:.2f}\nTotal: ${saldo['total']:.2f}"
                        tg(msg, crear_menu_principal())
                    
                    elif data == "menu_pausar":
                        bot_pausado = not bot_pausado
                        tg(f"{'⏸️ PAUSADO' if bot_pausado else '▶️ ACTIVO'}", crear_menu_principal())
        
        except Exception as e:
            print(f"❌ Listener error: {e}")
            time.sleep(5)

# ==========================================
# MAIN LOOP
# ==========================================
def main_loop():
    print(f"🚀 Bot iniciado para user {USER_ID}")
    
    # Determinar pares permitidos
    if user_data['plan'] == 'free':
        pairs_permitidos = ["BTC/USDT"]
    else:
        pairs_permitidos = PAIRS_ALL
    
    tg(
        f"🤖 <b>STRATEGOS.HC</b>\n\n"
        f"Plan: {user_data['plan'].upper()}\n"
        f"Max ops: {user_config['max_ops']}\n"
        f"Pares: {len(pairs_permitidos)}\n\n"
        f"{'🔴 REAL' if user_config['modo_real'] else '🟢 DEMO'}",
        crear_menu_principal()
    )
    
    ciclo = 0
    
    while True:
        try:
            ciclo += 1
            print(f"\n{'='*50}")
            print(f"🕐 Ciclo #{ciclo} - {datetime.now().strftime('%H:%M:%S')}")
            print(f"{'='*50}")
            
            # Verificar plan activo
            if not database.verificar_plan_activo(USER_ID):
                print(f"⚠️ Plan expirado - Bot detenido")
                tg(f"⚠️ <b>PLAN EXPIRADO</b>\n\nRenueva en: https://strategos.hc/pricing")
                break
            
            # Monitorear
            activas = [o for o in ops if o['activa']]
            if activas:
                print(f"👁️ Monitoreando {len(activas)} ops...")
                monitorear()
            
            # Buscar señales
            if not bot_pausado:
                activas_count = len(activas)
                
                if activas_count < user_config['max_ops']:
                    print(f"🔍 Buscando señales ({activas_count}/{user_config['max_ops']})...")
                    
                    for par in pairs_permitidos:
                        if any(o['par']==par and o['activa'] for o in ops):
                            continue
                        
                        señal = analizar(par)
                        if señal:
                            procesar_señal(señal)
                            break
                else:
                    print(f"⏸️ Max ops ({activas_count}/{user_config['max_ops']})")
            
            print(f"💤 Esperando 5 min...")
            time.sleep(300)
        
        except Exception as e:
            print(f"❌ Error main: {e}")
            time.sleep(30)

# ==========================================
# INICIO
# ==========================================
if __name__ == '__main__':
    print("\n" + "="*60)
    print("  🤖 STRATEGOS.HC - BOT COMERCIAL")
    print("="*60 + "\n")
    
    # Cargar usuario
    if not init_user():
        print("❌ Inicialización fallida")
        exit(1)
    
    # Thread Telegram
    t_tg = threading.Thread(target=tg_listener, daemon=True)
    t_tg.start()
    
    # Loop principal
    try:
        main_loop()
    except KeyboardInterrupt:
        print("\n🛑 Bot detenido")
