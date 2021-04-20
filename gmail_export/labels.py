# -*- coding: utf-8 -*-
import os

from .threads import GmailThread
from .messages import GmailMessage
from .api import GmailAPI
from . import EXPORT_PATH


class GmailLabel(object):
    def __init__(self, id, name, export_path=None, messages=[]):
        self.api = GmailAPI()
        self.id = id
        self.name = name
        self.export_path = export_path
        self.messages = messages
        self.threads = {}

    def get_messages(self):
        messages = []
        response = self.api.get_messages_for_label(self.id)
        if 'messages' in response:
            messages = response['messages']
        msg="Fetching"
        while 'nextPageToken' in response:
            msg += '.'
            print(msg, end='\r')
            page_token = response['nextPageToken']
            response = self.api.get_messages_for_label(self.id, page_token)
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
        self.export_path = os.path.join(export_root, self.name)
        return self.export_path

