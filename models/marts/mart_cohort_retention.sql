-- Merchant retention by first-payment month: share of each cohort processing payments N months later.
with active as (
    select distinct merchant_id, payment_month
    from {{ ref('mart_merchant_monthly') }}
    where succeeded_payments > 0
),

cohorts as (
    select merchant_id, min(payment_month) as cohort_month from active group by merchant_id
),

sizes as (
    select cohort_month, count(*) as cohort_size from cohorts group by cohort_month
)

select
    c.cohort_month,
    (cast(substr(a.payment_month, 1, 4) as integer) - cast(substr(c.cohort_month, 1, 4) as integer)) * 12
      + cast(substr(a.payment_month, 6, 2) as integer) - cast(substr(c.cohort_month, 6, 2) as integer) as months_since_first,
    count(*)                                   as active_merchants,
    s.cohort_size,
    round(1.0 * count(*) / s.cohort_size, 4)   as retention
from active a
join cohorts c on c.merchant_id = a.merchant_id
join sizes s on s.cohort_month = c.cohort_month
group by c.cohort_month, months_since_first, s.cohort_size
