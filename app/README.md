# Simple Fantasy Baseball Draft Tool

This is a basic Streamlit app to view your player rankings.

## Setup

1. **Install dependencies:**
   ```bash
   pip install -r requirements.txt
   ```

2. **Configure AWS:**
   ```bash
   aws configure
   ```

3. **Update the S3 output location:**
   - Open `app/app.py`
   - Find the line: `ATHENA_S3_OUTPUT = "s3://your-bucket/query-results/"`
   - Replace with your actual S3 bucket path for Athena query results

4. **Run the app:**
   ```bash
   streamlit run app/app.py
   ```

## What it does

- Shows a dropdown to select format (50s or OC)
- Has a button to load player rankings from your mart tables
- Displays the data in a table

That's it! Simple and straightforward.
