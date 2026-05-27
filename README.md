# UNBC CV Toolkit

Generates two outputs from a single set of source files:

| Output | File | Purpose |
|---|---|---|
| UNBC Faculty CV | `CV_<name>.pdf` | Required by UNBC for annual review / PAR |
| NSERC CCV XML | `CCV_<name>.xml` | Upload to [ccv-cvc.ca](https://ccv-cvc.ca) |

---

## Quick start

1. Copy `data/example/` to `data/<yourname>/`
2. Edit the YAML files and `.bib` file with your information
3. Run:

```bash
bash make_all.sh <yourname>
```

---

## Source files (`data/<yourname>/`)

| File | Contents |
|---|---|
| `publications.bib` | All publications in BibTeX format |
| `students.yaml` | Graduate student supervision |
| `grants.yaml` | Research funding |
| `courses.yaml` | Courses taught |
| `service.yaml` | Committee memberships, editorships, reviewing |
| `awards.yaml` | Awards and distinctions |
| `personal.yaml` | Name, rank, department, education, employment |

---

## Adding publications

**From NASA ADS** (recommended for journal articles):
1. Search [ui.adsabs.harvard.edu](https://ui.adsabs.harvard.edu)
2. Select your papers → Export → BibTeX
3. Paste into `publications.bib`

**Manually** (for reports, grey literature, etc.):
Add a BibTeX entry directly to `publications.bib`.

---

## Pipeline

`make_all.sh` runs in order:

1. `scripts/bib_to_ccv.py` — imports `publications.bib` into CCV XML
2. `scripts/yaml_to_ccv.py` — imports YAML sections into CCV XML
3. `scripts/ccv_filter_6yrs.py` — generates 6-year filtered CCV for NSERC portal
4. `scripts/ccv_to_pdf.py` — generates UNBC-format PDF via XeLaTeX

---

## Requirements

- Python 3.9+
- XeLaTeX (e.g. MacTeX on macOS, TeX Live on Linux)
- `pip install bibtexparser pyyaml`
