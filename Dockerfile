FROM python:3.12-slim

WORKDIR /sketch

RUN apt-get update && apt-get install build-essential -y

COPY requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt

COPY ./src .

CMD [ "python", "./sketch.py" ]