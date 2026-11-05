"""Local mock-only diagnostic; no real AWS and no datumoj import."""
import json
import threading
from concurrent.futures import ThreadPoolExecutor
from unittest.mock import patch
import boto3, botocore, moto
from botocore.exceptions import ClientError
from moto import mock_aws
from moto.s3.responses import S3Response

result = {'moto': moto.__version__, 'boto3': boto3.__version__, 'botocore': botocore.__version__}
with mock_aws():
    client = boto3.client('s3', region_name='us-east-1', aws_access_key_id='testing', aws_secret_access_key='testing')
    client.create_bucket(Bucket='synthetic-moto-race-bucket')
    def put(key, body):
        try:
            r = client.put_object(Bucket='synthetic-moto-race-bucket', Key=key, Body=body, IfNoneMatch='*')
            return {'body': body.decode(), 'status': r['ResponseMetadata']['HTTPStatusCode'], 'etag': r['ETag']}
        except ClientError as exc:
            return {'body': body.decode(), 'status': exc.response['ResponseMetadata']['HTTPStatusCode'], 'code': exc.response['Error']['Code']}
    result['serial_control'] = [put('serial', b'writer-a'), put('serial', b'writer-b')]
    original = S3Response._get_checksum
    barrier = threading.Barrier(2)
    def after_condition_before_write(self, *a, **kw):
        # This original method is reached only after the If-None-Match check.
        # Pause both requests here without changing condition or mutation code.
        if self.headers.get('If-None-Match') == '*':
            barrier.wait(timeout=5)
        return original(self, *a, **kw)
    with patch.object(S3Response, '_get_checksum', after_condition_before_write):
        with ThreadPoolExecutor(max_workers=2) as pool:
            result['forced_interleaving'] = list(pool.map(lambda body: put('concurrent', body), [b'writer-a', b'writer-b']))
    result['final_body'] = client.get_object(Bucket='synthetic-moto-race-bucket', Key='concurrent')['Body'].read().decode()
    client.close()
print(json.dumps(result, indent=2))
