# Datakvalitet i extraction steget

Beslut 1 och 2.
```
extraktion (per dokument)
  ├─ skriver chunkrader i Postgres
  │    └─ vector_id = uuid5(file_hash + chunkens nummer)     <-- beslut 1
  └─ PDF: sparar sidor / tomma sidor / korta sidor           <-- beslut 2
        │
        ▼
embedding (nästa steg)
  ├─ läser alla dokument med status EXTRACTED (ingen spärr)
  └─ skriver till Chroma med vector_id som ID
```
---

#### Hur bör `vector_id` skapas (Beslut 1)

* **Vad:** Varje chunk får ett `ID` som räknas ut från dokumentets innehålls `hash` (`file_hash`) och chunkens nummer i dokumentet. ID't får formen av en `UUID` och skapas med hjälp av `uuid5`.
* **Var:** ID't räknas ut i extraktionen när chunkraden skrivs, den sparas i `chunks.vector_id` och används som ID i `Chroma`.
* **Varför:** Samma innehåll ger *ALLTID* samma ID, i vilken ordning filerna än läses in. Databasens räknare börjar däremot om på 1 vid varje ombyggnad.

--- 

* **Förkastat:**
    * **Sökvägen:** Eftersom samma innehåll kan ligga på flera ställen(Transcript + PDF'er återanvänds och är relevanta för flertalet kurser).

    * **Databasens räknare:** Eftersom den beror på i vilken ordning filerna läses in.

    * **En hash av chunkens text:** Efersom att identisk text i olika dokument då får samma ID och den enda skrivningen skriver över den andras kurser.

* **Kostnad:**
    * En funktion, en rad i extraktionen och en migration(revision) som gör `vector_id` unik.

---

#### Sidantal och kvalitet-spärr (Beslut 2)

* **Vad:** Tre mätvärden sparas per dokument i `documents`:
    * 1) Antal sidor
    * 2) Antal helt TOMMA sidor
    * 3) Antal sidor med text under 50 tecken
    * Fälten är tomma för markdown och transkript som saknar sidor.

* **Ingen spärr:** Alla dokument med status `EXTRACTED` embeddas, även dom där en låg andel av sidorna gav text.
* **Varför:** Alla 94x unika PDF'er som tillsammans har ~1500 sidor. 436 av sidorna ger ingen chunk:
    * 82 PDFer är helt tomma och skulle kräva tyngre `OCR`-verktyg som jag medvetet prioriterat bort för tillfället.
    * 354 har kort text, oftast en rubrik.
    * En spärr skulle ta bort riktigt innehåll ifrån de större föreläsningarna där förklaringarna finns i video-transkripten.

* **Valen omprövas:** I v4, när utvärderingen kan visa om korta chunkar försämrar sökresultaten.
* **Kostnad:** Tre columns, en migration(revision) och några rader till i `PDF-extraktionen`.

