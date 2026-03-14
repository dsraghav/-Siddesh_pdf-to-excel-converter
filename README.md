# 📄 PDF Purchase Order to Excel Converter

A Streamlit web app that extracts item data from PDF purchase orders and exports them to Excel.

## Features
- Upload multiple PDF purchase orders at once
- Extracts item details: material, part number, quantity, unit, date, price, GST/CESS taxes
- Each PDF becomes a separate sheet in the output Excel file
- Preview extracted data before downloading

## Live Demo
> _Add your Streamlit Cloud URL here after deploying_

## Run Locally

```bash
pip install -r requirements.txt
streamlit run app.py
```

## Deploy on Streamlit Cloud
1. Fork or upload this repo to GitHub (must be **public**)
2. Go to [share.streamlit.io](https://share.streamlit.io)
3. Connect your GitHub repo
4. Set main file as `app.py`
5. Click **Deploy**
