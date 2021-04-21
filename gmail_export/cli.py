# -*- coding: utf-8 -*-
import os
import pendulum
from PyInquirer import Token, ValidationError, Validator, print_json, prompt, style_from_dict
from jinja2 import Template

from gmail_export import EXPORT_PATH, DROPBOX, AIRTABLE, TIMEZONE
import gmail_export.api as api


STYLE = style_from_dict({
    Token.QuestionMark: '#fac731 bold',
    Token.Answer: '#4688f1 bold',
    Token.Instruction: '',  # default
    Token.Separator: '#cc5454',
    Token.Selected: '#0abf5b',  # default
    Token.Pointer: '#673ab7 bold',
    Token.Question: '',
})


REPR_TEMPLATE="""ExportCLI({
        Path: {{ export_path }}
    Timezone: {{ timezone }}
      Labels: {% for label in labels %}{% if loop.first %}{{ label.name }}{% else %}
              {{ label.name }}{% endif %}{% endfor %}
     Formats: {{ formats }}
   Overwrite: {{ overwrite }}
})
"""


class ExportCLI(object):
    def __init__(self, export_path=EXPORT_PATH):
        self.api = api.GmailAPI()
        self.labels = self.api.get_labels()
        self.messages = {}
        self.threads = {}
        self.config = self.questions
        self.selected_labels = self.config['labels']
        self.export_path = self.config['export_path']
        self.path = self.export_path

    def __repr__(self):
        t = Template(REPR_TEMPLATE)
        return t.render(self.config)

    def get_datetime(self, internalDate=-1):
        return pendulum.from_timestamp(int(internalDate)/1000.0, tz=self.config['timezone'])

    def populate_selected_labels(self):
        for label in self.selected_labels:
            label.populate(self)
    
    def export_selected_labels(self):
        for label in self.selected_labels:
            label.populate(self)
            label.export(self)

    @property
    def labels(self, selected=False):
        return [label for label in self._labels if label.selected] if selected else self._labels
    
    @labels.setter
    def labels(self, results):
        self._labels = results

    @property
    def selected_labels(self):
        return [label for label in self.labels if label.selected==True]

    @selected_labels.setter
    def selected_labels(self, selected):
        for label in self.labels:
            label.selected = True if label in selected else False

    @property
    def questions(self):
        questions = []
        questions.append(self.export_root_question)
        questions.append(self.timezone_question)
        questions.append(self.label_question)
        questions.append(self.formats_question)
        questions.append(self.overwrite_question)
        return questions
    
    @property
    def config(self):
        if hasattr(self, "_config"):
            return self._config
        else:
            return None

    @config.setter
    def config(self, questions):
        self._config = prompt(questions, style=STYLE)

    @property
    def label_question(self):
        choices = [{'name': label.name, 'value': label } for label in self.labels]
        question = {
            'type': 'checkbox',
            'name': 'labels',
            'message': 'Select labels',
            'choices': choices,
            'validate': lambda answer: 'You must choose a label.' if len(answer) == 0 else True
        }
        return question
    
    @property
    def formats_question(self):
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
    
    @property
    def export_root_question(self):
        question = {
            'type': 'input',
            'name': 'export_path',
            'message': 'Export path:',
            'default': EXPORT_PATH,
            'validate': lambda answer: 'Enter an existing path.' if not os.path.exists(answer) else True
        }
        return question

    @property
    def overwrite_question(self):
        question = {
            'type': 'confirm',
            'name': 'overwrite',
            'message': 'Overwrite',
            'default': True
        }
        return question

    @property
    def timezone_question(self):
        question = {
            'type': 'input',
            'name': 'timezone',
            'message': 'Timezone TZ name',
            'default': TIMEZONE,
            'validate': lambda answer: 'Enter a valid timezone from https://en.wikipedia.org/wiki/List_of_tz_database_time_zones.' if not answer in pendulum.timezones else True
        }
        return question
        
