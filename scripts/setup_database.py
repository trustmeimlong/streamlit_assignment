import tomllib
from pathlib import Path

import mysql.connector

ROOT = Path(__file__).resolve().parent.parent
SQL_FILES = [ROOT / "sql" / "schema.sql", ROOT / "sql" / "seed_data.sql"]
SECRETS = ROOT / ".streamlit" / "secrets.toml"


def statements(path):
    return [s.strip() for s in path.read_text(encoding="utf-8").split(";\n") if s.strip()]


def main():
    with SECRETS.open("rb") as f:
        cfg = tomllib.load(f)["mysql"]
    con = mysql.connector.connect(host=cfg["host"], port=cfg["port"],
                                  user=cfg["username"], password=cfg["password"])
    try:
        cur = con.cursor()
        for path in SQL_FILES:
            for statement in statements(path):
                cur.execute(statement)
            print(f"ran {path.relative_to(ROOT)}")
        con.commit()
        for table in ["Plans", "Customers", "UsageLogs", "Subscriptions"]:
            cur.execute(f"SELECT COUNT(*) FROM SaaS_AI_DB.{table}")
            print(f"{table}: {cur.fetchone()[0]} rows")
    finally:
        con.close()


if __name__ == "__main__":
    main()
