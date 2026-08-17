# Sunday Church Class Attendance

A simple Streamlit app for recording Sunday-class attendance across prayer services, teachers, and classes. It uses CSV files as its database, so the data can also be opened in Excel.

## Run locally

1. Create and activate a Python virtual environment.
2. Install packages: `pip install -r requirements.txt`
3. Copy `.env.example` to `.env` (optional) and adjust `CSV_DATA_DIRECTORY` if needed.
4. Start: `streamlit run app.py`

The first run creates `services.csv`, `teachers.csv`, `classes.csv`, `students.csv`, and `attendance.csv`, plus demo services, teachers, classes, and students. Use **Settings & backup** to download all CSV files in one ZIP.

## Streamlit Cloud

Push this folder to GitHub, create a Streamlit Cloud app, and select `app.py` as the main file. Streamlit Cloud installs `requirements.txt` automatically. Set `SEED_DEMO_DATA=true` in the app secrets/environment settings only for a first-time demo.

> CSV files on Streamlit Cloud are not durable across some redeployments or container restarts. Download a backup regularly from **Settings & backup**, or set `CSV_DATA_DIRECTORY` to a mounted/persistent volume when your host provides one. CSV works best when one teacher is saving at a time; use a managed database for multiple simultaneous users.

## Import columns

Student imports accept CSV or Excel and recognize: `name`, `age`, `gender`, `mobile_number`, `area`, `father_name`, `mother_name`, `class_name`, `section`, `teacher_name`, `service_name`, and `address`. Name and teacher are required. Services, teachers, and classes not already present are created automatically.
