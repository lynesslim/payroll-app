import streamlit as st
import pandas as pd
import datetime as dt
import math
import calendar
from io import BytesIO

st.set_page_config(page_title="Payroll Processor (Multi-Sheet)", layout="centered")
st.title("🧾 Payroll Processor (Multi-Sheet, 8-hour Rule + Public Holiday)")
st.markdown("Upload an Excel timesheet file with multiple worksheets. Each worksheet's name should match an employee's name in employees.csv.")

# --- Select Date Format Source ---
date_format_source = st.radio("Select Timesheet Date Format Source", options=["Feedme", "Storehub"])
if date_format_source == "Feedme":
    date_format = "%d/%m/%Y %H:%M:%S"
else:  # Storehub
    date_format = "%m/%d/%Y %A %H:%M"

# --- Load local files ---
@st.cache_data
def load_employees():
    return pd.read_csv("employees.csv")  # Expected columns: Name,Status,Base Salary,Hourly Rate,OT Threshold

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

def round_to_nearest_half(x):
    # Rounds x to the nearest 0.5
    return round(x * 2) / 2

def count_working_days(month, year):
    """Returns the number of days in the month excluding Tuesdays."""
    last_day = calendar.monthrange(year, month)[1]
    working_days = sum(
        1 for d in range(1, last_day + 1)
        if dt.date(year, month, d).weekday() != 1  # Tuesday is 1 when Monday=0
    )
    return working_days

def calculate_pay(df, emp_info, ph_list, date_format):
    result_rows = []
    # Process each row in the sheet
    for _, row in df.iterrows():
        # Override the 'Name' column with the sheet name (already set later)
        name = row['Name']
        clock_in = pd.to_datetime(row['Clock In'], format=date_format)
        clock_out = pd.to_datetime(row['Clock Out'], format=date_format)
        
        # Calculate raw worked hours
        worked_hours = (clock_out - clock_in).total_seconds() / 3600
        # Only apply lunch break deduction if worked hours > 4 hours
        if worked_hours > 4:
            # If worked hours are less than 10, deduct 0.5; if 10 or more, deduct 1 hour.
            if worked_hours < 10:
                worked_hours -= 0.5
            else:
                worked_hours -= 1
        worked_hours = round_to_nearest_half(worked_hours)
        
        # Use OT Threshold from employee info (default to 8 if missing)
        try:
            ot_threshold = float(emp_info.iloc[0].get("OT Threshold", 8))
        except:
            ot_threshold = 8.0
        
        reg_hours = min(ot_threshold, worked_hours)
        ot_hours = max(0, worked_hours - ot_threshold)
        
        emp_row = emp_info.iloc[0]
        status = emp_row['Status'].strip().lower()
        
        if status == 'full time':
            # For full time, compute hourly rate from Base Salary and working days.
            month_val = clock_in.month
            year_val = clock_in.year
            working_days = count_working_days(month_val, year_val)
            hourly_rate = emp_row['Base Salary'] / (working_days * 8)
            # For full time, if on a public holiday, add extra premium:
            if is_public_holiday(clock_in, ph_list):
                # Extra premium: 1x for regular hours and 2x for OT hours
                reg_pay = reg_hours * hourly_rate  # extra premium for regular hours
                ot_pay = ot_hours * hourly_rate * 2  # extra premium for OT hours
            else:
                reg_pay = 0  # Regular pay is covered by base salary
                ot_pay = ot_hours * hourly_rate * 1.5
        else:
            # For part time, use provided hourly rate.
            hourly_rate = emp_row['Hourly Rate']
            if is_public_holiday(clock_in, ph_list):
                reg_pay = reg_hours * hourly_rate * 2
                ot_pay = ot_hours * hourly_rate * 3
            else:
                reg_pay = reg_hours * hourly_rate
                ot_pay = ot_hours * hourly_rate * 1.5
        
        total_pay = reg_pay + ot_pay
        
        result_rows.append({
            **row,
            'Adjusted Hours': worked_hours,
            'Hourly Rate': hourly_rate,
            'Regular Hours': reg_hours,
            'Overtime Hours': ot_hours,
            'Is Public Holiday': is_public_holiday(clock_in, ph_list),
            'Regular Pay': reg_pay,
            'Overtime Pay': ot_pay,
            'Total Pay': total_pay
        })
    
    result_df = pd.DataFrame(result_rows)
    if not result_df.empty:
        emp_status = emp_info.iloc[0]['Status'].strip().lower()
        if emp_status == 'full time':
            base_salary = emp_info.iloc[0]['Base Salary']
            # For full time, total regular pay = base salary + extra premiums from PH shifts
            extra_reg = result_df.loc[result_df['Is Public Holiday'] == True, 'Regular Pay'].sum()
            total_reg = base_salary + extra_reg
        else:
            total_reg = result_df['Regular Pay'].sum()
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
        # Iterate over each sheet in the uploaded Excel file.
        for sheet in xls.sheet_names:
            df_sheet = pd.read_excel(xls, sheet_name=sheet)
            # Override the "Name" column with the sheet name (assumes sheet name equals employee name)
            df_sheet['Name'] = sheet
            emp_info = employees[employees["Name"] == sheet]
            if emp_info.empty:
                st.warning(f"No employee info found for '{sheet}'. Skipping this worksheet.")
                continue
            processed_sheets[sheet] = calculate_pay(df_sheet, emp_info, ph_list, date_format)
        
        if processed_sheets:
            st.success("✅ Payroll processed for all worksheets!")
            for sheet, df_processed in processed_sheets.items():
                with st.expander(f"Worksheet: {sheet}"):
                    st.dataframe(df_processed)
            
            output_buffer = BytesIO()
            with pd.ExcelWriter(output_buffer, engine="openpyxl") as writer:
                for sheet, df_processed in processed_sheets.items():
                    df_processed.to_excel(writer, sheet_name=sheet, index=False)
            st.download_button("📥 Download Processed Payroll Excel", data=output_buffer.getvalue(), file_name="processed_payroll.xlsx")
        else:
            st.error("No worksheets were processed. Please check your timesheet file and employee data.")
        
    except Exception as e:
        st.error(f"❌ Error: {e}")
