FROM python:3-alpine

RUN pip install pikepdf imap-tools requests pyyaml munch

RUN mkdir /app

ADD src/main.py /app

CMD [ "python", "/app/main.py" ]
