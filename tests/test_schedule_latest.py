from estimates_monitor import schedule


def test_latest_ref_from_fixture():
    # load the captured live schedule HTML fixture
    with open('schedule.html', 'r', encoding='utf-8') as f:
        html = f.read()
    entries = schedule._parse_schedule_html(html, base_url='https://www.aph.gov.au/Parliamentary_Business/Hansard/Estimates_Transcript_Schedule')
    assert any(e for e in entries if '29366' in (str(e.ref_no) if e.ref_no else ''))
    # sort using module sort key (descending)
    entries.sort(key=schedule._sort_key_latest, reverse=True)
    top = entries[0]
    est, doc, _ = schedule._extract_estimate_id_parts(top.page_url)
    assert est == '29366', f"expected top estimate 29366 but got {est} (url={top.page_url})"
