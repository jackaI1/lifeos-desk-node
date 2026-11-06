"""Open headless exports with a useful assembly view in the FreeCAD desktop."""

from pathlib import Path

import FreeCAD as App


def open_assembly(path):
    if not App.GuiUp:
        raise RuntimeError("Open this file through a FreeCAD GUI macro, not headless Python")
    import FreeCADGui as Gui

    # Explicitly load the trusted toolkit before document restore in FreeCAD 1.1.
    from . import parts  # noqa: F401

    existing = set(App.listDocuments())
    document = None
    try:
        document = App.openDocument(str(Path(path).resolve()))
        root = document.getObject("Assembly")
        library = document.getObject("Library")
        if root is None or library is None:
            raise ValueError("This document needs Assembly and Library groups")
        library.ViewObject.Visibility = False
        for part in library.Group:
            part.ViewObject.Visibility = False
        root.ViewObject.Visibility = True
        for occurrence in root.Group:
            occurrence.ViewObject.Visibility = True
        Gui.activeDocument().activeView().viewAxonometric()
        Gui.activeDocument().activeView().fitAll()
        return document
    except Exception:
        if document is not None and document.Name not in existing:
            App.closeDocument(document.Name)
        raise
