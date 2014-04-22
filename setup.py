#!/usr/bin/python

# python setup.py sdist --format=zip,gztar

from setuptools import setup
import os
import sys
import platform
import imp


version = imp.load_source('version', 'lib/version.py')
util = imp.load_source('version', 'lib/util.py')

if sys.version_info[:3] < (2, 6, 0):
    sys.exit("Error: Electrum requires Python version >= 2.6.0...")

usr_share = '/usr/share'
if not os.access(usr_share, os.W_OK):
    usr_share = os.getenv("XDG_DATA_HOME", os.path.join(os.getenv("HOME"), ".local", "share"))

data_files = []
if (len(sys.argv) > 1 and (sys.argv[1] == "sdist")) or (platform.system() != 'Windows' and platform.system() != 'Darwin'):
    print "Including all files"
    data_files += [
        (os.path.join(usr_share, 'applications/'), ['electrum-myr.desktop']),
        (os.path.join(usr_share, 'app-install', 'icons/'), ['icons/electrum-myr.png'])
    ]
    if not os.path.exists('locale'):
        os.mkdir('locale')
    for lang in os.listdir('locale'):
        if os.path.exists('locale/%s/LC_MESSAGES/electrum.mo' % lang):
            data_files.append((os.path.join(usr_share, 'locale/%s/LC_MESSAGES' % lang), ['locale/%s/LC_MESSAGES/electrum.mo' % lang]))

appdata_dir = util.appdata_dir()
if not os.access(appdata_dir, os.W_OK):
    appdata_dir = os.path.join(usr_share, "electrum-myr")

data_files += [
    (appdata_dir, ["data/README"]),
    (os.path.join(appdata_dir, "cleanlook"), [
        "data/cleanlook/name.cfg",
        "data/cleanlook/style.css"
    ]),
    (os.path.join(appdata_dir, "sahara"), [
        "data/sahara/name.cfg",
        "data/sahara/style.css"
    ]),
    (os.path.join(appdata_dir, "dark"), [
        "data/dark/name.cfg",
        "data/dark/style.css"
    ])
]


setup(
    name="Electrum-LTC",
    version=version.ELECTRUM_VERSION,
    install_requires=['slowaes', 'ecdsa>=0.9', 'ltc_scrypt'],
    package_dir={
        'electrum_myr': 'lib',
        'electrum_myr_gui': 'gui',
        'electrum_myr_plugins': 'plugins',
    },
    scripts=['electrum-myr'],
    data_files=data_files,
    py_modules=[
        'electrum_myr.account',
        'electrum_myr.bitcoin',
        'electrum_myr.blockchain',
        'electrum_myr.bmp',
        'electrum_myr.commands',
        'electrum_myr.daemon',
        'electrum_myr.i18n',
        'electrum_myr.interface',
        'electrum_myr.mnemonic',
        'electrum_myr.msqr',
        'electrum_myr.network',
        'electrum_myr.plugins',
        'electrum_myr.pyqrnative',
        'electrum_myr.scrypt',
        'electrum_myr.simple_config',
        'electrum_myr.socks',
        'electrum_myr.transaction',
        'electrum_myr.util',
        'electrum_myr.verifier',
        'electrum_myr.version',
        'electrum_myr.wallet',
        'electrum_myr.wallet_bitkey',
        'electrum_myr_gui.gtk',
        'electrum_myr_gui.qt.__init__',
        'electrum_myr_gui.qt.amountedit',
        'electrum_myr_gui.qt.console',
        'electrum_myr_gui.qt.history_widget',
        'electrum_myr_gui.qt.icons_rc',
        'electrum_myr_gui.qt.installwizard',
        'electrum_myr_gui.qt.lite_window',
        'electrum_myr_gui.qt.main_window',
        'electrum_myr_gui.qt.network_dialog',
        'electrum_myr_gui.qt.password_dialog',
        'electrum_myr_gui.qt.qrcodewidget',
        'electrum_myr_gui.qt.receiving_widget',
        'electrum_myr_gui.qt.seed_dialog',
        'electrum_myr_gui.qt.transaction_dialog',
        'electrum_myr_gui.qt.util',
        'electrum_myr_gui.qt.version_getter',
        'electrum_myr_gui.stdio',
        'electrum_myr_gui.text',
        'electrum_myr_plugins.exchange_rate',
        'electrum_myr_plugins.labels',
        'electrum_myr_plugins.pointofsale',
        'electrum_myr_plugins.qrscanner',
        'electrum_myr_plugins.virtualkeyboard',
    ],
    description="Lightweight Myriadcoin Wallet",
    author="ecdsa",
    author_email="ecdsa@github",
    license="GNU GPLv3",
    url="http://electrum.org",
    long_description="""Lightweight Myriadcoin Wallet"""
)
