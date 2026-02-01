"""Email templates for cold outreach and follow-ups."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Optional

from jinja2 import Environment, BaseLoader


@dataclass
class EmailTemplate:
    """Email template with subject and body."""

    name: str
    subject: str
    body: str
    category: str = "cold_outreach"

    def render(self, **context: Any) -> tuple[str, str]:
        """
        Render the template with context.

        Args:
            **context: Template variables

        Returns:
            Tuple of (subject, body)
        """
        env = Environment(loader=BaseLoader())
        subject_template = env.from_string(self.subject)
        body_template = env.from_string(self.body)

        return (
            subject_template.render(**context),
            body_template.render(**context),
        )


# Cold Outreach Templates
COLD_OUTREACH_TEMPLATE = EmailTemplate(
    name="cold_outreach_v1",
    subject="{{ subject_line }}",
    body="""Guten Tag {{ anrede }} {{ ceo_name }},

ich bin auf {{ firma_name }} aufmerksam geworden, als ich nach {{ industry }}-Unternehmen in {{ region }} recherchiert habe.

{{ problem_hook }}

Bei meiner kurzen Analyse Ihrer Webseite ist mir aufgefallen:
{% for problem in website_problems %}
• {{ problem }}
{% endfor %}

Als Webentwickler mit Fokus auf Schweizer KMUs helfe ich Unternehmen wie {{ firma_name }}, ihre Online-Präsenz zu modernisieren - ohne riesige Budgets oder monatelange Projekte.

{{ value_proposition }}

Hätten Sie diese Woche 15 Minuten Zeit für ein kurzes Gespräch? Ich zeige Ihnen gerne, welche konkreten Verbesserungen möglich wären.

{{ signature }}""",
    category="cold_outreach",
)

COLD_OUTREACH_TEMPLATE_V2 = EmailTemplate(
    name="cold_outreach_v2",
    subject="{{ subject_line }}",
    body="""Guten Tag {{ anrede }} {{ ceo_name }},

kurze Frage: Wann haben Sie zuletzt Ihre Webseite auf einem Smartphone getestet?

Der Grund, warum ich frage: Bei {{ firma_name }} ist mir aufgefallen, dass {{ main_problem }}.

Das ist keine Kritik - viele {{ industry }}-Unternehmen in der Schweiz haben ähnliche Herausforderungen. Der Unterschied ist: {{ buying_signal_hook }}

Mein Angebot: Ein kostenloser 15-minütiger Website-Check für {{ firma_name }}. Konkret, ehrlich, ohne Verpflichtung.

Interesse?

{{ signature }}""",
    category="cold_outreach",
)

COLD_OUTREACH_TEMPLATE_V3 = EmailTemplate(
    name="cold_outreach_v3",
    subject="{{ subject_line }}",
    body="""Guten Tag {{ anrede }} {{ ceo_name }},

ich weiss, Sie bekommen wahrscheinlich viele solcher Emails. Deshalb mache ich es kurz:

{{ firma_name }} verliert vermutlich Kunden, weil:
{% for problem in website_problems[:2] %}
• {{ problem }}
{% endfor %}

Ich helfe {{ industry }}-Unternehmen, das zu ändern - schnell und bezahlbar.

Falls Sie neugierig sind: Ein Klick auf "Antworten" genügt, und ich zeige Ihnen, was ich meine.

{{ signature }}""",
    category="cold_outreach",
)

# Follow-up Templates
FOLLOW_UP_TEMPLATE_1 = EmailTemplate(
    name="follow_up_1",
    subject="Re: {{ original_subject }}",
    body="""Guten Tag {{ anrede }} {{ ceo_name }},

ich wollte nur kurz nachfragen, ob Sie meine letzte Nachricht gesehen haben.

Falls die Webseiten-Optimierung gerade kein Thema ist - kein Problem. Aber falls doch, stehe ich gerne für ein kurzes Gespräch zur Verfügung.

Beste Grüsse,
{{ sender_name }}""",
    category="follow_up",
)

FOLLOW_UP_TEMPLATE_2 = EmailTemplate(
    name="follow_up_2",
    subject="Eine letzte Frage zu {{ firma_name }}",
    body="""Guten Tag {{ anrede }} {{ ceo_name }},

ich schreibe ein letztes Mal bezüglich der Webseite von {{ firma_name }}.

Darf ich fragen: Ist eine Webseiten-Modernisierung aktuell überhaupt ein Thema für Sie? Eine kurze Antwort hilft mir, Sie nicht weiter zu belästigen.

Danke für Ihre Zeit,
{{ sender_name }}""",
    category="follow_up",
)

# Response Templates
POSITIVE_RESPONSE_TEMPLATE = EmailTemplate(
    name="positive_response",
    subject="Re: {{ original_subject }}",
    body="""Guten Tag {{ anrede }} {{ ceo_name }},

vielen Dank für Ihre Antwort - das freut mich sehr!

{{ response_content }}

Wann passt es Ihnen am besten? Ich bin flexibel und kann mich nach Ihrem Kalender richten.

Hier ein paar Vorschläge:
• {{ time_slot_1 }}
• {{ time_slot_2 }}
• {{ time_slot_3 }}

Oder nutzen Sie gerne diesen Link, um direkt einen Termin zu buchen: {{ calendar_link }}

Beste Grüsse,
{{ sender_name }}""",
    category="response",
)

QUESTION_RESPONSE_TEMPLATE = EmailTemplate(
    name="question_response",
    subject="Re: {{ original_subject }}",
    body="""Guten Tag {{ anrede }} {{ ceo_name }},

vielen Dank für Ihre Nachricht und die gute Frage.

{{ answer_content }}

Falls Sie weitere Fragen haben, beantworte ich diese gerne.

Beste Grüsse,
{{ sender_name }}""",
    category="response",
)

MEETING_CONFIRMATION_TEMPLATE = EmailTemplate(
    name="meeting_confirmation",
    subject="Bestätigung: Unser Gespräch am {{ meeting_date }}",
    body="""Guten Tag {{ anrede }} {{ ceo_name }},

hiermit bestätige ich unser Gespräch:

📅 Datum: {{ meeting_date }}
🕐 Uhrzeit: {{ meeting_time }}
📍 Ort: {{ meeting_location }}

Ich werde folgendes vorbereiten:
• Analyse Ihrer aktuellen Webseite
• Konkrete Verbesserungsvorschläge
• Beispiele ähnlicher Projekte

Falls sich etwas ändert, geben Sie mir bitte Bescheid.

Ich freue mich auf unser Gespräch!

Beste Grüsse,
{{ sender_name }}""",
    category="response",
)


# Subject Line Variations
SUBJECT_LINES = {
    "problem_focused": [
        "{{ firma_name }} - Kurze Frage zu Ihrer Webseite",
        "Verliert {{ firma_name }} Kunden durch die Webseite?",
        "Ihre Webseite auf dem Smartphone - haben Sie getestet?",
    ],
    "curiosity": [
        "Kurze Frage an {{ ceo_name }}",
        "{{ firma_name }} + moderne Webseite = ?",
        "15 Minuten für {{ firma_name }}?",
    ],
    "value_focused": [
        "Mehr Anfragen für {{ firma_name }} - eine Idee",
        "Webseite {{ firma_name }}: Potenzial erkannt",
        "{{ industry }} in {{ region }}: Digitale Chancen",
    ],
    "direct": [
        "Webentwicklung für {{ firma_name }}",
        "Angebot: Website-Check für {{ firma_name }}",
        "{{ ceo_name }} - Zusammenarbeit?",
    ],
}


# Value Propositions by Industry
VALUE_PROPOSITIONS = {
    "bau": """In der Baubranche entscheiden sich viele Kunden bereits vor dem ersten Anruf -
basierend auf dem, was sie online sehen. Eine professionelle Webseite zeigt Ihre Referenzen
und baut Vertrauen auf.""",
    "transport": """Im Transport- und Logistikbereich erwarten Kunden heute 24/7-Erreichbarkeit.
Eine moderne Webseite mit Kontaktformular und Angebotsanfrage macht genau das möglich -
ohne dass Sie ständig ans Telefon müssen.""",
    "logistik": """Logistik-Kunden recherchieren online, bevor sie anfragen. Eine klare,
schnelle Webseite mit Ihren Leistungen und Referenzen kann hier den Unterschied machen.""",
    "handwerk": """Handwerksbetriebe mit guter Online-Präsenz werden öfter gefunden und
kontaktiert. Ihre Arbeit spricht für sich - Ihre Webseite sollte das auch tun.""",
    "gastronomie": """Gäste suchen heute online nach Restaurants und Cafés. Speisekarte,
Öffnungszeiten, Reservierung - alles sollte auf einen Blick verfügbar sein.""",
    "default": """Eine professionelle Webseite ist heute oft der erste Eindruck, den
potenzielle Kunden von Ihrem Unternehmen bekommen. Sie sollte überzeugen.""",
}


# Problem Hooks by Website Issue
PROBLEM_HOOKS = {
    "nicht_mobile": "Über 60% der Schweizer surfen heute mit dem Smartphone - wenn Ihre "
    "Seite dort nicht gut aussieht, verlieren Sie potenzielle Kunden.",
    "langsam": "Wussten Sie, dass 40% der Besucher abspringen, wenn eine Seite länger "
    "als 3 Sekunden lädt? Jede Sekunde zählt.",
    "veraltet": "Eine veraltete Webseite kann den Eindruck erwecken, dass auch Ihr "
    "Unternehmen nicht auf dem neuesten Stand ist - auch wenn das Gegenteil der Fall ist.",
    "kein_ssl": "Ohne SSL-Zertifikat (https) zeigen Browser Warnungen an. Das schreckt "
    "Besucher ab und schadet Ihrem Google-Ranking.",
    "kein_kontaktformular": "Ohne einfache Kontaktmöglichkeit verlieren Sie Anfragen von "
    "Kunden, die nicht telefonieren möchten.",
    "default": "Ihre Online-Präsenz hat Potenzial, das noch nicht ausgeschöpft wird.",
}


class EmailTemplateManager:
    """Manager for email templates."""

    def __init__(self) -> None:
        """Initialize template manager."""
        self.templates = {
            "cold_outreach_v1": COLD_OUTREACH_TEMPLATE,
            "cold_outreach_v2": COLD_OUTREACH_TEMPLATE_V2,
            "cold_outreach_v3": COLD_OUTREACH_TEMPLATE_V3,
            "follow_up_1": FOLLOW_UP_TEMPLATE_1,
            "follow_up_2": FOLLOW_UP_TEMPLATE_2,
            "positive_response": POSITIVE_RESPONSE_TEMPLATE,
            "question_response": QUESTION_RESPONSE_TEMPLATE,
            "meeting_confirmation": MEETING_CONFIRMATION_TEMPLATE,
        }
        self.subject_lines = SUBJECT_LINES
        self.value_propositions = VALUE_PROPOSITIONS
        self.problem_hooks = PROBLEM_HOOKS

    def get_template(self, name: str) -> Optional[EmailTemplate]:
        """Get a template by name."""
        return self.templates.get(name)

    def get_cold_outreach_template(self, variant: int = 1) -> EmailTemplate:
        """Get a cold outreach template variant."""
        return self.templates.get(f"cold_outreach_v{variant}", COLD_OUTREACH_TEMPLATE)

    def get_follow_up_template(self, sequence_number: int = 1) -> EmailTemplate:
        """Get a follow-up template."""
        return self.templates.get(f"follow_up_{sequence_number}", FOLLOW_UP_TEMPLATE_1)

    def get_subject_lines(
        self, category: str, context: dict[str, Any]
    ) -> list[str]:
        """Get subject line options for a category."""
        templates = self.subject_lines.get(category, self.subject_lines["direct"])
        env = Environment(loader=BaseLoader())
        return [env.from_string(t).render(**context) for t in templates]

    def get_value_proposition(self, industry: str) -> str:
        """Get value proposition for an industry."""
        return self.value_propositions.get(
            industry.lower(), self.value_propositions["default"]
        )

    def get_problem_hook(self, problem_type: str) -> str:
        """Get problem hook text."""
        return self.problem_hooks.get(problem_type, self.problem_hooks["default"])

    def render_cold_email(
        self,
        ceo_name: str,
        firma_name: str,
        industry: str,
        region: str,
        website_problems: list[str],
        variant: int = 1,
        signature: str = "",
        **extra_context: Any,
    ) -> tuple[str, str]:
        """
        Render a complete cold email.

        Args:
            ceo_name: Name of the CEO/decision maker
            firma_name: Company name
            industry: Industry type
            region: Geographic region
            website_problems: List of identified website problems
            variant: Template variant (1, 2, or 3)
            signature: Email signature
            **extra_context: Additional template context

        Returns:
            Tuple of (subject, body)
        """
        template = self.get_cold_outreach_template(variant)

        # Determine anrede
        anrede = "Herr" if extra_context.get("gender") == "male" else "Frau"
        if not extra_context.get("gender"):
            anrede = "Herr/Frau"

        # Get appropriate hooks
        main_problem = website_problems[0] if website_problems else "Verbesserungspotenzial"
        problem_type = self._categorize_problem(main_problem)
        problem_hook = self.get_problem_hook(problem_type)
        value_proposition = self.get_value_proposition(industry)

        # Get subject lines and pick best one
        subject_context = {
            "firma_name": firma_name,
            "ceo_name": ceo_name,
            "industry": industry,
            "region": region,
        }
        subject_lines = self.get_subject_lines("problem_focused", subject_context)
        subject_line = subject_lines[0]  # Could add more sophisticated selection

        context = {
            "subject_line": subject_line,
            "anrede": anrede,
            "ceo_name": ceo_name,
            "firma_name": firma_name,
            "industry": industry,
            "region": region,
            "website_problems": website_problems,
            "main_problem": main_problem,
            "problem_hook": problem_hook,
            "value_proposition": value_proposition,
            "buying_signal_hook": extra_context.get(
                "buying_signal_hook", "Sie scheinen gerade zu wachsen"
            ),
            "signature": signature,
            **extra_context,
        }

        return template.render(**context)

    def _categorize_problem(self, problem: str) -> str:
        """Categorize a problem for hook selection."""
        problem_lower = problem.lower()
        if "mobil" in problem_lower or "responsive" in problem_lower:
            return "nicht_mobile"
        if "langsam" in problem_lower or "geschwindigkeit" in problem_lower:
            return "langsam"
        if "alt" in problem_lower or "veraltet" in problem_lower:
            return "veraltet"
        if "ssl" in problem_lower or "https" in problem_lower:
            return "kein_ssl"
        if "kontakt" in problem_lower or "formular" in problem_lower:
            return "kein_kontaktformular"
        return "default"
