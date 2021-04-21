from email.utils import parseaddr


class Email(object):
    def __init__(self, email, address=None, name=None, atId=None):
        self.email = email
        self.name, self.address = parseaddr(self.email)



