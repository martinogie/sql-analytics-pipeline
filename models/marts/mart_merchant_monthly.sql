-- Merchant x month activity and revenue. Grain: one row per merchant per month with at least one payment.
select
    merchant_id,
    payment_month,
    count(*)                                                                as payments,
    sum(case when status = 'succeeded' then 1 else 0 end)                   as succeeded_payments,
    round(sum(case when status = 'succeeded' then amount_usd else 0 end), 2) as gmv_usd,
    round(sum(fee_revenue_usd), 2)                                          as fee_revenue_usd,
    round(sum(net_revenue_usd), 2)                                          as net_revenue_usd,
    round(sum(refunded_usd), 2)                                             as refunded_usd,
    sum(chargeback_count)                                                   as chargebacks
from {{ ref('fct_payments') }}
group by merchant_id, payment_month
