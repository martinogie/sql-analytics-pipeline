-- One row per payment: the latest event the API sent, with typed columns and test-mode payments removed.
-- Handles epoch and ISO timestamps, amounts stored as text ("1,234.50", "$89.00"), and mixed-case codes.
with parsed as (
    select
        payment_id,
        merchant_id,
        case
            when created_at not like '%-%' then datetime(cast(created_at as integer), 'unixepoch')
            else datetime(replace(replace(created_at, 'T', ' '), 'Z', ''))
        end                                                        as created_at,
        cast(replace(replace(amount, '$', ''), ',', '') as real)   as amount,
        upper(trim(currency))                                      as currency,
        lower(trim(status))                                        as status,
        lower(trim(card_brand))                                    as card_brand,
        case when lower(is_test) = 'true' then 1 else 0 end        as is_test,
        datetime(replace(replace(ingested_at, 'T', ' '), 'Z', '')) as ingested_at
    from {{ source('raw', 'payments_raw') }}
),

latest as (
    select
        *,
        row_number() over (partition by payment_id order by ingested_at desc) as event_rank
    from parsed
)

select
    payment_id,
    merchant_id,
    created_at,
    date(created_at) as created_date,
    amount,
    currency,
    status,
    card_brand,
    ingested_at
from latest
where event_rank = 1
  and is_test = 0
