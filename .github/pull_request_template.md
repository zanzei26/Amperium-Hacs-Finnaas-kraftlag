## Hva endres og hvorfor

<!-- Kort. Hva var problemet, og hva gjør endringen? -->

## Hvordan er det kontrollert

- [ ] `ruff check .` og `pytest` er grønne (CI kjører det)
- [ ] Home Assistant-testene (`pytest -c tests_ha/pytest.ini tests_ha`) er grønne (CI kjører det)
- [ ] Endringen har en test som feiler uten den (eller en forklaring på hvorfor det ikke går)
- [ ] Tall som angår penger er kontrollert mot en faktura
- [ ] Det som ikke er prøvd i en ekte Home Assistant er nevnt under

## Ikke prøvd / kjent usikkerhet

<!-- Vær konkret. «Ikke kjørt i en ekte Home Assistant» er et fullgodt svar. -->

## Dokumentasjon og versjon

- [ ] CHANGELOG og README er oppdatert (ved endringer som brukere merker)
- [ ] Versjonen i `manifest.json` er hevet hvis dette skal ut som en ny versjon (release lages etterpå, ikke av selve flettingen)
