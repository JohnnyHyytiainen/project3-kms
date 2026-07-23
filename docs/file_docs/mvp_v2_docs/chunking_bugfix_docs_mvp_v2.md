# Infinity bug discovered in chunker.py script.
Efter genomgång och test av chunking logiken upptäcktes en bug, en infinity loop.

## Loop Invarianter (Invariant & Variant) och termineringsbevis.
När det kommer till loopar(`while`) och det pratas om *loop-invarianter* så handlar det till mestadels om att bevisa att en `loop` gör *rätt* sak och *termineringsbevis*(med hjälp av en *variant*) handlar om att bevisa att en loop faktiskt stannar. Detta för att undvika en infinity loop.

Man kan dela upp detta i två delar som är, loop-invariant och termineringsbevis och varianten.

1) - **Loop-invariant**: En invariant är något som aldrig förändras(tänk immutable). Inom programmering är en `loop-invariant` ett påstående eller en 'regel' som **ALLTID** är sann. Den är sann före, under och precis efter min loop har kört. Liknelse:

    - Tänk att du ska loopa över en kortlek och räkna antal röda kort och enbart röda kort, då vänder jag ett kort i taget.
    - Invarianten här är: Antalet röda kort jag har räknat plus antalet röda kort som är kvar i högen är ALLTID lika med det totala antalet röda kort från början.
        - **Varför det här är viktigt:** Den regeln är sann innan jag börjar räkna, den är sann efter varje kort jag vänder och den är fortfarande sann efter alla kort är räknade. Om regeln plötsligt inte stämmer längre så *vet* jag att jag har räknat fel.

2) - **Termineringsbevis och Varianten**: Att terminera betyder att avsluta. Ett termineringsbevis är helt enkelt ett logiskt bevis på att min loop garanterat kommer att stanna(OM den inte gör det så har jag en infinity loop).

    - För att bevisa det här använder man sig av en `variant`. En `variant` är ett värde(oftast en integer) som minskar för varje varv i loopen, *men* som **aldrig kan gå under noll eller annat slutvärde**.
        - Exempel: En mikro som är satt på 60 sekunder. `varianten` här är antalet sekunder kvar på timern. `beviset` är varje sekund som gör att siffran på timern minskar med -1. Eftersom att siffran hela tiden minskar och mikron stängs av när den når 0 så har jag ett `termineringsbevis` då det är fysiskt omöjligt för mikron att värma maten för evigt.
---

- Ett exempel på Termineringsbevis och Varianten med en enkel `while loop` i python:
```python
siffror_kvar = 5
# före loopen börjar
while siffror_kvar > 0:
    print(siffror_kvar)
    siffror_kvar = siffror_kvar -1 # Här minskar värdet
# Efter loopen har stannat
```

- Så här fungear teorin på koden ovan:
    * Termineringsbeviset med en variant: Min variant är variabeln `siffror_kvar`. Eftersom att jag drar bort 1 i varje iteration (`siffror_kvar -1`) så minskar värdet hela tiden. Loopen tillåter bara körning så länge värdet är *över 0*. Eftersom ett tal som minskar med 1 till slut måste nå 0, har jag här bevisat att loopen kommer att terminera (stanna). Det kan inte bli en infinite loop.
    
    * Loop-invariant: En invariant här skulle kunna vara påståendet: 'Variabeln `siffror_kvar` är ett heltal som är *större* än eller lika med 0'. Det är sant innan loopen startar(5), det är sant under loopen(4, 3, 2, 1) och det är sant när loopen precis har stannat (0).

**Sammanfattat:**
* `loop-invariant`: Ett påstående som *alltid* är **sant**
* `termineringsbevis`: Visar att loopen **måste stanna**.
* `variant`: Den siffra eller nedräkning jag tittar på för att göra termineringsbeviset.

---

## Lösningen i chunker.py
- Lösningen var att lyfta ut `position += TARGET_CHUNK_SIZE - OVERLAP_SIZE` ur `while-loopen` för att direkt säga åt koden att 'oavsett om textbiten är bra eller dålig, hoppa fram 1200 chars och kolla nästa bit', eftersom att jag alltid hoppar fram med 1200 tecken kommer min `position` alltid att bli störrre än `len(text)` och när det händer så avslutas loopen naturligt och jag slipper fler infinity loops.


