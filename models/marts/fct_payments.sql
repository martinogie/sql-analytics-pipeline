-- Fact table of valid payments. Grain: one row per payment. Revenue = fee revenue + dispute fees - processing cost.
select
    payment_id,
    merchant_id,
    created_at,
    created_date,
    strftime('%Y-%m', created_date)                                  as payment_month,
    status,
    card_brand,
    currency,
    amount,
    amount_usd,
    plan,
    fee_revenue_usd,
    processing_cost_usd,
    dispute_fee_usd,
    round(fee_revenue_usd + dispute_fee_usd - processing_cost_usd, 4) as net_revenue_usd,
    refunded_usd,
    refund_count,
    chargeback_usd,
    chargeback_count,
    chargeback_lost
from {{ ref('int_payments_enriched') }}
where plan is not null
  and amount > 0
  and amount_usd is not null
