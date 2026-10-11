-- Every de-duplicated payment lands in exactly one of fct_payments or quarantine_payments.
select s.payment_id
from {{ ref('stg_payments') }} s
left join {{ ref('fct_payments') }} f on f.payment_id = s.payment_id
left join {{ ref('quarantine_payments') }} q on q.payment_id = s.payment_id
where (f.payment_id is null) = (q.payment_id is null)
