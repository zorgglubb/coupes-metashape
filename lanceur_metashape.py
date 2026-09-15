"""
lanceur_metashape.py
=============================================================
Script Metashape — Fenetre de lancement des outils de coupe.

Outils disponibles :
  - Coupe Ceramique  -> coupe_ceramique7_metashape.py
  - Coupe Bloc       -> coupe_bloc_metashape.py  (a venir)

Placez ce script dans le meme dossier que les autres scripts.
"""

import Metashape
import os
import sys
import subprocess

HERE = os.path.dirname(os.path.abspath(__file__))

# ---------------------------------------------------------------------------
# Utilitaires
# ---------------------------------------------------------------------------

def _run_script(script_name):
    """Execute un script Python dans le meme dossier via exec()."""
    script_path = os.path.join(HERE, script_name)
    if not os.path.isfile(script_path):
        Metashape.app.messageBox(
            "Script introuvable :\n{0}\n\n"
            "Placez le fichier dans le meme dossier que lanceur_metashape.py.".format(script_path))
        return
    try:
        with open(script_path, 'r', encoding='utf-8') as f:
            code = f.read()
        # Executer dans un namespace propre avec Metashape disponible
        ns = {'__file__': script_path, '__name__': '__main__'}
        exec(compile(code, script_path, 'exec'), ns)
    except SystemExit:
        pass
    except Exception as e:
        import traceback
        Metashape.app.messageBox(
            "Erreur lors de l'execution de {0} :\n{1}\n\n{2}".format(
                script_name, str(e), traceback.format_exc()[-800:]))


def _open_pdf(pdf_name):
    """Ouvre un PDF situe dans le meme dossier avec le lecteur systeme."""
    pdf_path = os.path.join(HERE, pdf_name)
    if not os.path.isfile(pdf_path):
        Metashape.app.messageBox(
            "PDF introuvable :\n{0}\n\n"
            "Placez le fichier dans le meme dossier que lanceur_metashape.py.".format(pdf_path))
        return
    try:
        if sys.platform == 'win32':
            os.startfile(pdf_path)
        elif sys.platform == 'darwin':
            subprocess.Popen(['open', pdf_path])
        else:
            subprocess.Popen(['xdg-open', pdf_path])
    except Exception as e:
        Metashape.app.messageBox("Impossible d'ouvrir le PDF :\n{0}".format(str(e)))


# ---------------------------------------------------------------------------
# Fenetre principale
# ---------------------------------------------------------------------------

def show_launcher():
    try:
        from PySide2 import QtWidgets, QtCore, QtGui
    except ImportError:
        try:
            from PySide6 import QtWidgets, QtCore, QtGui
        except ImportError:
            Metashape.app.messageBox(
                "PySide2/PySide6 introuvable.\n"
                "Lancez les scripts directement depuis Metashape > Tools > Run Script.")
            return

    app = QtWidgets.QApplication.instance() or QtWidgets.QApplication(sys.argv)

    dlg = QtWidgets.QDialog()
    dlg.setWindowTitle("Outils de Coupe")
    dlg.setMinimumWidth(420)
    dlg.setWindowFlags(dlg.windowFlags() | QtCore.Qt.WindowStaysOnTopHint)

    # Style general
    dlg.setStyleSheet("""
        QDialog {
            background-color: #2b2b2b;
        }
        QLabel#titre {
            color: #e8e8e8;
            font-size: 15px;
            font-weight: bold;
            padding: 10px 0px 6px 0px;
        }
        QLabel#sous_titre {
            color: #999999;
            font-size: 11px;
            padding: 0px 0px 14px 0px;
        }
        QPushButton#btn_outil {
            background-color: #4a7fc1;
            color: white;
            border: none;
            border-radius: 6px;
            font-size: 13px;
            font-weight: bold;
            padding: 12px 20px;
            text-align: left;
        }
        QPushButton#btn_outil:hover {
            background-color: #5a8fd1;
        }
        QPushButton#btn_outil:pressed {
            background-color: #3a6fb1;
        }
        QPushButton#btn_outil:disabled {
            background-color: #444444;
            color: #777777;
        }
        QPushButton#btn_aide {
            background-color: #555555;
            color: #dddddd;
            border: none;
            border-radius: 5px;
            font-size: 12px;
            font-weight: bold;
            min-width: 28px;
            max-width: 28px;
            min-height: 28px;
            max-height: 28px;
        }
        QPushButton#btn_aide:hover {
            background-color: #e8a020;
            color: white;
        }
        QPushButton#btn_aide:pressed {
            background-color: #c88010;
        }
        QPushButton#btn_fermer {
            background-color: #555555;
            color: #dddddd;
            border: none;
            border-radius: 5px;
            font-size: 11px;
            padding: 7px 18px;
        }
        QPushButton#btn_fermer:hover {
            background-color: #666666;
        }
        QFrame#separateur {
            color: #444444;
        }
    """)

    layout = QtWidgets.QVBoxLayout(dlg)
    layout.setContentsMargins(24, 18, 24, 18)
    layout.setSpacing(0)

    # Titre
    lbl_titre = QtWidgets.QLabel("Outils de Coupe")
    lbl_titre.setObjectName("titre")
    lbl_titre.setAlignment(QtCore.Qt.AlignCenter)
    layout.addWidget(lbl_titre)

    lbl_sous = QtWidgets.QLabel("Photogrammetrie archeologique — M. Belarbi / Claude.ai")
    lbl_sous.setObjectName("sous_titre")
    lbl_sous.setAlignment(QtCore.Qt.AlignCenter)
    layout.addWidget(lbl_sous)

    # Separateur
    sep1 = QtWidgets.QFrame()
    sep1.setObjectName("separateur")
    sep1.setFrameShape(QtWidgets.QFrame.HLine)
    sep1.setStyleSheet("QFrame { color: #444444; margin-bottom: 16px; }")
    layout.addWidget(sep1)

    # --- Ligne Coupe Ceramique ---
    row1 = QtWidgets.QHBoxLayout()
    row1.setSpacing(8)

    btn_ceramique = QtWidgets.QPushButton("  ▶   Coupe Ceramique")
    btn_ceramique.setObjectName("btn_outil")
    btn_ceramique.setToolTip("Lance coupe_ceramique7_metashape.py")
    btn_ceramique.setCursor(QtCore.Qt.PointingHandCursor)

    btn_aide1 = QtWidgets.QPushButton("?")
    btn_aide1.setObjectName("btn_aide")
    btn_aide1.setToolTip("Ouvrir le mode d'emploi PDF — Coupe Ceramique")
    btn_aide1.setCursor(QtCore.Qt.PointingHandCursor)

    row1.addWidget(btn_ceramique, 1)
    row1.addWidget(btn_aide1, 0)
    layout.addLayout(row1)
    layout.addSpacing(10)

    # --- Ligne Coupe Bloc ---
    row2 = QtWidgets.QHBoxLayout()
    row2.setSpacing(8)

    btn_bloc = QtWidgets.QPushButton("  ▶   Coupe Bloc")
    btn_bloc.setObjectName("btn_outil")
    btn_bloc.setToolTip("Lance coupe_bloc_metashape.py")
    btn_bloc.setCursor(QtCore.Qt.PointingHandCursor)
    btn_bloc.setEnabled(True)

    btn_aide2 = QtWidgets.QPushButton("?")
    btn_aide2.setObjectName("btn_aide")
    btn_aide2.setToolTip("Ouvrir le mode d'emploi PDF — Coupe Bloc")
    btn_aide2.setCursor(QtCore.Qt.PointingHandCursor)
    btn_aide2.setEnabled(True)

    row2.addWidget(btn_bloc, 1)
    row2.addWidget(btn_aide2, 0)
    layout.addLayout(row2)

    # Separateur bas
    sep2 = QtWidgets.QFrame()
    sep2.setFrameShape(QtWidgets.QFrame.HLine)
    sep2.setStyleSheet("QFrame { color: #444444; margin-top: 16px; margin-bottom: 10px; }")
    layout.addWidget(sep2)

    # Bouton Fermer
    row_bas = QtWidgets.QHBoxLayout()
    row_bas.addStretch()
    btn_fermer = QtWidgets.QPushButton("Fermer")
    btn_fermer.setObjectName("btn_fermer")
    btn_fermer.setCursor(QtCore.Qt.PointingHandCursor)
    row_bas.addWidget(btn_fermer)
    layout.addLayout(row_bas)

    # --- Connexions ---
    def on_ceramique():
        dlg.hide()
        _run_script("coupe_ceramique7_metashape.py")
        dlg.close()

    def on_bloc():
        dlg.hide()
        _run_script("coupe_bloc_metashape.py")
        dlg.close()

    def on_aide_ceramique():
        _open_pdf("mode_emploi_coupe_ceramique.pdf")

    def on_aide_bloc():
        _open_pdf("mode_emploi_coupe_bloc.pdf")

    btn_ceramique.clicked.connect(on_ceramique)
    btn_bloc.clicked.connect(on_bloc)
    btn_aide1.clicked.connect(on_aide_ceramique)
    btn_aide2.clicked.connect(on_aide_bloc)
    btn_fermer.clicked.connect(dlg.close)

    dlg.exec_()


# ---------------------------------------------------------------------------
# Point d'entree
# ---------------------------------------------------------------------------
show_launcher()
