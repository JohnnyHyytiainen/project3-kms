# Ändring i data modell och VARFÖR v1 modellen inte fungerar längre
*Skriven 2026-09-26*

[Min första modell](../../architecture/erd/erd_model_v1.png) var passande för datan jag hade när projektet började byggas. I `v1` av `project3-kms` var förutsättningarna att *en fil* var just *ett innehåll* och det höll fram tills slutet av `v2`. Innehållet i korpusen växte och visade något helt annat, så som att samma `README` fanns i *sex* kurser, samma PDF `slides_LLM_theory.pdf` fanns i fyra kurser och samma hämtade `transkript` fanns för två lektioner. Insikten kring de problem som uppstådde med det här var att modellen behöver uppdateras, nuvarande [modell](../../architecture/erd/erd_model_v2.png) bör vara lösningen.

---

### Vad betyder en rad och vad var kärnproblemet med min tidigare modell?

1. Problemet med den initiala ERDn
I den första modellen försökte tabellen `documents` beskriva två helt skilda koncept samtidigt i en och samma rad.

*   **Problemet med "Grain":** En grundregel i Kimball-modellering (och generellt databasdesign) är att en tabell endast får ha ett svar på frågan: *"Vad representerar en rad?"*
*   Den gamla `documents`-tabellen hade två svar:
    1.  Ett unikt *innehåll* (hanterat av dedupliceringen via `file_hash`).
    2.  En specifik *fysisk fil på en specifik plats* (hanterat av `s3_key`, `filename`, och `course_tag`).

**Konsekvens:** Eftersom innehåll avdupliceras (en hash får bara finnas en gång) innebar det att om samma transkript (t.ex en video) förekom i två olika kurser (lektion 16 och 17 i en Databricks kurs), kastades den andra förekomsten bort i tysthet. Den andra kursens tagg försvann eftersom raden (innehållet) redan existerade.

## 2. Den Normaliserade Modellen
För att lösa det tillämpades branschstandard för normalisering: *Innehåll lagras en gång, och tillhörighet lagras som relationer.* Jag skapade en ny tabellstruktur där varje tabell har en strikt definierad "grain":

1.  **`documents`**: Ett unikt innehåll (identifierat med `file_hash`, som nu skyddas av en `UNIQUE CONSTRAINT`).
2.  **`courses`**: En specifik kurs (kursnamn/tagg).
3.  **`source_files`**: En fysisk fil på en fysisk plats på disk. Agerar som en "Junction Table" (kopplingstabell) mellan `documents` och `courses`.
4.  **`chunks`**: En specifik textbit (sektion) från ett dokument på en specifik position.

## 3. Liknelsen: Hur Git (och LangChain) fungerar
Den nuvarande arkitekturen speglar exakt hur versionshanteringssystem som Git (samt LangChains indexerings-API) fungerar internt. 
*   Git sparar varje unikt filinnehåll (Blob) en enda gång, oavsett hur många mappar filen ligger i.
*   Mappstrukturen (Trädet) pekar bara på de platser där innehållet befinner sig.

I KMS'en är `documents` min Blob (innehållet) och `source_files` är mitt Träd (pekarna). Om en README fil ligger i sex olika kurser, sparar jag texten (innehållet) en gång i `documents`, men jag får sex pekare (rader) i `source_files`. Det kallas för *Provenans* (härkomst/ursprung).

## 4. Varför denna refaktorering krävdes NU
Att göra den här ändringen precis innan övergången till MVP v3 (Vektordatabas och Embeddings) var kritiskt.
*   **Derivatens Förbannelse:** Vektordatabasen (Chroma), källhänvisningar i framtida API'er (v4) och data-marts (v5) bygger alla på det grundläggande tillståndet i Postgres.
*   **Kostnaden för Omsättning:** Eftersom lakehouset just nu enbart består av Postgres och rådata från disk, kan hela databasen tömmas och byggas om (rebuild) på ~28 sekunder. Hade jag väntat med detta tills Chroma fylldes med vektorer som saknade metadata om tillhörande kurser, hade kostnaden (och komplexiteten) för en migrering varit massiv.
*   **Framtidssäkring:** När Chroma-vektorerna skapas kommer de att berikas med metadata från alla tillhörande kurser (via relationen `chunks` -> `documents` -> `source_files` -> `courses`).
