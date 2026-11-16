FROM python:3.11-slim

# Paper studio: LaTeX (pdflatex + latexmk + bibtex), the journal classes (IEEEtran, acmart, llncs, elsarticle, apa7 …)
# and pandoc for Word / HTML export. Set STUDIO_SKIP_TEX=1 at build time to leave them out (compile then reports
# "not available" and editing/downloading the LaTeX still works).
ARG STUDIO_SKIP_TEX=0
RUN if [ "$STUDIO_SKIP_TEX" != "1" ]; then \
      apt-get update && apt-get install -y --no-install-recommends \
        latexmk texlive-latex-base texlive-latex-recommended texlive-latex-extra texlive-fonts-recommended \
        texlive-publishers texlive-science texlive-bibtex-extra pandoc \
      && rm -rf /var/lib/apt/lists/*; \
    fi

WORKDIR /app
COPY pyproject.toml README.md ./
COPY app ./app
RUN pip install --no-cache-dir -e .

EXPOSE 8000
CMD ["python", "-m", "uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
