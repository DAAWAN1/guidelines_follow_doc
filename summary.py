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
    # Build a simple numbered list of findings for the prompt
    findings_lines = []
    for r in results:
        # Use plain-text status labels
        if "Violated" in r["status"]:
            label = "[VIOLATION]"
        elif "Warning" in r["status"]:
            label = "[WARNING]"
        else:
            label = "[OK]"
        findings_lines.append(f"{label} {r['rule']}: {r['explanation']}")

    findings = "\n".join(findings_lines)

    prompt = f"""You are a compliance analyst. Write a short summary (max 150 words) of the following rule‑check results for a GSK Knowledge Article.
- First, list every violation as a bullet point.
- Then list the most important warnings (up to 5) as bullet points.
- Use only plain bullet points (no sub‑headings, no numbering, no markdown like **bold**).
- Do not add any introductory or closing sentences.

Results:
{findings}

Summary:"""

    try:
        completion = client.chat_completion(
            messages=[{"role": "user", "content": prompt}],
            model="katanemo/Arch-Router-1.5B",
            max_tokens=250,
            temperature=0.2,
        )
        raw = completion.choices[0].message["content"].strip()

        # Clean up common model artifacts
        raw = raw.replace("**", "")               # strip bold
        raw = re.sub(r"^#+\s*", "", raw)          # remove any leading headers like "## Violations"
        raw = re.sub(r"\n#+\s*", "\n", raw)
        # Ensure bullet points start with "- "
        if not raw.startswith("- "):
            # try to prepend a dash
            raw = "- " + raw
        # If the model produced no bullet points at all, fallback
        if "- " not in raw:
            raise ValueError("No bullet points found")

        return raw

    except Exception:
        # Clean fallback
        violated = [r for r in results if "Violated" in r["status"]]
        warnings = [r for r in results if "Warning" in r["status"]]

        lines = []
        if violated:
            lines.append("Violations:")
            lines.extend(f"- {r['rule']}" for r in violated)
        if warnings:
            lines.append("Major Warnings:")
            lines.extend(f"- {r['rule']}" for r in warnings[:5])
        return "\n".join(lines)