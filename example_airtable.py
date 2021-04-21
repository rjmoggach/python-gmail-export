from gmail_export.cli import ExportCLI
from gmail_export.api import AirtableAPI


def main():
    exporter=ExportCLI()
    exporter.export_selected_labels()
    # for k,v in exporter.messages.items():
    #     print("LABELS: ", v.labels)
    print(f"\nSCRIPT EXPORTER THREADS: {exporter.threads}\n")
    airtable=AirtableAPI(exporter)
    airtable.labels=exporter.selected_labels
    airtable.threads=exporter.threads
    airtable.messages=exporter.messages

if __name__ == '__main__':
    main()


