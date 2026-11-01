"""
Flask web frontend for the Autonomous Research Agent System.
"""
from dotenv import load_dotenv
load_dotenv(override=True)  # .env is authoritative, even over a polluted shell env

from flask import (Flask, render_template, request, jsonify, send_file, abort,
                   Response, stream_with_context)
from flask_talisman import Talisman
from flask_limiter import Limiter
from flask_limiter.util import get_remote_address
import asyncio
import io
import json
import os
import queue
import re
import sys
import tempfile
from datetime import datetime
from pathlib import Path
import threading
import concurrent.futures
from werkzeug.utils import secure_filename

# Add src to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'src'))

from src.research_system import AutonomousResearchSystem
from src.jobs import JOBS, STAGES, LITERATURE_STAGES, ResearchCancelled, is_sentinel, sse_format
from src.agents.custom_citation_formatter import CustomCitationFormatter
from src.agents.literature_builder_agent import LiteratureBuilderAgent, apply_literature_filter
from src.agents.humanizer_agent import HumanizerAgent
from src.agents.latex_citation_reorder import reorder_citations
from src.agents.prisma_diagram import render_svg as render_prisma_svg
from src.agents.literature_export import evidence_table_to_csv, document_to_latex
from src.models.data_models import LiteratureFilter
from src.agents.plagiarism_agent import PlagiarismCheckerAgent
from src.agents.journal_recommender_agent import JournalRecommenderAgent
from src.agents.abstract_screener_agent import AbstractScreenerAgent
from src.agents.checklist_agent import ChecklistAgent
from src.agents.grant_writer_agent import GrantWriterAgent, FUNDER_TEMPLATES
from src.agents.citation_network_agent import CitationNetworkAgent
from src.agents.access_router_agent import resolve_access
from src.blueprints.journals import journals_bp
from src.db.engine import init_db
from src.reporting.report_builder import (
    _generate_custom_citation,
    _get_paper_url,
    build_report_dict,
    render_markdown,
)

app = Flask(__name__)
app.config['SECRET_KEY'] = os.environ.get('SECRET_KEY', os.urandom(32).hex())
app.config['SESSION_COOKIE_HTTPONLY'] = True
app.config['SESSION_COOKIE_SAMESITE'] = 'Lax'
app.config['MAX_CONTENT_LENGTH'] = 5 * 1024 * 1024

# ── Rate limiting ────────────────────────────────────────────────────────────
limiter = Limiter(
    get_remote_address,
    app=app,
    default_limits=["200 per hour", "30 per minute"],
    storage_uri="memory://",
)

# ── Security headers (CSP allows CDN fonts/icons + inline styles needed by app)
csp = {
    'default-src': ["'self'"],
    'script-src':  ["'self'", "'unsafe-inline'",
                    "https://cdn.jsdelivr.net", "https://cdnjs.cloudflare.com",
                    "https://d3js.org"],
    'style-src':   ["'self'", "'unsafe-inline'",
                    "https://cdn.jsdelivr.net", "https://cdnjs.cloudflare.com",
                    "https://fonts.googleapis.com"],
    'font-src':    ["'self'", "https://fonts.gstatic.com",
                    "https://cdnjs.cloudflare.com"],
    'img-src':     ["'self'", "data:", "https:"],
    'connect-src': ["'self'"],
}
Talisman(
    app,
    content_security_policy=csp,
    force_https=False,               # localhost dev — flip to True in production
    strict_transport_security=False, # same
    referrer_policy='strict-origin-when-cross-origin',
    x_content_type_options=True,
    x_xss_protection=True,
)

# ── Journal database (SQL-backed multi-source journal/APC tracking) ─────────
init_db()
app.register_blueprint(journals_bp)

# ── Input validation helpers ─────────────────────────────────────────────────
_URL_RE = re.compile(r'^https?://', re.I)
_MAX_TEXT_LENGTH = 200_000


def _json_object():
    """Return a JSON object, or None for malformed/non-object request bodies."""
    data = request.get_json(silent=True)
    return data if isinstance(data, dict) else None


def _safe_text(value, max_len: int = _MAX_TEXT_LENGTH) -> str:
    """Return stripped text, rejecting wrong types and oversized values."""
    if not isinstance(value, str) or len(value) > max_len:
        return ""
    return value.strip()


def _text_fields_are_strings(data: dict, *keys: str) -> bool:
    return all(key not in data or isinstance(data[key], str) for key in keys)


def _plain_data(value):
    """Recursively convert Pydantic/dataclass-style results for jsonify."""
    if hasattr(value, 'model_dump'):
        return _plain_data(value.model_dump(mode='json'))
    if hasattr(value, 'to_dict') and callable(value.to_dict):
        return _plain_data(value.to_dict())
    if isinstance(value, dict):
        return {str(key): _plain_data(item) for key, item in value.items()}
    if isinstance(value, (list, tuple, set)):
        return [_plain_data(item) for item in value]
    return value


def _safe_slug(value) -> str:
    """Build an ASCII-only filename component from a user-supplied topic."""
    text = value if isinstance(value, str) else 'research'
    return re.sub(r'[^A-Za-z0-9_-]+', '_', text)[:40].strip('_') or 'research'


def _send_generated_file(path: str, mimetype: str, filename: str):
    """Send a generated file from memory and always remove the temp file."""
    try:
        with open(path, 'rb') as generated:
            payload = generated.read()
    finally:
        try:
            os.unlink(path)
        except OSError:
            app.logger.warning('Could not remove generated temporary file', exc_info=True)
    return send_file(
        io.BytesIO(payload), mimetype=mimetype, as_attachment=True,
        download_name=filename,
    )


def _valid_export_payload(data) -> bool:
    """Validate the collection shapes consumed by all export renderers."""
    if not isinstance(data, dict):
        return False
    if not all(isinstance(data.get(key, ''), str)
               for key in ('topic', 'generated_at', 'executive_summary')):
        return False
    if not isinstance(data.get('summary', {}), dict):
        return False
    for key in ('papers', 'research_gaps', 'recommendations', 'citations'):
        value = data.get(key, [])
        if not isinstance(value, list) or not all(isinstance(item, dict) for item in value):
            return False
    papers_valid = all(
        isinstance(paper.get('authors', []), list)
        and all(isinstance(author, str) for author in paper.get('authors', []))
        and all(isinstance(paper.get(key, ''), str)
                for key in ('title', 'venue', 'abstract'))
        for paper in data.get('papers', [])
    )
    gaps_valid = all(isinstance(gap.get('description', ''), str)
                     for gap in data.get('research_gaps', []))
    recommendations_valid = all(
        all(isinstance(item.get(key, ''), str) for key in ('title', 'rationale', 'action'))
        and isinstance(item.get('priority', 0), (int, float))
        and not isinstance(item.get('priority', 0), bool)
        for item in data.get('recommendations', [])
    )
    citations_valid = all(
        isinstance(item.get('custom_format', ''), str)
        and isinstance(item.get('bibtex', ''), str)
        for item in data.get('citations', [])
    )
    return papers_valid and gaps_valid and recommendations_valid and citations_valid

def _validate_url(url: str) -> str:
    """Return url only if it's a plain http/https web URL, else empty string."""
    if not isinstance(url, str):
        return ""
    url = url.strip()
    if _URL_RE.match(url) and len(url) < 2048:
        return url
    return ""


@app.errorhandler(413)
def request_too_large(_error):
    return jsonify({'error': 'Request body too large'}), 413


@app.before_request
def enforce_content_length():
    limit = app.config['MAX_CONTENT_LENGTH']
    if request.content_length is not None and request.content_length > limit:
        return jsonify({'error': 'Request body too large'}), 413


from werkzeug.serving import WSGIRequestHandler

# The dev server appends its own "Server: Werkzeug/x Python/y" line; blank it too.
WSGIRequestHandler.server_version = 'ResearchAgent'
WSGIRequestHandler.sys_version = ''


@app.after_request
def hide_server_version(response):
    response.headers['Server'] = 'ResearchAgent'
    return response

# Global system instance
research_system = None
executor = concurrent.futures.ThreadPoolExecutor(max_workers=2)

def get_system():
    """Get or create research system instance."""
    global research_system
    if research_system is None:
        research_system = AutonomousResearchSystem()
    return research_system


def run_research_in_thread(topic):
    """Run research in a separate thread with its own event loop."""
    def research_task():
        # Create new event loop for this thread
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        
        try:
            system = get_system()
            result = loop.run_until_complete(system.research(topic))
            return result
        except Exception as e:
            raise e
        finally:
            loop.close()
    
    return research_task()


def _extract_volume_info_crossref(paper):
    """Extract accurate volume, issue, and page information using CrossRef API."""
    volume_info = {
        'volume': None,
        'issue': None,
        'pages': None,
        'article_number': None
    }
    
    # Try to extract from DOI using CrossRef API
    if paper.doi:
        try:
            import requests
            import time
            
            # Clean DOI - handle various DOI formats
            doi = paper.doi.strip()
            if doi.startswith('https://doi.org/'):
                doi = doi.replace('https://doi.org/', '')
            elif doi.startswith('http://dx.doi.org/'):
                doi = doi.replace('http://dx.doi.org/', '')
            elif doi.startswith('doi:'):
                doi = doi.replace('doi:', '')
            
            # Query CrossRef API for accurate bibliographic data
            crossref_url = f"https://api.crossref.org/works/{doi}"
            headers = {
                'User-Agent': 'Research System/1.0 (mailto:research@example.com)',
                'Accept': 'application/json'
            }
            
            print(f"Fetching bibliographic data for DOI: {doi}")
            response = requests.get(crossref_url, headers=headers, timeout=10)
            
            if response.status_code == 200:
                data = response.json()
                work = data.get('message', {})
                
                # Extract volume
                if 'volume' in work and work['volume']:
                    volume_info['volume'] = str(work['volume']).strip()
                
                # Extract issue
                if 'issue' in work and work['issue']:
                    volume_info['issue'] = str(work['issue']).strip()
                
                # Extract pages - handle different formats
                if 'page' in work and work['page']:
                    pages = str(work['page']).strip()
                    if pages:
                        volume_info['pages'] = pages
                elif 'article-number' in work and work['article-number']:
                    article_num = str(work['article-number']).strip()
                    volume_info['article_number'] = article_num
                    volume_info['pages'] = article_num
                
                print(f"Successfully extracted: vol={volume_info['volume']}, issue={volume_info['issue']}, pages={volume_info['pages']}")
                
                # Small delay to be respectful to CrossRef API
                time.sleep(0.1)
                
            elif response.status_code == 404:
                print(f"DOI {doi} not found in CrossRef (404)")
            else:
                print(f"CrossRef API returned status {response.status_code} for DOI {doi}")
                
        except Exception as e:
            print(f"Error fetching bibliographic data for DOI {paper.doi}: {str(e)}")
    
    # Try to extract from venue name if it contains volume/issue info
    if not any([volume_info['volume'], volume_info['issue'], volume_info['pages']]):
        if paper.venue:
            venue_lower = paper.venue.lower()
            import re
            
            # Look for patterns like "vol. 25, no. 3" or "25(3)" in venue
            vol_match = re.search(r'vol(?:ume)?\.?\s*(\d+)', venue_lower)
            if vol_match:
                volume_info['volume'] = vol_match.group(1)
            
            issue_match = re.search(r'(?:no|issue)\.?\s*(\d+)', venue_lower)
            if issue_match:
                volume_info['issue'] = issue_match.group(1)
            
            # Look for pattern like "25(3)" 
            vol_issue_match = re.search(r'(\d+)\((\d+)\)', venue_lower)
            if vol_issue_match:
                volume_info['volume'] = vol_issue_match.group(1)
                volume_info['issue'] = vol_issue_match.group(2)
    
    return volume_info


def _generate_bibitem_key(paper):
    """Generate bibitem key from authors and year."""
    if not paper.authors:
        return f"Unknown{paper.year % 100:02d}"
    
    # Get first 2-3 authors
    authors_for_key = paper.authors[:3] if len(paper.authors) >= 3 else paper.authors[:2]
    
    # Extract first two letters of last names
    key_parts = []
    for author in authors_for_key:
        last_name = author.split()[-1] if author.split() else author
        if len(last_name) >= 2:
            key_parts.append(last_name[:2].title())
        elif len(last_name) == 1:
            key_parts.append(last_name.upper())
    
    # Add year (last 2 digits)
    year_suffix = paper.year % 100
    
    key = "".join(key_parts) + f"{year_suffix:02d}"
    return key


def _format_authors_custom(authors):
    """Format authors with initials first, then last name."""
    if not authors:
        return "Unknown Author"
    
    formatted_authors = []
    
    for author in authors:
        author = author.strip()
        parts = author.split()
        
        if len(parts) < 2:
            formatted_authors.append(author)
            continue
        
        # Check if author is already in correct format (e.g., "Y. Saad", "M.H. Schultz")
        if len(parts) == 2 and len(parts[0]) <= 4 and '.' in parts[0]:
            # Already in format like "Y. Saad" or "M.H. Schultz"
            formatted_authors.append(author)
            continue
            
        # Last part is last name
        last_name = parts[-1]
        
        # Everything else is first/middle names
        first_middle = parts[:-1]
        
        # Create initials
        initials = []
        for name in first_middle:
            if name and name[0].isalpha():
                # Handle names that might already have periods
                if name.endswith('.'):
                    initials.append(name)
                else:
                    initials.append(f"{name[0].upper()}.")
        
        # Format as "F.M. Last" (initials first, then last name)
        if initials:
            formatted_authors.append(f"{''.join(initials)} {last_name}")
        else:
            formatted_authors.append(last_name)
    
    return ", ".join(formatted_authors)


def _format_title_custom(title):
    """Format title with only first letter capital, except proper nouns."""
    if not title:
        return ""
    
    # Clean title
    title = title.strip()
    if title.endswith('.'):
        title = title[:-1]
    
    # Convert to lowercase first
    title_lower = title.lower()
    
    # Capitalize first letter
    if title_lower:
        title_formatted = title_lower[0].upper() + title_lower[1:]
    else:
        title_formatted = title_lower
    
    # Capitalize proper nouns
    proper_nouns = ["wiener", "euler", "hamilton", "fibonacci", "pascal", "newton", "gauss",
                   "fourier", "laplace", "bayes", "markov", "poisson", "bernoulli",
                   "covid", "sars", "hiv", "aids", "dna", "rna", "pcr", "crispr"]
    
    for proper_noun in proper_nouns:
        import re
        pattern = r'\b' + re.escape(proper_noun.lower()) + r'\b'
        replacement = proper_noun.capitalize()
        title_formatted = re.sub(pattern, replacement, title_formatted, flags=re.IGNORECASE)
    
    return title_formatted


@app.route('/')
def index():
    """Main page."""
    return render_template('index.html')


def _serialize_results(results):
    """Convert ResearchResults into the JSON payload the frontend expects.

    Shared by the legacy blocking /research route and the job-based flow so
    both return an identical contract.
    """
    try:
        return build_report_dict(results)
    except AttributeError as e:
        raise ValueError(f"Malformed research results: {e}") from e


def _save_results_file(response_data):
    """Persist a completed run to output/ and attach its download URL."""
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    filename = f"research_{timestamp}.json"
    report_filename = f"research_{timestamp}.md"
    output_dir = Path("output")
    try:
        output_dir.mkdir(parents=True, exist_ok=True)
        with open(output_dir / filename, 'w', encoding='utf-8') as f:
            json.dump(response_data, f, indent=2, default=str)
        response_data['download_url'] = f'/download/{filename}'
    except OSError as e:
        app.logger.error(f'Could not save research JSON report: {e}')

    try:
        output_dir.mkdir(parents=True, exist_ok=True)
        with open(output_dir / report_filename, 'w', encoding='utf-8') as f:
            f.write(render_markdown(response_data))
        response_data['report_url'] = f'/download/{report_filename}'
    except OSError as e:
        app.logger.error(f'Could not save research Markdown report: {e}')
    return response_data


@app.route('/research', methods=['POST'])
def research():
    """Blocking research run. Kept for scripts and backwards compatibility.

    The browser uses /research/start instead so it can stream progress.
    """
    try:
        data = _json_object()
        if data is None:
            return jsonify({'error': 'Invalid JSON object'}), 400
        topic = _safe_text(data.get('topic'), max_len=500)

        if not topic:
            return jsonify({'error': 'Topic is required'}), 400

        print(f"Starting research on topic: {topic}")

        # Run research in a separate thread to avoid event loop conflicts
        future = executor.submit(run_research_in_thread, topic)
        results = future.result(timeout=300)  # 5 minute timeout

        print("Research completed successfully")

        return jsonify(_save_results_file(_serialize_results(results)))

    except concurrent.futures.TimeoutError:
        return jsonify({'error': 'Research timed out. Please try a more specific topic.'}), 500
    except Exception as e:
        app.logger.exception('Research failed')
        return jsonify({'error': 'Internal server error'}), 500


# ── Job-based research: start → stream progress → fetch result ───────────────

def _run_research_job(job):
    """Worker body for one research job. Runs on its own thread + event loop."""
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)

    def progress(stage, name, state, **detail):
        # Cancellation is checked at every stage boundary, so a cancelled run
        # stops within one stage instead of burning the full 5 minutes.
        job.check_cancelled()
        job.emit('stage', stage=stage, name=name, state=state, detail=detail)

    try:
        job.status = 'running'
        job.emit('start', topic=job.topic, stages=[
            {'stage': n, 'name': label} for n, label in STAGES
        ])

        system = get_system()
        results = loop.run_until_complete(system.research(job.topic, progress=progress))

        payload = _save_results_file(_serialize_results(results))
        job.finish('done', result=payload)
        print(f"Research job {job.id} completed")

    except ResearchCancelled:
        job.finish('cancelled', error='Cancelled by user')
        print(f"Research job {job.id} cancelled")
    except Exception as e:
        import traceback
        traceback.print_exc()
        job.finish('error', error=str(e))
        print(f"Research job {job.id} failed: {e}")
    finally:
        loop.close()


@app.route('/research/start', methods=['POST'])
def research_start():
    """Queue a research run and return its job id immediately."""
    data = _json_object()
    if data is None:
        return jsonify({'error': 'Invalid JSON object'}), 400
    topic = _safe_text(data.get('topic', ''), max_len=500)

    if not topic:
        return jsonify({'error': 'Topic is required'}), 400

    job = JOBS.create(topic)
    threading.Thread(target=_run_research_job, args=(job,), daemon=True).start()

    return jsonify({
        'job_id': job.id,
        'topic': job.topic,
        'stages': [{'stage': n, 'name': label} for n, label in STAGES],
    }), 202


def _job_sse_response(job_id: str):
    """Stream a job's stage events as Server-Sent Events. Shared by /research/events
    and /generate-literature/events since both ride the same Job/JobRegistry."""
    job = JOBS.get(job_id)
    if job is None:
        return jsonify({'error': 'Unknown job'}), 404

    @stream_with_context
    def stream():
        q = job.subscribe()
        try:
            while True:
                try:
                    item = q.get(timeout=15)
                except queue.Empty:
                    yield ': keepalive\n\n'   # stops proxies idling the connection out
                    continue
                if is_sentinel(item):
                    break
                yield sse_format(item)
                if item.get('type') == 'end':
                    return
        finally:
            job.unsubscribe(q)

    return Response(stream(), mimetype='text/event-stream', headers={
        'Cache-Control': 'no-cache',
        'X-Accel-Buffering': 'no',
    })


def _job_cancel_response(job_id: str):
    """Ask a running job to stop at its next stage boundary. Shared by
    /research/cancel and /generate-literature/cancel."""
    job = JOBS.get(job_id)
    if job is None:
        return jsonify({'error': 'Unknown job'}), 404

    job.cancel()
    return jsonify({'job_id': job.id, 'status': 'cancelling'})


@app.route('/research/events/<job_id>')
@limiter.exempt
def research_events(job_id):
    return _job_sse_response(job_id)


@app.route('/research/result/<job_id>')
def research_result(job_id):
    """Fetch a finished job's payload, or its current status if still running."""
    job = JOBS.get(job_id)
    if job is None:
        return jsonify({'error': 'Unknown job'}), 404

    if job.status == 'done':
        return jsonify(job.result)
    if job.status in ('error', 'cancelled'):
        return jsonify({'error': job.error or job.status, 'status': job.status}), 409
    return jsonify(job.summary()), 202


@app.route('/report/<job_id>.md')
def research_report(job_id):
    """Download a finished in-memory job as a Markdown report."""
    job = JOBS.get(job_id)
    if job is None:
        return jsonify({'error': 'Unknown job'}), 404
    if job.status == 'done':
        markdown = render_markdown(job.result)
        return Response(
            markdown,
            mimetype='text/markdown',
            headers={'Content-Disposition': f'attachment; filename="research_{job_id}.md"'},
        )
    if job.status in ('error', 'cancelled'):
        return jsonify({'error': job.error or job.status, 'status': job.status}), 409
    return jsonify(job.summary()), 202


@app.route('/research/cancel/<job_id>', methods=['POST'])
def research_cancel(job_id):
    return _job_cancel_response(job_id)


@app.route('/download/<path:filename>')
def download_file(filename):
    """Download research results file."""
    try:
        name = secure_filename(filename)
        if not name or name != filename:
            return jsonify({'error': 'Invalid filename'}), 400
        output_dir = Path("output").resolve()
        filepath = (output_dir / name).resolve()
        if output_dir not in filepath.parents:
            return jsonify({'error': 'Invalid filename'}), 400
        if filepath.is_file():
            return send_file(filepath, as_attachment=True)
        else:
            return jsonify({'error': 'File not found'}), 404
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@app.route('/history')
def history():
    """Get list of previous research results."""
    try:
        output_dir = Path("output")
        files = []
        
        if output_dir.exists():
            for file in output_dir.glob("research_*.json"):
                try:
                    with open(file, 'r') as f:
                        data = json.load(f)
                    
                    files.append({
                        'filename': file.name,
                        'topic': data.get('topic', 'Unknown'),
                        'generated_at': data.get('generated_at', ''),
                        'papers_count': len(data.get('papers', [])),
                        'claims_count': len(data.get('claims', [])),
                        'download_url': f'/download/{file.name}'
                    })
                except:
                    continue
        
        # Sort by date (newest first)
        files.sort(key=lambda x: x['generated_at'], reverse=True)
        
        return jsonify(files)
        
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@app.route('/citations')
def citations_page():
    """Enhanced citations page."""
    return render_template('enhanced_citations.html')


@app.route('/literature')
def literature_page():
    """Literature builder page."""
    return render_template('literature_builder.html')


@app.route('/corrections-details')
def corrections_details():
    """Corrections details page."""
    return render_template('corrections_details.html')


@app.route('/validator')
def reference_validator_page():
    """Reference validator page."""
    return render_template('reference_validator.html')


@app.route('/validate-references', methods=['POST'])
def validate_references():
    """Validate and correct uploaded reference file."""
    try:
        data = _json_object()
        if data is None:
            return jsonify({'error': 'Invalid JSON object'}), 400
        content = _safe_text(data.get('content'))
        file_format = _safe_text(data.get('format', 'bibtex'), max_len=20)
        options = data.get('options', {})
        if not content or not file_format or not isinstance(options, dict):
            return jsonify({'error': 'No content provided'}), 400
        
        app.logger.info(f"Reference validation request: format={file_format}, length={len(content)}")
        
        # Run validation in a separate thread
        future = executor.submit(run_reference_validation, content, file_format, options)
        results = future.result(timeout=300)  # 5 minute timeout
        
        app.logger.info(f"Reference validation completed successfully")
        
        return jsonify(results)
        
    except concurrent.futures.TimeoutError:
        app.logger.error(f"Reference validation timed out")
        return jsonify({'error': 'Reference validation timed out. Please try with fewer references.'}), 500
    except Exception as e:
        app.logger.exception('Reference validation failed')
        return jsonify({'error': 'Internal server error'}), 500


@app.route('/reformat-references', methods=['POST'])
def reformat_references():
    """Reformat references to different output format."""
    try:
        data = _json_object()
        if data is None:
            return jsonify({'error': 'Invalid JSON object'}), 400
        references_data = data.get('references', [])
        output_format = _safe_text(data.get('format', 'bibitem'), max_len=20)
        if (not isinstance(references_data, list)
                or not all(isinstance(item, dict) for item in references_data)
                or not output_format):
            return jsonify({'error': 'Invalid request data'}), 400
        
        # Import reference validator
        from src.agents.reference_validator import ReferenceValidator
        validator = ReferenceValidator()
        
        # Create a mock result object with the references
        class MockResult:
            def __init__(self, refs):
                self.corrected_references = refs
        
        mock_result = MockResult(references_data)
        formatted_output = validator.generate_corrected_file(mock_result, output_format)
        
        return jsonify({
            'formatted_references': formatted_output,
            'format': output_format
        })
        
    except Exception as e:
        app.logger.exception('Reference reformatting failed')
        return jsonify({'error': 'Internal server error'}), 500


def run_reference_validation(content: str, file_format: str, options: dict):
    """Run reference validation in a separate thread."""
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    
    try:
        # Import reference validator
        from src.agents.reference_validator import ReferenceValidator, ReferenceValidationResult
        
        app.logger.info(f"Starting reference validation")
        validator = ReferenceValidator()
        
        # Process the reference file
        result = loop.run_until_complete(validator.process_reference_file(content, file_format))
        
        app.logger.info(f"Reference validation completed: {result.original_count} → {result.final_count}")
        
        # Generate outputs in different formats
        bibitem_output = validator.generate_corrected_file(result, 'bibitem')
        bibtex_output = validator.generate_corrected_file(result, 'bibtex')
        plain_output = validator.generate_corrected_file(result, 'plain')
        validation_report = validator.generate_validation_report(result)
        
        # Prepare response
        response = {
            'stats': {
                'original_count': result.original_count,
                'duplicates_removed': len(result.duplicates_removed),
                'format_corrections': len(result.format_corrections),
                'spelling_corrections': len(result.spelling_corrections),
                'invalid_papers': len(result.invalid_papers),
                'final_count': result.final_count
            },
            'processing_log': result.processing_log,
            'corrections': [],
            'issues': [],
            'corrected_references': bibitem_output,  # Default format
            'corrected_references_data': result.corrected_references,
            'outputs': {
                'bibitem': bibitem_output,
                'bibtex': bibtex_output,
                'plain': plain_output
            },
            'validation_report': validation_report
        }
        
        # Process corrections for display - avoid duplicates
        corrections_by_ref = {}
        
        # Group format corrections
        for correction in result.format_corrections:
            ref_key = correction['reference_key']
            if ref_key not in corrections_by_ref:
                corrections_by_ref[ref_key] = {
                    'type': 'Format',
                    'reference_key': ref_key,
                    'details': [],
                    'corrections_count': 0,
                    'processed_fields': set()  # Track processed fields to avoid duplicates
                }
            
            for corr_text in correction['corrections']:
                # Parse correction text to extract before/after
                if ' → ' in corr_text:
                    field, change = corr_text.split(':', 1) if ':' in corr_text else ('Field', corr_text)
                    field = field.strip()
                    
                    # Skip if this field was already processed
                    if field in corrections_by_ref[ref_key]['processed_fields']:
                        continue
                        
                    if ' → ' in change:
                        before, after = change.split(' → ', 1)
                        corrections_by_ref[ref_key]['details'].append({
                            'field': field,
                            'before': before.strip().strip("'\""),
                            'after': after.strip().strip("'\"")
                        })
                        corrections_by_ref[ref_key]['corrections_count'] += 1
                        corrections_by_ref[ref_key]['processed_fields'].add(field)
        
        # Group spelling corrections
        for correction in result.spelling_corrections:
            ref_key = correction['reference_key']
            if ref_key not in corrections_by_ref:
                corrections_by_ref[ref_key] = {
                    'type': 'Spelling',
                    'reference_key': ref_key,
                    'details': [],
                    'corrections_count': 0,
                    'processed_fields': set()
                }
            
            for corr_text in correction['corrections']:
                if ' → ' in corr_text:
                    field, change = corr_text.split(':', 1) if ':' in corr_text else ('Spelling', corr_text)
                    field = field.strip()
                    
                    if field in corrections_by_ref[ref_key]['processed_fields']:
                        continue
                        
                    if ' → ' in change:
                        before, after = change.split(' → ', 1)
                        corrections_by_ref[ref_key]['details'].append({
                            'field': field,
                            'before': before.strip().strip("'\""),
                            'after': after.strip().strip("'\"")
                        })
                        corrections_by_ref[ref_key]['corrections_count'] += 1
                        corrections_by_ref[ref_key]['processed_fields'].add(field)
        
        # Group paper verification corrections - only add unique corrections
        for verification in result.verification_results:
            ref_key = verification['reference_key']
            ver_result = verification['verification']
            
            if ver_result.get('corrections_made'):
                if ref_key not in corrections_by_ref:
                    corrections_by_ref[ref_key] = {
                        'type': 'Paper Data',
                        'reference_key': ref_key,
                        'details': [],
                        'corrections_count': 0,
                        'processed_fields': set()
                    }
                elif corrections_by_ref[ref_key]['type'] != 'Paper Data':
                    corrections_by_ref[ref_key]['type'] = 'Format & Data'
                
                for corr_text in ver_result['corrections_made']:
                    if 'corrected:' in corr_text or 'added:' in corr_text:
                        # Parse correction text
                        if 'corrected:' in corr_text:
                            field, change = corr_text.split(' corrected:', 1)
                        elif 'added:' in corr_text:
                            field, change = corr_text.split(' added:', 1)
                        else:
                            continue
                            
                        field = field.strip()
                        
                        # Skip if this field was already processed
                        if field in corrections_by_ref[ref_key]['processed_fields']:
                            continue
                            
                        if ' → ' in change:
                            before, after = change.split(' → ', 1)
                        else:
                            before = 'Not provided'
                            after = change.strip()
                        
                        corrections_by_ref[ref_key]['details'].append({
                            'field': field,
                            'before': before.strip().strip("'\""),
                            'after': after.strip().strip("'\"")
                        })
                        corrections_by_ref[ref_key]['corrections_count'] += 1
                        corrections_by_ref[ref_key]['processed_fields'].add(field)
        
        # Clean up processed_fields from response and convert to list
        for ref_key in corrections_by_ref:
            del corrections_by_ref[ref_key]['processed_fields']
        
        response['corrections'] = list(corrections_by_ref.values())
        
        # Process issues for display
        for duplicate in result.duplicates_removed:
            response['issues'].append({
                'type': 'Duplicate',
                'reference_key': duplicate['reference'].get('key', 'unknown'),
                'description': duplicate['reason']
            })
        
        for invalid in result.invalid_papers:
            response['issues'].append({
                'type': 'Invalid',
                'reference_key': invalid['reference'].get('key', 'unknown'),
                'description': invalid['reason']
            })
        
        app.logger.info(f"Reference validation response prepared successfully")
        return response
        
    except Exception as e:
        app.logger.error(f"Error in reference validation: {str(e)}")
        raise e
        
    finally:
        loop.close()


def _serialize_literature_result(topic: str, literature_document, literature_agent) -> dict:
    """Shared JSON contract for both the blocking and job-based literature routes.

    Adds evidence_table / synthesis_matrix / prisma (+ prisma_svg) on top of the
    original outline/sections/bibliography/stats contract — additive, so the
    existing frontend rendering keeps working unchanged.
    """
    stats = literature_agent.get_literature_stats(literature_document)

    result = {
        'topic': topic,
        'outline': {
            'title': literature_document.outline.title,
            'sections': literature_document.outline.sections,
            'total_papers': literature_document.outline.total_papers,
            'total_claims': literature_document.outline.total_claims,
            'date_range': literature_document.outline.date_range,
            'estimated_word_count': getattr(literature_document.outline, 'estimated_word_count', 0)
        },
        'sections': [
            {
                'section_type': section.section_type,
                'title': section.title,
                'content': section.content,
                'citations': section.citations,
                'claim_ids': section.claim_ids,
                'word_count': section.word_count
            }
            for section in literature_document.sections
        ],
        'bibliography': literature_document.bibliography,
        'metadata': literature_document.metadata,
        'stats': stats,
        'evidence_table': [row.model_dump() for row in literature_document.evidence_table],
        'synthesis_matrix': (
            literature_document.synthesis_matrix.model_dump()
            if literature_document.synthesis_matrix else None
        ),
        'prisma': literature_document.prisma.model_dump() if literature_document.prisma else None,
        'prisma_svg': render_prisma_svg(literature_document.prisma) if literature_document.prisma else None,
        'generated_at': literature_document.generated_at.isoformat()
    }
    return result


def _build_literature_filter(filters: dict) -> LiteratureFilter:
    """Build a LiteratureFilter from the UI's posted filters dict, tolerating
    missing/malformed keys rather than raising."""
    try:
        return LiteratureFilter(
            q_rankings=filters.get('q_rankings') or ['Q1', 'Q2', 'Q3'],
            include_sa_papers=bool(filters.get('include_sa_papers', True)),
            min_year=filters.get('min_year') or None,
            max_year=filters.get('max_year') or None,
            min_confidence=float(filters.get('min_confidence') or 0.0),
        )
    except (TypeError, ValueError):
        return LiteratureFilter()


def run_literature_generation(topic: str, filters: dict, progress=None):
    """Run literature generation. Used by both the blocking route and the
    SSE job worker (progress is None for the former)."""
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)

    try:
        app.logger.info(f"Starting research for topic: {topic}")
        system = get_system()
        research_results = loop.run_until_complete(system.research(topic, progress=progress))

        app.logger.info(f"Research completed. Found {len(research_results.papers)} papers, {len(research_results.claims)} claims")

        research_results = apply_literature_filter(research_results, _build_literature_filter(filters))

        app.logger.info("Starting literature generation...")
        literature_agent = LiteratureBuilderAgent()
        literature_document = loop.run_until_complete(
            literature_agent.process(research_results, progress=progress))

        app.logger.info(f"Literature generation completed. Generated {len(literature_document.sections)} sections")

        result = _serialize_literature_result(topic, literature_document, literature_agent)
        app.logger.info("Literature generation result prepared successfully")
        return result

    except Exception as e:
        app.logger.error(f"Error in literature generation: {str(e)}")
        raise e

    finally:
        loop.close()


@app.route('/generate-literature', methods=['POST'])
def generate_literature():
    """Blocking literature generation. Kept for scripts and backwards
    compatibility. The browser uses /generate-literature/start instead."""
    topic = ''
    try:
        data = _json_object()
        if data is None:
            return jsonify({'error': 'Invalid JSON object'}), 400
        topic = _safe_text(data.get('topic'), max_len=500)
        filters = data.get('filters', {})

        if not topic or not isinstance(filters, dict):
            return jsonify({'error': 'Topic is required'}), 400

        app.logger.info(f"Literature generation request for topic: {topic}")

        future = executor.submit(run_literature_generation, topic, filters)
        results = future.result(timeout=300)  # 5 minute timeout

        app.logger.info(f"Literature generated successfully for topic: {topic}")

        return jsonify(results)

    except concurrent.futures.TimeoutError:
        app.logger.error(f"Literature generation timed out for topic: {topic}")
        return jsonify({'error': 'Literature generation timed out. Please try a more specific topic.'}), 500
    except Exception as e:
        app.logger.exception("Literature generation failed for topic %r", topic)
        return jsonify({'error': 'Internal server error'}), 500


# ── Job-based literature generation: start -> stream progress -> fetch result ──

def _run_literature_job(job, filters: dict):
    """Worker body for one literature job. Continues the same 17-stage stream
    the main research job uses (stages 1-9), adding stages 10-17."""
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)

    def progress(stage, name, state, **detail):
        job.check_cancelled()
        job.emit('stage', stage=stage, name=name, state=state, detail=detail)

    try:
        job.status = 'running'
        job.emit('start', topic=job.topic, stages=[
            {'stage': n, 'name': label} for n, label in LITERATURE_STAGES
        ])

        system = get_system()
        research_results = loop.run_until_complete(system.research(job.topic, progress=progress))
        research_results = apply_literature_filter(research_results, _build_literature_filter(filters))

        literature_agent = LiteratureBuilderAgent()
        literature_document = loop.run_until_complete(
            literature_agent.process(research_results, progress=progress))

        payload = _serialize_literature_result(job.topic, literature_document, literature_agent)
        job.finish('done', result=payload)
        print(f"Literature job {job.id} completed")

    except ResearchCancelled:
        job.finish('cancelled', error='Cancelled by user')
        print(f"Literature job {job.id} cancelled")
    except Exception as e:
        import traceback
        traceback.print_exc()
        job.finish('error', error=str(e))
        print(f"Literature job {job.id} failed: {e}")
    finally:
        loop.close()


@app.route('/generate-literature/start', methods=['POST'])
def generate_literature_start():
    """Queue a literature generation run and return its job id immediately."""
    data = _json_object()
    if data is None:
        return jsonify({'error': 'Invalid JSON object'}), 400
    topic = _safe_text(data.get('topic', ''), max_len=500)
    filters = data.get('filters', {})

    if not topic or not isinstance(filters, dict):
        return jsonify({'error': 'Topic is required'}), 400

    job = JOBS.create(topic)
    threading.Thread(target=_run_literature_job, args=(job, filters), daemon=True).start()

    return jsonify({
        'job_id': job.id,
        'topic': job.topic,
        'stages': [{'stage': n, 'name': label} for n, label in LITERATURE_STAGES],
    }), 202


@app.route('/generate-literature/events/<job_id>')
@limiter.exempt
def generate_literature_events(job_id):
    return _job_sse_response(job_id)


@app.route('/generate-literature/result/<job_id>')
def generate_literature_result(job_id):
    job = JOBS.get(job_id)
    if job is None:
        return jsonify({'error': 'Unknown job'}), 404

    if job.status == 'done':
        return jsonify(job.result)
    if job.status in ('error', 'cancelled'):
        return jsonify({'error': job.error or job.status, 'status': job.status}), 409
    return jsonify(job.summary()), 202


@app.route('/generate-literature/cancel/<job_id>', methods=['POST'])
def generate_literature_cancel(job_id):
    return _job_cancel_response(job_id)


@app.route('/export-literature/<job_id>/<fmt>')
def export_literature(job_id, fmt):
    """Server-side export of a finished literature job: csv, tex, or prisma_svg."""
    job = JOBS.get(job_id)
    if job is None or job.status != 'done' or not job.result:
        return jsonify({'error': 'Result not ready'}), 404

    doc = job.result
    ts = datetime.now().strftime('%Y%m%d_%H%M%S')

    if fmt == 'csv':
        from src.models.data_models import EvidenceRow
        rows = [EvidenceRow(**row) for row in doc.get('evidence_table', [])]
        return Response(evidence_table_to_csv(rows), mimetype='text/csv', headers={
            'Content-Disposition': f'attachment; filename=evidence_table_{ts}.csv'
        })
    if fmt == 'tex':
        tex = document_to_latex(doc)
        return Response(tex, mimetype='text/x-tex', headers={
            'Content-Disposition': f'attachment; filename=literature_{ts}.tex'
        })
    if fmt == 'prisma_svg':
        svg = doc.get('prisma_svg') or ''
        return Response(svg, mimetype='image/svg+xml')

    return jsonify({'error': 'Unknown export format'}), 400


@app.route('/generate-custom-citations', methods=['POST'])
def generate_custom_citations():
    """Generate custom formatted citations."""
    try:
        data = _json_object()
        if data is None:
            return jsonify({'error': 'Invalid JSON object'}), 400
        topic = _safe_text(data.get('topic'), max_len=500)
        
        if not topic:
            return jsonify({'error': 'Topic is required'}), 400
        
        print(f"Generating custom citations for topic: {topic}")
        
        # Run research and citation generation in a separate thread
        future = executor.submit(run_citation_generation, topic)
        results = future.result(timeout=300)  # 5 minute timeout
        
        print(f"Custom citations generated successfully")
        
        return jsonify(results)
        
    except concurrent.futures.TimeoutError:
        return jsonify({'error': 'Citation generation timed out. Please try a more specific topic.'}), 500
    except Exception as e:
        app.logger.exception('Citation generation failed')
        return jsonify({'error': 'Internal server error'}), 500


def run_citation_generation(topic):
    """Run citation generation in a separate thread."""
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    
    try:
        # Get research system and run research
        system = get_system()
        results = loop.run_until_complete(system.research(topic))
        
        # Generate custom citations
        formatter = CustomCitationFormatter()
        custom_citations = loop.run_until_complete(formatter.process(results.papers))
        
        # Get statistics
        stats = formatter.get_citation_stats(custom_citations)
        
        return {
            'topic': topic,
            'citations': _plain_data(custom_citations),
            'stats': _plain_data(stats),
            'total_papers': len(results.papers)
        }
        
    finally:
        loop.close()


@app.route('/debug')
def debug_form():
    """The retired debug form is intentionally unavailable."""
    abort(404)


@app.route('/test')
def test():
    """System status — returns JSON consumed by the status popup in the UI."""
    import platform, sys
    from src.agents.llm_client import provider_info, _ollama_available
    try:
        system = get_system()
        llm_info = provider_info()
        llm_available = llm_info["available"]
        llm_label = llm_info["name"] if llm_available else "None"

        apis = {
            "ArXiv": True,
            "OpenAlex": True,
            "CrossRef": True,
            "PubMed": True,
            f"LLM ({llm_label})": llm_available,
            "Ollama (local)": _ollama_available(),
        }
        return jsonify({
            'status': 'ok',
            'message': 'All systems operational',
            'system_initialized': system is not None,
            'python_version': sys.version.split()[0],
            'platform': platform.system(),
            'llm_provider': llm_info,
            'apis': apis,
            'features': {
                'llm_extraction': llm_available,
                'humanizer': llm_available,
                'pdf_export': True,
                'docx_export': True,
                'abstract_screener': llm_available,
                'grant_writer': llm_available,
                'checklist': llm_available,
            }
        })
    except Exception as e:
        return jsonify({
            'status': 'error',
            'message': str(e),
            'apis': {},
            'features': {}
        }), 500


@app.route('/humanizer')
def humanizer_page():
    from src.agents.llm_client import provider_info
    llm = provider_info()
    return render_template('humanizer.html', llm_info=llm)


@limiter.limit("10 per minute")
@app.route('/humanize', methods=['POST'])
def humanize():
    try:
        text = None

        if request.content_type and 'multipart/form-data' in request.content_type:
            file = request.files.get('file')
            if not file or file.filename == '':
                return jsonify({'error': 'No file uploaded'}), 400

            filename = secure_filename(file.filename)
            if not filename.lower().endswith('.pdf'):
                return jsonify({'error': 'Only PDF files are accepted'}), 400

            with tempfile.NamedTemporaryFile(suffix='.pdf', delete=False) as tmp:
                file.save(tmp.name)
                tmp_path = tmp.name

            try:
                import fitz
                doc = fitz.open(tmp_path)
                pages_text = []
                for page in doc:
                    pages_text.append(page.get_text())
                doc.close()
                text = '\n\n'.join(pages_text).strip()
            finally:
                os.unlink(tmp_path)

            if not text:
                return jsonify({'error': 'Could not extract text from the PDF'}), 422
            if len(text) > _MAX_TEXT_LENGTH:
                return jsonify({'error': 'Text is too long'}), 400
            method_source = 'pdf'
        else:
            data = _json_object()
            if data is None:
                return jsonify({'error': 'Invalid JSON object'}), 400
            text = _safe_text(data.get('text'))
            if not text:
                return jsonify({'error': 'No text provided'}), 400
            method_source = 'text'

        agent = HumanizerAgent()
        result = agent.humanize(text)
        result['source'] = method_source
        return jsonify(result)

    except Exception as e:
        app.logger.exception('Humanization failed')
        return jsonify({'error': 'Internal server error'}), 500


@app.route('/latex-reorder')
def latex_reorder_page():
    return render_template('latex_reorder.html')


@app.route('/latex-reorder', methods=['POST'])
def latex_reorder():
    try:
        file = request.files.get('file')
        if not file or file.filename == '':
            return jsonify({'error': 'No file uploaded'}), 400

        filename = secure_filename(file.filename)
        source = file.read().decode('utf-8', errors='replace')

        reordered_source, info = reorder_citations(source)

        if 'error' in info:
            return jsonify({'error': info['error']}), 422

        return jsonify({
            'reordered_source': reordered_source,
            'citation_map': info.get('citation_map', {}),
            'total_citations': info.get('total_citations', 0),
            'keys_found_in_body': info.get('keys_found_in_body', 0),
        })

    except UnicodeDecodeError:
        return jsonify({'error': 'File encoding not supported. Please save as UTF-8.'}), 422
    except Exception as e:
        app.logger.exception('LaTeX reorder failed')
        return jsonify({'error': 'Internal server error'}), 500


@app.route('/export/json', methods=['POST'])
def export_json():
    try:
        data = _json_object()
        if not data or not _valid_export_payload(data):
            return jsonify({'error': 'Invalid request data'}), 400

        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
        topic_slug = _safe_slug(data.get('topic'))
        filename = f'research_{topic_slug}_{timestamp}.json'
        return send_file(
            io.BytesIO(json.dumps(data, indent=2, default=str).encode('utf-8')),
            mimetype='application/json',
            as_attachment=True,
            download_name=filename
        )
    except Exception as e:
        app.logger.exception('JSON export failed')
        return jsonify({'error': 'Internal server error'}), 500


@app.route('/export/pdf', methods=['POST'])
def export_pdf():
    tmp_path = None
    try:
        data = _json_object()
        if not data or not _valid_export_payload(data):
            return jsonify({'error': 'Invalid request data'}), 400

        from reportlab.lib.pagesizes import A4
        from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
        from reportlab.lib.units import cm
        from reportlab.lib import colors
        from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle, HRFlowable
        from reportlab.lib.enums import TA_LEFT, TA_CENTER

        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
        topic_slug = _safe_slug(data.get('topic'))
        filename = f'research_{topic_slug}_{timestamp}.pdf'
        fd, tmp_path = tempfile.mkstemp(suffix='.pdf')
        os.close(fd)

        doc = SimpleDocTemplate(
            tmp_path,
            pagesize=A4,
            rightMargin=2*cm, leftMargin=2*cm,
            topMargin=2*cm, bottomMargin=2*cm
        )

        styles = getSampleStyleSheet()
        title_style = ParagraphStyle('Title', parent=styles['Title'], fontSize=18, spaceAfter=6)
        h2_style = ParagraphStyle('H2', parent=styles['Heading2'], fontSize=13, spaceBefore=14, spaceAfter=4)
        body_style = ParagraphStyle('Body', parent=styles['Normal'], fontSize=10, leading=14, spaceAfter=4)
        meta_style = ParagraphStyle('Meta', parent=styles['Normal'], fontSize=9, textColor=colors.HexColor('#666666'), spaceAfter=2)

        story = []
        topic = data.get('topic', 'Research Report')
        generated_at = data.get('generated_at', datetime.now().isoformat())

        story.append(Paragraph(f'Research Report: {topic}', title_style))
        story.append(Paragraph(f'Generated: {generated_at}', meta_style))
        story.append(HRFlowable(width='100%', thickness=1, color=colors.HexColor('#30363d'), spaceAfter=12))

        executive_summary = data.get('executive_summary', '')
        if executive_summary:
            story.append(Paragraph('Executive Summary', h2_style))
            story.append(Paragraph(executive_summary, body_style))

        summary = data.get('summary', {})
        if summary:
            story.append(Paragraph('Summary', h2_style))
            summary_data = [
                ['Papers Analyzed', str(summary.get('papers_analyzed', 0))],
                ['Claims Extracted', str(summary.get('claims_extracted', 0))],
                ['Contradictions Found', str(summary.get('contradictions_found', 0))],
                ['Research Gaps', str(summary.get('research_gaps_identified', 0))],
            ]
            t = Table(summary_data, colWidths=[8*cm, 4*cm])
            t.setStyle(TableStyle([
                ('FONTSIZE', (0, 0), (-1, -1), 10),
                ('TEXTCOLOR', (0, 0), (0, -1), colors.HexColor('#444444')),
                ('FONTNAME', (0, 0), (0, -1), 'Helvetica-Bold'),
                ('ROWBACKGROUNDS', (0, 0), (-1, -1), [colors.HexColor('#f8f8f8'), colors.white]),
                ('GRID', (0, 0), (-1, -1), 0.5, colors.HexColor('#dddddd')),
                ('PADDING', (0, 0), (-1, -1), 5),
            ]))
            story.append(t)
            story.append(Spacer(1, 12))

        papers = data.get('papers', [])
        if papers:
            story.append(Paragraph(f'Papers ({len(papers)})', h2_style))
            for i, p in enumerate(papers, 1):
                title = p.get('title', 'Untitled')
                authors = ', '.join(p.get('authors', []))
                year = p.get('year', '')
                venue = p.get('venue', '')
                abstract = p.get('abstract', '')
                story.append(Paragraph(f'{i}. {title}', ParagraphStyle('PaperTitle', parent=body_style, fontName='Helvetica-Bold')))
                story.append(Paragraph(f'{authors} · {year} · {venue}', meta_style))
                if abstract:
                    story.append(Paragraph(abstract[:400] + ('...' if len(abstract) > 400 else ''), body_style))
                story.append(Spacer(1, 6))

        gaps = data.get('research_gaps', [])
        if gaps:
            story.append(Paragraph(f'Research Gaps ({len(gaps)})', h2_style))
            for g in gaps[:10]:
                story.append(Paragraph(f'• {g.get("description", "")}', body_style))

        recommendations = data.get('recommendations', [])
        if recommendations:
            story.append(Paragraph(f'Recommendations ({len(recommendations)})', h2_style))
            for recommendation in recommendations:
                priority = float(recommendation.get('priority') or 0)
                story.append(Paragraph(
                    f'{recommendation.get("rank", "-")}. {recommendation.get("title", "")} '
                    f'({priority:.0%} priority)',
                    ParagraphStyle('RecommendationTitle', parent=body_style, fontName='Helvetica-Bold'),
                ))
                if recommendation.get('rationale'):
                    story.append(Paragraph(recommendation['rationale'], body_style))
                if recommendation.get('action'):
                    story.append(Paragraph(f'Action: {recommendation["action"]}', body_style))

        citations = data.get('citations', [])
        if citations:
            story.append(Paragraph(f'Citations ({len(citations)})', h2_style))
            for c in citations:
                text = c.get('custom_format') or c.get('bibtex') or ''
                if text:
                    story.append(Paragraph(text, ParagraphStyle('Cite', parent=body_style, fontName='Courier', fontSize=8, leading=11)))
                    story.append(Spacer(1, 4))

        doc.build(story)

        response = _send_generated_file(tmp_path, 'application/pdf', filename)
        tmp_path = None
        return response

    except ImportError:
        return jsonify({'error': 'reportlab is not installed. Run: pip install reportlab'}), 500
    except Exception as e:
        if tmp_path:
            try:
                os.unlink(tmp_path)
            except OSError:
                pass
        app.logger.exception('PDF export failed')
        return jsonify({'error': 'Internal server error'}), 500


@app.route('/export/docx', methods=['POST'])
def export_docx():
    tmp_path = None
    try:
        data = _json_object()
        if not data or not _valid_export_payload(data):
            return jsonify({'error': 'Invalid request data'}), 400

        from docx import Document
        from docx.shared import Pt, RGBColor, Cm
        from docx.enum.text import WD_ALIGN_PARAGRAPH

        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
        topic_slug = _safe_slug(data.get('topic'))
        filename = f'research_{topic_slug}_{timestamp}.docx'
        fd, tmp_path = tempfile.mkstemp(suffix='.docx')
        os.close(fd)

        doc = Document()

        # Page margins
        for section in doc.sections:
            section.top_margin = Cm(2.5)
            section.bottom_margin = Cm(2.5)
            section.left_margin = Cm(3)
            section.right_margin = Cm(3)

        topic = data.get('topic', 'Research Report')
        generated_at = data.get('generated_at', datetime.now().isoformat())

        heading = doc.add_heading(f'Research Report: {topic}', level=0)
        heading.alignment = WD_ALIGN_PARAGRAPH.LEFT

        meta = doc.add_paragraph(f'Generated: {generated_at}')
        meta.runs[0].font.size = Pt(9)
        meta.runs[0].font.color.rgb = RGBColor(0x66, 0x66, 0x66)

        doc.add_paragraph()

        executive_summary = data.get('executive_summary', '')
        if executive_summary:
            doc.add_heading('Executive Summary', level=1)
            doc.add_paragraph(executive_summary)

        summary = data.get('summary', {})
        if summary:
            doc.add_heading('Summary', level=1)
            table = doc.add_table(rows=4, cols=2)
            table.style = 'Table Grid'
            rows_data = [
                ('Papers Analyzed', str(summary.get('papers_analyzed', 0))),
                ('Claims Extracted', str(summary.get('claims_extracted', 0))),
                ('Contradictions Found', str(summary.get('contradictions_found', 0))),
                ('Research Gaps', str(summary.get('research_gaps_identified', 0))),
            ]
            for i, (label, value) in enumerate(rows_data):
                row = table.rows[i]
                row.cells[0].text = label
                row.cells[1].text = value
            doc.add_paragraph()

        papers = data.get('papers', [])
        if papers:
            doc.add_heading(f'Papers ({len(papers)})', level=1)
            for i, p in enumerate(papers, 1):
                title_para = doc.add_paragraph()
                run = title_para.add_run(f'{i}. {p.get("title", "Untitled")}')
                run.bold = True
                run.font.size = Pt(11)

                authors = ', '.join(p.get('authors', []))
                year = p.get('year', '')
                venue = p.get('venue', '')
                meta_para = doc.add_paragraph(f'{authors} · {year} · {venue}')
                meta_para.runs[0].font.size = Pt(9)
                meta_para.runs[0].font.color.rgb = RGBColor(0x66, 0x66, 0x66)

                abstract = p.get('abstract', '')
                if abstract:
                    abs_para = doc.add_paragraph(abstract[:500] + ('...' if len(abstract) > 500 else ''))
                    abs_para.runs[0].font.size = Pt(10)

                doc.add_paragraph()

        gaps = data.get('research_gaps', [])
        if gaps:
            doc.add_heading(f'Research Gaps ({len(gaps)})', level=1)
            for g in gaps[:10]:
                p = doc.add_paragraph(g.get('description', ''), style='List Bullet')
                p.runs[0].font.size = Pt(10)

        recommendations = data.get('recommendations', [])
        if recommendations:
            doc.add_heading(f'Recommendations ({len(recommendations)})', level=1)
            for recommendation in recommendations:
                priority = float(recommendation.get('priority') or 0)
                paragraph = doc.add_paragraph(style='List Number')
                title_run = paragraph.add_run(
                    f'{recommendation.get("title", "")} ({priority:.0%} priority)'
                )
                title_run.bold = True
                if recommendation.get('rationale'):
                    doc.add_paragraph(recommendation['rationale'])
                if recommendation.get('action'):
                    action = doc.add_paragraph()
                    action.add_run('Action: ').bold = True
                    action.add_run(recommendation['action'])

        citations = data.get('citations', [])
        if citations:
            doc.add_heading(f'Citations ({len(citations)})', level=1)
            for c in citations:
                text = c.get('custom_format') or c.get('bibtex') or ''
                if text:
                    para = doc.add_paragraph(text)
                    para.runs[0].font.name = 'Courier New'
                    para.runs[0].font.size = Pt(8)

        doc.save(tmp_path)

        response = _send_generated_file(
            tmp_path,
            'application/vnd.openxmlformats-officedocument.wordprocessingml.document',
            filename,
        )
        tmp_path = None
        return response

    except ImportError:
        return jsonify({'error': 'python-docx is not installed. Run: pip install python-docx'}), 500
    except Exception as e:
        if tmp_path:
            try:
                os.unlink(tmp_path)
            except OSError:
                pass
        app.logger.exception('DOCX export failed')
        return jsonify({'error': 'Internal server error'}), 500


# ─── Plagiarism / Similarity Checker ───────────────────────────────────────

@app.route('/plagiarism')
def plagiarism_page():
    return render_template('plagiarism.html')


@limiter.limit("10 per minute")
@app.route('/check-plagiarism', methods=['POST'])
def check_plagiarism():
    try:
        data = _json_object()
        if data is None:
            return jsonify({'error': 'Invalid JSON object'}), 400
        text = _safe_text(data.get('text'))
        if not text:
            return jsonify({'error': 'No text provided'}), 400
        if len(text.split()) < 30:
            return jsonify({'error': 'Please provide at least 30 words for meaningful analysis'}), 400

        agent = PlagiarismCheckerAgent()
        result = agent.check(text)
        return jsonify(result)
    except Exception as e:
        app.logger.exception('Plagiarism check failed')
        return jsonify({'error': 'Internal server error'}), 500


# ─── Journal Fit Recommender ────────────────────────────────────────────────

@app.route('/journal-fit')
def journal_fit_page():
    return render_template('journal_fit.html')


@limiter.limit("10 per minute")
@app.route('/recommend-journals', methods=['POST'])
def recommend_journals():
    try:
        data = _json_object()
        if data is None:
            return jsonify({'error': 'Invalid JSON object'}), 400
        if not _text_fields_are_strings(data, 'abstract', 'field'):
            return jsonify({'error': 'Invalid request data'}), 400
        abstract = _safe_text(data.get('abstract'))
        field = _safe_text(data.get('field', ''), max_len=200)
        if not abstract:
            return jsonify({'error': 'Abstract is required'}), 400

        agent = JournalRecommenderAgent()
        result = agent.recommend(abstract, field)
        return jsonify(result)
    except Exception as e:
        app.logger.exception('Journal recommendation failed')
        return jsonify({'error': 'Internal server error'}), 500


# ─── Abstract Screener ──────────────────────────────────────────────────────

@app.route('/abstract-screener')
def abstract_screener_page():
    from src.agents.llm_client import get_provider
    has_key = get_provider() is not None
    return render_template('abstract_screener.html', has_anthropic_key=has_key)


@limiter.limit("10 per minute")
@app.route('/screen-abstracts', methods=['POST'])
def screen_abstracts():
    try:
        data = _json_object()
        if data is None:
            return jsonify({'error': 'Invalid JSON object'}), 400
        abstracts = data.get('abstracts') or []
        criteria = _safe_text(data.get('criteria'))
        if (not isinstance(abstracts, list)
                or not all(isinstance(item, dict)
                           and isinstance(item.get('title', ''), str)
                           and isinstance(item.get('abstract', item.get('text', '')), str)
                           for item in abstracts)):
            return jsonify({'error': 'Invalid request data'}), 400
        if not abstracts:
            return jsonify({'error': 'No abstracts provided'}), 400
        if not criteria:
            return jsonify({'error': 'Inclusion/exclusion criteria are required'}), 400
        if len(abstracts) > 100:
            return jsonify({'error': 'Maximum 100 abstracts per request'}), 400
        if sum(len(item.get('abstract', item.get('text', ''))) for item in abstracts) > _MAX_TEXT_LENGTH:
            return jsonify({'error': 'Abstract text is too long'}), 400

        agent = AbstractScreenerAgent()
        result = agent.screen(abstracts, criteria)
        return jsonify(result)
    except Exception as e:
        app.logger.exception('Abstract screening failed')
        return jsonify({'error': 'Internal server error'}), 500


# ─── Pre-Submission Checklist ───────────────────────────────────────────────

@app.route('/checklist')
def checklist_page():
    from src.agents.llm_client import get_provider
    has_key = get_provider() is not None
    return render_template('checklist.html', has_anthropic_key=has_key)


@limiter.limit("10 per minute")
@app.route('/generate-checklist', methods=['POST'])
def generate_checklist():
    try:
        data = _json_object()
        if data is None:
            return jsonify({'error': 'Invalid JSON object'}), 400
        if not _text_fields_are_strings(
                data, 'manuscript_type', 'journal', 'field', 'abstract'):
            return jsonify({'error': 'Invalid request data'}), 400
        manuscript_type = _safe_text(data.get('manuscript_type', 'Research Article'), max_len=100)
        journal = _safe_text(data.get('journal', ''), max_len=300)
        field = _safe_text(data.get('field', ''), max_len=200)
        abstract = _safe_text(data.get('abstract'))
        if not manuscript_type:
            return jsonify({'error': 'Invalid request data'}), 400

        agent = ChecklistAgent()
        result = agent.generate(manuscript_type, journal, field, abstract)
        return jsonify(result)
    except Exception as e:
        app.logger.exception('Checklist generation failed')
        return jsonify({'error': 'Internal server error'}), 500


# ─── Grant Writer ───────────────────────────────────────────────────────────

@app.route('/grant-writer')
def grant_writer_page():
    from src.agents.llm_client import get_provider
    funders = GrantWriterAgent.get_funders()
    has_key = get_provider() is not None
    return render_template('grant_writer.html', funders=funders, has_anthropic_key=has_key)


@limiter.limit("10 per minute")
@app.route('/write-grant', methods=['POST'])
def write_grant():
    try:
        data = _json_object()
        if data is None:
            return jsonify({'error': 'Invalid JSON object'}), 400
        if not _text_fields_are_strings(
                data, 'project_title', 'description', 'funder', 'field',
                'budget', 'duration', 'team'):
            return jsonify({'error': 'Invalid request data'}), 400
        project_title = _safe_text(data.get('project_title'), max_len=500)
        description = _safe_text(data.get('description'))
        funder = _safe_text(data.get('funder', 'NSF'), max_len=100)
        field = _safe_text(data.get('field', ''), max_len=200)
        budget = _safe_text(data.get('budget', ''), max_len=100)
        duration = _safe_text(data.get('duration', ''), max_len=100)
        team = _safe_text(data.get('team', ''), max_len=5000)

        if not project_title or not description:
            return jsonify({'error': 'Project title and description are required'}), 400

        agent = GrantWriterAgent()
        result = agent.write(project_title, description, funder, field, budget, duration, team)
        return jsonify(result)
    except Exception as e:
        app.logger.exception('Grant writing failed')
        return jsonify({'error': 'Internal server error'}), 500


@app.route('/funders')
def get_funders():
    return jsonify(GrantWriterAgent.get_funders())


# ─── Citation Network Explorer ──────────────────────────────────────────────

@app.route('/citation-network')
def citation_network_page():
    return render_template('citation_network.html')


@limiter.limit("10 per minute")
@app.route('/get-citation-network', methods=['POST'])
def get_citation_network():
    try:
        data = _json_object()
        if data is None:
            return jsonify({'error': 'Invalid JSON object'}), 400
        query = _safe_text(data.get('query'), max_len=500)
        depth = data.get('depth', 1)
        if not query or not isinstance(depth, int) or isinstance(depth, bool) or not 1 <= depth <= 3:
            return jsonify({'error': 'Paper title or ID is required'}), 400

        agent = CitationNetworkAgent()
        result = agent.get_network(query, depth)
        return jsonify(result)
    except Exception as e:
        app.logger.exception('Citation network lookup failed')
        return jsonify({'error': 'Internal server error'}), 500


# ─── Benchmark Dashboard ─────────────────────────────────────────────────────
# Demonstrates the paper's core claim in the running app: the dedicated,
# separately-measured contradiction/gap-detection pipeline vs a naive
# single-LLM baseline, on a frozen worked-example corpus from eval/topics/.

def _eval_topics_dir() -> Path:
    return Path(__file__).resolve().parent / 'eval' / 'topics'


def _list_benchmark_topics():
    topics = []
    topics_dir = _eval_topics_dir()
    if topics_dir.exists():
        for sub in sorted(topics_dir.iterdir()):
            if sub.is_dir() and (sub / 'papers.json').exists():
                info = {}
                topic_json = sub / 'topic.json'
                if topic_json.exists():
                    try:
                        info = json.loads(topic_json.read_text())
                    except (OSError, json.JSONDecodeError):
                        info = {}
                topics.append({'slug': sub.name, 'topic': info.get('topic', sub.name)})
    return topics


@app.route('/access')
def access_router_page():
    """Paywall access router."""
    return render_template('access_router.html')


@app.route('/resolve-access', methods=['POST'])
def resolve_access_route():
    """Find a legal route to the full text of one paper."""
    try:
        data = _json_object()
        if data is None:
            return jsonify({'error': 'Invalid JSON object'}), 400
        query = _safe_text(data.get('query', ''), max_len=500)

        if not query:
            return jsonify({'error': 'Enter a DOI or paper title'}), 400

        institution = data.get('institution', {})
        if not isinstance(institution, dict):
            return jsonify({'error': 'Invalid request data'}), 400
        if not _text_fields_are_strings(
                institution, 'name', 'resolver_url', 'ezproxy_prefix'):
            return jsonify({'error': 'Invalid request data'}), 400
        institution = {
            'name': _safe_text(institution.get('name', ''), max_len=200),
            'resolver_url': _validate_url(institution.get('resolver_url', '')),
            'ezproxy_prefix': _validate_url(institution.get('ezproxy_prefix', '')),
        }

        return jsonify(resolve_access(query, institution=institution))

    except Exception as e:
        app.logger.exception('Access lookup failed')
        return jsonify({'error': 'Internal server error'}), 500


@app.route('/benchmark')
def benchmark_page():
    return render_template('benchmark.html', topics=_list_benchmark_topics())


@limiter.limit("5 per minute")
@app.route('/run-benchmark', methods=['POST'])
def run_benchmark():
    try:
        data = _json_object()
        if data is None:
            return jsonify({'error': 'Invalid JSON object'}), 400
        slug = _safe_text(data.get('slug'), max_len=200)
        topics_by_slug = {t['slug']: t for t in _list_benchmark_topics()}
        if slug not in topics_by_slug:
            return jsonify({'error': 'Unknown worked-example topic. Run eval.snapshot_topic first.'}), 400

        topic_dir = _eval_topics_dir() / slug
        papers_payload = json.loads((topic_dir / 'papers.json').read_text())
        topic_text = topics_by_slug[slug]['topic']

        from src.models.data_models import PaperMetadata
        from src.agents import llm_client

        def run_pipeline():
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            try:
                frozen = [PaperMetadata(**{k: v for k, v in record.items() if k != 'paper_id'})
                          for record in papers_payload]
                system = AutonomousResearchSystem()
                results = loop.run_until_complete(system.research(topic_text, papers=frozen))
                return {
                    'claims': len(results.claims),
                    'contradictions': len(results.contradictions),
                    'gaps': len(results.research_gaps),
                    'usage': results.usage,
                    'run_metadata': results.run_metadata,
                    'sample_gaps': [g.description for g in results.research_gaps[:3]],
                }
            finally:
                loop.close()

        def run_naive_baseline():
            from eval.run_baseline import build_prompt, parse_response, to_predictions
            tracker = llm_client.UsageTracker()
            prompt = build_prompt(topic_text, papers_payload)
            try:
                raw = llm_client.chat(prompt, max_tokens=4000, temperature=0.0,
                                       tracker=tracker, purpose='baseline')
                parsed = parse_response(raw)
            except Exception:
                tracker.record_parse_failure('baseline')
                parsed = {'claims': [], 'contradictions': [], 'gaps': []}
            preds = to_predictions(parsed, papers_payload, tracker.summary())
            return {
                'claims': len(preds['claims']),
                'contradictions': len(preds['contradictions']),
                'gaps': len(preds['gaps']),
                'usage': preds['usage'],
                'sample_gaps': [g.get('description', '') for g in preds['gaps'][:3]],
            }

        return jsonify({
            'topic': topic_text,
            'slug': slug,
            'papers_analyzed': len(papers_payload),
            'dedicated_pipeline': run_pipeline(),
            'naive_baseline': run_naive_baseline(),
        })
    except Exception as e:
        app.logger.exception('Benchmark run failed')
        return jsonify({'error': 'Internal server error'}), 500


def _server_options():
    """Return opt-in development server settings with safe defaults."""
    debug = os.environ.get('FLASK_DEBUG', '').strip().lower() in {'1', 'true', 'yes', 'on'}
    return {
        'debug': debug,
        'host': os.environ.get('HOST') or '127.0.0.1',
        'port': int(os.environ.get('PORT', '5050')),
        'threaded': True,
    }


if __name__ == '__main__':
    # Create output directory
    Path("output").mkdir(exist_ok=True)
    
    print("🌐 Starting Research System Web Interface (Fixed Version)")
    print("📍 Open your browser to: http://localhost:5050")
    print("🧪 Test endpoint: http://localhost:5050/test")
    print("📖 Citations page: http://localhost:5050/citations")
    
    app.run(**_server_options())
