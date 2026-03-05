#!/bin/sh

touch tests/__init__.py
touch tests/studio_tests/__init__.py
touch tests/product_tests/__init__.py
python -m pytest --verbose tests 2>&1 | tee pytest_log.txt
