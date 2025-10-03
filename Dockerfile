FROM python:3.13-slim

WORKDIR /sketch

COPY requirements.txt ./
RUN apt-get update && apt-get install build-essential git -y --no-install-recommends && pip install --no-cache-dir -r requirements.txt && pip install --no-cache-dir -U git+https://github.com/Rapptz/discord.py && apt-get purge -y --auto-remove build-essential git && apt-get purge -y --auto-remove && apt-get autoremove -y && apt-get clean -y && rm -rf /var/lib/apt/lists/*

COPY ./src .
CMD [ "python", "./sketch.py" ]