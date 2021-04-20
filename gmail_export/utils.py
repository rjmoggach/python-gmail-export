# -*- coding: utf-8 -*-
import os
from email.utils import parseaddr
import shutil
import string
import pendulum
from email.header import Header, decode_header, make_header
from ratelimit import limits, sleep_and_retry


from . import TIMEZONE

def can_url_fetch(src):
    from urllib.error import URLError, HTTPError
    from urllib.request import Request, urlopen
    try:
        req = Request(src)
        urlopen(req)
    except HTTPError:
        return False
    except URLError:
        return False
    except ValueError:
        return False

    return True


def get_size_format(b, factor=1024, suffix="B"):
    """
    Scale bytes to its proper byte format
    e.g:
        1253656 => '1.20MB'
        1253656678 => '1.17GB'
    """
    for unit in ["", "K", "M", "G", "T", "P", "E", "Z"]:
        if b < factor:
            return f"{b:.2f}{unit}{suffix}"
        b /= factor
    return f"{b:.2f}Y{suffix}"


def cleanSimple(text):
    # clean text for creating a folder
    return ''.join(c if c.isalnum() else "_" for c in text)


def clean(text):
    valid_chars = f"-_.() ' à â ç è é ê î ô ù û  {string.ascii_letters} {string.digits}"
    valid_name = ''.join(ch for ch in text if ch in valid_chars)
    valid_name = valid_name.replace(' ','_').replace('__','_').strip(",._-")
    if valid_name.startswith('Re_'):
        return valid_name[3:]
    else:
        return valid_name


def parseaddr_unicode(addr) -> (str, str):
    """Like parseaddr but return name in unicode instead of in RFC 2047 format
    '=?UTF-8?B?TmjGoW4gTmd1eeG7hW4=?= <abcd@gmail.com>' -> ('Nhơn Nguyễn', "abcd@gmail.com")
    """
    name, email = parseaddr(addr)
    email = email.strip().lower()
    if name:
        name = name.strip()
        decoded_string, charset = decode_header(name)[0]
        if charset is not None:
            try:
                name = decoded_string.decode(charset)
            except UnicodeDecodeError:
                LOG.warning("Cannot decode addr name %s", name)
                name = ""
        else:
            name = decoded_string
    return name, email


def recursive_overwrite(src, dest, ignore=None):
    # https://stackoverflow.com/questions/12683834/how-to-copy-directory-recursively-in-python-and-overwrite-all
    if os.path.isdir(src):
        if not os.path.isdir(dest):
            os.makedirs(dest)
        files = os.listdir(src)
        if ignore is not None:
            ignored = ignore(src, files)
        else:
            ignored = set()
        for f in files:
            if f not in ignored:
                recursive_overwrite(os.path.join(src, f), 
                                    os.path.join(dest, f), 
                                    ignore)
    else:
        shutil.copyfile(src, dest)


def get_unique_filename(filename):
    # From here: http://stackoverflow.com/q/183480/27641
    counter = 1
    file_name_parts = os.path.splitext(filename)
    while os.path.isfile(filename):
        filename = f'{file_name_parts[0]}_{counter:03}{file_name_parts[1]}'
        counter += 1
    return filename


def get_datetime(internalDate=-1,timezone=TIMEZONE):
    return pendulum.from_timestamp(int(internalDate)/1000.0, tz=timezone)


html_escape_table = {
    "&": "&amp;",
    '"': "&quot;",
    "'": "&apos;",
    ">": "&gt;",
    "<": "&lt;",
}

def html_escape(text):
    """Produce entities within text."""
    return "".join(html_escape_table.get(c,c) for c in text)


# 30 calls per minute
CALLS = 5
RATE_LIMIT = 1

@sleep_and_retry
@limits(calls=CALLS, period=RATE_LIMIT)
def check_limit():
     ''' Empty function just to check for calls to API '''
     return