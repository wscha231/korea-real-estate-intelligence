# Phase 1 API applications and access gates

| Source | Official application | Collector status |
|---|---|---|
| Current legal-dong codes | https://www.data.go.kr/data/15077871/openapi.do | Offline code; live pending |
| Apartment sales detailed | https://www.data.go.kr/data/15126468/openapi.do | Offline code; live pending |
| Apartment sales basic | https://www.data.go.kr/data/15126469/openapi.do | Offline code; live pending |
| Apartment rentals | https://www.data.go.kr/data/15126474/openapi.do | Offline code; live pending |
| K-APT list | https://www.data.go.kr/data/15057332/openapi.do | Not implemented; schema pending |
| K-APT basic info | https://www.data.go.kr/data/15058453/openapi.do | Not implemented; schema pending |
| Building register | https://www.data.go.kr/data/15134735/openapi.do | Not implemented; schema pending |
| R-ONE price statistics | https://www.reb.or.kr/r-one/portal/openapi/openApiIntroPage.do | Not implemented; table codes pending |

## Procedure

1. Sign into data.go.kr, open each API's official page, complete **활용신청** and record the *individual service* permission and call quota.
2. Reconfirm operation path, response result codes, required request parameters, license, commercial use, attribution and redistribution rights; the registry is provisional until authenticated response is validated.
3. Add the approved key as GitHub Actions Secret `DATA_GO_KR_SERVICE_KEY` under **Settings → Secrets and variables → Actions**. Use plain/decoded key so the client encodes it once. Never paste a key into issues, workflow inputs or chat.
4. R-ONE, if approved, must use a separate secret `RONE_API_KEY`; no R-ONE live collector is in Phase 1 yet.
5. Limit the first authenticated request to exactly one RTMS service, one official five-digit LAWD region, and one contract month YYYYMM. Verify page counts and original schema. Auth failure is not an empty market.
6. Do not perform nationwide/historical backfill until permissions, rate limits, current/historic legal codes and private immutable raw storage have all been verified.

Details: `registry/api_registry.csv`, `registry/field_dictionary.csv`, `registry/sources.csv`, `registry/quality_gates.csv`.
