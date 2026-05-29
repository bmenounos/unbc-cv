#!/usr/bin/env python3
"""Parse publications.bib → create CCV.xml with Publications section.

Usage: bib_to_ccv.py <data_dir>
Creates: <data_dir>/CCV.xml
"""
import sys, os, uuid, re, io
import bibtexparser
from bibtexparser.bparser import BibTexParser
import xml.etree.ElementTree as ET

NS = 'http://www.cihr-irsc.gc.ca/generic-cv/1.0.0'
ET.register_namespace('generic-cv', NS)

def new_id():
    return uuid.uuid4().hex

def local(tag):
    return tag.split('}')[-1] if '}' in tag else tag

def mksec(parent, label, record_id=None):
    el = ET.SubElement(parent, 'section', label=label)
    if record_id:
        el.set('recordId', record_id)
    return el

def mkfield(parent, label, value=None, lov=None):
    f = ET.SubElement(parent, 'field', label=label)
    if value is not None:
        v = ET.SubElement(f, 'value')
        v.text = str(value)
    elif lov is not None:
        v = ET.SubElement(f, 'lov')
        v.text = str(lov)
    return f

def norm_authors(s):
    """'Last, First and Last, First' → 'Last, F., Last, F.'"""
    if not s:
        return ''
    parts = re.split(r'\s+and\s+', s.strip())
    out = []
    for a in parts:
        a = a.strip().strip('{}')
        if ',' in a:
            last, first = a.split(',', 1)
            first = first.strip()
            init = (first[0].upper() + '.') if first else ''
            out.append(f'{last.strip()}, {init}' if init else last.strip())
        else:
            out.append(a)
    return ', '.join(out)

def clean(s):
    """Strip BibTeX braces."""
    return re.sub(r'[{}]', '', s or '')

# ── Main ──────────────────────────────────────────────────────────────────────

if len(sys.argv) < 2:
    sys.exit('Usage: bib_to_ccv.py <data_dir>')

data_dir = sys.argv[1]
bib_path    = os.path.join(data_dir, 'publications.bib')
source_path = os.path.join(data_dir, 'CCV_source.xml')
out_path    = os.path.join(data_dir, 'CCV.xml')

# Start from CCV_source.xml if available (preserves presentations, media, etc.)
# but always rebuild the Publications section from the bib file.
if os.path.exists(source_path):
    tree = ET.parse(source_path)
    root = tree.getroot()
    # Remove existing Publications subsection so we rebuild it from bib
    for contrib in root:
        if local(contrib.tag) == 'section' and contrib.get('label') == 'Contributions':
            for pub_sec in list(contrib):
                if local(pub_sec.tag) == 'section' and pub_sec.get('label') == 'Publications':
                    contrib.remove(pub_sec)
    contrib = None
    for ch in root:
        if local(ch.tag) == 'section' and ch.get('label') == 'Contributions':
            contrib = ch; break
    if contrib is None:
        contrib = mksec(root, 'Contributions')
else:
    root    = ET.Element(f'{{{NS}}}generic-cv')
    contrib = mksec(root, 'Contributions')

pub_cont = mksec(contrib, 'Publications')

with open(bib_path, encoding='utf-8') as f:
    parser = BibTexParser(common_strings=True)
    parser.ignore_nonstandard_types = False
    bib = bibtexparser.load(f, parser)

counts = {'articles': 0, 'chapters': 0, 'reports': 0, 'other': 0}

for entry in bib.entries:
    etype   = entry.get('ENTRYTYPE', '').lower()
    authors = norm_authors(clean(entry.get('author', '')))
    year    = clean(entry.get('year', ''))
    title   = clean(entry.get('title', ''))
    doi     = clean(entry.get('doi', ''))

    if etype == 'article':
        sec = mksec(pub_cont, 'Journal Articles', new_id())
        mkfield(sec, 'Authors',          value=authors)
        mkfield(sec, 'Article Title',    value=title)
        mkfield(sec, 'Journal',          value=clean(entry.get('journal', '')))
        mkfield(sec, 'Volume',           value=clean(entry.get('volume', '')))
        mkfield(sec, 'Page Range',       value=clean(entry.get('pages', '')).replace('--', '-'))
        mkfield(sec, 'Year',             value=year)
        mkfield(sec, 'DOI',              value=doi)
        note = clean(entry.get('note', '')).lower()
        if 'review' in note or 'revision' in note:
            pub_status = 'Submitted'
        elif 'press' in note or 'accepted' in note:
            pub_status = 'In Press'
        else:
            pub_status = 'Published'
        mkfield(sec, 'Publishing Status', lov=pub_status)
        counts['articles'] += 1

    elif etype in ('incollection', 'inbook'):
        sec = mksec(pub_cont, 'Book Chapters', new_id())
        mkfield(sec, 'Authors',          value=authors)
        mkfield(sec, 'Chapter Title',    value=title)
        mkfield(sec, 'Book Title',       value=clean(entry.get('booktitle', '')))
        mkfield(sec, 'Page Range',       value=clean(entry.get('pages', '')).replace('--', '-'))
        mkfield(sec, 'Year',             value=year)
        mkfield(sec, 'Publisher',        value=clean(entry.get('publisher', '')))
        mkfield(sec, 'DOI',              value=doi)
        mkfield(sec, 'Refereed?',        lov='Yes')
        mkfield(sec, 'Publishing Status', lov='Published')
        counts['chapters'] += 1

    elif etype == 'techreport':
        sec = mksec(pub_cont, 'Reports', new_id())
        mkfield(sec, 'Authors',       value=authors)
        mkfield(sec, 'Report Title',  value=title)
        mkfield(sec, 'Other Organization', value=clean(entry.get('institution', '')))
        mkfield(sec, 'Year Submitted', value=year)
        mkfield(sec, 'DOI',           value=doi)
        counts['reports'] += 1

    else:
        counts['other'] += 1

# ── Write XML ─────────────────────────────────────────────────────────────────

ET.indent(ET.ElementTree(root), space='  ')
buf = io.BytesIO()
ET.ElementTree(root).write(buf, encoding='utf-8', xml_declaration=False)
content = buf.getvalue().decode('utf-8')
content = re.sub(r'</generic-cv:(?!generic-cv\b)(\w+)>', r'</\1>', content)
content = re.sub(r'<generic-cv:(?!generic-cv\b)', '<', content)

with open(out_path, 'w', encoding='utf-8') as f:
    f.write('<?xml version="1.0" encoding="UTF-8"?>\n')
    f.write(content)
    f.write('\n')

print(f'Written: {out_path}')
print(f'  Journal articles : {counts["articles"]}')
print(f'  Book chapters    : {counts["chapters"]}')
print(f'  Reports          : {counts["reports"]}')
if counts['other']:
    print(f'  Other (skipped)  : {counts["other"]}')
