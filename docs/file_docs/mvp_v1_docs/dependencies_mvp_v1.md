# Docs regarding my deps needed for MvP v1
Own docs regarding the dependencies I need to add to start working with my KMS project.

I will first need to separate my two different types of dependencies since I am using a CI-pipe that checks for linting, formatting and eventually testing with every PR prior to merge. These dependencies are:

**SQLAlchemy** - ORM:en som förvandlar ER-modellen ni redan designade (Document/Chunk/User, session_001) till riktiga Python-klasser. En tabell = en klass, en rad = en instans.

**Alembic** - git för schemat. Varje migration är en "commit" på databasstrukturen: kan köras framåt (upgrade) eller bakåt (downgrade), spårbart precis som kodhistorik. Inte ny mark - samma startmall som redan bevisad i Data Lake-projektet.

**psycopg2-binary** - SQLAlchemy pratar inte direkt med Postgres, den behöver en drivrutin som faktiskt talar wire-protokollet. Samma mönster som er Grunden.ai `api_client`: SQLAlchemy är den motor-agnostiska abstraktionen, drivrutinen är den utbytbara detaljen under. `-binary` = förkompilerad, annars krävs en C-kompilator lokalt bara för installationen.

**boto3** - samma AWS SDK du redan använt mot S3 i Data Lake. LocalStack låtsas vara riktig AWS lokalt; koden blir identisk oavsett dev eller prod - bara `AWS_ENDPOINT_URL` ändras. Redan avgjort indirekt, precis som vi hittade i session_001-sökningen häromdagen.

**pydantic-settings** - samma SoC-instinkt du precis tillämpade på docs-strukturen, fast på config: en typad `Settings`-klass istället för `os.environ.get()` utspritt i hela kodbasen. Validerar vid uppstart - saknas `DATABASE_URL` kraschar appen direkt med ett tydligt fel, inte djupt inne i ett script en timme senare. Bonus jag bekräftade i sandlådan: den drar med sig `python-dotenv` automatiskt, ingen separat `uv add` behövs för `.env`-läsning.

**pytest + ruff** (dev-only) - redan kända, redan låsta i CI dag 1.

```bash
uv add sqlalchemy alembic boto3 psycopg2-binary pydantic-settings
uv add --dev pytest ruff
```

`--dev` lägger dem i en egen dependency-grupp i pyproject.toml (verifierat: `[dependency-groups] dev = [...]`) - de behövs för att UTVECKLA systemet, inte för att KÖRA det i produktion. `uv` uppdaterar både `pyproject.toml` och `uv.lock` automatiskt; lockfilen fryser exakta versioner så CI och din maskin garanterat kör samma kod.

Kör de två kommandona - sen tar vi `docker-compose.yml`, LocalStack S3 + Postgres, med resonemang för varje rad innan vi skriver den.