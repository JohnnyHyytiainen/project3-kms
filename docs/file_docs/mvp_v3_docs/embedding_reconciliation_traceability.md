# Data trust - Reconciliation, referential integrity and traceability.
*written by Johnny 2026-10-17*

Översiktlig dokumentation kring spårbarhet och hur två olika system och dess transaktioner ska hållas i takt i det stora hela.

Status på projektet i skrivande stund är att allting ifrån mina källfiler till vektorer skrivs på ett kommando. Men hur kan jag lita på datan? Det är vad som behöver bekräftas nu.

---

## Traceability / Data lineage (Spårbarhet)
Spårbarhet(Traceability) i mitt fall vilar på referensintegritet(Referential integrity) mellan två separata databaser. Spårbarheten är själva kedjan jag kan följa när referensintegriteten är säkerställd.

- Förenklad förklaring kring just spårbarhet är detta: Kunna spåra någonting end to end i mina databaser(Postgres & Chroma). Det brukar oftast kallas för **Data lineage**, alltså datahärkomst. För mig i min `v3.0` innebär det:
    - När AIn i framtiden ger ett svar baserat på en specifik `vector` så ska jag med 100% säkerhet kunna följa det `ID't` tillbaka till `Chunk`-raden i Postgres, till dokumentet och till sist till källfilen(PDF'en, transkriptet etc). Den kedjan ska aldrig kunna brytas.

## Referential integrity (Referensintegritet)
Referensintegritet som jag nämner ovan i stycket kring traceability handlar om att kunna säkerställa att databasernas struktur håller och inte går sönder. Det är "enkelt" i Postgres då det är inbyggt och är möjligt genom att sätta en `Foreign Key` mellan t.ex `chunks` och `documents`, då vägrar databasen låta den strukturen gå sönder(t.ex genom att stoppa mig från att radera ett dokument om dess chunks finns kvar)

- Utmaningen framför mig för att kunna säkerställa referensintegritet i projektet är att jag har **två** olika databaser (Postgres och ChromaDB). Det finns *inga* inbyggda `Foreign Keys` mellan dom två. Därför behöver jag bygga någon typ av *distribuerad Referensintegritet* via kod och mina val i arkitekturen.

## Reconciliation (Avstämning)
Reconciliation handlar enkelt förklarat om att kunna *bevisa* att spårbarheten i mina nuvarande två databaser leder till samma sak i slutet. Likt den typiska test pyramiden för mjukvarutestet(unit/integration tests) så ska jag applicera det i form av `Data Tests` som testar att min produktionsdata faktiskt mår bra. Det är en kontinuerlig auditering som på så sätt bevisar att min distribuerade referensintegritet fungerar som i sin tur garanterar spårbarheten.

## Data trust (Datatillförlitlighet)
Som rubriken ovan säger handlar data trust om hur tillförlitlig datan är. Går den att lita på?

Data trust *ÄR* slutmålet. Ett Knowledge Management System(KMS) som hela mitt projekt byggs som är *värdelöst* utan tillförlitlighet, om en användare inte kan lita på att datan är korrekt innebär det att något är fel och inte genomtänkt. Om mitt system ibland hittar en text men inte kan säga vilken kurs, lektion eller video det kom ifrån eller tappar bort dokument som borde finnas så försvinner all tillit och allting blir ifrågasatt.

---

### Förenklad sammanfattning av hela kedjan ser ut så här:
- Genom att köra `Reconciliation` så bevisar jag systemets `Referensintegritet`.
    - Detta säkerställer `Spårbarhet` (`Data Lineage`). 
        - När `spårbarheten` är **bevisad**, skapas `Data Trust` hos slutanvändaren.
```
design              -> skapar referensintegriteten
                       (vector_id från innehållet, Chroma först och Postgres sist,
                        upsert, samlingen töms vid ombyggnad)
reconciliation      -> bevisar den, vid tillfället då kontrollen körs
integritet          -> gör spårbarheten möjlig
bevisad spårbarhet  -> data trust
```