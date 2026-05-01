from flask import Flask, jsonify, request, send_file

from main import CampaignService


app = Flask(__name__)
campaign_service = CampaignService()


campaign_service.startup_checks()

@app.route('/')
@app.route('/home')
def home():
    # Serves the actual UI to the user
    return send_file('launch_page.html')

@app.route('/data_review')
def data_review():
    return send_file('launch_page.html')

@app.route('/bucketing')
def bucketing():
    return send_file('launch_page.html')

@app.route('/email')
def email():
    return send_file('launch_page.html')

@app.route('/launch')
def launch():
    return send_file('launch_page.html')

# Internal API for the LangChain agent (hidden from UI)
@app.route('/api/internal/schema')
def api_schema():
    schema_data = campaign_service.get_schema_api_payload()
    if schema_data is None:
        return jsonify({"error": "failed"}), 500
    return jsonify(schema_data)


@app.route('/api/internal/campaign/run', methods=['POST'])
def api_campaign_run():
    payload = request.get_json(silent=True) or {}
    about_text = (payload.get("about") or "").strip()
    audience_text = (payload.get("campaign_for") or "").strip()
    success_text = (payload.get("success_conditions") or "").strip()

    if not about_text or not audience_text or not success_text:
        return jsonify({"error": "about, campaign_for, and success_conditions are required"}), 400

    try:
        result = campaign_service.build_campaign_response(about_text, audience_text, success_text)
        return jsonify(result)
    except Exception as exc:
        return jsonify({"error": str(exc)}), 500


@app.route('/api/internal/campaign/launch', methods=['POST'])
def api_campaign_launch():
    payload = request.get_json(silent=True) or {}
    return jsonify(campaign_service.launch_campaign(payload))


@app.route('/api/internal/campaign/history', methods=['GET'])
def api_campaign_history():
    return jsonify(campaign_service.load_campaign_history())

if __name__ == '__main__':
    app.run(debug=True)