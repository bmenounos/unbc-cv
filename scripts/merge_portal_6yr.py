#!/usr/bin/env python3
"""Merge portal 6yr export corrections into the filtered CCV_last6yrs.xml.

Usage: merge_portal_6yr.py <filtered.xml> <portal_6yr.xml> <dest.xml>

Takes publications/presentations from the filtered full-career CCV (correct,
complete, CrossRef-fixed), and supervision/service from the portal 6yr export
(authoritative — manually cleaned by user on portal website).
"""
import sys, os, re, io, copy
import xml.etree.ElementTree as ET

if len(sys.argv) < 4:
    sys.exit('Usage: merge_portal_6yr.py <filtered.xml> <portal_6yr.xml> <dest.xml>')

FILTERED   = sys.argv[1]   # CCV_last6yrs.xml from ccv_filter_6yrs.py
PORTAL_6YR = sys.argv[2]   # CCV_source_6yr.xml (portal manually-cleaned export)
DEST       = sys.argv[3]

NS = 'http://www.cihr-irsc.gc.ca/generic-cv/1.0.0'
ET.register_namespace('generic-cv', NS)

def local(t): return t.split('}')[-1] if '}' in t else t

def find_sec(root, *labels):
    cur = root
    for lbl in labels:
        for ch in cur:
            if local(ch.tag) == 'section' and ch.get('label') == lbl:
                cur = ch; break
        else:
            return None
    return cur

f_tree = ET.parse(FILTERED)
f_root = f_tree.getroot()
p_root = ET.parse(PORTAL_6YR).getroot()

def replace_children(f_parent, p_parent, child_label):
    """Remove all child records with child_label from f_parent; copy from p_parent."""
    if f_parent is None or p_parent is None:
        return 0
    for ch in list(f_parent):
        if local(ch.tag) == 'section' and ch.get('label') == child_label:
            f_parent.remove(ch)
    count = 0
    for ch in p_parent:
        if local(ch.tag) == 'section' and ch.get('label') == child_label:
            f_parent.append(copy.deepcopy(ch))
            count += 1
    return count

# 1. Supervision: replace with portal version
f_sup = find_sec(f_root, 'Activities', 'Supervisory Activities')
p_sup = find_sec(p_root, 'Activities', 'Supervisory Activities')
n = replace_children(f_sup, p_sup, 'Student/Postdoctoral Supervision')
print(f'Supervision records from portal: {n}')

# 2. Committee Memberships: replace with portal version
f_mb = find_sec(f_root, 'Memberships')
p_mb = find_sec(p_root, 'Memberships')
n = replace_children(f_mb, p_mb, 'Committee Memberships')
print(f'Committee Memberships from portal: {n}')

# 3. Organizational Review Activities: replace with portal version
f_ara = find_sec(f_root, 'Activities', 'Assessment and Review Activities')
p_ara = find_sec(p_root, 'Activities', 'Assessment and Review Activities')
n = replace_children(f_ara, p_ara, 'Organizational Review Activities')
print(f'Organizational Review Activities from portal: {n}')

# 4. Administrative Activities (Editorial): replace with portal version
f_act = find_sec(f_root, 'Activities')
p_adm = find_sec(p_root, 'Activities', 'Administrative Activities')
if f_act is not None:
    for ch in list(f_act):
        if local(ch.tag) == 'section' and ch.get('label') == 'Administrative Activities':
            f_act.remove(ch)
    if p_adm is not None:
        f_act.append(copy.deepcopy(p_adm))
        ed_count = sum(1 for ch in p_adm if local(ch.tag)=='section' and ch.get('label')=='Editorial Activities')
        print(f'Administrative Activities (editorial records: {ed_count}) from portal')

# 5. Research Funding History: replace with portal version (complete with Funding Sources + Other Investigators)
for ch in list(f_root):
    if local(ch.tag) == 'section' and ch.get('label') == 'Research Funding History':
        f_root.remove(ch)
n = 0
for ch in p_root:
    if local(ch.tag) == 'section' and ch.get('label') == 'Research Funding History':
        f_root.append(copy.deepcopy(ch))
        n += 1
print(f'Research Funding History records from portal: {n}')

# Write output
ET.indent(f_tree, space='  ')
buf = io.BytesIO()
f_tree.write(buf, encoding='utf-8', xml_declaration=False)
content = buf.getvalue().decode('utf-8')
content = re.sub(r'</generic-cv:(?!generic-cv\b)(\w+)>', r'</\1>', content)
content = re.sub(r'<generic-cv:(?!generic-cv\b)', '<', content)
with open(DEST, 'w', encoding='utf-8') as fh:
    fh.write('<?xml version="1.0" encoding="UTF-8"?>\n')
    fh.write(content)
print(f'Written: {DEST}')
