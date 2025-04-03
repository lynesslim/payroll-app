import streamlit as st
import pandas as pd
import datetime as dt
import math
from io import BytesIO

st.set_page_config(page_title="Payroll Processor", layout="centered")
st.title("🧾 Payroll Processor (8-hour Rule + Public Holiday)")
st.markdown("Select an employee, review the public holidays, then upload your timesheet file.")

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

# --- Employee selection ---
employee_names = employees["Name"].unique()
selected_employee = st.selectbox("Select Employee", employee_names)
emp_details = employees[employees["Name"] == selected_employee].iloc[0]
st.write("**Employee Details:**")
st.write(emp_details)

# Display public holidays (read-only)
st.write("**Public Holidays:**")
st.write(ph_list)

# Timesheet uploader
uploaded_timesheet = st.file_uploader("Upload Timesheet CSV or Excel", type=["csv", "xlsx"])

# --- Helper Functions ---

def is_public_holiday(date, holiday_list):
    return date.strftime('%Y-%m-%d') in holiday_list

def round_down_nearest_half(x):
    return math.floor(x * 2) / 2

def calculate_pay(df, emp_info, ph_list):
    result_rows = []
    # Process each timesheet row
    for _, row in df.iterrows():
        # Assume row has columns: Name, Clock In, Clock Out, etc.
        name = row['Name']
        clock_in = pd.to_datetime(row['Clock In'])
        clock_out = pd.to_datetime(row['Clock Out'])
        
        # Calculate raw worked hours and apply break deduction:
        # If worked <=7 hours, deduct 0.5; if >7, deduct 1 hour.
        worked_hours = (clock_out - clock_in).total_seconds() / 3600
        worked_hours -= 0.5 if worked_hours <= 7 else 1
        worked_hours = round_down_nearest_half(worked_hours)
        
        # For each row, assume regular hours are up to 8, OT is any excess.
        reg_hours = min(8, worked_hours)
        ot_hours = max(0, worked_hours - 8)
        
        emp_row = emp_info.iloc[0]  # Since we filtered by employee
        status = emp_row['Status'].strip().lower()
        
        # For full time, ignore computed regular pay.
        if status == 'full time':
            # Calculate hourly rate based on Base Salary / (working_days * 8)
            month = clock_in.month
            year = clock_in.year
            working_days = sum(
                1 for d in range(1, 32)
                if dt.date(year, month, d) >= dt.date(year, month, 1)
                and dt.date(year, month, d) <= dt.date(year, month, 28)
                and dt.date(year, month, d).weekday() != 1
            )
            hourly_rate = emp_row['Base Salary'] / (working_days * 8)
            # For each shift, set computed regular pay to 0;
            reg_pay = 0
        else:
            # For part time, use provided hourly rate.
            hourly_rate = emp_row['Hourly Rate']
            reg_pay = reg_hours * hourly_rate
        
        # Determine if the shift is on a public holiday
        is_ph = is_public_holiday(clock_in, ph_list)
        # Overtime multiplier: 3x on public holiday, 1.5x otherwise.
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
    
    # Append a totals row:
    if not result_df.empty:
        emp_status = emp_info.iloc[0]['Status'].strip().lower()
        # For full time, set total regular pay as the base salary; for part time, sum the computed regular pay.
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

# --- Process Timesheet if Uploaded ---
if uploaded_timesheet:
    try:
        # Load timesheet file (CSV or Excel)
        if uploaded_timesheet.name.endswith("csv"):
            df_timesheet = pd.read_csv(uploaded_timesheet)
        else:
            df_timesheet = pd.read_excel(uploaded_timesheet)
        
        # Filter timesheet to include only rows for the selected employee.
        df_timesheet = df_timesheet[df_timesheet["Name"] == selected_employee]
        
        # Get employee info for the selected employee.
        emp_info = employees[employees["Name"] == selected_employee]
        
        result_df = calculate_pay(df_timesheet, emp_info, ph_list)
        
        st.success("✅ Payroll processed!")
        st.dataframe(result_df)
        
        # Download buttons:
        buffer = BytesIO()
        result_df.to_excel(buffer, index=False)
        st.download_button("📥 Download Excel", data=buffer.getvalue(), file_name="processed_payroll.xlsx")
        
        csv_data = result_df.to_csv(index=False).encode("utf-8")
        st.download_button("📥 Download CSV", data=csv_data, file_name="processed_payroll.csv")
        
    except Exception as e:
        st.error(f"❌ Error: {e}")
