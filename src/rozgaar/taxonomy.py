"""A general skill taxonomy: canonical skill name -> phrases that mean it.

This is shared vocabulary, not anyone's resume. It is used to

* recognise skills in job-description text (the heuristic parser and the
  keyword extractor), and
* resolve the free-text skills in a user's profile to canonical names, so
  "Postgres" in a profile covers "PostgreSQL" in a job post.

Matching is whole-word (see :func:`find_terms`), so a short alias like "go"
or "r" never fires inside longer words. Aliases that are too ambiguous to
match safely on their own (bare "r", bare "c") are deliberately left out.
"""

from __future__ import annotations

import re
from collections.abc import Iterable
from functools import lru_cache

SKILLS: dict[str, tuple[str, ...]] = {
    # --- languages -------------------------------------------------------
    "Python": ("python",),
    "SQL": ("sql", "t-sql", "pl/sql", "ms sql", "mysql", "sql server"),
    "PostgreSQL": ("postgresql", "postgres"),
    "Java": ("java",),
    "JavaScript": ("javascript", "ecmascript"),
    "TypeScript": ("typescript",),
    "Go": ("golang", "go programming"),
    "C++": ("c++", "cpp"),
    "C#": ("c#", ".net", "dotnet"),
    "Rust": ("rust",),
    "Scala": ("scala",),
    "R": ("r programming", "rstudio", "tidyverse"),
    "Bash": ("bash", "shell scripting", "shell scripts"),
    "PowerShell": ("powershell",),
    # --- data & analytics ------------------------------------------------
    "pandas": ("pandas",),
    "NumPy": ("numpy",),
    "Excel": ("excel", "pivot table", "pivot tables", "vlookup"),
    "Power BI": ("power bi", "powerbi", "power-bi", "dax", "power query"),
    "Tableau": ("tableau",),
    "Looker": ("looker", "lookml"),
    "dashboards": (
        "dashboard",
        "dashboards",
        "data visualization",
        "data visualisation",
        "visualization",
    ),
    "KPI reporting": ("kpi", "kpis", "metrics reporting"),
    "statistics": (
        "statistics",
        "statistical analysis",
        "statistical modeling",
        "statistical model",
        "hypothesis testing",
    ),
    "A/B testing": ("a/b testing", "a/b test", "ab testing", "experimentation"),
    "time series": ("time series", "time-series", "forecasting"),
    "causal inference": ("causal inference",),
    "data analysis": ("data analysis", "data analytics", "analytics"),
    "data modeling": (
        "data modeling",
        "data modelling",
        "dimensional modeling",
        "dimensional model",
        "semantic model",
        "star schema",
    ),
    "data warehouse": ("data warehouse", "data warehousing"),
    "data lake": ("data lake", "lakehouse"),
    "data quality": ("data quality", "data validation", "data integrity"),
    "data governance": ("data governance", "data dictionary", "data catalog"),
    "ETL": ("etl", "elt", "data pipeline", "data pipelines", "data ingestion"),
    "dbt": ("dbt",),
    "Airflow": ("airflow",),
    "Spark": ("spark", "pyspark"),
    "Kafka": ("kafka",),
    "streaming": ("streaming", "stream processing", "real-time data"),
    "Snowflake": ("snowflake",),
    "BigQuery": ("bigquery",),
    "Redshift": ("redshift",),
    "Databricks": ("databricks",),
    "MongoDB": ("mongodb", "mongo"),
    "NoSQL": ("nosql",),
    "Redis": ("redis",),
    # --- ML / AI ---------------------------------------------------------
    "machine learning": ("machine learning", "ml models", "ml pipelines", "ml pipeline"),
    "deep learning": ("deep learning", "neural network", "neural networks", "cnn", "rnn"),
    "PyTorch": ("pytorch",),
    "TensorFlow": ("tensorflow", "keras"),
    "scikit-learn": ("scikit-learn", "sklearn", "sci-kit learn"),
    "NLP": ("nlp", "natural language processing"),
    "LLMs": (
        "llm",
        "llms",
        "large language model",
        "large language models",
        "generative ai",
        "genai",
    ),
    "feature engineering": ("feature engineering",),
    "model explainability": ("shap", "explainability", "model interpretability", "explainable ai"),
    "anomaly detection": ("anomaly detection",),
    # --- engineering & cloud --------------------------------------------
    "REST APIs": ("rest api", "rest apis", "restful", "api development"),
    "FastAPI": ("fastapi",),
    "Django": ("django",),
    "Flask": ("flask",),
    "React": ("react", "react.js", "reactjs"),
    "Node.js": ("node.js", "nodejs"),
    "Docker": ("docker", "containers", "containerization"),
    "Kubernetes": ("kubernetes", "k8s"),
    "Terraform": ("terraform",),
    "AWS": ("aws", "amazon web services"),
    "GCP": ("gcp", "google cloud"),
    "Azure": ("azure",),
    "Linux": ("linux", "unix"),
    "Git": ("git", "github", "gitlab", "version control"),
    "CI/CD": ("ci/cd", "continuous integration", "continuous delivery"),
    "testing": ("pytest", "unit testing", "unit tests", "test automation"),
    # --- security & GRC --------------------------------------------------
    "cybersecurity": ("cybersecurity", "cyber security", "information security", "infosec"),
    "vulnerability management": ("vulnerability management", "vulnerability", "cve", "cvss"),
    "SIEM": ("siem", "splunk", "security monitoring"),
    "incident response": ("incident response",),
    "penetration testing": ("penetration testing", "penetration test", "pentest", "pentesting"),
    "threat intelligence": ("threat intelligence", "threat intel"),
    "NIST": ("nist",),
    "MITRE ATT&CK": ("mitre att&ck", "mitre"),
    "ISO 27001": ("iso 27001", "iso/iec 27001"),
    "SOC 2": ("soc 2", "soc2"),
    "GRC": ("grc", "governance, risk", "compliance", "audit", "audits"),
    "risk management": ("risk management", "risk assessment", "risk assessments"),
    "OWASP": ("owasp",),
    "Active Directory": ("active directory",),
    "Security+": ("security+", "comptia security"),
    # --- delivery & business --------------------------------------------
    "Agile": ("agile", "scrum", "sprint", "sprints", "kanban"),
    "Jira": ("jira",),
    "project management": ("project management", "program management", "pmo"),
    "stakeholder management": (
        "stakeholder management",
        "stakeholders",
        "cross-functional",
        "business partners",
    ),
    "requirements gathering": (
        "requirements gathering",
        "business requirements",
        "requirements workshops",
    ),
    "communication": ("communication skills", "written and verbal", "verbal and written"),
}


def _pattern(phrase: str) -> re.Pattern[str]:
    # Word-ish boundaries that also work for phrases containing symbols
    # ("c++", "a/b testing", "node.js"): no letter/digit directly either side.
    return re.compile(r"(?<![a-z0-9])" + re.escape(phrase.lower()) + r"(?![a-z0-9])")


@lru_cache(maxsize=4096)
def _compiled(phrase: str) -> re.Pattern[str]:
    return _pattern(phrase)


def contains_phrase(text: str, phrase: str) -> bool:
    """True when ``phrase`` occurs in ``text`` as a whole word/phrase."""
    if not text or not phrase:
        return False
    return bool(_compiled(phrase.lower()).search(text.lower()))


def count_phrase(text: str, phrase: str) -> int:
    if not text or not phrase:
        return 0
    return len(_compiled(phrase.lower()).findall(text.lower()))


# Canonical names that are ordinary English words or single letters; they
# are only ever matched through their (unambiguous) aliases.
_UNSAFE_NAMES = frozenset({"go", "r", "c"})


def aliases_for(canonical: str) -> tuple[str, ...]:
    """Every phrase that means ``canonical``, including the name itself when
    the name is safe to match on its own."""
    own = () if canonical.lower() in _UNSAFE_NAMES else (canonical.lower(),)
    return tuple(dict.fromkeys((*own, *SKILLS.get(canonical, ()))))


def canonicalize(skill: str) -> str | None:
    """Map a free-text skill ("Postgres", "powerbi") to its canonical name."""
    s = (skill or "").strip().lower()
    if not s:
        return None
    for canon, aliases in SKILLS.items():
        if s == canon.lower() or s in aliases:
            return canon
    return None


def find_terms(text: str, vocabulary: Iterable[str] | None = None) -> dict[str, int]:
    """Count canonical skills mentioned in ``text``.

    ``vocabulary`` limits the search to those canonical names (default: all).
    Returns ``{canonical: hit_count}`` for terms with at least one hit.
    """
    names = list(vocabulary) if vocabulary is not None else list(SKILLS)
    hits: dict[str, int] = {}
    for canon in names:
        n = sum(count_phrase(text, a) for a in aliases_for(canon))
        if n:
            hits[canon] = n
    return hits
