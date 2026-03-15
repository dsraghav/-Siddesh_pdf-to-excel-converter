import streamlit as st
import pdfplumber
import re
import pandas as pd
from io import BytesIO

# ---------- Extraction function ----------
def extract_items_from_pdf(pdf_file, pdf_name):
    items = []
    current_item = None
    description_lines = []      # accumulate multi-line description
    tax_lines_buffer = []        # accumulate tax-related lines
    fields_found = False         # whether we have already found the fields for the current item

    # Patterns for tax lines
    tax_patterns = {
        'base': re.compile(r'Base Amount\s+([\d,]+\.?\d*)\s+INR'),
        'igst': re.compile(r'IN:\s*Integrated GST\s+(\d+\.?\d*)%\s+([\d,]+\.?\d*)'),
        'cess': re.compile(r'IN:\s*GST Comp CESS\s+(\d+\.?\d*)%\s+([\d,]+\.?\d*)'),
        'net': re.compile(r'Price\(Net\)\s+([\d,]+\.?\d*)')
    }

    # Pattern to extract fields from a line (must appear at the end of the line)
    # Groups: part_number, quantity, unit, date, price, amount
    field_extract_pattern = re.compile(
        r'(\d+(?:\s*-\s*[A-Z]+)?)\s*'          # part number (e.g., 995468 or 9983 - OT)
        r'([\d,]+\.?\d*)\s*'                    # quantity
        r'([A-Z]{2})\s*'                         # unit (two uppercase letters)
        r'(\d{2}\.\d{2}\.\d{4})\s*'              # date (dd.mm.yyyy)
        r'([\d,]+\.?\d*)\s*'                      # price per unit
        r'([\d,]+\.?\d*)$'                        # amount
    )

    # Pattern for a line that starts with an item number
    item_start_pattern = re.compile(r'^(\d+)\s+(.*)')

    with pdfplumber.open(pdf_file) as pdf:
        for page in pdf.pages:
            text = page.extract_text()
            if not text:
                continue
            lines = text.split('\n')
            for line in lines:
                line = line.strip()
                if not line:
                    continue

                # Check if this line starts a new item
                item_match = item_start_pattern.match(line)
                if item_match:
                    # Finalize previous item if exists
                    if current_item is not None:
                        finalize_item(current_item, description_lines, tax_lines_buffer, tax_patterns)
                        items.append(current_item)

                    # Start new item
                    item_num = item_match.group(1)
                    rest_of_line = item_match.group(2)
                    current_item = {
                        'item': item_num,
                        'pdf_name': pdf_name,
                        'material': '',
                        'part_number': '',
                        'quantity': '',
                        'unit': '',
                        'date': '',
                        'price_per_unit': '',
                        'amount': ''
                    }
                    description_lines = [rest_of_line]   # first part of description
                    tax_lines_buffer = []
                    fields_found = False
                    continue

                # If we're not inside an item, skip
                if current_item is None:
                    continue

                # Check if line contains tax keywords
                if any(kw in line for kw in ['Base Amount', 'Integrated GST', 'GST Comp CESS', 'Price(Net)']):
                    tax_lines_buffer.append(line)
                    continue

                # If fields have not been found yet, try to extract them from this line
                if not fields_found:
                    fields_match = field_extract_pattern.search(line)
                    if fields_match:
                        # Found the fields in this line
                        current_item['part_number'] = fields_match.group(1).strip()
                        current_item['quantity'] = fields_match.group(2).replace(',', '')
                        current_item['unit'] = fields_match.group(3)
                        current_item['date'] = fields_match.group(4)
                        current_item['price_per_unit'] = fields_match.group(5).replace(',', '')
                        current_item['amount'] = fields_match.group(6).replace(',', '')
                        # Any text before the fields on this line is part of the description
                        preceding_text = line[:fields_match.start()].strip()
                        if preceding_text:
                            description_lines.append(preceding_text)
                        fields_found = True
                    else:
                        # No fields yet, so this line is part of the description
                        description_lines.append(line)
                else:
                    # Fields already found; any non-tax line here is unexpected, but we'll ignore or could log
                    # In practice, after fields only tax lines appear, so we do nothing.
                    pass

        # Finalize the last item after processing all pages
        if current_item is not None:
            finalize_item(current_item, description_lines, tax_lines_buffer, tax_patterns)
            items.append(current_item)

    # Convert to DataFrame and clean up
    df = pd.DataFrame(items)
    # Reorder columns for readability
    col_order = ['pdf_name', 'item', 'material', 'part_number', 'quantity', 'unit',
                 'date', 'price_per_unit', 'amount', 'base_amount',
                 'igst_rate', 'igst_amount', 'cess_rate', 'cess_amount', 'net']
    col_order = [c for c in col_order if c in df.columns]
    df = df[col_order]

    # Convert numeric columns
    numeric_cols = ['quantity', 'price_per_unit', 'amount', 'base_amount',
                    'igst_amount', 'cess_amount', 'net']
    for col in numeric_cols:
        if col in df.columns:
            df[col] = pd.to_numeric(df[col], errors='coerce').round(2)

    rate_cols = ['igst_rate', 'cess_rate']
    for col in rate_cols:
        if col in df.columns:
            df[col] = pd.to_numeric(df[col], errors='coerce')

    return df


def finalize_item(item_dict, description_lines, tax_lines_buffer, tax_patterns):
    """Combine description lines and parse tax lines into the item dictionary."""
    # Build material from all collected description lines
    if description_lines:
        item_dict['material'] = ' '.join(description_lines).strip()

    # Parse tax lines
    tax_text = ' '.join(tax_lines_buffer)

    base_match = tax_patterns['base'].search(tax_text)
    if base_match:
        item_dict['base_amount'] = base_match.group(1).replace(',', '')

    igst_match = tax_patterns['igst'].search(tax_text)
    if igst_match:
        item_dict['igst_rate'] = igst_match.group(1)
        item_dict['igst_amount'] = igst_match.group(2).replace(',', '')

    cess_match = tax_patterns['cess'].search(tax_text)
    if cess_match:
        item_dict['cess_rate'] = cess_match.group(1)
        item_dict['cess_amount'] = cess_match.group(2).replace(',', '')

    net_match = tax_patterns['net'].search(tax_text)
    if net_match:
        item_dict['net'] = net_match.group(1).replace(',', '')


# ---------- Streamlit app ----------
st.set_page_config(page_title="PDF to Excel Converter", layout="wide")
st.title("📄 PDF Purchase Order to Excel Converter")
st.markdown("Upload one or more PDF purchase orders. All data will be combined into a single Excel sheet.")

uploaded_files = st.file_uploader(
    "Choose PDF files",
    type="pdf",
    accept_multiple_files=True
)

if uploaded_files:
    all_dfs = {}
    progress_bar = st.progress(0)
    status_text = st.empty()

    for i, uploaded_file in enumerate(uploaded_files):
        status_text.text(f"Processing {uploaded_file.name}...")
        try:
            df = extract_items_from_pdf(uploaded_file, uploaded_file.name)
            all_dfs[uploaded_file.name] = df
        except Exception as e:
            st.error(f"Error processing {uploaded_file.name}: {e}")
        progress_bar.progress((i + 1) / len(uploaded_files))

    status_text.text("Processing complete!")

    if all_dfs:
        # Combine all DataFrames into one
        combined_df = pd.concat(all_dfs.values(), ignore_index=True)

        st.subheader("Preview of combined data")
        st.dataframe(combined_df.head(20))

        output = BytesIO()
        with pd.ExcelWriter(output, engine='xlsxwriter') as writer:
            combined_df.to_excel(writer, sheet_name="Purchase Orders", index=False)
        output.seek(0)

        st.download_button(
            label="📥 Download Excel file",
            data=output,
            file_name="extracted_purchase_orders.xlsx",
            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
        )
    else:
        st.warning("No data could be extracted from the uploaded files.")
