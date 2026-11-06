# Finnås Kraftlag (Amperium)

Strømforbruk, kostnad og pris **direkte fra Finnås Kraftlag** via Amperium-plattformen – de samme tallene som vises i appen **Kraftlaget** fra Finnås Kraftlag.

**Bekreftet for:** Finnås Kraftlag (Bømlo). Andre kraftlag er ikke bekreftet – prøver du et annet, meld fra under Issues på GitHub.

## Sensorer
- Forbruk denne måneden / i dag (kWh)
- Effekt nå (kW), fra din egen effektsensor hvis du velger en
- Kraft, Nettleie og Totalt hittil i måneden (kr), med samme ord som på fakturaen
- Offisiell spotpris nå (kr/kWh)
- Laveste, høyeste og gjennomsnittlig timepris i dag (kr/kWh)
- Timepriser for i dag og i morgen som attributter på spotpris-sensoren
- Forbruk i går, siste time og forrige måned, dag/natt-fordeling, energikostnad i går
- Straumstøtte og Norgespris-sammenligning
- Nettleie med kapasitetsledd, kraftavtalens faste månedspris og Totalt for din ordning (Norgespris eller straumstøtte)
- Valgfri live effekt fra en sensor du har fra før (f.eks. Tibber Pulse)
- Valgfri, eksperimentell live effekt direkte fra Amperium for deg med Dobbe-modul (samme sanntidsstrøm som appen). Du velger ved oppsett om du har modulen
- Timeforbruk importert som statistikk til Energidashbordet (velg «Amperium forbruk»)
- HAN-måler online (binær)
- Når innloggingen utløper (diagnostikk), med varsel i god tid
- HAN-status hvert 5. minutt, siste data fra HAN-måleren og antall timer Amperium mangler data for (diagnostikk)
- Live-strøm som kommer tilbake av seg selv, med status-sensor og handlingen `amperium.koble_til_live`
- Strømregnskap: nettleie før støtte, fast månedspris, Norgespris og snittpris for forrige måned, og handlingen `amperium.hent_periode` for valgfrie perioder
- Fra 0.17.1: attributtet `til` står på alle «denne måneden»-sensorene som kommer fra øyeblikksbildet (også Nettleie før støtte, fast månedspris og kapasitet)
- Fra 0.17.0: «denne måneden» (Kraft, Nettleie, Norgespris, Totalt, forbruk) kommer fra ett øyeblikksbilde og er lik `hent_periode` for samme tidsrom (`til`)
- Fra 0.16.3: Norgespris bygges også fra timeprisene når alle timer har pris (retter 0,35 kr i oktober 2026 som skyldtes klokkeskiftet)
- Fra 0.16.1: Kraft for forrige måned og i `hent_periode` bygges fra timeprisene når alle timer har pris (retter oktober 2026, som var 7,54 kr for lav hos Amperium)
- Fra 0.16.0: forbruksvektet spotsnitt (denne og forrige måned), strømpris i dag inkl. påslag og mva, og Norgespris-taket som attributter (se README, «Spotsnitt»)
- Fra 0.14.0: navn etter fakturaen. Handlingen `amperium.oppdater_navn` viser og kan bytte de gamle entitets-ID-ene (se README, «Navn og fakturaen»)

## Oppsett
1. Installer via HACS og start Home Assistant på nytt.
2. **Innstillinger → Enheter og tjenester → Legg til integrasjon → Amperium**.
3. Skriv inn telefonnummeret du bruker hos kraftlaget → du får en engangskode på SMS → skriv den inn.
4. Har du flere anlegg, velger du hvilket du vil følge.

Passordløs innlogging med engangskode én gang; token fornyes automatisk i bakgrunnen. En oppdatering i HACS logger deg ikke ut. Du får varsel når det er under 30 dager til innloggingen utløper.

Alle endringer per versjon: [CHANGELOG](https://github.com/zanzei26/Amperium-Hacs-Finnaas-kraftlag/blob/main/CHANGELOG.md).

Se [README](https://github.com/zanzei26/Amperium-Hacs-Finnaas-kraftlag) for detaljer.
