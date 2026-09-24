PY := ../.venv/bin/python   # gear-kb's own venv (pyyaml is all the app needs)

.PHONY: data ports icons serve test setup

setup:            ## install the app's few packages into gear-kb's venv
	../.venv/bin/pip install -q -r requirements.txt

ports:            ## seed jacks from the gear-kb manuals -> data/ports.seed.yaml
	$(PY) tools/extract_ports.py

icons:            ## copy gear-kb's original drawings -> icons/*.svg (+ icons/_sheet.html contact sheet)
	$(PY) tools/trace_icons.py --sheet

data: ports       ## rebuild data/gear.json from gear-kb (run after new manuals/inventory/wiring)
	$(PY) tools/build_data.py

serve:            ## run the app on http://127.0.0.1:8765/
	$(PY) tools/patchbay.py --open

test:
	$(PY) -m unittest discover -s tests -v
