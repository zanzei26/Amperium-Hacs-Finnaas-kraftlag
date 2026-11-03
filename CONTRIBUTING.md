# Slik jobber vi med koden

Kort versjon: **ingen endringer rett på `main`. Én gren, én pull request, grønn CI, så fletting.**

1. Lag en gren fra `main` (for eksempel `rett-reauth` eller `ny-sensor-x`).
2. Gjør endringen med tester. Se «Utvikling» i [README](README.md) for hvordan verktøyene kjøres.
3. Push grenen og åpne en pull request. Fyll ut malen.
4. Vent på at **CI** er grønn: lint og tester (Python 3.12 og 3.14), testene i en ekte Home Assistant,
   Home Assistants `hassfest` og HACS-valideringen.
5. Flett. En flettet endring er **ikke** en utgivelse. En release lages bevisst etterpå fra `main`
   (Actions → Release), og den venter selv på at lint og tester består.

## Innstillinger på GitHub som holder oss til dette

Disse kan bare settes i GitHub (ikke i koden). Settings → Branches → Add branch ruleset for `main`:

- Require a pull request before merging
- Require status checks to pass: `tests / Lint and tests (Python 3.12)`,
  `tests / Lint and tests (Python 3.14)`, `tests / Home Assistant tests (Python 3.14)`
  (legg gjerne til `Home Assistant hassfest` og `HACS validation` når du er trygg på dem)
- Block force pushes

## Hva som kontrolleres automatisk, og hva som ikke gjør det

| Hva | Hvor | Hvor ofte |
|---|---|---|
| Lint og enhetstester | `.github/workflows/tests.yml` | hver endring, og før hver release |
| Integrasjonen i en ekte Home Assistant (fastlåst versjon) | `tests_ha/` | hver endring, og før hver release |
| Hassfest og HACS-validering | `.github/workflows/ci.yml` | hver endring |
| Feltene vi bruker finnes i Amperiums API-beskrivelse | `tests/test_contract.py` | hver endring |
| Nye versjoner av actions og Python-verktøy (kommer som pull requests) | `.github/dependabot.yml` | hver mandag |
| Nyeste Home Assistant, og Amperiums levende API-beskrivelse | `.github/workflows/api-drift.yml` | hver mandag |

Ikke dekket: hva Amperiums API faktisk svarer (bare hva beskrivelsen sier), at tallene stemmer med en
ny faktura (må sjekkes for hånd), og lang tids drift i din egen Home Assistant.
