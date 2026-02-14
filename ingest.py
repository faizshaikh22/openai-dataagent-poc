import kagglehub
import pandas as pd
import sqlite3
import os

def ingest_data():
    print("Downloading NYC Payroll data...")
    try:
        # Download latest version
        path = kagglehub.dataset_download("new-york-city/nyc-citywide-payroll-data")
        print(f"Path to dataset files: {path}")

        # Find the CSV file
        csv_file = None
        for root, dirs, files in os.walk(path):
            for file in files:
                if file.endswith(".csv"):
                    csv_file = os.path.join(root, file)
                    break

        if not csv_file:
            print("No CSV file found in downloaded dataset.")
            return

        print(f"Loading {csv_file} into pandas...")
        # Load a sample first to check columns, but for a POC let's try to load a chunk or all.
        # It might be large. Let's load 50k rows for the POC.
        df = pd.read_csv(csv_file, low_memory=False, nrows=50000)

        # Clean column names
        df.columns = [c.lower().replace(" ", "_") for c in df.columns]

        print(f"Columns: {df.columns.tolist()}")

        # Connect to SQLite
        db_file = "payroll.db"
        conn = sqlite3.connect(db_file)

        # Write to SQLite
        print(f"Writing 50k rows to {db_file}...")
        df.to_sql("payroll", conn, if_exists="replace", index=False)

        conn.close()
        print("Ingestion complete.")

    except Exception as e:
        print(f"Error: {e}")

if __name__ == "__main__":
    ingest_data()
