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

    def populate(self, export):
        print(f"\n> Label {self.id}: \"{self.name}\"")
        # labels don't have export path by default because we get that interactively
        # init the label path with the value of self.export_root retrieved from the CLI
        self.export_path = os.path.join(export.export_path, self.name)
        # get the label messages for me
        self.messageIds = self
        for idx, messageId in enumerate(self.messageIds):
            threadId = self.threadIds[idx]
            if not threadId in export.threads:
                thread = GmailThread(threadId)
                export.threads[threadId] = thread
            else:
                thread = export.threads[threadId]
            if not messageId in export.messages:
                export.messages[messageId] = GmailMessage(messageId, thread, self)
            else:
                export.messages[messageId].labels.append(self)
        # export.messages.extend(self.messages)
        # message_count = len(self.messages)
        # i=1
        # for message in self.messages:
        #     print(f"\n> Message {i} of {message_count} for label '{self.name}'.")
        #     i+=1
        #     message.export(config)

    def export(self, export):
        thread = None
        os.makedirs(self.export_path,exist_ok=True)
        print(f"  > Path: {export.path}")
        for idx, messageId in enumerate(self.messageIds):
            message = export.messages[messageId]
            if not message.thread is thread:
                message.thread.populate(export)
                export.path = os.path.join(self.export_path, message.thread.name)
                os.makedirs(export.path,exist_ok=True)
                print(f"      > Path: {export.path}")
                message.populate(export)
                message.export(export)
            thread = getattr(message, "thread", export.threads[self.threadIds[idx]])

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
    
