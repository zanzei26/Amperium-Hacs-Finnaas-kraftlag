# Finnås Kraftlag (Amperium) for Home Assistant

[![Åpne i Home Assistant og legg til i HACS.](https://my.home-assistant.io/badges/hacs_repository.svg)](https://my.home-assistant.io/redirect/hacs_repository/?owner=zanzei26&repository=Amperium-Hacs-Finnaas-kraftlag&category=integration)

Henter strømforbruk, kostnad og pris **direkte fra Finnås Kraftlag** via Amperium-plattformen – de samme tallene som vises i appen **Kraftlaget** fra Finnås Kraftlag, rett inn i Home Assistant.

> _Unofficial Home Assistant integration for the Amperium cloud platform (the **Kraftlaget** app from Finnås Kraftlag, Bømlo). Passwordless OTP login, HAN meter data as native sensors._

## Hvem fungerer dette for?

Bekreftet: kunder hos **Finnås Kraftlag** (Bømlo) som bruker appen **Kraftlaget** (`no.finnas_kraftlag.amperium`). Integrasjonen bruker samme API og samme innlogging som den appen.

Ikke bekreftet: om andre kraftlag bruker samme plattform, og om integrasjonen virker for dem. Prøver du den hos et annet kraftlag, meld fra under [Issues](https://github.com/zanzei26/Amperium-Hacs-Finnaas-kraftlag/issues) hva som skjedde, så oppdaterer vi listen.

## Hva du får

Sensorer per anlegg:

| Sensor | Beskrivelse |
|---|---|
| `sensor.*_forbruk_denne_maneden` | Forbruk hittil i måneden (kWh) |
| `sensor.*_forbruk_i_dag` | Forbruk i dag (kWh) |
| `sensor.*_effekt_na` | Effekt nå (kW). Følger din egen effektsensor hvis du har valgt en, ellers Amperiums verdi (oppdateres en gang i timen) |
| «Energikostnad brutto denne måneden» | Kraft hittil i måneden, brutto inkl. mva, før støtte (kr), fra månedstallene. **Inkl. den faste månedsprisen** (25 kr) |
| «Nettleie etter straumstøtte denne måneden» | Nettleie inkl. kapasitetsledd, **etter** straumstøtte (kr). Nettleien har ikke noe fastledd |
| «Total kostnad etter straumstøtte denne måneden» | Kraft (inkl. fast månedspris) + nettleie som over (kr). Dette er Amperiums eget månedstall |
| «… forrige måned» (energi, nettleie, total) | De samme tre tallene for forrige måned (kr) |
| «Nettleie før straumstøtte forrige måned» | Nettleie inkl. kapasitetsledd, før støtte (kr) for forrige måned: «Nettleie etter straumstøtte» + støtten. Postene ligger som attributter |
| «Straumstøtte trukket fra nettleien forrige måned» | Støtten som er trukket fra nettleien i månedstallene (kr). Gjelder ikke på Norgespris |
| «Fast månedspris (kraft) forrige måned» | Kraftavtalens faste månedspris forrige måned (kr). Den er **en del av** Kraft, ikke et tillegg (eksisterende installasjoner beholder entitets-ID-en `…fastledd_forrige_maned`) |
| «Norgespris-kompensasjon forrige måned» | Norgespris-kompensasjon forrige måned, summert fra timedata (kr) |
| «Netto kostnad forrige måned (din ordning, inkl. fast månedspris)» | Som «Netto kostnad denne måneden», men for forrige måned (kr) |
| «Snittpris forrige måned» / «Snittpris denne måneden» (kr/kWh) | Husets snittpris for ordningen du har valgt. Den faste månedsprisen er med, fordi den ligger i Kraft. Se «Strømregnskap» |
| «Nettleie før straumstøtte denne måneden» | Nettleie inkl. kapasitetsledd, før støtte (kr): «Nettleie etter straumstøtte» + støtten, så før − støtte = etter. Postene ligger som attributter (fra kostnadssvaret, kan avvike noen øre) |
| «Fast månedspris (kraft) denne måneden» | Kraftavtalens faste månedspris (kr). Den er **allerede med** i Kraft og i månedstallene over, ikke et tillegg (eksisterende installasjoner beholder entitets-ID-en `…fastledd_denne_maneden`) |
| «Total brutto denne måneden» | Kraft (inkl. fast månedspris) + nettleie, før støtte (kr): «Total kostnad etter straumstøtte» + støtten |
| «Kapasitetsgrunnlag denne måneden» (kW) | Effekten kapasitetsleddet beregnes av, med trinnet og trinntabellen som attributter |
| «Kapasitetsleddet denne måneden» (kr) og «Til neste kapasitetstrinn» (kW) | Beløpet for trinnet du er i, og hvor mange kW det er til neste trinn. Samme for forrige måned |
| `sensor.*_spotpris_na` | Spotpris nå (kr/kWh), uten mva og påslag. Offisiell pris når den er fastsatt, ellers prisen for gjeldende time fra timelisten (foreløpig). Attributtet `official` viser hvilken |
| «Strømpris nå inkl. påslag og mva» | Prisen du betaler per kWh nå: (spot + påslag) × (1 + mva%), med mva-satsen fra Amperium. Tas fra inneværende time i prislisten. Avledet, ikke bekreftet mot appen |
| `sensor.*_laveste_spotpris_i_dag` | Laveste timepris i dag (kr/kWh), med timen og prisen inkl. påslag og mva (`consumer`) som attributter |
| `sensor.*_hoyeste_spotpris_i_dag` | Høyeste timepris i dag (kr/kWh), med timen og `consumer` som attributter |
| `sensor.*_spotpris_snitt_i_dag` | Gjennomsnittlig timepris i dag (kr/kWh), med snittet inkl. påslag og mva (`consumer`) som attributt |
| `sensor.*_forbruk_i_gar` | Forbruk i går (kWh), summert fra timedata i lokal tid |
| `sensor.*_forbruk_siste_time` | Forbruk siste hele time (kWh) |
| `sensor.*_forbruk_forrige_maned` | Forbruk forrige måned (kWh) |
| `sensor.*_forbruk_dag_denne_maneden` / `..._natt_...` | Forbruk dag og natt hittil i måneden (kWh), se «Dag og natt» |
| `sensor.*_energikostnad_brutto_i_gar` | Brutto energikostnad i går (kr): (spot + påslag) × kWh inkl. mva, før støtte |
| `sensor.*_energikostnad_brutto_denne_maneden_timesummert` | Brutto energikostnad hittil i måneden (kr), summert fra timedata. Har **ikke** med den faste månedsprisen, så den ligger 25 kr under «Energikostnad brutto denne måneden» når timene er à jour |
| `sensor.*_mva_pa_energi_denne_maneden` | Mva-delen av energikostnaden hittil i måneden (kr), inkl. mva på den faste månedsprisen |
| «Straumstøtte trukket fra nettleien denne måneden» | Straumstøtten slik den er trukket fra nettleien (kr) |
| «Norgespris-kompensasjon denne måneden» | Norgespris-kompensasjon summert fra timedata (kr) |
| «Kompensasjon denne måneden (din ordning)» | Beløpet for ordningen du har valgt (kr) |
| «Netto kostnad denne måneden (din ordning)» | Total kostnad for ordningen du har valgt (kr). Den faste månedsprisen er med, én gang. Se «Kostnad: brutto, støtte og netto» |
| «Netto kostnad med Norgespris» / «… med straumstøtte» | Netto for hver ordning, avslått som standard |
| «Norgespris sparer denne måneden» | Hvor mye mer Norgespris gir enn straumstøtte hittil i måneden (kr) |
| `sensor.*_eksport_*` | Eksport (solceller), avslått som standard. Slå på hvis du produserer strøm |
| `sensor.*_han_signal` | HAN-signalstyrke (diagnostikk) |
| `sensor.*_han_signalkvalitet` | HAN-signal som tekst: Ingen signal, Dårlig, Middels, Bra, Veldig bra, Ingen data eller Ikke på nett (diagnostikk) |
| `binary_sensor.*_han_maler_online` | Om HAN-måleren er online (diagnostikk) |
| «Innlogging gyldig til» | Når innloggingen (fornyelsestokenet) utløper (diagnostikk). Tom hvis Amperium ikke har oppgitt tidspunktet, se «Innlogging og oppdateringer» |
| «Innlogging fornyes» | Når gjeldende tilgangstoken utløper og fornyes automatisk (diagnostikk). Flytter seg 5 døgn fram ved hver fornyelse |

Sensorene nullstilles daglig/månedlig, så de passer best som egne dashbordkort (se [`examples/lovelace-amperium.yaml`](examples/lovelace-amperium.yaml)).

### Energidashbordet

Integrasjonen importerer **timeforbruk** (og energikostnad, og eksport hvis du har solceller) som langtidsstatistikk i Home Assistant, rundt en gang i timen. Gå til **Innstillinger → Dashbord → Energi** og velg følgende statistikk:

| I Energidashbordet | Velg |
|---|---|
| Nettforbruk | `Amperium forbruk` |
| Kostnad: «Bruk en entitet som sporer totalkostnaden» | `Amperium energikostnad` |
| Retur til nett (hvis du har solceller) | `Amperium eksport` |

Noen ting å vite:
- Statistikken fylles ut for forrige og inneværende måned første gang. Eldre historikk importeres ikke.
- Tallene kommer med forsinkelse fra Amperium (HAN-måleren oppdateres time for time), så siste time kan mangle en stund.
- `Amperium energikostnad (brutto)` er brutto energikostnad (spot + påslag inkl. mva) **før** straumstøtte/Norgespris, og **uten nettleie**. Nettleie finnes bare i månedstallene fra `/api/sites`.

### Forbruk og pris per time (graf)

«Forbruk siste time» har attributtet `consumption_today` (en rad per hele time i dag), og «Spotpris nå» har `prices_today`. Eksempelet [`examples/lovelace-forbruk-og-pris.yaml`](examples/lovelace-forbruk-og-pris.yaml) viser forbruk som søyler og pris som linje med HACS-kortet apexcharts-card. Eksempelet er ikke testet.

### Live effekt fra en sensor du allerede har (valgfritt)

Amperium oppdaterer effekt bare én gang i timen. Under **Konfigurer** kan du velge en eksisterende effektsensor i Home Assistant, for eksempel en lokal HAN-leser eller **Tibber Pulse/Watty**.

**«Effekt nå»** følger da sensoren din (omregnet til kW, fra og med 0.10.0). Er sensoren utilgjengelig eller uten enhet (W, kW eller MW), brukes Amperiums verdi som reserve. Attributtet `source` viser hva som er brukt (`local_sensor` eller `amperium`), `local_entity` hvilken entitet, og `amperium_kw` hva Amperium selv oppgir. Har du ikke valgt noen sensor, viser «Effekt nå» Amperiums verdi, som bare oppdateres en gang i timen.

I tillegg får du to ekstra sensorer:

- **Effekt nå (live)**: speiler sensoren din, omregnet til kW (W, kW og MW støttes). Samme verdi som «Effekt nå» når sensoren virker.
- **Timeeffekt denne timen (prognose)**: kapasitetsleddet bygger på snittet av hver hele time, ikke på øyeblikkseffekt. Sensoren regner ut timesnittet så langt (tidsvektet) og anslår hvor timen ender hvis effekten holder seg. Attributtene viser snittet så langt og hvor stor del av timen som hadde målinger (`coverage`).

Velg en sensor som måler **hele huset**. En lader som Easee viser bare laderens effekt og passer ikke til kapasitetsleddet. Prognosen starter på nytt hvis Home Assistant startes midt i en time. Da regnes den ut fra målingene som finnes, og `coverage` viser det.

### Live effekt fra Amperium (Dobbe-modul, eksperimentell)

Amperium-appen viser live effekt fra en egen sanntidsstrøm (RabbitMQ/AMQP). Feltet «Effekt nå» fra vanlig henting oppdateres bare én gang i timen og kan stå på 0. Har du en **Dobbe-modul** (HAN-sensoren som sender målingene dine til Amperium), velger du det ved oppsett eller senere under **Konfigurer** («Jeg har en Dobbe-modul»). Svaret er **nei** som standard, også for eksisterende installasjoner. Svarer du ja, kobler integrasjonen seg til den samme strømmen som appen bruker, og du får sensoren **Effekt nå (Amperium live)**. Første gang installeres biblioteket `aio-pika`. Mislykkes det, er bare denne funksjonen av. Svarer du nei, skjer ingenting av dette.

«Effekt nå» bruker denne rekkefølgen: **din egen effektsensor** (se over), så **Amperium live** (siste måling må være under to minutter gammel), så Amperiums timeverdi. Attributtet `source` viser hva som er brukt (`local_sensor`, `amperium_live` eller `amperium`).

**Bekreftet i tester 3. oktober 2026, ikke over lang tid.** Meldingsformatet er lest fra appens kode. Tester i en ekte Home Assistant (én konto med Dobbe-modul) viste status `connected`, omtrent én måling hvert annet sekund, og verdier identiske med en lokal Tibber Pulse (1201 W mot 1,201 kW). Enheten fra Amperium er watt. I en overvåking på 15 minutter kom det meldinger uten opphold gjennom flere fornyelser av abonnementet (hvert 4. minutt). Det vanlige HTTP-kallet alene gir en tom liste, så live kommer bare via strømmen. Se attributtene på «Effekt nå (Amperium live)»: `status` (`connecting`, `connected`, `error`, `unavailable`), `messages` (antall mottatt), `age_seconds`, `last_error` (bare mens det er et problem) og `last_error_at`. Står den på `connected` mens `messages` forblir 0, leverer måleren ikke live-målinger til Amperium akkurat nå. Et svakt mobilsignal på HAN-modulen (se «HAN-signalkvalitet») kan være årsaken, men det er ikke bekreftet. Meld fra under Issues hva du ser, særlig hvis du ikke har Dobbe-modul, eller hvis forbindelsen faller ut over tid.

### Kostnad: brutto, støtte og netto

Amperiums månedstall er lettere å misforstå enn de ser ut til. Dette er hva tallene faktisk inneholder, utledet fra en ekte konto (oktober) og kontrollert mot septemberfakturaen (nr. 3551273). **Det er ikke bekreftet av Amperium.**

- **Nettleie i månedstallene er allerede etter straumstøtte.** Nettleien består av energiledd dag og natt, elavgift, Enova-avgift og **kapasitetsleddet**, minus straumstøtten. Regnestykket går opp på øre: 46,31 + 20,15 + 14,09 + 1,98 + 400 (kapasitetstrinn 5–10 kW) − 154,12 (støtte) = 328,41, mot oppgitt 328,40. Derfor kan nettleien bli negativ i en måned med mye støtte.
- **Kraften har en fast månedspris, og den ligger allerede i Kraft-beløpet.** Hos Finnås Kraftlag er den 25 kr i måneden («Fast månedspris» under Kraft på fakturaen). Den er med i energibeløpet i månedstallene og dermed i Amperiums månedstotal, så den skal **ikke** legges til en gang til. **Nettleien har ikke noe fastledd.** Septemberfakturaen viser det: Kraft 4 028,94 = kraftpris 3 898,26 + påslag 105,68 + fast månedspris 25,00, og nettleie 1 655,30 = dag 660,95 + natt 250,19 + kapasitet 525,00 + forbruksavgift 192,21 + Enova 26,95. Timesummene («timesummert») har ikke med den faste prisen, og derfor er månedstallets energi 25 kr høyere enn timesummen. Amperium oppgir den som «fastledd» i kostnadssvaret (`fixedCharges`): 25 kr for én måned, og 50 kr er observert for 30.08–01.10, som berører to måneder. Versjonene til og med 0.12.0 kalte den «fastledd» og la den til en gang til i «Netto kostnad» (alle varianter), «Total brutto» og i handlingens `price_per_kwh_norgespris_incl_fixed`. Det ga 25 kr for mye. Modellen «fastledd kommer i tillegg» ble innført i 0.5.0 (se CHANGELOG, 0.12.1).
- **Energi** (brutto, spot + påslag inkl. mva, pluss den faste månedsprisen) er før støtte.
- Beløpene ser ut til å være **inkludert mva**.

Derfor regnes sensorene slik:

- **Total brutto** = Amperiums månedstotal (etter støtte) + støtten. Det er det samme som kraft (inkl. fast månedspris) + nettleie før støtte. Tallene er bygget på samme kilde, så før − støtte = etter. Støtten hentes sjeldnere enn månedstallene og kan henge inntil én time etter.
- **Netto med straumstøtte** = Amperiums månedstotal (som allerede er etter støtte og har den faste månedsprisen med).
- **Netto med Norgespris** = Amperiums månedstotal + straumstøtten lagt tilbake − Norgespris-kompensasjonen. Straumstøtte gjelder ikke på Norgespris. For september gir det 3 888,97 + 1 795,27 − 2 819,94 = 2 864,30, det samme som «Totalt» i fakturaregnestykket Kraft + Nettleie + Norgespris (4 028,94 + 1 655,30 − 2 819,94).
- **Norgespris sparer** = Norgespris-kompensasjon − straumstøtten som er trukket fra nettleien (`gridRent`, det som faktisk er trukket på fakturaen). Det finnes bare ett støttetall: «Straumstøtte trukket fra nettleien denne måneden».

Du velger ordningen (Norgespris eller straumstøtte) når du setter opp integrasjonen, og kan endre den under **Konfigurer**. «Netto kostnad denne måneden» bruker valgt ordning. Har du ikke valgt (eldre installasjon), er den utilgjengelig til du velger.

Støtten leses uten hensyn til fortegn (den er alltid et fradrag). Tallene for **forrige måned** hentes fra samme kostnadssvar: nettleie etter støtte er `gridRent.totalAmount`, total er svarets `totalAmount`, og energi er differansen (avledet). Tallene er **omtrentlige**: kompensasjon og energi summeres fra hele timer, mens månedstallene kan ligge noen timer foran eller bak. Bruk dem som peiling, ikke som faktura. Eksempelkortet [`examples/lovelace-kostnad.yaml`](examples/lovelace-kostnad.yaml) viser oppsettet.

### Strømregnskap: forrige måned og valgfri periode

For deg som skal fordele strømkostnaden, for eksempel til en leietaker, er snittprisen per kWh det som teller. Integrasjonen regner den slik (kraft inkluderer den faste månedsprisen, så den er med én gang):

- **Norgespris:** (kraft + nettleie **før** straumstøtte − Norgespris-kompensasjon) / forbruk. Straumstøtten gjelder ikke på Norgespris, så den legges tilbake i nettleien.
- **Straumstøtte:** (kraft + nettleie etter straumstøtte) / forbruk.

«Snittpris denne måneden» og «Snittpris forrige måned» bruker ordningen du har valgt. Sensorene for forrige måned i tabellen over viser delene hver for seg. De bygger på timedata og kostnadsoppgaver som integrasjonen allerede henter, så det er ingen ekstra henting.

**Handlingen `amperium.hent_periode`** gir de samme tallene for en periode du velger selv, for eksempel en leietakers periode. Den leser bare fra Amperium og endrer ingenting. Prøv den under Utviklerverktøy → Handlinger (bruk YAML-modus):

```yaml
action: amperium.hent_periode
data:
  fra: "2026-09-01"
  til: "2026-10-01"
```

- **Fra** er med og **til er ikke med**, så 2026-09-01 til 2026-10-01 er hele september, og en periode som 2026-08-30 til 2026-10-01 går fra og med 30. august til og med 30. september. Datoer regnes som kl. 00:00 lokal tid. Du kan også oppgi dato og klokkeslett, for eksempel `"2026-09-01 06:00:00"`, og det tas da nøyaktig. Perioden kan være opptil 100 dager.
- Svaret har blant annet `consumption_kwh`, `energy_gross`, `grid_before_support`, `subsidy_applied`, `grid_after_support`, `capacity_charge`, `fixed_monthly_price`, `vat_on_energy`, `norgespris_compensation`, `house_cost_norgespris`, `price_per_kwh_norgespris` (og `_subsidy` for straumstøtte), `hours_expected`, `hours_with_data` og `warnings`. Feltene `from` og `to` viser nøyaktig hvilket tidsrom som er regnet ut.
- `energy_gross` er **Kraft** for perioden slik fakturaen viser den: Amperiums totalsum (energi og nettleie etter støtte) minus nettleien. Den inneholder `fixed_monthly_price`, kraftavtalens faste månedspris, som er **en del av** Kraft og ikke et tillegg. `energy_gross_hourly_sum` er summen av timene (kraftpris + påslag), så `energy_gross` = `energy_gross_hourly_sum` + `fixed_monthly_price`. `vat_on_energy` er mva på Kraft, inkl. mva på den faste prisen (septemberfakturaen: 805,79). Feltene `fixed_fee` og `price_per_kwh_norgespris_incl_fixed` fra 0.12.0 er fjernet, siden de la den faste prisen til en gang til.
- `warnings`: `period_not_over` (perioden er ikke ferdig, bare hele timer til nå er med), `hours_missing:N` (N timer mangler i svaret fra Amperium), `charge_hours_differ_from_consumption_hours`, `no_grid_rent_in_answer`, `period_spans_months`, `fixed_monthly_price_missing` (Amperium oppga ingen fast månedspris) og `fixed_monthly_price_not_in_energy_total` (totalsummen er ikke timene pluss den faste prisen, som ellers er det vanlige).

**Testet mot faktura:** Handlingen for 2026-09-01 til 2026-10-01 ga i Home Assistant (v0.12.0) Kraft 4 028,93, nettleie før støtte 1 655,32, Norgespris-kompensasjon 2 819,94, sum 2 864,31, 2 156,638 kWh og 1,3281 kr/kWh. Faktura 3551273 har Kraft 4 028,94, nettleie 1 655,30, Norgespris −2 819,94 og totalt 2 864,30. Forskjellen er 0–2 øre. Rettelsen i 0.12.1 (den faste månedsprisen er med én gang) er kontrollert mot de samme tallene i de automatiske testene, men ikke kjørt i Home Assistant.

**Ikke avklart:** Amperiums beskrivelse av kostnadsoppgaven sier bare «total charges for a site in a given period». Den sier ikke hvordan den faste månedsprisen og kapasitetsleddet fordeles i en periode som ikke er en hel måned. Derfor oppgir handlingen dem hver for seg (`capacity_charge`, `fixed_monthly_price` og `grid_before_support_excl_capacity`) og advarer med `period_spans_months` når perioden går over et månedsskifte. For 30.08–01.10 er det observert 50 kr i fast månedspris (to måneder); kapasitetsleddet for en slik periode er ikke kontrollert mot en faktura. Kontroller tall for perioder som ikke er en hel måned mot en faktura før du bruker dem.

### Kapasitetsledd

Slik beregnes det hos Finnås Kraftlag (tariffark gjeldende fra 1.1.2026, privatkunder): **trinnet bestemmes av snittet av de tre høyeste timeforbrukene i tre ulike døgn** i måneden du faktureres for. Hvis snittet blir 6,5 kW, havner du i trinn 5–10 kW og betaler 400 kr for måneden. Beløpene er **inkludert mva**.

| Trinn | kr/mnd |
|---|---|
| 0–2 kW | 210 |
| 2–5 kW | 300 |
| 5–10 kW | 400 |
| 10–15 kW | 525 |
| 15–20 kW | 700 |
| 20–25 kW | 875 |
| 25–50 kW | 2000 |
| 50–75 kW | 3000 |
| 75–100 kW | 4000 |
| over 100 kW | 5000 |

Tabellen er den samme som Amperium selv leverer, og integrasjonen leser trinnene derfra. Du får:

- **Kapasitetsgrunnlag denne måneden** (kW), **kapasitetsleddet** (kr) og **kW til neste trinn**, alle fra Amperium. Samme tall for forrige måned. Hele trinntabellen ligger som attributt.
- **Kapasitetsgrunnlag (beregnet, tre høyeste døgn):** Integrasjonen finner høyeste time hvert døgn (lokal tid) i denne måneden, tar de tre høyeste døgntoppene og regner snittet. Attributtet `peaks` viser de tre timene (dato, time og kW), og `difference_kw` viser avviket fra Amperiums eget tall. Amperiums tall er fasit. Den beregnede verdien brukes til å se hvilke timer som er toppene.
- **Terskel for ny kapasitetstopp:** Den tredje høyeste døgntoppen. Et nytt døgn må ha en time over dette for å heve grunnlaget.

Timedata fra Amperium kommer med litt forsinkelse, så den pågående timen er ikke med. Har du valgt en effektsensor (se over), viser «Timeeffekt denne timen (prognose)» attributtene `capacity_threshold_kw` og `above_threshold`. Da ser du om timen er på vei over terskelen.

**Kapasitetsgrunnlag: riktig fra første dag.** Integrasjonen henter kraftlagets egne timedata for hele måneden. Kapasitetsgrunnlaget (snittet av høyeste time i hvert av de tre høyeste døgnene) blir derfor riktig selv om du installerer integrasjonen midt i måneden. Lokale kalkulatorer som måler effekt selv, for eksempel fra en HAN-leser, kjenner bare timene etter at de ble satt opp, og kan vise for lavt grunnlag den første måneden. Eksempel fra en installasjon 2. oktober 2026 kl. 21:36: en lokal kalkulator viste 3,29 kW (trinn 2–5 kW), mens riktig grunnlag var 6,38 kW (trinn 5–10 kW). Tallet 3,29 er oppgitt av brukeren og er ikke kontrollert av meg.

Vil du unngå nye topper, bruk «Terskel for ny kapasitetstopp» og attributtet `above_threshold` på «Timeeffekt denne timen (prognose)».

### Når måneden starter

Alle månedstall («denne måneden») regnes fra kl. 00:00 **lokal tid** den 1. i måneden (norsk tid, med sommertid), og stemmer da med timedata og dag/natt-fordelingen. Fra og med 0.10.0. Før det startet hovedhentingen kl. 00:00 UTC, det vil si 01:00 eller 02:00 lokal tid.

### Dag og natt

Dag/natt-forbruket for denne måneden hentes direkte fra Amperium (`gridRent.importedEnergyDay/Night`), slik nettleien faktisk deles. Hvis Amperium ikke leverer dem, summeres det fra timedata i **lokal tid** med dag kl. 06–22 og natt resten. Timene kan endres under **Innstillinger → Enheter og tjenester → Amperium → Konfigurer** og gjelder bare i det tilfellet.

### Timepriser

Sensoren **Spotpris nå** har attributtene `official` (om prisen er offisiell eller foreløpig), `prices_today` og `prices_tomorrow`: lister med én rad per time (`start`, `end`, `spot`, `surcharge`, `vat_percent`, `official`). Prisene for i morgen kommer rundt midten av dagen. `spot` er offisiell spotpris når den er fastsatt, ellers foreløpig pris. Hver time har også `consumer`: prisen du betaler per kWh, (spot + påslag) inkl. mva. Listene kan brukes i for eksempel ApexCharts eller automasjoner.

## Installasjon (HACS)

1. HACS → ⋮ → **Egendefinerte arkiv** (Custom repositories).
2. Lim inn URL-en til dette repoet, kategori **Integration**.
3. Søk opp **Amperium** i HACS og installer.
4. Start Home Assistant på nytt.

Eller manuelt: kopier `custom_components/amperium/` til `config/custom_components/` og start på nytt.

## Oppsett

1. **Innstillinger → Enheter og tjenester → Legg til integrasjon → Amperium**.
2. Skriv inn **telefonnummeret** du bruker hos kraftlaget (samme som i Kraftlaget-appen).
3. Du får en **engangskode på SMS** – skriv den inn.
4. Har du flere anlegg, velger du hvilket du vil følge.
5. Velg ordning: **Norgespris** eller **straumstøtte**.
6. Velg om du har en **Dobbe-modul** (HAN-sensoren som sender målingene til Amperium). Svar nei hvis du er usikker. Du kan endre valget senere under **Konfigurer**. Ferdig.

Integrasjonen logger inn passordløst med engangskode én gang, lagrer et refresh-token og fornyer tilgangen automatisk i bakgrunnen. Du trenger normalt aldri logge inn på nytt.

## Innlogging og oppdateringer

Du logger inn med engangskode én gang. Integrasjonen lagrer tokens i oppsettet, og de ligger igjen når du oppdaterer integrasjonen i HACS og starter Home Assistant på nytt, så en oppdatering logger deg ikke ut.

Tokenene (målt fra svar fra Amperium, ikke dokumentert av dem): tilgangstokenet varer **5 døgn**, fornyelsestokenet ca. **1 år**. Fornyelsen godtar bare et tilgangstoken som har utløpt, så integrasjonen fornyer først når Amperium svarer 401.

**Bekreftet i en ekte Home Assistant (8. oktober 2026):** innloggingen fra 3. oktober ble fornyet automatisk kl. 12:50 norsk tid, uten feil og uten ny engangskode. Det nye tilgangstokenet utløper nøyaktig 5 døgn senere (13. oktober kl. 12:50). Svaret på fornyelsen inneholdt ikke utløpstid for fornyelsestokenet, så «Innlogging gyldig til» kan stå tom selv etter en vellykket fornyelse. Bruk «Innlogging fornyes» for å se neste fornyelse.

- **Token fornyes automatisk** når det utløper. Treffer flere forespørsler 401 samtidig, sendes bare én fornyelse, og de andre bruker det nye tokenet. Nye tokens lagres med en gang.
- **Feil hos Amperium logger deg ikke ut.** Bare når Amperium selv avviser tokenet (HTTP 400/401/403) ber integrasjonen deg logge inn på nytt. Tjenestefeil (HTTP 5xx, 429, nettverk) gir bare en midlertidig feil.
- **Du ser når innloggingen utløper.** Diagnostikksensoren «Innlogging gyldig til» viser tidspunktet Amperium har oppgitt for fornyelsestokenet. Amperium oppgir ikke alltid dette tidspunktet (se over), og da er sensoren tom. Da kan heller ikke varselet under komme, så logg inn på nytt hvis Home Assistant ber om det.
- **Varsel i god tid.** Er det under 30 dager igjen, kommer et varsel under Reparasjoner, og «Konfigurer på nytt» åpnes. Du får en ny engangskode på SMS til samme nummer. Husk døgngrensen for engangskoder.
- **Må du logge inn på nytt av andre grunner** (for eksempel etter lang tid uten kontakt), viser Home Assistant «Konfigurer på nytt» på integrasjonen.
- **Loggen** (nivå info) viser hver fornyelse med utløpstidene, uten tokenverdier: «Amperium token refreshed; refresh token expires … (was …)». Der ser du om fristen på ca. ett år løper videre ved hver fornyelse eller ligger fast. Det er ikke avklart ennå.
- Kjører du et eget skript mot Amperium ved siden av, la det logge inn for seg selv med egen engangskode i stedet for å dele tokenfilen. Det er ikke bekreftet om Amperium gjør et gammelt fornyelsestoken ugyldig når et nytt utstedes.

## Hvordan det virker

Amperium bruker passordløs OTP-innlogging i tillegg til en statisk app-nøkkel (`api-key`). Integrasjonen:

1. Ber om engangskode: `POST /api/accounts/login/request-otp`
2. Logger inn: `POST /api/accounts/login/otp` → access- og refresh-token
3. Fornyer ved behov: `POST /api/accounts/login/refresh-token` (kun når access-token er utløpt)
4. Henter data: `GET /api/sites?charges_from=…&charges_to=…`
5. Henter timepriser: `GET /api/sites/{id}/prices?from=…&to=…` (i dag og i morgen)
6. Henter timeforbruk: `GET /api/sites/{id}/consumption/energy?from=…&to=…&resolution=H`
7. Henter kostnad: `GET /api/sites/{id}/consumption/charges?from=…&to=…&resolution=H`

`resolution` må være én bokstav (`H`, `D` eller `M`). Ord og tall avvises av API-et. Timedata hentes høyst en gang i timen.

Polling hvert 15. minutt (HAN-måleren oppdateres time for time).

## Ansvarsfraskrivelse

Ikonet i `custom_components/amperium/brand/` er ikonet til appen Kraftlaget fra Finnås Kraftlag. Det vises i Home Assistant 2026.3 og nyere, og brukes bare for å vise hvilken tjeneste integrasjonen kobler til. Det betyr ikke at Finnås Kraftlag står bak integrasjonen.


Dette er et uoffisielt, community-laget prosjekt uten tilknytning til Amperium eller noe kraftlag. Det bruker samme offentlige API som Amperium-appen, med din egen innlogging mot din egen konto. Bruk på eget ansvar.

## Versjoner

Alle endringer per versjon, fra 0.1.0 til nå, står i [CHANGELOG.md](CHANGELOG.md). Det samme står i utgivelsesnotatet for hver versjon under [Releases](https://github.com/zanzei26/Amperium-Hacs-Finnaas-kraftlag/releases).

## Lisens

MIT – se [LICENSE](LICENSE).

## Utvikling

De rene beregningene (`derived.py`, `hourpower.py`, deler av `api.py`) har tester som ikke trenger Home Assistant:

```
cd tests && python -m pytest
```
