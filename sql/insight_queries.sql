USE SaaS_AI_DB;

WITH latest_status AS (
    SELECT customer_id, status, updated_at AS status_date,
           ROW_NUMBER() OVER (PARTITION BY customer_id ORDER BY updated_at DESC, subscription_id DESC) AS rn
    FROM Subscriptions
)
SELECT 'Tổng quan: Churn trung bình tháng (khách có từ đầu tháng)' AS section,
       SUM(c.signup_date < u.usage_month AND s.status = 'Churned' AND s.status_date >= u.usage_month
           AND s.status_date < u.usage_month + INTERVAL 1 MONTH) AS churned_from_start,
       SUM(c.signup_date < u.usage_month) AS start_customer_months,
       ROUND(SUM(c.signup_date < u.usage_month AND s.status = 'Churned' AND s.status_date >= u.usage_month
                 AND s.status_date < u.usage_month + INTERVAL 1 MONTH) * 100
             / SUM(c.signup_date < u.usage_month), 2) AS monthly_churn_pct
FROM Customers c
JOIN latest_status s ON s.customer_id = c.customer_id AND s.rn = 1
JOIN UsageLogs u     ON u.customer_id = c.customer_id;

WITH latest_status AS (
    SELECT customer_id, status,
           ROW_NUMBER() OVER (PARTITION BY customer_id ORDER BY updated_at DESC, subscription_id DESC) AS rn
    FROM Subscriptions
),
first_month_customers AS (
    SELECT DISTINCT customer_id FROM UsageLogs WHERE usage_month = (SELECT MIN(usage_month) FROM UsageLogs)
)
SELECT 'Tổng quan: Churn cả kỳ' AS section,
       SUM(s.status = 'Churned') AS churned,
       COUNT(*) AS customers,
       ROUND(SUM(s.status = 'Churned') * 100 / COUNT(*), 1) AS churn_pct_assignment_formula,
       SUM(s.status = 'Churned' AND c.customer_id IN (SELECT customer_id FROM first_month_customers)) AS churned_from_starting,
       (SELECT COUNT(*) FROM first_month_customers) AS starting_customers,
       ROUND(SUM(s.status = 'Churned' AND c.customer_id IN (SELECT customer_id FROM first_month_customers)) * 100
             / (SELECT COUNT(*) FROM first_month_customers), 1) AS starting_customers_churn_pct
FROM Customers c
JOIN latest_status s ON s.customer_id = c.customer_id AND s.rn = 1;

WITH latest_status AS (
    SELECT customer_id, status, updated_at AS status_date,
           ROW_NUMBER() OVER (PARTITION BY customer_id ORDER BY updated_at DESC, subscription_id DESC) AS rn
    FROM Subscriptions
),
month_end_customers AS (
    SELECT u.customer_id, u.usage_month, p.monthly_price
    FROM UsageLogs u
    JOIN Customers c     ON c.customer_id = u.customer_id
    JOIN Plans p         ON p.plan_id = c.plan_id
    JOIN latest_status s ON s.customer_id = u.customer_id AND s.rn = 1
    WHERE NOT (s.status = 'Churned' AND s.status_date >= u.usage_month
               AND s.status_date < u.usage_month + INTERVAL 1 MONTH)
),
start_set AS (
    SELECT customer_id, monthly_price FROM month_end_customers
    WHERE usage_month = (SELECT MIN(usage_month) FROM UsageLogs)
),
end_set AS (
    SELECT customer_id, monthly_price FROM month_end_customers
    WHERE usage_month = (SELECT MAX(usage_month) FROM UsageLogs)
)
SELECT 'Tổng quan: Biến động MRR từ tháng đầu đến tháng cuối' AS section,
       (SELECT SUM(monthly_price) FROM start_set) AS mrr_first_month,
       (SELECT SUM(monthly_price) FROM start_set
        WHERE customer_id NOT IN (SELECT customer_id FROM end_set)) AS mrr_lost_from_first_month_customers,
       (SELECT SUM(monthly_price) FROM end_set
        WHERE customer_id NOT IN (SELECT customer_id FROM start_set)) AS mrr_from_new_customers,
       (SELECT SUM(monthly_price) FROM end_set) AS mrr_last_month,
       ROUND((SELECT COUNT(*) FROM start_set WHERE customer_id NOT IN (SELECT customer_id FROM end_set)) * 100
             / (SELECT COUNT(*) FROM start_set), 1) AS lost_customers_pct,
       ROUND((SELECT SUM(monthly_price) FROM start_set WHERE customer_id NOT IN (SELECT customer_id FROM end_set))
             * 100 / (SELECT SUM(monthly_price) FROM start_set), 1) AS lost_mrr_pct;

SELECT 'Tổng quan: Doanh thu, chi phí AI và ticket cả kỳ' AS section,
       COUNT(*) AS customer_months,
       SUM(p.monthly_price) AS revenue,
       SUM(u.ai_api_cost) AS ai_cost,
       SUM(p.monthly_price) - SUM(u.ai_api_cost) AS ai_profit,
       ROUND((SUM(p.monthly_price) - SUM(u.ai_api_cost)) * 100 / SUM(p.monthly_price), 1) AS margin_pct,
       ROUND(AVG(u.support_tickets_opened), 2) AS avg_tickets
FROM UsageLogs u
JOIN Customers c ON c.customer_id = u.customer_id
JOIN Plans p     ON p.plan_id = c.plan_id;

SELECT 'Insight 1: Biên lợi nhuận AI theo tháng' AS section, u.usage_month,
       SUM(p.monthly_price) AS revenue,
       SUM(u.ai_api_cost) AS ai_cost,
       ROUND((SUM(p.monthly_price) - SUM(u.ai_api_cost)) * 100 / SUM(p.monthly_price), 1) AS margin_pct
FROM UsageLogs u
JOIN Customers c ON c.customer_id = u.customer_id
JOIN Plans p     ON p.plan_id = c.plan_id
GROUP BY u.usage_month
ORDER BY u.usage_month;

WITH customer_months AS (
    SELECT p.monthly_price, u.ai_api_cost, u.tokens_consumed,
           u.usage_month >= (SELECT MIN(usage_month) FROM UsageLogs) + INTERVAL 6 MONTH AS second_half
    FROM UsageLogs u
    JOIN Customers c ON c.customer_id = u.customer_id
    JOIN Plans p     ON p.plan_id = c.plan_id
)
SELECT 'Insight 1: Nửa đầu và nửa sau kỳ' AS section,
       CASE WHEN second_half = 1 THEN 'Nửa sau' ELSE 'Nửa đầu' END AS period,
       COUNT(*) AS customer_months,
       ROUND((SUM(monthly_price) - SUM(ai_api_cost)) * 100 / SUM(monthly_price), 1) AS margin_pct,
       ROUND(SUM(ai_api_cost) * 1000000 / SUM(tokens_consumed), 2) AS cost_per_million_tokens
FROM customer_months
GROUP BY second_half
ORDER BY second_half;

WITH customer_months AS (
    SELECT p.plan_id, p.plan_name, p.monthly_price, u.ai_api_cost,
           u.tokens_consumed * 100 / p.ai_token_limit AS usage_pct,
           u.usage_month >= (SELECT MIN(usage_month) FROM UsageLogs) + INTERVAL 6 MONTH AS second_half
    FROM UsageLogs u
    JOIN Customers c ON c.customer_id = u.customer_id
    JOIN Plans p     ON p.plan_id = c.plan_id
),
by_plan AS (
    SELECT plan_id, plan_name,
           AVG(CASE WHEN second_half = 0 THEN usage_pct END) AS usage_first,
           AVG(CASE WHEN second_half = 1 THEN usage_pct END) AS usage_second,
           SUM(CASE WHEN second_half = 0 THEN monthly_price - ai_api_cost END)
               / SUM(CASE WHEN second_half = 0 THEN monthly_price END) AS margin_first,
           SUM(CASE WHEN second_half = 1 THEN monthly_price - ai_api_cost END)
               / SUM(CASE WHEN second_half = 1 THEN monthly_price END) AS margin_second,
           SUM(CASE WHEN second_half = 1 THEN monthly_price END) AS revenue_second
    FROM customer_months
    GROUP BY plan_id, plan_name
)
SELECT 'Insight 1: Theo gói' AS section, plan_name,
       ROUND(usage_first, 1) AS usage_pct_first_half,
       ROUND(usage_second, 1) AS usage_pct_second_half,
       ROUND(margin_first * 100, 1) AS margin_pct_first_half,
       ROUND(margin_second * 100, 1) AS margin_pct_second_half,
       ROUND(revenue_second * (margin_first - margin_second), 0) AS profit_lost_second_half,
       ROUND(revenue_second * (margin_first - margin_second) / 6, 0) AS profit_lost_per_month
FROM by_plan
ORDER BY plan_id;

WITH customer_months AS (
    SELECT p.plan_id, p.plan_name, p.monthly_price, u.ai_api_cost,
           u.tokens_consumed * 100 / p.ai_token_limit AS usage_pct,
           u.usage_month >= (SELECT MIN(usage_month) FROM UsageLogs) + INTERVAL 6 MONTH AS second_half
    FROM UsageLogs u
    JOIN Customers c ON c.customer_id = u.customer_id
    JOIN Plans p     ON p.plan_id = c.plan_id
    WHERE c.customer_id NOT IN (SELECT customer_id FROM Subscriptions WHERE status = 'Upgraded')
),
by_plan AS (
    SELECT plan_id, plan_name,
           AVG(CASE WHEN second_half = 0 THEN usage_pct END) AS usage_first,
           AVG(CASE WHEN second_half = 1 THEN usage_pct END) AS usage_second,
           SUM(CASE WHEN second_half = 0 THEN monthly_price - ai_api_cost END)
               / SUM(CASE WHEN second_half = 0 THEN monthly_price END) AS margin_first,
           SUM(CASE WHEN second_half = 1 THEN monthly_price - ai_api_cost END)
               / SUM(CASE WHEN second_half = 1 THEN monthly_price END) AS margin_second,
           SUM(CASE WHEN second_half = 1 THEN monthly_price END) AS revenue_second
    FROM customer_months
    GROUP BY plan_id, plan_name
)
SELECT 'Insight 1: Kiểm tra độ vững, bỏ khách đã nâng cấp gói' AS section, plan_name,
       ROUND(usage_first, 1) AS usage_pct_first_half,
       ROUND(usage_second, 1) AS usage_pct_second_half,
       ROUND(margin_first * 100, 1) AS margin_pct_first_half,
       ROUND(margin_second * 100, 1) AS margin_pct_second_half,
       ROUND(revenue_second * (margin_first - margin_second) / 6, 0) AS profit_lost_per_month
FROM by_plan
ORDER BY plan_id;

SELECT 'Insight 1: Chi phí AI khi khách dùng hết giới hạn' AS section, p.plan_name, p.monthly_price,
       ROUND(p.monthly_price * 1000000 / p.ai_token_limit, 2) AS price_per_million_tokens,
       ROUND(SUM(u.ai_api_cost) * 1000000 / SUM(u.tokens_consumed), 2) AS cost_per_million_tokens,
       ROUND(p.ai_token_limit * SUM(u.ai_api_cost) / SUM(u.tokens_consumed) * 100 / p.monthly_price, 0)
           AS cost_share_at_full_use_pct
FROM UsageLogs u
JOIN Customers c ON c.customer_id = u.customer_id
JOIN Plans p     ON p.plan_id = c.plan_id
GROUP BY p.plan_id, p.plan_name, p.monthly_price, p.ai_token_limit
ORDER BY p.plan_id;

WITH customer_months AS (
    SELECT u.tokens_consumed > p.ai_token_limit AS over_limit,
           u.usage_month >= (SELECT MIN(usage_month) FROM UsageLogs) + INTERVAL 6 MONTH AS second_half
    FROM UsageLogs u
    JOIN Customers c ON c.customer_id = u.customer_id
    JOIN Plans p     ON p.plan_id = c.plan_id
)
SELECT 'Insight 1: Tỉ lệ tháng vượt giới hạn' AS section, 'Nửa sau so với nửa đầu kỳ' AS comparison,
       second_half AS exposed, SUM(over_limit) AS events, COUNT(*) AS total
FROM customer_months
GROUP BY second_half
ORDER BY exposed DESC;

WITH customer_months AS (
    SELECT u.customer_id,
           CASE WHEN p.plan_name IN ('Business', 'Scale') THEN 'Gói Business và Scale'
                ELSE 'Gói Starter và Pro' END AS plan_group,
           TIMESTAMPDIFF(MONTH, MIN(u.usage_month) OVER (PARTITION BY u.customer_id), u.usage_month) AS month_index,
           LN(u.tokens_consumed) AS log_tokens,
           COUNT(*) OVER (PARTITION BY u.customer_id) AS months
    FROM UsageLogs u
    JOIN Customers c ON c.customer_id = u.customer_id
    JOIN Plans p     ON p.plan_id = c.plan_id
),
centered AS (
    SELECT customer_id, plan_group,
           month_index - AVG(month_index) OVER (PARTITION BY customer_id) AS x,
           log_tokens - AVG(log_tokens) OVER (PARTITION BY customer_id) AS y
    FROM customer_months
    WHERE months >= 3
)
SELECT 'Insight 1: Mức dùng token của mỗi khách tăng theo tháng' AS section, plan_group,
       COUNT(DISTINCT customer_id) AS customers,
       ROUND((EXP(SUM(x * y) / SUM(x * x)) - 1) * 100, 1) AS growth_pct_per_month
FROM centered
GROUP BY plan_group
ORDER BY plan_group;

WITH latest_status AS (
    SELECT customer_id, status, updated_at AS status_date,
           ROW_NUMBER() OVER (PARTITION BY customer_id ORDER BY updated_at DESC, subscription_id DESC) AS rn
    FROM Subscriptions
),
customer_months AS (
    SELECT c.customer_id, c.company_size, s.status,
           u.tokens_consumed > p.ai_token_limit AS over_limit,
           LAG(u.tokens_consumed > p.ai_token_limit)
               OVER (PARTITION BY c.customer_id ORDER BY u.usage_month) AS over_last_month,
           CASE WHEN s.status = 'Churned' AND s.status_date >= u.usage_month
                     AND s.status_date < u.usage_month + INTERVAL 1 MONTH THEN 1 ELSE 0 END AS churned
    FROM Customers c
    JOIN Plans p         ON p.plan_id = c.plan_id
    JOIN latest_status s ON s.customer_id = c.customer_id AND s.rn = 1
    JOIN UsageLogs u     ON u.customer_id = c.customer_id
),
per_customer AS (
    SELECT customer_id, company_size, MAX(over_limit) AS ever_over, MAX(status = 'Churned') AS churned
    FROM customer_months
    GROUP BY customer_id, company_size
)
SELECT 'Insight 2: Vượt giới hạn và rời bỏ' AS section,
       CONCAT(company_size, ': Từng vượt giới hạn trong kỳ (theo khách)') AS comparison,
       ever_over AS exposed, SUM(churned) AS events, COUNT(*) AS total
FROM per_customer
GROUP BY company_size, ever_over
UNION ALL
SELECT 'Insight 2: Vượt giới hạn và rời bỏ', CONCAT(company_size, ': Vượt giới hạn tháng trước, rời bỏ tháng này'),
       over_last_month, SUM(churned), COUNT(*)
FROM customer_months
WHERE over_last_month IS NOT NULL
GROUP BY company_size, over_last_month
ORDER BY comparison, exposed DESC;

WITH latest_status AS (
    SELECT customer_id, status, churn_reason,
           ROW_NUMBER() OVER (PARTITION BY customer_id ORDER BY updated_at DESC, subscription_id DESC) AS rn
    FROM Subscriptions
),
per_customer AS (
    SELECT c.customer_id, c.company_size, MAX(u.tokens_consumed > p.ai_token_limit) AS ever_over
    FROM Customers c
    JOIN Plans p     ON p.plan_id = c.plan_id
    JOIN UsageLogs u ON u.customer_id = c.customer_id
    GROUP BY c.customer_id, c.company_size
),
churned AS (
    SELECT pc.company_size, pc.ever_over,
           s.churn_reason LIKE '%chi phí%' OR s.churn_reason LIKE '%giá gói%' AS cost_reason
    FROM per_customer pc
    JOIN latest_status s ON s.customer_id = pc.customer_id AND s.rn = 1
    WHERE s.status = 'Churned'
)
SELECT 'Insight 2: Lý do chi phí theo lịch sử vượt giới hạn' AS section,
       'Startup rời bỏ: Nêu lý do chi phí' AS comparison,
       ever_over AS exposed, SUM(cost_reason) AS events, COUNT(*) AS total
FROM churned
WHERE company_size = 'Startup'
GROUP BY ever_over
UNION ALL
SELECT 'Insight 2: Lý do chi phí theo lịch sử vượt giới hạn',
       'Toàn công ty, khách rời bỏ: Nêu lý do chi phí',
       ever_over, SUM(cost_reason), COUNT(*)
FROM churned
GROUP BY ever_over
ORDER BY comparison, exposed DESC;

WITH latest_status AS (
    SELECT customer_id, status, churn_reason,
           ROW_NUMBER() OVER (PARTITION BY customer_id ORDER BY updated_at DESC, subscription_id DESC) AS rn
    FROM Subscriptions
)
SELECT 'Insight 2: Lý do rời bỏ của Startup' AS section, s.churn_reason, COUNT(*) AS churned
FROM Customers c
JOIN latest_status s ON s.customer_id = c.customer_id AND s.rn = 1
WHERE s.status = 'Churned' AND c.company_size = 'Startup'
GROUP BY s.churn_reason
HAVING COUNT(*) >= 2
ORDER BY churned DESC;

WITH latest_status AS (
    SELECT customer_id, status,
           ROW_NUMBER() OVER (PARTITION BY customer_id ORDER BY updated_at DESC, subscription_id DESC) AS rn
    FROM Subscriptions
),
per_customer AS (
    SELECT c.customer_id, p.monthly_price, s.status, MAX(u.tokens_consumed > p.ai_token_limit) AS ever_over
    FROM Customers c
    JOIN Plans p         ON p.plan_id = c.plan_id
    JOIN latest_status s ON s.customer_id = c.customer_id AND s.rn = 1
    JOIN UsageLogs u     ON u.customer_id = c.customer_id
    WHERE c.company_size = 'Startup'
    GROUP BY c.customer_id, p.monthly_price, s.status
)
SELECT 'Insight 2: Quy mô tác động' AS section,
       SUM(ever_over = 1) AS startups_over_limit,
       SUM(ever_over = 1 AND status = 'Churned') AS churned_over_limit,
       SUM(CASE WHEN ever_over = 1 AND status = 'Churned' THEN monthly_price ELSE 0 END) AS mrr_lost_over_limit,
       ROUND(SUM(ever_over = 0 AND status = 'Churned') / SUM(ever_over = 0), 4) AS churn_rate_never_over,
       ROUND(SUM(ever_over = 1 AND status = 'Churned')
             - SUM(ever_over = 1) * SUM(ever_over = 0 AND status = 'Churned') / SUM(ever_over = 0), 1) AS excess_churners
FROM per_customer;

WITH customer_months AS (
    SELECT c.customer_id, c.customer_name, p.plan_name, p.monthly_price, u.ai_api_cost,
           u.tokens_consumed > p.ai_token_limit AS over_limit,
           p.monthly_price - u.ai_api_cost AS ai_profit
    FROM UsageLogs u
    JOIN Customers c ON c.customer_id = u.customer_id
    JOIN Plans p     ON p.plan_id = c.plan_id
),
worst_customer AS (
    SELECT customer_id FROM customer_months WHERE over_limit = 1
    GROUP BY customer_id ORDER BY SUM(ai_profit) LIMIT 1
)
SELECT 'Insight 3: Biên lợi nhuận khi vượt giới hạn' AS section, 'Tháng trong giới hạn' AS scope,
       COUNT(*) AS customer_months, SUM(monthly_price) AS revenue, SUM(ai_api_cost) AS ai_cost,
       ROUND((SUM(monthly_price) - SUM(ai_api_cost)) * 100 / SUM(monthly_price), 1) AS margin_pct
FROM customer_months WHERE over_limit = 0
UNION ALL
SELECT 'Insight 3: Biên lợi nhuận khi vượt giới hạn', 'Tháng vượt giới hạn', COUNT(*), SUM(monthly_price),
       SUM(ai_api_cost), ROUND((SUM(monthly_price) - SUM(ai_api_cost)) * 100 / SUM(monthly_price), 1)
FROM customer_months WHERE over_limit = 1
UNION ALL
SELECT 'Insight 3: Biên lợi nhuận khi vượt giới hạn', 'Tháng vượt giới hạn, bỏ 1 khách lỗ nhiều nhất', COUNT(*),
       SUM(monthly_price), SUM(ai_api_cost),
       ROUND((SUM(monthly_price) - SUM(ai_api_cost)) * 100 / SUM(monthly_price), 1)
FROM customer_months WHERE over_limit = 1 AND customer_id NOT IN (SELECT customer_id FROM worst_customer)
UNION ALL
SELECT 'Insight 3: Biên lợi nhuận khi vượt giới hạn', CONCAT('Tháng vượt giới hạn, gói ', plan_name), COUNT(*),
       SUM(monthly_price), SUM(ai_api_cost),
       ROUND((SUM(monthly_price) - SUM(ai_api_cost)) * 100 / SUM(monthly_price), 1)
FROM customer_months WHERE over_limit = 1
GROUP BY plan_name
UNION ALL
SELECT 'Insight 3: Biên lợi nhuận khi vượt giới hạn',
       CONCAT('Tháng vượt giới hạn, gói ', plan_name, ', bỏ 1 khách lỗ nhiều nhất'), COUNT(*),
       SUM(monthly_price), SUM(ai_api_cost),
       ROUND((SUM(monthly_price) - SUM(ai_api_cost)) * 100 / SUM(monthly_price), 1)
FROM customer_months WHERE over_limit = 1 AND customer_id NOT IN (SELECT customer_id FROM worst_customer)
GROUP BY plan_name;

WITH customer_months AS (
    SELECT c.customer_id, u.tokens_consumed > p.ai_token_limit AS over_limit,
           u.tokens_consumed > 2 * p.ai_token_limit AS over_200,
           p.monthly_price - u.ai_api_cost AS ai_profit
    FROM UsageLogs u
    JOIN Customers c ON c.customer_id = u.customer_id
    JOIN Plans p     ON p.plan_id = c.plan_id
)
SELECT 'Insight 3: Tháng lỗ' AS section,
       SUM(ai_profit < 0) AS loss_months,
       SUM(ai_profit < 0 AND over_limit = 1) AS loss_months_over_limit,
       COUNT(DISTINCT CASE WHEN ai_profit < 0 THEN customer_id END) AS loss_customers,
       ROUND(SUM(CASE WHEN ai_profit < 0 THEN ai_profit ELSE 0 END), 2) AS total_loss,
       SUM(ai_profit < 0 AND over_200 = 1) AS loss_months_over_200,
       COUNT(DISTINCT CASE WHEN ai_profit < 0 AND over_200 = 1 THEN customer_id END) AS loss_customers_over_200,
       ROUND(SUM(CASE WHEN ai_profit < 0 AND over_200 = 1 THEN ai_profit ELSE 0 END), 2) AS loss_over_200
FROM customer_months;

SELECT 'Insight 3: Tỉ lệ tháng vượt giới hạn theo gói' AS section, p.plan_name,
       COUNT(*) AS customer_months,
       SUM(u.tokens_consumed > p.ai_token_limit) AS over_limit_months,
       ROUND(AVG(u.tokens_consumed > p.ai_token_limit) * 100, 1) AS over_limit_pct
FROM UsageLogs u
JOIN Customers c ON c.customer_id = u.customer_id
JOIN Plans p     ON p.plan_id = c.plan_id
GROUP BY p.plan_id, p.plan_name
ORDER BY p.plan_id;

SELECT 'Insight 3: Khách lỗ nhiều nhất' AS section, c.customer_name, c.company_size, p.plan_name,
       COUNT(*) AS over_limit_months,
       ROUND(MAX(u.tokens_consumed * 100 / p.ai_token_limit), 1) AS max_usage_pct,
       SUM(p.monthly_price - u.ai_api_cost) AS profit
FROM UsageLogs u
JOIN Customers c ON c.customer_id = u.customer_id
JOIN Plans p     ON p.plan_id = c.plan_id
WHERE u.tokens_consumed > p.ai_token_limit
GROUP BY c.customer_id, c.customer_name, c.company_size, p.plan_name
ORDER BY profit
LIMIT 3;

WITH latest_status AS (
    SELECT customer_id, status, updated_at AS status_date,
           ROW_NUMBER() OVER (PARTITION BY customer_id ORDER BY updated_at DESC, subscription_id DESC) AS rn
    FROM Subscriptions
),
customer_months AS (
    SELECT u.support_tickets_opened > 3 AS many_tickets,
           LAG(u.support_tickets_opened > 3)
               OVER (PARTITION BY u.customer_id ORDER BY u.usage_month) AS many_tickets_last_month,
           CASE WHEN s.status = 'Churned' AND s.status_date >= u.usage_month
                     AND s.status_date < u.usage_month + INTERVAL 1 MONTH THEN 1 ELSE 0 END AS churned
    FROM UsageLogs u
    JOIN Customers c     ON c.customer_id = u.customer_id
    JOIN latest_status s ON s.customer_id = u.customer_id AND s.rn = 1
)
SELECT 'Insight 4: Ticket hỗ trợ và rời bỏ' AS section, 'Hơn 3 ticket trong tháng, rời bỏ cùng tháng' AS comparison,
       many_tickets AS exposed, SUM(churned) AS events, COUNT(*) AS total
FROM customer_months GROUP BY many_tickets
UNION ALL
SELECT 'Insight 4: Ticket hỗ trợ và rời bỏ', 'Hơn 3 ticket tháng trước, rời bỏ tháng này', many_tickets_last_month,
       SUM(churned), COUNT(*)
FROM customer_months WHERE many_tickets_last_month IS NOT NULL GROUP BY many_tickets_last_month
ORDER BY comparison, exposed DESC;

WITH latest_status AS (
    SELECT customer_id, status, updated_at AS status_date,
           ROW_NUMBER() OVER (PARTITION BY customer_id ORDER BY updated_at DESC, subscription_id DESC) AS rn
    FROM Subscriptions
),
customer_months AS (
    SELECT u.support_tickets_opened > 3 AS many_tickets,
           u.tokens_consumed > p.ai_token_limit AS over_limit,
           CASE WHEN s.status = 'Churned' AND s.status_date >= u.usage_month
                     AND s.status_date < u.usage_month + INTERVAL 1 MONTH THEN 1 ELSE 0 END AS churned
    FROM UsageLogs u
    JOIN Customers c     ON c.customer_id = u.customer_id
    JOIN Plans p         ON p.plan_id = c.plan_id
    JOIN latest_status s ON s.customer_id = u.customer_id AND s.rn = 1
)
SELECT 'Insight 4: Hơn 3 ticket và rời bỏ cùng tháng, tách theo vượt giới hạn' AS section,
       CASE WHEN over_limit = 1 THEN 'Tháng vượt giới hạn' ELSE 'Tháng trong giới hạn' END AS stratum,
       many_tickets AS exposed, SUM(churned) AS events, COUNT(*) AS total
FROM customer_months
GROUP BY over_limit, many_tickets
ORDER BY over_limit DESC, exposed DESC;

SELECT 'Insight 4: Trùng với vượt giới hạn' AS section,
       SUM(u.support_tickets_opened > 3) AS months_many_tickets,
       SUM(u.support_tickets_opened > 3 AND u.tokens_consumed > p.ai_token_limit) AS also_over_limit,
       ROUND(SUM(u.support_tickets_opened > 3 AND u.tokens_consumed > p.ai_token_limit) * 100
             / SUM(u.support_tickets_opened > 3), 1) AS overlap_pct
FROM UsageLogs u
JOIN Customers c ON c.customer_id = u.customer_id
JOIN Plans p     ON p.plan_id = c.plan_id;

WITH latest_status AS (
    SELECT customer_id, status,
           ROW_NUMBER() OVER (PARTITION BY customer_id ORDER BY updated_at DESC, subscription_id DESC) AS rn
    FROM Subscriptions
),
upgrades AS (
    SELECT customer_id, MIN(updated_at) AS upgraded_at FROM Subscriptions WHERE status = 'Upgraded'
    GROUP BY customer_id
)
SELECT 'Giả thuyết nâng cấp gói' AS section, 'Từng nâng cấp gói' AS comparison,
       g.customer_id IS NOT NULL AS exposed, SUM(s.status = 'Churned') AS events, COUNT(*) AS total
FROM Customers c
JOIN latest_status s ON s.customer_id = c.customer_id AND s.rn = 1
LEFT JOIN upgrades g ON g.customer_id = c.customer_id
GROUP BY exposed
ORDER BY exposed DESC;

WITH latest_status AS (
    SELECT customer_id, status,
           ROW_NUMBER() OVER (PARTITION BY customer_id ORDER BY updated_at DESC, subscription_id DESC) AS rn
    FROM Subscriptions
),
upgrades AS (
    SELECT customer_id, MIN(updated_at) AS upgraded_at FROM Subscriptions WHERE status = 'Upgraded'
    GROUP BY customer_id
),
usage_span AS (
    SELECT customer_id, MIN(usage_month) AS first_month, COUNT(*) AS months FROM UsageLogs GROUP BY customer_id
)
SELECT 'Giả thuyết nâng cấp gói: Thời gian chờ' AS section,
       ROUND(AVG(TIMESTAMPDIFF(MONTH, us.first_month, g.upgraded_at)), 1) AS avg_months_before_upgrade,
       MIN(TIMESTAMPDIFF(MONTH, us.first_month, g.upgraded_at)) AS min_months_before_upgrade,
       (SELECT COUNT(*) FROM usage_span x
        JOIN latest_status l ON l.customer_id = x.customer_id AND l.rn = 1
        WHERE l.status = 'Churned' AND x.months <= 2
          AND x.customer_id NOT IN (SELECT customer_id FROM upgrades)) AS never_upgraded_churned_within_2_months,
       (SELECT COUNT(*) FROM latest_status l
        WHERE l.rn = 1 AND l.status = 'Churned'
          AND l.customer_id NOT IN (SELECT customer_id FROM upgrades)) AS never_upgraded_churned
FROM upgrades g
JOIN usage_span us ON us.customer_id = g.customer_id;

WITH latest_status AS (
    SELECT customer_id, status, updated_at AS status_date,
           ROW_NUMBER() OVER (PARTITION BY customer_id ORDER BY updated_at DESC, subscription_id DESC) AS rn
    FROM Subscriptions
),
customer_months AS (
    SELECT u.customer_id, u.usage_month,
           CASE WHEN p.plan_name IN ('Business', 'Scale') THEN 'Gói Business và Scale'
                ELSE 'Gói Starter và Pro' END AS plan_group,
           u.usage_month >= (SELECT MIN(usage_month) FROM UsageLogs) + INTERVAL 6 MONTH AS second_half,
           u.tokens_consumed > p.ai_token_limit AS over_limit,
           CASE WHEN s.status = 'Churned' AND s.status_date >= u.usage_month
                     AND s.status_date < u.usage_month + INTERVAL 1 MONTH THEN 1 ELSE 0 END AS churned
    FROM UsageLogs u
    JOIN Customers c     ON c.customer_id = u.customer_id
    JOIN Plans p         ON p.plan_id = c.plan_id
    JOIN latest_status s ON s.customer_id = u.customer_id AND s.rn = 1
),
evaluations AS (
    SELECT plan_group, second_half, churned,
           MAX(over_limit) OVER (PARTITION BY customer_id ORDER BY usage_month
                                 ROWS BETWEEN 2 PRECEDING AND CURRENT ROW) AS high_risk,
           LEAD(churned) OVER (PARTITION BY customer_id ORDER BY usage_month) AS churned_next_month
    FROM customer_months
)
SELECT 'Insight 5: Kiểm chứng quy tắc rủi ro theo nửa kỳ và theo nhóm gói' AS section,
       CASE WHEN second_half = 1 THEN 'Nửa sau kỳ' ELSE 'Nửa đầu kỳ' END AS comparison,
       high_risk AS exposed, SUM(churned_next_month) AS events, COUNT(*) AS total, second_half + 1 AS sort_key
FROM evaluations
WHERE churned = 0 AND churned_next_month IS NOT NULL
GROUP BY second_half, high_risk
UNION ALL
SELECT 'Insight 5: Kiểm chứng quy tắc rủi ro theo nửa kỳ và theo nhóm gói', plan_group, high_risk,
       SUM(churned_next_month), COUNT(*), 3
FROM evaluations
WHERE churned = 0 AND churned_next_month IS NOT NULL
GROUP BY plan_group, high_risk
ORDER BY sort_key, comparison, exposed DESC;
