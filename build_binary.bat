@echo off
set PYI=pyinstaller
%PYI% --clean --onefile --name rp_extractor rp_extractor.py
%PYI% --clean --onefile --noconsole --name rp_extractor_gui rp_extractor_gui_tk.py
echo Built EXEs in .\dist
