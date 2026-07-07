# Docs regarding my ingestion course mapping script
ADR(Arkitekturbeslutsrapport - Architecture Decision Record) or as I would call it AUR(Architecture Understanding Record).

### 1) Skarpare definition av Single Source Of Truth (SSOT)
Till skillnad från när jag la till min `S3`-buckets namn och URL i min `Settings`-class så drog jag slutsatsen om att allt som rör projektet bör gå via den "huvudvägen". Det var en logisk tanke MEN det finns en *kritisk* nyans i arkitekturen som är värd att förstå. Som DE bygger jag script/kod som ska kunna köras i olika miljöer, lokalt(min laptop DEV miljö), i en testserver(Staging) och till slut i drift(Prod). För det kan jag "dela" upp det i några punkter som är:

* **Miljöspecifik Konfiguration (Hemma i t.ex `.env`/ `Settings`):** Saker som ändras beroende på *var* koden körs. DB-passwords, S3-endpoints eller API nycklar.

* **Statisk Domändata (Hemma *i* koden, t.ex `course_mapping.py`):** Saker som är fundamentala sanningar för mitt projekt(Eller företag) *oavsett var koden körs*. Att repot `python_course` ska taggas som `python` är sant oavsett om jag kör koden lokalt på min laptop eller i en produktions pipeline på `AWS`.

* Genom att lägga mappningen i en vanlig `.py` fil(En *explicit* dictionary) kan jag checka in den i git. Den versionhanteras tillsammans med resten av min kod. Om jag hade lagt alla mappningar i `.env` hade jag behövt uppdatera konfigurationsfilerna manuellt på *ALLA* servrar varje gång ett nytt repo kom in.

### 2) Fail loud, not Silent. Varför jag ska vägra att gissa
När jag tittar på listan över repon (t.ex `data_modeling_course`, `llmops_course`) skulle en kreativ kodare kunna tänka: *"Jag bygger bara en smart funktion som automatiskt klipper bort `_course` i slutet av namnet med Regex, så slipper jag uppdatera en lista!"*

I mjukvaruutveckling (Backend/Webb) verkar alla älska den typen av dynamiska funktioner, men **I Data Engineering ser jag redan problem med det.**

Varför? För att data pipelines kräver *determinism* (förutsägbarhet). Säg att jag kanske vill lägga till ett repo som heter `data-engineering-course` (med bindestreck) så hade min Regex regel kanske missat det, eller skapat en konstig S3-nyckel. Helt plötsligt har har jag lagrat flera gigabyte data i min Bronze Layer (S3) under fel namnrymd, och jag märker det inte förrän analytikerna klagar över att data saknas i mina DuckDB Gold-marts i MVP v5.

Genom att använda en explicit `dict` tvingar jag fram designmönstret **Fail Loud**:
Om `ingest.py` stöter på ett mapp namn som inte finns exakt stavat i min lista, kastar Python ett `KeyError`. Pipelinen **kraschar hårt och direkt**. Det är *bra*! Som Data Engineer vill jag att pipelinen ska skrika på hjälp (och generera ett larm i Airflow) så fort den ser data den inte känner igen, istället för att gissa och tyst förorena min lagring downstream.

### 3. Error Handling för Operations (Varför `from None`)
När koden väl kraschar (vilket den ska göra om ett okänt repo dyker upp), så måste felmeddelandet vara läsbart.

När min pipeline körs i MVP v5 via Airflow kommer jag inte sitta och titta på koden. Jag kommer läsa loggar. Om Python kastar ett standard fel får jag ofta en gigantisk "stack trace" som kedjar ihop flera fel.

Att använda `raise KeyError("Tydligt meddelande...") from None` är ett litet men otroligt bra trick `from None` säger till Python: *"Klipp bort all brusig bakgrundsinformation om exakt var i dictionaryn felet skedde, och visa BARA mitt tydliga meddelande till utvecklaren"*. Det gör att loggarna i mitt framtida Airflow system blir rena och läsbara: "Okänt repo 'ny_kurs' - lägg till det i REPO_TO_COURSE_TAG".

---

