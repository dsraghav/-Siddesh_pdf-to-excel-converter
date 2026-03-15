import streamlit as st
import pdfplumber
import pandas as pd
from io import BytesIO

def extract_po_table(pdf_file, pdf_name):
    """
    Extract purchase order lines from a PDF using table extraction.
    Assumes the table has columns in the order:
    ITEM, MATERIAL, DESCRIPTION, HSN/SAC, QUANTITY, UNIT, START DATE, END DATE, PRICE PER UNIT, AMOUNT
    (END DATE may be empty in some files.)
    """
    all_rows = []

    with pdfplumber.open(pdf_file) as pdf:
        for page in pdf.pages:
            tables = page.extract_tables()
            for table in tables:
                for row in table:
                    # Skip empty rows
                    if not row or all(cell is None or cell == "" for cell in row):
                        continue

                    # Skip header row (if it contains "ITEM")
                    if row[0] and "ITEM" in str(row[0]).upper():
                        continue

                    # Ensure the row has at least 9 columns (some may be missing END DATE)
                    if len(row) >= 9:
                        item = row[0]
                        material = row[1] if len(row) > 1 else ""
                        description = row[2] if len(row) > 2 else ""
                        hsn = row[3] if len(row) > 3 else ""
                        quantity = row[4] if len(row) > 4 else ""
                        unit = row[5] if len(row) > 5 else ""
                        start_date = row[6] if len(row) > 6 else ""
                        end_date = row[7] if len(row) > 7 else ""
                        price = row[8] if len(row) > 8 else ""
                        amount = row[9] if len(row) > 9 else ""

                        # Combine material and description (if both exist) into one field
                        material_desc = ""
                        if material and description:
                            material_desc = f"{material} {description}"
                        elif material:
                            material_desc = material
                        elif description:
                            material_desc = description

                        # Clean up: replace newlines with spaces
                        if material_desc:
                            material_desc = material_desc.replace("\n", " ").strip()

                        all_rows.append({
                            "pdf_name": pdf_name,
                            "item": item,
                            "material_description": material_desc,
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


# ---------- Streamlit app ----------
st.set_page_config(page_title="PDF PO to Excel", layout="wide")
st.title("📄 Purchase Order PDF → Excel Converter")
st.markdown("Upload one or more PDF purchase orders. All data will be combined into a single Excel sheet.")

uploaded_files = st.file_uploader(
    "Upload PO PDFs",
    type="pdf",
    accept_multiple_files=True
)

if uploaded_files:
    all_dfs = []
    progress_bar = st.progress(0)
    status_text = st.empty()

    for i, file in enumerate(uploaded_files):
        status_text.text(f"Processing {file.name}...")
        try:
            df = extract_po_table(file, file.name)
            all_dfs.append(df)
        except Exception as e:
            st.error(f"Error processing {file.name}: {e}")
        progress_bar.progress((i + 1) / len(uploaded_files))

    status_text.text("Processing complete!")

    if all_dfs:
        final_df = pd.concat(all_dfs, ignore_index=True)

        st.subheader("Preview of combined data")
        st.dataframe(final_df.head(20))

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
    else:
        st.warning("No data could be extracted from the uploaded files.")
