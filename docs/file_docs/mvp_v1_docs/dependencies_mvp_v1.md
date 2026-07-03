# Docs regarding my deps needed for MvP v1
Egna översiktliga docs för mina deps i `MVP V1`

I will first need to separate my two different types of dependencies since I am using a CI-pipe that checks for linting, formatting and eventually testing with every PR prior to merge. These dependencies are:

**SQLAlchemy** - ORM:en som förvandlar min ER-modell som redan designats (Document/Chunk/User) till riktiga Python-klasser. En tabell = en klass, en rad = en instans.

**Alembic** - git för schemat. Varje migration är en "commit" på databasstrukturen: kan köras framåt (upgrade) eller bakåt (downgrade), spårbart precis som kodhistorik. Inte ny mark - samma startmall som redan bevisad i Data Lake-projektet.

**psycopg3-binary** - `SQLAlchemy` pratar inte direkt med Postgres, den behöver en drivrutin som faktiskt talar wire-protokollet. Samma mönster som Grunden.ai `api_client`: `SQLAlchemy` är den engine agnostiska abstraktionen, drivrutinen är den utbytbara detaljen under. `-binary` = förkompilerad, annars krävs en C-kompilator lokalt bara för installationen.


**boto3** - samma AWS SDK jag redan använt mot S3 i mini deploy PoC. LocalStack låtsas vara riktig AWS lokalt, det vill säga, koden blir identisk oavsett dev eller prod - bara `AWS_ENDPOINT_URL` ändras.


**pydantic-settings** - samma SoC-instinkt jag precis tillämpade på docs strukturen, fast på `config`: en typad `Settings`-klass istället för `os.environ.get()` utspritt i hela kodbasen. Validerar vid uppstart, saknas min `DATABASE_URL` kraschar appen direkt med ett tydligt fel, inte djupt inne i ett script en timme senare. 

**pytest + ruff** (dev-only) - redan kända, redan låsta i CI dag 1.

```bash
uv add sqlalchemy alembic boto3 psycopg2-binary pydantic-settings
uv add --dev pytest ruff
```

`--dev` lägger dem i en egen dependency-grupp i pyproject.toml (verifierat: `[dependency-groups] dev = [...]`) - de behövs för att UTVECKLA systemet, inte för att KÖRA det i produktion. `uv` uppdaterar både `pyproject.toml` och `uv.lock` automatiskt; lockfilen fryser exakta versioner så CI och din maskin garanterat kör samma kod.
---

