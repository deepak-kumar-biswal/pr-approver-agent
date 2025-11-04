"""
One-time helper to mark a bundle hash as approved in DDB.

Usage:
  python tools/approve_bundle.py <table-name> <hash>
"""
import sys
import boto3


def main():
    if len(sys.argv) < 3:
        print("usage: approve_bundle.py <table> <hash>")
        sys.exit(2)
    table, h = sys.argv[1], sys.argv[2]
    ddb = boto3.client("dynamodb")
    pk = f"CONFIG#BUNDLE#{h}"
    ddb.put_item(
        TableName=table,
        Item={
            "pk": {"S": pk},
            "approved": {"BOOL": True},
        },
    )
    print("approved", h)


if __name__ == "__main__":
    main()