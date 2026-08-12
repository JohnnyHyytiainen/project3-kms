# S3 client script
# Kommentarer: Svenska
# Kod: Engelska
# Tunn wrapper runt Boto3 för att prata med S3 (LocalStack i dev miljö, riktig AWS S3 i produktion)
# Modulen känner endast till hur man pratar med S3 rent tekniskt.
# Den vet ingenting om course_tag, filtypes eller postgres, den logiken hör hemma i ingestion/ingest.py

import boto3
from botocore.exceptions import ClientError

from kms.config import settings


# Funktion för min Boto3 konfiguration, är det boto3 relaterat så sker det i denna funktion.
def get_s3_client():
    """
    Creates a Boto3 S3-client configured for LocalStack.

    The `endpoint_url` is the important difference compared to a real AWS client.
    Without it, boto3 would attempt to connect to actual AWS servers. With it,
    all calls are redirected to the LocalStack container instead.

    The `aws_access_key_id` and `aws_secret_access_key` do NOT need to be valid
    AWS keys. LocalStack does not validate them against an account.
    However, boto3's internal signing process (SigV4) requires SOME string value to be present,
    otherwise, an error is raised before the request is even sent.
    """
    return boto3.client(
        "s3",
        endpoint_url=settings.AWS_ENDPOINT_URL,
        aws_access_key_id=settings.AWS_ACCESS_KEY_ID,
        aws_secret_access_key=settings.AWS_SECRET_ACCESS_KEY,
        region_name="us-east-1",  # LocalStack bryr sig inte om regionen, kodar explicit in iaf, för läsbarheten
    )


# Funktion för min S3 bucket, säkerställer att den FINNS. LocalStack startar tom varje gång
# OM inte volymen redan har data. Säkerställer idempotens.
def ensure_bucket_exists(client, bucket_name: str) -> None:
    """
    Creates the S3 bucket if it doesnt already exist.

    head_bucket is a 'does it exist?' call with no side effects.
    If the response is 404 then bucket does not exist and it gets created.
    If other errors(403 Forbidden etc) are propogated they signify something other than 'does not exist'
    and should never be suppressed in an 'except' clause.
    """
    try:
        client.head_bucket(Bucket=bucket_name)
    except ClientError as e:
        error_code = e.response["Error"]["Code"]
        if error_code == "404":
            client.create_bucket(Bucket=bucket_name)
        else:
            raise


# Funktion för att ladda upp lokal fil till min bucket
def upload_file(client, local_path: str, bucket_name: str, key: str) -> None:
    """
    Uploads a local file to S3 under a given key.

    upload_file instead of put_object is a deliberate.
    boto3 automatically handles multipart uploads for large files with this method.

    put_object is lower-level: it requires reading the entire file into
    memory, which becomes a problem as the collection of PDFs and transcripts grows.
    """
    client.upload_file(local_path, bucket_name, key)


# Funktion för att ladda ner filer ut min S3-Bucket till disk LOKALT
def download_file(client, bucket_name: str, key: str, local_path: str) -> None:
    """
    Function made to download ONE object from S3-bucket to local file path.
    Mirror image of upload_file function on purpose. It does the same thing but
    in reverse. Source first, destination last.

    Download_file instead of get_object, same reason upload_file was chosen over using
    put_object: Boto3 STREAMS IT, a large PDF never has to sit in RAM in one piece.

    Caller decides where the file lands and is responsible for cleaning it up.

    Module knows how to talk with S3 and NOTHING ELSE.
    """
    client.download_file(bucket_name, key, local_path)
