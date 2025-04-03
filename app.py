import streamlit as st
import pandas as pd
import datetime as dt
import math
from io import BytesIO

st.set_page_config(page_title="Payroll Processor (Multi-Sheet)", layout="centered")
st.title("🧾 Payroll Processor (Multi-Sheet, 8-hour Rule + Public Holiday)")
st.markdown("Upload an Excel timesheet file with multiple worksheets. Each worksheet contains an employee's timesheet. The app automatically loads employees and public holidays.")

# --- Load local files ---
@st.cache_data
def load_employees():
    return pd.read_csv("employees.csv")  # Expected columns: Name,Status,Base Salary,Hourly Rate

@st.cache_data
def load_public_holidays():
    with open("public_holidays.txt", "r") as f:
        holidays = [line.strip() for line in f if line.strip() != ""]
    return holidays

employees = load_employees()
ph_list = load_public_holidays()

# Display employee data (read-only)
st.write("**Loaded Employee Data:**")
st.dataframe(employees)

# Display public holidays (read-only)
st.write("**Public Holidays:**")
st.write(ph_list)

# Timesheet uploader (Excel file with multiple worksheets)
uploaded_timesheet = st.file_uploader("Upload Timesheet Excel (Multi-Sheet)", type=["xlsx"])

# --- Helper Functions ---
def is_public_holiday(date, holiday_list):
    return date.strftime('%Y-%m-%d') in holiday_list

def round_down_nearest_half(x):
    return math.floor(x * 2) / 2

def calculate_pay(df, emp_info, ph_list):
    result_rows = []
    # Process each row in the sheet
    for _, row in df.iterrows():
        # Expected columns in each sheet: Name, Clock In, Clock Out, Duration, etc.
        name = row['Name']
        clock_in = pd.to_datetime(row['Clock In'])
        clock_out = pd.to_datetime(row['Clock Out'])
        
        # Calculate raw worked hours
        worked_hours = (clock_out - clock_in).total_seconds() / 3600
        # Apply lunch break deduction only if duration > 4 hours
        if worked_hours > 4:
            worked_hours -= 0.5 if worked_hours <= 7 else 1
        worked_hours = round_down_nearest_half(worked_hours)
        
        # Split hours: up to 8 hours are regular, excess are OT
        reg_hours = min(8, worked_hours)
        ot_hours = max(0, worked_hours - 8)
        
        # Retrieve employee info by matching Name (assumes sheet Name matches employees.csv)
        emp_row = emp_info[emp_info['Name'] == name].iloc[0]
        status = emp_row['Status'].strip().lower()
        
        if status == 'full time':
            # For full time, regular pay is simply the base salary overall,
            # so per shift, we set computed regular pay to 0 and only calculate OT.
            month = clock_in.month
            year = clock_in.year
            # Count working days in the month (excluding Tuesdays)
            working_days = sum(
                1 for d in range(1, 32)
                if dt.date(year, month, d) >= dt.date(year, month, 1)
                and dt.date(year, month, d) <= dt.date(year, month, 28)
                and dt.date(year, month, d).weekday() != 1
            )
            hourly_rate = emp_row['Base Salary'] / (working_days * 8)
            reg_pay = 0
        else:
            hourly_rate = emp_row['Hourly Rate']
            reg_pay = reg_hours * hourly_rate
        
        # Determine if the shift is on a public holiday
        is_ph = is_public_holiday(clock_in, ph_list)
        reg_multiplier = 2 if is_ph else 1
        ot_multiplier = 3 if is_ph else 1.5
        
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
    
    result_df = pd.DataFrame(result_rows)
    if not result_df.empty:
        emp_status = emp_info.iloc[0]['Status'].strip().lower()
        # For full time, total regular pay is the base salary; for part time, it's the sum.
        total_reg = emp_info.iloc[0]['Base Salary'] if emp_status == 'full time' else result_df['Regular Pay'].sum()
        total_ot = result_df['Overtime Pay'].sum()
        totals = {
            'Name': 'TOTAL',
            'Regular Pay': total_reg,
            'Overtime Pay': total_ot,
            'Total Pay': total_reg + total_ot
        }
        total_row = pd.DataFrame([totals])
        result_df = pd.concat([result_df, total_row], ignore_index=True)
    return result_df

# --- Process Multi-Sheet Timesheet if Uploaded ---
if uploaded_timesheet:
    try:
        xls = pd.ExcelFile(uploaded_timesheet)
        processed_sheets = {}
        for sheet in xls.sheet_names:
            df_sheet = pd.read_excel(xls, sheet_name=sheet)
            # No need to filter by employee since each sheet is an employee's timesheet
            processed_sheets[sheet] = calculate_pay(df_sheet, employees, ph_list)
        
        st.success("✅ Payroll processed for all worksheets!")
        # Display each processed sheet in an expander
        for sheet, df_processed in processed_sheets.items():
            with st.expander(f"Worksheet: {sheet}"):
                st.dataframe(df_processed)
        
        # Prepare a multi-sheet Excel file for download
        output_buffer = BytesIO()
        with pd.ExcelWriter(output_buffer, engine="openpyxl") as writer:
            for sheet, df_processed in processed_sheets.items():
                df_processed.to_excel(writer, sheet_name=sheet, index=False)
        st.download_button("📥 Download Processed Payroll Excel", data=output_buffer.getvalue(), file_name="processed_payroll.xlsx")
        
    except Exception as e:
        st.error(f"❌ Error: {e}")
