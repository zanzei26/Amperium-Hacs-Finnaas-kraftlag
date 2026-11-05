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
| «Kraft denne måneden» | Kraft hittil i måneden, brutto inkl. mva, før støtte (kr), fra månedstallene. **Inkl. den faste månedsprisen** (25 kr). Fakturaens «Kraft» |
| «Nettleie etter straumstøtte denne måneden» | Nettleie inkl. kapasitetsledd, **etter** straumstøtte (kr). Nettleien har ikke noe fastledd |
| «Kraft + Nettleie etter straumstøtte denne måneden» | Kraft (inkl. fast månedspris) + nettleie som over (kr). Dette er Amperiums eget månedstall |
| «Kraft forrige måned», «Nettleie etter straumstøtte forrige måned», «Kraft + Nettleie etter straumstøtte forrige måned» | De samme tre tallene for forrige måned (kr) |
| «Nettleie før straumstøtte forrige måned» | Nettleie inkl. kapasitetsledd, før støtte (kr) for forrige måned: «Nettleie etter straumstøtte» + støtten. Postene ligger som attributter |
| «Straumstøtte forrige måned» | Støtten som er trukket fra nettleien i månedstallene (kr). Gjelder ikke på Norgespris |
| «Fast månedspris forrige måned» | Kraftavtalens faste månedspris forrige måned (kr). Den er **en del av** Kraft, ikke et tillegg (se «Navn og fakturaen» om entitets-ID-ene) |
| «Norgespris forrige måned» | Norgespris-kompensasjon forrige måned, summert fra timedata (kr) |
| «Totalt forrige måned» | Som «Totalt denne måneden (hittil)», men for forrige måned (kr). Ordningen du har valgt, den faste månedsprisen er med én gang |
| «Snittpris forrige måned (Totalt ÷ forbruk)» / «Snittpris denne måneden (Totalt ÷ forbruk)» (kr/kWh) | Husets snittpris for ordningen du har valgt. Den faste månedsprisen er med, fordi den ligger i Kraft. Se «Strømregnskap» |
| «Nettleie før straumstøtte denne måneden» | Nettleie inkl. kapasitetsledd, før støtte (kr): «Nettleie etter straumstøtte» + støtten, så før − støtte = etter. Postene ligger som attributter (fra kostnadssvaret, kan avvike noen øre) |
| «Fast månedspris denne måneden» | Kraftavtalens faste månedspris (kr). Den er **allerede med** i Kraft og i månedstallene over, ikke et tillegg (se «Navn og fakturaen» om entitets-ID-ene) |
| «Kraft + Nettleie før støtte denne måneden» | Kraft (inkl. fast månedspris) + nettleie, før støtte (kr): «Total kostnad etter straumstøtte» + støtten |
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
| «Kraftpris og påslag i går» | Kraftpris og påslag i går (kr): (spot + påslag) × kWh inkl. mva, før støtte |
| «Kraftpris og påslag denne måneden (sum av timene)» | Kraftpris og påslag hittil i måneden (kr), summert fra timedata. Har **ikke** med den faste månedsprisen, så den ligger 25 kr under «Kraft denne måneden» når timene er à jour |
| «Herav MVA på Kraft denne måneden» | Mva-delen av Kraft hittil i måneden (kr), inkl. mva på den faste månedsprisen |
| «Straumstøtte denne måneden» | Straumstøtten slik den er trukket fra nettleien (kr) |
| «Norgespris denne måneden» | Norgespris-kompensasjon summert fra timedata (kr) |
| «Støtte denne måneden (Norgespris eller straumstøtte)» | Beløpet for ordningen du har valgt (kr) |
| «Totalt denne måneden (hittil)» | Totalt for ordningen du har valgt (kr). Den faste månedsprisen er med, én gang. Se «Kostnad: før støtte, støtte og totalt» |
| «Totalt denne måneden med Norgespris» / «Totalt denne måneden med straumstøtte» | Totalt for hver ordning, avslått som standard |
| «Norgespris sparer denne måneden» | Hvor mye mer Norgespris gir enn straumstøtte hittil i måneden (kr) |
| `sensor.*_eksport_*` | Eksport (solceller), avslått som standard. Slå på hvis du produserer strøm |
| `sensor.*_han_signal` | HAN-signalstyrke (diagnostikk) |
| `sensor.*_han_signalkvalitet` | HAN-signal som tekst: Ingen signal, Dårlig, Middels, Bra, Veldig bra, Ingen data eller Ikke på nett (diagnostikk) |
| `binary_sensor.*_han_maler_online` | Om HAN-måleren er online (diagnostikk). Leses hvert 5. minutt, se «HAN-måleren: offline og hull i timedata» |
| «HAN siste data» | Slutten av den nyeste timen Amperium har forbruk for (tidsstempel, diagnostikk). Samme tidspunkt som attributtet `updated` på «Forbruk denne måneden». Oppdateres én gang i timen, så ikke bruk den til å se sekunder |
| «Manglende timer denne måneden» | Hvor mange hele timer i måneden Amperium ikke har noe forbruk for, inne i dataene (diagnostikk). Timene står som attributtet `hours` (opptil 48). De to nyeste timene regnes ikke med ennå |
| «Innlogging gyldig til» | Når innloggingen (fornyelsestokenet) utløper (diagnostikk). Lages bare når Amperium har oppgitt tidspunktet, ellers finnes den ikke (en eldre sensor uten tidspunkt fjernes ved start fra 0.13.0), se «Innlogging og oppdateringer» |
| «Innlogging fornyes» | Når gjeldende tilgangstoken utløper og fornyes automatisk (diagnostikk). Flytter seg 5 døgn fram ved hver fornyelse |

Sensorene nullstilles daglig/månedlig, så de passer best som egne dashbordkort (se [`examples/lovelace-amperium.yaml`](examples/lovelace-amperium.yaml)).

### Navn og fakturaen (fra 0.14.0)

Fra 0.14.0 heter sensorene det fakturaen kaller postene: **Kraft**, **Fast månedspris** (en del av Kraft), **Nettleie** (før og etter straumstøtte), **Straumstøtte**, **Norgespris** og **Totalt**. Slik kan du lese et tall i Home Assistant og finne samme post på fakturaen.

| Fakturaen | Sensor denne måneden | Sensor forrige måned | Nøkkel i svaret fra `amperium.hent_periode` |
|---|---|---|---|
| Kraft (inkl. fast månedspris) | Kraft denne måneden | Kraft forrige måned | `energy_gross` |
| – herav Fast månedspris | Fast månedspris denne måneden | Fast månedspris forrige måned | `fixed_monthly_price` |
| – herav MVA på Kraft | Herav MVA på Kraft denne måneden | | `vat_on_energy` |
| Kraftpris og påslag (uten fast månedspris) | Kraftpris og påslag denne måneden (sum av timene), Kraftpris og påslag i går | | `energy_gross_hourly_sum` |
| Nettleie før straumstøtte | Nettleie før straumstøtte denne måneden | Nettleie før straumstøtte forrige måned | `grid_before_support` |
| Straumstøtte | Straumstøtte denne måneden | Straumstøtte forrige måned | `subsidy_applied` |
| Nettleie etter straumstøtte | Nettleie etter straumstøtte denne måneden | Nettleie etter straumstøtte forrige måned | `grid_after_support` |
| Kapasitetsledd | Kapasitetsledd denne måneden | Kapasitetsledd forrige måned | `capacity_charge` |
| Norgespris | Norgespris denne måneden | Norgespris forrige måned | `norgespris_compensation` |
| Støtte (Norgespris eller straumstøtte, det du har valgt) | Støtte denne måneden (Norgespris eller straumstøtte) | | |
| Kraft + Nettleie før støtte | Kraft + Nettleie før støtte denne måneden | | |
| Kraft + Nettleie etter straumstøtte | Kraft + Nettleie etter straumstøtte denne måneden | Kraft + Nettleie etter straumstøtte forrige måned | |
| Totalt (ordningen du har valgt) | Totalt denne måneden (hittil) | Totalt forrige måned | |
| Totalt med Norgespris | Totalt denne måneden med Norgespris | | `house_cost_norgespris` |
| Totalt med straumstøtte | Totalt denne måneden med straumstøtte | | `house_cost_subsidy` |
| Snittpris per kWh | Snittpris denne måneden (Totalt ÷ forbruk) | Snittpris forrige måned (Totalt ÷ forbruk) | `price_per_kwh_norgespris`, `price_per_kwh_subsidy` |

Attributtene på sensorene og nøklene i svaret fra `amperium.hent_periode` heter det de alltid har gjort (engelske nøkler som `energy_gross` og `fixed_monthly_price`). De er **ikke** endret, så maler og automasjoner som bruker dem virker som før. Tabellen over viser hvilken fakturapost hver nøkkel hører til.

**Ny installasjon:** entitets-ID-ene lages av de nye navnene, for eksempel `sensor.amperium_<anlegg>_kraft_denne_maneden`.

**Eksisterende installasjon:** Home Assistant endrer ikke en entitets-ID som allerede finnes. Etter oppdateringen står sensorene med de nye navnene, men med de gamle ID-ene. Det er trygt å la det være slik. Vil du ha ID-ene i samsvar med navnene:

1. Ta en sikkerhetskopi. Finn ut hva som bruker de gamle ID-ene (maler, automasjoner, skript, dashbord, intents).
2. Kjør handlingen `amperium.oppdater_navn` under Utviklerverktøy → Handlinger. Uten argumenter **endrer den ingenting**. Den viser bare en liste med `nokkel` (hvilken sensor det er), `fra`, `til` og `status` for hver sensor som er omdøpt. Eventuelt som YAML:

   ```yaml
   action: amperium.oppdater_navn
   data:
     kun_vis: true
   ```

3. Oppdater alt som bruker de gamle ID-ene, i takt med listen fra punkt 2.
4. Kjør handlingen med `kun_vis: false`. Da endres ID-ene. Handlingen er trygg å kjøre flere ganger: det som allerede har riktig ID står som `uendret`.

Statusene i listen: `bytte` (blir endret), `byttet` (er endret), `uendret` (har allerede ID-en), `finnes_allerede` (en annen entitet har den ID-en, så sensoren røres ikke), `eget_navn` (du har selv gitt sensoren navn, så den røres ikke) og `feilet`. Unike ID-er (`unique_id`) endres ikke, så Home Assistant flytter historikken til den nye ID-en. **Kontrollert 3. november 2026 i én installasjon (Norgespris, med Dobbe-modul):** alle 27 ID-er ble byttet, en ny kjøring viste alle som `uendret`, verdiene var like før og etter, og historikken og langtidsstatistikken fortsatte uten brudd under den nye ID-en. Det er ikke prøvd med straumstøtte som valgt ordning, med flere Amperium-oppføringer eller i andre installasjoner, så se etter at grafene henger sammen etter at du har kjørt handlingen. Energidashbordet bruker statistikk med egne ID-er (`amperium:…`) og ikke disse sensorene, og berøres ikke av det.

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

Amperium-appen viser live effekt fra en egen sanntidsstrøm (RabbitMQ/AMQP). Feltet «Effekt nå» fra vanlig henting oppdateres bare én gang i timen og kan stå på 0. Har du en **Dobbe-modul** (HAN-sensoren som sender målingene dine til Amperium), velger du det ved oppsett eller senere under **Konfigurer** («Jeg har en Dobbe-modul (eksperimentell live-strøm)»). Svaret er **nei** som standard, også for eksisterende installasjoner. Svarer du ja, kobler integrasjonen seg til den samme strømmen som appen bruker, og du får sensoren **Effekt nå (Amperium live, eksperimentell)**. Første gang installeres biblioteket `aio-pika`. Mislykkes det, er bare denne funksjonen av. Svarer du nei, skjer ingenting av dette.

«Effekt nå» bruker denne rekkefølgen: **din egen effektsensor** (se over), så **Amperium live** (siste måling må være under to minutter gammel), så Amperiums timeverdi. Attributtet `source` viser hva som er brukt (`local_sensor`, `amperium_live` eller `amperium`).

**Bekreftet i tester 3. oktober 2026, ikke over lang tid.** Meldingsformatet er lest fra appens kode. Tester i en ekte Home Assistant (én konto med Dobbe-modul) viste status `connected`, omtrent én måling hvert annet sekund, og verdier identiske med en lokal Tibber Pulse (samme verdi, bare ulik enhet). Enheten fra Amperium er watt. I en overvåking på 15 minutter kom det meldinger uten opphold gjennom flere fornyelser av abonnementet (hvert 4. minutt). Det vanlige HTTP-kallet alene gir en tom liste, så live kommer bare via strømmen. Se attributtene på «Effekt nå (Amperium live, eksperimentell)»: `status` (`connecting`, `connected`, `error`, `unavailable`), `messages` (antall mottatt), `age_seconds`, `last_error` (bare mens det er et problem) og `last_error_at`. Står den på `connected` mens `messages` forblir 0, leverer måleren ikke live-målinger til Amperium akkurat nå. Et svakt mobilsignal på HAN-modulen (se «HAN-signalkvalitet») kan være årsaken, men det er ikke bekreftet. Meld fra under Issues hva du ser, særlig hvis du ikke har Dobbe-modul, eller hvis forbindelsen faller ut over tid.

#### Når live-strømmen svikter (fra 0.13.0)

- **Nytt abonnement for hvert forsøk.** Hvert forsøk ber Amperium om nye tilkoblingsopplysninger, og opplysninger fra et tidligere forsøk brukes aldri om igjen. Er tilgangstokenet utløpt, fornyes det først (som ved alle andre kall) og kallet gjentas én gang.
- **Ventetid mellom forsøk** øker ved feil fra 5 sekunder til 10 minutter og blir der, og starter på nytt når målinger kommer igjen. Ender strømmen bare eller er den stille (måleren sender ikke), går ventetiden aldri over 5 minutter.
- **Loggen** får én advarsel når et problem begynner (og en ny hvis feilteksten endrer seg) og én melding «working again» når det virker igjen. Ikke en linje per forsøk. Står det «(same connection details as the attempt before)» i feilen, ga Amperium de samme opplysningene to ganger på rad etter en avvisning.
- **Utilgjengelig.** Uten måling i 15 minutter blir «Effekt nå (Amperium live, eksperimentell)» **utilgjengelig** (før det er den ukjent), så en overvåkingsregel i Home Assistant kan fange det. Home Assistant skjuler attributtene til en utilgjengelig sensor. Derfor finnes samme informasjon på diagnostikksensoren **Amperium live status (eksperimentell)** (tilstand: `off`, `starting`, `connecting`, `connected`, `error` eller `unavailable`), som alltid er tilgjengelig. Attributtene `feil` (siste feiltekst, tom når det virker) og `siste_melding` (når siste måling kom) ligger på begge sensorene, i tillegg til `status`, `messages` og de andre som fantes fra før. Status-sensoren skrives ved endringer og ellers høyst én gang i minuttet.
- **Handlingen `amperium.koble_til_live`** dropper strømmen og abonnerer på nytt med en gang, med ventetiden nullstilt, uten å starte Home Assistant på nytt. Den kan brukes fra en automasjon, for eksempel når «Amperium live status (eksperimentell)» har stått på `error` i en halvtime. Den feiler med en forklaring hvis valget «Jeg har en Dobbe-modul (eksperimentell live-strøm)» er av.
- **Slå live-strømmen av:** fjern «Jeg har en Dobbe-modul (eksperimentell live-strøm)» under Konfigurer. Vanlig «Effekt nå» (per time) og alt annet er upåvirket.

**Ikke avklart:** Over to døgn var sensoren ukjent i flere perioder (nesten en tredel av tiden) i Home Assistant. Loggen viste «Network error» med 5,5 minutters mellomrom. Det passer med tidsavbruddet på 30 sekunder pluss ventetiden på 300 sekunder, så kallet som oppretter abonnementet ser ut til å ha fått tidsavbrudd (utledet, ikke målt direkte). Det er også rapportert ACCESS_REFUSED fra meldingskøen en gang (ikke kontrollert, loggen fra da er borte). Årsaken er ikke funnet, og den er ikke at gamle opplysninger gjenbrukes: det gjorde ikke koden før 0.13.0 heller. Integrasjonen kan ikke gjøre noe med at Amperium ikke svarer, bare vente og prøve igjen uten å fylle loggen. Utholdenheten over tid er ikke målt etter 0.13.0.

### HAN-måleren: offline og hull i timedata

- **Status hvert 5. minutt.** «HAN-måler online», «HAN-signal» og «HAN siste data» leses hvert 5. minutt (med samme kall som hovedhentingen, som går hvert 15. minutt). Før kunne et utfall på under 15 minutter forsvinne mellom to lesninger. Appen viser mer fordi den spør oftere. Hvert skifte mellom online og offline står i loggen (nivå info).
- **Signalet er et nivå fra 0 til 4**, ikke dBm. Amperium gir ikke dBm. «HAN-signal» viser nivået og «HAN-signalkvalitet» navnet på det.
- **Det går ikke an å koble HAN-modulen til igjen herfra.** Online-status er modulens egen forbindelse til Amperium-skyen (Wi-Fi eller mobil), og Amperium har ikke noe kall for å starte den på nytt. Integrasjonen har derfor ingen «reconnect» mot modulen. Står den på «Dårlig» eller «Ingen signal», hjelper det å flytte den, for eksempel ut av et metallskap.
- **Hull i timedata.** Hele måneden hentes på nytt hver time, og statistikken for Energidashbordet skrives om hver gang. En time som Amperium leverer i ettertid kommer derfor med av seg selv, og det er ikke noe mer å fylle inn herfra. Er en time aldri levert, finnes det heller ikke noe tall å vise, og integrasjonen finner ikke på noe. «Forbruk denne måneden» og de andre månedstallene fra Amperium er da for lave med dette forbruket. «Manglende timer denne måneden» teller hullene (inne i dataene, de to nyeste timene regnes ikke med), og loggen (nivå info) sier fra når timer mangler og når de kommer. En gang manglet to timer i Amperiums data selv flere timer etterpå, uten at det ble forklart.
- Vil du varsles om at HAN-måleren har vært borte lenge, bruk «HAN-måler online» med `for:`, eller `now() - states('sensor.…han_siste_data')` større enn 90 minutter.

### Sommer- og vintertid

Når klokken stilles tilbake (siste søndag i oktober) har døgnet 25 timer, og når den stilles fram (siste søndag i mars) har det 23. De neste skiftene er 25. oktober 2026 og 28. mars 2027. Integrasjonen regner med faktiske tidspunkter og lokal dato og antar aldri 24 timer i et døgn. Det er testet på hele døgn og måneder rundt begge skiftene (`tests/test_dst.py`, 17 tester): forventet antall timer, «Forbruk i går», dag og natt, kapasitetstopper, statistikk og manglende timer blir riktige.

**Observert 25. oktober 2026 (én installasjon):** Amperium ga 25 timer med forbruk, men bare 24 med kostnad. Kostnadsraden for den første 02:00–03:00-timen manglet. Den timen mangler da i alt som summeres fra timene: «Kraftpris og påslag denne måneden (sum av timene)», Norgespris-summen og kostnadsstatistikken til Energidashbordet. For en måned var det et par kroner. «Kraft» og «Totalt» bruker Amperiums egne totaler og har timen med. `amperium.hent_periode` varsler med `charge_hours_differ_from_consumption_hours`. Integrasjonen finner ikke på noe for en time som mangler.

**Ikke avklart:** om Amperium sender 24 rader eller om to rader faller sammen hos oss (de rå svarene er ikke undersøkt), og hva Amperium sender for dagen med 23 timer. Et avvik gir en advarsel og ikke en feil. Kontroller 28. mars 2027 med `amperium.hent_periode` for den dagen.

### Kostnad: før støtte, støtte og totalt

Amperiums månedstall er lettere å misforstå enn de ser ut til. Dette er hva tallene faktisk inneholder, utledet fra en ekte konto og kontrollert mot en ekte faktura (tallene er ikke publisert). **Det er ikke bekreftet av Amperium.**

- **Nettleie i månedstallene er allerede etter straumstøtte.** Nettleien består av energiledd dag og natt, elavgift, Enova-avgift og **kapasitetsleddet**, minus straumstøtten. Regnestykket gikk opp på øre i en kontroll mot en ekte konto (energiledd + avgifter + kapasitetstrinn − støtte = oppgitt nettleie). Derfor kan nettleien bli negativ i en måned med mye støtte.
- **Kraften har en fast månedspris, og den ligger allerede i Kraft-beløpet.** Hos Finnås Kraftlag er den 25 kr i måneden («Fast månedspris» under Kraft på fakturaen). Den er med i energibeløpet i månedstallene og dermed i Amperiums månedstotal, så den skal **ikke** legges til en gang til. **Nettleien har ikke noe fastledd.** En ekte faktura viser det: Kraft = kraftpris + påslag + fast månedspris, og nettleien = dag + natt + kapasitet + forbruksavgift + Enova. Timesummene («timesummert») har ikke med den faste prisen, og derfor er månedstallets energi 25 kr høyere enn timesummen. Amperium oppgir den som «fastledd» i kostnadssvaret (`fixedCharges`): 25 kr for én måned, og 50 kr er observert for 30.08–01.10, som berører to måneder. Versjonene til og med 0.12.0 kalte den «fastledd» og la den til en gang til i «Netto kostnad» (alle varianter), «Total brutto» og i handlingens `price_per_kwh_norgespris_incl_fixed`. Det ga 25 kr for mye. Modellen «fastledd kommer i tillegg» ble innført i 0.5.0 (se CHANGELOG, 0.12.1).
- **Energi** (brutto, spot + påslag inkl. mva, pluss den faste månedsprisen) er før støtte.
- Beløpene ser ut til å være **inkludert mva**.

Derfor regnes sensorene slik:

- **Kraft + Nettleie før støtte** = Amperiums månedstotal (etter støtte) + støtten. Det er det samme som kraft (inkl. fast månedspris) + nettleie før støtte. Tallene er bygget på samme kilde, så før − støtte = etter. Støtten hentes sjeldnere enn månedstallene og kan henge inntil én time etter.
- **Totalt med straumstøtte** = Amperiums månedstotal (som allerede er etter støtte og har den faste månedsprisen med).
- **Totalt med Norgespris** = Amperiums månedstotal + straumstøtten lagt tilbake − Norgespris-kompensasjonen. Straumstøtte gjelder ikke på Norgespris. På en ekte faktura (september) ga det samme tall som «Totalt» i fakturaregnestykket Kraft + Nettleie − Norgespris.
- **Norgespris sparer** = Norgespris-kompensasjon − straumstøtten som er trukket fra nettleien (`gridRent`, det som faktisk er trukket på fakturaen). Det finnes bare ett støttetall: «Straumstøtte denne måneden».

Du velger ordningen (Norgespris eller straumstøtte) når du setter opp integrasjonen, og kan endre den under **Konfigurer**. «Totalt denne måneden (hittil)» bruker valgt ordning. Har du ikke valgt (eldre installasjon), er den utilgjengelig til du velger.

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
- Svaret har blant annet `consumption_kwh`, `energy_gross`, `grid_before_support`, `subsidy_applied`, `grid_after_support`, `capacity_charge`, `fixed_monthly_price`, `vat_on_energy`, `norgespris_compensation`, `norgespris_kwh`, `house_cost_norgespris`, `price_per_kwh_norgespris` (og `_subsidy` for straumstøtte), `hours_expected`, `hours_with_data` og `warnings`. Feltene `from` og `to` viser nøyaktig hvilket tidsrom som er regnet ut.
- `energy_gross` er **Kraft** for perioden slik fakturaen viser den: Amperiums totalsum (energi og nettleie etter støtte) minus nettleien. Den inneholder `fixed_monthly_price`, kraftavtalens faste månedspris, som er **en del av** Kraft og ikke et tillegg. `energy_gross_hourly_sum` er summen av timene (kraftpris + påslag), så `energy_gross` = `energy_gross_hourly_sum` + `fixed_monthly_price`. `vat_on_energy` er mva på Kraft, inkl. mva på den faste prisen. Feltene `fixed_fee` og `price_per_kwh_norgespris_incl_fixed` fra 0.12.0 er fjernet, siden de la den faste prisen til en gang til.
- `warnings`: `period_not_over` (perioden er ikke ferdig, bare hele timer til nå er med), `hours_missing:N` (N timer mangler i svaret fra Amperium), `charge_hours_differ_from_consumption_hours`, `norgespris_kwh_below_consumption` (se «Norgespris-taket»), `no_grid_rent_in_answer`, `period_spans_months`, `fixed_monthly_price_missing` (Amperium oppga ingen fast månedspris) og `fixed_monthly_price_not_in_energy_total` (totalsummen er ikke timene pluss den faste prisen, som ellers er det vanlige).

**Norgespris-taket (fra 0.14.1).** Norgespris gjelder for inntil 5 000 kWh i måneden for husholdninger. `norgespris_kwh` er antall kWh Amperium regner Norgespris-kompensasjon for (feltet `importedCompensationEnergyNorgespris`, summert over timene). Er det under forbruket i de samme timene (mer enn 0,5 kWh), står `norgespris_kwh_below_consumption` i `warnings`. Advarselen sier ikke hvorfor. Hva feltet betyr, er ikke bekreftet, men tallene under tyder på at det er kWh opp til Amperiums tak (se under).

**Kontrollert mot fakturaer (én installasjon, Norgespris, november 2025 til mars 2026).** Fakturaen gir Norgespris for alt forbruk opp til 5 000 kWh i måneden, regnet kronologisk fra den 1. Amperiums *timetall* for kompensasjon er riktige: summert i delperioder (hver under cirka 4 000 kWh) ga de fakturaens Norgespris-linje på øret for desember og februar, og for januar (som var over 5 000 kWh) innen en tidel av en krone når bare de første 5 000 kWh ble telt. **Men spør du Amperium om en periode med mer enn cirka 4 000 kWh fra periodens start, slutter summen å vokse ved cirka 4 000 kWh, og tallet blir for lavt.** Det gjelder også måneder under 5 000 kWh. Forskjellen var mellom noen hundre og over tusen kroner i desember, januar og februar, og ingenting varsler om det. Taket regnes fra starten på perioden du spør om, så delperioder kappes ikke.

**Integrasjonen bruker foreløpig Amperiums helmånedstall.** «Norgespris», «Støtte» og «Totalt» (denne og forrige måned) og `hent_periode` for hele måneder er derfor for lave i kompensasjon, og «Totalt» for høyt, i måneder over cirka 4 000 kWh. Måneder under 4 000 kWh er ikke berørt (oktober 2026 og mars 2026 stemte). `norgespris_kwh` og `norgespris_kwh_below_consumption` viser når det skjer. Rettelsen er ikke laget ennå.

**Testet mot faktura:** Handlingen for hele september ble kontrollert mot en ekte faktura i Home Assistant (v0.12.0): Kraft, nettleie før støtte, Norgespris-kompensasjon, sum, kWh og kr/kWh stemte med fakturaen innen 0–2 øre. Tallene er ikke publisert. Rettelsen i 0.12.1 (den faste månedsprisen er med én gang) er kontrollert i de automatiske testene, som bruker oppdiktede tall med samme oppbygning som fakturaen, men er ikke kjørt i Home Assistant.

**Oktober 2026 (én faktura, Norgespris):** forbruk, nettleie og kapasitetsledd stemte. «Kraft» var litt høyere på fakturaen, og «Totalt» avvek med under 0,3 %. Amperiums Kraft-total lå om lag 0,3 øre/kWh under fakturaens spotgrunnlag, mens Amperiums Norgespris-tall passet med det. Årsaken er ikke funnet. Den er ikke avrunding i integrasjonen: «Kraft» er Amperiums egen total (se «Kostnad»), og timebeløpene fra Amperium er ikke avrundet. Septemberfakturaen stemte på øret, så avviket er ikke konstant. Bruk tallene som peiling og kontroller mot fakturaen.

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

**Kapasitetsgrunnlag: riktig fra første dag.** Integrasjonen henter kraftlagets egne timedata for hele måneden. Kapasitetsgrunnlaget (snittet av høyeste time i hvert av de tre høyeste døgnene) blir derfor riktig selv om du installerer integrasjonen midt i måneden. Lokale kalkulatorer som måler effekt selv, for eksempel fra en HAN-leser, kjenner bare timene etter at de ble satt opp, og kan vise for lavt grunnlag den første måneden. Eksempel fra en installasjon tidlig i måneden: en lokal kalkulator viste et grunnlag i trinnet 2–5 kW, mens riktig grunnlag lå i trinnet 5–10 kW. Tallet fra kalkulatoren var oppgitt av brukeren og er ikke kontrollert av meg.

Vil du unngå nye topper, bruk «Terskel for ny kapasitetstopp» og attributtet `above_threshold` på «Timeeffekt denne timen (prognose)».

### Når måneden starter

Alle månedstall («denne måneden») regnes fra kl. 00:00 **lokal tid** den 1. i måneden (norsk tid, med sommertid), og stemmer da med timedata og dag/natt-fordelingen. Fra og med 0.10.0. Før det startet hovedhentingen kl. 00:00 UTC, det vil si 01:00 eller 02:00 lokal tid.

### Dag og natt

Dag/natt-forbruket for denne måneden hentes direkte fra Amperium (`gridRent.importedEnergyDay/Night`), slik nettleien faktisk deles. Hvis Amperium ikke leverer dem, summeres det fra timedata i **lokal tid** med dag kl. 06–22 og natt resten. Timene kan endres under **Innstillinger → Enheter og tjenester → Amperium → Konfigurer** og gjelder bare i det tilfellet.

### Timepriser

Sensoren **Spotpris nå** har attributtene `official` (om prisen er offisiell eller foreløpig), `prices_today` og `prices_tomorrow`: lister med én rad per time (`start`, `end`, `spot`, `surcharge`, `vat_percent`, `official`). Prisene for i morgen kommer rundt midten av dagen. `spot` er offisiell spotpris når den er fastsatt, ellers foreløpig pris. Hver time har også `consumer`: prisen du betaler per kWh, (spot + påslag) inkl. mva. Listene kan brukes i for eksempel ApexCharts eller automasjoner.

## Installasjon (HACS)

Krever **Home Assistant 2026.10.4 eller nyere**. Det er den eneste versjonen integrasjonen er testet mot (tidligere sto det 2024.6, men det var aldri prøvd). Eldre versjoner kan virke, men er ikke undersøkt.

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
- **Du ser når innloggingen utløper.** Diagnostikksensoren «Innlogging gyldig til» viser tidspunktet Amperium har oppgitt for fornyelsestokenet. Amperium oppgir ikke alltid dette tidspunktet (se over), og da lages ikke sensoren (fra 0.13.0; før var den ukjent for alltid). «Innlogging fornyes» finnes uansett. Uten tidspunktet kan heller ikke varselet under komme, så logg inn på nytt hvis Home Assistant ber om det.
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
8. Live effekt (bare med Dobbe-modul): `POST /api/sites/{id}/stream/amqp`, og så kobler den til meldingskøen i svaret.

`resolution` må være én bokstav (`H`, `D` eller `M`). Ord og tall avvises av API-et. Timedata hentes høyst en gang i timen.

Polling hvert 15. minutt (HAN-måleren oppdateres time for time). HAN-status (online, signal, siste data) leses i tillegg hvert 5. minutt med det samme kallet som punkt 4.

## Sikkerhet

Hva integrasjonen lagrer, hvor den kobler til, og hvordan du melder en sårbarhet står i [SECURITY.md](SECURITY.md). Kort: telefonnummer og tokens ligger i Home Assistants lagring (ikke kryptert, som hos andre integrasjoner), og ingenting sendes til andre enn Amperium.

## Ansvarsfraskrivelse

Ikonet i `custom_components/amperium/brand/` er ikonet til appen Kraftlaget fra Finnås Kraftlag. Det vises i Home Assistant 2026.3 og nyere, og brukes bare for å vise hvilken tjeneste integrasjonen kobler til. Det betyr ikke at Finnås Kraftlag står bak integrasjonen.


Dette er et uoffisielt, community-laget prosjekt uten tilknytning til Amperium eller noe kraftlag. Det bruker samme offentlige API som Amperium-appen, med din egen innlogging mot din egen konto. Bruk på eget ansvar.

## Versjoner

Alle endringer per versjon, fra 0.1.0 til nå, står i [CHANGELOG.md](CHANGELOG.md). Det samme står i utgivelsesnotatet for hver versjon under [Releases](https://github.com/zanzei26/Amperium-Hacs-Finnaas-kraftlag/releases).

## Lisens

MIT – se [LICENSE](LICENSE).

## Utvikling

Det er to sett med tester:

**Uten Home Assistant (`tests/`).** De rene beregningene og logikken (`derived.py`, `hourpower.py`, `api.py`, `amqp_feed.py`, `period.py`), og kontrolltester mot Amperiums API-beskrivelse.

```
pip install -r requirements-dev.txt   # pytest, pytest-cov, aiohttp og ruff, med låste versjoner
ruff check .                          # lint, innstillinger i pyproject.toml
pytest                                # testene; legg til --cov=custom_components/amperium for dekning
```

Testene ligger i én fil per modul (`tests/test_api.py`, `test_amqp_feed.py`, `test_derived.py`, …), og eksempeldata som flere filer bruker ligger i `tests/helpers.py`. `tests/test_contract.py` sjekker at hvert endepunkt, hver parameter og hvert felt integrasjonen bruker finnes i Amperiums offentlige API-beskrivelse (`tests/contract/swagger.json`, en lagret kopi). `tests/test_fake_api_matches_spec.py` sjekker at de oppdiktede svarene i testene under bare bruker felt fra den beskrivelsen.

**I en ekte Home Assistant (`tests_ha/`).** Hele integrasjonen kjøres i Home Assistant 2026.10.4 (Python 3.14): oppsett og fjerning, alle sensorene fra svar til tilstand (blant annet september-fakturaen), handlingene, oppsettsflyt, alternativer og ny innlogging, HAN-status, manglende timer, statistikk og live-sensorene. Svarene fra Amperium er oppdiktet, men går gjennom den ekte API-klienten (`tests_ha/fake_api.py` erstatter bare selve HTTP-kallet).

```
pip install -r requirements-test-ha.txt   # krever Python 3.14; henter Home Assistant 2026.10.4
pytest -c tests_ha/pytest.ini tests_ha    # tar ca. to minutter
```

**Mot en ekte RabbitMQ (`tests/test_real_rabbitmq.py`).** Live-strømmens tilkobling (`consume_with_aio_pika` og hele løkken rundt) kjøres mot en ekte RabbitMQ 3.13.7 med det ekte aio-pika, ikke et stand-in: meldinger kommer fram, lyttingen avsluttes når megleren fjerner køen eller lukker forbindelsen, feil passord og manglende kø gir en feil i stedet for å henge, og mottakeren tar nytt abonnement når køen er borte. Testene hoppes over uten en megler. I CI kjører de med nyeste aio-pika innen kravet og med 9.6.2; for hånd står docker-kommandoen øverst i filen.

Dekningen er målt: se `CHANGELOG.md` (0.13.1). Det som ikke dekkes er blant annet TLS-forbindelsen (Amperium bruker port 5671; testmegleren har ikke sertifikat), laveste aio-pika som kravet tillater (9.0.0) og den virkelige Amperium-tjenesten, der megler-versjonen ikke er kjent.

GitHub Actions (`.github/workflows/`): `ci.yml` kjører lint, enhetstester (Python 3.12 og 3.14), testene i Home Assistant, testene mot en ekte RabbitMQ, Home Assistants `hassfest` og HACS-valideringen for hver endring. `release.yml` lager bare en utgivelse når lint og testene består. `api-drift.yml` kjører hver mandag: den ser om Amperiums levende API-beskrivelse fortsatt har feltene vi bruker, og om integrasjonen fortsatt virker med den nyeste Home Assistant. Hvordan vi jobber (gren, pull request, grønn CI, fletting) står i [CONTRIBUTING.md](CONTRIBUTING.md).
