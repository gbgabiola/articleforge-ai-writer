# Imports
import os
import time
import json
import requests
from pymongo import MongoClient
from dotenv import load_dotenv

load_dotenv()

ARTICLEFORGE_API_KEY = os.getenv("ARTICLEFORGE_API_KEY")
WORKBENCH_API = os.getenv("WORKBENCH_API")
DB_CLIENT = MongoClient(os.getenv("MONGO_URI"))
SUPERDESK_DB = DB_CLIENT[os.getenv("MONGO_DBNAME")]
DESK_NAME = os.getenv("DESK_NAME")
STAGE_NAME = os.getenv("STAGE_NAME")


def login_db():
    superdesk_username = os.getenv("SUPERDESK_USERNAME")
    superdesk_password = os.getenv("SUPERDESK_PASSWORD")
    data = {"username": superdesk_username, "password": superdesk_password}
    headers = {"Content-Type": "application/json"}
    response = requests.post(
        "/".join([WORKBENCH_API, "auth_db"]), json=data, headers=headers).json()
    return response["token"], response["user"]


def lambda_handler(event, context):
    # Login and get token and user
    workbench_token, workbench_user = login_db()

    # Get trends data
    trends_data = requests.get(
        "https://qa-content-api.abs-cbn.com/QA/trending/googleTrends", timeout=5)

    # Prepare create template
    create_template = json.load(open("create_template.json", "r"))

    # Send post request to initiate article generation
    response = requests.post(
        f"https://af.articleforge.com/api/initiate_article", params=event)
    ref_key = response.json().get("ref_key")

    # Check the progress of the article generation
    while True:
        response = requests.post(
            f"https://af.articleforge.com/api/get_api_progress?key={ARTICLEFORGE_API_KEY}&ref_key={ref_key}").json()
        if response and response.get("api_status") == 201:
            break
        elif response and response.get("status") == "Fail":
            break
        else:
            time.sleep(1)

    # Get the generated article
    article = requests.post(
        f"https://af.articleforge.com/api/view_article?key={ARTICLEFORGE_API_KEY}&article_id={ref_key}")
    generated_text = article.json().get("data")

    # Prepare headers for submission
    headers = {"Authorization": f"Bearer {workbench_token}",
               "Content-Type": "application/json"}

    # Create a string URL since requests GET cannot properly parse nested dict as params
    where = f'where={{"name": "{DESK_NAME}"}}'
    desks_url = "".join([WORKBENCH_API, "/desks", "?", where])
    desk_response = requests.get(desks_url, headers=headers).json()
    desk = desk_response["_items"][0]

    where = f'where={{"name": "{STAGE_NAME}", "desk": "{desk["_id"]}"}}'
    stages_url = "".join([WORKBENCH_API, "/stages", "?", where])
    stage_response = requests.get(stages_url, headers=headers).json()

    # Update create template with generated text
    create_template["body_html"] = generated_text
    create_template["task"]["stage"] = stage_response["_items"][0]["_id"]
    create_template["task"]["desk"] = desk_response["_items"][0]["_id"]
    create_template["task"]["user"] = workbench_user

    # Submit article to workbench
    post_response = requests.post(
        "/".join([WORKBENCH_API, "archive"]), json=create_template, headers=headers).json()
    headers["If-Match"] = post_response["_etag"]
    update = {"slugline": event['keyword']}
    patch_response = requests.patch(
        "/".join([WORKBENCH_API, "archive", post_response["_id"]]), json=update, headers=headers).json()

    return {
        'statusCode': 200,
        'body': patch_response
    }
