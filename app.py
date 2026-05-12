import streamlit as st
import html
from config import init_config
from utils import shorten_filename
from extraction import extract_text_and_images
from compliance import check_article_compliance
from summary import load_inference_client, generate_summary_from_results

# ------------------------------------------------------------------
# Initialize app config (env, CSS, page settings)
# ------------------------------------------------------------------
init_config()

# ------------------------------------------------------------------
# Logo
# ------------------------------------------------------------------
st.image("GSK_LOGO.png", width=150)

# ------------------------------------------------------------------
# Session state
# ------------------------------------------------------------------
if "processed_files" not in st.session_state:
    st.session_state.processed_files = {}
if "selected_file" not in st.session_state:
    st.session_state.selected_file = None

# ------------------------------------------------------------------
# Main UI
# ------------------------------------------------------------------
st.header("Upload GSK Knowledge Article PDFs")

uploaded_files = st.file_uploader(
    """Upload one or more **GSK Knowledge Article PDFs** to check compliance.
    The app validates headings, tables, screenshots, notes, attachments, plain language,
    AQI checklist, and required sections (Audience, Prerequisites, Keywords, etc.).
    """,
    type=["pdf"],
    accept_multiple_files=True,
    key="article_uploader",
)

if uploaded_files:
    for file in uploaded_files:
        if file.name not in st.session_state.processed_files or True:
            with st.spinner(f"Processing {file.name}..."):
                text, img_count = extract_text_and_images(file)
                st.session_state.processed_files[file.name] = {
                    "text": text,
                    "image_count": img_count,
                    "results": None
                }

file_names = list(st.session_state.processed_files.keys())
if file_names and (st.session_state.selected_file is None or st.session_state.selected_file not in file_names):
    st.session_state.selected_file = file_names[0]

# Sidebar
st.sidebar.title("Uploaded Documents")
file_names = list(st.session_state.processed_files.keys())
selected_file = st.session_state.get("selected_file", None)

if file_names:
    if selected_file and selected_file in file_names:
        st.sidebar.markdown(
            f'<div style="background-color: white; color: black; padding: 15px; '
            f'border-radius: 4px; margin-bottom: 10px; font-weight: 500;">'
            f'Selected: {html.escape(selected_file)}'
            f'</div>',
            unsafe_allow_html=True
        )

    st.sidebar.markdown("---")
    for file in file_names:
        is_active = (selected_file == file)
        label = ("► " if is_active else "") + shorten_filename(file)
        btn_type = "primary" if is_active else "secondary"
        if st.sidebar.button(label, key=f"btn_{file}", type=btn_type):
            st.session_state.selected_file = file
else:
    st.sidebar.markdown(
        f'<div style="background-color: #A9A9A9; color: black; padding: 15px; '
        f'border-radius: 4px; margin-top: 10px;">'
        f'No documents uploaded yet.'
        f'</div>',
        unsafe_allow_html=True
    )

# Main area
if selected_file and selected_file in st.session_state.processed_files:
    file_data = st.session_state.processed_files[selected_file]
    article_text = file_data["text"]
    image_count = file_data["image_count"]

    if not article_text.strip():
        st.error(f"No text could be extracted from {selected_file}. Please check the file.")
    else:
        st.subheader(f"Compliance Analysis: {selected_file}")

        if file_data["results"] is None:
            with st.spinner("Running all rule checks..."):
                results = check_article_compliance(article_text, has_images=(image_count > 0))
            st.session_state.processed_files[selected_file]["results"] = results
        else:
            results = file_data["results"]

        passed = [r for r in results if "Followed" in r["status"]]
        warnings = [r for r in results if "Warning" in r["status"] or "Undetermined" in r["status"] or "Not applicable" in r["status"] or "Info" in r["status"]]
        violated = [r for r in results if "Violated" in r["status"]]

        tab1, tab2, tab3 = st.tabs([
            f" Passed ({len(passed)})",
            f" Warnings ({len(warnings)})",
            f" Violated ({len(violated)})"
        ])

        with tab1:
            if passed:
                for r in passed:
                    with st.expander(f"{r['rule']}"):
                        st.write(r["explanation"])
            else:
                st.info("No passed guidelines found.")

        with tab2:
            if warnings:
                for r in warnings:
                    with st.expander(f"{r['rule']}"):
                        st.write(r["explanation"])
            else:
                st.info("No warnings or undetermined items.")

        with tab3:
            if violated:
                for r in violated:
                    with st.expander(f"{r['rule']}"):
                        st.write(r["explanation"])
            else:
                st.info("No violations – excellent!")

        st.write("### Summary")
        client = load_inference_client()
        summary = generate_summary_from_results(results, client)
        st.markdown(
            f'<div style="background-color: #f0f2f6; color: black; padding: 15px; border-radius: 4px; margin-top: 10px;">'
            f'{html.escape(summary)}'
            f'</div>',
            unsafe_allow_html=True
        )

        report_text = "\n\n".join(
            f"{r['status']} {r['rule']}\n{r['explanation']}" for r in results
        )
        st.download_button(
            f"Download Report",
            data=report_text,
            file_name=f"compliance_report_{selected_file}.txt",
            mime="text/plain",
            type="primary",
        )
else:
    st.markdown(
        f'<div style="background-color: #f0f2f6; color: black; padding: 15px; '
        f'border-radius: 4px; margin-top: 10px;">'
        f'Please upload PDFs to begin compliance checking. Use the sidebar to select a document after uploading.'
        f'</div>',
        unsafe_allow_html=True
    )