FROM apache/spark:4.2.0-java21-python3

ARG PYSPARK_VERSION=4.2.0
ARG DELTA_SPARK_VERSION=4.4.0rc1.dev1
ARG MARIMO_VERSION=0.23.16

# Optional pre-release override: filename of a locally-staged wheel under
# spark/delta-override/ (e.g. delta_spark-4.4.0-py3-none-any.whl). Stage it with
# `just stage-delta <path>` and set DELTA_SPARK_WHEEL in .env. When blank the
# image installs delta-spark==${DELTA_SPARK_VERSION} from PyPI as usual.
ARG DELTA_SPARK_WHEEL=""

USER root

# Optional pip index URL override, e.g. for building behind a corporate PyPI
# proxy: --build-arg PYPI_PROXY_URL=https://pypi-proxy.your-company.com/simple/
ARG PYPI_PROXY_URL=""
ENV PYPI_PROXY_URL=${PYPI_PROXY_URL}
# pip reads PIP_INDEX_URL; map the project-facing proxy var onto it.
ENV PIP_INDEX_URL=${PYPI_PROXY_URL:-https://pypi.org/simple/}

# Staged wheels (git-ignored; usually just .gitkeep unless overriding delta-spark).
COPY spark/delta-override/ /tmp/delta-override/

RUN set -eux; \
    if [ -n "${DELTA_SPARK_WHEEL}" ]; then \
        echo "Overriding delta-spark with local wheel: ${DELTA_SPARK_WHEEL}"; \
        delta_pkg="/tmp/delta-override/${DELTA_SPARK_WHEEL}"; \
    else \
        echo "Installing delta-spark==${DELTA_SPARK_VERSION} from PyPI"; \
        delta_pkg="delta-spark==${DELTA_SPARK_VERSION}"; \
    fi; \
    pip install --no-cache-dir \
        "${delta_pkg}" \
        "marimo[recommended]>=${MARIMO_VERSION}" \
        "nbconvert>=7.17.0" \
        "numpy>=2.2.6" \
        "playwright>=1.58.0" \
        "pyspark==${PYSPARK_VERSION}"

RUN playwright install --with-deps chromium

WORKDIR /opt/workspace

COPY marimo-playground/ ./marimo-playground/

EXPOSE 2718

ENTRYPOINT ["marimo", "edit", "--host", "0.0.0.0", "--port", "2718", "marimo-playground/notebooks/unitycatalog-delta.py"]
