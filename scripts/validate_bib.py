#!/usr/bin/env python3
"""Validate journal articles in CCV.xml against CrossRef using DOIs.

Usage: validate_bib.py <data_dir> [--fix]
  --fix   write CrossRef-corrected metadata back to CCV.xml

Queries api.crossref.org for each article that has a DOI.
"""
import sys, os, re, time, json, io
import urllib.request, urllib.parse
import xml.etree.ElementTree as ET

NS = 'http://www.cihr-irsc.gc.ca/generic-cv/1.0.0'
ET.register_namespace('generic-cv', NS)

def local(t): return t.split('}')[-1] if '}' in t else t

def fv(sec, lbl):
    for el in sec.iter():
        if local(el.tag) == 'field' and el.get('label') == lbl:
            for ch in el:
                if local(ch.tag) in ('value', 'lov') and ch.text:
                    return ch.text.strip()
    return ''

def set_fv(sec, lbl, val):
    for el in sec.iter():
        if local(el.tag) == 'field' and el.get('label') == lbl:
            for ch in el:
                if local(ch.tag) in ('value', 'lov'):
                    ch.text = val
                    return
    # field doesn't exist — create it
    f = ET.SubElement(sec, 'field', label=lbl)
    v = ET.SubElement(f, 'value')
    v.text = val

def cr_get(doi):
    url = f'https://api.crossref.org/works/{urllib.parse.quote(doi)}'
    req = urllib.request.Request(url, headers={
        'User-Agent': 'unbc-cv/1.0 (mailto:bmenounos@gmail.com)'
    })
    try:
        with urllib.request.urlopen(req, timeout=10) as r:
            return json.loads(r.read())['message']
    except Exception:
        return None

def cr_year(work):
    for field in ('published-print', 'published-online', 'issued'):
        dp = work.get(field, {}).get('date-parts', [[]])
        if dp and dp[0]:
            return str(dp[0][0])
    return ''

def cr_pages(work):
    return work.get('page', '').replace('–', '-').replace('—', '-')

def cr_authors(work):
    parts = []
    for a in work.get('author', []):
        last  = a.get('family', '')
        first = a.get('given', '')
        init  = (first[0].upper() + '.') if first else ''
        parts.append(f'{last}, {init}' if init else last)
    return ', '.join(parts)

def merge_authors(stored, cr_full):
    """Use CrossRef full list but preserve * markers from stored list."""
    # Build set of starred last names from stored
    starred = set()
    for token in stored.split(','):
        token = token.strip()
        if token.startswith('*'):
            starred.add(token.lstrip('*').split(',')[0].strip().lower())
    # Apply stars to CrossRef list
    parts = []
    for token in cr_full.split(','):
        t = token.strip()
        lastname = t.split(',')[0].strip().lower()
        if lastname in starred and not t.startswith('*'):
            parts.append('*' + t)
        else:
            parts.append(t)
    return ', '.join(parts)

if len(sys.argv) < 2:
    sys.exit('Usage: validate_bib.py <data_dir_or_xml> [--fix]')

arg      = sys.argv[1]
do_fix   = '--fix' in sys.argv
if arg.endswith('.xml'):
    xml_path = arg
    data_dir = os.path.dirname(arg)
else:
    data_dir = arg
    xml_path = os.path.join(data_dir, 'CCV.xml')

tree = ET.parse(xml_path)
root = tree.getroot()

articles = [s for s in root.iter()
            if local(s.tag) == 'section' and s.get('label') == 'Journal Articles'
            and s.get('recordId')]

with_doi    = [s for s in articles if fv(s, 'DOI')]
without_doi = [s for s in articles if not fv(s, 'DOI')]

print(f'Articles: {len(articles)} total, {len(with_doi)} have DOI, {len(without_doi)} lack DOI')
print()

issues  = []
n_fixed = 0

for i, sec in enumerate(with_doi):
    doi   = fv(sec, 'DOI')
    title = fv(sec, 'Article Title')[:55]
    sys.stdout.write(f'\r  Checking {i+1}/{len(with_doi)}: {title:<55}')
    sys.stdout.flush()

    work = cr_get(doi)
    if work is None:
        issues.append(('NO_RESPONSE', doi, ''))
        time.sleep(0.5)
        continue

    # Author check: flag if CrossRef has more authors (truncation)
    bib_auths = fv(sec, 'Authors')
    cr_auths  = cr_authors(work)
    bib_count = len(bib_auths.split(',')) // 2 if bib_auths else 0
    cr_count  = len(work.get('author', []))

    entry_issues = []
    if cr_auths and cr_count > bib_count:
        entry_issues.append(f'authors truncated: {bib_count} stored, {cr_count} in CrossRef')
        if do_fix:
            merged = merge_authors(bib_auths, cr_auths)
            set_fv(sec, 'Authors', merged)
            n_fixed += 1

    checks = [
        ('Year',       fv(sec,'Year'),       cr_year(work),   'year'),
        ('Volume',     fv(sec,'Volume'),      work.get('volume','').strip(), 'volume'),
        ('Page Range', fv(sec,'Page Range').replace('--','-'), cr_pages(work), 'pages'),
    ]
    for fld, bib_val, cr_val, name in checks:
        if cr_val and bib_val != cr_val:
            entry_issues.append(f'{name}: {bib_val!r} → {cr_val!r}')
            if do_fix:
                set_fv(sec, fld, cr_val)
                n_fixed += 1

    if entry_issues:
        issues.append(('MISMATCH', doi, f'{fv(sec,"Article Title")[:50]}: ' + '; '.join(entry_issues)))

    time.sleep(0.1)

print('\n')

if without_doi:
    print(f'── {len(without_doi)} articles WITHOUT DOI (cannot validate) ──')
    for s in without_doi[:15]:
        print(f'  {fv(s,"Year")}: {fv(s,"Article Title")[:70]}')
    if len(without_doi) > 15:
        print(f'  ... and {len(without_doi)-15} more')
    print()

if issues:
    mismatches = [x for x in issues if x[0]=='MISMATCH']
    no_resp    = [x for x in issues if x[0]=='NO_RESPONSE']
    if mismatches:
        print(f'── {len(mismatches)} mismatches ──────────────────────────────')
        for _, doi, detail in mismatches:
            print(f'  {detail}')
    if no_resp:
        print(f'\n── {len(no_resp)} no CrossRef response ──')
        for _, doi, _ in no_resp:
            print(f'  {doi}')
else:
    print('No mismatches found.')

if do_fix and n_fixed:
    ET.indent(tree, space='  ')
    buf = io.BytesIO()
    tree.write(buf, encoding='utf-8', xml_declaration=False)
    content = buf.getvalue().decode('utf-8')
    content = re.sub(r'</generic-cv:(?!generic-cv\b)(\w+)>', r'</\1>', content)
    content = re.sub(r'<generic-cv:(?!generic-cv\b)', '<', content)
    with open(xml_path, 'w', encoding='utf-8') as f:
        f.write('<?xml version="1.0" encoding="UTF-8"?>\n')
        f.write(content)
    print(f'\nFixed {n_fixed} fields in {xml_path}')
