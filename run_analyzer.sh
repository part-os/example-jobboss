#!/bin/bash

cd /home/paperless/connector/example-jobboss
source /home/paperless/connector/osenv/bin/activate
export PYTHONPATH="/home/paperless/connector/example-jobboss/core-python:/home/paperless/connector/example-jobboss/jobboss-python"
python analyzer.py
