# conftest.py
def pytest_addoption(parser):
    parser.addoption("--singleton_file", action="store", default=None, help="Path to the singleton file")
