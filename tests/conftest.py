# tests/conftest.py
from __future__ import annotations

from typing import Tuple

import boto3
import pytest
from moto import mock_aws  # <- changed from mock_s3

from s3_manager.manager import S3Manager


@pytest.fixture
def aws_credentials(monkeypatch: pytest.MonkeyPatch) -> None:
    """
    Provide dummy AWS credentials for moto / boto3.

    This prevents boto3 from trying to use real credentials on your machine.
    """
    monkeypatch.setenv("AWS_ACCESS_KEY_ID", "testing")
    monkeypatch.setenv("AWS_SECRET_ACCESS_KEY", "testing")
    monkeypatch.setenv("AWS_SECURITY_TOKEN", "testing")
    monkeypatch.setenv("AWS_SESSION_TOKEN", "testing")
    monkeypatch.setenv("AWS_DEFAULT_REGION", "eu-central-1")


@pytest.fixture
def s3_client(aws_credentials) -> Tuple[boto3.client, str]:
    """
    Start a mocked AWS environment and return an S3 client + a created bucket name.
    """
    # mock_aws mocks all AWS services; we only use S3 here
    with mock_aws():
        region = "eu-central-1"
        client = boto3.client("s3", region_name=region)

        bucket_name = "test-bucket"
        client.create_bucket(
            Bucket=bucket_name,
            CreateBucketConfiguration={"LocationConstraint": region},
        )

        yield client, bucket_name
        # mock_aws context exits here (teardown)


@pytest.fixture
def s3_manager(s3_client) -> S3Manager:
    """
    Return an S3Manager instance bound to the mocked S3 client + test bucket.
    """
    client, bucket_name = s3_client
    return S3Manager(bucket_name=bucket_name, prefix="", s3_client=client)
