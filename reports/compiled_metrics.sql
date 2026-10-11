-- gmv: Gross merchandise volume (USD)
select strftime('%Y-%m', created_date) as month,
       sum(amount_usd) as gmv
from fct_payments
where status = 'succeeded'
group by 1
order by 1;

-- net_revenue: Net revenue (USD)
select strftime('%Y-%m', created_date) as month,
       sum(net_revenue_usd) as net_revenue
from fct_payments
group by 1
order by 1;

-- take_rate: Take rate
select strftime('%Y-%m', created_date) as month,
       sum(fee_revenue_usd) * 1.0 / nullif(sum(case when status = 'succeeded' then amount_usd else 0 end), 0) as take_rate
from fct_payments
group by 1
order by 1;

-- refund_rate: Refund rate
select strftime('%Y-%m', created_date) as month,
       sum(refunded_usd) * 1.0 / nullif(sum(case when status = 'succeeded' then amount_usd else 0 end), 0) as refund_rate
from fct_payments
group by 1
order by 1;

-- authorisation_rate: Authorisation rate
select strftime('%Y-%m', created_date) as month,
       sum(case when status = 'succeeded' then 1 else 0 end) * 1.0 / nullif(sum(case when status in ('succeeded', 'failed') then 1 else 0 end), 0) as authorisation_rate
from fct_payments
group by 1
order by 1;

-- active_merchants: Active merchants
select strftime('%Y-%m', created_date) as month,
       count(distinct merchant_id) as active_merchants
from fct_payments
where status = 'succeeded'
group by 1
order by 1;