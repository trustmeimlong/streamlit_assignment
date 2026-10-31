import io

import pandas as pd

XLSX_MIME = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"


def to_csv_bytes(df):
    return df.to_csv(index=False).encode("utf-8-sig")


def to_excel_bytes(sheets):
    buffer = io.BytesIO()
    with pd.ExcelWriter(buffer, engine="openpyxl") as writer:
        for name, df in sheets.items():
            df.to_excel(writer, sheet_name=name, index=False)
            sheet = writer.sheets[name]
            for i, col in enumerate(df.columns, start=1):
                width = max(len(str(col)), *(len(str(v)) for v in df[col].head(200))) if len(df) else len(str(col))
                sheet.column_dimensions[sheet.cell(row=1, column=i).column_letter].width = min(width + 2, 45)
            sheet.freeze_panes = "A2"
    return buffer.getvalue()
