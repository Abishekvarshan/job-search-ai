from flask import Flask, request, jsonify
from flask_cors import CORS
from transformers import pipeline
import requests
from bs4 import BeautifulSoup
import re
from urllib.parse import urljoin

app = Flask(__name__)
CORS(app)

summarizer = pipeline("summarization", model="sshleifer/distilbart-cnn-12-6")

def extract_text_from_url(url):
    try:
        res = requests.get(url)
        res.raise_for_status()
        soup = BeautifulSoup(res.text, 'html.parser')
        text = soup.get_text(separator=' ', strip=True)
        return text
    except Exception as e:
        print(f"Error fetching URL {url}: {e}")
        return None

def extract_job_title_from_page(url):
    try:
        res = requests.get(url)
        res.raise_for_status()
        soup = BeautifulSoup(res.text, 'html.parser')

        title_tag = soup.find('title')
        if title_tag and title_tag.text.strip():
            return title_tag.text.strip()

        heading = soup.find(['h1', 'h2'])
        if heading and heading.text.strip():
            return heading.text.strip()

        return None
    except Exception as e:
        print(f"Error fetching title from URL {url}: {e}")
        return None

def parse_job_details(text):
    job_title = None
    department = None
    deadline = None
    exam_info = None

    title_match = re.search(r"(Station Master|Job Vacancy|Vacancies|Recruitment|Exam)", text, re.IGNORECASE)
    if title_match:
        job_title = title_match.group(0)

    if "Sri Lanka Railway" in text:
        department = "Sri Lanka Railway Department"

    dl_match = re.search(r"closing date[:\s]*([\d\-\/\.]+)", text, re.IGNORECASE)
    if dl_match:
        deadline = dl_match.group(1)

    exam_match = re.search(r"exam date[:\s]*([\d\-\/\.]+)", text, re.IGNORECASE)
    if exam_match:
        exam_info = exam_match.group(1)

    return job_title or "Job Opening", department or "N/A", deadline or "N/A", exam_info or "N/A"

def search_gazette(query):
    search_url = f"https://www.gazette.lk/?s={query.replace(' ', '+')}"
    try:
        response = requests.get(search_url)
        response.raise_for_status()
    except Exception as e:
        print(f"Error searching Gazette.lk: {e}")
        return []

    soup = BeautifulSoup(response.text, 'html.parser')
    links = [a['href'] for a in soup.select("h2.entry-title a")[:3]]
    results = []

    for link in links:
        page_text = extract_text_from_url(link)
        if not page_text:
            continue

        job_title = extract_job_title_from_page(link) or "Job Opening"
        summary = summarizer(page_text[:1024], max_length=120, min_length=30, do_sample=False)[0]['summary_text'].strip()

        parsed_title, department, deadline, exam_info = parse_job_details(page_text)
        # If parsed title is too generic, replace with real title
        if parsed_title.lower() in ["vacancies", "job vacancy", "vacancy", "job openings"]:
            parsed_title = job_title

        results.append({
            "url": link,
            "title": parsed_title,
            "department": department,
            "deadline": deadline,
            "exam_info": exam_info,
            "summary": summary
        })
    return results

def get_all_jobs():
    jobs_url = "https://www.gazette.lk/category/jobs/"
    base_url = "https://www.gazette.lk/"

    try:
        response = requests.get(jobs_url)
        response.raise_for_status()
    except Exception as e:
        print(f"Error fetching jobs page: {e}")
        return []

    soup = BeautifulSoup(response.text, 'html.parser')
    links = [a['href'] for a in soup.select("h2.entry-title a")]
    # Ensure full absolute URLs
    links = [urljoin(base_url, link) for link in links]

    results = []
    for link in links[:10]:  # limit for performance
        page_text = extract_text_from_url(link)
        if not page_text:
            continue

        job_title = extract_job_title_from_page(link) or "Job Opening"
        summary = summarizer(page_text[:1024], max_length=120, min_length=30, do_sample=False)[0]['summary_text'].strip()

        parsed_title, department, deadline, exam_info = parse_job_details(page_text)
        if parsed_title.lower() in ["vacancies", "job vacancy", "vacancy", "job openings"]:
            parsed_title = job_title

        results.append({
            "url": link,
            "title": parsed_title,
            "department": department,
            "deadline": deadline,
            "exam_info": exam_info,
            "summary": summary
        })
    return results

@app.route("/analyze", methods=["POST"])
def analyze_query():
    data = request.get_json()
    query = data.get("query")

    if not query:
        return jsonify({"error": "No query provided"}), 400

    job_results = search_gazette(query)

    return jsonify({
        "query": query,
        "results": job_results
    })

@app.route("/alljobs", methods=["GET"])
def all_jobs():
    jobs = get_all_jobs()
    return jsonify({"jobs": jobs})

if __name__ == "__main__":
    app.run(debug=True)
