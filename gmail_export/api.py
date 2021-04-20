# -*- coding: utf-8 -*-
import os
from pathlib import Path
from googleapiclient.discovery import build
from google_auth_oauthlib.flow import InstalledAppFlow
from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials

from . import TOKEN_PATH, CREDENTIALS_PATH, SCOPES


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
    
    def get_labels(self):
        return self.service.users().labels().list(userId='me').execute()
    
    def get_messages_for_label(self, id, page_token=None):
        return self.service.users().messages().list(userId="me", labelIds=id, q=None, pageToken=page_token, maxResults=None, includeSpamTrash=None).execute()

    def get_message_id(self, id):
        return self.service.users().messages().get(userId="me", id=id, format="raw", metadataHeaders=None).execute()
    
    def get_message_meta(self, id):
        return self.service.users().messages().get(userId="me", id=id, format="metadata", metadataHeaders=["Subject","From","To","Date","Cc","Bcc"]).execute()