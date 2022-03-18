# Building

python setup.py sdist
python setup.py bdist_wheel

# Uploading

twine upload --skip-existing dist/*
twine upload --skip-existing --repository testpypi dist/*

# Testing

pip install py3createtorrent
pip install --index-url https://test.pypi.org/simple/ --extra-index-url https://pypi.org/simple py3createtorrent
