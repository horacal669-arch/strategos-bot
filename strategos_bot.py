# STRATEGOS.HC - BOT AUTOMÁTICO V24
# Modo Auto | Saldo Mínimo Inteligente | BE Dinámico | TPs Progresivos
import time, requests, ccxt, pandas as pd, json, os, threading
from datetime import datetime
from zoneinfo import ZoneInfo

# ==========================================
# CONFIGURACIÓN
# ==========================================
TG_TOKEN = "8203230724:AAHU9VOTSaakauqrvB3IrWl2GkAzrAsdqQ4"
TG_CHAT = "6618443331"

PAIRS = [
    "BTC/USDT", "ETH/USDT", "BNB/USDT", "SOL/USDT", "XRP/USDT", "DOGE/USDT",
    "LTC/USDT", "AVAX/USDT", "LINK/USDT", "MATIC/USDT", "UNI/USDT"
]

# MODO AUTOMÁTICO
AUTO_MODE = True  # True = Automático, False = Manual (confirma en Telegram)
AUTO_CAPITAL = 100
AUTO_LEVERAGE = 10
MAX_OPS_SIMULTANEAS = 5
MAX_DRAWDOWN_DIARIO = 500
FILTRO_TP1_MIN = 7.0

MODO_REAL = False
COMISION_BINANCE = 0.0004

import os
BINANCE_API_KEY = os.getenv('BINANCE_API_KEY', '')
BINANCE_API_SECRET = os.getenv('BINANCE_API_SECRET', '')

BASE_PATH = r"C:\Users\HORACIO\BotfinalClaude"
BOT_CONFIG_FILE = os.path.join(BASE_PATH, "bot_config.json")
STATS_FILE = os.path.join(BASE_PATH, "stats_bot.json")
OPS_FILE = os.path.join(BASE_PATH, "operaciones_bot.json")
BALANCE_FILE = os.path.join(BASE_PATH, "balance_completo.json")

# ==========================================
# BINANCE
# ==========================================
exchange = ccxt.binance({
    'apiKey': BINANCE_API_KEY,
    'secret': BINANCE_API_SECRET,
    'enableRateLimit': True,
    'options': {'defaultType': 'future'}
})

# ==========================================
# VARIABLES GLOBALES
# ==========================================
ops = []
op_id = 0
stats = {'wins': 0, 'losses': 0, 'be': 0, 'total_pnl': 0.0, 'drawdown_hoy': 0.0}
balance = {'hoy': {}, 'semana': {}, 'mes': {}, 'año': {}}
bot_pausado = False
ciclo_cerrado = False
señales_pendientes = {}
cierre_manual_activo = False
last_update_id = 0

# ==========================================
# TELEGRAM
# ==========================================
def tg(txt, keyboard=None):
    try:
        data = {"chat_id": TG_CHAT, "text": txt, "parse_mode": "HTML"}
        if keyboard:
            data["reply_markup"] = json.dumps(keyboard)
        
        if "ABIERTA" in txt or "WIN" in txt or "SL" in txt or "TP" in txt or "SEÑAL" in txt:
            print(f"📡 {txt[:35]}... ", end="")
            
        res = requests.post(f"https://api.telegram.org/bot{TG_TOKEN}/sendMessage", json=data, timeout=10)
        
        if "ABIERTA" in txt or "WIN" in txt or "SL" in txt or "TP" in txt or "SEÑAL" in txt:
            print("✅")
    except Exception as e:
        print(f"🚨 TG Error: {e}")

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
            [{"text": "5x", "callback_data": "lev_5"}, {"text": "8x", "callback_data": "lev_8"}, {"text": "10x", "callback_data": "lev_10"}]
        ]
    }

def crear_teclado_confirmar(op_id):
    return {
        "inline_keyboard": [
            [{"text": "✅ ABRIR", "callback_data": f"confirmar_{op_id}"}, {"text": "❌ CANCELAR", "callback_data": f"cancelar_{op_id}"}]
        ]
    }

def crear_teclado_cerrar_ops():
    activas = [o for o in ops if o['activa']]
    if not activas:
        return None
    
    botones = []
    for op in activas:
        try:
            ticker = exchange.fetch_ticker(op['par'])
            p = ticker['last']
            cap = op.get('capital', 0)
            lev = op.get('leverage', 0)
            
            if op['side']=='LONG':
                pnl = (p-op['entry'])/op['entry']*cap*lev
            else:
                pnl = (op['entry']-p)/op['entry']*cap*lev
            
            if pnl > 0:
                botones.append([{"text": f"{op['tag']} +${pnl:.2f}", "callback_data": f"cerrar_op_{op['tag']}"}])
        except:
            pass
    
    if not botones:
        return None
    
    botones.append([{"text": "❌ Cancelar", "callback_data": "cancelar_cierre"}])
    return {"inline_keyboard": botones}

def crear_menu_principal():
    modo_txt = "🤖 AUTO" if AUTO_MODE else "👤 MANUAL"
    
    if ciclo_cerrado:
        estado_text = "▶️ REANUDAR"
    elif bot_pausado:
        estado_text = "▶️ REANUDAR"
    else:
        estado_text = "⏸️ PAUSAR"
    
    return {
        "inline_keyboard": [
            [{"text": "📊 Stats", "callback_data": "menu_stats"}, {"text": "📈 Activas", "callback_data": "menu_activas"}],
            [{"text": "💰 Balance", "callback_data": "menu_balance"}, {"text": "💼 Saldo", "callback_data": "menu_saldo"}],
            [{"text": "💵 CERRAR OP", "callback_data": "menu_cerrar_op"}],
            [{"text": estado_text, "callback_data": "menu_pausar"}, {"text": modo_txt, "callback_data": "menu_auto"}],
            [{"text": "⏹️ CERRAR CICLO", "callback_data": "menu_ciclo"}],
            [{"text": "🔄 Modo", "callback_data": "menu_modo"}, {"text": "🗑️ RESET", "callback_data": "menu_reset"}]
        ]
    }

# ==========================================
# SALDO MÍNIMO INTELIGENTE
# ==========================================
def calcular_saldo_minimo():
    return (AUTO_CAPITAL * MAX_OPS_SIMULTANEAS) * 1.5

def verificar_saldo_suficiente():
    saldo_min = calcular_saldo_minimo()
    
    if MODO_REAL:
        _, _, total = obtener_saldo_real()
        return total >= saldo_min, total, saldo_min
    else:
        saldo_demo = 1000.0 + stats['total_pnl']
        return saldo_demo >= saldo_min, saldo_demo, saldo_min

# ==========================================
# PERSISTENCIA
# ==========================================
def cargar_modo():
    global MODO_REAL, AUTO_MODE, AUTO_CAPITAL, AUTO_LEVERAGE, MAX_OPS_SIMULTANEAS
    try:
        if os.path.exists(BOT_CONFIG_FILE):
            with open(BOT_CONFIG_FILE, 'r') as f:
                d = json.load(f)
                MODO_REAL = d.get('MODO_REAL', False)
                AUTO_MODE = d.get('AUTO_MODE', True)
                AUTO_CAPITAL = d.get('AUTO_CAPITAL', 100)
                AUTO_LEVERAGE = d.get('AUTO_LEVERAGE', 10)
                MAX_OPS_SIMULTANEAS = d.get('MAX_OPS_SIMULTANEAS', 5)
    except: pass

def guardar_modo():
    try:
        with open(BOT_CONFIG_FILE, 'w') as f:
            json.dump({
                'MODO_REAL': MODO_REAL,
                'AUTO_MODE': AUTO_MODE,
                'AUTO_CAPITAL': AUTO_CAPITAL,
                'AUTO_LEVERAGE': AUTO_LEVERAGE,
                'MAX_OPS_SIMULTANEAS': MAX_OPS_SIMULTANEAS
            }, f)
    except: pass

def cargar_datos():
    global op_id, stats, ops, balance
    cargar_modo()
    try:
        if os.path.exists(STATS_FILE):
            with open(STATS_FILE, 'r') as f:
                d = json.load(f)
                op_id = d.get('op_id', 0)
                stats = d.get('stats', stats)
        if os.path.exists(OPS_FILE):
            with open(OPS_FILE, 'r') as f:
                ops = json.load(f)
        if os.path.exists(BALANCE_FILE):
            with open(BALANCE_FILE, 'r') as f:
                balance = json.load(f)
    except: pass

def guardar_datos():
    try:
        with open(STATS_FILE, 'w') as f:
            json.dump({'op_id': op_id, 'stats': stats}, f)
        with open(OPS_FILE, 'w') as f:
            json.dump(ops, f)
        with open(BALANCE_FILE, 'w') as f:
            json.dump(balance, f)
    except: pass

def actualizar_balance(pnl, ganada):
    hoy = datetime.now()
    f_hoy = hoy.strftime('%Y-%m-%d')
    f_sem = hoy.strftime('%Y-W%V')
    f_mes = hoy.strftime('%Y-%m')
    f_año = hoy.strftime('%Y')
    
    for p, k in [('hoy', f_hoy), ('semana', f_sem), ('mes', f_mes), ('año', f_año)]:
        if k not in balance[p]: balance[p][k] = {'ops': 0, 'wins': 0, 'losses': 0, 'be': 0, 'pnl': 0.0}
        balance[p][k]['ops'] += 1
        balance[p][k]['pnl'] += pnl
        if ganada == 'win': balance[p][k]['wins'] += 1
        elif ganada == 'loss': balance[p][k]['losses'] += 1
        else: balance[p][k]['be'] += 1
    guardar_datos()

# ==========================================
# UTILIDADES
# ==========================================
def obtener_hora_arg():
    try:
        tz = ZoneInfo("America/Argentina/Buenos_Aires")
        return datetime.now(tz).strftime('%H:%M')
    except:
        return datetime.now().strftime('%H:%M')

def obtener_saldo_real():
    try:
        # FUTURES (ARREGLADO)
        fut_bal = exchange.fetch_balance(params={'type': 'future'})
        fut_usdt = fut_bal.get('USDT', {}).get('total', 0.0)
        
        # SPOT (ARREGLADO)
        spot_bal = exchange.fetch_balance()
        spot_usdt = spot_bal.get('USDT', {}).get('total', 0.0)
        
        otros_activos_usdt = 0.0
        for par in PAIRS:
            moneda = par.split('/')[0]
            if moneda == "USDT": continue
            
            total_moneda = spot_bal.get(moneda, {}).get('total', 0.0)
            if total_moneda > 0:
                try:
                    ticker = exchange.fetch_ticker(f"{moneda}/USDT")
                    otros_activos_usdt += total_moneda * ticker['last']
                except: pass
        
        total_spot = spot_usdt + otros_activos_usdt
        total_general = total_spot + fut_usdt
        
        return total_spot, fut_usdt, total_general
    except Exception as e:
        print(f"Error saldo: {e}")
        return 0.0, 0.0, 0.0

# ==========================================
# MENSAJES
# ==========================================
def enviar_stats():
    total = stats['wins'] + stats['losses'] + stats['be']
    wr = (stats['wins']/total*100) if total > 0 else 0
    activas = len([o for o in ops if o['activa']])
    
    modo_txt = "🤖 AUTOMÁTICO" if AUTO_MODE else "👤 MANUAL"
    
    if ciclo_cerrado:
        estado = "⏹️ CICLO CERRADO"
    elif bot_pausado:
        estado = "⏸️ PAUSADO"
    else:
        estado = "▶️ ACTIVO"
    
    msg = f"📊 <b>STRATEGOS.HC</b>\n\n<b>Stats:</b>\nOps: {total}\nWins: {stats['wins']}\nLosses: {stats['losses']}\nBE: {stats['be']}\nWR: {wr:.1f}%\nP&L: ${stats['total_pnl']:+.2f}\n\n<b>Estado:</b>\n{estado}\n{modo_txt}\n{'🔴 REAL' if MODO_REAL else '🟢 PAPER'}\n\nActivas: {activas}/{MAX_OPS_SIMULTANEAS}"
    tg(msg, crear_menu_principal())

def enviar_activas():
    activas = [o for o in ops if o['activa']]
    if not activas: 
        tg("Sin ops activas", crear_menu_principal())
        return
    
    msg = "📈 <b>OPERACIONES ACTIVAS</b>\n\n"
    for op in activas:
        try:
            ticker = exchange.fetch_ticker(op['par'])
            p = ticker['last']
            cap = op.get('capital', 0)
            lev = op.get('leverage', 0)
            
            if op['side']=='LONG':
                pnl = (p-op['entry'])/op['entry']*cap*lev
            else:
                pnl = (op['entry']-p)/op['entry']*cap*lev
            
            be_status = " 🔒BE" if op['be'] else ""
            tps_hit = f" TP{len(op['tps'])}" if op['tps'] else ""
            msg += f"{op['tag']} {op['par']} {op['side']}{tps_hit}{be_status}\nP&L: ${pnl:+.2f}\n\n"
        except:
            msg += f"{op['tag']} {op['par']} Error\n\n"
    
    tg(msg, crear_menu_principal())

def enviar_saldo_binance():
    if MODO_REAL:
        spot, fut, total = obtener_saldo_real()
        saldo_min = calcular_saldo_minimo()
        msg = f"💼 <b>SALDO BINANCE</b>\n\n🟢 Spot: ${spot:.2f}\n🔴 Futures: ${fut:.2f}\n\n<b>Total: ${total:.2f}</b>\n\nMínimo requerido: ${saldo_min:.2f}\n({AUTO_CAPITAL} × {MAX_OPS_SIMULTANEAS} × 1.5)"
    else:
        demo = 1000.0 + stats['total_pnl']
        saldo_min = calcular_saldo_minimo()
        msg = f"💰 <b>CUENTA DEMO</b>\n\nBase: $1000\nP&L: ${stats['total_pnl']:+.2f}\n\n<b>Saldo: ${demo:.2f}</b>\n\nMínimo: ${saldo_min:.2f}"
    
    tg(msg, crear_menu_principal())

def enviar_balance():
    hoy_str = datetime.now().strftime('%Y-%m-%d')
    hoy_dt = datetime.now().replace(hour=0, minute=0, second=0, microsecond=0)
    
    ops_hoy = [o for o in ops if not o['activa'] and datetime.fromisoformat(o['timestamp']) >= hoy_dt]
    
    msg = f"💰 <b>BALANCE STRATEGOS.HC</b>\n\n"
    
    b_hoy = balance['hoy'].get(hoy_str, {'pnl': 0.0})
    b_sem = balance['semana'].get(datetime.now().strftime('%Y-W%V'), {'pnl': 0.0})
    b_mes = balance['mes'].get(datetime.now().strftime('%Y-%m'), {'pnl': 0.0})
    b_año = balance['año'].get(datetime.now().strftime('%Y'), {'pnl': 0.0})
    
    msg += f"📅 HOY: ${b_hoy['pnl']:+.2f}\n"
    msg += f"📅 SEMANA: ${b_sem['pnl']:+.2f}\n"
    msg += f"📅 MES: ${b_mes['pnl']:+.2f}\n"
    msg += f"📅 AÑO: ${b_año['pnl']:+.2f}\n\n"
    
    if ops_hoy:
        msg += f"📝 <b>ÚLTIMAS 5</b>\n"
        for op in ops_hoy[-5:]:
            res = "🏆" if len(op['tps'])==3 else ("⚖️" if op['be'] else "❌")
            pnl = op.get('pnl_final', 0) if res=="🏆" else (0 if res=="⚖️" else -op['capital'])
            msg += f"{op['tag']} {op['par']} {res} ${pnl:+.2f}\n"
    
    tg(msg, crear_menu_principal())

# ==========================================
# INDICADORES
# ==========================================
def ema(s, p): return s.ewm(span=p, adjust=False).mean()
def sma(s, p): return s.rolling(p).mean()

def rsi(s, p=14): 
    d = s.diff()
    g = d.clip(lower=0)
    l = -d.clip(upper=0)
    return 100-(100/(1+g.ewm(com=p-1,min_periods=p).mean()/l.ewm(com=p-1,min_periods=p).mean()))

def atr(df, p=14): 
    hl = df['high']-df['low']
    hc = (df['high']-df['close'].shift()).abs()
    lc = (df['low']-df['close'].shift()).abs()
    return pd.concat([hl,hc,lc],axis=1).max(axis=1).ewm(span=p,adjust=False).mean()

def adx_completo(df, p=14):
    high = df['high']
    low = df['low']
    close = df['close']
    up = high - high.shift(1)
    down = low.shift(1) - low
    plus_dm = ((up > down) & (up > 0)) * up
    minus_dm = ((down > up) & (down > 0)) * down
    tr1 = high - low
    tr2 = (high - close.shift()).abs()
    tr3 = (low - close.shift()).abs()
    tr = pd.concat([tr1, tr2, tr3], axis=1).max(axis=1)
    atr_val = tr.rolling(p).mean()
    plus_di = 100 * (plus_dm.ewm(span=p, adjust=False).mean() / atr_val)
    minus_di = 100 * (minus_dm.ewm(span=p, adjust=False).mean() / atr_val)
    dx = ((plus_di - minus_di).abs() / (plus_di + minus_di).abs()) * 100
    adx_val = dx.ewm(span=p, adjust=False).mean()
    return adx_val, plus_di, minus_di

def macd(c, f=12, s=26, sig=9):
    ema_f = ema(c, f)
    ema_s = ema(c, s)
    macd_line = ema_f - ema_s
    signal = ema(macd_line, sig)
    return macd_line, signal

def bollinger(c, p=20, std=2):
    m = sma(c, p)
    s = c.rolling(p).std()
    return m + (std*s), m, m - (std*s)

def pivot_points(df):
    high = df['high'].tail(96).max()
    low = df['low'].tail(96).min()
    close = df['close'].iloc[-96]
    pivot = (high + low + close) / 3
    return pivot, pivot + (high - low), pivot - (high - low)

def detectar_mercado(df):
    c = df['close']
    bb_u, bb_m, bb_l = bollinger(c)
    bb_width = (bb_u.iloc[-1] - bb_l.iloc[-1]) / bb_m.iloc[-1]
    
    try:
        adx_val = adx_completo(df)[0].iloc[-1]
    except:
        adx_val = 20
    
    if bb_width < 0.03: return "📊 LATERAL"
    elif bb_width < 0.045 and adx_val > 25: return "⚡ EXPLOSIÓN"
    elif adx_val > 30: return "📈 TENDENCIA+"
    elif adx_val > 20: return "📈 TENDENCIA"
    else: return "📊 LATERAL"

# ==========================================
# ESTRATEGIAS
# ==========================================
def analizar(par):
    try:
        ohlcv = exchange.fetch_ohlcv(par, '15m', limit=200)
        df = pd.DataFrame(ohlcv, columns=['t','o','high','low','close','volume'])
        c = df['close']
        h = df['high']
        l = df['low']
        v = df['volume']
        p = c.iloc[-1]
        
        e9, e21, e50, e200 = ema(c,9).iloc[-1], ema(c,21).iloc[-1], ema(c,50).iloc[-1], ema(c,200).iloc[-1]
        e9p, e21p = ema(c,9).iloc[-2], ema(c,21).iloc[-2]
        
        rsi_val = rsi(c, 14).iloc[-1]
        atr_val = atr(df, 14).iloc[-1]
        
        adx_val = adx_completo(df)[0].iloc[-1]
        plus_di = adx_completo(df)[1].iloc[-1]
        minus_di = adx_completo(df)[2].iloc[-1]
        
        macd_line, signal = macd(c)
        macd_now, signal_now = macd_line.iloc[-1], signal.iloc[-1]
        macd_prev, signal_prev = macd_line.iloc[-2], signal.iloc[-2]
        
        bb_u, bb_m, bb_l = bollinger(c)
        bb_upper = bb_u.iloc[-1]
        bb_mid = bb_m.iloc[-1]
        bb_lower = bb_l.iloc[-1]
        bb_width = (bb_upper - bb_lower) / bb_mid
        
        pivot = pivot_points(df)[0]
        r1 = pivot_points(df)[1]
        s1 = pivot_points(df)[2]
        
        high_20 = h.tail(20).max()
        low_20 = l.tail(20).min()
        
        tipo_mercado = detectar_mercado(df)
        
        tp_mult = [2.0, 3.5, 5.0]
        sl_mult = 1.2
        
        # E1 RSI
        if 25 < rsi_val < 35 and c.iloc[-1] > c.iloc[-2]:
            return {'par':par,'side':'LONG','entry':p,'tp1':p+(atr_val*tp_mult[0]),'tp2':p+(atr_val*tp_mult[1]),'tp3':p+(atr_val*tp_mult[2]),'sl':p-(atr_val*sl_mult),'tipo':'RSI Sobreventa','mercado':tipo_mercado,'lev_sug':8}
        if 65 < rsi_val < 75 and c.iloc[-1] < c.iloc[-2]:
            return {'par':par,'side':'SHORT','entry':p,'tp1':p-(atr_val*tp_mult[0]),'tp2':p-(atr_val*tp_mult[1]),'tp3':p-(atr_val*tp_mult[2]),'sl':p+(atr_val*sl_mult),'tipo':'RSI Sobrecompra','mercado':tipo_mercado,'lev_sug':8}
        
        # E2 BB Squeeze
        if bb_width < 0.05:
            if p > bb_upper and v.iloc[-1] > v.mean() * 1.3:
                return {'par':par,'side':'LONG','entry':p,'tp1':p+(atr_val*tp_mult[0]),'tp2':p+(atr_val*tp_mult[1]),'tp3':p+(atr_val*tp_mult[2]),'sl':p-(atr_val*sl_mult),'tipo':'BB Squeeze+','mercado':tipo_mercado,'lev_sug':10}
            if p < bb_lower and v.iloc[-1] > v.mean() * 1.3:
                return {'par':par,'side':'SHORT','entry':p,'tp1':p-(atr_val*tp_mult[0]),'tp2':p-(atr_val*tp_mult[1]),'tp3':p-(atr_val*tp_mult[2]),'sl':p+(atr_val*sl_mult),'tipo':'BB Squeeze-','mercado':tipo_mercado,'lev_sug':10}
        
        # E3 Cruce EMA
        if e9p <= e21p and e9 > e21:
            return {'par':par,'side':'LONG','entry':p,'tp1':p+(atr_val*tp_mult[0]),'tp2':p+(atr_val*tp_mult[1]),'tp3':p+(atr_val*tp_mult[2]),'sl':p-(atr_val*sl_mult),'tipo':'Cruce EMA+','mercado':tipo_mercado,'lev_sug':5}
        if e9p >= e21p and e9 < e21:
            return {'par':par,'side':'SHORT','entry':p,'tp1':p-(atr_val*tp_mult[0]),'tp2':p-(atr_val*tp_mult[1]),'tp3':p-(atr_val*tp_mult[2]),'sl':p+(atr_val*sl_mult),'tipo':'Cruce EMA-','mercado':tipo_mercado,'lev_sug':5}
        
        # E4 MACD
        if macd_prev <= signal_prev and macd_now > signal_now and rsi_val < 65:
            return {'par':par,'side':'LONG','entry':p,'tp1':p+(atr_val*tp_mult[0]),'tp2':p+(atr_val*tp_mult[1]),'tp3':p+(atr_val*tp_mult[2]),'sl':p-(atr_val*sl_mult),'tipo':'MACD+','mercado':tipo_mercado,'lev_sug':5}
        if macd_prev >= signal_prev and macd_now < signal_now and rsi_val > 35:
            return {'par':par,'side':'SHORT','entry':p,'tp1':p-(atr_val*tp_mult[0]),'tp2':p-(atr_val*tp_mult[1]),'tp3':p-(atr_val*tp_mult[2]),'sl':p+(atr_val*sl_mult),'tipo':'MACD-','mercado':tipo_mercado,'lev_sug':5}
        
        # E5 ADX
        if adx_val > 15:
            if plus_di > minus_di and p > e200 and 30 < rsi_val < 65:
                return {'par':par,'side':'LONG','entry':p,'tp1':p+(atr_val*tp_mult[0]),'tp2':p+(atr_val*tp_mult[1]),'tp3':p+(atr_val*tp_mult[2]),'sl':p-(atr_val*sl_mult),'tipo':f'ADX+ {adx_val:.0f}','mercado':tipo_mercado,'lev_sug':8}
            if minus_di > plus_di and p < e200 and 35 < rsi_val < 70:
                return {'par':par,'side':'SHORT','entry':p,'tp1':p-(atr_val*tp_mult[0]),'tp2':p-(atr_val*tp_mult[1]),'tp3':p-(atr_val*tp_mult[2]),'sl':p+(atr_val*sl_mult),'tipo':f'ADX- {adx_val:.0f}','mercado':tipo_mercado,'lev_sug':8}
        
        # E6 EMA 200
        distancia_200 = abs(p - e200) / p
        if distancia_200 < 0.005 and v.iloc[-1] > v.mean() * 1.3:
            if p > e200:
                return {'par':par,'side':'LONG','entry':p,'tp1':p+(atr_val*tp_mult[0]),'tp2':p+(atr_val*tp_mult[1]),'tp3':p+(atr_val*tp_mult[2]),'sl':p-(atr_val*sl_mult),'tipo':'EMA200+','mercado':tipo_mercado,'lev_sug':8}
            if p < e200:
                return {'par':par,'side':'SHORT','entry':p,'tp1':p-(atr_val*tp_mult[0]),'tp2':p-(atr_val*tp_mult[1]),'tp3':p-(atr_val*tp_mult[2]),'sl':p+(atr_val*sl_mult),'tipo':'EMA200-','mercado':tipo_mercado,'lev_sug':8}
        
        # E7 Pivot
        if abs(p - s1) / p < 0.003 and v.iloc[-1] > v.mean() * 1.2:
            if c.iloc[-1] > c.iloc[-2]:
                return {'par':par,'side':'LONG','entry':p,'tp1':p+(atr_val*tp_mult[0]),'tp2':p+(atr_val*tp_mult[1]),'tp3':p+(atr_val*tp_mult[2]),'sl':p-(atr_val*sl_mult),'tipo':'Pivot S1','mercado':tipo_mercado,'lev_sug':5}
        if abs(p - r1) / p < 0.003 and v.iloc[-1] > v.mean() * 1.2:
            if c.iloc[-1] < c.iloc[-2]:
                return {'par':par,'side':'SHORT','entry':p,'tp1':p-(atr_val*tp_mult[0]),'tp2':p-(atr_val*tp_mult[1]),'tp3':p-(atr_val*tp_mult[2]),'sl':p+(atr_val*sl_mult),'tipo':'Pivot R1','mercado':tipo_mercado,'lev_sug':5}
        
        # E8 Volume Spike
        vr = v.iloc[-1] / v.mean()
        if vr > 2.0:
            if c.iloc[-1] > c.iloc[-2] > c.iloc[-3] and rsi_val < 70:
                return {'par':par,'side':'LONG','entry':p,'tp1':p+(atr_val*tp_mult[0]),'tp2':p+(atr_val*tp_mult[1]),'tp3':p+(atr_val*tp_mult[2]),'sl':p-(atr_val*sl_mult),'tipo':'Vol Spike+','mercado':tipo_mercado,'lev_sug':10}
            if c.iloc[-1] < c.iloc[-2] < c.iloc[-3] and rsi_val > 30:
                return {'par':par,'side':'SHORT','entry':p,'tp1':p-(atr_val*tp_mult[0]),'tp2':p-(atr_val*tp_mult[1]),'tp3':p-(atr_val*tp_mult[2]),'sl':p+(atr_val*sl_mult),'tipo':'Vol Spike-','mercado':tipo_mercado,'lev_sug':10}
        
        # E9 Breakout
        if p > high_20 * 1.001 and v.iloc[-1] > v.mean() * 1.2:
            return {'par':par,'side':'LONG','entry':p,'tp1':p+(atr_val*tp_mult[0]),'tp2':p+(atr_val*tp_mult[1]),'tp3':p+(atr_val*tp_mult[2]),'sl':high_20-(atr_val*0.8),'tipo':'Break R','mercado':tipo_mercado,'lev_sug':8}
        if p < low_20 * 0.999 and v.iloc[-1] > v.mean() * 1.2:
            return {'par':par,'side':'SHORT','entry':p,'tp1':p-(atr_val*tp_mult[0]),'tp2':p-(atr_val*tp_mult[1]),'tp3':p-(atr_val*tp_mult[2]),'sl':low_20+(atr_val*0.8),'tipo':'Break S','mercado':tipo_mercado,'lev_sug':8}
        
        return None
    except Exception as e:
        print(f"Error analizar {par}: {e}")
        return None

# ==========================================
# GESTIÓN - MODO AUTOMÁTICO
# ==========================================
def procesar_señal(s):
    global op_id
    op_id += 1
    tag = f"#{op_id:03d}"
    
    # Calcular TP1 en USDT
    tp1_usd = abs(s['tp1']-s['entry']) if 'BTC' in s['par'] else abs(s['tp1']-s['entry']) * 10
    tp1_real = abs(s['tp1']-s['entry']) / s['entry'] * AUTO_CAPITAL * AUTO_LEVERAGE
    
    # FILTRO $7
    if tp1_real < FILTRO_TP1_MIN:
        print(f"⚠️ {tag} {s['par']} DESCARTADA (TP1: ${tp1_real:.2f})")
        return
    
    # VERIFICAR SALDO
    suficiente, saldo_actual, saldo_min = verificar_saldo_suficiente()
    if not suficiente:
        tg(f"⚠️ <b>SALDO INSUFICIENTE</b>\n\nActual: ${saldo_actual:.2f}\nMínimo: ${saldo_min:.2f}\n\nBot pausado", crear_menu_principal())
        global bot_pausado
        bot_pausado = True
        return
    
    # VERIFICAR MAX DRAWDOWN
    if stats['drawdown_hoy'] >= MAX_DRAWDOWN_DIARIO:
        tg(f"🛑 <b>MAX DRAWDOWN ALCANZADO</b>\n\nPérdidas hoy: ${stats['drawdown_hoy']:.2f}\nLímite: ${MAX_DRAWDOWN_DIARIO}\n\nBot detenido por hoy", crear_menu_principal())
        global ciclo_cerrado
        ciclo_cerrado = True
        return
    
    # VERIFICAR MAX OPS
    activas = len([o for o in ops if o['activa']])
    if activas >= MAX_OPS_SIMULTANEAS:
        print(f"⏸️ Max ops alcanzadas ({activas}/{MAX_OPS_SIMULTANEAS})")
        return
    
    if AUTO_MODE:
        # MODO AUTOMÁTICO - ABRIR DIRECTO
        abrir_operacion_auto(s, tag, AUTO_CAPITAL, AUTO_LEVERAGE)
    else:
        # MODO MANUAL - PEDIR CONFIRMACIÓN
        nueva_señal_manual(s, tag)

def nueva_señal_manual(s, tag):
    tp1_usd = abs(s['tp1']-s['entry']) if 'BTC' in s['par'] else abs(s['tp1']-s['entry']) * 10
    tp2_usd = abs(s['tp2']-s['entry']) if 'BTC' in s['par'] else abs(s['tp2']-s['entry']) * 10
    tp3_usd = abs(s['tp3']-s['entry']) if 'BTC' in s['par'] else abs(s['tp3']-s['entry']) * 10
    
    emoji = "📈" if s['side']=="LONG" else "📉"
    
    s['tp1_usd'] = tp1_usd
    s['tp2_usd'] = tp2_usd
    s['tp3_usd'] = tp3_usd
    
    msg = (
        f"🚨 <b>SEÑAL {tag} {emoji}</b>\n\n"
        f"<b>{s['par']} {s['side']}</b>\n"
        f"{s['tipo']} | {s['mercado']}\n\n"
        f"Entry: {s['entry']:.4f}\n"
        f"🎯 TP1: {s['tp1']:.4f} (~${tp1_usd:.1f})\n"
        f"TP2: {s['tp2']:.4f} (~${tp2_usd:.1f})\n"
        f"TP3: {s['tp3']:.4f} (~${tp3_usd:.1f})\n"
        f"🛡️ SL: {s['sl']:.4f}\n\n"
        f"Lev: {s['lev_sug']}x\n\n"
        f"💰 <b>Capital?</b>"
    )
    
    señales_pendientes[op_id] = {'señal': s, 'tag': tag, 'esperando': 'capital', 'capital': None, 'leverage': None}
    guardar_datos()
    tg(msg, crear_teclado_capital())
    print(f"🔔 {tag} {s['par']}")

def abrir_operacion_auto(s, tag, cap, lev):
    hora = obtener_hora_arg()
    
    tp1_real = abs(s['tp1']-s['entry']) / s['entry'] * cap * lev
    tp2_real = abs(s['tp2']-s['entry']) / s['entry'] * cap * lev
    tp3_real = abs(s['tp3']-s['entry']) / s['entry'] * cap * lev
    sl_perdida = abs(s['sl']-s['entry']) / s['entry'] * cap * lev
    
    if MODO_REAL:
        try:
            exchange.set_leverage(lev, s['par'])
            cantidad = cap * lev / s['entry']
            binance_side = "buy" if s['side'] == "LONG" else "sell"
            exchange.create_market_order(s['par'], binance_side, cantidad)
        except Exception as e:
            tg(f"❌ Error {tag}: {e}", crear_menu_principal())
            return
    
    tg(f"✅ <b>🤖 AUTO {tag}</b>\n\n{s['par']} {s['side']}\n{hora}hs\n\n{s['tipo']}\n\n💰 ${cap} | {lev}x\n\n🎯 TP1: ${tp1_real:.2f}\nTP2: ${tp2_real:.2f}\nTP3: ${tp3_real:.2f}\n\n🛡️ SL: ${sl_perdida:.2f}\n\n{'🔴 REAL' if MODO_REAL else '🟢 PAPER'}", crear_menu_principal())
    
    ops.append({
        'tag':tag, 'par':s['par'], 'side':s['side'], 
        'entry':s['entry'], 'tp1':s['tp1'], 'tp2':s['tp2'], 'tp3':s['tp3'], 'sl':s['sl'], 
        'tps':[], 'activa':True, 'be':False, 'tipo':s['tipo'], 
        'capital':cap, 'leverage':lev, 'timestamp':datetime.now().isoformat(), 
        'tp1_usd':tp1_real, 'tp2_usd':tp2_real, 'tp3_usd':tp3_real, 'pnl_final':0
    })
    guardar_datos()
    print(f"✅ {tag} AUTO - ${cap} {lev}x")

def cerrar_operacion_manual(tag):
    hora = obtener_hora_arg()
    
    for op in ops:
        if op['tag'] == tag and op['activa']:
            try:
                ticker = exchange.fetch_ticker(op['par'])
                p = ticker['last']
                cap = op['capital']
                lev = op['leverage']
                
                if op['side']=='LONG':
                    pnl = (p-op['entry'])/op['entry']*cap*lev
                else:
                    pnl = (op['entry']-p)/op['entry']*cap*lev
                
                if pnl <= 0:
                    tg(f"⚠️ {tag} en pérdida ${pnl:.2f}\nNo se puede cerrar", crear_menu_principal())
                    return
                
                if MODO_REAL:
                    try:
                        cantidad = cap*lev/p
                        binance_side = "sell" if op['side']=="LONG" else "buy"
                        exchange.create_market_order(op['par'], binance_side, cantidad)
                    except Exception as e:
                        tg(f"Error: {e}", crear_menu_principal())
                        return
                
                op['activa'] = False
                op['pnl_final'] = pnl
                stats['wins'] += 1
                stats['total_pnl'] += pnl
                actualizar_balance(pnl, 'win')
                
                tg(f"💵 <b>CERRADA {tag}</b>\n{op['par']}\n{hora}hs\n+${pnl:.2f}\n\n(Manual)", crear_menu_principal())
                print(f"💵 {tag} Manual +${pnl:.2f}")
                
            except Exception as e:
                tg(f"Error: {e}", crear_menu_principal())
            break

def procesar_callback(callback_data):
    global bot_pausado, MODO_REAL, ciclo_cerrado, AUTO_MODE
    
    if callback_data == "menu_stats": 
        enviar_stats()
    elif callback_data == "menu_activas": 
        enviar_activas()
    elif callback_data == "menu_balance": 
        enviar_balance()
    elif callback_data == "menu_saldo": 
        enviar_saldo_binance()
    elif callback_data == "menu_auto":
        AUTO_MODE = not AUTO_MODE
        guardar_modo()
        tg(f"{'🤖 MODO AUTOMÁTICO' if AUTO_MODE else '👤 MODO MANUAL'}\n\n{'Abre ops sin confirmación' if AUTO_MODE else 'Pide confirmación Telegram'}", crear_menu_principal())
    elif callback_data == "menu_cerrar_op":
        teclado = crear_teclado_cerrar_ops()
        if teclado:
            tg("💵 <b>CERRAR OP</b>\n\nSelecciona:", teclado)
        else:
            tg("Sin ops en ganancia", crear_menu_principal())
    elif callback_data.startswith("cerrar_op_"):
        tag = callback_data.replace("cerrar_op_", "")
        cerrar_operacion_manual(tag)
    elif callback_data == "cancelar_cierre":
        tg("❌ Cancelado", crear_menu_principal())
    elif callback_data == "menu_pausar":
        if ciclo_cerrado:
            ciclo_cerrado = False
            bot_pausado = False
            stats['drawdown_hoy'] = 0.0
            tg("▶️ <b>REANUDADO</b>", crear_menu_principal())
        else:
            bot_pausado = not bot_pausado
            tg(f"{'⏸️ PAUSADO' if bot_pausado else '▶️ ACTIVO'}", crear_menu_principal())
    elif callback_data == "menu_ciclo":
        ciclo_cerrado = not ciclo_cerrado
        if ciclo_cerrado:
            bot_pausado = True
            tg("⏹️ <b>CICLO CERRADO</b>\n\nMonitoreo activo", crear_menu_principal())
        else:
            bot_pausado = False
            tg("▶️ <b>REANUDADO</b>", crear_menu_principal())
    elif callback_data == "menu_modo":
        MODO_REAL = not MODO_REAL
        guardar_modo()
        tg(f"🔄 {'🔴 REAL' if MODO_REAL else '🟢 PAPER'}", crear_menu_principal())
    elif callback_data == "menu_reset":
        resetear_bot()
    
    elif callback_data.startswith("cap_"):
        m = int(callback_data.replace("cap_", ""))
        for oid, d in señales_pendientes.items():
            if d['esperando'] == 'capital':
                d['capital'] = m
                d['esperando'] = 'leverage'
                tg(f"Capital: ${m}", crear_teclado_leverage())
                break
    
    elif callback_data.startswith("lev_"):
        l = int(callback_data.replace("lev_", ""))
        for oid, d in señales_pendientes.items():
            if d['esperando'] == 'leverage':
                d['leverage'] = l
                d['esperando'] = 'confirmar'
                s = d['señal']
                
                tp1_real = abs(s['tp1']-s['entry']) / s['entry'] * d['capital'] * l
                tp3_real = abs(s['tp3']-s['entry']) / s['entry'] * d['capital'] * l
                sl_real = abs(s['sl']-s['entry']) / s['entry'] * d['capital'] * l
                
                msg = f"Confirmar {d['tag']}\n{s['par']}\n${d['capital']} {l}x\n\nTP1: +${tp1_real:.2f}\nMax: +${tp3_real:.2f}\nSL: -${sl_real:.2f}"
                tg(msg, crear_teclado_confirmar(oid))
                break
    
    elif callback_data.startswith("confirmar_"):
        oid = int(callback_data.replace("confirmar_", ""))
        if oid in señales_pendientes:
            d = señales_pendientes[oid]
            s = d['señal']
            cap = d['capital']
            lev = d['leverage']
            
            tp1_real = abs(s['tp1']-s['entry']) / s['entry'] * cap * lev
            
            if tp1_real < FILTRO_TP1_MIN:
                tg(f"⚠️ DESCARTADA\n\n{d['tag']} TP1: ${tp1_real:.2f}\n\nMin $7", crear_menu_principal())
                del señales_pendientes[oid]
            else:
                abrir_operacion_auto(s, d['tag'], cap, lev)
                del señales_pendientes[oid]
    
    elif callback_data.startswith("cancelar_"):
        oid = int(callback_data.replace("cancelar_", ""))
        if oid in señales_pendientes:
            tg(f"❌ {señales_pendientes[oid]['tag']} cancelada")
            del señales_pendientes[oid]

def resetear_bot():
    global op_id, stats, ops, balance
    try:
        if os.path.exists(STATS_FILE): os.remove(STATS_FILE)
        if os.path.exists(OPS_FILE): os.remove(OPS_FILE)
        if os.path.exists(BALANCE_FILE): os.remove(BALANCE_FILE)
        
        op_id = 0
        stats = {'wins': 0, 'losses': 0, 'be': 0, 'total_pnl': 0.0, 'drawdown_hoy': 0.0}
        ops = []
        balance = {'hoy': {}, 'semana': {}, 'mes': {}, 'año': {}}
        
        guardar_datos()
        tg("🗑️ <b>RESET</b>\n\nID: #001", crear_menu_principal())
        print("🗑️ Reset")
    except Exception as e:
        tg(f"Error: {e}", crear_menu_principal())

# ==========================================
# MONITOREO - BE PROGRESIVO
# ==========================================
def monitorear():
    hora = obtener_hora_arg()
    for op in ops[:]:
        if not op['activa']: continue
        
        try:
            ticker = exchange.fetch_ticker(op['par'])
            p = ticker['last']
            cap = op.get('capital', 0)
            lev = op.get('leverage', 0)
            if cap <= 0: continue
            
            # SL
            if (op['side']=="LONG" and p<=op['sl']) or (op['side']=="SHORT" and p>=op['sl']):
                if MODO_REAL:
                    try:
                        cantidad = cap*lev/p
                        binance_side = "sell" if op['side']=="LONG" else "buy"
                        exchange.create_market_order(op['par'], binance_side, cantidad)
                    except: pass
                
                if op['be']:
                    if len(op['tps']) == 2:
                        ganancia_tp1 = op['tp1_usd']
                        tg(f"🔒 <b>BE TP1 {op['tag']}</b>\n{op['par']}\n{hora}hs\n+${ganancia_tp1:.2f}")
                        stats['wins'] += 1
                        stats['total_pnl'] += ganancia_tp1
                        op['pnl_final'] = ganancia_tp1
                        actualizar_balance(ganancia_tp1, 'win')
                    else:
                        tg(f"⚖️ <b>BE {op['tag']}</b>\n{op['par']}\n{hora}hs\n$0.00")
                        stats['be'] += 1
                        actualizar_balance(0, 'be')
                else:
                    perdida = abs(op['sl']-op['entry'])/op['entry']*cap*lev
                    tg(f"❌ <b>SL {op['tag']}</b>\n{op['par']}\n{hora}hs\n-${perdida:.2f}")
                    stats['losses'] += 1
                    stats['total_pnl'] -= perdida
                    stats['drawdown_hoy'] += perdida
                    actualizar_balance(-perdida, 'loss')
                
                op['activa'] = False
                guardar_datos()
                continue
            
            # TP
            for i, tp in enumerate([op['tp1'], op['tp2'], op['tp3']]):
                if i not in op['tps']:
                    if (op['side']=="LONG" and p>=tp) or (op['side']=="SHORT" and p<=tp):
                        usdt = 0
                        if i == 0: 
                            usdt = op['tp1_usd']
                        elif i == 1: 
                            usdt = op['tp2_usd'] - op['tp1_usd']
                        elif i == 2: 
                            usdt = op['tp3_usd'] - op['tp2_usd']
                        
                        tg(f"✅ <b>TP{i+1} {op['tag']}</b>\n{op['par']}\n{tp:.4f}\n{hora}hs\n+${usdt:.2f}")
                        op['tps'].append(i)
                        
                        # BE PROGRESIVO
                        if i == 0:
                            comision = op['entry'] * COMISION_BINANCE
                            if op['side']=='LONG':
                                op['sl'] = op['entry'] + comision
                            else:
                                op['sl'] = op['entry'] - comision
                            op['be'] = True
                            tg(f"🔒 <b>BE ENTRY {op['tag']}</b>\nSL: {op['sl']:.4f}")
                            actualizar_balance(usdt, 'win')
                        
                        elif i == 1:
                            op['sl'] = op['tp1']
                            tg(f"🔒 <b>BE TP1 {op['tag']}</b>\nSL: {op['sl']:.4f}\n(TP1 asegurado)")
                            actualizar_balance(usdt, 'win')
                        
                        guardar_datos()
            
            # WIN
            if len(op['tps']) == 3:
                if MODO_REAL:
                    try:
                        cantidad = cap*lev/p
                        binance_side = "sell" if op['side']=="LONG" else "buy"
                        exchange.create_market_order(op['par'], binance_side, cantidad)
                    except: pass
                
                total = op['tp3_usd']
                op['pnl_final'] = total
                tg(f"🏆 <b>WIN {op['tag']}</b>\n{op['par']}\n{hora}hs\n+${total:.2f}")
                stats['wins'] += 1
                stats['total_pnl'] += total
                actualizar_balance(total, 'win')
                op['activa'] = False
                guardar_datos()
        
        except Exception as e:
            print(f"Error monitoreo {op.get('tag', '?')}: {e}")

# ==========================================
# LISTENER TELEGRAM
# ==========================================
def tg_listener():
    global last_update_id
    while True:
        try:
            res = requests.get(f"https://api.telegram.org/bot{TG_TOKEN}/getUpdates?offset={last_update_id+1}&timeout=10", timeout=15).json()
            if not res.get("ok"): continue
            
            for u in res.get("result", []):
                last_update_id = u['update_id']
                if "callback_query" in u:
                    procesar_callback(u["callback_query"]["data"])
        except Exception as e:
            print(f"Error listener: {e}")
            time.sleep(5)

# ==========================================
# MAIN LOOP
# ==========================================
def main_loop():
    saldo_min = calcular_saldo_minimo()
    tg(f"🤖 <b>STRATEGOS.HC</b>\n\n{'AUTOMÁTICO' if AUTO_MODE else 'MANUAL'}\n${AUTO_CAPITAL} | {AUTO_LEVERAGE}x\nMax: {MAX_OPS_SIMULTANEAS} ops\n\nSaldo mín: ${saldo_min:.2f}\n\n{'🔴 REAL' if MODO_REAL else '🟢 PAPER'}", crear_menu_principal())
    
    while True:
        try:
            print(f"💓 {datetime.now().strftime('%H:%M:%S')} | {obtener_hora_arg()} ARG")
            
            monitorear()
            
            if not bot_pausado and not ciclo_cerrado:
                activas = len([o for o in ops if o['activa']])
                
                if activas < MAX_OPS_SIMULTANEAS:
                    print("🔍 Buscando...")
                    for par in PAIRS:
                        if any(o['par']==par and o['activa'] for o in ops):
                            continue
                        if any(d['señal']['par']==par for d in señales_pendientes.values()):
                            continue
                        
                        s = analizar(par)
                        if s: 
                            procesar_señal(s)
                            break
            
            time.sleep(300)
        
        except Exception as e:
            print(f"⚠️ Error loop: {e}")
            time.sleep(10)

# ==========================================
# INICIO
# ==========================================
if __name__ == '__main__':
    cargar_datos()
    
    t_bot = threading.Thread(target=main_loop)
    t_bot.daemon = True
    t_bot.start()
    
    t_tg = threading.Thread(target=tg_listener)
    t_tg.daemon = True
    t_tg.start()
    
    print("="*60)
    print("  🤖 STRATEGOS.HC - MODO AUTOMÁTICO")
    print("  BE Progresivo | Saldo Inteligente")
    print("="*60)
    
    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:

        print("\n🛑 Detenido")
