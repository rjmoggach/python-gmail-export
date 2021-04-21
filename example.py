from gmail_export.cli import ExportCLI


def main():
    exporter=ExportCLI()
    print(exporter)
    exporter.export_selected_labels()

if __name__ == '__main__':
    main()


