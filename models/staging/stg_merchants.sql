-- Merchant attributes as a type-2 slowly changing dimension: one row per plan version with valid_from / valid_to.
-- Fixes industry casing and stray spaces, and two signup date formats (YYYY-MM-DD and MM/DD/YYYY).
with base as (
    select
        merchant_id,
        legal_name,
        country,
        case
            when signup_date like '%/%'
                then substr(signup_date, 7, 4) || '-' || substr(signup_date, 1, 2) || '-' || substr(signup_date, 4, 2)
            else signup_date
        end                                                                  as signup_date,
        upper(substr(trim(industry), 1, 1)) || lower(substr(trim(industry), 2)) as industry,
        lower(trim(plan))                                                    as plan,
        date(plan_effective_from)                                            as valid_from
    from {{ source('raw', 'merchants_raw') }}
)

select
    merchant_id,
    legal_name,
    country,
    signup_date,
    industry,
    plan,
    valid_from,
    coalesce(date(lead(valid_from) over w, '-1 day'), '9999-12-31') as valid_to,
    case when lead(valid_from) over w is null then 1 else 0 end      as is_current
from base
window w as (partition by merchant_id order by valid_from)
