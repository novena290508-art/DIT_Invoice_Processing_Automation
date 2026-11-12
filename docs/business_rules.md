# Business Rules

- Priority: `Invalid > Duplicate > Warning > Valid`.
- Zero-value invoices (`0, 0, 0`) are `Warning / Review Required`.
- Duplicate key: normalized `vendor_name + invoice_number`.
- Per-currency totals are never combined across currencies.
