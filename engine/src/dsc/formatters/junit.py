from __future__ import annotations

import xml.etree.ElementTree as ET

from dsc.scanner.models import ScanResult


def format_junit(result: ScanResult) -> str:
    suite = ET.Element(
        "testsuite",
        attrib={
            "name": "dsc",
            "tests": str(len(result.findings)),
            "failures": str(len(result.findings)),
            "errors": "0",
        },
    )

    for f in result.findings:
        case = ET.SubElement(
            suite,
            "testcase",
            attrib={
                "classname": f.rule_id,
                "name": f"{f.file_path}:{f.line_start}",
            },
        )
        failure = ET.SubElement(
            case,
            "failure",
            attrib={"message": f.message},
        )
        body = f"{f.rule_id} {f.severity.name} {f.file_path}:{f.line_start}:{f.column}\n{f.message}\n"
        if f.fix_suggestion:
            body += f"Fix: {f.fix_suggestion}\n"
        failure.text = body

    xml_bytes = ET.tostring(suite, encoding="utf-8", xml_declaration=True)
    return xml_bytes.decode("utf-8") + "\n"

