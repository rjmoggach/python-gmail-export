# -*- coding: utf-8 -*-
import os
from email.utils import parseaddr
import pendulum
from PyInquirer import Token, ValidationError, Validator, print_json, prompt, style_from_dict

from . import EXPORT_PATH, DROPBOX, AIRTABLE
from .api import GmailAPI
from .labels import GmailLabel


STYLE = style_from_dict({
    Token.QuestionMark: '#fac731 bold',
    Token.Answer: '#4688f1 bold',
    Token.Instruction: '',  # default
    Token.Separator: '#cc5454',
    Token.Selected: '#0abf5b',  # default
    Token.Pointer: '#673ab7 bold',
    Token.Question: '',
})


class ExportCLI(object):
    def __init__(self, export_path=EXPORT_PATH):
        self.api = GmailAPI()
        self.labels = []
        self.selected_labels = []
        self.threads = []
        self.messages = []
        self.export_path = export_path
        self.questions = self.get_questions()
        self.answers = self.get_answers()
        if self.answers:
            self.export_path = self.answers['export_path']
            self.overwrite = self.answers['overwrite']
            self.timezone = self.answers['timezone']
            self.selected_labels = self.get_selected_labels()
    
    def get_questions(self):
        questions = []
        questions.append(self.get_export_path_question())
        questions.append(self.get_timezone_question())
        questions.append(self.get_label_question())
        questions.append(self.get_formats_question())
        questions.append(self.get_overwrite_question())
        return questions
    
    def get_answers(self):
        answers = prompt(self.get_questions(), style=STYLE)
        return answers

    def get_labels(self):
        labels = []
        results = self.api.get_labels()
        results_labels = results['labels']
        user_labels = sorted([label for label in results_labels if label['type']=="user"], key=lambda k: k['name'].lower())
        for label in user_labels:
            new_label = GmailLabel(label['id'], label['name'], os.path.join(self.export_path,label['name']))
            labels.append(new_label)
        return labels

    def get_label_question(self):
        self.labels = self.get_labels()
        choices = [{'name': label.name, 'value': {'name': label.name, 'id': label.id}} for label in self.labels]
        question = {
            'type': 'checkbox',
            'name': 'labels',
            'message': 'Select labels',
            'choices': choices,
            'validate': lambda answer: 'You must choose a label.' if len(answer) == 0 else True
        }
        return question
    
    def get_formats_question(self):
        choices = [
            {'name': "eml", 'checked': True },
            {'name': "html" },
            {'name': "pdf" },
            {'name': "attachments"},
            {'name': "inline"}
        ]
        question = {
            'type': 'checkbox',
            'name': 'formats',
            'message': 'Select file formats',
            'choices': choices,
            'validate': lambda answer: 'You must choose one.' if len(answer) == 0 else True
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
            'default': True
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
        
    def get_selected_labels(self):
        selected_labels=[]
        for answer in self.answers['labels']:
            for label in self.labels:
                if label.id == answer['id']:
                    selected_labels.append(label)
        return selected_labels

    def export(self):
        for label in self.selected_labels:
            # get the label path
            label_export_path = label.get_export_path(self.export_path)
            # get the label messages
            messages = label.get_messages()
            eml = True if 'eml' in self.answers['formats'] else False
            html5 = True if 'html' in self.answers['formats'] else False
            pdf = True if 'pdf' in self.answers['formats'] else False
            inl = True if 'inline' in self.answers['formats'] else False
            att = True if 'attachments' in self.answers['formats'] else False
            message_count = len(messages)
            i=1
            for message in messages:
                print(f"\n> Message {i} of {message_count} for label '{label.name}'.")
                i+=1
                message.export(eml,html5,pdf,att,inl)

