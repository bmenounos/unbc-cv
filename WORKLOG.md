# unbc-cv Build Log

## Session: 2026-05-28

### Changes

**Editorial activities**
- Added Annals of Glaciology (Associate Editor, Volume on Vanishing Glaciers, 2025–2026/05) to `data/example/CCV_source_6yr.xml`
- Set Annals of Glaciology end date to 2026/05 in `CCV_source_6yr.xml`

**Presentation Location fixes (`scripts/yaml_to_ccv.py`)**
- Previous fix only prevented adding a *second* Location field but left 25 existing empty Location fields unfilled
- Rewrote fill logic: if Location field exists but is empty → clear it and fill with Canada LOV; if missing → add new field with Canada LOV

**Funding records (`scripts/ccv_filter_6yrs.py` + `scripts/merge_portal_6yr.py`)**
- `ccv_filter_6yrs.py` was stripping `Funding Sources` and `Other Investigators` subsections, causing Total Funding, Portion of Funding Received, Funding Competitive?, and co-applicant fields to be blank in `CCV_last6yrs.xml`
- Removed `Funding Sources` and `Other Investigators` from `STRIP_LABELS` (only `Advisory Activities` remains)
- Extended `merge_portal_6yr.py` to replace all Research Funding History records wholesale from the portal export (`CCV_source_6yr.xml`), which has complete Funding Sources and Other Investigators data
- Result: 17 funding records, all complete

### Current pipeline output (`data/example/`)
- `CCV.xml` — full career (153 articles, 59 grants, 105 supervisees)
- `CCV_last6yrs.xml` — 6-yr filtered (68 articles, 17 grants, 35 supervisees, 7 CM, 10 ORA, 2 editorial) — portal-ready
- `CV_example.pdf` — full-career PDF via XeLaTeX

---

## Session: 2026-05-27

### What was built

Four scripts that form a complete pipeline for generating a UNBC faculty CV PDF and NSERC CCV XML from YAML + BibTeX source files.

### Pipeline

```
publications.bib + *.yaml
        │
        ▼
scripts/bib_to_ccv.py      → data/<name>/CCV.xml  (publications only)
        │
        ▼
scripts/yaml_to_ccv.py     → data/<name>/CCV.xml  (adds personal/edu/employment/
        │                                            students/grants/service/awards)
        ▼
scripts/ccv_filter_6yrs.py → data/<name>/CCV_last6yrs.xml  (2020+ for NSERC portal)
        │
        ▼
scripts/ccv_to_pdf.py      → data/<name>/CV_<name>.pdf  (via XeLaTeX)
```

Run with: `bash make_all.sh example`

### Source files (`data/<name>/`)

| File | Contents | Maps to XML section |
|---|---|---|
| `publications.bib` | Google Scholar BibTeX | Contributions > Publications |
| `personal.yaml` | Name, ORCID, education, employment | Personal Information, Education, Employment |
| `students.yaml` | Graduate students, postdocs, committee | Activities > Supervisory Activities |
| `grants.yaml` | Competitive grants and contracts | Research Funding History |
| `service.yaml` | Committees, reviewing, editorships | Committee Memberships, ORA |
| `awards.yaml` | Teaching/scholarship/service awards | Recognitions |
| `courses.yaml` | (parsed by portal; not yet in XML) | — |

### Script notes

**bib_to_ccv.py**
- Uses `bibtexparser` v1 (`bibtexparser.load()`)
- Maps `@article` → Journal Articles, `@incollection`/`@inbook` → Book Chapters, `@techreport` → Reports
- Other entry types (misc, inproceedings, phdthesis) are skipped with a count

**yaml_to_ccv.py**
- Runs after `bib_to_ccv.py`; reads and modifies existing CCV.xml
- Supervisor role logic: first name in `supervisors` list = Principal Supervisor; second = Co-Supervisor
- Grant role logic: if `pi` contains "Menounos" → Principal Investigator, else Co-Investigator
- Stores ORCID in `Personal Information > Identification` as field label `ORCID`
- Stores city in `Personal Information > Address` as field label `City`

**ccv_filter_6yrs.py**
- Copied verbatim from `port_my_ccv/filter_last_6yrs.py`
- Two args: `<src.xml> <dest.xml>`

**ccv_to_pdf.py**
- Copied from `port_my_ccv/ccv_to_pdf.py` with these changes:
  - Paths derived from `sys.argv[1]`; stem = basename of the data directory
  - Header `family_name` read from XML (dynamic)
  - Subtitle (rank · dept · institution) read from most recent Employment record
  - City read from `Personal Information > Address > City`
  - ORCID read from `Personal Information > Identification > ORCID`
  - `\\[2pt]` and `\\[8pt]}` are conditional on content being present

### Tested output (example/)
- 184 journal articles, 4 book chapters, 3 reports
- 55 grants (competitive + contracts)
- 53 supervisees (graduate students + postdocs + committee)
- PDF: `data/example/CV_example.pdf`
- 6-yr XML: `data/example/CCV_last6yrs.xml`

### Known gaps / future work
- `@misc`, `@inproceedings`, `@phdthesis` entries in .bib are skipped (133 in example)
  - Could add `@inproceedings` → Presentations section
- `courses.yaml` is not yet written into the CCV XML (relevant for NSERC portal upload)
- `university_other` and `community_other` free-text lists in service.yaml are not mapped
- No deduplication guard: re-running `yaml_to_ccv.py` on the same XML will duplicate entries
  — always start from a fresh `bib_to_ccv.py` run (make_all.sh does this correctly)
