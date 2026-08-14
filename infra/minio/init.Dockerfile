FROM python@sha256:8fef26df932191825664e4957ff488c96dfe64918327634a357a55facbc994d3
WORKDIR /app
COPY requirements.lock /app/requirements.lock
RUN pip install --require-hashes -r /app/requirements.lock
COPY create-bucket.py /app/create-bucket.py
ENTRYPOINT ["python", "/app/create-bucket.py"]
