import os
import time
import requests
import json
import threading
import websocket
from datetime import datetime
import pytz  # 用于动态获取纽约时区
from dotenv import load_dotenv
from py_clob_client.client import ClobClient
from py_clob_client.clob_types import OrderArgs, OrderType, BalanceAllowanceParams, AssetType

# ==========================================
# 1. 系统初始化与安全校验
# ==========================================
load_dotenv()

# 🚨 核心安全隔离：从 .env 文件读取私钥，绝不硬编码
private_key = os.getenv("PRIVATE_KEY")
funder_address = os.getenv("FUNDER_ADDRESS")

if not private_key or not funder_address:
    raise ValueError("🚨 致命错误: 未在 .env 文件中找到 PRIVATE_KEY 或 FUNDER_ADDRESS。请参考 .env.example 进行配置！")

client = ClobClient(
    host="https://clob.polymarket.com",
    key=private_key,
    chain_id=137,
    signature_type=1,
    funder=funder_address
)
client.set_api_creds(client.create_or_derive_api_creds())

# 初始资金设为0，通过 sync_capital 动态获取
TOTAL_CAPITAL = 0.0 

def sync_capital():
    global TOTAL_CAPITAL
    try:
        params = BalanceAllowanceParams(asset_type=AssetType.COLLATERAL)
        resp = client.get_balance_allowance(params)
        cash = float(resp['balance']) / 1e6 if isinstance(resp, dict) and 'balance' in resp else 0.0
        pos_value = 0.0
        try:
            val_url = f"https://data-api.polymarket.com/value?user={funder_address}"
            val_resp = requests.get(val_url, timeout=5).json()
            pos_value = float(val_resp[0].get('value', 0)) if isinstance(val_resp, list) else float(val_resp.get('value', 0))
        except: pass
        TOTAL_CAPITAL = cash + pos_value
        print(f"💰 [资产更新] 总资产: ${TOTAL_CAPITAL:.2f}")
    except Exception as e:
        pass

# ==========================================
# 2. 交易执行模块 (严格 90s 闭环)
# ==========================================
def execute_trade(side, trigger_type):
    # 挂单价变更为 0.50
    price = 0.50 
    print(f"🚀 [信号触发] 目标: {side.upper()} | 触发: {trigger_type} | 挂单 {price}")
    current_time = int(time.time())
    
    # 获取即将开始的新 5 分钟市场靶子
    target_boundary = ((current_time + 150) // 300) * 300 
    slug = f"eth-updown-5m-{target_boundary}"
    token_id = None
    headers = {'User-Agent': 'Mozilla/5.0'}

    for _ in range(500):
        try:
            r = requests.get(f"https://gamma-api.polymarket.com/events?slug={slug}", headers=headers, timeout=1).json()
            m = r[0].get('markets', [])
            tids = json.loads(m[0]['clobTokenIds'])
            outcomes = json.loads(m[0]['outcomes'])
            token_id = tids[0] if outcomes[0].lower() == side.lower() else tids[1]
            break
        except: pass
        time.sleep(0.02)
    if not token_id: return

    # 丝滑复利模式
    size = round((TOTAL_CAPITAL * 0.0198) / price, 2)
    print(f"📡 挂单指令: 价格 {price} | 份额 {size} | 潜伏倒计时 90 秒开始...")

    start_fire = time.time()
    order_id = None
    try:
        order = client.create_order(OrderArgs(price=price, size=size, side="BUY", token_id=token_id))
        resp = client.post_order(order, OrderType.GTC)
        if resp.get('success'):
            order_id = resp.get('orderID')
            print(f"💥 [订单已挂] ID: {order_id} | 刺客就位！等待砸盘...")
        else:
            print(f"⚠️ 下单被拒: {resp.get('errorMsg')}")
            return
    except Exception as e:
        print(f"❌ 发射异常: {e}")
        return

    # 防护网：确保 order_id 存在再进入循环
    if not order_id: return

    # 90秒生死线监控
    start_monitor = time.time()
    while (time.time() - start_monitor) < 90.0:
        try:
            status = client.get_order(order_id).get('status')
            if status in ['closed', 'filled']:
                print(f"✅ [成交确认] {price} 捡漏成功！")
                return
        except: pass
        time.sleep(2)
    
    print(f"🕒 [时间耗尽] 行情未回头，执行 90s 战术撤单...")
    try:
        client.cancel_orders([order_id])
        print(f"🛡️ [撤单成功] 僵尸单已清理，本金释放。")
    except Exception as e:
        print(f"🔴 [撤单提示] 撤单被拒 (可能已在最后一秒压哨成交，或API拥堵): {e}")

# ==========================================
# 3. 策略大脑 (双扳机 + 纯色判定版 + 智能时区时间锁)
# ==========================================
MAX_LOSSES = 4       
PAUSE_MINUTES = 15   

candle_history = []
consecutive_losses = 0
cooldown_end_time = 0
last_signal = None  
last_processed_t = 0  

def on_message(ws, message):
    global candle_history, consecutive_losses, cooldown_end_time, last_signal, last_processed_t
    data = json.loads(message)
    k = data['k']
    
    t_start = k['t']         
    t_close = k['T']         
    event_time = data['E']   
    time_left = t_close - event_time
    
    # 双扳机逻辑
    trigger_early = (0 <= time_left <= 1250)
    trigger_closed = k['x']

    if (trigger_early or trigger_closed) and t_start != last_processed_t:
        last_processed_t = t_start # 单K线自锁
        trigger_type = "⚡1.25s极速抢跑" if trigger_early else "🛡️闭合信号兜底"
        
        # 绝对颜色判定，剔除十字星干扰
        c_price = float(k['c'])
        o_price = float(k['o'])
        if c_price > o_price:
            k_color = "🟢"
        elif c_price < o_price:
            k_color = "🔴"
        else:
            k_color = "⚪" # 十字星
        
        # 结果复盘 (无视时间锁，前一单的结果必须判定)
        if last_signal:
            won = (last_signal == "up" and k_color == "🟢") or (last_signal == "down" and k_color == "🔴")
            if won:
                consecutive_losses = 0
                print(f"🏆 [战报] 拿下！连亏清零。")
            else:
                consecutive_losses += 1
                print(f"🩸 [战报] 没中。连亏: {consecutive_losses}/{MAX_LOSSES}")
                if consecutive_losses >= MAX_LOSSES:
                    cooldown_end_time = time.time() + (PAUSE_MINUTES * 60)
                    print(f"\n🚨 [熔断触发] 触发休眠 {PAUSE_MINUTES} 分钟！\n")
                    consecutive_losses = 0
            last_signal = None

        # K线队列依然保持更新，为美股开盘做热身
        candle_history.append(k_color)
        if len(candle_history) > 3: candle_history.pop(0)
        
        print(f"📊 {trigger_type}判定 | {k_color} | 队列: {candle_history}")

        if time.time() < cooldown_end_time: return
        
        # ==============================================================
        # ⏰【狙击手黄金时间锁 (智能锚定纽约当地时间 10:00 - 19:00)】
        # ==============================================================
        ny_tz = pytz.timezone('America/New_York')
        current_ny_time = datetime.now(ny_tz)
        ny_hour = current_ny_time.hour
        
        if not (10 <= ny_hour < 19):
            print(f"[{current_ny_time.strftime('%H:%M:%S')} NYT] 💤非主力时间 (纽约 {ny_hour}点)，休眠防守中...")
            return  # 没收开枪权！下面的开仓逻辑全部阻断！
        # ==============================================================

        # 只有绝对纯色的 3 连才触发，十字星 ⚪ 永远无法凑成三连
        if len(candle_history) == 3:
            if candle_history == ["🟢", "🟢", "🟢"]: 
                last_signal = "down"
                threading.Thread(target=execute_trade, args=("down", trigger_type)).start()
            elif candle_history == ["🔴", "🔴", "🔴"]: 
                last_signal = "up"
                threading.Thread(target=execute_trade, args=("up", trigger_type)).start()

def on_open(ws): print("📡 神经连通！V47.0 智能时区复利版 (夜间狙击) 就绪...")
def on_close(ws, c, m): time.sleep(3); start_brain()

def start_brain():
    ws_url = "wss://stream.binance.com:9443/ws/ethusdt@kline_5m"
    ws = websocket.WebSocketApp(ws_url, on_message=on_message, on_open=on_open, on_close=on_close)
    ws.run_forever()

if __name__ == '__main__':
    sync_capital()
    def sync_loop():
        while True:
            time.sleep(600)
            sync_capital()
    threading.Thread(target=sync_loop, daemon=True).start()
    start_brain()