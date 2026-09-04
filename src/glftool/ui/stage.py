"""
stage.py

"""

import pandas as pd
import streamlit as st
from pathlib import Path

from glftool.models import DiversityFactorShiftTool, DiversityFactorTool
from glftool.ui.ui import (
    build_individual_profiles_csv,
    build_result_csv,
    get_sheet_names,
    make_comparison_chart,
    read_raw_table,
    read_uploaded_profile,
    render_pdf_viewer,
    render_placeholder_message,
    render_warning_message,
    saturation_hint,
    validate_uploaded_profiles,
)


def _render_sheet_and_column_picker(sample_file):
    sheet_names = get_sheet_names(sample_file)
    sheet_name = None
    if sheet_names and len(sheet_names) > 1:
        sheet_name = st.selectbox("Sheet", options=sheet_names)
    elif sheet_names:
        sheet_name = sheet_names[0]
 
    raw_table = read_raw_table(sample_file, sheet_name=sheet_name)
 
    col1, col2, col3 = st.columns(3)
    with col1:
        column_number = st.number_input(
            "Column number with load values",
            min_value=1, max_value=raw_table.shape[1], value=1, step=1,
        )
    with col2:
        row_number = st.number_input(
            "Row where the time series starts",
            min_value=1, value=1, step=1,
            help="Row number as shown in the preview table below.",
        )
    with col3:
        end_row_number = st.number_input(
            "End row (optional)",
            min_value=0, value=0, step=1,
            help="Leave at 0 to read to the end of the file. Set a row to stop there instead.",
        )

    column_index = column_number - 1
    start_row = row_number - 1
    end_row = None if end_row_number == 0 else end_row_number
    col_name = raw_table.columns[column_index]
 

    numeric_from_selection = pd.to_numeric(raw_table.loc[row_number:, col_name], errors="coerce")
    first_valid_row = numeric_from_selection.first_valid_index()
 
    if first_valid_row is None:
        st.caption(
            f"No numeric values found in column {column_number} at or below row {row_number}. "
            "Try a different column or row - see the preview below."
        )
        st.dataframe(raw_table, height=250)
    else:
        if first_valid_row != row_number:
            st.caption(
                f"Row {row_number} has no number in this column - starting automatically "
                f"at row {first_valid_row}, the first row with a real value."
            )
        else:
            st.caption(
                "Preview of the uploaded file - the highlighted cells below show "
                "exactly what will be read as the time series."
            )
 
        def _highlight(data):
            styles = pd.DataFrame("", index=data.index, columns=data.columns)
            mask = data.index >= first_valid_row
            styles.loc[mask, col_name] = "background-color: #FBE2C0"
            return styles
 
        st.dataframe(raw_table.style.apply(_highlight, axis=None), height=250)

        try:
            preview_series = read_uploaded_profile(
                sample_file, sheet_name=sheet_name, column_index=column_index,
                start_row=start_row, end_row=end_row,
            )
            st.caption(f"Values that will be read: {len(preview_series)}")
        except Exception:
            pass

    return sheet_name, column_index, start_row, end_row


def _render_inputs():
    st.subheader("1. Choose approach")
    approach = st.radio(
        label="Approach",
        options=["Scaling approach (Winter)", "Shift approach"],
        label_visibility="collapsed",
    )
 
    if approach == "Scaling approach (Winter)":
        st.caption(
            "The diversity factor is calculated according to [Winter’s approach](https://www.verenum.ch/Dokumente/2001_Winter-Gleichzeitig.pdf). - only the diversity-factor formula comes from that paper. "
            "How the resulting peak reduction is then spread across nearby time steps is our own implementation, not part of Winter's original method."
        )
    else:
        st.caption(
            "Each building profile is randomly shifted within a time window. "
            "The window grows with the number of buildings, up to the maximum "
            "you set below. This reduces the overlap of individual peaks and "
            "therefore lowers the peak of the aggregated profile."
        )
 
    st.subheader("2. Settings")
 
    values = {"approach": approach, "sheet_name": None, "column_index": 0, "start_row": 0, "end_row": None}
 
    if approach == "Scaling approach (Winter)":
        values["a_value"] = st.slider(
            "Lower limit of diversity factor",
            min_value=0.0, max_value=1.0, value=0.45, step=0.01,
        )
        st.caption(
            "Controls how strongly the load peaks are reduced. "
            "Lower values result in stronger peak reduction, "
            "while higher values result in weaker peak reduction."
        )
        values["resolution_minutes"] = st.selectbox(
            "Time resolution",
            options=[60, 15, 1],
            format_func=lambda m: {60: "hourly", 15: "15-minute", 1: "1-minute"}[m],
        )
    else:
        values["resolution_minutes"] = st.selectbox(
            "Time resolution",
            options=[60, 15, 1],
            format_func=lambda m: {60: "hourly", 15: "15-minute", 1: "1-minute"}[m],
        )
        values["window_max"] = st.slider(
            "Maximum time window (h)",
            min_value=0.25, max_value=4.0, value=1.0, step=0.25,
            help="The upper limit the shift window can grow towards as the "
                 "number of buildings increases.",
        )
        values["tau"] = st.slider(
            "Saturation speed (τ)",
            min_value=10, max_value=250, value=80, step=5,
        )
        st.caption(saturation_hint(values["tau"], window_max=values["window_max"]))
 
    st.subheader("3. Upload profiles")
 
    if approach == "Scaling approach (Winter)":
        input_type = st.radio(
            "Input type",
            options=["Aggregated profile", "Individual profiles"],
            horizontal=True,
        )
        values["winter_input_type"] = input_type
 
        if input_type == "Aggregated profile":
            st.caption("An already aggregated profile (one file).")
            values["uploaded_files"] = st.file_uploader(
                "Aggregated profile (.csv or .xlsx)", type=["csv", "xlsx", "xls"], accept_multiple_files=False,
            )
            if values["uploaded_files"] is not None:
                values["sheet_name"], values["column_index"], values["start_row"], values["end_row"] = _render_sheet_and_column_picker(
                    values["uploaded_files"]
                )
            values["n_buildings"] = st.number_input(
                "Number of buildings in profile", min_value=2, value=50, step=1,
            )
            if values["n_buildings"] > 200:
                render_warning_message(
                    "Winter's formula was empirically validated for up to 200 "
                    "buildings. It still works for larger numbers, but the "
                    "result is an extrapolation beyond the tested range. If "
                    "you're not satisfied with the result, try choosing a "
                    "higher value for the diversity-factor parameter above."
                )
        else:
            st.caption("Individual building profiles (one file per building).")
            render_warning_message(
                "Please make sure all uploaded files share the same structure "
                "(same column position, same starting row) - e.g. all exported "
                "from the same program. Files with a different layout may be "
                "read incorrectly."
            )
            values["uploaded_files"] = st.file_uploader(
                "Individual profiles (.csv or .xlsx)", type=["csv", "xlsx", "xls"], accept_multiple_files=True,
            )
            if values["uploaded_files"]:
                values["sheet_name"], values["column_index"], values["start_row"], values["end_row"] = _render_sheet_and_column_picker(
                    values["uploaded_files"][0]
                )
                if len(values["uploaded_files"]) > 200:
                    render_warning_message(
                        "Winter's formula was empirically validated for up to 200 "
                        "buildings. It still works for larger numbers, but the "
                        "result is an extrapolation beyond the tested range. If "
                        "you're not satisfied with the result, try choosing a "
                        "higher value for the diversity-factor parameter above."
                    )
                if len(values["uploaded_files"]) > 1:
                    st.caption(
                        "These settings (column/row) are applied to ALL uploaded "
                        "files below. Check that every file was read correctly - "
                        "especially if they come from different sources/programs:"
                    )
                    st.dataframe(
                        validate_uploaded_profiles(
                            values["uploaded_files"],
                            sheet_name=values["sheet_name"],
                            column_index=values["column_index"],
                            start_row=values["start_row"],
                            end_row=values["end_row"],
                        ),
                        hide_index=True,
                    )
    else:
        st.caption("Individual building profiles (one file per building).")
        render_warning_message(
            "Please make sure all uploaded files share the same structure "
            "(same column position, same starting row) - e.g. all exported "
            "from the same program. Files with a different layout may be "
            "read incorrectly."
        )
        values["uploaded_files"] = st.file_uploader(
            "Individual profiles (.csv or .xlsx)", type=["csv", "xlsx", "xls"], accept_multiple_files=True,
        )
        if values["uploaded_files"]:
            values["sheet_name"], values["column_index"], values["start_row"], values["end_row"] = _render_sheet_and_column_picker(
                values["uploaded_files"][0]
            )
            if len(values["uploaded_files"]) > 1:
                st.caption(
                    "These settings (column/row) are applied to ALL uploaded "
                    "files below. Check that every file was read correctly - "
                    "especially if they come from different sources/programs:"
                )
                st.dataframe(
                    validate_uploaded_profiles(
                        values["uploaded_files"],
                        sheet_name=values["sheet_name"],
                        column_index=values["column_index"],
                        start_row=values["start_row"],
                        end_row=values["end_row"],
                    ),
                    hide_index=True,
                )
 
    values["calculate"] = st.button("Calculate", type="primary", use_container_width=True)
    return values


def _run_calculation(values):
    approach = values["approach"]
    uploaded_files = values["uploaded_files"]
 
    if approach == "Scaling approach (Winter)":
        tool = DiversityFactorTool(a=values["a_value"])
 
        if values["winter_input_type"] == "Aggregated profile":
            if uploaded_files is None:
                return None, None, None, "Please upload an aggregated profile first.", None
            try:
                original = read_uploaded_profile(
                    uploaded_files,
                    sheet_name=values["sheet_name"],
                    column_index=values["column_index"],
                    start_row=values["start_row"],
                    end_row=values["end_row"],
                )
                if len(original) == 0:
                    return None, None, None, (
                        "No numeric values found in the selected column/row. "
                        "Please check your column and row selection above "
                        "(use the preview table to find the right ones)."
                    ), None
                n_buildings = values["n_buildings"]
                adjusted = tool.apply(original, n=n_buildings)
                diversity_factor = tool.get_diversity_factor(n_buildings)
                info = {"Calculated diversity factor": f"{diversity_factor:.3f}"}
                return original, adjusted, info, None, None
            except Exception as exc:
                return None, None, None, f"An error occurred while reading/calculating: {exc}", None
        else:
            if not uploaded_files or len(uploaded_files) < 2:
                return None, None, None, "Please upload at least two individual building profiles.", None
            try:
                profiles = [
                    read_uploaded_profile(
                        f,
                        sheet_name=values["sheet_name"],
                        column_index=values["column_index"],
                        start_row=values["start_row"],
                        end_row=values["end_row"],
                    )
                    for f in uploaded_files
                ]
                lengths = {len(p) for p in profiles}
                if len(lengths) > 1:
                    return None, None, None, (
                        "The uploaded profiles have different lengths "
                        f"({sorted(lengths)}). Please upload only profiles of "
                        "equal length and equal resolution."
                    ), None
                n_buildings = len(profiles)
                adjusted = tool.apply(profiles, n=n_buildings)
                original = pd.concat(profiles, axis=1).sum(axis=1)
                diversity_factor = tool.get_diversity_factor(n_buildings)
                info = {
                    "Number of buildings (n)": str(n_buildings),
                    "Calculated diversity factor": f"{diversity_factor:.3f}",
                }
                return original, adjusted, info, None, None
            except Exception as exc:
                return None, None, None, f"An error occurred while reading/calculating: {exc}", None
 
    else:
        if not uploaded_files or len(uploaded_files) < 2:
            return None, None, None, "Please upload at least two individual building profiles.", None
        try:
            profiles = [
                read_uploaded_profile(
                    f,
                    sheet_name=values["sheet_name"],
                    column_index=values["column_index"],
                    start_row=values["start_row"],
                    end_row=values["end_row"],
                )
                for f in uploaded_files
            ]
            lengths = {len(p) for p in profiles}
            if len(lengths) > 1:
                return None, None, None, (
                    "The uploaded profiles have different lengths "
                    f"({sorted(lengths)}). Please upload only profiles of "
                    "equal length and equal resolution."
                ), None
            tool = DiversityFactorShiftTool(
                seed=42,
                input_resolution_minutes=values["resolution_minutes"],
                window_max=values["window_max"],
                tau=values["tau"],
            )
            adjusted, shifted_profiles, shift_info = tool.apply(profiles)
            original = pd.concat(profiles, axis=1).sum(axis=1)
            info = {
                "Effective diversity factor": f"{shift_info['effective_glf']:.3f}",
                "Time window used (min)": f"{shift_info['window_hours'] * 60:.1f}",
                "Peak reduction (%)": (
                    f"{100 * (1 - shift_info['peak_shifted'] / shift_info['peak_original']):.2f}"
                ),
            }
            file_names = [f.name for f in uploaded_files]
            individual_csv = build_individual_profiles_csv(shifted_profiles, file_names)
            individual_download = (individual_csv, "depeak_individual_profiles.csv")
            return original, adjusted, info, None, individual_download
        except Exception as exc:
            return None, None, None, f"An error occurred while reading/calculating: {exc}", None
 


def _render_output(original, adjusted, info, error_message, individual_download=None):
    """Right column: chart, metrics, download button(s)."""
    st.subheader("Result")
    st.caption("Original and adjusted profile in the same chart")

    if error_message:
        st.error(error_message)
    elif adjusted is not None:
        st.plotly_chart(make_comparison_chart(original, adjusted), use_container_width=True)

        if info:
            info_cols = st.columns(len(info))
            for col, (label, value) in zip(info_cols, info.items()):
                col.metric(label, value)

        download_cols = st.columns(2) if individual_download else [st.container()]
        with download_cols[0]:
            st.download_button(
                label="Download aggregated profile (.csv)",
                data=build_result_csv(original, adjusted),
                file_name="depeak_result.csv",
                mime="text/csv",
            )
        if individual_download:
            individual_csv, individual_filename = individual_download
            with download_cols[1]:
                st.download_button(
                    label="Download individual profiles (.csv)",
                    data=individual_csv,
                    file_name=individual_filename,
                    mime="text/csv",
                    help="One column per building - the shifted profile "
                         "for each uploaded file, before aggregation.",
                )
    else:
        render_placeholder_message("No result yet. Choose an approach, upload profiles, and click 'Calculate'.")


def render():
    """Renders the complete stage: title + two-column layout."""
    st.title("DePeak")
    st.caption("Apply diversity effects to load profiles")

    left_col, right_col = st.columns([1, 1.3], gap="large")

    with left_col:
        with st.container(border=True):
            values = _render_inputs()

    original = adjusted = info = error_message = individual_download = None
    if values["calculate"]:
        original, adjusted, info, error_message, individual_download = _run_calculation(values)

    with right_col:
        with st.container(border=True):
            _render_output(original, adjusted, info, error_message, individual_download)

    st.divider()
    with st.expander("Documentation"):
        doc_path = Path(__file__).resolve().parent.parent.parent.parent / "docs" / "DePeak_Losieva_Polina.pdf"
        render_pdf_viewer(doc_path)
        st.markdown(
            "Full source code available on "
            "[GitHub](https://github.com/Losieva/DePeak)."
        )

    with st.expander("Contact"):
        st.markdown("Polina Losieva — [losievapolina@gmail.com](mailto:losievapolina@gmail.com)")