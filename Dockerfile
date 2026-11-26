FROM python:3.12-slim
WORKDIR /app
RUN groupadd -g 10001 dsig && useradd -u 10001 -g dsig -M dsig && mkdir -p /app/data && chown dsig:dsig /app/data
COPY --chmod=0644 *.py /app/
COPY --chmod=0644 requirements.txt /app/
RUN pip install --no-cache-dir -r requirements.txt
COPY dist /app/dist
# Normalize copied assets independently of the host checkout umask.
RUN find /app/dist -type d -exec chmod 0755 {} + && find /app/dist -type f -exec chmod 0644 {} +
USER 10001:10001
ENV PYTHONDONTWRITEBYTECODE=1 DSIG_CONTAINER=1 DSIG_DB=/app/data/requests.sqlite3
EXPOSE 8080
HEALTHCHECK --interval=30s --timeout=5s --retries=3 CMD ["python", "-c", "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8080/api/ready', timeout=3).read()"]
CMD ["python","server.py"]
