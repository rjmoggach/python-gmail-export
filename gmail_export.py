# -*- coding: utf-8 -*-
"""
* GMail Export Ver 0.1.0
* This script allows the user to export gmail to various formats.
"""

__version__ = '0.1.0'

import os
import argparse
import pickle
from pathlib import Path
import base64
import email
import shutil
import string
import pendulum
from googleapiclient.discovery import build
from google_auth_oauthlib.flow import InstalledAppFlow
from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from PyInquirer import Token, ValidationError, Validator, print_json, prompt, style_from_dict
from pprint import pprint
# from email2pdf import Email2Html, Html2Pdf


try:
    import colorama
    colorama.init()
except ImportError:
    colorama = None


try:
    from termcolor import colored
except ImportError:
    colored = None


CFG_PATH = os.path.join(str(Path.home()), '.gmail_export')
TOKEN_PATH = os.path.join(CFG_PATH, 'token.json')
CREDENTIALS_PATH = os.path.join(CFG_PATH, 'credentials.json')
EXPORT_PATH = os.path.join(CFG_PATH, 'export')
os.makedirs(EXPORT_PATH, exist_ok=True)
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


def valid_dir_name(dir_name):
    valid_chars = f"-_.() ' à â ç è é ê î ô ù û  {string.ascii_letters} {string.digits}"
    valid_name = ''.join(ch for ch in dir_name if ch in valid_chars)
    valid_name = valid_name.replace(' ','_').replace('__','_')
    return valid_name

class GmailExport(object):
    def __init__(self, labels=[], token_path=TOKEN_PATH, credentials_path=CREDENTIALS_PATH, export_path=EXPORT_PATH, scopes=SCOPES):
        self.labels = labels
        self.credentials = None
        self.token_path = token_path
        self.credentials_path = credentials_path
        self.export_path = export_path
        self.scopes = scopes
        self.credentials = self.get_credentials()
        self.service = self.get_service()
        self.questions = self.get_questions()
        self.answers = self.get_answers()
        if self.answers:
            self.export_path = self.answers['export_path']
            self.overwrite = self.answers['overwrite']
            self.labels = self.answers['labels']
            self.timezone = self.answers['timezone']
            self.emails_for_labels = self.get_emails_for_labels(self.answers)
    
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
    
    def get_datetime(self, internalDate=-1):
        return pendulum.from_timestamp(int(internalDate)/1000.0, tz=self.timezone)

    def get_questions(self):
        questions = []
        questions.append(self.get_label_question())
        questions.append(self.get_export_path_question())
        questions.append(self.get_overwrite_question())
        questions.append(self.get_timezone_question())
        return questions
    
    def get_answers(self):
        answers = prompt(self.get_questions(), style=STYLE)
        return answers

    def get_labels(self):
        results = self.service.users().labels().list(userId='me').execute()
        labels = results['labels']
        user_labels = sorted([label for label in labels if label['type']=="user"], key=lambda k: k['name'].lower()) 
        return user_labels

    def get_label_question(self):
        labels = self.get_labels()
        choices = [{'name': label['name'], 'value': {'name': label['name'], 'id': label['id']}} for label in labels]
        question = {
            'type': 'checkbox',
            'name': 'labels',
            'message': 'Select labels',
            'choices': choices,
            'validate': lambda answer: 'You must choose a label.' if len(answer) == 0 else True
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
            'default': False
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
        
    def get_emails_for_labels(self, answers):
        emails_for_labels=[]
        for label in answers['labels']:
            id = label['id']
            name = label['name']
            export_path=os.path.join(self.export_path,name)
            messages = []
            response = self.service.users().messages().list(userId="me", labelIds=id, q=None, pageToken=None, maxResults=None, includeSpamTrash=None).execute()
            if 'messages' in response:
                messages = response['messages']
            # only 20 messages are returned so need to cycle through pages with new requests
            while 'nextPageToken' in response:
                page_token = response['nextPageToken']
                response = self.service.users().messages().list(userId="me", labelIds=id, q=None, pageToken=page_token, maxResults=None, includeSpamTrash=None).execute()
                messages.extend(response['messages'])
            emails_for_labels.append({
                'id': id,
                'name': name,
                'export_path': export_path,
                'messages': messages
            })
        return emails_for_labels

    def export_emails(self, emails_for_labels):
        for label in emails_for_labels:
            id = label['id']
            name = label['name']
            export_path=label['export_path']
            messages = label['messages']
            os.makedirs(export_path,exist_ok=True)
            for msg in messages:
                # folder = threadID (converted to subject later)
                # filename = date (converted to 2021-04-09_T15h45m32)
                # get entire message in RFC2822 formatted base64url encoded string to convert to .eml
                msg_raw = self.service.users().messages().get(userId="me", id=msg["id"], format="raw", metadataHeaders=None).execute()
                internalDate = msg_raw['internalDate']
                msg_datetime = self.get_datetime(internalDate)
                msg_name = msg_datetime.format('YYYY-MM-DD-HHmmss')
                # get message headers
                msg_headers = self.service.users().messages().get(userId="me", id=msg["id"], format="full", metadataHeaders=None).execute()
                # retrieve headers
                headers = msg_headers["payload"]["headers"]
                try:
                    msg_str = base64.urlsafe_b64decode(msg_raw['raw'].encode('ASCII'))
                    msg_mime = email.message_from_string(msg_str.decode())
                    msg_thread_id = msg_raw['threadId']
                    msg_dir_path = os.path.join(export_path, msg_thread_id)
                    os.makedirs(msg_dir_path, exist_ok=True)
                    if not os.path.exists(msg_dir_path) or self.overwrite:
                        msg_path = os.path.join(msg_dir_path, f'{msg_name}.eml')
                        with open(msg_path, 'w') as outfile:
                            gen = email.generator.Generator(outfile)
                            gen.flatten(msg_mime)
                            print(f"mail saved: {msg['id']} {msg_name}")
                except Exception as e:
                    print(e)
                    print("Error! Msg Id: ", msg['id'], " - ", msg_raw['snippet'] )
            # rename thread id to date & subject of first email
            for root, dirs, files in os.walk(export_path):
                for dir in dirs:
                    response = self.service.users().threads().get(userId="me", id=dir, metadataHeaders=None, format="full").execute()
                    # get headers from first msg
                    headers = response["messages"][0]["payload"]["headers"]
                    internalDate = response["messages"][0]["internalDate"]
                    thread_datetime = self.get_datetime(internalDate)
                    thread_date_str = thread_datetime.format('YYYY-MM-DD-HHmmss')
                    subject = [metadata['value'] for metadata in headers if metadata["name"]=="Subject"]
                    if subject == []:
                        subject = ["(no subject)"]
                    thread_dir_name = f'{thread_date_str}-{valid_dir_name(subject[0])}'
                    old_thread_dir_name = os.path.join(root, dir)
                    new_thread_dir_name = os.path.join(root, thread_dir_name)
                    print(old_thread_dir_name + " >>> " + thread_dir_name)
                    shutil.move(old_thread_dir_name, new_thread_dir_name)


def main():
    export=GmailExport()
    export.export_emails(export.emails_for_labels)


def mainOld():
    """Shows basic usage of the Gmail API.
    Lists the user's Gmail labels.
    """
    creds = None
    # The file token.json stores the user's access and refresh tokens, and is
    # created automatically when the authorization flow completes for the first
    # time.
    if os.path.exists(TOKEN_PATH):
        creds = Credentials.from_authorized_user_file(TOKEN_PATH, SCOPES)

    # If there are no (valid) credentials available, let the user log in.
    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            creds.refresh(Request())
        else:
            flow = InstalledAppFlow.from_client_secrets_file(CREDENTIALS_PATH, SCOPES)
            creds = flow.run_local_server(port=0)
        # Save the credentials for the next run
        with open(TOKEN_PATH, 'w') as token:
            token.write(creds.to_json())

    service = build('gmail', 'v1', credentials=creds)

    # Call the Gmail API
    results = service.users().labels().list(userId='me').execute()
    labels = results.get('labels', [])

    if not labels:
        print('No labels found.')
    else:
        print('Labels:')
        for label in labels:
            print(label['id'])

def parse_args():
    parser = argparse.ArgumentParser(description='This script will export your email!')
    parser.add_argument('-d','--dest',default=EXPORT_PATH, help='Destination - path to export to')




if __name__ == '__main__':
    main()