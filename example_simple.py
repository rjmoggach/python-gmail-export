from gmail_export.cli import ExportCLI
from gmail_export.api import AirtableAPI


def main():
    exporter=ExportCLI()
    exporter.export_selected_labels()

if __name__ == '__main__':
    main()


