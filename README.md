Med Spa Accounting Automation Pipeline
Automated ETL for EMR Transactions → QuickBooks Desktop (via Transaction Pro)

This pipeline processes EMR transactions, tips, Gravity Payments, vendor rewards, and payment mappings into ready-to-import QuickBooks files.

It ensures:

Accurate item-based invoices

Exact-matched credit card payments

Separation of cash vs card payments

Vendor receivable journal entries

Automatic customer master management

Detailed exception reporting

⭐ Quick Start (Follow These Steps Each Month)
STEP 1 — Export Files From EMR

Place all exported files inside:

/input

Required EMR exports:
1. emr_transactions.xlsx

Columns required:

Date
Invoice #
CID
Client Name
Service/Product
SKU
Staff
QTY
Price
Discounts
Tax
Total Due
Amount
Payment Type

2. emr_tips.xlsx

⚠️ Important: Headers begin on row 2, not row 1.

Required columns:

Invoice
Tip Amount

3. gravity_payments.csv

Columns required:

Date/Time
Sale Amount
Tip
Total
Card Type
Approval
Name (optional)

STEP 2 — Confirm Mapping Files Are Present

Inside /input ensure:

COA_Quickbooks_matched.xlsx

emr_service_items tab

emr_service_text
matched_item
taxcode


emr_payment_types tab

payment_type
mapped_to_account

customer_master.xlsx

Automatically updated by pipeline.

STEP 3 — Run Pipeline

Open PowerShell:

cd C:\Users\Trader\MedSpa\medspa_pipeline
.\.venv\Scripts\Activate.ps1
python main.py


If successful, you'll see:

Loading files...
Tips loaded for X invoices.
Tips merged into EMR transactions.
Mapping services...
Mapping payments...
Matching Gravity payments...
Building Receive_Payments_From_Gravity.csv...
Building Receive_Payments_Cash.csv...
Building Vendor_Receivable_JournalEntries.csv...
Done. Check the 'output' folder for results.

⭐ STEP 4 — Import Into QuickBooks Desktop (via Transaction Pro)
1. Import Invoices

File:

output/Invoice_Import_ItemBased.csv


Mapping:

CSV Field	QB Field
Customer	Customer
TxnDate	Invoice Date
RefNumber	Invoice #
Item	Item
Qty	Quantity
Rate	Rate
Amount	Amount
TaxCode	Tax Code
Memo	Description
2. Import Credit Card Payments (from Gravity)

File:

output/Receive_Payments_From_Gravity.csv


Mapping:

CSV Field	QB Field
Customer	Customer
TxnDate	Payment Date
RefNumber	Reference #
Amount	Amount
PaymentMethod	Method
DepositToAccount	Deposit To
ApplyToRefNumber	Apply to Invoice

All card deposits post to:

1030 · Merchant Clearing

3. Import Cash Payments

File:

output/Receive_Payments_Cash.csv


Same mapping as above.

Mixed invoices (cash + card):

Card portion → Gravity file

Cash portion → Cash file

No duplication.

4. Import Vendor Receivable Journal Entries

File:

output/Vendor_Receivable_JournalEntries.csv


Maps directly via Transaction Pro Journal Entry import.

Each reward (Alle / Aspire / Cherry) creates:

Debit	Credit
Vendor Receivable	A/R (customer)
⭐ What the Pipeline Does
1. Loads all input files

EMR, Tips, Gravity, mappings, customer master.

2. Applies customer name validation

Flags EMR IDs with name changes:

output/Duplicate_ID_Different_Name.csv

3. Merges tips into EMR transactions

Using invoice number.

4. Maps EMR services → QB Items

Unmapped output:

output/Unmapped_Services.csv

5. Maps EMR payment types → QB Accounts

Unmapped output:

output/Unmapped_Payments.csv

6. Generates invoice import file

One line per service, item-based.

7. Matches Gravity payments

Match rules:

Match Gravity Total to EMR card payment lines (Amount)

Same day preferred

Otherwise ±3 days allowed

Card type used as tie-breaker

Ambiguous → unmatched

Outputs:

Receive_Payments_From_Gravity.csv
Unmatched_Gravity_Payments.csv
Gravity_Refunds.csv

8. Separates cash payments

Non-service EMR lines where:

Payment Type = Cash


Output:

Receive_Payments_Cash.csv

9. Builds vendor receivable journal entries

Outputs:

Vendor_Receivable_JournalEntries.csv

⭐ Folder Structure
medspa_pipeline/
│
├── input/
│   ├── emr_transactions.xlsx
│   ├── emr_tips.xlsx
│   ├── gravity_payments.csv
│   ├── COA_Quickbooks_matched.xlsx
│   ├── customer_master.xlsx
│
├── output/
│   ├── Invoice_Import_ItemBased.csv
│   ├── Receive_Payments_From_Gravity.csv
│   ├── Receive_Payments_Cash.csv
│   ├── Vendor_Receivable_JournalEntries.csv
│   ├── Unmatched_Gravity_Payments.csv
│   ├── Unmapped_Services.csv
│   ├── Unmapped_Payments.csv
│   ├── Duplicate_ID_Different_Name.csv
│   ├── Gravity_Refunds.csv
│
├── main.py
├── README.md
└── .venv/