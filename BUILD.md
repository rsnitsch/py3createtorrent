# How to build and upload to PyPI

## Build

```
python -m build
twine check dist/*
```

## Upload

### 1. Configuring the API token

Generate an API token at https://pypi.org/manage/account/ and then save the following to `$HOME/.pypirc`:

    [distutils]
    index-servers =
        py3createtorrent

    [py3createtorrent]
    repository = https://upload.pypi.org/legacy/
    username = __token__
    password = <INSERT API TOKEN HERE>

### 2. Executing the upload

```
twine upload --skip-existing --repository py3createtorrent dist/*
twine upload --skip-existing --repository testpypi dist/*
```

## Test `pip install`

```sh
pip install py3createtorrent
pip install --index-url https://test.pypi.org/simple/ --extra-index-url https://pypi.org/simple py3createtorrent
```
