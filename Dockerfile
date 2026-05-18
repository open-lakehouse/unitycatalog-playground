FROM apache/spark:4.1.1-java21-python3

ARG PIP_INDEX_URL
ENV PIP_INDEX_URL=$PIP_INDEX_URL

USER root

RUN pip install --no-cache-dir \
    "delta-spark==4.2.0" \
    "marimo[recommended]>=0.23.1" \
    "nbconvert>=7.17.0" \
    "numpy>=2.2.6" \
    "playwright>=1.58.0" \
    "pyspark==4.1.1"

RUN playwright install --with-deps chromium

WORKDIR /opt/workspace

COPY marimo-playground/ ./marimo-playground/

EXPOSE 2718

ENTRYPOINT ["marimo", "edit", "--host", "0.0.0.0", "--port", "2718", "marimo-playground/notebooks/unitycatalog-delta.py"]
