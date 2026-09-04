"""
ui.py
"""

import io
 
import pandas as pd
import plotly.graph_objects as go
import streamlit as st

import base64
from pathlib import Path
 
# Accent colors (Jeju-inspired palette)
LEAF_GREEN = "#457534"
TANGERINE = "#F58F1F"
CHART_BG = "#FAF8F3"
 
 
def get_sheet_names(uploaded_file):
    name = uploaded_file.name.lower()
    if name.endswith((".xlsx", ".xls")):
        uploaded_file.seek(0)
        excel_file = pd.ExcelFile(uploaded_file)
        return excel_file.sheet_names
    return None
 
 
def read_raw_table(uploaded_file, sheet_name=None, n_rows=60) -> pd.DataFrame:
    uploaded_file.seek(0)
    name = uploaded_file.name.lower()
    if name.endswith((".xlsx", ".xls")):
        df = pd.read_excel(uploaded_file, sheet_name=sheet_name, header=None, nrows=n_rows)
    else:
        try:
            df = pd.read_csv(uploaded_file, header=None, nrows=n_rows, comment="#", sep=None, engine="python")
        except pd.errors.ParserError:
            uploaded_file.seek(0)
            df = pd.read_csv(
                uploaded_file, header=None, nrows=n_rows, comment="#",
                sep=None, engine="python", on_bad_lines="skip",
            )
    df.columns = [f"Column {i + 1}" for i in range(df.shape[1])]
    df.index = df.index + 1
    return df
 
 
def read_uploaded_profile(uploaded_file, sheet_name=None, column_index=0, start_row=0, end_row=None) -> pd.Series:
    uploaded_file.seek(0)
    name = uploaded_file.name.lower()
    if name.endswith((".xlsx", ".xls")):
        df = pd.read_excel(uploaded_file, sheet_name=sheet_name, header=None)
    else:
        try:
            df = pd.read_csv(uploaded_file, header=None, comment="#", sep=None, engine="python")
        except pd.errors.ParserError:
            uploaded_file.seek(0)
            df = pd.read_csv(
                uploaded_file, header=None, comment="#",
                sep=None, engine="python", on_bad_lines="skip",
            )

    column = df.iloc[start_row:end_row, column_index]
    numeric = pd.to_numeric(column, errors="coerce")
    return numeric.dropna().reset_index(drop=True)
 
 
def validate_uploaded_profiles(uploaded_files, sheet_name=None, column_index=0, start_row=0, end_row=None) -> pd.DataFrame:
    rows = []
    for f in uploaded_files:
        try:
            series = read_uploaded_profile(
                f, sheet_name=sheet_name, column_index=column_index, start_row=start_row, end_row=end_row
            )
            rows.append({"File": f.name, "Values read": len(series)})
        except Exception as exc:
            rows.append({"File": f.name, "Values read": f"Error: {exc}"})
    return pd.DataFrame(rows)
 
 
def make_comparison_chart(original: pd.Series, adjusted: pd.Series) -> go.Figure:
    """Builds the zoomable Plotly chart: original vs. adjusted profile."""
    x = list(range(len(original)))
    fig = go.Figure()
    fig.add_trace(go.Scatter(
        x=x, y=original, mode="lines", name="Original",
        line=dict(color=LEAF_GREEN, width=2),
    ))
    fig.add_trace(go.Scatter(
        x=x, y=adjusted, mode="lines", name="With diversity applied",
        line=dict(color=TANGERINE, width=2),
    ))
    fig.update_layout(
        xaxis_title="Time step",
        yaxis_title="Load",
        legend=dict(orientation="h", yanchor="bottom", y=1.02, x=0),
        margin=dict(l=10, r=10, t=10, b=10),
        height=420,
        plot_bgcolor=CHART_BG,
        paper_bgcolor=CHART_BG,
    )
    fig.update_xaxes(showgrid=True, gridcolor="#E2DCCD")
    fig.update_yaxes(showgrid=True, gridcolor="#E2DCCD")
    return fig
 
 
def build_result_csv(original: pd.Series, adjusted: pd.Series) -> str:
    buffer = io.StringIO()
    pd.DataFrame({
        "original": pd.Series(original).reset_index(drop=True),
        "with_diversity_factor": pd.Series(adjusted).reset_index(drop=True),
    }).to_csv(buffer, index=False)
    return buffer.getvalue()
 
 
def build_individual_profiles_csv(shifted_profiles: list, file_names: list) -> str:
    buffer = io.StringIO()
    data = {
        name: pd.Series(profile).reset_index(drop=True)
        for name, profile in zip(file_names, shifted_profiles)
    }
    pd.DataFrame(data).to_csv(buffer, index=False)
    return buffer.getvalue()
 
def render_placeholder_message(text: str):
    st.markdown(
        f"""
        <div style="
            background-color: #DDE7D2;
            border: 1px solid {LEAF_GREEN};
            border-radius: 10px;
            padding: 14px 18px;
            color: #363636;
            font-size: 0.95rem;
            line-height: 1.5;
        ">
            {text}
        </div>
        <div style="height: 16px;"></div>
        """,
        unsafe_allow_html=True,
    )
 
 
def render_warning_message(text: str):
    st.markdown(
        f"""
        <div style="
            background-color: #FBE2C0;
            border: 1px solid {TANGERINE};
            border-radius: 10px;
            padding: 14px 18px;
            color: #363636;
            font-size: 0.95rem;
            line-height: 1.5;
        ">
            ⚠️ {text}
        </div>
        <div style="height: 12px;"></div>
        """,
        unsafe_allow_html=True,
    )


def saturation_hint(tau: float, window_max: float = 1.0) -> str:
    n50 = 0.69 * tau
    n90 = 2.3 * tau

    return (
        f"Lower values spread the peaks over a wider time range sooner, "
        f"while higher values keep them closer together for longer. "
        f"With τ={tau:.0f}, the time-shift range reaches about 50% of its "
        f"maximum at {n50:.0f} buildings and 90% at {n90:.0f} buildings."
    )

def render_pdf_viewer(pdf_path: Path, height: int = 800):
    if not pdf_path.exists():
        st.warning(f"Documentation file not found: {pdf_path.name}")
        return

    pdf_bytes = pdf_path.read_bytes()

    st.download_button(
        label="Download documentation (PDF)",
        data=pdf_bytes,
        file_name=pdf_path.name,
        mime="application/pdf",
    )

    base64_pdf = base64.b64encode(pdf_bytes).decode("utf-8")
    st.markdown(
        f"""
        <iframe
            src="data:application/pdf;base64,{base64_pdf}"
            width="100%"
            height="{height}"
            style="border: 1px solid #E2DCCD; border-radius: 8px;"
            type="application/pdf">
        </iframe>
        """,
        unsafe_allow_html=True,
    )