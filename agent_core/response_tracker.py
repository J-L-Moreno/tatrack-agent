import boto3
from botocore.exceptions import ClientError

from config import config


def update_response(response_id: str | None, status: str, response: str) -> None:
    """Update the API's pending response record. Streaming and reminder runs have no response_id."""
    if not response_id or not config.dynamodb_table_name:
        return
    try:
        dynamodb = boto3.resource("dynamodb", region_name=config.aws_region)
        table = dynamodb.Table(config.dynamodb_table_name)
        table.update_item(
            Key={"id": response_id},
            UpdateExpression="SET #s = :s, #r = :r",
            ConditionExpression="attribute_exists(id)",
            ExpressionAttributeNames={"#s": "status", "#r": "response"},
            ExpressionAttributeValues={":s": status, ":r": response},
        )
    except ClientError as e:
        error_code = e.response.get("Error", {}).get("Code", "Unknown")
        print(f"[DynamoDB] ClientError updating response {response_id}: {error_code} - {e}")
    except Exception as e:
        print(f"[DynamoDB] Error updating response: {e}")
