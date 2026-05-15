"""
Qt compatibility shim. Tries PySide6 → PyQt6 → PyQt5 in order.
Import all Qt symbols from here instead of directly from Qt packages.
"""
try:
    from PySide6.QtWidgets import (
        QDialog, QVBoxLayout, QHBoxLayout, QLabel,
        QLineEdit, QPushButton, QTextEdit, QFileDialog,
        QMessageBox, QCheckBox, QProgressBar, QComboBox,
        QTabWidget, QWidget, QGridLayout, QScrollArea,
        QFrame, QGroupBox, QListWidget, QListWidgetItem,
        QTextBrowser,
    )
    from PySide6.QtCore import Qt, QThread, Signal as pyqtSignal, QObject, QWaitCondition, QMutex, QTimer
    from PySide6.QtGui import QDragEnterEvent, QDropEvent, QIcon
    QT_NAME = "PySide6"
except ImportError:
    try:
        from PyQt6.QtWidgets import (
            QDialog, QVBoxLayout, QHBoxLayout, QLabel,
            QLineEdit, QPushButton, QTextEdit, QFileDialog,
            QMessageBox, QCheckBox, QProgressBar, QComboBox,
            QTabWidget, QWidget, QGridLayout, QScrollArea,
            QFrame, QGroupBox, QListWidget, QListWidgetItem,
            QTextBrowser,
        )
        from PyQt6.QtCore import Qt, QThread, pyqtSignal, QObject, QWaitCondition, QMutex, QTimer
        from PyQt6.QtGui import QDragEnterEvent, QDropEvent, QIcon
        QT_NAME = "PyQt6"
    except ImportError:
        from PyQt5.QtWidgets import (
            QDialog, QVBoxLayout, QHBoxLayout, QLabel,
            QLineEdit, QPushButton, QTextEdit, QFileDialog,
            QMessageBox, QCheckBox, QProgressBar, QComboBox,
            QTabWidget, QWidget, QGridLayout, QScrollArea,
            QFrame, QGroupBox, QListWidget, QListWidgetItem,
            QTextBrowser,
        )
        from PyQt5.QtCore import Qt, QThread, pyqtSignal, QObject, QWaitCondition, QMutex, QTimer
        from PyQt5.QtGui import QDragEnterEvent, QDropEvent, QIcon
        QT_NAME = "PyQt5"

__all__ = [
    "QT_NAME",
    "QDialog", "QVBoxLayout", "QHBoxLayout", "QLabel",
    "QLineEdit", "QPushButton", "QTextEdit", "QFileDialog",
    "QMessageBox", "QCheckBox", "QProgressBar", "QComboBox",
    "QTabWidget", "QWidget", "QGridLayout", "QScrollArea",
    "QFrame", "QGroupBox", "QListWidget", "QListWidgetItem",
    "QTextBrowser",
    "Qt", "QThread", "pyqtSignal", "QObject", "QWaitCondition", "QMutex", "QTimer",
    "QDragEnterEvent", "QDropEvent", "QIcon",
]
