# -*- coding: utf-8 -*-
import os

from .threads import GmailThread
from .messages import GmailMessage

from gmail_export import EXPORT_PATH
import gmail_export.api as api


class GmailLabel(object):
    def __init__(self, id, name, selected=False):
        self.api = api.GmailAPI()
        self.id = id
        self.name = name
        self.selected = selected

    def __str__(self):
        return self.name

    def __repr__(self):
        if not getattr(self,'atId',None):
            return f"GmailLabel(id='{self.id}', name='{self.name}', selected={self.selected})"
        else:
            return f"GmailLabel(id='{self.id}', name='{self.name}', atId={self.atId}, selected={self.selected})"

    def populate(self, exporter):
        print(f"\n> Label {self.id}: \"{self.name}\"")
        # labels don't have export path by default because we get that interactively
        # init the label path with the value of self.export_root retrieved from the CLI
        self.export_path = os.path.join(exporter.export_path, self.name)
        # get the label messages for me
        self.messageIds = self
        for idx, messageId in enumerate(self.messageIds):
            threadId = self.threadIds[idx]
            if not threadId in exporter.threads:
                thread = GmailThread(threadId)
                exporter.threads[threadId] = thread
            else:
                thread = exporter.threads[threadId]
            if not messageId in exporter.messages:
                exporter.messages[messageId] = GmailMessage(messageId, thread, self, exporter)
                exporter.messages[messageId].meta = messageId
            else:
                exporter.messages[messageId].labels.append(self)

    def export(self, exporter):
        thread = None
        os.makedirs(self.export_path,exist_ok=True)
        print(f"  > Path: {exporter.path}")
        for idx, messageId in enumerate(self.messageIds):
            # message = exporter.messages[messageId]
            if not exporter.messages[messageId].thread is thread:
                exporter.messages[messageId].thread.populate(exporter)
                exporter.path = os.path.join(self.export_path, exporter.messages[messageId].thread.name)
                os.makedirs(exporter.path,exist_ok=True)
                print(f"      > Path: {exporter.path}")
                exporter.messages[messageId].populate(exporter)
                exporter.messages[messageId].export(exporter)
            thread = getattr(exporter.messages[messageId], "thread", exporter.threads[self.threadIds[idx]])

    @property
    def messageIds(self):
        return getattr(self, '_messageIds', {})

    @messageIds.setter
    def messageIds(self, label):
        self._messageIds, self.threadIds = self.api.get_id_list_for_label(label)

    # @property
    # def threads(self):
    #     return getattr(self, '_threads', [])

    # @threads.setter
    # def threads(self, thread_list=[]):
    #     self._threads=thread_list
    #     if self._threads:
    #         if not [thread for thread in self._threads if thread.id==threadId]:
    #             self._threads.append(GmailThread(threadId))

    def add_thread(self, thread):
        if self.threads:
            if not [t for t in self.threads if t.id==thread.id]:
                self.threads.append(thread)
            else:
                return next((t for t in self.threads if t.id == thread.id), None)
        else:
            self.threads.append(thread)
        return thread
    
