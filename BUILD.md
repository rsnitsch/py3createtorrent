# Building

python setup.py sdist
python setup.py bdist_wheel

# Uploading

twine upload dist/*
twine upload --repository testpypi dist/*

# Testing

pip install py3createtorrent
pip install --index-url https://test.pypi.org/simple/ --extra-index-url https://pypi.org/simple py3createtorrent
