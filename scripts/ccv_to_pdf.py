#!/usr/bin/env python3
"""Generate an academic CV PDF from CCV-updated.xml using LaTeX."""
import xml.etree.ElementTree as ET
import subprocess, os, sys, re, textwrap, datetime

if len(sys.argv) < 2:
    print('Usage: ccv_to_pdf.py <CCV.xml> [--credit]', file=sys.stderr); sys.exit(1)
XML_PATH    = sys.argv[1]
SHOW_CREDIT = '--credit' in sys.argv
_dir        = os.path.dirname(os.path.abspath(XML_PATH))
_stem       = os.path.basename(os.path.dirname(os.path.abspath(XML_PATH)))
TEX_PATH    = os.path.join(_dir, f'CV_{_stem}.tex')
PDF_PATH    = os.path.join(_dir, f'CV_{_stem}.pdf')
NSERC_PATH  = os.path.join(_dir, f'CV_{_stem}_nserc_contributions.txt')

# ── CRediT role annotations ────────────────────────────────────────────────────
CREDIT_ROLES = {}   # normalized title → sorted list of role codes
_CREDIT_LEGEND = (
    'Contributor roles (CRediT taxonomy, https://credit.niso.org/): '
    'co=Conceptualization, dc=Data curation, fa=Formal analysis, '
    'fu=Funding acquisition, in=Investigation, me=Methodology, '
    'pa=Project administration, re=Resources, so=Software, '
    'su=Supervision, va=Validation, vi=Visualization, '
    'wo=Writing–original draft, wr=Writing–review & editing.'
)

def _norm_title(t):
    return re.sub(r'\s+', ' ', re.sub(r'[{}\\]', '', t).lower().strip())

def _bib_field(entry_text, field):
    """Extract a BibTeX field value handling nested braces."""
    m = re.search(rf'\b{field}\s*=\s*\{{', entry_text, re.IGNORECASE)
    if not m:
        return None
    start = m.end(); depth = 1
    for i, c in enumerate(entry_text[start:], start):
        if c == '{': depth += 1
        elif c == '}':
            depth -= 1
            if depth == 0:
                return entry_text[start:i]
    return None

if SHOW_CREDIT:
    _bib_path = os.path.join(_dir, 'publications.bib')
    if os.path.exists(_bib_path):
        _bib_text = open(_bib_path, encoding='utf-8').read()
        for _entry in re.split(r'(?=^@)', _bib_text, flags=re.MULTILINE):
            _title  = _bib_field(_entry, 'title')
            _credit = _bib_field(_entry, 'credit')
            if _title and _credit:
                _key   = _norm_title(_title)
                _roles = sorted(r.strip() for r in _credit.split(',') if r.strip())
                if _roles:
                    CREDIT_ROLES[_key] = _roles

# ── XML helpers ───────────────────────────────────────────────────────────────

def local(tag):
    return tag.split('}')[-1] if '}' in tag else tag

def field_val(sec, label):
    """Get first matching field value (checks value, lov, refTable) by label."""
    for el in sec.iter():
        if local(el.tag) == 'field' and el.get('label') == label:
            for ch in el:
                lt = local(ch.tag)
                if lt in ('value', 'lov') and ch.text and ch.text.strip():
                    return ch.text.strip()
                if lt == 'refTable':
                    org = ch.get('name', '')
                    if org:
                        return org
    return ''

def fields_dict(sec):
    """Return dict of all field label→value for direct children fields."""
    result = {}
    for el in sec:
        if local(el.tag) == 'field':
            lbl = el.get('label', '')
            for ch in el:
                lt = local(ch.tag)
                if lt in ('value', 'lov') and ch.text and ch.text.strip():
                    result[lbl] = ch.text.strip()
                    break
                if lt == 'refTable' and ch.get('name'):
                    result[lbl] = ch.get('name')
                    break
    return result

def child_sections(sec, label=None):
    """Return direct child sections, optionally filtered by label."""
    result = []
    for el in sec:
        if local(el.tag) == 'section':
            if label is None or el.get('label') == label:
                result.append(el)
    return result

def find_section(root, *labels):
    """Find nested section by successive label matching."""
    sec = root
    for lbl in labels:
        found = None
        for el in sec:
            if local(el.tag) == 'section' and el.get('label') == lbl:
                found = el
                break
        if found is None:
            return None
        sec = found
    return sec

def find_all(root, label):
    """Find all top-level child sections with given label."""
    return [el for el in root if local(el.tag) == 'section' and el.get('label') == label]

# ── LaTeX escaping ────────────────────────────────────────────────────────────

_ESC = str.maketrans({
    '&':  r'\&',
    '%':  r'\%',
    '$':  r'\$',
    '#':  r'\#',
    '_':  r'\_',
    '{':  r'\{',
    '}':  r'\}',
    '~':  r'\textasciitilde{}',
    '^':  r'\textasciicircum{}',
    '\\': r'\textbackslash{}',
    '\u2500': '--',        # BOX DRAWINGS LIGHT HORIZONTAL
    '\u2014': '---',       # em dash
    '\u2013': '--',        # en dash
    '\u2019': "'",         # right single quotation mark
    '\u2018': "`",         # left single quotation mark
    '\u201c': "``",        # left double quotation mark
    '\u201d': "''",        # right double quotation mark
    '\u2026': r'\ldots{}', # ellipsis
    '\u2212': '--',         # minus sign
})

def normalize_authors(author_str):
    """Normalize author string to uniform 'Last, F.' format.

    Handles both semicolon-separated ('Last, First; Last, First') and
    comma-separated ('Last, F., Last, F.') author strings, including
    full first names, multi-initials, and ADS-style asterisks.
    """
    if not author_str:
        return author_str

    s = author_str.strip()

    # Remove ADS corresponding-author asterisks attached to last name ("Hugonnet*")
    s = re.sub(r'([A-Za-zÀ-ÖØ-öø-ÿ])\*(?=[,;])', r'\1', s)

    if ';' in s:
        # ── Semicolon-separated format ──────────────────────────────────────
        raw_tokens = re.split(r'\s*;\s*', s)
    else:
        # ── Comma-separated format ──────────────────────────────────────────
        # Fix ", and " / " and " separators
        s = re.sub(r',?\s+and\s+', ', ', s)
        # Fix missing comma: "Menounos B." → "Menounos, B."
        s = re.sub(r'([A-Za-zÀ-ÖØ-öø-ÿ]) ([A-Z]\.)', r'\1, \2', s)
        # Fix period instead of comma: "McDougall. S." → "McDougall, S."
        s = re.sub(r'([A-Za-zÀ-ÖØ-öø-ÿ])\. ([A-Z]\.)', r'\1, \2', s)
        # Fix missing separator between authors: "F. NextLast," → "F., NextLast,"
        s = re.sub(r'([A-Z]\.)\s+([A-Z][a-z])', r'\1, \2', s)
        # Strip trailing comma
        s = re.sub(r',\s*$', '', s.strip())
        # Split on ", " after a period (end of an initial) — safe for lowercase-starting names
        raw_tokens = re.split(r'(?<=\.),\s*', s)

    normalized = []
    for token in raw_tokens:
        token = token.strip().strip(',').strip()
        if not token:
            continue

        # Pull off leading student-marker asterisk
        prefix = ''
        if token.startswith('*'):
            prefix = '*'
            token = token[1:].strip()

        if ',' not in token:
            # Last name only (no first name available)
            normalized.append(prefix + token)
            continue

        comma_idx = token.index(',')
        last  = token[:comma_idx].strip()
        first = token[comma_idx + 1:].strip()

        # Abbreviate first name/initials to single first initial
        m = re.match(r'^([A-Z]\.)', first)
        if m:
            abbrev = m.group(1)          # already starts with initial
        elif first:
            abbrev = first[0].upper() + '.'   # full first name → initial
        else:
            abbrev = ''

        normalized.append(f'{prefix}{last}, {abbrev}' if abbrev else f'{prefix}{last}')

    return ', '.join(normalized)

def mark_student_authors(author_str, student_lastnames):
    """Prepend * to any author whose last name is in student_lastnames, if not already marked."""
    if not author_str:
        return author_str
    # Authors are "Last, F." separated by commas/and; last name is first word of each token
    def mark(token):
        t = token.strip().lstrip('*').strip()
        lastname = t.split(',')[0].strip()
        if lastname.lower() in student_lastnames:
            return '*' + t
        return token.strip()
    # Split on ' and ' first, then commas — rebuild carefully
    result = re.sub(r'\*?([A-Z][a-zA-Z\-\']+)(?=,)',
                    lambda m: ('*' if m.group(1).lower() in student_lastnames else '') + m.group(1),
                    author_str)
    return result

def esc(s):
    if not s:
        return ''
    # Translate only LaTeX special chars and common typographic chars;
    # all other Unicode passes through — xelatex handles it natively.
    return s.translate(_ESC)

MONTHS = ['Jan','Feb','Mar','Apr','May','Jun',
          'Jul','Aug','Sep','Oct','Nov','Dec']

def fmt_ym(ym):
    """Format any date-like string to 'Mon YYYY'. Handles YYYY/M, YYYY-MM-DD, YYYY-MM."""
    if not ym:
        return ''
    try:
        if '/' in ym:
            parts = ym.split('/')
            y, m = int(parts[0]), int(parts[1])
        elif '-' in ym:
            parts = ym.split('-')
            y, m = int(parts[0]), int(parts[1])
        else:
            return ym
        return f'{MONTHS[m-1]} {y}'
    except Exception:
        return ym

def fmt_date(d):
    """Format Date 'YYYY-MM-DD' → 'Mon YYYY'."""
    return fmt_ym(d)

def year_of(s):
    """Extract 4-digit year from a date string."""
    m = re.search(r'\b(19|20)\d\d\b', s or '')
    return int(m.group()) if m else 9999

# ── Parse the XML ─────────────────────────────────────────────────────────────

tree = ET.parse(XML_PATH)
root = tree.getroot()

# ── Personal Information ──────────────────────────────────────────────────────

pi_sec = find_section(root, 'Personal Information', 'Identification')
first_name  = field_val(pi_sec, 'First Name') if pi_sec else 'Brian'
family_name = field_val(pi_sec, 'Family Name') if pi_sec else 'Menounos'

# Contact details from Address/Telephone sections if present
address_sec = find_section(root, 'Personal Information', 'Address')
phone = field_val(address_sec, 'Telephone') if address_sec else ''
email = field_val(address_sec, 'Email') if address_sec else ''

# ── Education ─────────────────────────────────────────────────────────────────

degrees = []
ed_root = find_section(root, 'Education')
if ed_root:
    for deg in child_sections(ed_root, 'Degrees'):
        name   = field_val(deg, 'Degree Name')
        spec   = field_val(deg, 'Specialization')
        inst   = field_val(deg, 'Organization')
        start  = fmt_ym(field_val(deg, 'Degree Start Date'))
        end    = fmt_ym(field_val(deg, 'Degree Received Date'))
        thesis = field_val(deg, 'Thesis/Project Title')
        sup    = field_val(deg, 'Supervisor')
        if name:
            degrees.append({'name':name,'spec':spec,'inst':inst,
                            'start':start,'end':end,'thesis':thesis,'sup':sup})

# ── Employment ────────────────────────────────────────────────────────────────

positions = []
for emp_sec in find_all(root, 'Employment'):
    for pos in child_sections(emp_sec):
        title = field_val(pos, 'Position Title')
        org   = field_val(pos, 'Organization')
        dept  = field_val(pos, 'Department')
        start = fmt_ym(field_val(pos, 'Start Date'))
        end_  = fmt_ym(field_val(pos, 'End Date'))
        if title or org:
            positions.append({'title':title,'org':org,'dept':dept,
                              'start':start,'end':end_})

# ── Research Funding ──────────────────────────────────────────────────────────

grants = []
for g_sec in root:
    if local(g_sec.tag) != 'section' or g_sec.get('label') != 'Research Funding History':
        continue
    title  = field_val(g_sec, 'Funding Title')
    start  = fmt_ym(field_val(g_sec, 'Funding Start Date'))
    end_   = fmt_ym(field_val(g_sec, 'Funding End Date'))
    role   = field_val(g_sec, 'Funding Role')
    agency = amount = comp = prog = ''
    coinvs = []
    for ch in g_sec:
        if local(ch.tag) != 'section':
            continue
        if ch.get('label') == 'Funding Sources':
            agency = (field_val(ch, 'Funding Organization') or
                      field_val(ch, 'Other Funding Organization'))
            prog   = field_val(ch, 'Program Name')
            amount = field_val(ch, 'Total Funding')
            comp   = field_val(ch, 'Funding Competitive?')
        elif ch.get('label') == 'Other Investigators':
            name = field_val(ch, 'Investigator Name')
            inv_role = field_val(ch, 'Role')
            if name:
                coinvs.append((name, inv_role))
    if title or agency:
        yr = year_of(start or end_)
        grants.append({'title':title,'agency':agency,'prog':prog,'amount':amount,
                       'start':start,'end':end_,'role':role,'comp':comp,
                       'coinvs':coinvs,'yr':yr})
grants.sort(key=lambda g: -g['yr'])

# ── Supervisory Activities ────────────────────────────────────────────────────

supervisees = []
act_sec = find_section(root, 'Activities')
if act_sec:
    for ch in act_sec:
        if local(ch.tag) == 'section' and ch.get('label') == 'Supervisory Activities':
            for rec in child_sections(ch):
                name   = field_val(rec, 'Student Name')
                role   = field_val(rec, 'Supervision Role')
                deg    = field_val(rec, 'Degree Type or Postdoctoral Status')
                status = field_val(rec, 'Student Degree Status')
                inst   = field_val(rec, 'Student Institution')
                start  = fmt_ym(field_val(rec, 'Supervision Start Date') or field_val(rec, 'Student Degree Start Date'))
                end_   = fmt_ym(field_val(rec, 'Supervision End Date') or field_val(rec, 'Student Degree Received Date'))
                if name:
                    yr = year_of(start or end_)
                    supervisees.append({'name':name,'role':role,'deg':deg,
                                        'status':status,'inst':inst,
                                        'start':start,'end':end_,'yr':yr})
supervisees.sort(key=lambda s: -s['yr'])

# ── Service: Committee Memberships ────────────────────────────────────────────

committees = []
for sec in root.iter():
    if local(sec.tag) == 'section' and sec.get('label') == 'Committee Memberships' and sec.get('recordId'):
        role  = field_val(sec, 'Role')
        name  = field_val(sec, 'Committee Name')
        org   = field_val(sec, 'Organization') or field_val(sec, 'Other Organization')
        start = fmt_ym(field_val(sec, 'Membership Start Date'))
        end_  = fmt_ym(field_val(sec, 'Membership End Date'))
        if name:
            yr = year_of(end_ or start)
            committees.append({'role':role,'name':name,'org':org,
                               'start':start,'end':end_,'yr':yr})
committees.sort(key=lambda c: -c['yr'])

# ── Service: Organizational Review Activities ─────────────────────────────────

ora = []
for sec in root.iter():
    if local(sec.tag) == 'section' and sec.get('label') == 'Organizational Review Activities' and sec.get('recordId'):
        role  = field_val(sec, 'Role')
        org   = field_val(sec, 'Organization') or field_val(sec, 'Other Organization')
        start = fmt_ym(field_val(sec, 'Start Date'))
        end_  = fmt_ym(field_val(sec, 'End Date'))
        desc  = field_val(sec, 'Activity Description')
        if org or desc:
            yr = year_of(end_ or start)
            ora.append({'role':role,'org':org,'start':start,'end':end_,
                        'desc':desc,'yr':yr})
ora.sort(key=lambda o: -o['yr'])

# ── Service: Recognitions / Awards ───────────────────────────────────────────

recognitions = []
for sec in root.iter():
    if local(sec.tag) == 'section' and sec.get('label') == 'Recognitions' and sec.get('recordId'):
        rtype = field_val(sec, 'Recognition Type')
        rname = field_val(sec, 'Recognition Name')
        org   = field_val(sec, 'Organization') or field_val(sec, 'Other Organization')
        date  = fmt_ym(field_val(sec, 'Effective Date'))
        desc  = field_val(sec, 'Description')
        if rname:
            yr = year_of(date)
            recognitions.append({'type':rtype,'name':rname,'org':org,
                                 'date':date,'desc':desc,'yr':yr})
recognitions.sort(key=lambda r: -r['yr'])

# Build set of supervised student last names (exclude postdocs if desired — include all here)
student_lastnames = set()
for s in supervisees:
    lastname = s['name'].split(',')[0].strip().lower()
    if lastname and 'german rise' not in lastname:
        student_lastnames.add(lastname)

# ── Publications ──────────────────────────────────────────────────────────────

pubs = []
contrib_sec = None
for sec in root:
    if local(sec.tag) == 'section' and sec.get('label') == 'Contributions':
        contrib_sec = sec
        break

chapters = []   # book chapters
reports  = []   # technical reports

if contrib_sec is not None:
    for pub_container in contrib_sec:
        if local(pub_container.tag) != 'section' or pub_container.get('label') != 'Publications':
            continue
        for pub in pub_container:
            if local(pub.tag) != 'section':
                continue
            pub_type = pub.get('label', '')

            if pub_type == 'Journal Articles':
                authors = field_val(pub, 'Authors')
                title   = field_val(pub, 'Article Title') or field_val(pub, 'Title')
                journal = field_val(pub, 'Journal') or field_val(pub, 'Publisher')
                vol     = field_val(pub, 'Volume')
                pages   = field_val(pub, 'Page Range') or field_val(pub, 'Pages')
                year    = field_val(pub, 'Year') or field_val(pub, 'Publication Year')
                doi     = field_val(pub, 'DOI')
                status  = field_val(pub, 'Publishing Status') or field_val(pub, 'Publication Status')
                if title:
                    pubs.append({'authors':authors,'title':title,'journal':journal,
                                 'vol':vol,'pages':pages,'year':year,'doi':doi,
                                 'status':status})

            elif pub_type == 'Book Chapters':
                authors  = field_val(pub, 'Authors')
                title    = field_val(pub, 'Chapter Title')
                book     = field_val(pub, 'Book Title')
                pages    = field_val(pub, 'Page Range')
                year     = field_val(pub, 'Year')
                pub_name = field_val(pub, 'Publisher')
                refereed = field_val(pub, 'Refereed?')
                doi      = field_val(pub, 'DOI')
                status   = field_val(pub, 'Publishing Status')
                if title:
                    chapters.append({'authors':authors,'title':title,'book':book,
                                     'pages':pages,'year':year,'publisher':pub_name,
                                     'refereed':refereed,'doi':doi,'status':status})

            elif pub_type == 'Reports':
                authors = field_val(pub, 'Authors')
                title   = field_val(pub, 'Report Title')
                org     = (field_val(pub, 'Funding Organization') or
                           field_val(pub, 'Other Organization'))
                pages   = field_val(pub, 'Number of Pages')
                year    = field_val(pub, 'Year Submitted') or field_val(pub, 'Year')
                doi     = field_val(pub, 'DOI')
                if title:
                    reports.append({'authors':authors,'title':title,'org':org,
                                    'pages':pages,'year':year,'doi':doi})

pubs.sort(    key=lambda p: -(int(p['year'])      if p.get('year')      and p['year'].isdigit()      else 0))
chapters.sort(key=lambda c: -(int(c['year'])      if c.get('year')      and c['year'].isdigit()      else 0))
reports.sort( key=lambda r: -(int(r['year'])      if r.get('year')      and r['year'].isdigit()      else 0))

# ── Presentations ─────────────────────────────────────────────────────────────
# Structure: Contributions > Presentations (direct records, some may contain nested Presentations)
# Fields: Presentation Title, Conference / Event Name, City, Invited?, Keynote?, Presentation Year

invited_pres = []
other_pres   = []

def parse_pres_record(pres):
    title   = field_val(pres, 'Presentation Title')
    venue   = field_val(pres, 'Conference / Event Name')
    year    = field_val(pres, 'Presentation Year')
    city    = field_val(pres, 'City')
    invited = field_val(pres, 'Invited?')
    keynote = field_val(pres, 'Keynote?')
    copres  = field_val(pres, 'Co-Presenters')
    return title, venue, year, city, invited, keynote, copres

if contrib_sec is not None:
    for pres in contrib_sec:
        if local(pres.tag) != 'section' or pres.get('label') != 'Presentations':
            continue
        title, venue, year, city, invited, keynote, copres = parse_pres_record(pres)
        yr = int(year) if year and year.isdigit() else 9999
        rec = {'title':title,'venue':venue,'year':year,'city':city,
               'invited':invited,'keynote':keynote,'copres':copres,'yr':yr}
        if title or venue:
            if invited == 'Yes' or keynote == 'Yes':
                invited_pres.append(rec)
            else:
                other_pres.append(rec)
        # Also check for nested Presentations (ADS-imported abstracts inside first record)
        for sub in pres:
            if local(sub.tag) == 'section' and sub.get('label') == 'Presentations':
                t, v, y, c, inv, kn, cp = parse_pres_record(sub)
                yr2 = int(y) if y and y.isdigit() else 9999
                r2 = {'title':t,'venue':v,'year':y,'city':c,
                      'invited':inv,'keynote':kn,'copres':cp,'yr':yr2}
                if t or v:
                    if inv == 'Yes' or kn == 'Yes':
                        invited_pres.append(r2)
                    else:
                        other_pres.append(r2)

invited_pres.sort(key=lambda p: -p['yr'])
other_pres.sort(key=lambda p: -p['yr'])

# ── Media / Interviews ────────────────────────────────────────────────────────

media = []
if contrib_sec is not None:
    for im_sec in contrib_sec:
        if local(im_sec.tag) != 'section' or im_sec.get('label') != 'Interviews and Media Relations':
            continue
        for rec in im_sec:
            if local(rec.tag) != 'section':
                continue
            topic   = field_val(rec, 'Topic')
            network = field_val(rec, 'Network')
            program = field_val(rec, 'Program')
            date    = field_val(rec, 'First Broadcast Date')
            if topic or network:
                yr = year_of(date or '')
                media.append({'topic':topic,'network':network,
                              'program':program,'date':date,'yr':yr})
media.sort(key=lambda m: (-m['yr'], m['network'] or ''))

# ── Build LaTeX ───────────────────────────────────────────────────────────────

lines = []
A = lines.append

A(r"""\documentclass[11pt,letterpaper]{article}
\usepackage[top=0.75in,bottom=0.75in,left=0.75in,right=0.75in]{geometry}
\usepackage{fontspec}
\usepackage{hyperref}
\usepackage{enumitem}
\usepackage{longtable}
\usepackage{booktabs}
\usepackage{array}
\usepackage{parskip}
\usepackage{microtype}
\usepackage{titlesec}
\usepackage{xcolor}
\usepackage{fancyhdr}
\usepackage{lastpage}
\definecolor{seccolor}{RGB}{0,70,127}
\titleformat{\section}{\large\bfseries\color{seccolor}}{}{0em}{}[\titlerule]
\titleformat{\subsection}{\normalsize\bfseries}{}{0em}{}
\titlespacing{\section}{0pt}{14pt}{6pt}
\titlespacing{\subsection}{0pt}{8pt}{4pt}
\setlength{\parindent}{0pt}
\hypersetup{colorlinks=true,linkcolor=seccolor,urlcolor=seccolor}
\setlist[itemize]{leftmargin=1.5em,itemsep=2pt,topsep=4pt}
\pagestyle{fancy}
\fancyhf{}
\fancyhead[L]{\color{gray}\small """ + esc(family_name) + r""", Curriculum Vitae """ + datetime.date.today().strftime('%d-%m-%Y') + r"""}
\fancyfoot[C]{\thepage/\pageref{LastPage}}
\renewcommand{\headrulewidth}{0pt}
\fancypagestyle{plain}{%
  \fancyhf{}%
  \fancyfoot[C]{\thepage/\pageref{LastPage}}%
  \renewcommand{\headrulewidth}{0pt}%
}
\begin{document}
\thispagestyle{plain}
""")

# Header
A(r'{\centering')
A(r'{\LARGE\textbf{' + esc(f'{first_name} {family_name}') + r'}\\[4pt]}')
# Build subtitle from most recent position
_title_parts = []
if positions:
    p = positions[0]
    if p['title']: _title_parts.append(esc(p['title']))
    if p['dept']:  _title_parts.append(esc(p['dept']))
    if p['org']:   _title_parts.append(esc(p['org']))
_subtitle = r' $\cdot$ '.join(_title_parts) if _title_parts else ''
if _subtitle:
    A(r'{\large ' + _subtitle + r'\\[2pt]}')
_city = field_val(find_section(root, 'Personal Information', 'Address'), 'City') or     field_val(find_section(root, 'Personal Information', 'Address'), 'Municipality') or ''
_contact = []
if _city: _contact.append(esc(_city))
if email: _contact.append(r'\href{mailto:' + esc(email) + r'}{' + esc(email) + r'}')
if _contact:
    A(' $\\cdot$ '.join(_contact) + r'\\[2pt]')
_orcid = field_val(pi_sec, 'ORCID') if pi_sec else ''
if _orcid:
    A(r'\href{https://orcid.org/' + esc(_orcid) + r'}{ORCID: ' + esc(_orcid) + r'}\\[8pt]}')
else:
    A(r'\vspace{4pt}}')
A(r'\hrule')
A('')

# Education
if degrees:
    A(r'\section{Education}')
    A(r'\begin{longtable}{@{}p{0.72\textwidth}p{0.25\textwidth}@{}}')
    for d in degrees:
        name = esc(d['name'])
        spec = esc(d['spec'])
        inst = esc(d['inst'])
        period = esc(d['end'] or d['start'])
        line = f"\\textbf{{{name}}}"
        if spec:
            line += f", {spec}"
        if inst:
            line += f"\\\\\n{inst}"
        if d['thesis']:
            line += f"\\\\\n\\textit{{Thesis: }}{esc(d['thesis'])}"
        if d['sup']:
            line += f"\\\\\n\\textit{{Supervisor: }}{esc(d['sup'])}"
        A(f'{line} & {period} \\\\[6pt]')
    A(r'\end{longtable}')

# Employment
if positions:
    A(r'\section{Academic Appointments}')
    A(r'\begin{longtable}{@{}p{0.72\textwidth}p{0.25\textwidth}@{}}')
    for p in positions:
        title = esc(p['title'])
        org   = esc(p['org'])
        dept  = esc(p['dept'])
        start = esc(p['start'])
        end_  = esc(p['end']) or 'present'
        period = f"{start}--{end_}" if start else end_
        line = f"\\textbf{{{title}}}"
        if dept:
            line += f", {dept}"
        if org:
            line += f"\\\\\n{org}"
        A(f'{line} & {period} \\\\[6pt]')
    A(r'\end{longtable}')

def fmt_amount(raw):
    try:
        return r'\$' + '{:,}'.format(int(float(raw))) if raw else ''
    except Exception:
        return esc(raw)

def render_grants(glist, heading):
    if not glist:
        return
    A(f'\\section{{{heading}}}')
    A(r'{\small')
    A(r'\begin{longtable}{@{}p{0.56\textwidth}p{0.20\textwidth}p{0.16\textwidth}@{}}')
    A(r'\toprule')
    A(r'\textbf{Title / Agency} & \textbf{Period} & \textbf{Amount} \\')
    A(r'\midrule')
    A(r'\endhead')
    A(r'\endfoot')
    A(r'\bottomrule')
    A(r'\endlastfoot')
    for g in glist:
        agency = esc(g['agency'])
        prog   = esc(g['prog'])
        title  = esc(g['title'])
        start  = esc(g['start'])
        end_   = esc(g['end'])
        period = f"{start}\\newline {end_}" if start and end_ else (start or end_)
        amt    = fmt_amount(g['amount'])
        role   = esc(g['role'] or 'PI')
        pi_names  = [esc(n) for n, r in g['coinvs'] if 'Principal' in r]
        coi_names = [esc(n) for n, r in g['coinvs'] if 'Principal' not in r]
        coinv_str = ''
        if pi_names:
            coinv_str += 'PI: ' + ', '.join(pi_names)
        if coi_names:
            if coinv_str:
                coinv_str += '; '
            coinv_str += 'Co-I: ' + ', '.join(coi_names)

        left = f'\\textbf{{{title}}}'
        if agency:
            left += f'\\\\\n{agency}'
            if prog:
                left += f' ({prog})'
        if role:
            left += f'\\\\\n\\textit{{Role: {role}}}'
        if coinv_str:
            left += f'\\\\\n\\textit{{{coinv_str}}}'

        A(f'{left} & {period} & {amt} \\\\[4pt]')
    A(r'\end{longtable}}')  # close \small

comp_grants = [g for g in grants if g['comp'] in ('Yes', '')]
nc_grants   = [g for g in grants if g['comp'] == 'No']
render_grants(comp_grants, 'Research Grants (Competitive)')
render_grants(nc_grants,   'Research Contracts (Non-Competitive)')

# Supervision
if supervisees:
    A(r'\section{Student \& Postdoctoral Supervision}')

    # Group by degree type
    postdocs  = [s for s in supervisees if 'Post' in (s['deg'] or '')]
    res_assoc = [s for s in supervisees if 'Research' in (s['deg'] or '') and 'Post' not in (s['deg'] or '')]
    phd      = [s for s in supervisees if 'Doctor' in (s['deg'] or '') and 'Post' not in (s['deg'] or '')]
    msc      = [s for s in supervisees if "Master" in (s['deg'] or '')]
    bsc      = [s for s in supervisees if "Bachelor" in (s['deg'] or '')]

    def sup_table(slist, heading):
        if not slist:
            return
        A(f'\\subsection{{{heading}}}')
        A(r'{\small')
        A(r'\begin{longtable}{@{}p{0.32\textwidth}p{0.20\textwidth}p{0.24\textwidth}p{0.17\textwidth}@{}}')
        A(r'\toprule Name & Role & Institution & Period \\')
        A(r'\midrule')
        A(r'\endhead')
        A(r'\endfoot')
        A(r'\bottomrule')
        A(r'\endlastfoot')
        for s in slist:
            name   = esc(s['name'])
            role   = esc(s['role'] or '')
            inst   = esc(s['inst']).replace('University of Northern British Columbia', 'UNBC')
            start  = esc(s['start'])
            end_   = esc(s['end'])
            period = f"{start}--{end_}" if start and end_ else (start or end_)
            A(f'{name} & {role} & {inst} & {period} \\\\[1pt]')
        A(r'\end{longtable}}')

    sup_table(postdocs,  'Postdoctoral Fellows')
    sup_table(res_assoc, 'Research Associates')
    sup_table(phd,      'Doctoral Students')
    sup_table(msc,      "Master's Students")
    sup_table(bsc,      'Undergraduate Students')

# Publications
if pubs:
    A(r'\section{Refereed Journal Articles}')
    A(r'{\footnotesize $*$Supervised or co-supervised trainee}\\[4pt]')
    if SHOW_CREDIT and CREDIT_ROLES:
        A(r'{\footnotesize \textit{' + esc(_CREDIT_LEGEND) + r'}}\\[4pt]')
    A(r'{\small')
    A(r'\begin{enumerate}[leftmargin=2em,itemsep=3pt]')
    A(r'\setcounter{enumi}{' + str(len(pubs)) + r'}')
    A(r'\renewcommand{\theenumi}{\arabic{enumi}}')
    A(r'\setlength{\itemsep}{3pt}')
    for pub in pubs:
        authors = esc(mark_student_authors(normalize_authors(pub['authors']), student_lastnames))
        title   = esc(pub['title'])
        journal = esc(pub['journal'])
        vol     = esc(pub['vol'])
        pages   = esc(pub['pages'])
        year    = esc(pub['year'])
        status  = pub['status']
        doi     = pub['doi']
        line = ''
        if authors:
            line += f'{authors}, '
        if year:
            line += f'{year}. '
        line += f'\\textit{{{title}}}. '
        if journal:
            line += f'{journal}'
        if vol:
            line += f' {vol}'
        if pages:
            line += f', {pages}'
        if 'press' in (status or '').lower() or 'review' in (status or '').lower():
            line += f' ({esc(status)})'
        if doi:
            line += f'. \\href{{https://doi.org/{esc(doi)}}}{{doi:{esc(doi)}}}'
        if SHOW_CREDIT:
            roles = CREDIT_ROLES.get(_norm_title(pub['title']))
            if roles:
                line += r' \textnormal{\footnotesize [' + ', '.join(roles) + ']}'
        A(r'\item[\arabic{enumi}.]' + line)
        A(r'\addtocounter{enumi}{-1}')
    A(r'\end{enumerate}}')

# Book Chapters
def render_chapters(clist, heading):
    if not clist:
        return
    A(f'\\section{{{heading}}}')
    A(r'{\small\begin{enumerate}[leftmargin=2em,itemsep=3pt]')
    A(r'\setcounter{enumi}{' + str(len(clist)) + r'}')
    A(r'\renewcommand{\theenumi}{\arabic{enumi}}')
    for c in clist:
        authors = esc(mark_student_authors(normalize_authors(c['authors']), student_lastnames))
        title   = esc(c['title'])
        book    = esc(c['book'])
        pages   = esc(c['pages'])
        year    = esc(c['year'])
        pub_    = esc(c['publisher'])
        doi     = c['doi']
        status  = c['status']
        line = ''
        if authors:
            line += f'{authors}, '
        if year:
            line += f'{year}. '
        line += f'\\textit{{{title}}}. '
        if book:
            line += f'In \\textit{{{book}}}'
        if pages:
            line += f', pp.\\ {pages}'
        if pub_:
            line += f'. {pub_}'
        if 'press' in (status or '').lower() or 'review' in (status or '').lower():
            line += f' ({esc(status)})'
        if doi:
            line += f'. \\href{{https://doi.org/{esc(doi)}}}{{doi:{esc(doi)}}}'
        A(r'\item[\arabic{enumi}.]' + line)
        A(r'\addtocounter{enumi}{-1}')
    A(r'\end{enumerate}}')

peer_chapters = [c for c in chapters if c['refereed'] == 'Yes']
nonp_chapters = [c for c in chapters if c['refereed'] != 'Yes']
render_chapters(peer_chapters, 'Peer-Reviewed Book Chapters')
render_chapters(nonp_chapters, 'Book Chapters (Non-Refereed)')

# Technical Reports
if reports:
    A(r'\section{Technical Reports}')
    A(r'{\small\begin{enumerate}[leftmargin=2em,itemsep=3pt]')
    A(r'\setcounter{enumi}{' + str(len(reports)) + r'}')
    A(r'\renewcommand{\theenumi}{\arabic{enumi}}')
    for r_ in reports:
        authors = esc(mark_student_authors(normalize_authors(r_['authors']), student_lastnames))
        title   = esc(r_['title'])
        org     = esc(r_['org'])
        pages   = esc(r_['pages'])
        year    = esc(r_['year'])
        doi     = r_['doi']
        line = ''
        if authors:
            line += f'{authors}, '
        if year:
            line += f'{year}. '
        line += f'\\textit{{{title}}}.'
        if org:
            line += f' {org}'
        if pages:
            line += f', {pages} pp.'
        if doi:
            line += f'. \\href{{https://doi.org/{esc(doi)}}}{{doi:{esc(doi)}}}'
        A(r'\item[\arabic{enumi}.]' + line)
        A(r'\addtocounter{enumi}{-1}')
    A(r'\end{enumerate}}')

# Invited presentations
if invited_pres:
    A(r'\section{Invited Presentations \& Keynote Addresses}')
    A(r'{\small\begin{enumerate}[leftmargin=2em,itemsep=3pt]')
    A(r'\setcounter{enumi}{' + str(len(invited_pres)) + r'}')
    for p in invited_pres:
        title  = esc(p['title'])
        venue  = esc(p['venue'])
        year   = esc(p['year'])
        city   = esc(p['city'])
        copres = esc(normalize_authors(p['copres']))
        line   = f'\\textit{{{title}}}' if title else ''
        if venue:
            line += ('. ' if line else '') + venue
        if city:
            line += f', {city}'
        if year:
            line += f'. {year}'
        if copres:
            line += f'. \\textit{{With: {copres}}}'
        A(r'\item[\arabic{enumi}.]' + line)
        A(r'\addtocounter{enumi}{-1}')
    A(r'\end{enumerate}}')

# Other presentations
if other_pres:
    A(r'\section{Conference Presentations}')
    A(r'{\small\begin{enumerate}[leftmargin=2em,itemsep=3pt]')
    A(r'\setcounter{enumi}{' + str(len(other_pres)) + r'}')
    for p in other_pres:
        title  = esc(p['title'])
        venue  = esc(p['venue'])
        year   = esc(p['year'])
        city   = esc(p['city'])
        copres = esc(normalize_authors(p['copres']))
        line   = f'\\textit{{{title}}}' if title else ''
        if venue:
            line += ('. ' if line else '') + venue
        if city:
            line += f', {city}'
        if year:
            line += f'. {year}'
        if copres:
            line += f'. \\textit{{With: {copres}}}'
        A(r'\item[\arabic{enumi}.]' + line)
        A(r'\addtocounter{enumi}{-1}')
    A(r'\end{enumerate}}')

# Media
if media:
    A(r'\section{Media Interviews \& Outreach}')
    A(r'{\small\begin{itemize}[leftmargin=1.5em,itemsep=1pt]')
    for m in media:
        date_str = esc(fmt_date(m['date']) if '-' in (m['date'] or '') else m['date'])
        network  = esc(m['network'])
        program  = esc(m['program'])
        topic    = esc(m['topic'])
        line = ''
        if date_str:
            line += f'{date_str}: '
        if network:
            line += f'\\textit{{{network}}}'
        if program and program != network:
            line += f', {program}'
        if topic:
            line += f' --- {topic}'
        if line:
            A(r'\item ' + line)
    A(r'\end{itemize}}')

# Recognitions / Awards
if recognitions:
    A(r'\section{Awards \& Honours}')
    A(r'{\small')
    A(r'\begin{longtable}{@{}p{0.72\textwidth}p{0.20\textwidth}@{}}')
    A(r'\toprule \textbf{Award} & \textbf{Date} \\ \midrule \endhead \endfoot \bottomrule \endlastfoot')
    for r in recognitions:
        left = f'\\textbf{{{esc(r["name"])}}}'
        if r['org']:
            left += f'\\\\\n{esc(r["org"])}'
        if r['desc']:
            left += f'\\\\\n\\textit{{{esc(r["desc"])}}}'
        A(f'{left} & {esc(r["date"])} \\\\[4pt]')
    A(r'\end{longtable}}')

# Committee Memberships
if committees:
    A(r'\section{Committee Memberships \& Professional Affiliations}')
    A(r'{\small')
    A(r'\begin{longtable}{@{}p{0.55\textwidth}p{0.22\textwidth}p{0.15\textwidth}@{}}')
    A(r'\toprule \textbf{Committee / Organization} & \textbf{Role} & \textbf{Period} \\ \midrule \endhead \endfoot \bottomrule \endlastfoot')
    for c in committees:
        name = esc(c['name'])
        if c['org']:
            name += f'\\\\\n\\textit{{{esc(c["org"])}}}'
        role = esc(c['role'])
        period = f"{esc(c['start'])}\\newline {esc(c['end'])}" if c['start'] and c['end'] else esc(c['start'] or c['end'])
        A(f'{name} & {role} & {period} \\\\[3pt]')
    A(r'\end{longtable}}')

# Organizational Review Activities
if ora:
    A(r'\section{Review Activities}')
    A(r'{\small')
    A(r'\begin{longtable}{@{}p{0.72\textwidth}p{0.20\textwidth}@{}}')
    A(r'\toprule \textbf{Activity} & \textbf{Period} \\ \midrule \endhead \endfoot \bottomrule \endlastfoot')
    for o in ora:
        left = esc(o['desc']) if o['desc'] else esc(o['org'])
        if o['desc'] and o['org'] and o['org'] not in o['desc']:
            left = f'{esc(o["org"])}: {esc(o["desc"])}'
        period = f"{esc(o['start'])}\\newline {esc(o['end'])}" if o['start'] and o['end'] else esc(o['start'] or o['end'])
        A(f'{left} & {period} \\\\[3pt]')
    A(r'\end{longtable}}')

A(r'\end{document}')

# ── Write and compile ─────────────────────────────────────────────────────────

tex = '\n'.join(lines)
with open(TEX_PATH, 'w', encoding='utf-8') as f:
    f.write(tex)
print(f'Wrote {TEX_PATH}  ({len(tex):,} chars)')

# Compile twice for longtable page breaks
outdir = os.path.dirname(TEX_PATH)
for run in range(2):
    result = subprocess.run(
        ['xelatex', '-interaction=nonstopmode', '-output-directory', outdir, TEX_PATH],
        capture_output=True, text=True, cwd=outdir
    )
    if result.returncode != 0:
        print('pdflatex FAILED on run', run+1)
        # Show last 40 lines of log
        log_path = TEX_PATH.replace('.tex', '.log')
        if os.path.exists(log_path):
            with open(log_path) as lf:
                log_lines = lf.readlines()
            errors = [l for l in log_lines if l.startswith('!') or 'Error' in l]
            for e in errors[:20]:
                print(e.rstrip())
        sys.exit(1)

print(f'PDF written to {PDF_PATH}')
print(f'  Publications : {len(pubs)}')
print(f'  Invited pres : {len(invited_pres)}')
print(f'  Other pres   : {len(other_pres)}')
print(f'  Grants       : {len(grants)}')
print(f'  Supervisees  : {len(supervisees)}')
print(f'  Media        : {len(media)}')

if SHOW_CREDIT and CREDIT_ROLES:
    lines = [
        'NSERC Discovery Grant — Most Significant Contributions',
        '=' * 60,
        '',
        _CREDIT_LEGEND,
        '',
        'Publications (B. Menounos contributions in [brackets]):',
        '-' * 60,
        '',
    ]
    for i, pub in enumerate(pubs, 1):
        authors = normalize_authors(pub['authors'])
        yr = pub['year']; title = pub['title']
        jrn = pub['journal']; vol = pub['vol']; pgs = pub['pages']
        doi = pub['doi']; status = pub['status']
        entry = f'{i:3}. {authors}, {yr}. {title}. {jrn}'
        if vol: entry += f' {vol}'
        if pgs: entry += f', {pgs}'
        if 'press' in (status or '').lower() or 'review' in (status or '').lower():
            entry += f' ({status})'
        if doi: entry += f'. doi:{doi}'
        roles = CREDIT_ROLES.get(_norm_title(pub['title']))
        if roles:
            entry += f' [{", ".join(roles)}]'
        lines.append(entry)
    with open(NSERC_PATH, 'w', encoding='utf-8') as _nf:
        _nf.write('\n'.join(lines) + '\n')
    print(f'NSERC contributions: {NSERC_PATH}')
