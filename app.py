import streamlit as st
import pdfplumber
import pandas as pd
from io import BytesIO

def extract_po_table(pdf_file, pdf_name):

```
all_rows = []

with pdfplumber.open(pdf_file) as pdf:

    for page in pdf.pages:

        tables = page.extract_tables()

        for table in tables:

            for row in table:

                if not row:
                    continue

                if "ITEM" in str(row[0]).upper():
                    continue

                if len(row) >= 9:

                    item = row[0]
                    part_number = row[1]
                    description = row[2]
                    hsn = row[3]
                    quantity = row[4]
                    unit = row[5]
                    start_date = row[6]
                    end_date = row[7]
                    price = row[8]
                    amount = row[9] if len(row) > 9 else ""

                    all_rows.append({
                        "pdf_name": pdf_name,
                        "item": item,
                        "part_number": part_number,
                        "material_description": description,
                        "hsn_sac": hsn,
                        "quantity": quantity,
                        "unit": unit,
                        "start_date": start_date,
                        "end_date": end_date,
                        "price_per_unit": price,
                        "amount": amount
                    })

df = pd.DataFrame(all_rows)

return df
```

st.set_page_config(page_title="PDF PO to Excel", layout="wide")

st.title("📄 Purchase Order PDF → Excel Converter")

uploaded_files = st.file_uploader(
"Upload PO PDFs",
type="pdf",
accept_multiple_files=True
)

if uploaded_files:

```
all_dfs = []

for file in uploaded_files:

    df = extract_po_table(file, file.name)

    all_dfs.append(df)

final_df = pd.concat(all_dfs, ignore_index=True)

st.subheader("Preview")

st.dataframe(final_df)

output = BytesIO()

with pd.ExcelWriter(output, engine="xlsxwriter") as writer:
    final_df.to_excel(writer, sheet_name="PO_Data", index=False)

output.seek(0)

st.download_button(
    label="📥 Download Excel",
    data=output,
    file_name="purchase_orders.xlsx",
    mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
)
```
