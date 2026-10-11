-- Current merchant attributes plus first and last payment dates and lifetime processed volume.
with activity as (
    select
        merchant_id,
        min(created_date)                                                  as first_payment_date,
        max(created_date)                                                  as last_payment_date,
        sum(case when status = 'succeeded' then amount_usd else 0 end)    as lifetime_gmv_usd,
        count(*)                                                           as payment_count
    from {{ ref('fct_payments') }}
    group by merchant_id
)

select
    m.merchant_id,
    m.legal_name,
    m.country,
    m.industry,
    m.plan                          as current_plan,
    m.signup_date,
    a.first_payment_date,
    a.last_payment_date,
    coalesce(a.lifetime_gmv_usd, 0) as lifetime_gmv_usd,
    coalesce(a.payment_count, 0)    as payment_count
from {{ ref('stg_merchants') }} m
left join activity a on a.merchant_id = m.merchant_id
where m.is_current = 1
