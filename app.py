import streamlit as st
import html
from config import init_config
from utils import shorten_filename
from compliance import check_article_compliance
from summary import load_inference_client, generate_summary_from_results
from extraction import extract_text, extract_rich_docx_data

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
    """Upload one or more **GSK Kno wledge Article** files (PDF or DOCX) to check compliance.
    The app validates headings, tables, screenshots, notes, attachments, plain language,
    AQI checklist, and required sections (Audience, Prerequisites, Keywords, etc.).
    """,
    type=["pdf", "docx"],   # ← only change here
    accept_multiple_files=True,
    key="article_uploader",
)

if uploaded_files:
    for file in uploaded_files:
        if file.name not in st.session_state.processed_files or True:
            with st.spinner(f"Processing {file.name}..."):
                # Determine file type
                is_docx = file.name.lower().endswith('.docx')
                
                if is_docx:
                    # Extract rich formatting data
                    rich_data = extract_rich_docx_data(file)
                    # Plain text is taken from the rich data (we added 'full_text')
                    text = rich_data.get("full_text", "")
                    # Store both
                    st.session_state.processed_files[file.name] = {
                        "text": text,
                        "rich_data": rich_data,   # <-- new key
                        "results": None
                    }
                else:
                    # PDF: only plain text available
                    text = extract_text(file)
                    st.session_state.processed_files[file.name] = {
                        "text": text,
                        "rich_data": None,        # <-- no rich data for PDF
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
        f'<div style="background-color: #C4C4C4; color: black; padding: 15px; '
        f'border-radius: 4px; margin-top: 10px;">'
        f'No documents uploaded yet.'
        f'</div>',
        unsafe_allow_html=True
    )

# Main area
if selected_file and selected_file in st.session_state.processed_files:
    file_data = st.session_state.processed_files[selected_file]
    article_text = file_data["text"]

    if not article_text.strip():
        st.error(f"No text could be extracted from {selected_file}. Please check the file.")
    else:
        st.subheader(f"Compliance Analysis: {selected_file}")

        if file_data["results"] is None:
            with st.spinner("Running all rule checks..."):
                rich_data = file_data.get("rich_data", None)
                results = check_article_compliance(article_text, doc_data=rich_data)
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
        # Summary (displayed on screen) -----------------------------------------------
        st.subheader("Summary")
        client = load_inference_client()
        summary = generate_summary_from_results(results, client)

        # Helper: convert a simple markdown string with bullet lists to HTML
        def simple_md_to_html(text: str) -> str:
            lines = text.split('\n')
            html_parts = []
            in_list = False
            for line in lines:
                stripped = line.strip()
                if stripped.startswith('- '):
                    if not in_list:
                        html_parts.append('<ul>')
                        in_list = True
                    html_parts.append(f'<li>{stripped[2:]}</li>')
                else:
                    if in_list:
                        html_parts.append('</ul>')
                        in_list = False
                    if stripped:
                        html_parts.append(f'<p>{stripped}</p>')
            if in_list:
                html_parts.append('</ul>')
            return ''.join(html_parts)

        summary_html = simple_md_to_html(summary)

        st.markdown(
            f"""<div style="background-color: #f0f2f6; color: black; padding: 20px;
            border-radius: 4px; margin-top: 10px;">
            {summary_html}
            </div>""",
            unsafe_allow_html=True
        )

        # Build downloadable report text
        report_parts = []
        report_parts.append("=== COMPLIANCE SUMMARY ===")
        report_parts.append(summary)
        report_parts.append("\n=== DETAILED RESULTS ===\n")

        # Add all individual checks
        for r in results:
            report_parts.append(f"{r['status']} {r['rule']}")
            report_parts.append(f"   {r['explanation']}")
            report_parts.append("")   # blank line

        report_text = "\n".join(report_parts)

        # Download button
        st.download_button(
            label="Download Report",
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