-- Plan versions for a merchant never overlap, so the SCD join returns at most one plan per payment.
select a.merchant_id, a.valid_from, b.valid_from as overlapping_from
from {{ ref('stg_merchants') }} a
join {{ ref('stg_merchants') }} b
  on a.merchant_id = b.merchant_id
 and a.valid_from < b.valid_from
 and b.valid_from <= a.valid_to
