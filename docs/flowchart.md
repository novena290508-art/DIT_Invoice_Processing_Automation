# Workflow Flowchart

1. Ingest CSV/XLSX (`data_reader.py`)
2. Validate rows (`validator.py`)
3. Detect duplicates & reconcile per currency (`business_rules.py`)
4. Export CSV/XLSX reports (`report_generator.py`)
