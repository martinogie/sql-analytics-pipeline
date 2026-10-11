-- One rate per currency per calendar day: the latest business-day rate on or before that day (as-of join).
with recursive days(day) as (
    select (select min(rate_date) from {{ ref('stg_fx_rates') }})
    union all
    select date(day, '+1 day') from days
    where day < (select max(rate_date) from {{ ref('stg_fx_rates') }})
),

currencies as (
    select distinct currency from {{ ref('stg_fx_rates') }}
)

select
    d.day as rate_date,
    c.currency,
    (
        select f.rate_to_usd
        from {{ ref('stg_fx_rates') }} f
        where f.currency = c.currency
          and f.rate_date <= d.day
        order by f.rate_date desc
        limit 1
    ) as rate_to_usd
from days d
cross join currencies c
