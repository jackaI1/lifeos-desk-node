from pathlib import Path

import FreeCAD as App
import pytest

from freecad_tools.gui import open_assembly


def test_gui_opener_rejects_headless_use_without_opening_documents():
    before = set(App.listDocuments())
    with pytest.raises(RuntimeError, match="GUI"):
        open_assembly(Path("examples/sample-output/assembly.FCStd"))
    assert set(App.listDocuments()) == before
