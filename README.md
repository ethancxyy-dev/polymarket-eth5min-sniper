# 🎯 Polymarket ETH 5M Event-Driven Sniper Bot

A high-frequency, event-driven statistical arbitrage bot built for the Polymarket prediction market. This system leverages micro-structure latency and purely statistical mean-reversion models to execute trades on Ethereum hourly outcome markets. 

Due to Polymarket's binary option mechanism, this strategy natively benefits from **zero slippage**.

## 🧠 Core Architecture & Micro-structure Logic

* **Latency Arbitrage (Time-left Trigger):** Connects to Binance WebSockets (`ethusdt@kline_5m`) to preemptively map underlying asset movements 1.25 seconds before the Polymarket 5-minute candle closes.
* **Statistical Reversion Engine:** Implements a strict mean-reversion signal based on 3 consecutive solid-color candles, programmatically filtering out Doji (cross) noise to ensure statistical purity.
* **Order Micro-structure:** * Utilizes pure limit orders (GTC) fixed at $0.50. This achieves zero-slippage execution and maximizes capital efficiency.
  * **90-Second Time-in-Force (TiF) Kill Switch:** Cancels unexecuted orders after 90 seconds to free up capital and avoid stale limit orders.
* **Time-Lock Liquidity Defense:** Dynamically anchored to Eastern Time (New York 10:00 - 19:00) using `pytz`, focusing capital deployment strictly during peak Wall Street liquidity and volatility hours.

## 🛠️ Installation & Setup

### 1. Clone the repository
```bash
git clone [https://github.com/YOUR_GITHUB_USERNAME/YOUR_REPOSITORY_NAME.git](https://github.com/YOUR_GITHUB_USERNAME/YOUR_REPOSITORY_NAME.git)
cd YOUR_REPOSITORY_NAME
```

### 2. Install dependencies
Ensure you have Python 3.8+ installed. Install the required packages:
```bash
pip install py-clob-client websocket-client python-dotenv requests pytz
```

### 3. Environment Variables (Security First 🛡️)
This bot requires your Polymarket wallet credentials to execute trades. **Never hardcode your private keys into the scripts.**

We use `.env` files to keep secrets safe. Follow these steps to configure your environment:

1. In the root directory, locate the `.env.example` file.
2. Make a copy of this file and rename it to exactly `.env` (notice the dot at the beginning):
   ```bash
   cp .env.example .env
   ```
3. Open the newly created `.env` file and insert your actual credentials:
   ```text
   PRIVATE_KEY=your_private_key_here_without_0x
   FUNDER_ADDRESS=0x_your_public_wallet_address_here
   ```
*(Note: Ensure your `.env` file is added to your `.gitignore` to prevent accidental uploads to GitHub.)*

## 🚀 Running the Bot
Once the environment is securely configured, deploy the system:
```bash
python Eth5minbot.py
```
The console will display real-time capital synchronization, active WebSocket streams, and order execution logs.

## ⚠️ Disclaimer
This software is for educational and research purposes only. Algorithmic trading involves significant risk. Do not deploy this bot with funds you cannot afford to lose.