-- Company KPIs by month: volume, revenue, take rate, authorisation, refund and chargeback rates,
-- active / new / churned merchants and month-over-month growth.
with monthly as (
    select
        payment_month,
        sum(case when status = 'succeeded' then amount_usd else 0 end)            as gmv_usd,
        sum(fee_revenue_usd)                                                      as fee_revenue_usd,
        sum(net_revenue_usd)                                                      as net_revenue_usd,
        sum(refunded_usd)                                                         as refunded_usd,
        sum(case when status = 'succeeded' then 1 else 0 end)                     as succeeded,
        sum(case when status in ('succeeded', 'failed') then 1 else 0 end)        as attempted,
        sum(chargeback_count)                                                     as chargebacks
    from {{ ref('fct_payments') }}
    group by payment_month
),

active as (
    select payment_month, merchant_id from {{ ref('mart_merchant_monthly') }} where succeeded_payments > 0
),

first_month as (
    select merchant_id, min(payment_month) as first_month from active group by merchant_id
),

merchant_counts as (
    select
        a.payment_month,
        count(*)                                                        as active_merchants,
        sum(case when f.first_month = a.payment_month then 1 else 0 end) as new_merchants
    from active a
    join first_month f on f.merchant_id = a.merchant_id
    group by a.payment_month
),

churned as (
    -- active last month, not active this month
    select
        strftime('%Y-%m', date(prev.payment_month || '-01', '+1 month')) as payment_month,
        count(*)                                                         as churned_merchants
    from active prev
    left join active cur
        on cur.merchant_id = prev.merchant_id
       and cur.payment_month = strftime('%Y-%m', date(prev.payment_month || '-01', '+1 month'))
    where cur.merchant_id is null
    group by 1
)

select
    m.payment_month,
    round(m.gmv_usd, 2)                                                    as gmv_usd,
    round(m.net_revenue_usd, 2)                                            as net_revenue_usd,
    round(m.fee_revenue_usd / m.gmv_usd, 5)                                as take_rate,
    round(1.0 * m.succeeded / m.attempted, 4)                              as authorisation_rate,
    round(m.refunded_usd / m.gmv_usd, 5)                                   as refund_rate,
    round(1.0 * m.chargebacks / m.succeeded, 5)                            as chargeback_rate,
    mc.active_merchants,
    mc.new_merchants,
    coalesce(c.churned_merchants, 0)                                       as churned_merchants,
    round(m.gmv_usd / lag(m.gmv_usd) over (order by m.payment_month) - 1, 4) as gmv_mom_growth
from monthly m
join merchant_counts mc on mc.payment_month = m.payment_month
left join churned c on c.payment_month = m.payment_month
order by m.payment_month
