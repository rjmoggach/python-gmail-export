# -*- coding: utf-8 -*-
"""
* GMail Export Ver 0.1.0
* This library allows the user to export gmail to various formats.
"""
import os
import json
from pathlib import Path
try:
    import airtable
    AIRTABLE = True
except ImportError: AIRTABLE = False
try:
    import dropbox
    DROPBOX = True
except ImportError: DROPBOX = False

__version__ = '0.1.0'

TIMEZONE='America/Toronto'

CFG_PATH = os.path.join(str(Path.home()), '.gmail_export')
TOKEN_PATH = os.path.join(CFG_PATH, 'token.json')
CREDENTIALS_PATH = os.path.join(CFG_PATH, 'credentials.json')
# # If modifying these scopes, delete the file token.json.
SCOPES = ['https://www.googleapis.com/auth/gmail.readonly']
IMAGE_LOAD_BLACKLIST = frozenset(['emltrk.com', 'trk.email', 'shim.gif'])


EXPORT_PATH = os.path.join(CFG_PATH, 'export')
os.makedirs(EXPORT_PATH, exist_ok=True)


AT_CONFIG = {}
if AIRTABLE:
    AIRTABLE_CFG = os.path.join(CFG_PATH, 'airtable.json')
    with open(AIRTABLE_CFG, "r") as jsonfile:
        AT_CONFIG = json.load(jsonfile)
    atThreads = airtable.Airtable(AT_CONFIG['base_id'], 'Threads', api_key=AT_CONFIG['api_key'])
    atLabels = airtable.Airtable(AT_CONFIG['base_id'], 'Labels', api_key=AT_CONFIG['api_key'])
    atMessages = airtable.Airtable(AT_CONFIG['base_id'], 'Messages', api_key=AT_CONFIG['api_key'])
    atEmails = airtable.Airtable(AT_CONFIG['base_id'], 'Emails', api_key=AT_CONFIG['api_key'])

if DROPBOX:
    DROPBOX_CFG  = os.path.join(CFG_PATH, 'dropbox.json')

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


