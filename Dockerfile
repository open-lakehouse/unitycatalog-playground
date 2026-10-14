FROM apache/spark:4.2.0-java21-python3@sha256:fc64959c04bd87b0ac686be9aaa9008b69cdb1afc695400528279c8b01f43d89

# Optional pre-release override: filename of a locally-staged wheel under
# spark/delta-override/ (e.g. delta_spark-4.4.0-py3-none-any.whl). Stage it with
# `just stage-delta <path>` and set DELTA_SPARK_WHEEL in .env. When set, this
# replaces the locked public delta-spark package after the environment installs.
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
COPY marimo-playground/requirements.lock /tmp/requirements.lock

RUN set -eux; \
    pip install --no-cache-dir --require-hashes -r /tmp/requirements.lock; \
    if [ -n "${DELTA_SPARK_WHEEL}" ]; then \
        echo "Overriding delta-spark with local wheel: ${DELTA_SPARK_WHEEL}"; \
        pip install --no-cache-dir --no-deps --force-reinstall \
            "/tmp/delta-override/${DELTA_SPARK_WHEEL}"; \
    fi

WORKDIR /opt/workspace

COPY marimo-playground/ ./marimo-playground/

EXPOSE 2718

ENTRYPOINT ["marimo", "edit", "--host", "0.0.0.0", "--port", "2718", "marimo-playground/notebooks/"]
