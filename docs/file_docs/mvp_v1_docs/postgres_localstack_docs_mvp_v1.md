# Docs and theory regarding PostgreSQL and LocalStack
Postgres och LocalStack i min `docker-compose.yml`-fil och vilken version jag tänker använda i detta projekt och varför.

**Postgres:**
- `image: postgres:18` - `PostgreSQL 18.4` är senaste stabila (18 släpptes hösten 2025, 19 är i beta just nu, GA väntas september/oktober). Eftersom att jag börjar ett nytt projekt så finns ingen anledning att starta två versioner bakom.

- `POSTGRES_USER/PASSWORD/DB` - hårdkodat rakt av för tillfället nu när jag testar bygga, bara lokal dev. Jag tar och parametriserar via `.env` i nästa steg (`.env.example`), inte samtidigt som jag sätter upp min `docker-compose`

- `healthcheck` - utan den vet varken Jag eller Alembic NÄR `Postgres` faktiskt tar emot anslutningar. Containern kan rapportera "startad" långt innan databasmotorn är redo att prata, vilket är ett typiskt race condition inom orkestrering, samma typ av problem jag kommer stöta på igen med Airflow i MVP v5 och jag stött på i tidigare projekt.

- `volumes: postgres_data:...` - utan namngiven volym försvinner all data varje gång jag kör `docker-compose down`. Med den överlever datan mellan omstarter.

**LocalStack:**
- `image: localstack/localstack:latest` - Sen Maj 2026 speglar `latest`-taggen den senaste STABILA releasen, inte natt-byggen som tidigare. Säkrare val nu än det brukade vara.

- `SERVICES=s3` - `LocalStack` kan emulera dussintals AWS-tjänster (`Lambda, DynamoDB, SQS`...). Jag behöver dock bara en. Att begränsa den håller "igång tiden" nere och signalerar tydligt i koden vad systemet faktiskt använder.
- Samma volume-logik som för Postgres.


**Praktisk varning innan jag kör:** Jag har två andra projekt (`Data Lake` och `Glossary DB`) som redan redan använder `5432` och/eller `4566`. Kör `docker ps` först och dubbelkolla om något projekt redan sitter på de portarna, byt bara den vänstra sidan här, t.ex `"5433:5432"`. Höger sida (vad Postgres lyssnar på *inuti* containern) rörs inte.

## Testa

```bash
docker-compose up -d
docker-compose ps        # båda ska visa "healthy" (postgres) / "running" (localstack)
```
