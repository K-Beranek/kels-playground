# python:3.12-slim-bookworm, not the floating python:3.12-slim tag -- pinned to the Debian release
# name on purpose, since the ODBC driver install below fetches a Debian-12-specific package from
# Microsoft's repo. If the floating tag ever moves to a newer Debian release, this Dockerfile
# would silently start pointing a "debian/12" package at a different OS underneath it.
FROM python:3.12-slim-bookworm

# Installs the Microsoft ODBC Driver 18 for SQL Server, the one piece pyodbc needs that pip alone
# can't provide. Unlike telemetry-event-generator (which runs natively on Karel's own Windows
# machine, where the driver is a one-time manual install -- see that component's README), this
# component only ever runs inside this image, so the driver install belongs here, in version
# control, rather than as a README instruction someone has to remember to repeat.
# Source: Microsoft's own current instructions for Debian 12 (bookworm) --
# https://learn.microsoft.com/en-us/sql/connect/odbc/linux-mac/installing-the-microsoft-odbc-driver-for-sql-server
RUN apt-get update \
    && apt-get install -y --no-install-recommends curl gnupg apt-transport-https \
    && curl -sSL -O https://packages.microsoft.com/config/debian/12/packages-microsoft-prod.deb \
    && dpkg -i packages-microsoft-prod.deb \
    && rm packages-microsoft-prod.deb \
    && apt-get update \
    && ACCEPT_EULA=Y apt-get install -y --no-install-recommends msodbcsql18 unixodbc-dev \
    && apt-get purge -y --auto-remove curl gnupg apt-transport-https \
    && apt-get clean \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY consume_telemetry_events.py .

# config/ is deliberately NOT copied into the image -- config/config.json holds a real password
# and must never be baked into an image layer (an image is easy to copy/push/inspect, unlike a
# gitignored file on disk). It's bind-mounted read-only instead; see docker-compose.yml.
CMD ["python", "consume_telemetry_events.py"]
