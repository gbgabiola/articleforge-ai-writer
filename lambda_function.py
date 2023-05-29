# Imports
import os
import time
import json
import streamlit as st
from dotenv import load_dotenv
import requests
import pandas as pd
from pymongo import MongoClient

load_dotenv()

def login_db():
    superdesk_username = os.getenv("SUPERDESK_USERNAME")
    superdesk_password = os.getenv("SUPERDESK_PASSWORD")
    data = { "username": superdesk_username, "password": superdesk_password }
    headers = { "Content-Type": "application/json" }
    response = requests.post("/".join([WORKBENCH_API, "auth_db"]), json=data, headers=headers).json()
    st.write(response)
    st.session_state["workbench_token"] = response["token"]
    st.session_state["workbench_user"] = response["user"]

trends_data = requests.get("https://qa-content-api.abs-cbn.com/QA/trending/googleTrends", timeout=5)

db_client = MongoClient(os.getenv("MONGO_URI"))
superdesk_db = db_client[os.getenv("MONGO_DBNAME")]
create_template = json.load(open("create_template.json", "r"))
desk_name = os.getenv("DESK_NAME")
stage_name = os.getenv("STAGE_NAME")

ARTICLEFORGE_API_KEY = os.getenv("ARTICLEFORGE_API_KEY")
WORKBENCH_API= os.getenv("WORKBENCH_API")

st.title("🤖 POC AI Writer (ArticleForge)")

st.write("A Proof-Of-Concept Web App for Writing Articles using Article Forge API")

st.write("## Trending Topics")
st.write("### Google Trends")
# st.write(trends_data)
pd.set_option("display.max_rows", None,)
st.table(pd.DataFrame.from_dict(trends_data.json()))

text_input = st.text_area("Paste your keywords here (Space separated): ")
col1, col2 = st.columns(2)
length_list = ["short", "medium", "long", "longer"]
length = col1.selectbox("Select Length", options=length_list, index=length_list.index("short"), help="Short: 250 words, Medium: 500 words, Long: 750 words, Longer: 1000 words approx.")
image_probability = col2.slider("Probability of Adding image", min_value=0.0, max_value=1.0, value=0.0, step=0.1)
video_probability = col2.slider("Probability of Adding video", min_value=0.0, max_value=1.0, value=0.0, step=0.1)
excluded_topics = st.text_area("Excluded topics (Comma separated): ")
instructions = st.text_area("Instructions (No URLs; 500 char limit): ", max_chars=500)
query_params = {
    "key": ARTICLEFORGE_API_KEY,
    "keyword": text_input,
    "length": length,
    "excluded_topics": excluded_topics,
    "instructions": instructions,
    "image": image_probability,
    "video": video_probability
}

is_clicked = st.button("Generate Article")

response = None
if is_clicked and text_input:
    response = requests.post(f"https://af.articleforge.com/api/initiate_article", params=query_params)
    st.write(response.json())

    if 'response' not in st.session_state:
        st.session_state['response'] = response.json()

    ref_key = response.json().get("ref_key")

    if 'ref_key' not in st.session_state:
        st.session_state['ref_key'] = ref_key

    if ref_key != st.session_state['ref_key']:
        st.session_state['ref_key'] = ref_key

# ref_key = st.text_input("Paste in your Ref Key here to Show Progress: ")

    if ref_key:
        progress_bar = st.progress(0, text="Article Generation Progress")
        while True:
            response = requests.post(f"https://af.articleforge.com/api/get_api_progress?key={ARTICLEFORGE_API_KEY}&ref_key={ref_key}").json()
            if response and response.get("api_status") == 201:
                st.write(f"Article Generated for Ref Key: {ref_key}")
                progress_bar.progress(100)
                break
            elif response and response.get("api_status") == 200:
                progress_bar.progress(response.get("progress"))
                time.sleep(1)
            elif response and response.get("status") == "Fail":
                st.write("Article Generation Failed!")
                st.write(response.get("error_message"))
                break
            else:
                time.sleep(1)

get_article = st.button("Get Article")

generated_text = None
if get_article:
    ref_key = st.session_state['ref_key']
    article = requests.post(f"https://af.articleforge.com/api/view_article?key={ARTICLEFORGE_API_KEY}&article_id={ref_key}")
    st.write(article.json())
    generated_text = article.json().get("data")
    if 'generated_text' not in st.session_state:
        st.session_state['generated_text'] = generated_text

    if generated_text != st.session_state['generated_text']:
        st.session_state['generated_text'] = generated_text

submit_article = st.button("Submit Article to Workbench")

if submit_article:
    if'generated_text' not in st.session_state:
        st.write("Please generate an article first!")
        st.stop()

    generated_text = st.session_state['generated_text']
    if "workbench_token" not in st.session_state:
        login_db()

    st.write(st.session_state["workbench_token"])

    headers = {"Authorization": f"Bearer {st.session_state['workbench_token']}", "Content-Type": "application/json"}

    # Create a string URL since requests GET cannot properly parse nested dict as params
    where = f'where={{"name": "{desk_name}"}}'
    desks_url = "".join([WORKBENCH_API, "/desks", "?", where])
    desk_response = requests.get(desks_url, headers=headers).json()
    desk = desk_response["_items"][0]

    where = f'where={{"name": "{stage_name}", "desk": "{desk["_id"]}"}}'
    stages_url = "".join([WORKBENCH_API, "/stages", "?", where])
    stage_response = requests.get(stages_url, headers=headers).json()

    create_template["body_html"] = generated_text

    create_template["task"]["stage"] = stage_response["_items"][0]["_id"]
    create_template["task"]["desk"] = desk_response["_items"][0]["_id"]
    create_template["task"]["user"] = st.session_state["workbench_user"]
    # st.write(create_template)

    post_response = requests.post("/".join([WORKBENCH_API, "archive"]), json=create_template, headers=headers).json()

    # st.write(post_response)
    headers["If-Match"] = post_response["_etag"]
    update = {"slugline": text_input}
    patch_response = requests.patch("/".join([WORKBENCH_API, "archive", post_response["_id"]]), json=update, headers=headers).json()
    st.write(patch_response)


# def lambda_hander(event, context):
# def actual_handler(event):
# def actual_handler(event):
