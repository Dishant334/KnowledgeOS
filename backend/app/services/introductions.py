"""
Social messages are answered and remembered at once, with no search and no LLM call:

    "hello, how are you? myself Dishant Kumar, what's your name?"
      -> "Hello Dishant Kumar! I'm doing well, thanks for asking. I'm KnowledgeOS, ... I'll remember your name."

A message is split into clauses; each clause is a SELF-FACT, a SOCIAL phrase, or OTHER (a real question).
Only when nothing is OTHER is the whole message social. Self-facts (also inside a message that asks a real
question) are stored in long-term memory:

    name       "my name is X", "myself X", "I'm X" / "I am X", "call me X", "this is X"   -> "Name: X"
    role       "I am a/an X", "I work as a/an X"                                          -> "Role: X"
    workplace  "I work at/for X", "I work in X"                                           -> "Works at: X" / "Works in: X"
    preference "I prefer X"                                                               -> "Prefers: X"

Look-alikes are rejected ("I'm fine", "I am not sure", "I am looking for the policy", "this is great"):
a name is 1-3 plain words, none of them a common word. The stored text still goes through the memory
guard (no secrets, no instructions) in app/memory/store.py. Everything else a conversation says about the
user is learned by the per-conversation memory step (an LLM call, see services/conversation_memory.py).
"""

import re
from dataclasses import dataclass

NAME_PREFIX = "Name: "

# words that are never part of a name ("I'm fine", "I am not sure", "this is great", "I'm from Delhi"...)
_NOT_A_NAME = set("""
a an the not no yes so very really just also too quite pretty bit little lot fine good great ok okay alright well bad
sad happy glad sorry sure unsure new old here there back home ready done busy free tired confused lost stuck
from at in on of for with to by about into over looking trying going working using asking wondering thinking
interested curious excited worried afraid able unable available back again still now currently always never
what who how why where when which this that these those it its is are was be been my your our their his her
student teacher engineer developer manager doctor admin user customer employee intern
hi hello hey thanks thank you please wrong right correct awesome cool nice amazing perfect terrible
me him her us them myself someone somebody anyone nobody everyone
""".split())

_ARTICLE = r"(?:a|an)"

# social phrases: (kind, pattern for a WHOLE clause, after the greeting word is removed)
_SOCIAL = [
    ("how_are_you", re.compile(r"^(?:and\s+)?(?:how (?:are|r) (?:you|u|ya)(?: doing)?(?: today)?|how(?:'s| is) it going|how do you do|what'?s up|sup|wassup|you good)$", re.I)),
    ("ask_name", re.compile(r"^(?:and\s+)?(?:what(?:'s| is) your name|who are (?:you|u)|what are (?:you|u)|your name|tell me about yourself|introduce yourself)$", re.I)),
    ("capabilities", re.compile(r"^(?:what can (?:you|u) do|how can (?:you|u) help(?: me)?|help)$", re.I)),
    ("nice_to_meet", re.compile(r"^(?:nice|glad|pleased|good) to meet (?:you|u)(?: too)?$", re.I)),
    ("thanks", re.compile(r"^(?:thanks?(?: you)?(?: (?:so|very) much)?|thank u|thx|ty|cheers)$", re.I)),
    ("bye", re.compile(r"^(?:bye|goodbye|good night|see (?:you|ya)(?: later)?|take care)$", re.I)),
    ("ack", re.compile(r"^(?:ok(?:ay)?|cool|nice|great|alright|got it|sure)$", re.I)),
]
_GREETING = re.compile(
    r"^(?:hi+|hey+|hello+|hiya|yo|howdy|namaste|good (?:morning|afternoon|evening|day))"
    r"(?:\s+(?:there|again|everyone|all|team|guys|friend|kos|knowledgeos|bot))?\b[\s,!.]*",
    re.I,
)

_NAME = re.compile(r"^(?:my name is|my name's|myself|i am|i'm|im|call me|this is)\s+(.+)$", re.I)
_ROLE = re.compile(rf"^(?:i am|i'm|im|i work as)\s+{_ARTICLE}\s+(.{{2,60}})$", re.I)
_WORKPLACE = re.compile(r"^i work (at|for|in)\s+(.{2,60})$", re.I)
_PREFERENCE = re.compile(r"^i prefer\s+(.{3,80})$", re.I)

# first words of "I am a ..." that describe a mood or amount, not a role ("I am a bit confused")
_NOT_A_ROLE = {"bit", "little", "lot", "fan", "big", "huge", "quick", "real", "new"}


@dataclass(frozen=True)
class SelfFact:
    kind: str   # "name" | "role" | "workplace" | "preference"
    text: str   # how it is stored, e.g. "Name: Dishant Kumar"
    value: str  # the part the user said, e.g. "Dishant Kumar"


def _clauses(message: str) -> list[str]:
    parts = re.split(r"[.,!?;\n]+|\s+and\s+", message)
    return [" ".join(p.split()) for p in parts if p and p.strip()]


def _as_name(raw: str) -> str | None:
    words = raw.strip(" '\"").split()
    if not 1 <= len(words) <= 3:
        return None
    if any(not re.fullmatch(r"[A-Za-z][A-Za-z'\-]*", w) or w.lower() in _NOT_A_NAME or w.lower().endswith("ing") for w in words):
        return None
    def tidy(word: str) -> str:
        if word.isupper() and len(word) <= 3:
            return word                                    # initials stay as written ("DK")
        if word.islower() or word.isupper():
            return word[:1].upper() + word[1:].lower()     # "dishant" / "DISHANT" -> "Dishant"
        return word                                        # mixed case is kept ("McKenzie")

    return " ".join(tidy(w) for w in words)


def _fact_in(clause: str) -> SelfFact | None:
    clause = _GREETING.sub("", clause).strip()
    if not clause:
        return None
    if m := _ROLE.match(clause):
        role = m.group(1).strip().rstrip("?")
        if role.split()[0].lower() not in _NOT_A_ROLE and "?" not in clause:
            return SelfFact("role", f"Role: {role}", role)
    if m := _WORKPLACE.match(clause):
        where = m.group(2).strip()
        label = "Works in" if m.group(1).lower() == "in" else "Works at"
        return SelfFact("workplace", f"{label}: {where}", where)
    if m := _PREFERENCE.match(clause):
        what = m.group(1).strip()
        return SelfFact("preference", f"Prefers: {what}", what)
    if m := _NAME.match(clause):
        if name := _as_name(m.group(1)):
            return SelfFact("name", f"{NAME_PREFIX}{name}", name)
    return None


@dataclass
class Analysis:
    facts: list[SelfFact]   # self-facts found anywhere in the message
    social: list[str]       # social phrases found ("greeting", "how_are_you", "ask_name", ...)
    only_social: bool       # True when the WHOLE message is greetings / small talk / self-facts (no real question)


def _social_kind(clause: str) -> str | None:
    if _GREETING.match(clause) and not _GREETING.sub("", clause).strip():
        return "greeting"
    rest = _GREETING.sub("", clause).strip().rstrip("?")
    for kind, pattern in _SOCIAL:
        if pattern.match(rest):
            return kind
    return None


def analyze_message(message: str) -> Analysis:
    facts: list[SelfFact] = []
    social: list[str] = []
    other = False
    for clause in _clauses(message):
        if _GREETING.match(clause) and "greeting" not in social:
            social.append("greeting")
        kind = _social_kind(clause)
        if kind:
            if kind not in social:
                social.append(kind)
            continue
        fact = _fact_in(clause)
        if fact:
            if fact not in facts:
                facts.append(fact)
            continue
        other = True
    return Analysis(facts, social, bool(facts or social) and not other)


ABOUT_ME = (
    "I'm KnowledgeOS, your document assistant: I answer questions from the documents you add to a chat, "
    "and every answer points to the passage it came from."
)
GREETING_REPLY = (
    "Hello! I'm KnowledgeOS. Add a document to this chat with the paperclip, and ask me anything about it: "
    "every answer points to the passage it came from."
)


def social_reply(analysis: Analysis, saved: list[SelfFact], memory_full: bool, has_documents: bool) -> str:
    """One friendly answer that covers every part of a social message (`saved` = facts now in memory)."""
    social, facts = analysis.social, analysis.facts
    name = next((f.value for f in facts if f.kind == "name"), None)

    # a bare greeting in a chat without documents: the standard welcome
    if social == ["greeting"] and not facts and not has_documents:
        return GREETING_REPLY

    parts: list[str] = []
    if "bye" in social and not facts:
        return "Goodbye! Your chats and documents stay here in the sidebar." + (f" See you, {name}!" if name else "")
    if name:
        parts.append(f"Hello {name}! Nice to meet you." if "greeting" in social or "nice_to_meet" in social or len(social) == 0
                     else f"Nice to meet you, {name}!")
    elif "greeting" in social:
        parts.append("Hello! Nice to meet you too." if "nice_to_meet" in social else "Hello!")
    elif "nice_to_meet" in social:
        parts.append("Nice to meet you too!")
    if "how_are_you" in social:
        parts.append("I'm doing well, thanks for asking.")
    if "thanks" in social:
        parts.append("You're welcome!")
    if "ask_name" in social or "capabilities" in social:
        parts.append(ABOUT_ME)
    if facts:
        others = [f for f in saved if f.kind != "name"]
        if saved and any(f.kind == "name" for f in saved) and not others:
            parts.append("I'll remember your name.")
        elif saved:
            parts.append(("I'll remember your name and that you " if any(f.kind == "name" for f in saved) else "I'll remember that you ")
                         + _describe(others) + ".")
        if memory_full and len(saved) < len(facts):
            parts.append('My memory is full (15 facts), so I couldn\'t save everything. You can remove something under "What I remember about you".')
    if "ack" in social and not parts:
        parts.append("Great!")
    if "bye" not in social:
        parts.append("What would you like to know about your documents?" if has_documents
                     else "Add a document with the paperclip whenever you want to ask about it.")
    return " ".join(parts)


def _describe(facts: list[SelfFact]) -> str:
    phrases = []
    for f in facts:
        if f.kind == "role":
            phrases.append(f"are {'an' if f.value[:1].lower() in 'aeiou' else 'a'} {f.value}")
        elif f.kind == "workplace":
            phrases.append(f"work {'in' if f.text.startswith('Works in') else 'at'} {f.value}")
        elif f.kind == "preference":
            phrases.append(f"prefer {f.value}")
    return " and ".join(phrases)
