# -*- coding: utf-8 -*-
"""
* GMail Export Ver 0.1.0
* This library allows the user to export gmail to various formats.
"""
import os
import json
from os.path import expanduser
from pathlib import Path
import platform


try:
    import airtable
    AIRTABLE = True
except ImportError: 
    AIRTABLE = False
try:
    import dropbox
    DROPBOX = True
except ImportError: 
    DROPBOX = False

TIMEZONE='America/Toronto'

CFG_PATH = os.path.join(str(Path.home()), '.gmail_export')
TOKEN_PATH = os.path.join(CFG_PATH, 'token.json')
CREDENTIALS_PATH = os.path.join(CFG_PATH, 'credentials.json')
# # If modifying these scopes, delete the file token.json.
SCOPES = ['https://www.googleapis.com/auth/gmail.readonly']
IMAGE_LOAD_BLACKLIST = frozenset(['emltrk.com', 'trk.email', 'shim.gif'])





AT_CONFIG = {}
if AIRTABLE:
    AIRTABLE_CFG = os.path.join(CFG_PATH, 'airtable.json')
    with open(AIRTABLE_CFG, "r") as jsonfile:
        AT_CONFIG = json.load(jsonfile)
DB_CONFIG = {}
if DROPBOX:
    DROPBOX_CFG  = os.path.join(CFG_PATH, 'dropbox.json')
    with open(DROPBOX_CFG, "r") as jsonfile:
        DB_CONFIG = json.load(jsonfile)

if platform.system() == "Windows":
    appdata=os.path.join(os.getenv('APPDATA'),'Dropbox','info.json' )
    localappdata=os.path.join(os.getenv('LOCALAPPDATA'),'Dropbox','info.json' )
    if os.path.isfile(appdata):
        with open(appdata, "r") as jsonfile:
            _path = json.load(jsonfile)['personal']['path']
            EXPORT_PATH = os.path.join(_path, "EmailBackup")
    elif os.path.isfile(localappdata):
        with open(localappdata, "r") as jsonfile:
            _path = json.load(jsonfile)['personal']['path']
            EXPORT_PATH = os.path.join(_path, "EmailBackup")
    else:
        EXPORT_PATH = os.path.join(CFG_PATH, 'export')
        os.makedirs(EXPORT_PATH, exist_ok=True)
else:
    dbcfg=expanduser('~/.dropbox/info.json')
    if os.path.isfile(dbcfg):
        with open(dbcfg, "r") as jsonfile:
            _path = json.load(jsonfile)['personal']['path']
            EXPORT_PATH = os.path.join(_path, "EmailBackup")
    else:
        EXPORT_PATH = os.path.join(CFG_PATH, 'export')

os.makedirs(EXPORT_PATH, exist_ok=True)

print("EXPORT_PATH: ", EXPORT_PATH)


WKHTMLTOPDF_EXTERNAL_COMMAND = 'wkhtmltopdf'
WKHTMLTOPDF_ERRORS_IGNORE = frozenset(
    [r'QFont::setPixelSize: Pixel size <= 0 \(0\)',
     r'Invalid SOS parameters for sequential JPEG',
     r'libpng warning: Out of place sRGB chunk',
     r'Exit with code 1 due to network error: ContentNotFoundError',
     r'Exit with code 1 due to network error: UnknownContentError',
     r'QPainter::begin(): Returned false\r\nExit with code 1'])


class FatalException(Exception):
    def __init__(self, value):
        Exception.__init__(self, value)
        self.value = value

    def __str__(self):
        return repr(self.value)


