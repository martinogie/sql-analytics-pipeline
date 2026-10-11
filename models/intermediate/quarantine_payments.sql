-- Payments held back from the marts, with the reason: unknown merchant, non-positive amount, or no FX rate.
select
    payment_id,
    merchant_id,
    created_date,
    amount,
    currency,
    status,
    case
        when plan is null then 'unknown merchant'
        when amount <= 0 then 'non-positive amount'
        when amount_usd is null then 'missing FX rate'
    end as reason
from {{ ref('int_payments_enriched') }}
where plan is null
   or amount <= 0
   or amount_usd is null
