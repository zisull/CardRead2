"""把 pytest 的 junitxml 失败项转写成 GitHub annotations

CI 日志接口需要鉴权，annotations 不需要，失败时至少能在 API 里看到具体是哪个用例。
"""
import sys
import xml.etree.ElementTree as ET

MAX_ANNOTATIONS = 40


def annotate(path: str) -> int:
    try:
        root = ET.parse(path).getroot()
    except Exception as e:
        print('::error::无法解析 junit 报告 %s: %s' % (path, e))
        return 0

    cases = list(root.iter('testcase'))
    failed = [tc for tc in cases if any(n.tag in ('failure', 'error') for n in tc)]
    print('collected=%d failed=%d' % (len(cases), len(failed)))

    for tc in failed[:MAX_ANNOTATIONS]:
        for node in tc:
            if node.tag not in ('failure', 'error'):
                continue
            detail = ((node.get('message') or '') + ' || ' + (node.text or '')).strip()
            detail = detail.replace('%', '%25').replace('\r', '').replace('\n', '%0A')
            print('::error::%s › %s: %s' % (tc.get('classname'), tc.get('name'), detail[:900]))
    if len(failed) > MAX_ANNOTATIONS:
        print('::error::其余 %d 个失败见日志' % (len(failed) - MAX_ANNOTATIONS))
    return 0


if __name__ == '__main__':
    sys.exit(annotate(sys.argv[1] if len(sys.argv) > 1 else 'results.xml'))
