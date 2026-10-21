# conftest.py
def pytest_addoption(parser):
    parser.addoption(
        "--sequence_file",
        action="store",
        default=None,
        help="Path to the sequence file"
    )
