from PyQt4.QtGui import *
from PyQt4.QtCore import *

import datetime
import decimal
import httplib
import json
import threading
import time
import re
from decimal import Decimal
from electrum_myr.plugins import BasePlugin, hook
from electrum_myr.i18n import _
from electrum_myr_gui.qt.util import *
from electrum_myr_gui.qt.amountedit import AmountEdit


EXCHANGES = ["Cryptsy",
             "MintPal",
             "Prelude"]


class Exchanger(threading.Thread):

    def __init__(self, parent):
        threading.Thread.__init__(self)
        self.daemon = True
        self.parent = parent
        self.quote_currencies = None
        self.lock = threading.Lock()
        self.query_rates = threading.Event()
        self.use_exchange = self.parent.config.get('use_exchange', "MintPal")
        self.parent.exchanges = EXCHANGES
        self.parent.currencies = ["BTC"]
        self.parent.win.emit(SIGNAL("refresh_exchanges_combo()"))
        self.parent.win.emit(SIGNAL("refresh_currencies_combo()"))
        self.is_running = False

    def get_json(self, site, get_string, http=False):
        try:
            if http:
                connection = httplib.HTTPConnection(site)
            else:
                connection = httplib.HTTPSConnection(site)
            connection.request("GET", get_string, headers={"User-Agent":"Electrum"})
        except Exception:
            raise
        resp = connection.getresponse()
        if resp.reason == httplib.responses[httplib.NOT_FOUND]:
            raise
        try:
            json_resp = json.loads(resp.read())
        except Exception:
            raise
        return json_resp


    def exchange(self, btc_amount, quote_currency):
        with self.lock:
            if self.quote_currencies is None:
                return None
            quote_currencies = self.quote_currencies.copy()
        if quote_currency not in quote_currencies:
            return None
        return btc_amount * decimal.Decimal(str(quote_currencies[quote_currency]))

    def stop(self):
        self.is_running = False

    def update_rate(self):
        self.use_exchange = self.parent.config.get('use_exchange', "MintPal")
        update_rates = {
            "Cryptsy": self.update_c,
            "MintPal": self.update_mp,
            "Prelude": self.update_pl,
        }
        try:
            update_rates[self.use_exchange]()
        except KeyError:
            return

    def run(self):
        self.is_running = True
        while self.is_running:
            self.query_rates.clear()
            self.update_rate()
            self.query_rates.wait(150)


    def update_mp(self):
        quote_currencies = {"BTC": 0.0}
        for cur in quote_currencies:
            try:
                quote_currencies[cur] = Decimal(self.get_json('api.mintpal.com', "/v1/market/stats/MYR/BTC")[0]['last_price'])
            except Exception:
                pass
        quote_currencies['mBTC'] = quote_currencies['BTC'] * Decimal('1000.0')
        quote_currencies['uBTC'] = quote_currencies['mBTC'] * Decimal('1000.0')
        quote_currencies['sat'] = quote_currencies['uBTC'] * Decimal('100.0')
        with self.lock:
            self.quote_currencies = quote_currencies
        self.parent.set_currencies(quote_currencies)

    def update_pl(self):
        quote_currencies = {"BTC": 0.0}
        try:
            jsonresp = self.get_json('api.prelude.io', "/last/MYR")
        except Exception:
            return
        try:
            btcprice = jsonresp["last"]
            quote_currencies["BTC"] = decimal.Decimal(str(btcprice))
            quote_currencies['mBTC'] = quote_currencies['BTC'] * Decimal('1000.0')
            quote_currencies['uBTC'] = quote_currencies['mBTC'] * Decimal('1000.0')
            quote_currencies['sat'] = quote_currencies['uBTC'] * Decimal('100.0')
            with self.lock:
                self.quote_currencies = quote_currencies
        except KeyError:
            pass
        self.parent.set_currencies(quote_currencies)

    def update_c(self):
        quote_currencies = {"BTC": 0.0}
        try:
            jsonresp = self.get_json('pubapi.cryptsy.com', "/api.php?method=singlemarketdata&marketid=200", http=True)['return']['markets']['MYR']
        except Exception:
            return
        try:
            btcprice = jsonresp['lasttradeprice']
            quote_currencies['BTC'] = decimal.Decimal(str(btcprice))
            quote_currencies['mBTC'] = quote_currencies['BTC'] * Decimal('1000.0')
            quote_currencies['uBTC'] = quote_currencies['mBTC'] * Decimal('1000.0')
            quote_currencies['sat'] = quote_currencies['uBTC'] * Decimal('100.0')
            with self.lock:
                self.quote_currencies = quote_currencies
        except KeyError:
            pass
        self.parent.set_currencies(quote_currencies)


    def get_currencies(self):
        return [] if self.quote_currencies == None else sorted(self.quote_currencies.keys())


class Plugin(BasePlugin):

    def fullname(self):
        return "Exchange rates"

    def description(self):
        return """exchange rates, retrieved from MintPal"""


    def __init__(self,a,b):
        BasePlugin.__init__(self,a,b)
        self.currencies = [self.fiat_unit()]
        self.exchanges = [self.config.get('use_exchange', "MintPal")]
        self.exchanger = None

    @hook
    def init_qt(self, gui):
        self.gui = gui
        self.win = self.gui.main_window
        self.win.connect(self.win, SIGNAL("refresh_currencies()"), self.win.update_status)
        self.btc_rate = Decimal("0.0")
        if self.exchanger is None:
            # Do price discovery
            self.exchanger = Exchanger(self)
            self.exchanger.start()
            self.gui.exchanger = self.exchanger #
            self.add_fiat_edit()
            self.win.update_status()

    def close(self):
        self.exchanger.stop()
        self.exchanger = None
        self.win.tabs.removeTab(1)
        self.win.tabs.insertTab(1, self.win.create_send_tab(), _('Send'))
        self.win.update_status()

    def set_currencies(self, currency_options):
        self.currencies = sorted(currency_options)
        self.win.emit(SIGNAL("refresh_currencies()"))
        self.win.emit(SIGNAL("refresh_currencies_combo()"))

    @hook
    def get_fiat_balance_text(self, btc_balance, r):
        # return balance as: 1.23 USD
        r[0] = self.create_fiat_balance_text(Decimal(btc_balance) / 100000000)

    def get_fiat_price_text(self, r):
        # return BTC price as: 123.45 USD
        r[0] = self.create_fiat_balance_text(1)
        quote = r[0]
        if quote:
            r[0] = "%s"%quote

    @hook
    def get_fiat_status_text(self, btc_balance, r2):
        # return status as:   (1.23 USD)    1 BTC~123.45 USD
        text = ""
        r = {}
        self.get_fiat_price_text(r)
        quote = r.get(0)
        if quote:
            price_text = "1 MYR~%s"%quote
            fiat_currency = self.fiat_unit()
            btc_price = self.btc_rate
            fiat_balance = Decimal(btc_price) * (Decimal(btc_balance)/100000000)
            balance_text = "(%.2f %s)" % (fiat_balance,fiat_currency)
            text = "  " + balance_text + "     " + price_text + " "
        r2[0] = text

    def create_fiat_balance_text(self, btc_balance):
        quote_currency = self.fiat_unit()
        self.exchanger.use_exchange = self.config.get("use_exchange", "MintPal")
        cur_rate = self.exchanger.exchange(Decimal("1.0"), quote_currency)
        if cur_rate is None:
            quote_text = ""
        else:
            quote_balance = btc_balance * Decimal(cur_rate)
            self.btc_rate = cur_rate
            quote_text = "%.2f %s" % (quote_balance, quote_currency)
        return quote_text

    @hook
    def load_wallet(self, wallet):
        self.wallet = wallet
        tx_list = {}
        for item in self.wallet.get_tx_history(self.wallet.storage.get("current_account", None)):
            tx_hash, conf, is_mine, value, fee, balance, timestamp = item
            tx_list[tx_hash] = {'value': value, 'timestamp': timestamp, 'balance': balance}

        self.tx_list = tx_list


    def requires_settings(self):
        return True


    def settings_widget(self, window):
        return EnterButton(_('Settings'), self.settings_dialog)

    def settings_dialog(self):
        d = QDialog()
        d.setWindowTitle("Settings")
        layout = QGridLayout(d)
        layout.addWidget(QLabel(_('Exchange rate API: ')), 0, 0)
        layout.addWidget(QLabel(_('Currency: ')), 1, 0)
        combo = QComboBox()
        combo_ex = QComboBox()
        ok_button = QPushButton(_("OK"))

        def on_change(x):
            try:
                cur_request = str(self.currencies[x])
            except Exception:
                return
            if cur_request != self.fiat_unit():
                self.config.set_key('currency', cur_request, True)
                cur_exchange = self.config.get('use_exchange', "MintPal")
                self.win.update_status()
                try:
                    self.fiat_button
                except:
                    pass
                else:
                    self.fiat_button.setText(cur_request)

        def on_change_ex(x):
            cur_request = str(self.exchanges[x])
            if cur_request != self.config.get('use_exchange', "MintPal"):
                self.config.set_key('use_exchange', cur_request, True)
                self.currencies = []
                combo.clear()
                self.exchanger.query_rates.set()
                cur_currency = self.config.get('currency', "BTC")
                set_currencies(combo)
                self.win.update_status()

        def set_currencies(combo):
            current_currency = self.fiat_unit()
            try:
                combo.clear()
            except Exception:
                return
            combo.addItems(self.currencies)
            try:
                index = self.currencies.index(current_currency)
            except Exception:
                index = 0
            combo.setCurrentIndex(index)

        def set_exchanges(combo_ex):
            try:
                combo_ex.clear()
            except Exception:
                return
            combo_ex.addItems(self.exchanges)
            try:
                index = self.exchanges.index(self.config.get('use_exchange', "MintPal"))
            except Exception:
                index = 0
            combo_ex.setCurrentIndex(index)

        def ok_clicked():
            d.accept();

        set_exchanges(combo_ex)
        set_currencies(combo)
        combo.currentIndexChanged.connect(on_change)
        combo_ex.currentIndexChanged.connect(on_change_ex)
        combo.connect(self.win, SIGNAL('refresh_currencies_combo()'), lambda: set_currencies(combo))
        combo_ex.connect(d, SIGNAL('refresh_exchanges_combo()'), lambda: set_exchanges(combo_ex))
        ok_button.clicked.connect(lambda: ok_clicked())
        layout.addWidget(combo,1,1)
        layout.addWidget(combo_ex,0,1)
        layout.addWidget(ok_button,3,1)

        if d.exec_():
            return True
        else:
            return False

    def fiat_unit(self):
        return self.config.get("currency", "BTC")

    def add_fiat_edit(self):
        self.fiat_e = AmountEdit(self.fiat_unit)
        self.btc_e = self.win.amount_e
        grid = self.btc_e.parent()
        def fiat_changed():
            try:
                fiat_amount = Decimal(str(self.fiat_e.text()))
            except:
                self.btc_e.setText("")
                return
            exchange_rate = self.exchanger.exchange(Decimal("1.0"), self.fiat_unit())
            if exchange_rate is not None:
                btc_amount = fiat_amount/exchange_rate
                self.btc_e.setAmount(int(btc_amount*Decimal(100000000)))
        self.fiat_e.textEdited.connect(fiat_changed)
        def btc_changed():
            btc_amount = self.btc_e.get_amount()
            if btc_amount is None:
                self.fiat_e.setText("")
                return
            fiat_amount = self.exchanger.exchange(Decimal(btc_amount)/Decimal(100000000), self.fiat_unit())
            if fiat_amount is not None:
                self.fiat_e.setText("%.2f"%fiat_amount)
        self.btc_e.textEdited.connect(btc_changed)
        self.btc_e.frozen.connect(lambda: self.fiat_e.setFrozen(self.btc_e.isReadOnly()))
        self.win.send_grid.addWidget(self.fiat_e, 4, 3, Qt.AlignHCenter)
