#
# Prypto - Electrum plugin for redeeming prypto codes
# Copyright (C) 2014 Foodies/Cr0wley (be nice this is my first pyqt project)
#
# This program is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE. See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with this program. If not, see <http://www.gnu.org/licenses/>.
 
from PyQt4.QtGui import QPushButton, QMessageBox, QDialog, QVBoxLayout, QGridLayout, QLabel, QLineEdit
from PyQt4.QtCore import Qt, QRectF, QByteArray
 
from electrum_myr.plugins import BasePlugin
from electrum_myr.i18n import _
from electrum_myr_gui.qt.util import *

import urllib2

class Plugin(BasePlugin):
 
    def fullname(self): return 'Redeem Prypto'
 
    def description(self): return "Allows redeeming of prypto cards."
 
    def __init__(self, gui, name):
        BasePlugin.__init__(self, gui, name)
        self._is_available = self._init()
 
    def _init(self):

        return True
 
    def is_available(self):
        return self._is_available
 

    def load_wallet(self, wallet):
        label = _("Prypto &Redeem")
        menu = self.gui.main_window.menuBar().actions()[2].menu();
        for i in range(menu.actions().__len__()):
            if menu.actions()[i].text() == label:
                return
        menu.addSeparator()
        dialog = menu.addAction(label)
        dialog.triggered.connect(self.show_paper_dialog)
       
    def show_paper_dialog(self):
        dialog = QDialog(self.gui.main_window)
        dialog.setModal(1)
        dialog.setWindowTitle(_("Prypto Redeem"))
        vbox = QVBoxLayout()
        grid = QGridLayout()
        grid.setColumnStretch(0,1)
       
       
       
       
        grid.addWidget(QLabel(_('Prypto Code') + ':'), 3, 0)
        self.pryp = QLineEdit()
           
        grid.addWidget(self.pryp, 3, 1)
       
        grid.addWidget(QLabel(_('Security Code') + ':'), 4, 0)
        self.sec = QLineEdit()
        grid.addWidget(self.sec, 4, 1)
       
       
        nextline = 5
       
       
        b = QPushButton(_("Redeem"))
        b.clicked.connect(self.do_credit)
        grid.addWidget(b, nextline, 0)                        
 
       
        vbox.addLayout(grid)
        dialog.setLayout(vbox)
        dialog.exec_()

		

    def do_credit(self):
        if self.gui.main_window.question("Are you sure you want to redeem this code ?"):
            coin = "MYR"
            token = "88dba8ea5697f6bfe1881fa84062b81874618517"
            act = self.get_account("")
            myradd = act.get_addresses(False)
            addr = str(myradd[0])
            url = "https://prypto.com/merchants/api/?T=RX&TKN={}&COIN={}&PC={}&SC={}&RX={}".format(token, coin, str(self.pryp.text()), str(self.sec.text()), addr)
            data = urllib2.urlopen(url)
            response = data.read()
            if response != None and len(response) == 64:
                response = str(response)
            else:
                response = "Failed!"
            QMessageBox.information(None,"Response:", _("TX= %s" % (str(response))))
			
    def get_account(self, name):
        if self.gui.main_window.wallet.seed_version == 4:
            return self.gui.main_window.wallet.accounts[0]
        actnames = self.gui.main_window.wallet.get_account_names()
        for k,v in actnames.iteritems():
            if v == name:
                return self.gui.main_window.wallet.accounts[0]
        return None
			

	
