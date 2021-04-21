# -*- coding: utf-8 -*-
import os
import re
import functools
import base64
import html
import email
from email.utils import parseaddr
import magic
import pendulum
from subprocess import Popen, PIPE
from jinja2 import Environment, PackageLoader, select_autoescape
from bs4 import BeautifulSoup, NavigableString, Tag
from rfc6266_parser import parse_headers, build_header

from gmail_export import WKHTMLTOPDF_EXTERNAL_COMMAND, WKHTMLTOPDF_ERRORS_IGNORE, IMAGE_LOAD_BLACKLIST, FatalException
from gmail_export.utils import clean, html_escape, can_url_fetch
import gmail_export.api as api

env = Environment(
    loader=PackageLoader('gmail_export','templates'),
    autoescape=select_autoescape([ 'xml'])
)

class GmailMessage(object):
    def __init__(self, id, thread, label, exporter=None):
        self.api = api.GmailAPI()
        self.id = id
        self.labels = [label]
        self.thread = thread
        self.threadId = thread.id
        self.exporter = exporter

        # self.msg_dt, self.subject = self.get_name_parts()

    def __str__(self):
        return self.id

    def __repr__(self):
        if getattr(self, 'headers', None) is None:
            if not getattr(self,'atId',None):
                return f"GmailMessage(id='{self.id}', headers=<multiple>)"
            else:
                return f"GmailMessage(id='{self.id}', headers=<multiple>, atId={self.atId})"
        else:
            if not getattr(self,'atId',None):
                return f"GmailMessage(id='{self.id}')"
            else:
                return f"GmailMessage(id='{self.id}', atId={self.atId})"

    @property
    def meta(self):
        return getattr(self,'_meta',{})

    @meta.setter
    def meta(self, id):
        _meta = {}
        response = self.api.get_message_meta(id)
        headers = response['payload']['headers']
        subject = [header['value'] for header in headers if header['name']=="Subject"]
        if subject == []:
            subject = ['NO SUBJECT']
        internalDate = response['internalDate']
        subject = subject[0]
        _meta = {
            'headers': headers,
            'subject': subject,
            'internalDate': internalDate
        }
        self._meta = _meta

    @property
    def msg(self):
        return getattr(self, '_msg', None)

    @property
    def msg_dt(self):
        return self.exporter.get_datetime(self.internalDate).format('YYYY-MM-DD-THHmmss')

    @property
    def dt(self):
        return self.exporter.get_datetime(self.internalDate)

    @property
    def subject(self):
        return getattr(self, '_subject', None)

    @property
    def name(self):
        return f'{self.msg_dt}-{clean(self.subject)[:128]}'

    @property
    def internalDate(self):
        return self.meta['internalDate']

    @property
    def subject(self):
        return self.meta['subject']

    @property
    def headers(self):
        _headers=self.meta['headers']
        output = {
            'Subject': None,
            'From': None,
            'To': [],
            'Date': None,
            'Cc': []
        }
        for k,v in output.items():
            for header in _headers:
                name = header['name']
                value = header['value']
                if header['name'] == k:
                    if name in ['Date','Subject']:
                        output[k] = value
                    elif name in ['From','To','Cc']:
                        if ',' in value:
                            value = value.split(',')
                            value = [email.strip() for email in value]
                        else:
                            value = [value]
                        output[k] = value
        return output

    def populate(self, exporter):
        self.get_mime_msg()
        print(f"        Message {self.id}: {self.name}")

    def export(self, exporter):
        if 'eml' in exporter.config['formats']:
            eml_name = f'{self.msg_dt}-Eml-{clean(self.subject)[:128]}.eml'
            self.export_eml(exporter.path, eml_name)
        if 'html' in exporter.config['formats']:
            html_name = f'{self.msg_dt}-Eml-{clean(self.subject)[:128]}.html'
            self.export_html(exporter.path, html_name)
        if 'pdf' in exporter.config['formats']:
            pdf_name = f'{self.msg_dt}-Eml-{clean(self.subject)[:128]}.pdf'
            self.export_pdf(exporter.path, pdf_name)
        if 'attachments' in exporter.config['formats']:
            att_name = f'{self.msg_dt}-EmlAtt'
            self.export_content(exporter.path, att_name, False)
        if 'inline' in exporter.config['formats']:
            inl_name = f'{self.msg_dt}-Inline'
            self.export_content(exporter.path, inl_name, True)

    def get_mime_msg(self):
        print(f"        Fetching mime msg", end="\r")
        # get entire message in RFC2822 formatted base64url encoded string to convert to .eml
        msg_raw = self.api.get_message_id(self.id)
        msg_bytes = base64.urlsafe_b64decode(msg_raw['raw'])
        mime_msg = email.message_from_bytes(msg_bytes)
        self._msg = mime_msg
        return mime_msg

    def get_message_body(self):
        part = self.get_part_by_content_type("text/html")
        if not part is None:
            return self.handle_html_message_body(part)
        part = self.get_part_by_content_type("text/plain")
        if not part is None:
            return self.handle_plain_message_body(part)
        raise FatalException("Email message has no body")

    def convert(self):
        self.meta = self.id
        try:
            body = self.get_message_body()
        except:
            body = ""
        body = self.clean_soup(body)
        self.attachments = self.find_attachments()
        content_disposition_list = [parse_headers(att[0]) for att in self.attachments]
        att_list = []
        for cd in content_disposition_list:
            att_list.append({'filename': cd.filename_unsafe})
        template = env.get_template('email.html')
        rendered = template.render(headers=self.headers, body=body, attachments=att_list)
        return rendered

    def clean_soup(self, payload):
        soup = BeautifulSoup(payload, "html5lib")
        soup.html.hidden = True
        soup.body.hidden = True
        soup.head.hidden = True
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
                    font['face']='"Helvetica Neue", "Segoe UI Emoji", "Noto Color Emoji", "Apple Color Emoji", Helvetica,  Arial, sans-serif',
            if font.has_attr('color'):
                color = font['color']
                if color =="#000000": del font['color']
            if font.has_attr('style'):
                style = font['style']
                if style == "background-color:rgb(255,255,255)": del font['style']
        return str(soup.prettify('utf-8').decode('utf-8'))


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

    def export_eml(self, export_path, eml_name):
        write_path = os.path.join(export_path, eml_name)
        try:
            with open(write_path, 'w') as outfile:
                gen = email.generator.Generator(outfile)
                gen.flatten(self.msg)
            print(f"        > Saved eml:  {eml_name}")
            return write_path
        except:
            return None

    def export_html(self, export_path, html_name):
        output = self.convert().encode('utf-8')
        write_path = os.path.join(export_path, html_name)
        with open(write_path, 'wb') as outfile:
            outfile.write(output)
            print(f"        > Saved html: {html_name}")
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
        print(f"        > Saved pdf:  {pdf_name}")
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
            filename = parse_headers(content_disposition).filename_unsafe
            nm, ex = os.path.splitext(filename)
            content_name = f'{name}-{nm[:128]}{ex}'
            write_path = os.path.join(export_path, content_name)
            with open(write_path, 'wb') as outfile:
                data = part.get_payload(decode=True)
                outfile.write(data)
            str_inline="inline " if inline else ""
            print(f"          > Saved {str_inline}content: {content_name}")
        return True

    def find_attachments(self, inline=False):
        """
        Return a tuple of parsed content-disposition dict, message object for each attachment found
        """
        attachments = []
        for part in self.msg.walk():
            if 'content-disposition' not in part: continue
            cd_part="".join(part['content-disposition'].splitlines())
            cd_part=cd_part.replace('\t','')
            cd_part_list = re.split(''';(?=(?:[^'"]|'[^']*'|"[^"]*")*$)''', cd_part)
            prefixes = ['attach','inline','filenam']
            cd_part_list = [i.strip() for i in cd_part_list]
            cd_part = ";".join(cd_part_list)
            try:
                content_disposition = parse_headers(cd_part)
            except ValueError:
                content_disposition = parse_headers(cd_part, relaxed=True)
            disposition = content_disposition.disposition
            if not disposition in ['attachment', 'inline']:
                continue
            if not inline:
                if disposition == 'attachment':
                    try: parsed = build_header(content_disposition.filename_unsafe)
                    except TypeError: continue
                    attachments.append((parsed, part))
            elif inline:
                if disposition == 'inline':
                    try: parsed = build_header(content_disposition.filename_unsafe)
                    except TypeError: continue
                    attachments.append((parsed, part))
        return attachments
