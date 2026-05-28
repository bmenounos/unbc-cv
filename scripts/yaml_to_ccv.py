#!/usr/bin/env python3
"""Add YAML sections to CCV.xml (run after bib_to_ccv.py).

Usage: yaml_to_ccv.py <data_dir>
Reads:  <data_dir>/CCV.xml  (modified in place)
Sources: personal.yaml, students.yaml, grants.yaml,
         service.yaml, awards.yaml, courses.yaml
"""
import sys, os, uuid, re, io
import yaml
import xml.etree.ElementTree as ET

NS = 'http://www.cihr-irsc.gc.ca/generic-cv/1.0.0'
ET.register_namespace('generic-cv', NS)

# ── Helpers ───────────────────────────────────────────────────────────────────

def new_id(): return uuid.uuid4().hex
def local(tag): return tag.split('}')[-1] if '}' in tag else tag

def name_key(s):
    """Frozenset of lowercase tokens — matches 'Last, First' and 'First Last'."""
    return frozenset(re.split(r'[\s,]+', s.lower())) - {''}

def mksec(parent, label, record_id=None):
    el = ET.SubElement(parent, 'section', label=label)
    if record_id: el.set('recordId', record_id)
    return el

def mkfield(parent, label, value=None, lov=None):
    f = ET.SubElement(parent, 'field', label=label)
    if value is not None:
        v = ET.SubElement(f, 'value'); v.text = str(value)
    elif lov is not None:
        v = ET.SubElement(f, 'lov'); v.text = str(lov)
    return f

def find_or_create(parent, label):
    for el in parent:
        if local(el.tag) == 'section' and el.get('label') == label:
            return el
    return mksec(parent, label)

def fmt(d):
    """YYYY, YYYY-MM, or YYYY-MM-DD → 'YYYY/M' for CCV."""
    if not d: return ''
    s = str(d)
    m = re.match(r'^(\d{4})-(\d{2})', s)
    if m: return f'{m.group(1)}/{int(m.group(2))}'
    if re.match(r'^\d{4}$', s): return s + '/1'
    return s

def load(path):
    with open(path, encoding='utf-8') as f:
        return yaml.safe_load(f) or {}

def has_records(parent, label):
    for el in parent.iter():
        if local(el.tag) == 'section' and el.get('label') == label and el.get('recordId'):
            return True
    return False

# ── Load XML ──────────────────────────────────────────────────────────────────

if len(sys.argv) < 2:
    sys.exit('Usage: yaml_to_ccv.py <data_dir>')

data_dir = sys.argv[1]
xml_path = os.path.join(data_dir, 'CCV.xml')

tree = ET.parse(xml_path)
root = tree.getroot()

# ── personal.yaml → Personal Information, Education, Employment ───────────────

p = load(os.path.join(data_dir, 'personal.yaml'))

pi_cont = find_or_create(root, 'Personal Information')
id_sec  = find_or_create(pi_cont, 'Identification')
n = p.get('name', {})
mkfield(id_sec, 'First Name',   value=n.get('first', ''))
mkfield(id_sec, 'Family Name',  value=n.get('surname', ''))
if n.get('middle'):
    mkfield(id_sec, 'Middle Name', value=n.get('middle', ''))
if p.get('orcid'):
    mkfield(id_sec, 'ORCID', value=p['orcid'])

addr_sec = find_or_create(pi_cont, 'Address')
_city = p.get('city', 'Prince George, BC, Canada')
mkfield(addr_sec, 'City', value=_city)

ed_cont = find_or_create(root, 'Education')
for deg in (p.get('education') or []):
    sec = mksec(ed_cont, 'Degrees', new_id())
    mkfield(sec, 'Degree Name',         value=deg.get('degree', ''))
    mkfield(sec, 'Specialization',      value=deg.get('subject', ''))
    mkfield(sec, 'Organization',        value=deg.get('institution', ''))
    mkfield(sec, 'Degree Start Date',   value=fmt(deg.get('start')))
    mkfield(sec, 'Degree Received Date',value=fmt(deg.get('end')))
    if deg.get('thesis'):
        mkfield(sec, 'Thesis/Project Title', value=deg['thesis'])
    if deg.get('supervisor'):
        mkfield(sec, 'Supervisor', value=deg['supervisor'])

emp_cont = find_or_create(root, 'Employment')
unbc = p.get('employment_unbc') or []
dept = p.get('department', 'Geography, Earth and Environmental Science')
for pos in unbc:
    sec = mksec(emp_cont, 'Academic Work Experience', new_id())
    mkfield(sec, 'Position Title',  value=pos.get('title', ''))
    mkfield(sec, 'Organization',    value='University of Northern British Columbia')
    mkfield(sec, 'Department',      value=dept)
    mkfield(sec, 'Start Date',      value=fmt(pos.get('start')))
    mkfield(sec, 'End Date',        value=fmt(pos.get('end')) if pos.get('end') else '')

for pos in (p.get('employment_prior') or []):
    sec = mksec(emp_cont, 'Academic Work Experience', new_id())
    mkfield(sec, 'Position Title',  value=pos.get('title', ''))
    mkfield(sec, 'Organization',    value=pos.get('institution', ''))
    mkfield(sec, 'Start Date',      value=fmt(pos.get('start')))
    mkfield(sec, 'End Date',        value=fmt(pos.get('end')))

# ── students.yaml → Activities > Supervisory Activities ──────────────────────

s_data  = load(os.path.join(data_dir, 'students.yaml'))
act_sec = find_or_create(root, 'Activities')
sup_sec = find_or_create(act_sec, 'Supervisory Activities')
# Build set of already-stored trainee name keys for dedup (handles 'Last, First' vs 'First Last')
_existing_trainee_keys = set()
for _el in root.iter():
    if local(_el.tag) == 'section' and _el.get('label') == 'Student/Postdoctoral Supervision' and _el.get('recordId'):
        for _f in _el.iter():
            if local(_f.tag) == 'field' and _f.get('label') == 'Student Name':
                for _v in _f:
                    if _v.text: _existing_trainee_keys.add(name_key(_v.text.strip()))

def add_supervision(sec, name, deg_type, role, inst, start, end_, status=''):
    if name_key(name) in _existing_trainee_keys:
        return
    r = mksec(sec, 'Student/Postdoctoral Supervision', new_id())
    mkfield(r, 'Student Name', value=name)
    mkfield(r, 'Supervision Role', value=role)
    mkfield(r, 'Degree Type or Postdoctoral Status', value=deg_type)
    mkfield(r, 'Student Institution', value=inst or 'University of Northern British Columbia')
    mkfield(r, 'Supervision Start Date', value=fmt(start))
    mkfield(r, 'Supervision End Date',   value=fmt(end_) if end_ and end_ not in ('withdrew', 'medical withdraw') else '')
    if status:
        mkfield(r, 'Student Degree Status', value=status)

me = 'Menounos'
for g in (s_data.get('graduate') or []):
    sups = g.get('supervisors', [])
    if me in sups:
        role = 'Principal Supervisor' if sups[0] == me else 'Co-Supervisor'
    else:
        continue  # Menounos not supervisor — skip (handled in supervisory_committee)
    prog = g.get('program', 'MSc')
    if 'PhD' in prog or 'Doctor' in prog:
        deg = 'Doctoral'
    elif 'MA' in prog or 'Thesis' in prog:
        deg = "Master's"
    else:
        deg = "Master's"
    fin = g.get('finish')
    status = 'Completed' if fin and fin not in ('withdrew', 'medical withdraw', None) else \
             ('Withdrew' if fin in ('withdrew', 'medical withdraw') else 'In Progress')
    inst = g.get('university', '') or ''
    add_supervision(sup_sec, g['name'], deg, role, inst, g.get('start'), fin, status)

for pf in (s_data.get('postdoctoral_fellows') or []):
    add_supervision(sup_sec, pf['name'], 'Postdoctoral', 'Principal Supervisor',
                    'University of Northern British Columbia',
                    pf.get('start'), pf.get('finish'),
                    'Completed' if pf.get('finish') else 'In Progress')

for ra in (s_data.get('research_associates') or []):
    add_supervision(sup_sec, ra['name'], 'Research Associate', 'Principal Supervisor',
                    'University of Northern British Columbia',
                    ra.get('start'), ra.get('finish'),
                    'Completed' if ra.get('finish') else 'In Progress')

for sc in (s_data.get('supervisory_committee') or []):
    prog = sc.get('program', 'MSc')
    deg = 'Doctoral' if 'PhD' in prog else "Master's"
    add_supervision(sup_sec, sc['name'], deg, 'Committee Member',
                    'University of Northern British Columbia',
                    sc.get('start'), sc.get('finish'))

# ── grants.yaml → Research Funding History ────────────────────────────────────

g_data = load(os.path.join(data_dir, 'grants.yaml'))
_skip_grants = has_records(root, 'Research Funding History')

def add_grant(entry, competitive):
    pi_str = str(entry.get('pi', ''))
    is_pi  = 'Menounos' in pi_str or me in pi_str
    role   = 'Principal Investigator' if is_pi else 'Co-Investigator'

    sec = mksec(root, 'Research Funding History', new_id())
    mkfield(sec, 'Funding Title',       value=entry.get('subject', ''))
    mkfield(sec, 'Funding Start Date',  value=fmt(entry.get('start')))
    mkfield(sec, 'Funding End Date',    value=fmt(entry.get('end')))
    mkfield(sec, 'Funding Role',        value=role)

    src = mksec(sec, 'Funding Sources', new_id())
    mkfield(src, 'Funding Organization', value=entry.get('agency', ''))
    mkfield(src, 'Total Funding',        value=str(entry.get('amount_per_year', '')))
    mkfield(src, 'Funding Competitive?', lov='Yes' if competitive else 'No')

    for co in (entry.get('co_investigators') or []):
        if not co or co == me or 'Menounos' in str(co):
            continue
        inv = mksec(sec, 'Other Investigators', new_id())
        mkfield(inv, 'Investigator Name', value=str(co))
        mkfield(inv, 'Role', value='Co-Investigator')
    if not is_pi:
        inv = mksec(sec, 'Other Investigators', new_id())
        mkfield(inv, 'Investigator Name', value=pi_str)
        mkfield(inv, 'Role', value='Principal Investigator')

if not _skip_grants:
    for entry in (g_data.get('competitive') or []):
        add_grant(entry, True)
    for entry in (g_data.get('contracts') or []):
        add_grant(entry, False)

# ── service.yaml → Committee Memberships, Editorial Activities, ORA ───────────
# Field and section IDs must match the CCV portal schema exactly.
# Source: port_my_ccv/add_service_and_awards.py + CCV-71051.xml inspection.

_SEC = {
    'Committee Memberships':            '6c3b449732a84ac9af45d6935b8323d9',
    'Organizational Review Activities': 'd936ced236a14d59a24fad5f41befd94',
    'Editorial Activities':             '95433781426f45749b05ff6bc0062dd9',
}
_CM = {
    'role':      'da89e8800c6641be91b0b21a61118c09',
    'name':      'b3c21a20aeee49cea5c1c33029da4c4c',
    'org':       'e1f84da9b6df40fe9db972af2f85e5eb',
    'org_type':  '2ef5054449c44bbeba1cd30cd9a63549',
    'other_org': '99aa9de868c442f281a0ba67a3d3116d',
    'start':     '4c1a9700923d4bf9b541e479f4f32a66',
    'end':       '1db804cbb6f04c64b57e60c306557d91',
    'desc':      'acf1a91ab6cd43bfbdc3ee3df5cb7af7',
}
_ORA = {
    'role':      'c030139006a74969a4d191711ba0557b',
    'org':       '2bd6e279a13944f5b63938fc8169768c',
    'org_type':  '731da824622d460ab1490435169f2a04',
    'other_org': '025f3819c6af4ac19eb5a64eb64e1f3e',
    'start':     '2786302e3cfc47ee8bd9248acb9754a6',
    'end':       '70e06bb0787f468aa41d36991f663984',
    'desc':      'fddf414852db46dbbb1a9f93674216c1',
}
_ED = {
    'role':      'bca52391a28840879ef185c41ae728e3',
    'pub_type':  '024515508fd2498f99516cb71a109da1',
    'pub_name':  '42711a8af574435f82b02c5f455d96fb',
    'start':     'cbe5defb3e804adbb0e7cdc581b55fd0',
    'end':       'c4c319cffb764895bb4b98c360275978',
    'desc':      'a95eb3c02b964746ab3c30ad0bd60a27',
}
_CM_ROLE_LOV = {
    'Committee Member': '00000000000000000000000100002301',
    'Member':           '00000000000000000000000100002303',
    'Chair':            '00000000000000000000000100002300',
    'Group Chair':      '00000000000000000000000100002302',
}
_ED_PUBTYPE_LOV = {
    'Journal': '00000000000000000000000100001602',
}
_ORA_NOT_FOR_PROFIT = ('00000000000000000000000000000133', 'Not for Profit')

def _fv(fid, label, text, typ='String', fmt_=None):
    el = ET.Element('field', {'id': fid, 'label': label})
    attrs = {'type': typ}
    if fmt_: attrs['format'] = fmt_
    v = ET.SubElement(el, 'value', attrs)
    if text: v.text = str(text)
    return el

def _flov(fid, label, lov_id, lov_text):
    el = ET.Element('field', {'id': fid, 'label': label})
    v = ET.SubElement(el, 'lov', {'id': lov_id})
    v.text = lov_text
    return el

def _fempty(fid, label):
    return ET.Element('field', {'id': fid, 'label': label})

def _fbil(fid, label, text=''):
    el = ET.Element('field', {'id': fid, 'label': label})
    v = ET.SubElement(el, 'value', {'type': 'Bilingual'})
    if text: v.text = text
    bil = ET.SubElement(el, 'bilingual')
    ET.SubElement(bil, 'french')
    eng = ET.SubElement(bil, 'english')
    if text: eng.text = text
    return el

svc = load(os.path.join(data_dir, 'service.yaml'))

_skip_svc       = has_records(root, 'Committee Memberships')
_skip_editorial = has_records(root, 'Editorial Activities')
_skip_ora       = has_records(root, 'Organizational Review Activities')

mb_cont    = find_or_create(root, 'Memberships')
admin_cont = find_or_create(act_sec, 'Administrative Activities')
ara_cont   = find_or_create(act_sec, 'Assessment and Review Activities')

def add_cm(name, other_org, start, end_, role='Committee Member'):
    lov_id = _CM_ROLE_LOV.get(role, _CM_ROLE_LOV['Committee Member'])
    sec = ET.SubElement(mb_cont, 'section',
                        id=_SEC['Committee Memberships'],
                        label='Committee Memberships', recordId=new_id())
    sec.append(_flov(_CM['role'], 'Role', lov_id, role))
    sec.append(_fv(_CM['name'], 'Committee Name', name))
    sec.append(_fempty(_CM['org'], 'Organization'))
    sec.append(_fempty(_CM['org_type'], 'Other Organization Type'))
    sec.append(_fv(_CM['other_org'], 'Other Organization', other_org or ''))
    sec.append(_fv(_CM['start'], 'Membership Start Date', fmt(start), 'YearMonth', 'yyyy/MM'))
    sec.append(_fbil(_CM['desc'], 'Description'))
    sec.append(_fv(_CM['end'], 'Membership End Date', fmt(end_) if end_ else '', 'YearMonth', 'yyyy/MM'))

def add_editorial(journal, role, pub_type, start, end_):
    lov_id = _ED_PUBTYPE_LOV.get(pub_type, _ED_PUBTYPE_LOV['Journal'])
    sec = ET.SubElement(admin_cont, 'section',
                        id=_SEC['Editorial Activities'],
                        label='Editorial Activities', recordId=new_id())
    sec.append(_fv(_ED['role'], 'Role', role))
    sec.append(_flov(_ED['pub_type'], 'Publication Type', lov_id, pub_type))
    sec.append(_fv(_ED['pub_name'], 'Publication Name', journal))
    sec.append(_fv(_ED['start'], 'Start Date', fmt(start), 'YearMonth', 'yyyy/MM'))
    sec.append(_fv(_ED['end'], 'End Date', fmt(end_) if end_ else '', 'YearMonth', 'yyyy/MM'))
    sec.append(_fbil(_ED['desc'], 'Activity Description'))

def add_ora(other_org, role, start, end_, desc=''):
    sec = ET.SubElement(ara_cont, 'section',
                        id=_SEC['Organizational Review Activities'],
                        label='Organizational Review Activities', recordId=new_id())
    sec.append(_fv(_ORA['role'], 'Role', role))
    sec.append(_fempty(_ORA['org'], 'Organization'))
    sec.append(_flov(_ORA['org_type'], 'Other Organization Type',
                     _ORA_NOT_FOR_PROFIT[0], _ORA_NOT_FOR_PROFIT[1]))
    sec.append(_fv(_ORA['other_org'], 'Other Organization', other_org))
    sec.append(_fv(_ORA['start'], 'Start Date', fmt(start), 'YearMonth', 'yyyy/MM'))
    sec.append(_fv(_ORA['end'], 'End Date', fmt(end_) if end_ else '', 'YearMonth', 'yyyy/MM'))
    sec.append(_fbil(_ORA['desc'], 'Activity Description', desc))

if not _skip_svc:
    for c in (svc.get('university_committees') or []):
        add_cm(c['name'], 'University of Northern British Columbia',
               c.get('start'), c.get('end'))
    for c in (svc.get('scholarly_societies') or []):
        add_cm(c['name'], '', c.get('start'), c.get('end'))
    for c in (svc.get('scholarly_committees') or []):
        add_cm(c['name'], '', c.get('start'), c.get('end'))
    for c in (svc.get('other_committees') or []):
        add_cm(c['name'], '', c.get('start'), c.get('end'))

if not _skip_editorial:
    for e in (svc.get('editorships') or []):
        add_editorial(e.get('journal', ''), e.get('role', 'Editor'),
                      e.get('type', 'Journal'), e.get('start'), e.get('end'))

if not _skip_ora:
    for jr in (svc.get('journal_reviews') or []):
        years = jr.get('years', [])
        if years:
            add_ora(jr['journal'], 'Peer Reviewer',
                    str(min(years)), str(max(years)),
                    f'Peer reviewer for {jr["journal"]}')
    for gr in (svc.get('grant_reviews') or []):
        years = gr.get('years', [])
        if years:
            add_ora(gr['agency'], 'Peer Reviewer', str(min(years)), str(max(years)),
                    gr.get('note', f'Grant review for {gr["agency"]}'))
    for ex in (svc.get('external_examining') or []):
        yr = ex.get('year') or (ex.get('years', [None])[-1])
        add_ora(ex['institution'], ex.get('type', 'External Examiner'),
                str(yr), str(yr),
                f'{ex.get("type","External examiner")}, {ex["institution"]}')

# ── Fill missing Presentation Locations → Canada ──────────────────────────────
_LOC_CANADA_ID  = '00000000000000000000000000002124'
_LOC_FIELD_ID   = 'f4b5f1a1d181404ca9c0fea81f9a7e79'
for _s in root.iter():
    if local(_s.tag) == 'section' and _s.get('label') == 'Presentations' and _s.get('recordId'):
        _loc_field = next((f for f in _s if local(f.tag) == 'field' and f.get('label') == 'Location'), None)
        _has_content = _loc_field is not None and any(c.text and c.text.strip() for c in _loc_field)
        if not _has_content:
            if _loc_field is None:
                _loc_field = ET.SubElement(_s, 'field', {'id': _LOC_FIELD_ID, 'label': 'Location'})
            else:
                for _c in list(_loc_field):
                    _loc_field.remove(_c)
            ET.SubElement(_loc_field, 'lov', {'id': _LOC_CANADA_ID}).text = 'Canada'

# ── awards.yaml → Recognitions ────────────────────────────────────────────────

aw = load(os.path.join(data_dir, 'awards.yaml'))
_skip_aw = has_records(root, 'Recognitions')

def add_rec(item, rtype):
    yr   = item.get('year') or item.get('end') or item.get('start', '')
    mon  = item.get('month', 1)
    date = f'{yr}/{mon}' if yr else ''
    r = mksec(root, 'Recognitions', new_id())
    mkfield(r, 'Recognition Type', lov=rtype)
    mkfield(r, 'Recognition Name', value=item.get('name', ''))
    mkfield(r, 'Organization',     value=item.get('organization', ''))
    mkfield(r, 'Effective Date',   value=date)
    if item.get('note'):
        mkfield(r, 'Description', value=item['note'])

if not _skip_aw:
 for item in (aw.get('scholarship') or []):
    add_rec(item, 'Research / Scholarly')
for item in (aw.get('teaching') or []):
    add_rec(item, 'Teaching')
for item in (aw.get('service') or []):
    add_rec(item, 'Service')

# ── Write XML back ────────────────────────────────────────────────────────────

ET.indent(tree, space='  ')
buf = io.BytesIO()
tree.write(buf, encoding='utf-8', xml_declaration=False)
content = buf.getvalue().decode('utf-8')
content = re.sub(r'</generic-cv:(?!generic-cv\b)(\w+)>', r'</\1>', content)
content = re.sub(r'<generic-cv:(?!generic-cv\b)', '<', content)

with open(xml_path, 'w', encoding='utf-8') as f:
    f.write('<?xml version="1.0" encoding="UTF-8"?>\n')
    f.write(content)
    f.write('\n')

print(f'Updated: {xml_path}')
