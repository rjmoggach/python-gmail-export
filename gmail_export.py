# -*- coding: utf-8 -*-
"""
* GMail Export Ver 0.1.0
* This script allows the user to export gmail to various formats.
"""

__version__ = '0.1.0'

import os
import re
import sys
import mimetypes
import argparse
import functools
from pathlib import Path
import base64
import html
import email
from email.utils import parseaddr
import shutil
import string
import magic
import pendulum
from googleapiclient.discovery import build
from google_auth_oauthlib.flow import InstalledAppFlow
from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from PyInquirer import Token, ValidationError, Validator, print_json, prompt, style_from_dict
from pprint import pprint
from subprocess import Popen, PIPE
from jinja2 import Environment, PackageLoader, select_autoescape
from bs4 import BeautifulSoup, NavigableString, Tag
from email.header import Header, decode_header, make_header
from xhtml2pdf import pisa


DEBUG = True
CFG_PATH = os.path.join(str(Path.home()), '.gmail_export')
TOKEN_PATH = os.path.join(CFG_PATH, 'token.json')
CREDENTIALS_PATH = os.path.join(CFG_PATH, 'credentials.json')
EXPORT_PATH = os.path.join(CFG_PATH, 'export')
TIMEZONE='America/Toronto'
os.makedirs(EXPORT_PATH, exist_ok=True)
IMAGE_LOAD_BLACKLIST = frozenset(['emltrk.com', 'trk.email', 'shim.gif'])
# # If modifying these scopes, delete the file token.json.
SCOPES = ['https://www.googleapis.com/auth/gmail.readonly']
STYLE = style_from_dict({
    Token.QuestionMark: '#fac731 bold',
    Token.Answer: '#4688f1 bold',
    Token.Instruction: '',  # default
    Token.Separator: '#cc5454',
    Token.Selected: '#0abf5b',  # default
    Token.Pointer: '#673ab7 bold',
    Token.Question: '',
})
WKHTMLTOPDF_EXTERNAL_COMMAND = 'wkhtmltopdf'
WKHTMLTOPDF_ERRORS_IGNORE = frozenset(
    [r'QFont::setPixelSize: Pixel size <= 0 \(0\)',
     r'Invalid SOS parameters for sequential JPEG',
     r'libpng warning: Out of place sRGB chunk',
     r'Exit with code 1 due to network error: ContentNotFoundError',
     r'Exit with code 1 due to network error: UnknownContentError',
     r'QPainter::begin(): Returned false\r\nExit with code 1'])

env = Environment(
    loader=PackageLoader('gmail_export','templates'),
    autoescape=select_autoescape([ 'xml'])
)

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

class GmailAPI(object):
    def __init__(self, token_path=TOKEN_PATH, credentials_path=CREDENTIALS_PATH, scopes=SCOPES):
        self.credentials = None
        self.token_path = token_path
        self.credentials_path = credentials_path
        self.scopes = scopes
        self.credentials = self.get_credentials()
        self.service = self.get_service()

    def get_credentials(self):
        if os.path.exists(self.token_path):
            credentials = Credentials.from_authorized_user_file(self.token_path, scopes=self.scopes)
        if not credentials or not credentials.valid:
            if credentials and credentials.expired and credentials.refresh_token:
                credentials.refresh(Request())
            else:
                flow = InstalledAppFlow.from_client_secrets_file(self.credentials_path, self.scopes)
                credentials = flow.run_local_server(port=0)
            # Save the credentials for the next run
            with open(self.token_path, 'w') as token:
                token.write(credentials.to_json())
        return credentials
    
    def get_service(self):
        return build('gmail', 'v1', credentials=self.credentials)
    

class GmailMessage(object):
    def __init__(self, id, thread, msg=None):
        self.service = GmailAPI().service
        self.id = id
        self.msg = msg
        # self.msg_dt, self.subject = self.get_name_parts()
        self.threadId = thread.id
        self.thread = thread

    def get_message(self):
        # get entire message in RFC2822 formatted base64url encoded string to convert to .eml
        msg_raw = self.service.users().messages().get(userId="me", id=self.id, format="raw", metadataHeaders=None).execute()
        msg_bytes = base64.urlsafe_b64decode(msg_raw['raw'])
        # msg_str = base64.urlsafe_b64decode(msg_raw['raw'].encode('UTF-8'))
        mime_msg = email.message_from_bytes(msg_bytes)
        # mime_msg = email.message_from_string(msg_str.decode())
        self.msg = mime_msg
        return mime_msg

    def get_name_parts(self):
        # get message metadata (specifically Subject)
        self.meta = self.service.users().messages().get(userId="me", id=self.id, format="metadata",metadataHeaders=["Subject","From","To","Date","Cc","Bcc"]).execute()
        headers = self.meta['payload']['headers']
        subject = [header['value'] for header in headers if header['name']=="Subject"]
        if subject == []:
            subject = ['NO SUBJECT']
        internalDate = self.meta['internalDate']
        msg_dt = get_datetime(internalDate).format('YYYY-MM-DD-THHmmss')
        subject = clean(subject[0])
        return msg_dt, subject

    def convert(self):
        body = self.get_message_body()
        # body = self.remove_invalid_urls(body)
        headers = self.get_headers()
        template = env.get_template('email.html')
        rendered = template.render(headers=headers, body=body)
        return rendered

    def remove_invalid_urls(self, payload):
        soup = BeautifulSoup(payload, "html5lib")
        soup.html.hidden = True
        soup.body.hidden = True
        soup.head.hidden = True
        # print(soup.prettify())
        images = soup.findAll('img')
        for img in images:
            if img.has_attr('src'):
                src = img['src']
                lower_src = src.lower()
                if lower_src == 'broken':
                    del img['src']
                elif not lower_src.startswith('data'):
                    found_blacklist = False
                    for image_load_blacklist_item in IMAGE_LOAD_BLACKLIST:
                        if image_load_blacklist_item in lower_src:
                            found_blacklist = True
                    if not found_blacklist:
                        if not can_url_fetch(src):
                            del img['src']
                    else:
                        del img['src']
        for br in soup.findAll("br"):
            while isinstance(br.next_sibling, Tag) and br.next_sibling.name == 'br':
                br.next_sibling.extract()
        for meta in soup.findAll("meta"):
            meta.extract()
        for font in soup.findAll('font'):
            if font.has_attr('face'):
                face = font['face']
                if face == "tahoma, sans-serif":
                    font['face']='"Helvetica Neue","Noto Color Emoji", "Apple Color Emoji", "Segoe UI Emoji",Helvetica,Arial,sans-serif',
        # return str(soup.encode('utf-8').decode('utf-8'))
        return str(soup.prettify('utf-8').decode('utf-8'))

    def get_headers(self):
        payload_headers=self.meta['payload']['headers']
        output = {
            'Subject': None,
            'From': None,
            'To': [],
            'Date': None,
            'Cc': []
        }
        for k,v in output.items():
            for header in payload_headers:
                name = header['name']
                value = header['value']
                if header['name'] == k:
                    if name in ['Date','Subject', 'From']:
                        output[k] = html_escape(value)
                    elif name in ['To','Cc']:
                        if ',' in value:
                            value = value.split(',')
                            value = [html_escape(email.strip()) for email in value]
                        else:
                            value = [html_escape(value)]
                        output[k] = value
        return output

    def get_part_by_content_type(self, content_type):
        for part in self.msg.walk():
            if part.get_content_type() == content_type:
                return part
        return None
    
    def get_part_by_content_id(self, content_id):
        for part in self.msg.walk():
            if part['Content-ID'] in (content_id, '<' + content_id + '>'):
                return part
        return None

    def get_part_by_content_type_name(self, content_type_name):
        for part in self.msg.walk():
            part_content_type = part.get_param('name', header="Content-Type")
            if part_content_type == content_type_name:
                return part
        return None

    def get_mime_type(self, buffer_data):
        # pylint: disable=no-member
        if 'from_buffer' in dir(magic):
            mime_type = magic.from_buffer(buffer_data, mime=True)
            if type(mime_type) is not str:
                # Older versions of python-magic seem to output bytes for the
                # mime_type name. As of Python 3.6+, it seems to be outputting
                # strings directly.
                mime_type = str(
                    magic.from_buffer(buffer_data, mime=True), 'utf-8')
        else:
            m_handle = magic.open(magic.MAGIC_MIME_TYPE)
            m_handle.load()
            mime_type = m_handle.buffer(buffer_data)
        return mime_type

    def handle_html_message_body(self, part):
        payload = part.get_payload(decode=True)
        charset = part.get_content_charset()
        if not charset: charset = 'utf-8'
        try:
            payload = re.sub(r'cid:([\w_@.-]+)', functools.partial(self.replace_cid), str(payload, charset))
        except UnicodeDecodeError:
            charset = 'latin1'
            try:
                payload = re.sub(r'cid:([\w_@.-]+)', functools.partial(self.replace_cid), str(payload, charset))
            except UnicodeDecodeError:
                pass
                try:
                    payload = re.sub(r'cid:([\w_@.-]+)', functools.partial(self.replace_cid), str(payload, charset))
                except:
                    pass
        return payload

    def handle_plain_message_body(self, part):
        if part['Content-Transfer-Encoding'] == '8bit':
            payload = part.get_payload(decode=False)
            assert isinstance(payload, str)
        else:
            payload = part.get_payload(decode=True)
            assert isinstance(payload, bytes)
            charset = part.get_content_charset()
            if not charset:
                charset = 'utf-8'
            payload = str(payload, charset)
            payload = html.escape(payload)
            payload = f"<pre>{payload}</pre>"
        return payload

    def get_message_body(self):
        part = self.get_part_by_content_type("text/html")
        if not part is None:
            return self.handle_html_message_body(part)
        part = self.get_part_by_content_type("text/plain")
        if not part is None:
            return self.handle_plain_message_body(part)
        raise FatalException("Email message has no body")

    def replace_cid(self, matchobj):
        cid = matchobj.group(1)
        image_part = self.get_part_by_content_id(cid)

        if image_part is None:
            image_part = self.get_part_by_content_type_name(cid)

        if image_part is not None:
            assert image_part['Content-Transfer-Encoding'] == 'base64'
            image_base64 = image_part.get_payload(decode=False)
            image_base64 = re.sub("[\r\n\t]", "", image_base64)
            image_decoded = image_part.get_payload(decode=True)
            mime_type = self.get_mime_type(image_decoded)
            return "data:" + mime_type + ";base64," + image_base64
        # else:
        #     raise FatalException(
        #         "Could not find image cid " + cid + " in email content.")
        return ""

    def export(self, eml=True, html5=False, pdf=False, att=False, inl=False):
        thread_path = self.thread.get_export_path(self.thread.export_root)
        os.makedirs(thread_path, exist_ok=True)
        print("> THREAD PATH: ", thread_path)
        self.msg_dt, self.subject = self.get_name_parts()
        self.msg = self.get_message()
        if eml:
            eml_name = f'{self.msg_dt}-Eml-{self.subject}.eml'
            self.export_eml(thread_path, eml_name)
        if html5:
            html_name = f'{self.msg_dt}-Eml-{self.subject}.html'
            self.export_html(thread_path, html_name)
        if pdf:
            pdf_name = f'{self.msg_dt}-Eml-{self.subject}.pdf'
            self.export_pdf(thread_path, pdf_name)
        if att:
            att_name = f'{self.msg_dt}-EmlAtt'
            self.export_content(thread_path, att_name, False)
        if inl:
            inl_name = f'{self.msg_dt}-Inline'
            self.export_content(thread_path, inl_name, True)

    def export_eml(self, export_path, eml_name):
        write_path = os.path.join(export_path, eml_name)
        try:
            with open(write_path, 'w') as outfile:
                gen = email.generator.Generator(outfile)
                gen.flatten(self.msg)
            print(f"  > SAVED EML ID: {self.id} NAME: {eml_name}")
            return write_path
        except:
            return None

    def export_html(self, export_path, html_name):
        output = self.convert()
        write_path = os.path.join(export_path, html_name)
        with open(write_path, 'wb') as outfile:
            outfile.write(output.encode('utf-8'))
        print(f"  > SAVED HTML ID: {self.id} NAME: {html_name}")
        return write_path

    def export_pdf(self, export_path, pdf_name):
        output = self.convert().encode('utf-8')
        write_path = os.path.join(export_path, pdf_name)
        wkh2p_process = Popen([WKHTMLTOPDF_EXTERNAL_COMMAND, '-q',
                               '--load-error-handling', 'ignore',
                               '--load-media-error-handling', 'ignore',
                               '--encoding', 'utf-8', '-s', 'Letter',
                               '-', write_path],
                              stdin=PIPE, stdout=PIPE, stderr=PIPE)
        output, error = wkh2p_process.communicate(input=output)
        ret_code = wkh2p_process.returncode
        assert output == b''
        self.process_errors(ret_code, error)
        print(f"  > SAVED PDF ID: {self.id} NAME: {pdf_name}")
        return write_path

    def process_errors(self, ret_code, error):
        stripped_error = str(error, 'utf-8')
        # suppress certain errors
        for error_pattern in WKHTMLTOPDF_ERRORS_IGNORE:
            (stripped_error, _) = re.subn(error_pattern, '', stripped_error)

        original_error = str(error, 'utf-8').rstrip()
        stripped_error = stripped_error.rstrip()

        if ret_code > 0 and original_error == '':
            raise FatalException("wkhtmltopdf failed with exit code " +
                                 str(ret_code) +
                                 ", no error output.")
        elif ret_code > 0 and stripped_error != '':
            raise FatalException("wkhtmltopdf failed with exit code " +
                                 str(ret_code) +
                                 ", stripped error: " + stripped_error)
        elif stripped_error != '':
            print("wkhtmltopdf exited with rc = 0 but produced \
                    unknown stripped error output " + stripped_error)

    def export_content(self, export_path, name, inline=False):
        attachments = self.find_attachments(inline)
        for content_disposition, part in attachments:
            filename = content_disposition['filename']
            content_name = f'{name}-{filename}'
            write_path = os.path.join(export_path, content_name)
            with open(write_path, 'wb') as outfile:
                data = part.get_payload(decode=True)
                outfile.write(data)
            print(f"    > SAVED CONTENT: {content_name}")
        return True

    def find_attachments(self, inline=False):
        """
        Return a tuple of parsed content-disposition dict, message object for each attachment found
        """
        attachments = []
        for part in self.msg.walk():
            if 'content-disposition' not in part:
                continue
            content_disposition = part['content-disposition'].split(';')
            content_disposition = [i.strip() for i in content_disposition]
            content = content_disposition[0].lower()
            if not content in ['attachment', 'inline']:
                continue
            parsed = {}
            for kv in content_disposition[1:]:
                key, _, val = kv.partition('=')
                if val.startswith('"'): val = val.strip('"')
                elif val.startswith("'"): val = val.strip("'")
                parsed[key] = val
            if not inline:
                if content == 'attachment':
                    attachments.append((parsed, part))
            elif inline:
                if content == 'inline':
                    attachments.append((parsed, part))
        return attachments


class GmailLabel(object):
    def __init__(self, id, name, export_path=None, messages=[]):
        self.service = GmailAPI().service
        self.id = id
        self.name = name
        self.export_path = export_path
        self.messages = messages
        self.threads = {}

    def get_messages(self):
        messages = []
        response = self.service.users().messages().list(userId="me", labelIds=self.id, q=None, pageToken=None, maxResults=None, includeSpamTrash=None).execute()
        if 'messages' in response:
            messages = response['messages']
        msg="Fetching"
        while 'nextPageToken' in response:
            msg += '.'
            print(msg, end='\r')
            page_token = response['nextPageToken']
            response = self.service.users().messages().list(userId="me", labelIds=self.id, q=None, pageToken=page_token, maxResults=None, includeSpamTrash=None).execute()
            messages.extend(response['messages'])
        print(msg)
        j=1
        for message in messages:
            msg = f"Reading message {j} of {len(messages)}."
            print(msg, end='\r')
            j+=1
            threadId = message['threadId']
            if not threadId in self.threads:
                new_thread = GmailThread(threadId, self.export_path)
                self.threads[threadId]= new_thread
            new_message = GmailMessage(message['id'],self.threads[threadId])
            self.messages.append(new_message)
        print(msg)
        return self.messages

    def get_export_path(self, export_root):
        return os.path.join(export_root, self.name)


class GmailThread(object):
    def __init__(self, id, export_root=EXPORT_PATH):
        self.service = GmailAPI().service
        self.id = id
        self.export_root=export_root
        self.name = None
    
    def get_datetime(self, internalDate=-1):
        return pendulum.from_timestamp(int(internalDate)/1000.0, tz=self.timezone)

    def get_name(self):
        messages = []
        response = self.service.users().threads().get(userId="me", id=self.id, format="full").execute()
        if 'messages' in response:
            msg0 = response['messages'][0]
            headers = msg0["payload"]["headers"]
            internalDate = msg0["internalDate"]
            thread_dt = get_datetime(internalDate).format('YYYY-MM-DD_THHmmss')
            subject = [header['value'] for header in headers if header["name"]=="Subject"]
            if subject == []:
                subject = ["(no subject)"]
            thread_name = f'{thread_dt}-{clean(subject[0])}'
        else:
            thread_name = self.id
        self.name = thread_name
        return thread_name

    def get_export_path(self, export_root):
        if not self.name: self.get_name()
        return os.path.join(export_root, self.name)


class GmailExport(object):
    def __init__(self, export_path=EXPORT_PATH):
        self.service = GmailAPI().service
        self.labels = []
        self.selected_labels = []
        self.threads = []
        self.export_path = export_path
        self.questions = self.get_questions()
        self.answers = self.get_answers()
        if self.answers:
            self.export_path = self.answers['export_path']
            self.overwrite = self.answers['overwrite']
            self.timezone = self.answers['timezone']
            self.selected_labels = self.get_selected_labels()
        self.export()
    
    def get_datetime(self, internalDate=-1):
        return pendulum.from_timestamp(int(internalDate)/1000.0, tz=self.timezone)

    def get_questions(self):
        questions = []
        questions.append(self.get_export_path_question())
        questions.append(self.get_timezone_question())
        questions.append(self.get_label_question())
        questions.append(self.get_formats_question())
        questions.append(self.get_overwrite_question())
        return questions
    
    def get_answers(self):
        answers = prompt(self.get_questions(), style=STYLE)
        return answers

    def get_labels(self):
        labels = []
        results = self.service.users().labels().list(userId='me').execute()
        results_labels = results['labels']
        user_labels = sorted([label for label in results_labels if label['type']=="user"], key=lambda k: k['name'].lower())
        for label in user_labels:
            new_label = GmailLabel(label['id'], label['name'], os.path.join(self.export_path,label['name']))
            labels.append(new_label)
        return labels

    def get_label_question(self):
        self.labels = self.get_labels()
        choices = [{'name': label.name, 'value': {'name': label.name, 'id': label.id}} for label in self.labels]
        question = {
            'type': 'checkbox',
            'name': 'labels',
            'message': 'Select labels',
            'choices': choices,
            'validate': lambda answer: 'You must choose a label.' if len(answer) == 0 else True
        }
        return question
    
    def get_formats_question(self):
        choices = [
            {'name': "eml", 'checked': True },
            {'name': "html" },
            {'name': "pdf" },
            {'name': "attachments"},
            {'name': "inline"}
        ]
        question = {
            'type': 'checkbox',
            'name': 'formats',
            'message': 'Select file formats',
            'choices': choices,
            'validate': lambda answer: 'You must choose one.' if len(answer) == 0 else True
        }
        return question
    
    def get_export_path_question(self):
        question = {
            'type': 'input',
            'name': 'export_path',
            'message': 'Export path:',
            'default': self.export_path,
            'validate': lambda answer: 'Enter an existing path.' if not os.path.exists(answer) else True
        }
        return question

    def get_overwrite_question(self):
        question = {
            'type': 'confirm',
            'name': 'overwrite',
            'message': 'Overwrite',
            'default': True
        }
        return question

    def get_timezone_question(self):
        question = {
            'type': 'input',
            'name': 'timezone',
            'message': 'Timezone TZ name',
            'default': 'America/Toronto',
            'validate': lambda answer: 'Enter a valid timezone from https://en.wikipedia.org/wiki/List_of_tz_database_time_zones.' if not answer in pendulum.timezones else True
        }
        return question
        
    def get_selected_labels(self):
        selected_labels=[]
        for answer in self.answers['labels']:
            for label in self.labels:
                if label.id == answer['id']:
                    selected_labels.append(label)
        return selected_labels

    def export(self):
        for label in self.selected_labels:
            # get the label path
            label_export_path = label.get_export_path(self.export_path)
            # get the label messages
            messages = label.get_messages()
            print("RESULTS: ", len(messages), " Messages.")
            eml = True if 'eml' in self.answers['formats'] else False
            html5 = True if 'html' in self.answers['formats'] else False
            pdf = True if 'pdf' in self.answers['formats'] else False
            inl = True if 'inline' in self.answers['formats'] else False
            att = True if 'attachments' in self.answers['formats'] else False
            for message in messages:
                message.export(eml,html5,pdf,att,inl)


class FatalException(Exception):
    def __init__(self, value):
        Exception.__init__(self, value)
        self.value = value

    def __str__(self):
        return repr(self.value)


def main():
    export=GmailExport()


def parse_args():
    parser = argparse.ArgumentParser(description='This script will export your email!')
    parser.add_argument('-d','--dest',default=EXPORT_PATH, help='Destination - path to export to')


if __name__ == '__main__':
    main()