import subprocess
import uuid
from pathlib import Path
from zipfile import ZipFile

import streamlit as st

BASE_DIR = Path(__file__).resolve().parent
WORK_DIR = BASE_DIR / 'work'
WORK_DIR.mkdir(exist_ok=True)
MAX_LOG_SNIPPET = 2000


def write_log(path: Path, content: str) -> None:
  path.parent.mkdir(parents=True, exist_ok=True)
  path.write_text(content)


def run_subprocess(command, cwd, timeout=None):
    return subprocess.run(
        command,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        cwd=cwd,
        timeout=timeout
    )


def create_zip(kml_files, zip_path: Path):
  with ZipFile(zip_path, 'w') as zip_file:
    for file_path in kml_files:
      zip_file.write(file_path, arcname=file_path.name)


def display_log_snippet(content: str):
  snippet = content[:MAX_LOG_SNIPPET]
  st.code(snippet or 'Log vuoto')


st.set_page_config(page_title='Recce Webapp')
st.title('Recce Webapp – GPX → KML')
st.write('Incolla un link Rallymaps e ottieni uno ZIP con i KML generati automaticamente.')

url = st.text_input('Link Rallymaps')
run_job = st.button('Genera KML')

if run_job:
  if not url.strip():
    st.error('Per favore incolla un link Rallymaps valido.')
    st.stop()

  job_id = uuid.uuid4().hex[:12]
  job_root = WORK_DIR / job_id
  desktop_dir = job_root / 'Desktop'
  kml_dir = job_root / 'kml'
  logs_dir = job_root / 'logs'

  for directory in (desktop_dir, kml_dir, logs_dir):
    directory.mkdir(parents=True, exist_ok=True)

  st.info(f'Job ID: {job_id}')

  node_command = ['node', str(BASE_DIR / 'rally2gpx' / 'index_all.js'), url.strip(), str(desktop_dir)]
  with st.spinner('Scarico i GPX da Rallymaps...'):
    node_result = run_subprocess(node_command, cwd=BASE_DIR)
  node_log_path = logs_dir / 'rally2gpx.log'
  write_log(node_log_path, node_result.stdout)

  if node_result.returncode != 0:
    st.error('Errore durante la generazione dei GPX con Node.js')
    st.caption('Estratto log rally2gpx:')
    display_log_snippet(node_result.stdout)
    st.stop()

  gpx_files = sorted(desktop_dir.glob('*.gpx'))
  if not gpx_files:
    st.error('Nessun file GPX trovato dopo la fase Node. Controlla il log in logs/rally2gpx.log')
    st.stop()

  conversion_results = []
  with st.spinner('Converto GPX in KML...'):
    for gpx_path in gpx_files:
      kml_path = kml_dir / f'{gpx_path.stem}.kml'
      python_command = ['python3', 'curve_detector.py', str(gpx_path), str(kml_path)]
      result = run_subprocess(python_command, cwd=BASE_DIR)
      log_path = logs_dir / f'{gpx_path.stem}.log'
      write_log(log_path, result.stdout)
      conversion_results.append({
        'gpx': gpx_path,
        'kml': kml_path,
        'success': result.returncode == 0 and kml_path.exists(),
        'log_path': log_path
      })

  successful_kmls = [entry['kml'] for entry in conversion_results if entry['success']]
  if not successful_kmls:
    st.error('Tutte le conversioni KML sono fallite. Controlla i log nelle cartelle di lavoro.')
    st.stop()

  zip_path = job_root / 'KML_ALL.zip'
  create_zip(successful_kmls, zip_path)

  st.success(f'Conversione completata. File KML generati: {len(successful_kmls)}')

  failed = [entry for entry in conversion_results if not entry['success']]
  if failed:
    st.warning(f"Alcuni GPX non sono stati convertiti correttamente ({len(failed)} falliti).")

  zip_data = zip_path.read_bytes()
  st.download_button('Scarica KML_ALL.zip', data=zip_data, file_name='KML_ALL.zip', mime='application/zip')

  with st.expander('Log rally2gpx'):
    display_log_snippet(node_log_path.read_text())

  for entry in conversion_results:
    label = f"Log {entry['gpx'].name}"
    with st.expander(label):
      display_log_snippet(Path(entry['log_path']).read_text())
