# -*- coding: utf-8 -*-
from gmail_export.threads import GmailThread
import html
import os
from googleapiclient.discovery import build
from google_auth_oauthlib.flow import InstalledAppFlow
from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from ratelimit import limits, sleep_and_retry

from email.utils import parseaddr


from gmail_export import TOKEN_PATH, CREDENTIALS_PATH, SCOPES, DROPBOX, AIRTABLE, AT_CONFIG
from gmail_export.utils import html_escape
from gmail_export.labels import GmailLabel
from gmail_export.emails import Email


if AIRTABLE:
    import airtable
if DROPBOX:
    import dropbox
    from dropbox.files import WriteMode
    from dropbox.exceptions import ApiError, AuthError


def sort_lists_by_list(sorter, sortee):
    zipped_lists = zip(sorter, sortee)
    sorted_pairs = sorted(zipped_lists)
    tuples = zip(*sorted_pairs)
    sorter, sortee = [list(tuple) for tuple in tuples]
    return sorter, sortee


# 5 calls per second
CALLS = 5
RATE_LIMIT = 1

@sleep_and_retry
@limits(calls=CALLS, period=RATE_LIMIT)
def check_limit():
     ''' Empty function just to check for calls to API '''
     return


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


class DropboxAPI(GmailAPI):
    def __init__(self, export):
        super().__init__(self)
        self.threads     = self.get_table_api_pointer("Threads")
        self.labels      = self.get_table_api_pointer("Labels")
        self.messages    = self.get_table_api_pointer("Messages")
        self.emails      = self.get_table_api_pointer("Emails")
        self.attachments = self.get_table_api_pointer("Attachments")


    def get_table_api_pointer(self, table_name, base_id=AT_CONFIG['base_id'], api_key=AT_CONFIG['api_key']):
        return airtable.Airtable(base_id, table_name, api_key)
    

class AirtableAPI(object):
    def __init__(self, export):
        self.export = export
        self.threads_query     = self.get_table_api_pointer("Threads")
        self.labels_query      = self.get_table_api_pointer("Labels")
        self.messages_query    = self.get_table_api_pointer("Messages")
        self.emails_query      = self.get_table_api_pointer("Emails")
        self.attachments_query = self.get_table_api_pointer("Attachments")

    def get_table_api_pointer(self, table_name, base_id=AT_CONFIG['base_id'], api_key=AT_CONFIG['api_key']):
        return airtable.Airtable(base_id, table_name, api_key)
    
    @property
    def labels(self):
        return self._labels

    @labels.setter
    def labels(self, new_labels):
        _labels = getattr(self,'_labels',{})
        atLabels = self.labels_query.get_all(fields=['labelId'])
        atLabelIds = {label['fields']['labelId']:label['id'] for label in atLabels }
        new_labels = {label.id:label for label in new_labels}
        for label_id, new_label in new_labels.items():
            if label_id in atLabelIds:
                if not getattr(new_label,'atId',None):
                    new_label.atId = atLabelIds[label_id]
            else:
                data = {
                    'labelId': label_id,
                    'Name': new_label.name
                }
                atId = self.labels_query.insert(data)
                new_label.atId = atId['id']
            if not label_id in _labels:
                _labels[label_id]= new_label
        self._labels = _labels


    @property
    def threads(self):
        return self._threads

    @threads.setter
    def threads(self, new_threads):
        _threads = getattr(self,'_threads',{})
        atThreads = self.threads_query.get_all(fields=['threadId'])
        atThreadIds = {thread['fields']['threadId']:thread['id'] for thread in atThreads }
        for thread_id, new_thread in new_threads.items():
            if thread_id in atThreadIds:
                if not getattr(new_thread, 'atId', None):
                    new_thread.atId = atThreadIds[thread_id]
            else:
                data = {
                    'threadId': thread_id,
                    'Name': new_thread.name,
                    'Subject': new_thread.subject,
                    'Date': str(new_thread.dt)
                }
                atId = self.threads_query.insert(data)
                new_thread.atId = atId['id']
            if not thread_id in _threads:
                _threads[thread_id]= new_threads[thread_id]
        self._threads = _threads

    @property
    def messages(self):
        return self._messages

    
    @messages.setter
    def messages(self, new_messages):
        _messages = getattr(self,'_messages',{})
        atMessages = self.messages_query.get_all(fields=['messageId', 'Labels'])
        atMessageIds = {message['fields']['messageId']:message['id'] for message in atMessages }
        atLabels = { message['fields']['messageId']:message['fields'].get('Labels',[]) for message in atMessages }
        for message_id, new_message in new_messages.items():
            email_headers={}
            new_labels = [label.atId for label in new_message.labels]
            for email_type in ['From','To', 'Cc']:
                email_headers[email_type]=[]
                input = []
                for email_str in new_message.headers[email_type]:
                    name, address = parseaddr(email_str)
                    if address in self.emails:
                        email = self.emails[address]
                        if name:
                            email.name = name
                        email_headers[email_type].append(email.atId)
                    else:
                        email = Email(email_str)
                        self.emails = email
                        email_headers[email_type].append(self.emails[email.address].atId)

            if message_id in atMessageIds:
                if not getattr(new_message,'atId',None):
                    new_message.atId = atMessageIds[message_id]
                if new_labels:
                    atLabelsForMessage = atLabels.get(message_id, [])
                    # labels = list(set(new_labels) - set(atLabelsForMessage))
                    resulting_list = list(atLabelsForMessage)
                    resulting_list.extend(x for x in new_labels if x not in resulting_list)
                    self.messages_query.update(new_message.atId, {'Labels': resulting_list})
                    # insert new list value
            else:
                data = {
                    'messageId': message_id,
                    'Subject': new_message.subject,
                    'Name': new_message.name,
                    'Thread': [self.threads[new_message.threadId].atId],
                    'Date': str(new_message.dt),
                    'From': email_headers['From'],
                    'To': email_headers['To'],
                    'Cc': email_headers['Cc'],
                    'Labels': new_labels
                }
                # print(f"NEW MSG LABELS: {new_message.labels}")
                # print(f"DATA: {data}")
                atId = self.messages_query.insert(data)
                new_message.atId = atId['id']
            
            # labels = {label.atId:label for label in new_message.labels}
            # if new_message.labels

            if not message_id in _messages:
                _messages[message_id]= new_message
        self._messages = _messages

    @property
    def emails(self):
        return getattr(self,"_emails",{})
    
    @emails.setter
    def emails(self, new_email):
        _emails = getattr(self,'_emails',{})
        atEmails = self.emails_query.get_all(fields=['Address','Name'])
        atEmailIds = {}
        for email in atEmails:
            address = email['fields']['Address']
            id = email['id']
            atEmailIds[address]=id
        if new_email.address in atEmailIds:
            if not getattr(new_email,'atId',None):
                new_email.atId = atEmailIds[new_email.address]
        else:
            data = {'Address': new_email.address, 'Name': new_email.name }
            emailId = self.emails_query.insert(data)
            new_email.atId = emailId['id']
        if not new_email.address in _emails:
            # TODO: update name if different
            _emails[new_email.address]= new_email
        self._emails = _emails
