# -*- coding: utf-8 -*-
from gmail_export.threads import GmailThread
import os
from googleapiclient.discovery import build
from google_auth_oauthlib.flow import InstalledAppFlow
from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials

from . import TOKEN_PATH, CREDENTIALS_PATH, SCOPES, AIRTABLE, AT_CONFIG
from .labels import GmailLabel

if AIRTABLE:
    import airtable


def sort_lists_by_list(sorter, sortee):
    zipped_lists = zip(sorter, sortee)
    sorted_pairs = sorted(zipped_lists)
    tuples = zip(*sorted_pairs)
    sorter, sortee = [list(tuple) for tuple in tuples]
    return sorter, sortee


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
    
    def get_labels(self, all=False):
        results = []
        response = self.service.users().labels().list(userId='me').execute()
        response_labels = response['labels']
        if all:
            labels = sorted([label for label in response_labels], key=lambda k: k['name'].lower())
        else:
            labels = sorted([label for label in response_labels if label['type']=="user"], key=lambda k: k['name'].lower())
        for label in labels:
            new_label = GmailLabel(label['id'], label['name'])
            results.append(new_label)
        return results

    def get_id_list_for_label(self, label, page_token=None):
        messageIds = []
        threadIds = []
        response = self.service.users().messages().list(userId="me", labelIds=label.id, q=None, pageToken=page_token, maxResults=None, includeSpamTrash=None).execute()
        if 'messages' in response:
            messages = response['messages']
        print_msg = "  > Fetching message ids."
        while 'nextPageToken' in response:
            print_msg += "."
            print(print_msg, end='\r')
            page_token = response['nextPageToken']
            response = self.service.users().messages().list(userId="me", labelIds=label.id, q=None, pageToken=page_token, maxResults=None, includeSpamTrash=None).execute()
            messages.extend(response['messages'])
        print(print_msg)
        print(f"    Fetched {len(messages)} messages.")
        messageIds=[message['id'] for message in messages]
        threadIds=[message['threadId'] for message in messages]
        threadIds, messageIds = sort_lists_by_list(threadIds, messageIds)
        return messageIds, threadIds
# list1 = ["c", "b", "d", "a"]
# list2 = [2, 3, 1, 4]

# zipped_lists = zip(list1, list2)
# sorted_pairs = sorted(zipped_lists)

# tuples = zip(*sorted_pairs)
# list1, list2 = [ list(tuple) for tuple in  tuples]

# print(list1)
# OUTPUT
# ['a', 'b', 'c', 'd']
# print(list2)
# OUTPUT
# [4, 3, 2, 1]
    def get_messages_for_label(self, label, page_token=None):
        results = {}
        threads = {}
        response = self.service.users().messages().list(userId="me", labelIds=label.id, q=None, pageToken=page_token, maxResults=None, includeSpamTrash=None).execute()
        if 'messages' in response:
            messages = response['messages']
        print_msg = "Fetching"
        while 'nextPageToken' in response:
            print_msg += "."
            print(print_msg, end='\r')
            page_token = response['nextPageToken']
            response = self.service.users().messages().list(userId="me", labelIds=label.id, q=None, pageToken=page_token, maxResults=None, includeSpamTrash=None).execute()
            messages.extend(response['messages'])
        print(print_msg)
        j=1
        for message in messages:
            print_msg = f"Reading message {j} of {len(messages)}."
            print(print_msg, end='\r')
            j+=1
            threadId = message['threadId']
            thread = label.add_thread(GmailThread(threadId))
            results[message['id']] = GmailMessage(message['id'], label, thread)
        return results

    def get_message_id(self, id):
        return self.service.users().messages().get(userId="me", id=id, format="raw", metadataHeaders=None).execute()
    
    def get_message_meta(self, id):
        return self.service.users().messages().get(userId="me", id=id, format="metadata", metadataHeaders=["Subject","From","To","Date","Cc","Bcc"]).execute()
    
    def get_thread(self, id):
        return self.service.users().threads().get(userId="me", id=id, format="full").execute()


class AirtableAPI(GmailAPI):
    def __init__(self):
        super().__init__(self)
        self.threads = self.get_table_api_pointer("Threads")
        self.labels = self.get_table_api_pointer("Labels")
        self.messages = self.get_table_api_pointer("Messages")
        self.emails = self.get_table_api_pointer("Emails")

    def get_table_api_pointer(self, table_name, base_id=AT_CONFIG['base_id'], api_key=AT_CONFIG['api_key']):
        return airtable.Airtable(base_id, table_name, api_key)



