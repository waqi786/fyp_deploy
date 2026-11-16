"""Paper templates for the LaTeX Studio.

Each template uses the publisher's real class when it is installed on the compile server (TeX Live package
`texlive-publishers` provides IEEEtran, acmart, llncs, elsarticle, apa7 …). When the class is missing, the same file
falls back to a close preview layout built on `article`, and the compile result says so — the document always
compiles, and the exact class is used as soon as it is installed. Converting a paper to another format swaps only
the preamble; the body (everything between \\begin{document} and \\end{document}) is kept.
"""

from __future__ import annotations

import re

# Commands some classes define; provided as no-ops so a body written for one format compiles in another.
_COMPAT = r"""\providecommand{\institute}[1]{}
\providecommand{\email}[1]{\texttt{#1}}
\providecommand{\orcid}[1]{}
\providecommand{\keywords}[1]{\par\noindent\textbf{Keywords:} #1}
\usepackage{graphicx}
\usepackage{amsmath,amssymb}
\usepackage{booktabs}
\usepackage[hidelinks]{hyperref}
\graphicspath{{images/}{./}}
"""

TEMPLATES: dict[str, dict[str, str]] = {
    "article": {
        "name": "Article (generic)",
        "class": "article",
        "preamble": r"""\documentclass[11pt]{article}
\usepackage[margin=1in]{geometry}
\usepackage[utf8]{inputenc}
\usepackage[T1]{fontenc}
\usepackage[numbers]{natbib}
""" + _COMPAT,
        "bibstyle": "plainnat",
    },
    "ieee": {
        "name": "IEEE conference",
        "class": "IEEEtran",
        "preamble": r"""\IfFileExists{IEEEtran.cls}{\documentclass[conference]{IEEEtran}}{\documentclass[10pt,twocolumn]{article}\usepackage[margin=0.7in,columnsep=0.25in]{geometry}\usepackage{times}}
\usepackage{cite}
""" + _COMPAT,
        "bibstyle": "IEEEtran",
    },
    "acm": {
        "name": "ACM (sigconf)",
        "class": "acmart",
        "preamble": r"""\IfFileExists{acmart.cls}{\documentclass[sigconf,nonacm]{acmart}}{\documentclass[9pt,twocolumn]{article}\usepackage[margin=0.75in,columnsep=0.33in]{geometry}\usepackage[numbers]{natbib}}
""" + _COMPAT,
        "bibstyle": "ACM-Reference-Format",
    },
    "springer": {
        "name": "Springer LNCS",
        "class": "llncs",
        "preamble": r"""\IfFileExists{llncs.cls}{\documentclass[runningheads]{llncs}}{\documentclass[10pt]{article}\usepackage[paperwidth=152mm,paperheight=235mm,margin=20mm]{geometry}}
""" + _COMPAT,
        "bibstyle": "splncs04",
    },
    "elsevier": {
        "name": "Elsevier journal",
        "class": "elsarticle",
        "preamble": r"""\IfFileExists{elsarticle.cls}{\documentclass[preprint,12pt]{elsarticle}}{\documentclass[12pt]{article}\usepackage[margin=1in]{geometry}\usepackage[numbers]{natbib}}
""" + _COMPAT,
        "bibstyle": "elsarticle-num",
    },
    "apa": {
        "name": "APA 7 (student paper)",
        "class": "apa7",
        "preamble": r"""\IfFileExists{apa7.cls}{\documentclass[stu,12pt]{apa7}}{\documentclass[12pt]{article}\usepackage[margin=1in]{geometry}\usepackage{setspace}\doublespacing\usepackage{natbib}}
""" + _COMPAT,
        "bibstyle": "apalike",
    },
    "thesis": {
        "name": "Thesis / report",
        "class": "report",
        "preamble": r"""\documentclass[12pt,oneside]{report}
\usepackage[margin=1in,left=1.25in]{geometry}
\usepackage{setspace}\onehalfspacing
\usepackage[numbers]{natbib}
""" + _COMPAT,
        "bibstyle": "plainnat",
    },
    "beamer": {
        "name": "Presentation slides",
        "class": "beamer",
        "preamble": r"""\documentclass[aspectratio=169]{beamer}
\usetheme{Madrid}
\usepackage[numbers]{natbib}
\providecommand{\institute}[1]{}
\providecommand{\keywords}[1]{}
\usepackage{booktabs}
\graphicspath{{images/}{./}}
""",
        "bibstyle": "plainnat",
    },
}

STARTER_BODY = r"""\title{Your paper title}
\author{Your Name}
\date{\today}

\begin{document}
\maketitle

\begin{abstract}
One paragraph that states the problem, the method, the main result and why it matters.
\end{abstract}

\section{Introduction}
Write your introduction here. Cite related work like this~\cite{example2024}.

\section{Method}
An equation:
\begin{equation}
  \hat{y} = \sigma(Wx + b)
\end{equation}

% Upload an image in the Files panel, then:
% \begin{figure}[t]
%   \centering
%   \includegraphics[width=0.9\linewidth]{figure1.png}
%   \caption{What the figure shows.}
%   \label{fig:overview}
% \end{figure}

\section{Results}
\begin{table}[t]
  \centering
  \caption{Main results.}
  \begin{tabular}{lcc}
    \toprule
    Method & Accuracy & F1 \\
    \midrule
    Baseline & 81.2 & 79.5 \\
    Ours & \textbf{86.9} & \textbf{85.1} \\
    \bottomrule
  \end{tabular}
\end{table}

\section{Conclusion}
Summarize the contribution and the limitations.

\bibliographystyle{BIBSTYLE}
\bibliography{references}
\end{document}
"""

STARTER_SLIDES = r"""\title{Your talk title}
\author{Your Name}
\date{\today}

\begin{document}
\frame{\titlepage}

\begin{frame}{Motivation}
  \begin{itemize}
    \item The problem in one line
    \item Why it matters~\cite{example2024}
  \end{itemize}
\end{frame}

\begin{frame}{Results}
  \centering
  \begin{tabular}{lc}
    \toprule
    Method & Accuracy \\
    \midrule
    Ours & 86.9 \\
    \bottomrule
  \end{tabular}
\end{frame}

\begin{frame}{References}
  \bibliographystyle{BIBSTYLE}
  \bibliography{references}
\end{frame}
\end{document}
"""

STARTER_BIB = """@article{example2024,
  title   = {An example reference},
  author  = {Author, Ada and Researcher, Ben},
  journal = {Journal of Examples},
  year    = {2024},
  volume  = {1},
  pages   = {1--10},
  doi     = {10.1000/example}
}
"""

_DOC_START = re.compile(r"\\begin\{document\}")
_BIBSTYLE = re.compile(r"\\bibliographystyle\{[^}]*\}")


def template_list() -> list[dict[str, str]]:
    return [{"id": key, "name": value["name"], "class": value["class"]} for key, value in TEMPLATES.items()]


def starter(template: str) -> str:
    spec = TEMPLATES[template]
    body = STARTER_SLIDES if template == "beamer" else STARTER_BODY
    return spec["preamble"] + "\n" + body.replace("BIBSTYLE", _fallback_bibstyle(template))


def _fallback_bibstyle(template: str) -> str:
    """The class's own .bst when the class is installed is chosen at compile time; plainnat always works."""
    return "plainnat" if template in {"acm", "springer", "elsevier"} else TEMPLATES[template]["bibstyle"]


def split(source: str) -> tuple[str, str]:
    """(preamble, rest) where rest starts with the title block or \\begin{document}."""
    title = re.search(r"^\\title\{", source, re.M)
    start = _DOC_START.search(source)
    cut = min(position for position in [title.start() if title else None, start.start() if start else None] if position is not None) if (title or start) else 0
    return source[:cut], source[cut:]


def convert(source: str, target: str) -> str:
    """Swap the preamble for another template's, keep the body and title block; adjust the bibliography style."""
    if target not in TEMPLATES:
        raise KeyError(target)
    slides = "\\begin{frame}" in source or "\\frame{" in source
    if (target == "beamer") != slides:
        raise ValueError("slides_and_papers_differ")  # a paper body is not a slide deck and vice versa
    preamble, rest = split(source)
    # Keep the user's own \usepackage / \newcommand lines that the target template does not already load.
    target_preamble = TEMPLATES[target]["preamble"]
    keep = []
    for line in preamble.splitlines():
        stripped = line.strip()
        if stripped.startswith(("\\newcommand", "\\renewcommand", "\\DeclareMathOperator", "\\def\\")) or (
            stripped.startswith("\\usepackage") and stripped not in target_preamble and "geometry" not in stripped and "IfFileExists" not in stripped
            and not any(name in stripped for name in ("inputenc", "fontenc", "natbib", "cite}", "times", "setspace"))
        ):
            keep.append(line)
    new_preamble = target_preamble + ("% kept from your previous preamble\n" + "\n".join(keep) + "\n" if keep else "")
    rest = _BIBSTYLE.sub(lambda _: "\\bibliographystyle{" + _fallback_bibstyle(target) + "}", rest)
    return new_preamble + "\n" + rest


def detect(source: str) -> str:
    for key, spec in TEMPLATES.items():
        if spec["class"] != "article" and re.search(r"\{" + re.escape(spec["class"]) + r"\}", source[:2000]):
            return key
    return "article"
