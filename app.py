import streamlit as st
import pdfplumber
import re
import pandas as pd
from io import BytesIO
import numpy as np

# ---------- Extraction function ----------
def extract_items_from_pdf(pdf_file, pdf_name):
    items = []
    current_item = None
    tax_lines_buffer = []

    tax_patterns = {
        'base': re.compile(r'Base Amount\s+([\d,]+\.?\d*)\s+INR'),
        'igst': re.compile(r'IN:\s*Integrated GST\s+(\d+\.?\d*)%\s+([\d,]+\.?\d*)'),
        'cess': re.compile(r'IN:\s*GST Comp CESS\s+(\d+\.?\d*)%\s+([\d,]+\.?\d*)'),
        'net': re.compile(r'Price\(Net\)\s+([\d,]+\.?\d*)')
    }

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

                item_match = re.match(r'^(\d+)\s+(.*)', line)
                if item_match:
                    if current_item is not None:
                        tax_text = ' '.join(tax_lines_buffer)
                        parse_tax_lines(current_item, tax_text, tax_patterns)
                        items.append(current_item)
                        tax_lines_buffer = []

                    item_num = item_match.group(1)
                    rest = item_match.group(2)
                    current_item = {
                        'item': item_num,
                        'main_line': rest,
                        'pdf_name': pdf_name
                    }
                else:
                    if current_item is not None:
                        if any(k in line for k in ['Base Amount', 'Integrated GST', 'GST Comp CESS', 'Price(Net)']):
                            tax_lines_buffer.append(line)

        if current_item is not None:
            tax_text = ' '.join(tax_lines_buffer)
            parse_tax_lines(current_item, tax_text, tax_patterns)
            items.append(current_item)

    df = pd.DataFrame(items)
    if 'main_line' in df.columns:
        df.drop(columns=['main_line'], inplace=True)

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

    if 'igst_rate' in df.columns:
        df['igst_rate'] = pd.to_numeric(df['igst_rate'], errors='coerce')
    if 'cess_rate' in df.columns:
        df['cess_rate'] = pd.to_numeric(df['cess_rate'], errors='coerce')

    return df


def parse_tax_lines(item_dict, tax_text, patterns):
    main = item_dict['main_line']
    parse_main_line(item_dict, main)

    base_match = patterns['base'].search(tax_text)
    if base_match:
        item_dict['base_amount'] = base_match.group(1).replace(',', '')

    igst_match = patterns['igst'].search(tax_text)
    if igst_match:
        item_dict['igst_rate'] = igst_match.group(1)
        item_dict['igst_amount'] = igst_match.group(2).replace(',', '')

    cess_match = patterns['cess'].search(tax_text)
    if cess_match:
        item_dict['cess_rate'] = cess_match.group(1)
        item_dict['cess_amount'] = cess_match.group(2).replace(',', '')

    net_match = patterns['net'].search(tax_text)
    if net_match:
        item_dict['net'] = net_match.group(1).replace(',', '')


def parse_main_line(item_dict, main_line):
    main_line = main_line.replace('&amp;', '&')

    pattern = re.compile(
        r'^(.*?)\s+(\d+\s*-\s*MA)\s+([\d,]+\.?\d*)\s+(\w+)\s+(\d{2}\.\d{2}\.\d{4})\s+([\d,]+\.?\d*)(?:\s+([\d,]+\.?\d*))?$'
    )
    match = pattern.match(main_line)
    if match:
        item_dict['material'] = match.group(1).strip()
        item_dict['part_number'] = match.group(2).strip()
        item_dict['quantity'] = match.group(3).replace(',', '')
        item_dict['unit'] = match.group(4).strip()
        item_dict['date'] = match.group(5).strip()
        item_dict['price_per_unit'] = match.group(6).replace(',', '')
        item_dict['amount'] = match.group(7).replace(',', '') if match.group(7) else match.group(6).replace(',', '')
    else:
        item_dict['material'] = main_line
        item_dict['part_number'] = ''
        item_dict['quantity'] = ''
        item_dict['unit'] = ''
        item_dict['date'] = ''
        item_dict['price_per_unit'] = ''
        item_dict['amount'] = ''


# ---------- Streamlit app ----------
st.set_page_config(page_title="PDF to Excel Converter", layout="wide")
st.title("📄 PDF Purchase Order to Excel Converter")
st.markdown("Upload one or more PDF purchase orders. Each PDF will become a separate sheet in the output Excel file.")

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
            sheet_name = uploaded_file.name.rsplit('.', 1)[0][:31]
            all_dfs[sheet_name] = df
        except Exception as e:
            st.error(f"Error processing {uploaded_file.name}: {e}")
        progress_bar.progress((i + 1) / len(uploaded_files))

    status_text.text("Processing complete!")

    if all_dfs:
        st.subheader("Preview of extracted data")
        for sheet_name, df in all_dfs.items():
            with st.expander(f"📄 {sheet_name}"):
                st.dataframe(df.head(10))

        output = BytesIO()
        with pd.ExcelWriter(output, engine='xlsxwriter') as writer:
            for sheet_name, df in all_dfs.items():
                df.to_excel(writer, sheet_name=sheet_name, index=False)
        output.seek(0)

        st.download_button(
            label="📥 Download Excel file",
            data=output,
            file_name="extracted_purchase_orders.xlsx",
            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
        )
    else:
        st.warning("No data could be extracted from the uploaded files.")
