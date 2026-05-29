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

# ── Field element helpers (used by grants, service, awards) ───────────────────

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

# ── grants.yaml → Research Funding History ────────────────────────────────────

g_data = load(os.path.join(data_dir, 'grants.yaml'))

_GF = {
    'sec':    'aaedc5454412483d9131f7619d10279e',
    'type':   '931b92a5ffed4e5aa9c7b3a0afd5f8ba',
    'start':  '9c1db4674334436ca891b7b8a9e114bd',
    'end':    'b63179ab0f0e4c9eaa7e9a8130d60ee3',
    'title':  '735545eb499e4cc6a949b4b375a804e8',
    'gtype':  'c8e3451d1e3a405bb1e8aa0ebeb66c8d',
    'desc':   '0674312de78f4647aba3bf202a41d58e',
    'clin':   'f7bfa6e647fd48cf8d404263df5843b1',
    'status': '0991ead151e3445ca7537aa15acbec57',
    'role':   '7496de092dc84038a1881e8f9d77e713',
    'uptake': '32ce1c0c194447c19c6847b1915d35f1',
}
_GFS = {
    'sec':      '376b8991609f46059a3d66028f005360',
    'org':      '67e083b070954e91bcbb1cc70131145a',
    'other_org':'1bdead14642545f3971a59997d82da67',
    'program':  '97231512141a452a82151cc162e9a59c',
    'ref':      '3fb9015d879f435d937ae9aa7ccd2973',
    'total':    'dfe6a0b34347486aaa677f07306a141e',
    'currency': '4775aa8f2a3f4f5083dd1c816462f260',
    'received': '882a94c7548744ca992e2647346d2e14',
    'recv_cur': 'b8ea355ed5ad4970bf1367fe0281b724',
    'renew':    'a445f692a0d54760bcf2ed9c8a829eff',
    'comp':     '00efdc7e790a48ac8675696c66afc3ad',
    'src_s':    'd62313c1cdb9419caf79014f07e1cfe0',
    'src_e':    'efc68e7d74f849eebb59f9a3bb85e5db',
}
_GFI = {
    'sec':  'c7c473d1237b432fb7f2abd831130fb7',
    'name': 'ddd551dfb26344fbb17f07afcffc94ed',
    'role': '13806a6772d248158619261afaab2fe0',
}
_GF_TYPE_LOV = {
    'Grant':          '00000000000000000000000100000900',
    'Contract':       '00000000000000000000000100000904',
    'Research Chair': '00000000000000000000000100000901',
}
_GF_ROLE_LOV = {
    'Principal Investigator': '00000000000000000000000100002800',
    'Co-investigator':        '00000000000000000000000100002801',
    'Co-applicant':           '00000000000000000000000100002802',
    'Principal Applicant':    '00000000000000000000000100002807',
}
_GF_COMP_LOV  = {'Yes': '00000000000000000000000000000400', 'No': '00000000000000000000000000000401'}
_GF_STAT_LOV  = {'Awarded': '00000000000000000000000100000800', 'Completed': '00000000000000000000000100000802'}

# Always rebuild from grants.yaml — clear any existing records from source XML
for _ch in list(root):
    if local(_ch.tag) == 'section' and _ch.get('label') == 'Research Funding History':
        root.remove(_ch)

import datetime as _dt
_CURRENT_YR = _dt.date.today().year

def add_grant(entry, competitive):
    pi_str  = str(entry.get('pi', ''))
    is_pi   = 'Menounos' in pi_str or me in pi_str
    my_role = entry.get('my_role', '')
    if my_role:
        role = my_role
    elif competitive:
        role = 'Principal Investigator' if is_pi else 'Co-investigator'
    else:
        role = 'Principal Applicant' if is_pi else 'Co-investigator'

    start_yr = int(str(entry.get('start', 0))[:4])
    end_yr   = int(str(entry.get('end',   start_yr))[:4])
    amt      = int(entry.get('amount_per_year', 0))
    total    = entry.get('total', amt * (end_yr - start_yr + 1))
    recv_pct = entry.get('received', 100)
    status   = 'Awarded' if end_yr >= _CURRENT_YR else 'Completed'
    ftype    = 'Contract' if not competitive else 'Grant'

    sec = ET.SubElement(root, 'section',
                        id=_GF['sec'], label='Research Funding History', recordId=new_id())
    sec.append(_flov(_GF['type'],   'Funding Type',      _GF_TYPE_LOV[ftype], ftype))
    sec.append(_fv  (_GF['start'],  'Funding Start Date', fmt(entry.get('start')), 'YearMonth', 'yyyy/MM'))
    sec.append(_fv  (_GF['end'],    'Funding End Date',   fmt(entry.get('end')),   'YearMonth', 'yyyy/MM'))
    sec.append(_fv  (_GF['title'],  'Funding Title',      entry.get('subject', '')))
    sec.append(_flov(_GF['gtype'],  'Grant Type',         '00000000000000000000000100001001', 'Operating'))
    sec.append(_fbil(_GF['desc'],   'Project Description'))
    sec.append(_fempty(_GF['clin'], 'Clinical Research Project?'))
    sec.append(_flov(_GF['status'], 'Funding Status',     _GF_STAT_LOV[status], status))
    sec.append(_flov(_GF['role'],   'Funding Role',       _GF_ROLE_LOV.get(role, _GF_ROLE_LOV['Co-investigator']), role))
    sec.append(_fbil(_GF['uptake'], 'Research Uptake'))

    src = ET.SubElement(sec, 'section',
                        id=_GFS['sec'], label='Funding Sources', recordId=new_id())
    src.append(_fempty(_GFS['org'],      'Funding Organization'))
    src.append(_fv    (_GFS['other_org'],'Other Funding Organization', entry.get('agency', '')))
    src.append(_fempty(_GFS['program'],  'Program Name'))
    src.append(_fempty(_GFS['ref'],      'Funding Reference Number'))
    src.append(_fv    (_GFS['total'],    'Total Funding',           str(total), 'Number'))
    src.append(_fempty(_GFS['currency'], 'Currency of Total Funding'))
    src.append(_fv    (_GFS['received'], 'Portion of Funding Received', str(recv_pct), 'Number'))
    src.append(_fempty(_GFS['recv_cur'], 'Currency of Portion of Funding Received'))
    src.append(_fempty(_GFS['renew'],    'Funding Renewable?'))
    src.append(_flov  (_GFS['comp'],     'Funding Competitive?',
                       _GF_COMP_LOV['Yes' if competitive else 'No'],
                       'Yes' if competitive else 'No'))
    src.append(_fv    (_GFS['src_s'],    'Funding Start Date', '', 'YearMonth', 'yyyy/MM'))
    src.append(_fv    (_GFS['src_e'],    'Funding End Date',   '', 'YearMonth', 'yyyy/MM'))

    cos = [c for c in (entry.get('co_investigators') or [])
           if c and 'Menounos' not in str(c) and str(c) != me]
    for co in cos:
        inv = ET.SubElement(sec, 'section',
                            id=_GFI['sec'], label='Other Investigators', recordId=new_id())
        inv.append(_fv  (_GFI['name'], 'Investigator Name', str(co)))
        inv.append(_flov(_GFI['role'], 'Role',
                         '00000000000000000000000100002802', 'Co-applicant'))
    if not is_pi and pi_str:
        inv = ET.SubElement(sec, 'section',
                            id=_GFI['sec'], label='Other Investigators', recordId=new_id())
        inv.append(_fv  (_GFI['name'], 'Investigator Name', pi_str))
        inv.append(_flov(_GFI['role'], 'Role',
                         '00000000000000000000000100002800', 'Principal Investigator'))

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
