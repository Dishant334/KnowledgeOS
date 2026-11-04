# eval/corpus.py
"""
The evaluation corpus: 13 synthetic documents of a fictional company ("Northwind Labs"),
written in 5 file formats so the real loaders are exercised too.
"""

import io
import random
import re
import zipfile
from dataclasses import dataclass

import pymupdf

MIME = {
    "md": "text/markdown",
    "txt": "text/plain",
    "html": "text/html",
    "pdf": "application/pdf",
    "docx": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
}

# Neutral sentences with no numbers, used to pad documents so they are cut into several chunks.
FILLER = [
    "This section applies to all employees of Northwind Labs in every office.",
    "Questions about this section can be sent to the people team through the internal help channel.",
    "Managers are expected to explain these rules to their teams during onboarding.",
    "Exceptions require a written request and the approval of a department head.",
    "The company reviews this document regularly and publishes updates on the intranet.",
    "Employees are encouraged to read the full text before asking for clarification.",
    "Contractors follow the rules of their agreement, which may differ from this document.",
    "If a rule here conflicts with local law, the local law takes precedence.",
    "Records related to these rules are kept in the company archive for the required period.",
    "The people team is happy to walk new colleagues through the process step by step.",
    "Teams may add their own guidelines as long as they do not contradict the company rules.",
    "Requests are handled in the order in which they arrive.",
    "Employees should keep their manager informed about anything that affects their work.",
    "Please use the standard forms that are available on the intranet.",
    "Shared documents should be stored in the team workspace, not on personal devices.",
    "The company values clear communication and expects everyone to be respectful.",
    "Feedback on these rules is welcome and can be shared with the people team at any time.",
    "Temporary arrangements are possible when a colleague is covering for someone else.",
    "Each department nominates a contact person who knows these rules well.",
    "Training materials about this topic are available in the learning library.",
    "Where several options are allowed, the most economical one should be chosen.",
    "Colleagues who are unsure about a rule should ask before acting rather than after.",
    "Seasonal peaks in workload may slightly delay the processing of requests.",
    "Confidential information discussed in this context must not be shared outside the company.",
    "Any misuse of these arrangements may lead to disciplinary action.",
    "The rules described here were agreed together with the employee representatives.",
    "A short summary of this section is available as a one-page poster in every office.",
    "Translations of this document are provided for offices where English is not the main language.",
    "Updates take effect on the first working day after they are announced.",
    "Employees on leave are not expected to respond to requests related to this section.",
    "Reminders about upcoming changes are sent by email and posted on the intranet front page.",
    "The company keeps a short list of frequently asked questions next to every policy.",
    "Employees working part time follow the same procedure and may ask the people team for guidance.",
    "Where an approval is needed, the request should explain the business reason clearly.",
    "Colleagues are asked to plan ahead so that teams can arrange cover without disruption.",
    "The facilities team can help with practical questions about the offices.",
    "Each office keeps a printed copy of the policy handbook at the reception desk.",
    "Policies are written in plain language and should be read together with the handbook introduction.",
    "Staff who join part way through the year receive their entitlements in proportion.",
    "A representative of the employee council attends the yearly review of these rules.",
    "Departments report on how these arrangements are working at the end of each quarter.",
    "The company aims to treat every request fairly and consistently across teams.",
    "Anonymous suggestions for improving a process can be left in the feedback box.",
    "Newly published versions replace all earlier versions of the same document.",
    "People who are unsure whether a situation is covered should speak to their manager first.",
    "Large teams may agree a simple schedule among themselves to avoid overlapping absences.",
    "The intranet search box finds the latest version of every policy by its title.",
    "Auditors may request to see how these rules were applied in individual cases.",
    "Complaints about how a rule was applied are handled by the people team in confidence.",
    "Language that is unclear in this document will be clarified in the next revision.",
    "Mentors and buddies are a good first point of contact for practical questions.",
    "Photographs and posters in the offices summarise the key points for visitors.",
    "The company does not tolerate pressure on colleagues to ignore these rules.",
    "Health and safety officers are available in each building during normal working hours.",
    "Departments with special requirements agree additional guidance with the people team.",
    "Regional managers decide how to apply these rules to their local situation within the limits given here.",
    "Information about changes is shared first with managers, who then inform their teams.",
    "The yearly all-hands meeting includes a short update about policies and processes.",
    "Digital copies of signed forms are stored securely and are available on request.",
    "Colleagues returning after a long absence receive a brief refresher on these arrangements.",
]

# (filename, kind, title, [(section heading, [fact sentences])])
DOCS = [
    ("leave_policy.md", "md", "Leave Policy", [
        ("Vacation", ["Full-time employees accrue 25 days of paid vacation per calendar year.",
                      "Up to 5 unused vacation days may be carried over into the next calendar year."]),
        ("Family leave", ["Parental leave is 16 weeks at full pay for each parent."]),
        ("Sick leave", ["A doctor's note is required for sick leave longer than 3 consecutive days."]),
        ("Bereavement", ["Bereavement leave is 5 days for the loss of an immediate family member."]),
    ]),
    ("expense_policy.pdf", "pdf", "Expense Policy", [
        ("Submitting claims", ["Expense claims must be submitted within 30 days of the purchase date.",
                               "Receipts are required for every expense above $25."]),
        ("Meals", ["Meals are reimbursed up to $60 per day while travelling on company business."]),
        ("Flights", ["Flights must be booked in economy class unless the flight is longer than 8 hours."]),
        ("Mileage", ["Personal car mileage is reimbursed at $0.58 per mile."]),
    ]),
    ("remote_work_policy.docx", "docx", "Remote Work Policy", [
        ("Working remotely", ["Employees may work remotely up to 3 days per week with manager approval.",
                              "Core collaboration hours are 10:00 to 15:00 in the employee's local time."]),
        ("Equipment", ["A one-time home office stipend of $400 is paid after the first 90 days."]),
        ("Working abroad", ["Working from another country is limited to 20 days per calendar year."]),
    ]),
    ("security_policy.html", "html", "Information Security Policy", [
        ("Incidents", ["Any security incident must be reported to the security team within 2 hours of discovery."]),
        ("Devices", ["Laptops lock automatically after 5 minutes of inactivity.",
                     "USB storage devices are not allowed on company laptops."]),
        ("Accounts", ["Multi-factor authentication is mandatory for all company accounts.",
                      "Company passwords must be stored in the approved password manager."]),
    ]),
    ("benefits_guide.md", "md", "Benefits Guide", [
        ("Retirement", ["The company matches 401k contributions up to 4 percent of salary."]),
        ("Health", ["Health insurance covers employees and their dependents, and a spouse can be added at enrolment."]),
        ("Wellbeing and learning", ["A gym stipend of $50 per month is available to all employees.",
                                    "Each employee has a learning budget of $1,500 per year."]),
        ("Equity", ["Stock options vest over 4 years with a 1-year cliff."]),
    ]),
    ("onboarding_guide.txt", "txt", "Onboarding Guide", [
        ("Before the first day", ["New hires receive their laptop at least one day before their start date."]),
        ("First weeks", ["Every new hire is assigned an onboarding buddy for the first 90 days.",
                         "Orientation sessions are held every Monday at 9:30."]),
        ("Mandatory training", ["Employees must complete the security awareness course within 14 days of joining."]),
    ]),
    ("it_helpdesk.md", "md", "IT Helpdesk Guide", [
        ("Opening hours", ["The IT helpdesk is open from 8:00 to 18:00 on weekdays."]),
        ("Tickets", ["Priority 1 tickets receive a first response within 1 hour."]),
        ("Accounts and devices", ["Passwords can be reset through the self-service portal.",
                                  "Loaner laptops are available at the reception desk."]),
    ]),
    ("travel_policy_europe.pdf", "pdf", "Travel Policy: Europe", [
        ("Allowances", ["For travel in Europe the daily allowance is EUR 75."]),
        ("Hotels", ["The hotel limit in Europe is EUR 180 per night."]),
        ("Transport", ["Rail travel is preferred for journeys under 4 hours in Europe."]),
    ]),
    ("travel_policy_us.pdf", "pdf", "Travel Policy: United States", [
        ("Allowances", ["For travel in the United States the daily allowance is $85."]),
        ("Hotels", ["The hotel limit in the United States is $220 per night."]),
        ("Transport", ["Rental cars are allowed for trips outside major cities."]),
    ]),
    ("performance_reviews.md", "md", "Performance Reviews", [
        ("Review cycle", ["Performance reviews take place twice a year, in June and in December.",
                          "Ratings use a scale from 1 to 5."]),
        ("Promotions", ["Promotion decisions are made once a year in January."]),
        ("Improvement plans", ["A performance improvement plan lasts 60 days."]),
    ]),
    ("holidays_2027.md", "md", "Holidays 2027", [
        ("Public holidays", ["The company observes 12 public holidays in 2027.",
                             "Each employee also gets 2 floating holidays."]),
        ("Winter break", ["The winter break runs from December 24 to January 1."]),
        ("Office hours", ["The office closes at 6 pm on Fridays."]),
    ]),
    ("procurement_policy.docx", "docx", "Procurement Policy", [
        ("Quotes and approvals", ["Purchases above $5,000 require two written quotes.",
                                  "Purchases above $25,000 need approval from the CFO."]),
        ("Vendors", ["New vendors take 10 business days to onboard."]),
        ("Software", ["Software subscriptions must be approved by the IT department."]),
    ]),
    ("engineering_handbook.md", "md", "Engineering Handbook", [
        ("Code review", ["Every pull request needs approval from 2 reviewers before merging."]),
        ("Releases", ["Production deployments are frozen on Fridays."]),
        ("On-call", ["The on-call rotation changes every week."]),
        ("Incidents and reliability", ["A written post-incident review is due within 5 days of an incident.",
                                       "The availability target for the main product is 99.9 percent."]),
    ]),
]

FILLER_PER_SECTION = 40   # more filler = longer documents = more chunks to search through


@dataclass
class Document:
    filename: str
    kind: str
    mime: str
    data: bytes
    text: str   # plain text, used by tests to check the golden set against the documents


def section_paragraphs(filename: str, sections) -> list[tuple[str, list[str]]]:
    """For each section: its facts mixed with filler sentences (always the same for the same file)."""
    rng = random.Random(filename)
    result = []
    for heading, facts in sections:
        sentences = rng.sample(FILLER, FILLER_PER_SECTION)
        for fact in facts:
            sentences.insert(rng.randint(1, len(sentences) - 1), fact)
        result.append((heading, sentences))
    return result


def docx_bytes(paragraphs: list[str]) -> bytes:
    """A minimal valid .docx file (a zip with one XML document)."""
    body = "".join(f"<w:p><w:r><w:t>{p}</w:t></w:r></w:p>" for p in paragraphs)
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w") as z:
        z.writestr("[Content_Types].xml", '<?xml version="1.0"?><Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types"><Default Extension="xml" ContentType="application/xml"/><Override PartName="/word/document.xml" ContentType="application/vnd.openxmlformats-officedocument.wordprocessingml.document.main+xml"/></Types>')
        z.writestr("word/document.xml", f'<?xml version="1.0"?><w:document xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main"><w:body>{body}</w:body></w:document>')
    return buffer.getvalue()


def render(filename: str, kind: str, title: str, sections) -> bytes:
    parts = section_paragraphs(filename, sections)

    if kind == "md":
        text = f"# {title}\n\n" + "\n\n".join(f"## {h}\n\n" + " ".join(s) for h, s in parts) + "\n"
        return text.encode()
    if kind == "txt":
        return (f"{title}\n\n" + "\n\n".join(f"{h}\n" + " ".join(s) for h, s in parts) + "\n").encode()
    if kind == "html":
        body = "".join(f"<h2>{h}</h2><p>{' '.join(s)}</p>" for h, s in parts)
        return f"<html><body><h1>{title}</h1>{body}</body></html>".encode()
    if kind == "docx":
        return docx_bytes([title] + [x for h, s in parts for x in (h, " ".join(s))])
    if kind == "pdf":
        doc = pymupdf.open()
        for heading, sentences in parts:                      # one page per section
            page = doc.new_page()
            leftover = page.insert_textbox(pymupdf.Rect(50, 50, 550, 790), f"{title}\n\n{heading}\n\n" + " ".join(sentences), fontsize=8)
            assert leftover >= 0, f"{filename}: section '{heading}' does not fit on one PDF page (text would be cut off)"
        return doc.tobytes()
    raise ValueError(f"unknown kind {kind}")


def plain_text(sections) -> str:
    """All sentences of a document as one whitespace-normalised string."""
    return " ".join(" ".join(" ".join(facts) for _, facts in sections).split())


def build_corpus() -> list[Document]:
    documents = []
    for filename, kind, title, sections in DOCS:
        data = render(filename, kind, title, sections)
        documents.append(Document(filename, kind, MIME[kind], data, plain_text(sections)))
    return documents


def normalise(text: str) -> str:
    return re.sub(r"\s+", " ", text).strip()
