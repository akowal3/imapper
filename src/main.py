#!/usr/bin/env python
from imap_tools import MailBox, AND, MailAttachment
import os
import yaml
import pikepdf
from munch import DefaultMunch
import logging as log
from time import sleep
import shutil
import requests

def read_config():
    with open('/app/config.yaml', 'r') as configFile:
        config = yaml.safe_load(configFile)
        config = DefaultMunch.fromDict(config)
        for d in config.directories.values():
            if(not os.path.exists(d)):
                os.mkdir(d)
        log.basicConfig(level=config.log.level.upper(), format='%(asctime)s %(levelname)s: %(message)s') 
        return config
    
# global config
config = read_config()

# save attachments to unprocessed directory
def save_attachment(attachment: MailAttachment):

    def sanitize_filename(rawFileName: str):
        filename = rawFileName
        for bad_char in ["/", "*", ":", "<", ">", "|", '"', "’", "–", " "]:
            filename = filename.replace(bad_char, "_")
        return filename

    filename = sanitize_filename(attachment.filename)
    path = f"{config.directories.unprocessed}/{filename}"
    with open(path, 'wb') as f:
        log.info(f"Trying to save {attachment.filename} into {config.directories.unprocessed}/{filename}")
        f.write(attachment.payload)
    return path
    

# save successfully processed attachments to processed directory and remove from unprocessed. Failed attachments go to failed directory
def process_attachments():

    def process_pdf(filename, inputPath: str, outputPath: str, password: str):
        try:
            with pikepdf.open(inputPath, password = password) as unlockedPdf:
                if(password):
                    log.info(f"{filename} unlocked with {password}")
                else:
                    log.info(f"{filename} is not password protected. Success.")
                unlockedPdf.save(outputPath)
            os.remove(inputPath)
            return True                    
        except pikepdf.PasswordError as e:
            return False

    for f in os.listdir(config.directories.unprocessed):
        inputPath = f"{config.directories.unprocessed}/{f}"
        outputPath = f"{config.directories.success}/{f}"
        failedPath = f"{config.directories.failed}/{f}"

        if str(f).lower().endswith('.pdf'):
            unlocked = False
            for p in ['', *config.passwords]:
                unlocked = process_pdf(f, inputPath, outputPath, p)
                if unlocked:
                    break
            if not unlocked:
                log.warn(f"File {inputPath} was not processed. Moving to {config.directories.failed}")
                shutil.move(inputPath, failedPath)
                os.chmod(failedPath, 0o0777)
                continue
        else:
            shutil.move(inputPath, outputPath)
        os.chmod(outputPath, 0o0777)

# log in to imap, fetch new messages with attachments and save them for processing         
def fetch_attachments():
    log.info(f"Starting to pull new messages from {config.imap.url}")
    with MailBox(config.imap.url).login(config.imap.username, config.imap.password, config.imap.folder.attachments) as mailbox:
        mails = mailbox.fetch(
            criteria=AND(seen=False),
            limit=config.imap.batchSize,
            mark_seen=False,
        )
        for i, msg in enumerate(mails):
            log.info(f"Processing {msg.subject} from {msg.from_}")
            if len(msg.attachments) == 0:
                log.info(f"Received message without attachment. Title: {msg.subject}")
                continue
            for att in msg.attachments:
                save_attachment(att)

            mailbox.delete(msg.uid)

# send status to uptime kuma
def monitor(status: str):
    if(config.uptime.monitor):
        requests.get(f"{config.uptime.endpoint}?status={status}")

if __name__ == "__main__":
    while True:
        try:
            fetch_attachments()
            process_attachments()
            monitor("up")
        except Exception as e:
            log.error('Failed to process', e)
            monitor("down")
        sleep(config.loop.interval)