# -*- coding: utf-8 -*-
import os

import gmail_export.api as api
from gmail_export.utils import  clean


class GmailThread(object):
    def __init__(self, id):
        self.api = api.GmailAPI()
        self.id = id
    
    def __repr__(self):
        if not getattr(self, '_name', None) is None:
            if not getattr(self,'atId',None):
                return f"GmailThread(id='{self.id}', name='{self.name}')"
            else:
                return f"GmailThread(id='{self.id}', name='{self.name}', atId={self.atId})"
        else:
            return f"GmailThread(id='{self.id}')"

    def populate(self, export):
        self.generate_name(export)
        print(f"    > Thread {self.id}: \"{self.name}\"")

    @property
    def name(self):
        return getattr(self, '_name', self.id)

    def generate_name(self, export):
        response = self.api.get_thread(self.id)
        if 'messages' in response:
            msg0 = response['messages'][0]
            headers = msg0["payload"]["headers"]
            internalDate = msg0["internalDate"]
            self.dt = export.get_datetime(internalDate)
            thread_dt = self.dt.format('YYYY-MM-DD_THHmmss')
            subject = [header['value'] for header in headers if header["name"]=="Subject"]
            if subject == []:
                subject = ["(no subject)"]
            self.subject = subject[0]
            thread_name = f'{thread_dt}-{clean(self.subject)}'
        else:
            thread_name = thread_id
        self._name = thread_name
