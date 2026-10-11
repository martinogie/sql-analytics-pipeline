-- Chargebacks (disputes) with normalised reason and status.
select
    chargeback_id,
    payment_id,
    cast(amount as real)      as amount,
    lower(trim(reason_code))  as reason_code,
    date(opened_at)           as opened_date,
    lower(trim(status))       as status
from {{ source('raw', 'chargebacks_raw') }}
