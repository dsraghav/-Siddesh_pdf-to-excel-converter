import streamlit as st
import pdfplumber
import re
import pandas as pd
from io import BytesIO

# ---------- Extraction function ----------
def extract_items_from_pdf(pdf_file, pdf_name):
    items = []
    current_item = None
    description_lines = []
    tax_lines_buffer = []
    fields_found = False  # flag: have we parsed the field line for this item?

    tax_patterns = {
        'base': re.compile(r'Base Amount\s+([\d,]+\.?\d*)\s+INR'),
        'igst': re.compile(r'IN:\s*Integrated GST\s+(\d+\.?\d*)%\s+([\d,]+\.?\d*)'),
        'cess': re.compile(r'IN:\s*GST Comp CESS\s+(\d+\.?\d*)%\s+([\d,]+\.?\d*)'),
        'net': re.compile(r'Price\(Net\)\s+([\d,]+\.?\d*)')
    }

    # Matches the structured data line: PART_NO  QTY  UNIT  DATE  PRICE  AMOUNT
    field_pattern = re.compile(
        r'^\s*(\d[\d\s]*-\s*(?:\w+)?)\s+'
        r'([\d,]+\.?\d*)\s+'
        r'(\w+)\s+'
        r'(\d{2}\.\d{2}\.\d{4})\s+'
        r'([\d,]+\.?\d*)\s+'
        r'([\d,]+\.?\d*)$'
    )

    # Lines to skip (headers/footers)
    skip_patterns = [
        re.compile(r'Item\s+Material\s+'),
        re.compile(r'Purchase Order\s+\d+'),
        re.compile(r'Delivery Date'),
        re.compile(r'Net price\s+Per'),
        re.compile(r'Page\s+\d+'),
    ]

    item_start_pattern = re.compile(r'^(\d{1,4})\s+(.*)')

    with pdfplumber.open(pdf_file) as pdf:
        for page in pdf.pages:
            text = page.extract_text()
            if not text:
                continue
            lines = text.split('\n')

            for line in lines:
                line_stripped = line.strip()
                if not line_stripped:
                    continue

                # Skip known header/footer lines
                if any(p.search(line_stripped) for p in skip_patterns):
                    continue

                # Check for new item start (1-4 digit item number at line start)
                item_match = item_start_pattern.match(line_stripped)
                if item_match:
                    # Finalize previous item
                    if current_item is not None:
                        finalize_item(current_item, description_lines, tax_lines_buffer, tax_patterns)
                        items.append(current_item)

                    item_num = item_match.group(1)
                    rest_of_line = item_match.group(2)
                    current_item = {
                        'pdf_name': pdf_name,
                        'item': item_num,
                        'material': '',
                        'part_number': '',
                        'quantity': '',
                        'unit': '',
                        'date': '',
                        'price_per_unit': '',
                        'amount': ''
                    }
                    description_lines = [rest_of_line]
                    tax_lines_buffer = []
                    fields_found = False
                    continue

                if current_item is None:
                    continue

                # Tax lines
                if any(kw in line_stripped for kw in ['Base Amount', 'Integrated GST', 'GST Comp CESS', 'Price(Net)']):
                    tax_lines_buffer.append(line_stripped)
                    continue

                # Field line (part number, qty, unit, date, price, amount)
                field_match = field_pattern.match(line_stripped)
                if field_match and not fields_found:
                    current_item['part_number'] = field_match.group(1).strip()
                    current_item['quantity'] = field_match.group(2).replace(',', '')
                    current_item['unit'] = field_match.group(3)
                    current_item['date'] = field_match.group(4)
                    current_item['price_per_unit'] = field_match.group(5).replace(',', '')
                    current_item['amount'] = field_match.group(6).replace(',', '')
                    fields_found = True
                    continue

                # Multi-line description: collect lines before the field line
                if not fields_found:
                    description_lines.append(line_stripped)

        # Finalize last item
        if current_item is not None:
            finalize_item(current_item, description_lines, tax_lines_buffer, tax_patterns)
            items.append(current_item)

    df = pd.DataFrame(items)

    col_order = ['pdf_name', 'item', 'material', 'part_number', 'quantity', 'unit',
                 'date', 'price_per_unit', 'amount', 'base_amount',
                 'igst_rate', 'igst_amount', 'cess_rate', 'cess_amount', 'net']
    col_order = [c for c in col_order if c in df.columns]
    df = df[col_order]

    numeric_cols = ['quantity', 'price_per_unit', 'amount', 'base_amount',
                    'igst_amount', 'cess_amount', 'net']
    for col in numeric_cols:
        if col in df.columns:
            df[col] = pd.to_numeric(df[col], errors='coerce').round(2)

    for col in ['igst_rate', 'cess_rate']:
        if col in df.columns:
            df[col] = pd.to_numeric(df[col], errors='coerce')

    return df


def finalize_item(item_dict, description_lines, tax_lines_buffer, tax_patterns):
    """Combine multi-line description and parse tax info into item dict."""
    # Join all description lines into one clean string
    item_dict['material'] = ' '.join(
        part.strip() for part in description_lines if part.strip()
    )

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


# ---------- Streamlit App ----------
st.set_page_config(page_title="PDF to Excel Converter", layout="wide")
st.title("📄 PDF Purchase Order to Excel Converter")
st.markdown(
    "Upload one or more PDF purchase orders. "
    "All data will be combined into a **single Excel sheet** with a `pdf_name` column to identify each source file."
)

uploaded_files = st.file_uploader(
    "Choose PDF files",
    type="pdf",
    accept_multiple_files=True
)

if uploaded_files:
    all_dfs = []
    progress_bar = st.progress(0)
    status_text = st.empty()

    for i, uploaded_file in enumerate(uploaded_files):
        status_text.text(f"Processing {uploaded_file.name}...")
        try:
            df = extract_items_from_pdf(uploaded_file, uploaded_file.name)
            all_dfs.append(df)
        except Exception as e:
            st.error(f"Error processing {uploaded_file.name}: {e}")
        progress_bar.progress((i + 1) / len(uploaded_files))

    status_text.text("✅ Processing complete!")

    if all_dfs:
        # Combine all PDFs into ONE DataFrame
        combined_df = pd.concat(all_dfs, ignore_index=True)

        st.subheader(f"Preview — {len(combined_df)} rows from {len(all_dfs)} file(s)")
        st.dataframe(combined_df.head(50), use_container_width=True)

        # Summary per file
        with st.expander("📊 Rows extracted per file"):
            summary = combined_df.groupby('pdf_name').size().reset_index(name='rows_extracted')
            st.dataframe(summary, use_container_width=True)

        # Write to a single Excel sheet named 'Purchase Orders'
        output = BytesIO()
        with pd.ExcelWriter(output, engine='xlsxwriter') as writer:
            combined_df.to_excel(writer, sheet_name='Purchase Orders', index=False)

            # Auto-fit column widths
            worksheet = writer.sheets['Purchase Orders']
            for col_idx, col in enumerate(combined_df.columns):
                max_len = max(
                    combined_df[col].astype(str).map(len).max(),
                    len(col)
                ) + 2
                worksheet.set_column(col_idx, col_idx, min(max_len, 60))

        output.seek(0)

        st.download_button(
            label="📥 Download Excel file",
            data=output,
            file_name="extracted_purchase_orders.xlsx",
            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
        )
    else:
        st.warning("No data could be extracted from the uploaded files.")
