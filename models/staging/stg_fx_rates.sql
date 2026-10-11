-- Business-day FX rates to USD. Weekends and holidays are missing; int_fx_daily fills them.
select
    date(rate_date)             as rate_date,
    upper(currency)             as currency,
    cast(rate_to_usd as real)   as rate_to_usd
from {{ source('raw', 'fx_rates') }}
