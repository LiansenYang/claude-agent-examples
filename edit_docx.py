# -*- coding: utf-8 -*-
import xml.etree.ElementTree as ET
import zipfile
import shutil
import os
import sys

SRC = r"C:\Users\root\Desktop\3_兼职.docx"
OUT = r"C:\Users\root\Desktop\3_兼职.docx"
TMP = r"F:\IntelliJ_project\claude-agent-examples\tmp_docx"
RESULT = r"F:\IntelliJ_project\claude-agent-examples\edit_result.txt"

def log(msg):
    with open(RESULT, "a", encoding="utf-8") as f:
        f.write(msg + "\n")

# Clean tmp
if os.path.exists(TMP):
    shutil.rmtree(TMP)

# Unpack
log("Unpacking...")
with zipfile.ZipFile(SRC, "r") as zf:
    zf.extractall(TMP)
log("Unpacked to: " + TMP)

# Parse document.xml
doc_xml = os.path.join(TMP, "word", "document.xml")
log("Reading: " + doc_xml)
tree = ET.parse(doc_xml)
root = tree.getroot()

# Define namespaces
ns = {
    "w": "http://schemas.openxmlformats.org/wordprocessingml/2006/main",
}

# Find the last paragraph in the body
body = root.find("w:body", ns)
paragraphs = body.findall("w:p", ns)
log("Found " + str(len(paragraphs)) + " paragraphs")

# Create a new paragraph with text '已完成测试'
# Build XML manually to ensure correct structure
new_p = ET.SubElement(body, "{http://schemas.openxmlformats.org/wordprocessingml/2006/main}p")
new_r = ET.SubElement(new_p, "{http://schemas.openxmlformats.org/wordprocessingml/2006/main}r")
new_t = ET.SubElement(new_r, "{http://schemas.openxmlformats.org/wordprocessingml/2006/main}t")
new_t.text = "已完成测试"
new_t.set("{http://www.w3.org/XML/1998/namespace}space", "preserve")

log("New paragraph added")

# Write document.xml back
tree.write(doc_xml, xml_declaration=True, encoding="UTF-8", standalone=True)
log("document.xml written")

# Remove existing docx if exists
if os.path.exists(OUT + ".bak"):
    os.remove(OUT + ".bak")
if os.path.exists(OUT):
    shutil.move(OUT, OUT + ".bak")

# Pack back to docx
log("Packing docx...")
with zipfile.ZipFile(OUT, "w", zipfile.ZIP_DEFLATED) as zout:
    for dirpath, dirnames, filenames in os.walk(TMP):
        for fn in filenames:
            full = os.path.join(dirpath, fn)
            arcname = os.path.relpath(full, TMP)
            zout.write(full, arcname)
            log("  Adding: " + arcname)

log("DONE - docx saved to: " + OUT)

# Cleanup tmp
shutil.rmtree(TMP)
log("Temp cleaned up")