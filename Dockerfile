FROM python:3.13-slim

# los logs salen al momento, sin búfer (los lee Render)
ENV PYTHONUNBUFFERED=1

WORKDIR /app

# primero lo que cambia poco, para aprovechar la caché; el README lo pide el pyproject
COPY pyproject.toml README.md ./
COPY src/ src/
RUN pip install --no-cache-dir .

# sin privilegios de root
RUN useradd --create-home app
USER app

EXPOSE 8000
CMD ["epf-web"]
