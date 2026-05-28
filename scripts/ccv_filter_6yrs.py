#!/usr/bin/env python3
"""Filter CCV-updated.xml to entries from the last 6 years (2020–present).

Sections kept in full (static/biographical):
  Personal Information, Education/Degrees, User Profile,
  Academic Work Experience, Language Skills, Address, Telephone, Email, Website

Sections filtered by date:
  Journal Articles          → Year >= 2020
  Book Chapters             → Year >= 2020
  Reports                   → Year Submitted >= 2020
  Presentations             → Presentation Year >= 2020
  Broadcast Interviews      → First Broadcast Date year >= 2020
  Text Interviews           → Publication Date year >= 2020
  Student/Postdoctoral Supervision → Supervision End Date year >= 2020
                               (or End Date absent/blank → ongoing, keep)
  Research Funding History  → Funding End Date year >= 2020
                               (or End Date blank → ongoing, keep)
  Recognitions              → Effective Date year >= 2020
  Committee Memberships     → Membership End Date year >= 2020 or blank
  Affiliations              → End Date year >= 2020 or blank
  Courses Taught            → End Date year >= 2020 or blank
  Organizational Review Activities → End Date year >= 2020 or blank
  Leaves of Absence         → End Date year >= 2020 or blank
"""
import xml.etree.ElementTree as ET
import re
import copy

import sys as _sys
if len(_sys.argv) < 3:
    _sys.exit('Usage: ccv_filter_6yrs.py <src.xml> <dest.xml>')
SRC  = _sys.argv[1]
DEST = _sys.argv[2]
CUTOFF = 2020

def local(tag):
    return tag.split('}')[-1] if '}' in tag else tag

def field_val(sec, label):
    for f in sec:
        if local(f.tag) == 'field' and f.get('label') == label:
            for v in f:
                lt = local(v.tag)
                if lt in ('value', 'lov') and v.text and v.text.strip():
                    return v.text.strip()
    return ''

def extract_year(s):
    """Pull first 4-digit year from a date string, or None."""
    if not s:
        return None
    m = re.search(r'(\d{4})', s)
    return int(m.group(1)) if m else None

def keep_by_end(sec, end_label):
    """Keep if end date year >= CUTOFF or end date is blank (ongoing)."""
    val = field_val(sec, end_label)
    yr = extract_year(val)
    return yr is None or yr >= CUTOFF

def keep_by_year(sec, year_label):
    val = field_val(sec, year_label)
    yr = extract_year(val)
    return yr is not None and yr >= CUTOFF

def keep_by_date(sec, date_label):
    val = field_val(sec, date_label)
    yr = extract_year(val)
    return yr is not None and yr >= CUTOFF

def keep_supervision(sec):
    end = field_val(sec, 'Supervision End Date')
    yr = extract_year(end)
    return yr is None or yr >= CUTOFF  # blank = ongoing

# Section labels that should be filtered and HOW
FILTER_RULES = {
    'Journal Articles':                  lambda s: keep_by_year(s, 'Year'),
    'Book Chapters':                     lambda s: keep_by_year(s, 'Year'),
    'Reports':                           lambda s: keep_by_year(s, 'Year Submitted'),
    'Presentations':                     lambda s: keep_by_year(s, 'Presentation Year'),
    'Broadcast Interviews':              lambda s: keep_by_date(s, 'First Broadcast Date'),
    'Text Interviews':                   lambda s: keep_by_date(s, 'Publication Date'),
    'Student/Postdoctoral Supervision':  keep_supervision,
    'Research Funding History':          lambda s: keep_by_end(s, 'Funding End Date'),
    'Recognitions':                      lambda s: keep_by_end(s, 'Effective Date'),
    'Committee Memberships':             lambda s: keep_by_end(s, 'Membership End Date'),
    'Affiliations':                      lambda s: keep_by_end(s, 'End Date'),
    'Courses Taught':                    lambda s: keep_by_end(s, 'End Date'),
    'Organizational Review Activities':  lambda s: keep_by_end(s, 'End Date'),
    'Leaves of Absence and Impact on Research': lambda s: keep_by_end(s, 'End Date'),
}

tree = ET.parse(SRC)
root = tree.getroot()

counts = {lbl: {'kept': 0, 'removed': 0} for lbl in FILTER_RULES}

def filter_section(sec):
    lbl = sec.get('label', '')
    if lbl in FILTER_RULES:
        rule = FILTER_RULES[lbl]
        if rule(sec):
            counts[lbl]['kept'] += 1
            return True
        else:
            counts[lbl]['removed'] += 1
            return False
    return True  # keep everything else

def prune(sec):
    """Recursively remove child sections that fail their filter rule."""
    to_remove = []
    for child in sec:
        if local(child.tag) == 'section':
            if not filter_section(child):
                to_remove.append(child)
            else:
                prune(child)
    for child in to_remove:
        sec.remove(child)

prune(root)

# ── Strip subsections the portal doesn't accept on import ─────────────────────
# Funding Sources and Other Investigators are nested inside Research Funding
# History records; Advisory Activities is an empty container. All three cause
# "unrecognized section" warnings on portal import and are not needed there.
STRIP_LABELS = {'Advisory Activities'}

def strip_unrecognized(sec):
    to_remove = []
    for child in sec:
        if local(child.tag) == 'section' and child.get('label', '') in STRIP_LABELS:
            to_remove.append(child)
        else:
            strip_unrecognized(child)
    for child in to_remove:
        sec.remove(child)

strip_unrecognized(root)

# ── Set Funding Status based on end date ──────────────────────────────────────
LOV_AWARDED   = '00000000000000000000000100000800'
LOV_COMPLETED = '00000000000000000000000100000802'

def set_funding_status(root):
    for sec in root.iter():
        if local(sec.tag) != 'section' or sec.get('label') != 'Research Funding History':
            continue
        if not sec.get('recordId'):
            continue
        end_val = field_val(sec, 'Funding End Date')
        end_yr = extract_year(end_val)
        status_lov_id   = LOV_AWARDED if (end_yr is None or end_yr >= 2026) else LOV_COMPLETED
        status_lov_text = 'Awarded'   if (end_yr is None or end_yr >= 2026) else 'Completed'
        for f in sec:
            if local(f.tag) == 'field' and f.get('label') == 'Funding Status':
                for v in f:
                    if local(v.tag) == 'lov':
                        v.set('id', status_lov_id)
                        v.text = status_lov_text

set_funding_status(root)

# Write — strip generic-cv: prefix from child elements (portal format)
import io
ET.register_namespace('generic-cv', 'http://www.cihr-irsc.gc.ca/generic-cv/1.0.0')
buf = io.BytesIO()
tree.write(buf, encoding='utf-8', xml_declaration=False)
content = buf.getvalue().decode('utf-8')
content = re.sub(r'</generic-cv:(?!generic-cv\b)(\w+)>', r'</\1>', content)
content = re.sub(r'<generic-cv:(?!generic-cv\b)', '<', content)

with open(DEST, 'w', encoding='utf-8') as f:
    f.write('<?xml version="1.0" encoding="UTF-8"?>\n')
    f.write(content)

print(f'Written: {DEST}')
print(f'\n{"Section":<45} {"Kept":>6} {"Removed":>8}')
print('-' * 62)
for lbl, c in counts.items():
    print(f'{lbl:<45} {c["kept"]:>6} {c["removed"]:>8}')
