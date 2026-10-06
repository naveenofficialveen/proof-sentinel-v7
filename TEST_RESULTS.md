# Proof Sentinel v7 – verification notes

## Verified in this build

- Python backend source compiles with `python -m compileall`.
- JPEG DQT fingerprint parsing returns a table fingerprint and quality.
- JPEG marker/hex parsing returns marker rows.
- Magic-byte checking detects JPEG content against `.jpg`.
- ELA statistics run and the ELA transparent PNG heat layer is generated.
- OCR runs with Tesseract on a generated document image.
- OCR Document Lock produces ID/name fields plus SHA-256 fingerprints.
- Document Lock now distinguishes `locked`, `not_applicable`, and `ocr_failed` states.
- GPS parsing accepts valid latitude/longitude and rejects invalid ranges.
- Privacy score is calculated from GPS/device/date/author/serial/software metadata.
- Filename regex recognizes WhatsApp Android names, Windows Camera `WIN_...` names, and compact Android/OPPO `IMGYYYYMMDDHHMMSS` names.
- Frontend TS/TSX files were syntax/transpile-checked with TypeScript.
- Docker Compose YAML structure was parsed and the expected backend/frontend services and ports were verified.
- Report generation was tested and verified to include filename pattern, privacy score, GPS position/map link, and Document Lock SHA-256 fields.

## Runtime note

The verification environment used for this build did not have Docker available and the frontend package installation could not finish before the test timeout, so a full Docker/browser runtime test was not possible here. The project remains configured for Docker Desktop with frontend `:3000`, backend `:8000`, PostgreSQL, Redis, and Celery worker.
