# Embedding-förfrågan och dess innehåll.

Översiktlig dokumentation kring embeddings förfrågor och vad man får tillbaka (API calls).

Nu när jag bygger min `RAG`-applikation (Knowledge Management System) ska texten i min `chunks`-tabell översättas till ett format som en algoritm kan söka i. Det är allt en `embedding` egentligen är: en lång `array` av floats som representerar textens innebörd.

---

### Vad returnerar API't när jag skickar en embedding-förfrågan?

När jag skickar en text ifrån min `chunks`-tabell till `grunden.ai` så kommer jag få tillbaka ett `JSON`-objekt som svar. Det allra viktigasteh är är själva `data-arrayen`. Om jag till exempel skickar in tre texter(`chunks`) så får jag tillbaka en `array` med tre objekt. Varje objekt har ett `index` så jag vet vilken chunk det tillhör och själva `embeddingen`(listan med tal). Det är just den `array` av `floats` jag kommer koppla till min `chunks.vector_id` via `ChromaDB`.

- Vad får jag tillbaka när jag gör en skickar en `embedding-förfrågan`?
    - Jag skickar två saker. **Vilken modell** och en **lista med texter**.
    - Jag får tillbaka ett paket med *tre* delar, dom delarna är:
        - `Data[]` - Som innehåller ett `index`(Vilka av mina texter posten hör till, (0, 1, 2, 3)) men även `embedding` som är en lista med tal, dvs mina vectors.
        - `model`, den modellen som faktiskt svarade.
        - `usage`, hur många tokens som går åt(De tokens jag betalar för).
- Det ser ungefär ut så här:
```text
svar
├─ data[]   en post per text du skickade
│   ├─ index       vilken av dina texter posten hör till (0, 1, 2, 3, ...)
│   └─ embedding   listan med tal, vektorn
├─ model    modellen som faktiskt svarade
└─ usage    tokens du betalar för
```
---

### Dimensioner och vektorns längd(normalisering) och cosinus(cosine)

- Den embedding model `BGE-M3` jag kommer använda mig av kommer ge ut en `array` på 1024 tal för varje text. När jag då väljer att spara min första vector i `ChromaDB` kommer `ChromaDB` automatiskt att sätta sitt interna schema till "här tillåts enbart arrayer med exakt 1024 tal". Om jag vid senare tillfälle väljer att stoppa in en ny vektor ifrån en annan modell som ger 1536 tal så kommer `ChromaDB` att krascha. Så att `Dimensioner` i det här kan man se som själva tabellschemat i `ChromaDB`.

- Vektorns längd(normalisering) och cosine: Det här är kärnan i hur mitt RAG system kommer att fungera. När jag söker i min databas vill jag snabbt hitta den chunk vars vektorer är mest lik min input frågas vektor. För att jämföra två `arrayer` av tal matematiskt tittar man på proportionerna mellan talen, dvs `Cosine similarity`. Istället för att mäta det raka avståndet mellan två punkter (`L2 / Euclidean distance`), mäter `Cosine Similarity` vinkeln (riktningen) mellan två vektorer. Inom Natural Language Processing (`NLP`) är det här branschstandard, eftersom textens "längd" (magnitud) är mindre viktig än dess faktiska "riktning" (innebörd).