DROP DATABASE IF EXISTS SaaS_AI_DB;
CREATE DATABASE SaaS_AI_DB CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;
USE SaaS_AI_DB;

CREATE TABLE Plans (
    plan_id INT AUTO_INCREMENT PRIMARY KEY,
    plan_name VARCHAR(50) NOT NULL,
    monthly_price DECIMAL(10, 2) NOT NULL,
    ai_token_limit INT NOT NULL,
    CONSTRAINT uq_plans_name UNIQUE (plan_name),
    CONSTRAINT chk_plans_price CHECK (monthly_price >= 0),
    CONSTRAINT chk_plans_limit CHECK (ai_token_limit > 0)
);

CREATE TABLE Customers (
    customer_id INT AUTO_INCREMENT PRIMARY KEY,
    customer_name VARCHAR(100) NOT NULL,
    company_size VARCHAR(20) CHECK (company_size IN ('Startup', 'SMB', 'Enterprise')),
    signup_date DATE NOT NULL,
    plan_id INT,
    FOREIGN KEY (plan_id) REFERENCES Plans(plan_id)
);

CREATE TABLE UsageLogs (
    log_id INT AUTO_INCREMENT PRIMARY KEY,
    customer_id INT,
    usage_month DATE NOT NULL,
    tokens_consumed INT NOT NULL,
    ai_api_cost DECIMAL(10, 2) NOT NULL,
    support_tickets_opened INT DEFAULT 0,
    FOREIGN KEY (customer_id) REFERENCES Customers(customer_id),
    CONSTRAINT uq_usage_customer_month UNIQUE (customer_id, usage_month),
    CONSTRAINT chk_usage_first_day CHECK (DAY(usage_month) = 1),
    CONSTRAINT chk_usage_tokens CHECK (tokens_consumed >= 0),
    CONSTRAINT chk_usage_cost CHECK (ai_api_cost >= 0),
    CONSTRAINT chk_usage_tickets CHECK (support_tickets_opened >= 0)
);

CREATE TABLE Subscriptions (
    subscription_id INT AUTO_INCREMENT PRIMARY KEY,
    customer_id INT,
    status VARCHAR(20) CHECK (status IN ('Active', 'Churned', 'Upgraded')),
    churn_reason VARCHAR(150),
    updated_at DATE NOT NULL,
    FOREIGN KEY (customer_id) REFERENCES Customers(customer_id),
    CONSTRAINT chk_subscriptions_reason CHECK ((status = 'Churned') = (churn_reason IS NOT NULL)),
    INDEX idx_subscriptions_customer_date (customer_id, updated_at)
);
