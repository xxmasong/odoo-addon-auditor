import { AUDITOR_SOURCES } from './auditor-src.js'
import { SAMPLES } from './samples.js'

const el = (id) => document.getElementById(id)
const state = { pyodide: null, files: {}, active: null }

/** Boot Pyodide and write the real package into its virtual filesystem. */
async function boot() {
  setStatus('loading Python…', 'busy')

  const pyodide = await loadPyodide({
    indexURL: 'https://cdn.jsdelivr.net/pyodide/v0.26.4/full/',
  })

  // The package is pure standard library, so it runs unmodified. Nothing here
  // reimplements the rules: the page reports exactly what the CLI reports.
  for (const [path, source] of Object.entries(AUDITOR_SOURCES)) {
    const dir = path.split('/').slice(0, -1).join('/')
    if (dir) pyodide.FS.mkdirTree(dir)
    pyodide.FS.writeFile(path, source)
  }

  await pyodide.runPythonAsync(`
import sys, json, pathlib, shutil
sys.path.insert(0, '')

from odoo_auditor.scanner import audit_addon

def run_audit(payload):
    """Write the supplied files to a scratch addon and audit it."""
    files = json.loads(payload)
    root = pathlib.Path('/tmp/addon')
    if root.exists():
        shutil.rmtree(root)
    root.mkdir(parents=True)

    for name, text in files.items():
        target = root / name
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(text, encoding='utf-8')

    report = audit_addon(root)
    return json.dumps({
        'blocking': report.blocking,
        'findings': [f.as_dict() for f in report.findings],
    })
`)

  state.pyodide = pyodide
  setStatus('ready', 'ok')
  el('run').disabled = false
}

function setStatus(text, kind) {
  const node = el('status')
  node.textContent = text
  node.className = `status status-${kind}`
}

function renderTabs() {
  const tabs = el('tabs')
  tabs.innerHTML = ''

  for (const name of Object.keys(state.files)) {
    const tab = document.createElement('button')
    tab.className = 'tab'
    tab.textContent = name
    tab.setAttribute('role', 'tab')
    tab.setAttribute('aria-selected', String(name === state.active))
    tab.onclick = () => {
      // Keep edits to the current file before switching away.
      state.files[state.active] = el('editor').value
      state.active = name
      renderTabs()
      el('editor').value = state.files[name]
    }
    tabs.append(tab)
  }
}

function loadSample(key) {
  const sample = SAMPLES[key]
  state.files = { ...sample.files }
  state.active = Object.keys(sample.files)[0]
  renderTabs()
  el('editor').value = state.files[state.active]
  el('results').innerHTML = '<p class="placeholder">Run the audit to see findings.</p>'
}

async function run() {
  if (!state.pyodide) return

  state.files[state.active] = el('editor').value
  el('run').disabled = true
  setStatus('auditing…', 'busy')

  try {
    const raw = state.pyodide.globals.get('run_audit')(JSON.stringify(state.files))
    renderResults(JSON.parse(raw))
    setStatus('ready', 'ok')
  } catch (error) {
    el('results').innerHTML =
      `<p class="placeholder">The audit failed: ${escapeHtml(String(error))}</p>`
    setStatus('error', 'err')
  } finally {
    el('run').disabled = false
  }
}

function escapeHtml(text) {
  const div = document.createElement('div')
  div.textContent = text
  return div.innerHTML
}

function renderResults({ findings, blocking }) {
  const results = el('results')

  if (findings.length === 0) {
    results.innerHTML =
      '<p class="clean">No findings. This addon is clean — which a linter has to ' +
      'get right as often as it catches things, or people switch it off.</p>'
    return
  }

  const counts = findings.reduce((acc, f) => {
    acc[f.severity] = (acc[f.severity] ?? 0) + 1
    return acc
  }, {})

  const summary = Object.entries(counts)
    .map(([sev, n]) => `${n} ${sev}`)
    .join(', ')

  const verdict = blocking
    ? '<p class="verdict verdict-block">Blocking: installing this risks breaking ' +
      'records the addon does not own.</p>'
    : '<p class="verdict">No critical findings.</p>'

  results.innerHTML =
    verdict +
    `<p class="summary">${summary}</p>` +
    findings
      .map(
        (f) => `
      <article class="finding finding-${f.severity}">
        <header>
          <span class="sev">${f.severity}</span>
          <code class="loc">${escapeHtml(f.path)}:${f.line}</code>
          <span class="rule">${escapeHtml(f.rule)}</span>
        </header>
        <p class="msg">${escapeHtml(f.message)}</p>
        ${f.snippet ? `<pre class="snippet">${escapeHtml(f.snippet)}</pre>` : ''}
        ${f.remedy ? `<p class="remedy">${escapeHtml(f.remedy)}</p>` : ''}
      </article>`,
      )
      .join('')
}

el('sample').onchange = (event) => loadSample(event.target.value)
el('run').onclick = run

for (const [key, sample] of Object.entries(SAMPLES)) {
  const option = document.createElement('option')
  option.value = key
  option.textContent = sample.label
  el('sample').append(option)
}

loadSample('broken')
boot().catch((error) => {
  setStatus('failed to load Python', 'err')
  el('results').innerHTML =
    `<p class="placeholder">Pyodide could not start: ${escapeHtml(String(error))}</p>`
})
