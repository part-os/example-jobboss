call osenv\Scripts\activate
set PYTHONPATH=%PYTHONPATH%;jobboss-python;core-python
set DJANGO_SETTINGS_MODULE=jobboss.settings
python connector.py
