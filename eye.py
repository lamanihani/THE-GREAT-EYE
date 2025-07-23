import sys
import asyncio
import aiohttp
import pandas as pd
from datetime import datetime
from binance.client import Client
from PyQt5.QtWidgets import (
    QApplication, QWidget, QVBoxLayout, QLabel, QPushButton, QTextBrowser, QHBoxLayout
)
from PyQt5.QtGui import QFont, QColor, QPalette, QMovie
from PyQt5.QtCore import Qt, QThread, pyqtSignal, QTimer

api_key = 'YOUR_API_KEY'
api_secret = 'YOUR_API_SECRET'
client = Client(api_key, api_secret)
BASE_URL = "https://api.binance.com"

class DataFetcher(QThread):
    data_ready = pyqtSignal(str)

    def run(self):
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        data = loop.run_until_complete(self.fetch_data())
        self.data_ready.emit(data)

    async def fetch_data(self):
        async with aiohttp.ClientSession() as session:
            usdt_pairs = await self.get_usdt_pairs(session)
            volatility_data = await self.get_volatility(session, usdt_pairs)
            movers_data = await self.get_movers(session, usdt_pairs)

        now = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        report = f"""
        <html>
        <head><style>
        table {{ width: 100%; border-collapse: collapse; color: #ffffff; }}
        th, td {{ border: 1px solid #444; padding: 8px; text-align: left; }}
        th {{ background-color: #333; }}
        h2 {{ color: #00ffee; text-align: center; }}
        .green {{ color: #66ff66; }}
        .red {{ color: #ff4d4d; }}
        .light {{ color: #cccccc; }}
        .yellow {{ color: #ffff66; font-weight: bold; }}
        </style></head>
        <body>
        <h2>⚡ Live Crypto Market Status ({now}) ⚡</h2><hr>
        <table>
        <tr>
            <th style='width:33%'>🚀 Top 10 Volatile (1m)</th>
            <th style='width:33%'>📈 Gainers</th>
            <th style='width:33%'>📉 Losers</th>
        </tr>
        <tr>
            <td valign='top'>
        """

        for i, (symbol, vol) in enumerate(volatility_data, 1):
            css_class = "yellow" if i <= 3 else "light"
            report += f"{i}. {symbol} — <span class='{css_class}'>{vol:.2f}%</span><br>"

        report += """
            </td>
            <td valign='top'>
        """
        for interval, section in movers_data.items():
            report += f"<h4>{interval.upper()}</h4>"
            for sym, chg in section['gainers']:
                report += f"🔥 {sym}: <span class='green'>{chg:.2f}%</span><br>"

        report += """
            </td>
            <td valign='top'>
        """
        for interval, section in movers_data.items():
            report += f"<h4>{interval.upper()}</h4>"
            for sym, chg in section['losers']:
                report += f"💀 {sym}: <span class='red'>{chg:.2f}%</span><br>"

        report += """
            </td>
        </tr>
        </table>
        </body>
        </html>
        """

        return report

    async def get_usdt_pairs(self, session):
        async with session.get(f"{BASE_URL}/api/v3/exchangeInfo") as resp:
            info = await resp.json()
            return [s['symbol'] for s in info['symbols'] if s['quoteAsset'] == 'USDT' and s['status'] == 'TRADING']

    async def fetch_klines(self, session, symbol, interval, limit=60):
        url = f"{BASE_URL}/api/v3/klines"
        params = {'symbol': symbol, 'interval': interval, 'limit': limit}
        try:
            async with session.get(url, params=params) as resp:
                return await resp.json()
        except:
            return []

    async def get_volatility(self, session, symbols):
        tasks = [self.fetch_klines(session, sym, '1m') for sym in symbols]
        klines = await asyncio.gather(*tasks)
        results = []
        for sym, data in zip(symbols, klines):
            try:
                closes = [float(k[4]) for k in data]
                returns = pd.Series(closes).pct_change().dropna()
                volatility = returns.std() * 100
                results.append((sym, volatility))
            except:
                continue
        return sorted(results, key=lambda x: x[1], reverse=True)[:10]

    async def get_movers(self, session, pairs):
        intervals = ['1h', '4h', '1d']
        movers = {}
        for interval in intervals:
            tasks = [self.fetch_klines(session, sym, interval, 2) for sym in pairs]
            klines = await asyncio.gather(*tasks)
            changes = []
            for sym, data in zip(pairs, klines):
                try:
                    open_, close = float(data[-2][1]), float(data[-1][4])
                    change = ((close - open_) / open_) * 100
                    changes.append((sym, change))
                except:
                    continue
            gainers = sorted(changes, key=lambda x: x[1], reverse=True)[:5]
            losers = sorted(changes, key=lambda x: x[1])[:5]
            movers[interval] = {'gainers': gainers, 'losers': losers}
        return movers

class CryptoTerminal(QWidget):
    def __init__(self):
        super().__init__()
        self.initUI()
        self.auto_refresh_timer = QTimer(self)
        self.auto_refresh_timer.timeout.connect(self.start_scan)
        self.auto_refresh_timer.start(5 * 60 * 1000)

    def initUI(self):
        self.setWindowTitle("⚡ Live Crypto Feed")
        self.setGeometry(100, 100, 1100, 900)

        palette = QPalette()
        palette.setColor(QPalette.Window, QColor("#121212"))
        self.setPalette(palette)

        layout = QVBoxLayout()
        self.setLayout(layout)

        self.title = QLabel("⚡ LIVE CRYPTO FEED")
        self.title.setFont(QFont("Segoe UI", 22, QFont.Bold))
        self.title.setAlignment(Qt.AlignCenter)
        self.title.setStyleSheet("color: #00ffee; padding: 16px;")

        self.browser = QTextBrowser()
        self.browser.setStyleSheet("""
            background-color: #1a1a1a;
            color: #cccccc;
            border: 1px solid #444;
            border-radius: 10px;
            padding: 16px;
            font-family: Consolas;
            font-size: 12pt;
        """)

        self.loading = QLabel()
        self.loading.setAlignment(Qt.AlignCenter)
        self.loading.setVisible(False)
        self.movie = QMovie("https://media.giphy.com/media/sSgvbe1m3n93G/giphy.gif")
        self.loading.setMovie(self.movie)

        self.button = QPushButton("🔄 Manual Refresh")
        self.button.setFont(QFont('Segoe UI', 13, QFont.Bold))
        self.button.setStyleSheet("""
            QPushButton {
                background-color: #333;
                color: #ffffff;
                border: 1px solid #555;
                padding: 12px;
                border-radius: 8px;
            }
            QPushButton:hover {
                background-color: #444;
            }
        """)
        self.button.clicked.connect(self.start_scan)

        layout.addWidget(self.title)
        layout.addWidget(self.browser)
        layout.addWidget(self.loading)
        layout.addWidget(self.button)

        self.start_scan()

    def start_scan(self):
        self.button.setEnabled(False)
        self.loading.setVisible(True)
        self.movie.start()
        self.browser.setHtml("<p style='color:#ffaa00;'>🔍 Scanning markets, stand by...</p>")
        self.worker = DataFetcher()
        self.worker.data_ready.connect(self.display_data)
        self.worker.start()

    def display_data(self, html):
        self.movie.stop()
        self.loading.setVisible(False)
        self.browser.setHtml(html)
        self.button.setEnabled(True)

if __name__ == '__main__':
    app = QApplication(sys.argv)
    gui = CryptoTerminal()
    gui.show()
    sys.exit(app.exec_())
