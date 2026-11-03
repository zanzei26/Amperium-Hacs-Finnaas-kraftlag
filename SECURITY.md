# Sikkerhet

## Slik melder du en sårbarhet

Bruk **Report a vulnerability** under fanen *Security* i repoet. Da går meldingen privat til
vedlikeholderen. Legg aldri tokens, telefonnummer eller adresser i åpne issues eller pull requests.

Ser du ikke den knappen, åpne en vanlig issue med teksten «trenger privat kanal» og ingen detaljer,
så ordner vi en annen vei.

Det er bare den siste utgivelsen som får rettelser.

## Hva integrasjonen gjør med dataene dine

- **Hvem den snakker med:** `api.amperium.cloud` (HTTPS). Har du valgt «Jeg har en Dobbe-modul», kobler
  den også til meldingskøen (RabbitMQ) som Amperium oppgir i svaret. Tilkoblingen bruker TLS når Amperium
  sier det, med Home Assistants vanlige sertifikatkontroll. Sier Amperium at TLS ikke skal brukes, brukes
  det ikke. Den sender ingenting til andre, og har ingen telemetri.
- **Hva som lagres:** telefonnummeret, tilgangstokenet og fornyelsestokenet ligger i oppføringen i
  Home Assistants lagring (`.storage/core.config_entries`). Det er ikke kryptert, slik som hos andre
  integrasjoner. Den som kan lese lagringen eller en sikkerhetskopi kan logge inn hos Amperium som deg,
  så beskytt sikkerhetskopiene.
- **Hva som logges:** ikke tokens, passord, engangskoder eller telefonnummer. Tilkoblingsopplysningene til
  meldingskøen fjernes fra feiltekster (det er testet).
- **App-nøkkelen i koden** (`API_KEY` i `const.py`) er den samme nøkkelen som Amperium-appen sender. Den er
  ikke en personlig hemmelighet, men den er hentet fra appen, og Amperium kan endre eller sperre den.

## Uoffisielt

Integrasjonen er ikke laget eller støttet av Amperium eller noe kraftlag. Den bygger på et API vi har lest
oss til, uten avtale. Bruk på eget ansvar (se README).

## Hva som er kontrollert, og hva som ikke er det

Kontrollert 3. november 2026:

- kodeskanning med `bandit`: ingen funn med høy eller middels alvorlighet (9 lave, hovedsakelig `assert`)
- kjente sårbarheter i avhengighetene (`pip-audit`): ingen
- hemmeligheter i filene og i historikken: ingen funnet
- test av alle inn- og utganger mot Amperiums API-beskrivelse, og av hele integrasjonen i en ekte Home Assistant

**Ikke gjort:** en manuell sikkerhetsgjennomgang av hele koden, en trusselmodell, og test av
live-strømmen mot en ekte meldingskø. Skanningene finner bare kjente mønstre.

## Avhengigheter og automatikk

- Dependabot ser ukentlig etter nye versjoner av GitHub-actions og av Python-pakkene i
  `requirements-dev.txt` og `requirements-test-ha.txt`. Hver endring går gjennom CI.
- GitHub-actions er låst til én bestemt commit (med versjonen som kommentar), slik at en endring hos
  andre ikke kan slå inn uten at vi ser den.
- Biblioteket for live-strømmen (`aio-pika`) har en øvre versjonsgrense og installeres første gang valget
  slås på.
