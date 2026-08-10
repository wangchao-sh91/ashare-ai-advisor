# AKShare compatibility record

## Approved baseline

- Validation date: 2026-08-07
- Python: 3.12
- AKShare: exactly `1.18.82`
- Scope: public A-share stocks and the explicitly supported broad indexes only

The executable allowlist is defined in `apps/api/app/providers/akshare_allowlist.py`. Application code must select a domain operation from this allowlist and must never accept an AKShare function name from a model or user.

| Operation | Approved interface | Approved parameters | Expected source |
| --- | --- | --- | --- |
| Stock lookup | `stock_info_a_code_name` | none | Exchange lists via AKShare |
| Broad-index lookup | `index_stock_info` | none | JoinQuant public index directory |
| Stock history | `stock_zh_a_hist` | symbol, daily period, dates, unadjusted/approved adjustment, timeout | Eastmoney |
| Index history | `index_zh_a_hist` | symbol, daily period, dates | Eastmoney |
| Financial overview | `stock_financial_abstract` | symbol | Sina Finance |
| Valuation history | `stock_value_em` | symbol | Eastmoney |
| Ownership | `stock_main_stock_holder` | stock | Sina Finance |
| Pledge | `stock_gpzy_individual_pledge_ratio_detail_em` | symbol | Eastmoney |

## Spike results

Runtime reflection verified that all approved functions exist in 1.18.82 and that their signatures contain the allowlisted parameters. Package source inspection verified each returned column mapping; sanitized fixtures preserve those contracts for deterministic tests.

Live calls were attempted with a 40-second per-call budget. The stock directory connection was reset by its upstream, the index directory returned HTML without the expected table, the unfiltered pledge endpoint exceeded the budget, and the remaining concurrent calls did not complete reliably within the budget. These outcomes are recorded as upstream unavailability, not absence of data. They motivated use of the per-instrument pledge interface, bounded execution, retries, typed failures, fixture contracts, and opt-in live smoke tests.

Any AKShare upgrade requires rerunning signature tests, fixture contract tests, and the opt-in live spike before changing `AKSHARE_VERSION`.
