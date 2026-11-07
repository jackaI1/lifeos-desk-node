FROM python:3.12.8-slim-bookworm
WORKDIR /app
COPY networking/requirements.txt /tmp/requirements.txt
RUN pip install --no-cache-dir -r /tmp/requirements.txt
COPY networking/*.py /app/networking/
COPY firmware/tools/desk_api.py /app/firmware/tools/desk_api.py
USER 65534:65534
ENTRYPOINT ["python", "-m", "networking.mqtt"]
