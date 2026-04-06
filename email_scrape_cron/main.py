import email
import gzip
import io
import os
import zipfile
from typing import cast
from imaplib import IMAP4_SSL

import boto3
from botocore.exceptions import ClientError
from aws_lambda_powertools.utilities.typing import LambdaContext

mail_server = os.environ['MAIL_SERVER']
mail_port = int(os.environ['MAIL_PORT'])
mail_user = os.environ['MAIL_USER']
mail_password = os.environ['MAIL_PASSWORD']

dmarc_aggregate_reports_addr = os.environ['DMARC_AGGREGATE_REPORTS_ADDR']
s3_bucket = os.environ['S3_BUCKET']

s3 = boto3.client('s3')


def decompress(filename: str, data: bytes) -> tuple[str, bytes]:
    if filename.endswith('.xml.gz') or filename.endswith('.xml.gzip'):
        xml_name = filename.rsplit('.', 1)[0]
        return xml_name, gzip.decompress(data)
    if filename.endswith('.xml.zip'):
        with zipfile.ZipFile(io.BytesIO(data)) as zf:
            xml_name = next(n for n in zf.namelist() if n.endswith('.xml'))
            return xml_name, zf.read(xml_name)
    if filename.endswith('.zip'):
        with zipfile.ZipFile(io.BytesIO(data)) as zf:
            xml_name = next(n for n in zf.namelist() if n.endswith('.xml'))
            return xml_name, zf.read(xml_name)
    return filename, data


def upload_to_s3(key: str, data: bytes) -> bool:
    """Upload data to S3. Returns True if uploaded, False if already exists."""
    try:
        s3.head_object(Bucket=s3_bucket, Key=key)
        return False
    except ClientError as e:
        if e.response['Error']['Code'] != '404':
            raise
    s3.put_object(Bucket=s3_bucket, Key=key, Body=data, ContentType='application/xml')
    return True


def process_attachments(msg: email.message.Message) -> list[str]:
    results = []
    for part in msg.walk():
        if part.get_content_disposition() != 'attachment':
            continue
        filename = part.get_filename()
        if not filename:
            continue
        xml_name, xml_data = decompress(filename, cast(bytes, part.get_payload(decode=True)))
        uploaded = upload_to_s3(xml_name, xml_data)
        results.append(f"{xml_name} ({'uploaded' if uploaded else 'already exists'})")
    return results


def handler(event: dict, context: LambdaContext):
    with IMAP4_SSL(host=mail_server, port=mail_port) as M:
        M.login(mail_user, mail_password)
        M.select()

        typ, data = M.search(None, 'ALL')
        for num in data[0].split():
            typ, data = M.fetch(num, '(RFC822)')
            msg = email.message_from_bytes(data[0][1])

            if msg['To'] == dmarc_aggregate_reports_addr:
                results = process_attachments(msg)
                if results:
                    print(f"{msg['Subject']}: {results}")
                else:
                    print(f"{msg['Subject']}: no attachments found")

        M.close()
        M.logout()

if __name__ == '__main__':
    handler({}, LambdaContext())
