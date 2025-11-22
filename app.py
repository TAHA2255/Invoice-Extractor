import streamlit as st
from PIL import Image
import io
import pandas as pd
import base64
import os
import json
from pdf2image import convert_from_bytes
from openai import OpenAI
from dotenv import load_dotenv
import httpx

load_dotenv()

# ---- CONFIG ----

# Disable Render proxy env vars
for p in ["HTTP_PROXY", "HTTPS_PROXY", "ALL_PROXY", "http_proxy", "https_proxy", "all_proxy"]:
    os.environ.pop(p, None)
OPENAI_API_KEY = os.environ.get("OPENAI_API_KEY")


transport = httpx.HTTPTransport(proxy=None)

client = OpenAI(
    api_key=OPENAI_API_KEY,
    http_client=httpx.Client(transport=transport)
)
MODEL = "gpt-4.1"

st.title("Invoice To Excel Extractor")


uploaded = st.file_uploader("Upload invoice (PDF or Image)", type=["png","jpg","jpeg","pdf"])


# Convert PIL image → Base64 Data URL
def pil_to_data_url(pil_img):
    buffered = io.BytesIO()
    pil_img.save(buffered, format="PNG")
    img_bytes = buffered.getvalue()
    base64_str = base64.b64encode(img_bytes).decode("utf-8")
    return f"data:image/png;base64,{base64_str}"


def call_llm_with_image(data_url):
    system_prompt = """
    You are an invoice parser. 
    Extract ONLY line items. Return STRICT JSON array.

    Format:
    [
      {
        "Quantity": "...",
        "Unit": "...",
        "Product": "...",
        "Unit Price": "...",
        "Line Total": "..."
      }
    ]
    """

    resp = client.responses.create(
        model=MODEL,
        input=[
            {"role": "system", "content": system_prompt},
            {"role": "user",
             "content": [
                 {"type": "input_image", "image_url": data_url}
             ]
            },
        ],
        max_output_tokens=1500,
        temperature=0
    )

    return resp.output_text


if uploaded:
    pages = []

    # If PDF → convert to images
    if uploaded.type == "application/pdf":
        pdf_bytes = uploaded.read()
        pages = convert_from_bytes(pdf_bytes)
    else:
        pages = [Image.open(uploaded)]

    st.write(f"Detected **{len(pages)} page(s)**")

    all_items = []

    if st.button("Extract & Download Excel"):
        for i, page in enumerate(pages):
            st.write(f"Processing page {i+1}...")

            data_url = pil_to_data_url(page)
            extracted = call_llm_with_image(data_url)

            try:
                items = json.loads(extracted)
                all_items.extend(items)
            except:
                st.error(f"LLM returned invalid JSON on page {i+1}:")
                st.code(extracted)

        # Convert all items into DataFrame
        df = pd.DataFrame(all_items)

        buffer = io.BytesIO()
        df.to_excel(buffer, index=False, engine="openpyxl")
        buffer.seek(0)

        st.success("Extraction complete! Download below.")
        st.download_button(
            "Download Excel File",
            data=buffer,
            file_name="invoice_output.xlsx",
            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
        )
