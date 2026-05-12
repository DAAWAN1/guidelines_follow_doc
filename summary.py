import streamlit as st
from huggingface_hub import InferenceClient
import os

@st.cache_resource
def load_inference_client():
    token = os.getenv("HF_TOKEN")
    if not token:
        st.error("HF_TOKEN not found. Set it in .env.")
        st.stop()
    return InferenceClient(token=token)

def generate_summary_from_results(results: list, client) -> str:
    findings = ""
    for r in results:
        findings += f"- {r['status']} {r['rule']}: {r['explanation']}\n"
    prompt = f"""You are a compliance analyst. Given the following rule‑check results for a GSK Knowledge Article, write a short, flowing paragraph (max 150 words) summarising the overall compliance, highlighting major violations and warnings. Use plain English.

Results:
{findings}

Summary:"""
    try:
        completion = client.chat_completion(
            messages=[{"role": "user", "content": prompt}],
            model="katanemo/Arch-Router-1.5B",
            max_tokens=150,
            temperature=0.2,
        )
        return completion.choices[0].message["content"]
    except Exception as e:
        violated = [r for r in results if "Violated" in r["status"]]
        warnings = [r for r in results if "Warning" in r["status"]]
        summary = f"The article follows most rules but has {len(violated)} violations and {len(warnings)} warnings. "
        if violated:
            summary += "Violations: " + "; ".join([r["rule"] for r in violated[:5]]) + "."
        return summary