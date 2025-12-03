import os
import pandas as pd

def merge_csvs(csv_dir: str, project_dir: str):
    output_file = os.path.join(project_dir, "All-Merged.xlsx")
    all_rows = []

    for file in sorted(os.listdir(csv_dir)):
        if file.endswith(".csv") and file.startswith("#"):
            df = pd.read_csv(os.path.join(csv_dir, file))
            keyword_no = file.replace(".csv", "")
            for _, row in df.iterrows():
                all_rows.append({
                    "KeywordNo": keyword_no,
                    "PMID": row["PMID"],
                    "Title": row["Title"],
                    "Journal": row["Journal"]
                })

    merged = pd.DataFrame(all_rows)
    merged.to_excel(output_file, index=False)
    return output_file

