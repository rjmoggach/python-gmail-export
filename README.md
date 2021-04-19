# Python GMail Export CLI

This is my python tool to export mail from gmail in formats I require.

This library allows me to connect to my Gmail account and download as `.eml` files for a specific label. It then converts the `.eml` files to pdf or html and extracts attachments.

> Use at your own risk. Don't delete files if you're not clear on what's happening in here.


## Usage

### Installation & Environment

Most dependencies are managed with poetry. 

To install run the `install` command.

```
poetry install
```

To run the command line tools you'll need to be in the virtual environment using:

```
poetry shell
```

#### Additional Dependencies

You'll also need [wkhtmltopdf](http://wkhtmltopdf.org/).

I installed using Chocolatey for Windows.


### Credentials

1. Go to [https://console.cloud.google.com/home/dashboard](https://console.cloud.google.com/home/dashboard)
2. Create a new project eg. `mydomain-com-gmail`
3. Go to the Gmail API Library [https://console.cloud.google.com/apis/library/gmail.googleapis.com](https://console.cloud.google.com/apis/library/gmail.googleapis.com)
   *make sure the correct project is in the path*
4. Click on "Enable".
5. Click on "OAuth consent screen".
6. Select "Internal" and click on "Create".
7. Follow the steps to create a consent screen.
8. Add the Gmail API scopes you want... at a minimum `gmail.readonly`.
9. Click on "Credentials" and then "Create Credentials".
10. Choose "OAuth client ID", "Desktop App", and give it a name like `gmail_export`.
11. Download the `.json` file and rename it as `credentials.json`.
12. Move the file to `~/.gmail_export/credentials.json`.

### Run the Script!

```
python gmail_export.py
```

The rest is self-explanatory.


## Thank you & Credit where Credit is due

The following were instrumental in me getting to my implementation:

* [https://github.com/MagTun/gmail-to-pdf](https://github.com/MagTun/gmail-to-pdf)
* [https://github.com/pixelcog/gmail-to-pdf](https://github.com/pixelcog/gmail-to-pdf)
* [https://github.com/andrewferrier/email2pdf](https://github.com/andrewferrier/email2pdf)
* [https://github.com/hghotra/eml2pdflib](https://github.com/hghotra/eml2pdflib)
* [https://www.thepythoncode.com/article/use-gmail-api-in-python](https://www.thepythoncode.com/article/use-gmail-api-in-python)



## More Resources

* https://developers.google.com/gmail/api/reference/rest/v1/users.messages/get

### List email by Labels
* https://developers.google.com/resources/api-libraries/documentation/gmail/v1/python/latest/index.html 
* https://developers.google.com/resources/api-libraries/documentation/gmail/v1/python/latest/gmail_v1.users.messages.html#list
* example of code for list: https://developers.google.com/gmail/api/v1/reference/users/messages/list?apix_params=%7B%22userId%22%3A%22me%22%2C%22includeSpamTrash%22%3Afalse%2C%22labelIds%22%3A%5B%22LM%22%5D%7D

### Get emails

* https://developers.google.com/resources/api-libraries/documentation/gmail/v1/python/latest/gmail_v1.users.messages.html#get
* https://developers.google.com/gmail/api/v1/reference/users/messages/get 
* https://python-forum.io/Thread-TypeError-initial-value-must-be-str-or-None-not-bytes--12161

### Thread

* https://developers.google.com/resources/api-libraries/documentation/gmail/v1/python/latest/gmail_v1.users.threads.html#get
