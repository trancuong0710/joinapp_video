"""
Backward compatibility shim for app_gui.
Re-exports MainWindow as VideoJoinerApp and run_app.
"""
from src.ui.main_window import MainWindow, run_app, DragDropCTk

# Alias VideoJoinerApp to MainWindow for backward compatibility
VideoJoinerApp = MainWindow

__all__ = ["MainWindow", "VideoJoinerApp", "run_app", "DragDropCTk"]
