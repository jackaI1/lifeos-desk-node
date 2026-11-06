import pytest


@pytest.fixture
def doc():
    import FreeCAD as App

    document = App.newDocument("TestMount")
    name = document.Name
    try:
        yield document
    finally:
        if name in App.listDocuments():
            App.closeDocument(name)
