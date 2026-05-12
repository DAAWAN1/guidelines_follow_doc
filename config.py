import streamlit as st
from dotenv import load_dotenv
import os

def init_config():
    """Load .env, set page config, inject custom CSS."""
    load_dotenv()
    if os.getenv("HF_TOKEN"):
        os.environ["HF_TOKEN"] = os.getenv("HF_TOKEN")

    st.set_page_config(page_title="GSK Document Intelligence", layout="wide")

    # First custom CSS block
    st.markdown(
        """
        <style>
        .stApp {
            background-color: white;
            color: #31333F;
        }
        section[data-testid="stSidebar"] div.stAlert {
            background-color: #f0f2f6 !important;
            color: black !important;
            border-color: #f0f2f6 !important;
        }
        div[data-testid="stExpander"] details summary {
            background-color: #F36633 !important;
            color: white !important;
            border-radius: 4px;
            padding: 8px 12px;
            font-weight: bold;
        }
        div[data-testid="stExpander"] details div[data-testid="stExpanderDetails"] {
            background-color: white !important;
            color: #31333F !important;
            padding: 12px;
        }
        div.stAlert {
            background-color: #f29d80 !important;
            color: white !important;
            border-color: #f29d80 !important;
        }
        div.stAlert p, div.stAlert span, div.stAlert div {
            color: white !important;
        }
        input[type="file"]::file-selector-button {
            background-color: #F36633 !important;
            color: white !important;
            border: 1px solid #F36633 !important;
            border-radius: 4px;
            padding: 4px 12px;
            font-weight: bold;
        }
        input[type="file"]::file-selector-button:hover {
            background-color: #e0552a !important;
            border-color: #e0552a !important;
        }
        button[kind="primary"] {
            background-color: #F36633 !important;
            color: white !important;
            border-color: #F36633 !important;
        }
        button[kind="primary"]:hover {
            background-color: #e0552a !important;
            border-color: #e0552a !important;
            color: white !important;
        }
        div[data-testid="stTabs"] div[role="tabpanel"] {
            max-height: 300px !important;
            overflow-y: auto !important;
            background-color: white !important;
            padding: 15px 20px !important;
            border-radius: 4px;
            box-shadow: 0 2px 8px rgba(0,0,0,0.08);
            margin-top: 0;
        }
        div[data-testid="stTabs"] [role="tablist"] {
            display: grid !important;
            grid-template-columns: 1fr 1fr 1fr;
            width: 100%;
        }
        div[data-testid="stTabs"] [role="tablist"] button[role="tab"] {
            width: 100% !important;
            text-align: center;
            justify-content: center;
        }
        [data-testid="stHeader"] {
            display: none;
        }
        </style>
        """,
        unsafe_allow_html=True,
    )

    # Second custom CSS block (sidebar buttons)
    st.markdown(
        """
        <style>
        section[data-testid="stSidebar"] button[kind="secondary"],
        section[data-testid="stSidebar"] button[kind="primary"] {
            background-color: #F36633 !important;
            color: white !important;
            border-color: #F36633 !important;
            width: 100%;
            text-align: left;
            padding: 0.5rem;
            margin-bottom: 0.2rem;
        }
        section[data-testid="stSidebar"] button[kind="secondary"]:hover,
        section[data-testid="stSidebar"] button[kind="primary"]:hover {
            background-color: #e0552a !important;
            color: white !important;
        }
        section[data-testid="stSidebar"] button[kind="primary"].selected-button {
            border: 2px solid white;
            font-weight: bold;
        }
        </style>
        """,
        unsafe_allow_html=True,
    )