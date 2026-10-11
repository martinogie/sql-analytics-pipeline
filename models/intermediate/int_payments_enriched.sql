-- Payments converted to USD, with the merchant's plan as of the payment date (SCD type-2 join),
-- pricing, processing cost, refunds and chargebacks. Grain: one row per payment.
with pay as (
    select
        p.*,
        f.rate_to_usd,
        round(p.amount * f.rate_to_usd, 2) as amount_usd
    from {{ ref('stg_payments') }} p
    left join {{ ref('int_fx_daily') }} f
        on f.currency = p.currency
       and f.rate_date = p.created_date
),

with_plan as (
    select
        pay.*,
        m.plan,
        m.industry,
        m.country
    from pay
    left join {{ ref('stg_merchants') }} m
        on m.merchant_id = pay.merchant_id
       and pay.created_date between m.valid_from and m.valid_to
),

refunds as (
    select payment_id, sum(amount) as refunded_amount, count(*) as refund_count
    from {{ ref('stg_refunds') }}
    group by payment_id
),

chargebacks as (
    select payment_id, sum(amount) as chargeback_amount, count(*) as chargeback_count,
           max(case when status = 'lost' then 1 else 0 end) as chargeback_lost
    from {{ ref('stg_chargebacks') }}
    group by payment_id
)

select
    w.*,
    case w.plan when 'standard' then 0.029 when 'growth' then 0.026 when 'enterprise' then 0.022 end as pct_fee,
    case w.plan when 'standard' then 0.30  when 'growth' then 0.25  when 'enterprise' then 0.20  end as fixed_fee,
    case when w.status = 'succeeded' then
        round(w.amount_usd * case w.plan when 'standard' then 0.029 when 'growth' then 0.026 else 0.022 end
              + case w.plan when 'standard' then 0.30 when 'growth' then 0.25 else 0.20 end, 4)
         else 0 end                                                              as fee_revenue_usd,
    case when w.status = 'succeeded' then round(w.amount_usd * 0.018 + 0.10, 4) else 0 end as processing_cost_usd,
    round(coalesce(r.refunded_amount, 0) * w.rate_to_usd, 2)                     as refunded_usd,
    coalesce(r.refund_count, 0)                                                  as refund_count,
    round(coalesce(c.chargeback_amount, 0) * w.rate_to_usd, 2)                   as chargeback_usd,
    coalesce(c.chargeback_count, 0)                                              as chargeback_count,
    coalesce(c.chargeback_lost, 0)                                               as chargeback_lost,
    15.0 * coalesce(c.chargeback_count, 0)                                       as dispute_fee_usd
from with_plan w
left join refunds r on r.payment_id = w.payment_id
left join chargebacks c on c.payment_id = w.payment_id
