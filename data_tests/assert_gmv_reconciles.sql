-- Monthly GMV in the KPI mart equals the sum of succeeded payments in the fact table (to the cent).
with fact as (
    select payment_month, round(sum(amount_usd), 2) as gmv
    from {{ ref('fct_payments') }}
    where status = 'succeeded'
    group by payment_month
)
select k.payment_month, k.gmv_usd, f.gmv
from {{ ref('mart_kpis_monthly') }} k
join fact f on f.payment_month = k.payment_month
where abs(k.gmv_usd - f.gmv) > 0.01
