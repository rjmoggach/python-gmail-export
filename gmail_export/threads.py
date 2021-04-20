# -*- coding: utf-8 -*-
import os

from . import EXPORT_PATH
from .api import GmailAPI
from .utils import get_datetime, clean


class GmailThread(object):
    def __init__(self, id, export_root=EXPORT_PATH):
        self.service = GmailAPI().service
        self.id = id
        self.export_root=export_root
        self.name = None
    
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
