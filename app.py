
import streamlit as st
import pandas as pd
import datetime as dt
import math
from io import BytesIO

st.set_page_config(page_title="Payroll Processor", layout="centered")

st.title("🧾 Payroll Processor (8-hour Rule + Public Holiday)")

st.markdown("Upload your **timesheet**, **employee info**, and optional **public holiday list** to get started.")

# Upload section
uploaded_timesheet = st.file_uploader("Upload Timesheet CSV or Excel", type=["csv", "xlsx"])
uploaded_employees = st.file_uploader("Upload Employee Info CSV", type=["csv"])
uploaded_ph_list = st.file_uploader("Upload Public Holidays (.txt, one date per line)", type=["txt"])

# Helper functions
def is_public_holiday(date, holiday_list):
    return date.strftime('%Y-%m-%d') in holiday_list

def calculate_pay(df, emp_info, ph_list):
    result_rows = []

    for _, row in df.iterrows():
        name = row['Name']
        clock_in = pd.to_datetime(row['Clock In'])
        clock_out = pd.to_datetime(row['Clock Out'])

        worked_hours = (clock_out - clock_in).total_seconds() / 3600
        worked_hours -= 0.5 if worked_hours <= 7 else 1
        worked_hours = math.floor(worked_hours)

        reg_hours = min(8, worked_hours)
        ot_hours = max(0, worked_hours - 8)

        emp_row = emp_info[emp_info['Name'] == name].iloc[0]
        status = emp_row['Status'].strip().lower()

        if status == 'full time':
            month = clock_in.month
            year = clock_in.year
            working_days = sum(1 for d in range(1, 32)
                               if dt.date(year, month, 1) <= dt.date(year, month, d) <= dt.date(year, month, 28)
                               and dt.date(year, month, d).weekday() != 1)
            hourly_rate = emp_row['Base Salary'] / (working_days * 8)
        else:
            hourly_rate = emp_row['Hourly Rate']

        is_ph = is_public_holiday(clock_in, ph_list)
        reg_multiplier = 2 if is_ph else 1
        ot_multiplier = 3 if is_ph else 1.5

        reg_pay = reg_hours * hourly_rate * reg_multiplier
        ot_pay = ot_hours * hourly_rate * ot_multiplier
        total_pay = reg_pay + ot_pay

        result_rows.append({
            **row,
            'Adjusted Hours': worked_hours,
            'Hourly Rate': hourly_rate,
            'Regular Hours': reg_hours,
            'Overtime Hours': ot_hours,
            'Is Public Holiday': is_ph,
            'Regular Pay': reg_pay,
            'Overtime Pay': ot_pay,
            'Total Pay': total_pay
        })

    return pd.DataFrame(result_rows)

# Process logic
if uploaded_timesheet and uploaded_employees:
    try:
        df_timesheet = pd.read_csv(uploaded_timesheet) if uploaded_timesheet.name.endswith("csv") else pd.read_excel(uploaded_timesheet)
        df_employees = pd.read_csv(uploaded_employees)
        ph_list = [line.strip() for line in uploaded_ph_list.readlines()] if uploaded_ph_list else []

        result_df = calculate_pay(df_timesheet, df_employees, ph_list)

        st.success("✅ Payroll processed!")

        st.dataframe(result_df)

        # Download as Excel
        buffer = BytesIO()
        result_df.to_excel(buffer, index=False)
        st.download_button("📥 Download Excel", data=buffer.getvalue(), file_name="processed_payroll.xlsx")

        # Download as CSV
        csv_data = result_df.to_csv(index=False).encode("utf-8")
        st.download_button("📥 Download CSV", data=csv_data, file_name="processed_payroll.csv")

    except Exception as e:
        st.error(f"❌ Error: {e}")
