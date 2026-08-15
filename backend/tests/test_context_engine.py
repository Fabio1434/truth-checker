from app.services.context_engine import ContextEngine


def test_context_engine_flags_old_year():
    issue = ContextEngine().detect_context_issues(
        "Cette règle est toujours en vigueur", "Le dispositif de 2018 a été remplacé."
    )
    assert issue is not None


def test_context_engine_does_not_flag_plain_current_text():
    issue = ContextEngine().detect_context_issues(
        "Le rapport publié en 2026 présente les résultats actuels.", "résultats actuels 2026"
    )
    assert issue is None or issue.get("issue_type") != "outdated"
