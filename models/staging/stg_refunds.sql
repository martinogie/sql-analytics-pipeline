-- Refunds with typed amount and date.
select
    refund_id,
    payment_id,
    cast(amount as real)                                     as amount,
    date(replace(replace(created_at, 'T', ' '), 'Z', ''))    as refund_date
from {{ source('raw', 'refunds_raw') }}
