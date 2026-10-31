from datetime import date, timedelta
from pathlib import Path

import numpy as np

SEED = 2026
FIRST_MONTH = date(2025, 10, 1)
N_MONTHS = 12
INITIAL_CUSTOMERS = 70
OUTPUT = Path(__file__).resolve().parent.parent / "sql" / "seed_data.sql"

PLANS = [
    (1, "Starter", 29.00, 2_000_000),
    (2, "Pro", 99.00, 8_000_000),
    (3, "Business", 299.00, 25_000_000),
    (4, "Scale", 799.00, 70_000_000),
]

SEGMENTS = {
    "Startup": {"share": 0.45, "plans": [0.55, 0.35, 0.10, 0.00], "usage": (0.62, 0.42),
                "tickets": 0.6, "churn": 0.030, "overage_churn": 3.2, "upgrade": 0.25},
    "SMB": {"share": 0.35, "plans": [0.20, 0.45, 0.30, 0.05], "usage": (0.55, 0.33),
            "tickets": 0.8, "churn": 0.019, "overage_churn": 2.0, "upgrade": 0.40},
    "Enterprise": {"share": 0.20, "plans": [0.00, 0.15, 0.45, 0.40], "usage": (0.50, 0.28),
                   "tickets": 1.2, "churn": 0.009, "overage_churn": 1.6, "upgrade": 0.55},
}

COST_REASONS = [("Chi phí vượt ngân sách khi dùng AI nhiều", 5.0), ("Giá gói quá cao so với giá trị", 2.5)]
SUPPORT_REASONS = [("Hỗ trợ kỹ thuật phản hồi chậm", 3.0), ("Lỗi sản phẩm / AI trả lời thiếu chính xác", 2.5)]
OTHER_REASONS = [("Chuyển sang đối thủ rẻ hơn", 1.0), ("Thiếu tính năng cần thiết", 1.0),
                 ("Cắt giảm ngân sách / ngừng hoạt động", 1.0)]

NAME_PARTS = (
    ["An", "Bao", "Binh", "Cat", "Dai", "Dong", "Gia", "Hai", "Hoa", "Hung", "Khang", "Kim", "Lam", "Linh",
     "Long", "Minh", "Nam", "Ngoc", "Nhat", "Phat", "Phu", "Quang", "Sao", "Son", "Tam", "Tan", "Thanh",
     "Thien", "Tin", "Trung", "Tue", "Viet", "Vinh", "Xuan"],
    ["Tech", "Soft", "AI", "Data", "Labs", "Cloud", "Logistics", "Retail", "Edu", "Health", "Media", "Pay",
     "Commerce", "Travel", "Food", "Home", "Studio", "Analytics", "Mobility", "Energy"],
)
LEGAL_FORM = {"Startup": "", "SMB": " Co., Ltd", "Enterprise": " Group"}


def add_months(d, n):
    total = d.year * 12 + d.month - 1 + n
    return date(total // 12, total % 12 + 1, 1)


def months_between(start, end):
    return (end.year - start.year) * 12 + end.month - start.month


def sql_value(v):
    if v is None:
        return "NULL"
    if isinstance(v, str):
        return "'" + v.replace("'", "''") + "'"
    if isinstance(v, date):
        return f"'{v.isoformat()}'"
    if isinstance(v, float):
        return f"{v:.2f}"
    return str(v)


def insert_statements(table, columns, rows, chunk=400):
    statements = []
    for i in range(0, len(rows), chunk):
        values = ",\n".join("(" + ", ".join(sql_value(v) for v in row) + ")" for row in rows[i:i + chunk])
        statements.append(f"INSERT INTO {table} ({', '.join(columns)}) VALUES\n{values};")
    return statements


class Generator:
    def __init__(self, seed):
        self.rng = np.random.default_rng(seed)
        self.customers = []
        self.usage = []
        self.subscriptions = []
        self.used_names = set()

    def pick(self, options):
        names = [o[0] for o in options]
        weights = np.array([o[1] for o in options], dtype=float)
        return names[self.rng.choice(len(names), p=weights / weights.sum())]

    def company_name(self, size):
        while True:
            name = (f"{self.rng.choice(NAME_PARTS[0])} {self.rng.choice(NAME_PARTS[1])}"
                    f"{LEGAL_FORM[size]}")
            if name not in self.used_names:
                self.used_names.add(name)
                return name

    def new_customer(self, signup):
        sizes = list(SEGMENTS)
        size = sizes[self.rng.choice(len(sizes), p=[SEGMENTS[s]["share"] for s in sizes])]
        cfg = SEGMENTS[size]
        tier = int(self.rng.choice(4, p=cfg["plans"]))
        mu, sigma = cfg["usage"]
        customer = {
            "id": len(self.customers) + 1,
            "name": self.company_name(size),
            "size": size,
            "signup": signup,
            "tier": tier,
            "base_tokens": PLANS[tier][3] * self.rng.lognormal(np.log(mu), sigma),
            "growth": self.rng.normal(0.025, 0.03),
            "rate": self.rng.uniform(7.5, 11.5),
            "active": True,
            "over_streak": 0,
        }
        self.customers.append(customer)
        self.subscriptions.append((customer["id"], "Active", None, signup))
        return customer

    def churn_reason(self, customer, over, tickets):
        options = list(OTHER_REASONS)
        if customer["size"] == "Startup":
            options[2] = (options[2][0], 1.4)
        if over:
            options += COST_REASONS
        if tickets > 3:
            options += SUPPORT_REASONS
        return self.pick(options)

    def simulate_month(self, month, is_last):
        for c in self.customers:
            if not c["active"] or c["signup"] >= add_months(month, 1):
                continue
            cfg = SEGMENTS[c["size"]]
            limit = PLANS[c["tier"]][3]
            age = months_between(c["signup"], month)
            tokens = int(c["base_tokens"] * (1 + c["growth"]) ** age * self.rng.lognormal(0, 0.18))
            over = tokens > limit
            cost = round(tokens / 1_000_000 * c["rate"] * self.rng.lognormal(0, 0.06), 2)
            lam = cfg["tickets"] + (2.6 if over else 0) + (0.8 if not over and tokens > 0.9 * limit else 0)
            if self.rng.random() < 0.03:
                lam += 2.5
            tickets = int(self.rng.poisson(lam))
            self.usage.append((c["id"], month, tokens, cost, tickets))
            c["over_streak"] = c["over_streak"] + 1 if over else 0

            hazard = cfg["churn"]
            if over:
                hazard *= cfg["overage_churn"]
            if tickets > 3:
                hazard *= 2.2
            if c["over_streak"] >= 2:
                hazard *= 1.3
            if age < 3:
                hazard *= 1.3
            if self.rng.random() < min(hazard, 0.6):
                first_day = max(3, c["signup"].day + 1) if age == 0 else 3
                churn_date = month + timedelta(days=int(self.rng.integers(first_day - 1, 28)))
                self.subscriptions.append((c["id"], "Churned", self.churn_reason(c, over, tickets), churn_date))
                c["active"] = False
            elif (not is_last and c["over_streak"] >= 2 and c["tier"] < 3
                  and self.rng.random() < cfg["upgrade"]):
                c["tier"] += 1
                c["over_streak"] = 0
                upgrade_date = add_months(month, 1) + timedelta(days=int(self.rng.integers(0, 5)))
                self.subscriptions.append((c["id"], "Upgraded", None, upgrade_date))

    def run(self):
        start = date(2025, 1, 1)
        signups = sorted(start + timedelta(days=int(d)) for d in self.rng.integers(0, 272, INITIAL_CUSTOMERS))
        for signup in signups:
            self.new_customer(signup)
        for i in range(N_MONTHS):
            month = add_months(FIRST_MONTH, i)
            n_new = int(self.rng.poisson(9 + 0.6 * i))
            for day in sorted(self.rng.integers(0, 25, n_new)):
                self.new_customer(month + timedelta(days=int(day)))
            self.simulate_month(month, i == N_MONTHS - 1)

    def to_sql(self):
        customers = [(c["id"], c["name"], c["size"], c["signup"], PLANS[c["tier"]][0]) for c in self.customers]
        usage = sorted(self.usage, key=lambda r: (r[1], r[0]))
        subscriptions = sorted(self.subscriptions, key=lambda r: (r[3], r[0]))
        parts = ["USE SaaS_AI_DB;"]
        parts += insert_statements("Plans", ["plan_id", "plan_name", "monthly_price", "ai_token_limit"], PLANS)
        parts += insert_statements("Customers", ["customer_id", "customer_name", "company_size", "signup_date",
                                                 "plan_id"], customers)
        parts += insert_statements("UsageLogs", ["customer_id", "usage_month", "tokens_consumed", "ai_api_cost",
                                                 "support_tickets_opened"], usage)
        parts += insert_statements("Subscriptions", ["customer_id", "status", "churn_reason", "updated_at"],
                                   subscriptions)
        return "\n\n".join(parts) + "\n"


if __name__ == "__main__":
    generator = Generator(SEED)
    generator.run()
    OUTPUT.write_text(generator.to_sql(), encoding="utf-8")
    churned = sum(1 for s in generator.subscriptions if s[1] == "Churned")
    upgraded = sum(1 for s in generator.subscriptions if s[1] == "Upgraded")
    print(f"customers={len(generator.customers)} usage_rows={len(generator.usage)} "
          f"subscription_rows={len(generator.subscriptions)} churned={churned} upgrades={upgraded}")
    print(f"written {OUTPUT}")
